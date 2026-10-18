import io
import json
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import Column, Integer, Table, inspect
from skylark.wind.db import Database, Conflict, metadata
from skylark.wind.domain import RunSpec, Scenario, Fault, Final, canonical, digest, freeze
from skylark.wind.runner import Context, Cancelled, work_once
from skylark.wind.sandbox import Sandbox
from skylark.wind.service import enqueue, propose, compare
from skylark.wind.artifacts import bundle, replay_zip
from skylark.wind.reporting import report
from skylark.wind.verifier import verify


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "lab")


def finished(db, spec=None):
    ident = enqueue(db, spec or RunSpec(), uuid.uuid4().hex)
    work_once(db)
    return ident


def test_cancellation_during_tool_keeps_effect_and_observation(db):
    spec = RunSpec()
    ident = enqueue(db, spec, "cancel-during-call")
    db.claim("owner")
    class CancellingSandbox(Sandbox):
        def invoke(self, name, arguments):
            actual = super().invoke(name, arguments)
            db.cancel(ident)
            return actual
    context = Context(db, ident, "owner", spec, CancellingSandbox(spec.scenario))
    with pytest.raises(Cancelled):
        context.call("create_reservation", {"resource": "studio-a", "customer": "Alex"})
    assert len(db.get(ident)["state"]["reservations"]) == 1
    events = db.read_events(ident)
    assert [e["kind"] for e in events] == ["tool_requested", "tool_effect", "tool_observed"]
    assert events[-1]["payload"]["result"]["error"] == "timeout"
    assert events[-1]["payload"]["authoritative_result"]["reservation_id"] == "res-001"


def test_frozen_migration_does_not_import_future_schema(tmp_path):
    future = Table("future_table", metadata, Column("id", Integer, primary_key=True))
    try:
        database = Database(tmp_path / "frozen-migration")
        assert "future_table" not in inspect(database.engine).get_table_names()
    finally:
        metadata.remove(future)


def test_concurrent_initialization_and_duplicate_submission(tmp_path):
    import threading
    ready = threading.Barrier(4)
    def initialize(_):
        ready.wait(timeout=10)
        database = Database(tmp_path / "shared")
        ident = enqueue(database, RunSpec(), "same-run-key")
        database.engine.dispose()
        return ident
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(initialize, range(4)))
    assert len(set(ids)) == 1


def test_concurrent_exports_are_complete(db, tmp_path):
    ident = finished(db)
    with ThreadPoolExecutor(max_workers=4) as pool:
        bundles = list(pool.map(lambda _: bundle(db, ident), range(8)))
    assert len(set(bundles)) == 1
    assert len(list((db.directory / 'artifacts').glob('*.zip'))) == 1
    for index, data in enumerate(bundles):
        destination = tmp_path / f"incident-{index}.zip"
        destination.write_bytes(data)
        assert replay_zip(destination)["matches_recorded"]


def test_corrupt_stored_artifact_is_visible(db):
    ident = finished(db)
    bundle(db, ident)
    saved = next((db.directory / 'artifacts').glob('*.zip'))
    saved.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='content hash'):
        bundle(db, ident)


@pytest.mark.parametrize("remove_kind", ["verification", "final_claim", "tool_observed"])
def test_incomplete_trace_is_rejected_even_with_updated_checksums(db, tmp_path, remove_kind):
    import hashlib
    original = zipfile.ZipFile(io.BytesIO(bundle(db, finished(db))))
    members = {name: original.read(name) for name in original.namelist()}
    events = json.loads(members["events.json"])
    events.pop(next(i for i, e in enumerate(events) if e["kind"] == remove_kind))
    for sequence, event in enumerate(events, 1):
        event["sequence"] = sequence
    members["events.json"] = canonical(events).encode()
    manifest = json.loads(members["manifest.json"])
    manifest["files"]["events.json"] = hashlib.sha256(members["events.json"]).hexdigest()
    members["manifest.json"] = canonical(manifest).encode()
    destination = tmp_path / "incomplete.zip"
    with zipfile.ZipFile(destination, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    with pytest.raises(ValueError):
        replay_zip(destination)


def test_missing_final_evidence_is_inconclusive_and_false_id_fails():
    scenario = Scenario(fault=Fault(kind="none"))
    state = Sandbox(scenario).state
    assert verify(scenario, state, None, False)["verdict"] == "inconclusive"
    assert verify(scenario, state, Final(status="incomplete", reservation_id="invented"), False)["verdict"] == "failed"


def test_repair_cannot_hide_changed_model_dependencies(db, monkeypatch):
    ident = finished(db)
    repair = propose(db, ident)
    db.approve(repair["id"])
    monkeypatch.setattr("skylark.wind.service.VERIFIER_VERSION", "future/3")
    with pytest.raises(Conflict, match="verifier changed"):
        compare(db, repair["id"])


def test_report_keeps_unknowns_controls_and_usage(db):
    fault = finished(db)
    finished(db, RunSpec(scenario=Scenario(fault=Fault(kind="none"))))
    queued = enqueue(db, RunSpec(), "pending-report")
    usage = db.reserve(fault, 1000, 2000)
    db.settle(usage, None, {"error": "ambiguous_timeout"})
    result = report(db)
    group = next(g for g in result["groups"] if g["condition"] == "timeout_after_commit")
    assert group["pending"] == 1
    assert group["dimensions"]["safety"] == {
        "passed": 0, "failed": 1, "unknown": 1, "not_applicable": 0,
        "observed": 1, "rate": 0, "wilson_95": [0, 0.793451]}
    assert group["uncertain_usd"] == .001
    control = next(g for g in result["groups"] if g["condition"] == "none")
    assert control["dimensions"]["fault_coverage"]["not_applicable"] == 1
    assert {a["run_id"] for a in result["attempts"]} >= {fault, queued}


def test_report_does_not_pool_model_or_verifier_versions(db):
    a = freeze(RunSpec())
    b = {**a, "model": {"id": "another-model", "revision": "unknown"}}
    c = {**a, "verifier_version": "another-verifier"}
    for snapshot in (a, b, c):
        db.enqueue(snapshot, digest(snapshot))
    assert len(report(db)["groups"]) == 3


def test_report_reads_early_agent_lab_records_without_rewriting_them(db):
    snapshot = freeze(RunSpec())
    del snapshot["spec"]["environment_version"]
    ident = db.enqueue(snapshot, "early-lab-version")
    assert report(db)["groups"][0]["environment_version"] == "reservation/1"
    assert "environment_version" not in db.get(ident)["snapshot"]["spec"]


def test_scoped_report_contains_every_scheduled_attempt(db):
    from skylark.wind.benchmark import schedule
    benchmark = schedule(db, trials=1, split="development")
    enqueue(db, RunSpec(), "outside-protocol")
    result = report(db, benchmark["id"])
    assert {r["run_id"] for r in result["attempts"]} == set(benchmark["runs"])
    assert result["protocol"]["pack_hash"] == benchmark["pack_hash"]


def test_agent_observation_records_guard_output_not_raw_timeout(db):
    from skylark.wind.domain import Policy
    ident = finished(db, RunSpec(policy=Policy(stable_key=True, reconcile=True, validate_receipt=True)))
    events = db.read_events(ident)
    raw = next(e["payload"] for e in events if e["kind"] == "tool_observed" and e["payload"].get("fault"))
    delivered = next(e["payload"] for e in events if e["kind"] == "agent_observed" and e["payload"]["invocation_id"] == raw["invocation_id"])
    assert raw["result"] == {"error": "timeout", "outcome": "unknown"}
    assert delivered["result"]["status"] == "completed"
    assert delivered["result"]["reservation_id"] == "res-001"


def test_sse_drains_events_committed_during_completion_check(db, monkeypatch):
    from fastapi.testclient import TestClient
    from skylark.wind.api import create_app
    ident = finished(db)
    original = db.read_events
    calls = 0
    def racing_read(*args, **kwargs):
        nonlocal calls
        calls += 1
        return [] if calls == 1 else original(*args, **kwargs)
    monkeypatch.setattr(db, "read_events", racing_read)
    with TestClient(create_app(db)) as client:
        response = client.get(f"/api/v1/runs/{ident}/events?stream=true")
        assert '"kind": "verification"' in response.text
        assert response.text.index('"kind": "verification"') < response.text.index("event: done")
        exported = client.get("/api/v1/results/export")
        assert exported.status_code == 200
        assert exported.json()["schema_version"] == "skylark-report/1"
