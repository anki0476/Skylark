"""SQLite checkpoints, immutable inference cache, and a shared experiment ledger."""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BudgetExceeded(ValueError):
    pass


class Store:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "skylark.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, sample_id TEXT NOT NULL,
                    model TEXT NOT NULL, status TEXT NOT NULL, estimated_usd REAL NOT NULL,
                    accounted_usd REAL NOT NULL, cost_basis TEXT NOT NULL,
                    input_tokens INTEGER, output_tokens INTEGER, latency_seconds REAL,
                    error TEXT, created_at TEXT NOT NULL, finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    dataset_fingerprint TEXT NOT NULL, sample_id TEXT NOT NULL,
                    payload TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(dataset_fingerprint, sample_id)
                );
                CREATE TABLE IF NOT EXISTS reconciliations (
                    id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL, previous_usd REAL NOT NULL,
                    confirmed_usd REAL NOT NULL, evidence TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def budget(self) -> dict:
        with self.connection() as db:
            return dict(db.execute("""
                SELECT COALESCE(SUM(accounted_usd),0) AS accounted_usd,
                COALESCE(SUM(CASE WHEN cost_basis NOT IN ('reported_tokens', 'provider_reconciled')
                    THEN accounted_usd ELSE 0 END),0)
                    AS uncertain_or_reserved_usd,
                COUNT(*) AS attempts FROM attempts
            """).fetchone())

    def reserve(self, run_id: str, sample_id: str, model: str, amount: float, limit: float) -> str:
        if not math.isfinite(amount) or not math.isfinite(limit) or amount <= 0 or limit <= 0:
            raise ValueError("Positive cost estimate and allowance are required")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            spent = db.execute("SELECT COALESCE(SUM(accounted_usd),0) FROM attempts").fetchone()[0]
            if spent + amount > limit + 1e-12:
                raise BudgetExceeded("Experiment allowance reached; no API request was sent")
            attempt_id = uuid.uuid4().hex
            db.execute("""
                INSERT INTO attempts(id, run_id, sample_id, model, status, estimated_usd,
                                     accounted_usd, cost_basis, created_at)
                VALUES (?, ?, ?, ?, 'running', ?, ?, 'reserved_estimate', ?)
            """, (attempt_id, run_id, sample_id, model, amount, amount, now()))
            return attempt_id

    def finish_attempt(self, attempt_id: str, *, status: str, latency: float,
                       cost: float | None, input_tokens: int | None = None,
                       output_tokens: int | None = None, error: str | None = None):
        if cost is not None and (not math.isfinite(cost) or cost < 0):
            raise ValueError("Recorded cost must be finite and nonnegative")
        with self.connection() as db:
            if cost is not None:
                db.execute("""UPDATE attempts SET status=?, latency_seconds=?, accounted_usd=?,
                    cost_basis='reported_tokens', input_tokens=?, output_tokens=?, error=?, finished_at=?
                    WHERE id=?""", (status, latency, cost, input_tokens, output_tokens, error, now(), attempt_id))
            else:
                # Unknown billing (including network timeouts) is never counted as free.
                db.execute("""UPDATE attempts SET status=?, latency_seconds=?, error=?,
                    cost_basis='unconfirmed_estimate', finished_at=? WHERE id=?""",
                           (status, latency, error, now(), attempt_id))

    def attempts(self, run_id: str) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM attempts WHERE run_id=? ORDER BY created_at", (run_id,))]

    def sample_cost(self, run_id: str, sample_id: str, model: str) -> float:
        with self.connection() as db:
            return db.execute("""SELECT COALESCE(SUM(accounted_usd),0) FROM attempts
                WHERE run_id=? AND sample_id=? AND model=?""", (run_id, sample_id, model)).fetchone()[0]

    def reconcile(self, attempt_id: str, confirmed_usd: float, evidence: str) -> dict:
        """Record a user's provider-dashboard reconciliation without erasing original estimates."""
        if not math.isfinite(confirmed_usd) or confirmed_usd < 0:
            raise ValueError("Confirmed amount must be finite and nonnegative")
        if not 8 <= len(evidence.strip()) <= 1000:
            raise ValueError("Record a provider usage reference and verification date (8 to 1000 characters)")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown attempt ID")
            if row["status"] == "running":
                raise ValueError("Cannot reconcile an active request; stop its process and inspect the run first")
            if row["cost_basis"] not in {"unconfirmed_estimate", "provider_reconciled"}:
                raise ValueError("This attempt already has reported token usage; reconcile only uncertain charges")
            audit = {"id": uuid.uuid4().hex, "attempt_id": attempt_id,
                     "previous_usd": row["accounted_usd"], "confirmed_usd": confirmed_usd,
                     "evidence": evidence.strip(), "created_at": now()}
            db.execute("INSERT INTO reconciliations VALUES (?, ?, ?, ?, ?, ?)", tuple(audit.values()))
            db.execute("UPDATE attempts SET accounted_usd=?, cost_basis='provider_reconciled' WHERE id=?",
                       (confirmed_usd, attempt_id))
            return audit

    def get_cache(self, key: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT payload FROM cache WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def put_cache(self, key: str, payload: dict):
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO cache VALUES (?, ?, ?)", (key, json.dumps(payload), now()))

    def save_run(self, run_id: str, state: str, payload: dict):
        with self.connection() as db:
            db.execute("""INSERT INTO runs VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET state=excluded.state, payload=excluded.payload,
                updated_at=excluded.updated_at""", (run_id, state, json.dumps(payload), now(), now()))

    def get_run(self, run_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            return {**dict(row), "payload": json.loads(row["payload"])} if row else None

    def list_runs(self) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT id, state, created_at, updated_at FROM runs ORDER BY created_at DESC")]

    def save_review(self, fingerprint: str, sample_id: str, payload: dict):
        with self.connection() as db:
            db.execute("""INSERT INTO reviews VALUES (?, ?, ?, ?)
                ON CONFLICT(dataset_fingerprint, sample_id) DO UPDATE SET
                payload=excluded.payload, updated_at=excluded.updated_at""",
                       (fingerprint, sample_id, json.dumps(payload), now()))

    def reviews(self, fingerprint: str) -> list[dict]:
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT payload FROM reviews WHERE dataset_fingerprint=? ORDER BY sample_id", (fingerprint,))]

