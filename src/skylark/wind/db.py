from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, Float, Text, select, insert, update, event
from alembic import command
from alembic.config import Config
from .domain import canonical, digest

metadata = MetaData()
runs = Table("runs", metadata,
    Column("id", String, primary_key=True), Column("request_key", String, unique=True, nullable=False),
    Column("request_hash", String, nullable=False), Column("snapshot", Text, nullable=False),
    Column("status", String, nullable=False), Column("created", Float, nullable=False), Column("updated", Float, nullable=False),
    Column("owner", String), Column("cancel_requested", Integer, nullable=False, default=0),
    Column("result", Text), Column("state", Text), Column("error", Text), Column("sequence", Integer, nullable=False, default=0),
    Column("artifact_bytes", Integer, nullable=False, default=0), Column("comparison_id", String))
events = Table("events", metadata, Column("id", String, primary_key=True), Column("run_id", String, nullable=False, index=True),
    Column("sequence", Integer, nullable=False), Column("kind", String, nullable=False), Column("payload", Text, nullable=False), Column("created", Float, nullable=False))
workers = Table("workers", metadata, Column("id", Integer, primary_key=True), Column("owner", String), Column("expires", Float, nullable=False))
repairs = Table("repairs", metadata, Column("id", String, primary_key=True), Column("run_id", String, nullable=False),
    Column("payload", Text, nullable=False), Column("approved", Integer, nullable=False, default=0), Column("created", Float, nullable=False))
comparisons = Table("comparisons", metadata, Column("id", String, primary_key=True), Column("payload", Text, nullable=False), Column("created", Float, nullable=False))
usage = Table("usage", metadata, Column("id", String, primary_key=True), Column("run_id", String, nullable=False),
    Column("reserved_micros", Integer, nullable=False), Column("accounted_micros", Integer, nullable=False),
    Column("status", String, nullable=False), Column("payload", Text, nullable=False), Column("created", Float, nullable=False))
reconciliations = Table("reconciliations", metadata, Column("id", String, primary_key=True), Column("attempt_id", String, nullable=False),
    Column("payload", Text, nullable=False), Column("created", Float, nullable=False))


class Conflict(ValueError): pass
class LeaseLost(RuntimeError): pass
class BudgetExceeded(RuntimeError): pass


class Database:
    def __init__(self, directory: str | Path, *, _restoring=False):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        if (self.directory / "RESTORE_INCOMPLETE").exists() and not _restoring:
            raise ValueError("Restore did not complete; execution disabled. Restore the original backup into another new directory.")
        self.path = self.directory / "agent-lab.sqlite3"
        self.engine = create_engine("sqlite:///" + self.path.as_posix(), connect_args={"timeout": 15, "check_same_thread": False})
        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA busy_timeout=15000")
            connection.execute("PRAGMA foreign_keys=ON")
            deadline = time.monotonic() + 15
            while True:
                try:
                    # WAL is persistent. Avoid requesting its write lock on
                    # every connection; initial concurrent upgrades can still
                    # return SQLITE_BUSY without honoring the busy timeout.
                    mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                    if mode != "wal":
                        mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                    if mode != "wal":
                        raise RuntimeError("SQLite could not enable WAL; startup stopped")
                    break
                except sqlite3.OperationalError as exc:
                    code = getattr(exc, "sqlite_errorcode", 0) & 0xff
                    if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) or time.monotonic() >= deadline:
                        raise
                    time.sleep(.05)
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        # Multiple CLI/worker processes can start together. Serialize migrations,
        # including their version check, rather than racing create_all/ALTERs.
        with self.transaction() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "head")

    @contextmanager
    def transaction(self):
        with self.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @staticmethod
    def decode(row):
        if row is None:
            return None
        result = dict(row)
        for key in ("snapshot", "result", "state", "payload"):
            if key in result and result[key] is not None:
                result[key] = json.loads(result[key])
        return result

    def enqueue(self, snapshot, key: str, comparison_id=None):
        with self.transaction() as conn:
            old = conn.execute(select(runs).where(runs.c.request_key == key)).mappings().first()
            if old:
                if old["request_hash"] != digest(snapshot):
                    raise Conflict("Request key already used with a different experiment")
                return old["id"]
            run_id = uuid.uuid4().hex
            conn.execute(insert(runs).values(id=run_id, request_key=key, request_hash=digest(snapshot), snapshot=canonical(snapshot),
                status="queued", created=time.time(), updated=time.time(), cancel_requested=0, sequence=0, artifact_bytes=0, comparison_id=comparison_id))
            return run_id

    def get(self, run_id):
        with self.engine.connect() as conn:
            return self.decode(conn.execute(select(runs).where(runs.c.id == run_id)).mappings().first())

    def list_runs(self, limit=100):
        with self.engine.connect() as conn:
            return [self.decode(r) for r in conn.execute(select(runs).order_by(runs.c.created.desc()).limit(limit)).mappings()]

    def claim(self, owner, adapter_name=None, run_id=None):
        now = time.time()
        with self.transaction() as conn:
            lease = conn.execute(select(workers).where(workers.c.id == 1)).mappings().first()
            if lease and lease["expires"] > now:
                return None
            # A stale owner is fenced before any new work. Never retry its uncertain attempt.
            conn.execute(update(runs).where(runs.c.status == "running").values(status="interrupted", updated=now,
                error="Worker lease expired; no automatic retry. Preserved observations are incomplete.", result=canonical({"verdict": "inconclusive", "assertions": []})))
            candidates = conn.execute(select(runs).where(runs.c.status == "queued").order_by(runs.c.created)).mappings()
            row = None
            for candidate in candidates:
                spec = json.loads(candidate["snapshot"])["spec"]
                if run_id and candidate["id"] != run_id:
                    continue
                if spec["mode"] == "local_adapter" and spec["agent_version"] != adapter_name:
                    continue
                row = candidate
                break
            if not row:
                return None
            if lease:
                conn.execute(update(workers).where(workers.c.id == 1).values(owner=owner, expires=now + 20))
            else:
                conn.execute(insert(workers).values(id=1, owner=owner, expires=now + 20))
            conn.execute(update(runs).where(runs.c.id == row["id"]).values(owner=owner, status="running", updated=now))
            return row["id"]

    def heartbeat(self, owner):
        with self.transaction() as conn:
            result = conn.execute(update(workers).where(workers.c.id == 1, workers.c.owner == owner, workers.c.expires > time.time()).values(expires=time.time() + 20))
            return result.rowcount == 1

    def fenced(self, conn, run_id, owner):
        lease = conn.execute(select(workers).where(workers.c.id == 1, workers.c.owner == owner, workers.c.expires > time.time())).first()
        row = conn.execute(select(runs).where(runs.c.id == run_id, runs.c.owner == owner, runs.c.status == "running")).mappings().first()
        if not lease or not row:
            raise LeaseLost("Worker ownership expired; refusing late writes")
        return row

    def owns(self, run_id, owner):
        with self.engine.connect() as conn:
            try:
                self.fenced(conn, run_id, owner)
                return True
            except LeaseLost:
                return False

    def append(self, run_id, owner, kind, payload, *, state=None, event_id=None):
        body = canonical(payload)
        if len(body.encode()) > 65536:
            raise ValueError("Event exceeds 64 KB; execution stopped without truncating evidence")
        event_id = event_id or uuid.uuid4().hex
        with self.transaction() as conn:
            row = self.fenced(conn, run_id, owner)
            previous = conn.execute(select(events).where(events.c.id == event_id)).mappings().first()
            if previous:
                if previous["run_id"] != run_id or previous["payload"] != body or previous["kind"] != kind:
                    raise Conflict("Conflicting event identity")
                return previous["sequence"]
            size = row["artifact_bytes"] + len(body.encode())
            if size > 8_000_000:
                raise ValueError("Run trace limit reached; no events were silently dropped")
            sequence = row["sequence"] + 1
            conn.execute(insert(events).values(id=event_id, run_id=run_id, sequence=sequence, kind=kind, payload=body, created=time.time()))
            values = {"sequence": sequence, "artifact_bytes": size, "updated": time.time()}
            if state is not None:
                values["state"] = canonical(state)
            conn.execute(update(runs).where(runs.c.id == run_id).values(**values))
            return sequence

    def read_events(self, run_id, after=0):
        with self.engine.connect() as conn:
            return [self.decode(r) for r in conn.execute(select(events).where(events.c.run_id == run_id, events.c.sequence > after).order_by(events.c.sequence)).mappings()]

    def finish(self, run_id, owner, status, result, error=None):
        with self.transaction() as conn:
            row = self.fenced(conn, run_id, owner)
            if row["cancel_requested"]:
                status, result = "cancelled", {**result, "verdict": "inconclusive"}
            conn.execute(update(runs).where(runs.c.id == run_id).values(status=status, result=canonical(result), error=error, updated=time.time()))
            conn.execute(update(workers).where(workers.c.owner == owner).values(expires=0))

    def cancel(self, run_id):
        with self.transaction() as conn:
            row = conn.execute(select(runs).where(runs.c.id == run_id)).mappings().first()
            if not row:
                raise KeyError(run_id)
            if row["status"] == "queued":
                conn.execute(update(runs).where(runs.c.id == run_id).values(cancel_requested=1, status="cancelled", updated=time.time()))
            elif row["status"] == "running":
                conn.execute(update(runs).where(runs.c.id == run_id).values(cancel_requested=1, updated=time.time()))

    def save_repair(self, run_id, payload):
        repair_id = uuid.uuid4().hex
        with self.transaction() as conn:
            conn.execute(insert(repairs).values(id=repair_id, run_id=run_id, payload=canonical(payload), approved=0, created=time.time()))
        return self.get_repair(repair_id)

    def get_repair(self, repair_id):
        with self.engine.connect() as conn:
            return self.decode(conn.execute(select(repairs).where(repairs.c.id == repair_id)).mappings().first())

    def approve(self, repair_id):
        with self.transaction() as conn:
            if not conn.execute(update(repairs).where(repairs.c.id == repair_id).values(approved=1)).rowcount:
                raise KeyError(repair_id)
        return self.get_repair(repair_id)

    def save_comparison(self, comparison_id, payload):
        with self.transaction() as conn:
            conn.execute(insert(comparisons).values(id=comparison_id, payload=canonical(payload), created=time.time()))

    def schedule_comparison(self, comparison_id, payload, snapshots):
        """The pair list and all jobs commit together; interrupted submission leaves neither."""
        with self.transaction() as conn:
            conn.execute(insert(comparisons).values(id=comparison_id, payload=canonical(payload), created=time.time()))
            for run_id, snapshot in snapshots:
                conn.execute(insert(runs).values(id=run_id, request_key=run_id, request_hash=digest(snapshot), snapshot=canonical(snapshot),
                    status="queued", created=time.time(), updated=time.time(), cancel_requested=0, sequence=0, artifact_bytes=0, comparison_id=comparison_id))

    def get_comparison(self, comparison_id):
        with self.engine.connect() as conn:
            return self.decode(conn.execute(select(comparisons).where(comparisons.c.id == comparison_id)).mappings().first())

    def reserve(self, run_id, micros, cap, *, owner=None, payload=None):
        if type(micros) is not int or type(cap) is not int or not 0 < micros <= 2**63-1 or not 0 < cap <= 2**63-1:
            raise BudgetExceeded("Configure a positive measured cost ceiling and allowance")
        with self.transaction() as conn:
            if owner is not None:
                row = self.fenced(conn, run_id, owner)
                if row["cancel_requested"]:
                    raise BudgetExceeded("Cancellation requested; no provider request sent")
            rows = list(conn.execute(select(usage)).mappings())
            if any(json.loads(row["payload"]).get("estimate_exceeded") and not json.loads(row["payload"]).get("anomaly_resolved") for row in rows):
                raise BudgetExceeded("Spending paused after an underestimated charge. Inspect usage and explicitly resolve the anomaly before another request.")
            spent = sum(row["accounted_micros"] for row in rows)
            if spent + micros > cap:
                raise BudgetExceeded("Project allowance reached; no provider request sent")
            attempt_id = uuid.uuid4().hex
            conn.execute(insert(usage).values(id=attempt_id, run_id=run_id, reserved_micros=micros, accounted_micros=micros,
                status="reserved", payload=canonical(payload or {}), created=time.time()))
        return attempt_id

    def settle(self, attempt_id, actual_micros, payload):
        if actual_micros is not None and (type(actual_micros) is not int or not 0 <= actual_micros <= 2**63-1):
            raise ValueError("Reported cost must be a finite nonnegative integer number of microdollars")
        with self.transaction() as conn:
            row = conn.execute(select(usage).where(usage.c.id == attempt_id)).mappings().one()
            if row["status"] != "reserved":
                raise Conflict("Usage attempt already settled")
            details = {**json.loads(row["payload"]), **payload}
            if actual_micros is not None and actual_micros > row["reserved_micros"]:
                details.update(estimate_exceeded=True, anomaly_resolved=False)
            conn.execute(update(usage).where(usage.c.id == attempt_id).values(status="reported" if actual_micros is not None else "uncertain",
                accounted_micros=actual_micros if actual_micros is not None else row["reserved_micros"], payload=canonical(details)))

    def budget(self):
        with self.engine.connect() as conn:
            rows = [self.decode(r) for r in conn.execute(select(usage)).mappings()]
        return {"accounted_usd": sum(r["accounted_micros"] for r in rows) / 1e6,
                "uncertain_usd": sum(r["accounted_micros"] for r in rows if r["status"] in ("reserved", "uncertain")) / 1e6,
                "unresolved_anomalies": [r["id"] for r in rows if r["payload"].get("estimate_exceeded") and not r["payload"].get("anomaly_resolved")],
                "attempts": rows}

    def resolve_anomaly(self, attempt_id, evidence):
        if not 8 <= len(evidence.strip()) <= 2000:
            raise ValueError("Provide 8–2000 characters describing verified pricing and the provider usage evidence")
        with self.transaction() as conn:
            row = conn.execute(select(usage).where(usage.c.id == attempt_id)).mappings().first()
            if not row or not json.loads(row["payload"]).get("estimate_exceeded"):
                raise ValueError("Usage attempt has no recorded estimate anomaly")
            active = conn.execute(select(runs.c.id).where(runs.c.status == "running")).first()
            if active:
                raise Conflict("Wait for active runs to finish before resolving a spending anomaly")
            details = json.loads(row["payload"])
            if details.get("anomaly_resolved"):
                return
            conn.execute(insert(reconciliations).values(id=uuid.uuid4().hex, attempt_id=attempt_id, created=time.time(),
                payload=canonical({"kind": "estimate_anomaly_resolved", "evidence": evidence})))
            details["anomaly_resolved"] = True
            conn.execute(update(usage).where(usage.c.id == attempt_id).values(payload=canonical(details)))

    def reconcile(self, attempt_id, micros, evidence):
        if type(micros) is not int or not 0 <= micros <= 2**63-1 or not 8 <= len(evidence.strip()) <= 2000:
            raise ValueError("Nonnegative cost and provider evidence are required")
        with self.transaction() as conn:
            row = conn.execute(select(usage).where(usage.c.id == attempt_id)).mappings().one()
            if row["status"] == "reported":
                raise Conflict("Already accounted from reported tokens")
            run = conn.execute(select(runs).where(runs.c.id == row["run_id"])).mappings().first()
            if run and run["status"] == "running":
                raise Conflict("Stop the run before reconciling")
            conn.execute(insert(reconciliations).values(id=uuid.uuid4().hex, attempt_id=attempt_id, created=time.time(),
                payload=canonical({"previous_micros": row["accounted_micros"], "confirmed_micros": micros, "evidence": evidence})))
            details = json.loads(row["payload"])
            if micros > row["reserved_micros"]:
                details.update(estimate_exceeded=True, anomaly_resolved=False)
            conn.execute(update(usage).where(usage.c.id == attempt_id).values(accounted_micros=micros, status="reconciled", payload=canonical(details)))
