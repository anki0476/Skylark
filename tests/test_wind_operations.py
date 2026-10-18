import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from skylark.wind.db import Database
from skylark.wind.domain import RunSpec, Scenario, Limits, freeze
from skylark.wind.runner import Context, work_once
from skylark.wind.service import enqueue
from skylark.wind.processes import spawn_python, stop_process
from skylark.wind.supervisor import supervise_once, parent_alive
from skylark.wind.backup import create_backup, restore_backup
from skylark.wind.artifacts import bundle, replay_zip


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "lab")


def wait_until(predicate, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError("Condition did not become true before deadline")


def alive(pid):
    if os.name == "nt":
        return parent_alive(pid)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_spawn_handle_is_actual_interpreter_and_keeps_venv(tmp_path):
    import sys
    path = tmp_path / "identity.json"
    code = f"import os,sys,json,time; from pathlib import Path; Path({str(path)!r}).write_text(json.dumps({{'pid':os.getpid(),'prefix':sys.prefix}})); time.sleep(30)"
    process = spawn_python(["-c", code])
    try:
        wait_until(path.exists)
        identity = json.loads(path.read_text())
        assert identity["pid"] == process.pid
        assert Path(identity["prefix"]).resolve() == Path(sys.prefix).resolve()
    finally:
        stop_process(process)
    assert not alive(identity["pid"])


@pytest.mark.parametrize("cause", ["cancel", "deadline"])
def test_supervisor_kills_actual_sleeping_attempt_and_preserves_commit(db, tmp_path, cause, monkeypatch):
    launched = []
    def capture(*args, **kwargs):
        process = spawn_python(*args, **kwargs)
        launched.append(process)
        return process
    monkeypatch.setattr("skylark.wind.supervisor.spawn_python", capture)
    adapter = tmp_path / "sleepy.py"
    adapter.write_text('''import os, time
class Adapter:
    name = "sleepy/1"
    def run(self, task, context):
        context.call("create_reservation", {"resource":task["resource"], "customer":task["customer"]})
        context.emit("test_process", {"pid":os.getpid()})
        time.sleep(30)
        context.call("create_reservation", {"resource":task["resource"], "customer":task["customer"]})
''', encoding="utf-8")
    spec = RunSpec(mode="local_adapter", agent_version="sleepy/1", limits=Limits(deadline_seconds=8))
    ident = enqueue(db, spec, "sleepy-" + cause)
    pid = None
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(supervise_once, db, adapter, "sleepy/1", ident)
            def observed_pid():
                return next((e["payload"]["pid"] for e in db.read_events(ident) if e["kind"] == "test_process"), None)
            pid = wait_until(observed_pid, seconds=8)
            assert launched[0].pid == pid, "Supervisor must own the actual interpreter"
            if cause == "cancel":
                db.cancel(ident)
            assert pending.result(timeout=12) == ident
        assert launched[0].poll() is not None
        wait_until(lambda: not alive(pid), seconds=3)
        row = db.get(ident)
        assert row["status"] == ("cancelled" if cause == "cancel" else "interrupted")
        assert row["result"]["verdict"] == "inconclusive"
        assert len(row["state"]["reservations"]) == 1
        assert work_once(db) is None
    finally:
        for process in launched:
            stop_process(process)


@pytest.mark.parametrize("boundary", ["before_checkpoint", "after_checkpoint"])
def test_actual_process_crash_does_not_rerun_uncertain_action(db, tmp_path, boundary):
    adapter = tmp_path / "crashing.py"
    if boundary == "before_checkpoint":
        code = '''import os
from skylark.wind.sandbox import Sandbox
class CrashEnvironment(Sandbox):
    def invoke(self, name, args):
        result = super().invoke(name, args)
        if name == "create_reservation": os._exit(23)
        return result
class Adapter:
    name = "crash/1"
    def create_environment(self, scenario): return CrashEnvironment(scenario)
    def run(self, task, context):
        context.call("create_reservation", {"resource":task["resource"], "customer":task["customer"]})
'''
    else:
        code = '''import os
class Adapter:
    name = "crash/1"
    def run(self, task, context):
        context.call("create_reservation", {"resource":task["resource"], "customer":task["customer"]})
        os._exit(23)
'''
    adapter.write_text(code, encoding="utf-8")
    spec = RunSpec(mode="local_adapter", agent_version="crash/1")
    ident = enqueue(db, spec, "crash-" + boundary)
    assert supervise_once(db, adapter, "crash/1", ident) == ident
    row = db.get(ident)
    assert row["status"] == "interrupted" and row["result"]["verdict"] == "inconclusive"
    kinds = [e["kind"] for e in db.read_events(ident)]
    assert "tool_requested" in kinds
    if boundary == "after_checkpoint":
        assert "tool_effect" in kinds and len(row["state"]["reservations"]) == 1
    else:
        assert "tool_effect" not in kinds and "tool_observed" not in kinds
    assert work_once(db) is None


def test_dead_server_does_not_claim_more_jobs(db, monkeypatch):
    ident = enqueue(db, RunSpec(), "orphan-worker")
    monkeypatch.setattr("skylark.wind.supervisor.parent_alive", lambda pid: False)
    assert supervise_once(db, parent_pid=123) is None
    assert db.get(ident)["status"] == "queued"


def test_actual_worker_loss_stops_attempt_without_repeating_commit(db, tmp_path):
    from sqlalchemy import update
    from skylark.wind.db import workers
    adapter = tmp_path / 'worker_loss.py'
    adapter.write_text('''import os, time
class Adapter:
    name = "worker-loss/1"
    def run(self, task, context):
        context.call("create_reservation", {"resource":task["resource"], "customer":task["customer"]})
        context.emit("test_process", {"pid":os.getpid()})
        time.sleep(30)
''', encoding='utf-8')
    ident = enqueue(db, RunSpec(mode='local_adapter', agent_version='worker-loss/1'), 'real-worker-loss')
    db.reserve(ident, 500, 1000)
    code = f"from skylark.wind.db import Database; from skylark.wind.supervisor import supervise_once; supervise_once(Database({str(db.directory)!r}), adapter_path={str(adapter)!r}, adapter_name='worker-loss/1', run_id={ident!r})"
    worker = spawn_python(['-c', code])
    try:
        pid = wait_until(lambda: next((e['payload']['pid'] for e in db.read_events(ident) if e['kind']=='test_process'), None))
        stop_process(worker)
        wait_until(lambda: not alive(pid), seconds=5)
        # Advance the lease expiry rather than waiting the full 20 seconds.
        with db.transaction() as connection:
            connection.execute(update(workers).values(expires=0))
        assert work_once(db) is None
        row = db.get(ident)
        assert row['status']=='interrupted' and row['result']['verdict']=='inconclusive'
        assert len(row['state']['reservations'])==1
        assert db.budget()['uncertain_usd']==.0005
    finally:
        stop_process(worker)


def test_launch_failure_is_infrastructure_not_agent_failure(db, monkeypatch):
    ident = enqueue(db, RunSpec(), "launch-failure")
    def fail(*args, **kwargs):
        raise OSError("test launch failure")
    monkeypatch.setattr("skylark.wind.supervisor.spawn_python", fail)
    supervise_once(db)
    assert db.get(ident)["status"] == "infrastructure_failed"
    assert db.get(ident)["result"]["verdict"] == "inconclusive"


def test_environment_setup_failure_releases_worker_lease(db):
    class Agent:
        name = "bad-environment/1"
        def create_environment(self, scenario):
            raise RuntimeError("sensitive adapter error must not appear")
    ident = enqueue(db, RunSpec(mode="local_adapter", agent_version=Agent.name), "setup-failure")
    work_once(db, Agent())
    row = db.get(ident)
    assert row["status"] == "infrastructure_failed"
    assert "sensitive" not in row["error"]
    next_id = enqueue(db, RunSpec(), "after-setup-failure")
    assert db.claim("next") == next_id


def test_backup_restore_preserves_evidence_and_suspends_work(db, tmp_path):
    completed = enqueue(db, RunSpec(), "completed-backup")
    work_once(db)
    active = enqueue(db, RunSpec(), "active-backup")
    queued = enqueue(db, RunSpec(), "queued-backup")
    db.claim("original-worker")
    context = Context(db, active, "original-worker", RunSpec())
    context.call("create_reservation", {"resource": "studio-a", "customer": "Alex"})
    db.reserve(active, 500, 1000)
    backup = tmp_path / "backup"
    assert create_backup(db, backup)["run_count"] == 3
    restored_path = tmp_path / "restored"
    result = restore_backup(backup, restored_path)
    assert result["suspended_runs"] == 2 and result["budget"]["uncertain_usd"] == .0005
    restored = Database(restored_path)
    assert work_once(restored) is None
    for ident in (active, queued):
        assert restored.get(ident)["status"] == "interrupted"
    assert len(restored.get(active)["state"]["reservations"]) == 1
    assert restored.get(completed)["result"] == db.get(completed)["result"]
    path = tmp_path / "restored-incident.zip"
    path.write_bytes(bundle(restored, completed))
    assert replay_zip(path)["matches_recorded"]
    assert db.get(active)["status"] == "running"  # The original was never altered.


def test_restore_rejects_corruption_and_existing_destination(db, tmp_path):
    source = tmp_path / "backup"
    create_backup(db, source)
    with pytest.raises(ValueError, match="new directory"):
        restore_backup(source, source)
    with (source / "agent-lab.sqlite3").open("ab") as handle:
        handle.write(b"corrupt")
    with pytest.raises(ValueError, match="checksum or size"):
        restore_backup(source, tmp_path / "invalid-restore")
    assert not (tmp_path / "invalid-restore").exists()


def test_interrupted_restore_cannot_run_pending_jobs(db, tmp_path, monkeypatch):
    enqueue(db, RunSpec(), 'queued-before-restore')
    source, destination = tmp_path / 'backup', tmp_path / 'interrupted-restore'
    create_backup(db, source)
    def fail(*args, **kwargs):
        raise RuntimeError('Simulated crash after the database copy')
    monkeypatch.setattr('skylark.wind.backup.Database', fail)
    with pytest.raises(RuntimeError, match='Simulated crash'):
        restore_backup(source, destination)
    with pytest.raises(ValueError, match='Restore did not complete'):
        Database(destination)


def test_targeted_fixture_cannot_dispatch_unrelated_queued_work(db):
    unrelated = enqueue(db, RunSpec(), 'unrelated-earlier-work')
    demo = enqueue(db, RunSpec(), 'requested-demo')
    assert work_once(db, run_id=demo) == demo
    assert db.get(demo)['status'] == 'completed'
    assert db.get(unrelated)['status'] == 'queued'
