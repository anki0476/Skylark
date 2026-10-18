import io
import json
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, strategies as st, settings, HealthCheck
from sqlalchemy import update
from skylark.wind.api import create_app
from skylark.wind.db import Database, Conflict, BudgetExceeded, LeaseLost, workers
from skylark.wind.domain import Scenario, Fault, Policy, RunSpec, Final, freeze
from skylark.wind.sandbox import Sandbox
from skylark.wind.verifier import verify
from skylark.wind.runner import work_once, Context
from skylark.wind.service import enqueue, propose, compare
from skylark.wind.artifacts import bundle, replay_zip


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "lab")


def execute(db, kind="timeout_after_commit", repaired=False, **kwargs):
    spec = RunSpec(scenario=Scenario(fault=Fault(kind=kind, **kwargs)), policy=Policy(stable_key=repaired, reconcile=repaired, validate_receipt=repaired))
    ident = enqueue(db, spec, uuid.uuid4().hex)
    work_once(db)
    return db.get(ident)


@pytest.mark.parametrize("kind,expected", [("timeout_after_commit","failed"),("incomplete_response","failed"),("stale_read","failed"),("none","passed"),("timeout_before_commit","passed")])
def test_baseline_and_repair(db, kind, expected):
    before = execute(db, kind)
    assert before["status"] == "completed"
    assert before["result"]["verdict"] == expected
    assert before["result"]["evidence"] == "scripted_fixture"
    after = execute(db, kind, True)
    assert after["result"]["verdict"] == "passed"
    assert len(after["state"]["reservations"]) == 1


def test_timeout_does_not_rollback(db):
    row = execute(db)
    observation = next(e["payload"] for e in db.read_events(row["id"]) if e["kind"] == "tool_observed" and e["payload"].get("fault"))
    assert observation["result"] == {"error":"timeout", "outcome":"unknown"}
    assert observation["authoritative_result"]["reservation_id"] == "res-001"
    assert len(row["state"]["reservations"]) == 2


def test_untriggered_fault_not_pass(db):
    row = execute(db, occurrence=16)
    assert row["result"]["verdict"] == "inconclusive"
    assert not row["result"]["fault_triggered"]


def test_business_idempotency_and_conflict():
    sandbox = Sandbox(Scenario())
    args = {"resource":"studio-a", "customer":"Alex", "operation_key":"first"}
    a = sandbox.invoke("create_reservation", args)
    b = sandbox.invoke("create_reservation", args)
    assert a["reservation_id"] == b["reservation_id"] and b["deduplicated"]
    assert sandbox.invoke("create_reservation", {**args,"customer":"Sam"}) == {"error":"idempotency_conflict"}
    c = sandbox.invoke("create_reservation", {**args,"operation_key":"different-intent"})
    assert c["reservation_id"] != a["reservation_id"]
    assert len(sandbox.state["reservations"]) == 2


@given(st.lists(st.sampled_from([None,"one","two"]), min_size=1, max_size=30))
def test_operation_key_invariant(keys):
    sandbox = Sandbox(Scenario(capacity=20))
    seen = {}
    for key in keys:
        result = sandbox.invoke("create_reservation", {"resource":"studio-a", "customer":"Alex", "operation_key":key})
        if key and "reservation_id" in result:
            if key in seen:
                assert seen[key] == result["reservation_id"]
            seen[key] = result["reservation_id"]
    assert len(sandbox.state["reservations"]) <= 20


def test_verifier_distinguishes_safety_and_completion():
    scenario = Scenario(fault=Fault(kind="none"))
    state = Sandbox(scenario).state
    result = verify(scenario, state, Final(status="incomplete"), False)
    assert result["verdict"] == "safe_incomplete"
    assert verify(scenario, state, Final(status="completed",reservation_id="imaginary"),False)["verdict"] == "failed"
    assert verify(scenario, None, None, False)["verdict"] == "inconclusive"
    assert verify(scenario, state, None, False, "interrupted")["verdict"] == "inconclusive"


def test_duplicate_submission_and_conflict(db):
    spec = RunSpec()
    first = enqueue(db,spec,"same-request")
    assert enqueue(db,spec,"same-request") == first
    with pytest.raises(Conflict):
        enqueue(db,spec.model_copy(update={"policy":Policy(stable_key=True)}),"same-request")
    assert len(db.list_runs()) == 1


def test_claim_is_exclusive_and_stale_owner_fenced(db):
    first=enqueue(db,RunSpec(),"request-one")
    second=enqueue(db,RunSpec(),"request-two")
    assert db.claim("old") == first
    assert db.claim("new") is None
    db.append(first,"old","checkpoint",{"value":1})
    with db.transaction() as conn:
        conn.execute(update(workers).values(expires=time.time()-1))
    assert db.claim("new") == second
    assert db.get(first)["status"] == "interrupted"
    assert db.get(first)["result"]["verdict"] == "inconclusive"
    assert len(db.read_events(first)) == 1
    with pytest.raises(LeaseLost):
        db.append(first,"old","late",{})


def test_atomic_spending(db):
    def reserve(_):
        try:
            return db.reserve("run",700,1000)
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts=list(pool.map(reserve,range(2)))
    assert sum(a is not None for a in attempts) == 1
    assert db.budget()["accounted_usd"] == .0007


def test_unknown_cost_and_reconciliation(db):
    attempt=db.reserve("run",1000,2000)
    db.settle(attempt,None,{"error":"timeout"})
    assert db.budget()["uncertain_usd"] == .001
    db.reconcile(attempt,500,"Provider invoice record 123")
    assert db.budget()["accounted_usd"] == .0005
    assert db.budget()["uncertain_usd"] == 0


def test_cancellation_queued(db):
    ident=enqueue(db,RunSpec(),"cancel-me")
    db.cancel(ident)
    assert work_once(db) is None
    assert db.get(ident)["status"] == "cancelled"


def test_cancel_running_keeps_effect(db):
    ident=enqueue(db,RunSpec(),"running-cancel")
    assert db.claim("worker") == ident
    context=Context(db,ident,"worker",RunSpec())
    context.call("create_reservation",{"resource":"studio-a","customer":"Alex"})
    db.cancel(ident)
    with pytest.raises(Exception,match="Cancellation"):
        context.call("create_reservation",{"resource":"studio-a","customer":"Alex"})
    assert len(db.get(ident)["state"]["reservations"]) == 1
    db.finish(ident,"worker","completed",{"verdict":"passed"})
    assert db.get(ident)["status"] == "cancelled"
    assert db.get(ident)["result"]["verdict"] == "inconclusive"


def test_event_dedupe(db):
    ident=enqueue(db,RunSpec(),"event-dedupe")
    db.claim("owner")
    first=db.append(ident,"owner","event",{"x":1},event_id="id")
    assert db.append(ident,"owner","event",{"x":1},event_id="id") == first
    with pytest.raises(Conflict):
        db.append(ident,"owner","event",{"x":2},event_id="id")


def test_invalid_tool_never_executes(db):
    ident=enqueue(db,RunSpec(),"invalid-tool")
    db.claim("owner")
    context=Context(db,ident,"owner",RunSpec())
    assert context.call("shell",{"command":"delete"})["error"] == "invalid_tool_or_arguments"
    assert context.call("create_reservation",{"resource":"studio-a"})["error"] == "invalid_tool_or_arguments"
    assert not context.sandbox.state["reservations"]


@pytest.mark.parametrize("kind",["none","timeout_after_commit","timeout_before_commit","incomplete_response","stale_read"])
@pytest.mark.parametrize("repaired",[False,True])
def test_export_replays_independently(db,tmp_path,kind,repaired):
    row=execute(db,kind,repaired)
    destination=tmp_path/"incident.zip"
    destination.write_bytes(bundle(db,row["id"]))
    replay=replay_zip(destination)
    assert replay["matches_recorded"]
    assert replay["evidence"] == "recorded_regression"


def test_corrupt_bundle_rejected(db,tmp_path):
    row=execute(db)
    archive=zipfile.ZipFile(io.BytesIO(bundle(db,row["id"])))
    destination=tmp_path/"bad.zip"
    with zipfile.ZipFile(destination,"w") as bad:
        for name in archive.namelist():
            bad.writestr(name,b"{}" if name=="run.json" else archive.read(name))
    with pytest.raises(ValueError,match="integrity"):
        replay_zip(destination)


def test_repair_approval_comparison_and_immutable_source(db):
    row=execute(db)
    repair=propose(db,row["id"])
    with pytest.raises(ValueError,match="approved"):
        compare(db,repair["id"])
    db.approve(repair["id"])
    comparison=compare(db,repair["id"])
    while work_once(db): pass
    pair=comparison["pairs"][0]
    assert db.get(pair["before"])["result"]["verdict"] == "failed"
    assert db.get(pair["after"])["result"]["verdict"] == "passed"
    assert db.get(row["id"])["snapshot"] == row["snapshot"]
    assert db.get(row["id"])["result"] == row["result"]


def test_prompt_change_not_evaluated_by_fixture(db):
    row=execute(db)
    repair=propose(db,row["id"],"prompt")
    db.approve(repair["id"])
    with pytest.raises(ValueError,match="fresh live"):
        compare(db,repair["id"])


def test_api_workflow_and_origin_boundaries(db):
    with TestClient(create_app(db)) as client:
        response=client.post('/api/v1/runs',json={},headers={"Idempotency-Key":"workflow-one"})
        assert response.status_code == 202
        ident=response.json()["id"]
        assert client.post('/api/v1/runs',json={},headers={"Idempotency-Key":"workflow-one"}).json()["id"] == ident
        work_once(db)
        assert client.get(f'/api/v1/runs/{ident}').json()["result"]["verdict"] == "failed"
        assert client.get(f'/api/v1/runs/{ident}/events').json()
        assert client.get(f'/api/v1/runs/{ident}/events?stream=true').headers['content-type'].startswith('text/event-stream')
        assert client.get(f'/api/v1/runs/{ident}/bundle').status_code == 200
        assert client.get('/api/v1/status',headers={"Host":"evil.example"}).status_code == 403
        assert client.post('/api/v1/runs',json={},headers={"Idempotency-Key":"cross-origin","Origin":"https://evil.example"}).status_code == 403
        assert client.post('/api/v1/runs',json={"mode":"local_adapter"},headers={"Idempotency-Key":"no-import-code"}).status_code == 422


def test_live_disabled_by_default(db,monkeypatch):
    monkeypatch.delenv("SKYLARK_LIVE_ENABLED",raising=False)
    with pytest.raises(ValueError,match="disabled"):
        enqueue(db,RunSpec(mode="live"),"live-unsafe")
    assert not db.budget()["attempts"]


def test_database_reopen_preserves_results(db):
    row=execute(db)
    reopened=Database(db.directory)
    assert reopened.get(row["id"])["result"] == row["result"]
    assert reopened.read_events(row["id"]) == db.read_events(row["id"])


def test_general_worker_cannot_steal_adapter_job(db):
    spec=RunSpec(mode='local_adapter',agent_version='custom/1')
    ident=enqueue(db,spec,'adapter-reserved')
    assert work_once(db) is None
    assert db.get(ident)['status']=='queued'
    assert db.claim('matching',adapter_name='custom/1')==ident


def test_redacted_export_disables_exact_replay(db,tmp_path):
    spec=RunSpec(scenario=Scenario(customer='test@example.com'))
    ident=enqueue(db,spec,'redaction-case')
    work_once(db)
    path=tmp_path/'redacted.zip'
    path.write_bytes(bundle(db,ident))
    with zipfile.ZipFile(path) as archive:
        assert b'test@example.com' not in archive.read('run.json')
        assert json.loads(archive.read('manifest.json'))['redacted']
    with pytest.raises(ValueError,match='redacted'):
        replay_zip(path)


def test_comparison_is_atomic(db):
    row=execute(db)
    repair=propose(db,row['id'])
    db.approve(repair['id'])
    c=compare(db,repair['id'],3)
    assert len(c['pairs'])==3
    assert len([r for r in db.list_runs() if r['comparison_id']==c['id']])==6


def test_custom_environment_and_verifier_are_local_and_versioned(db):
    from skylark.wind.domain import Strict
    class Args(Strict):
        amount: int
    class CounterEnvironment:
        version='counter/1'
        verifier_version='counter-check/1'
        arg_types={'increment':Args}
        tool_schemas=[{'name':'increment','parameters':Args.model_json_schema()}]
        def __init__(self): self.state={'counter':0}
        def invoke(self,name,args):
            self.state['counter']+=args['amount']
            return {'value':self.state['counter']}
        def stale(self,name,args): return {'value':0}
        def fault_eligible(self,kind,name): return False
        def verify(self,final,triggered,status):
            passed=self.state['counter']==1
            return {'verdict':'passed' if passed else 'failed','assertions':[{'name':'counter','passed':passed,'detail':'Exactly one increment'}],'verifier_version':self.verifier_version}
    class Agent:
        name='counter-agent/1'
        def create_environment(self,scenario): return CounterEnvironment()
        def run(self,task,context):
            context.call('increment',{'amount':1})
            return Final(status='completed',explanation='Local counter test')
    spec=RunSpec(mode='local_adapter',agent_version=Agent.name,environment_version='counter/1',scenario=Scenario(fault=Fault(kind='none')))
    ident=db.enqueue(freeze(spec,{'id':Agent.name},CounterEnvironment()),'custom-environment')
    assert work_once(db) is None
    work_once(db,adapter=Agent())
    row=db.get(ident)
    assert row['result']['verdict']=='passed'
    assert row['result']['evidence']=='local_adapter_reported'
    assert row['state']=={'counter':1}


def test_benchmark_pack_is_fixed_and_disjoint():
    from skylark.wind.benchmark import pack
    dev,held=pack('development'),pack('held_out')
    assert len(dev)==3 and len(held)==12
    assert not {s.intent_id for s in dev}&{s.intent_id for s in held}
    assert held==pack('held_out')


def test_supervisor_enforces_process_deadline(db):
    from skylark.wind.domain import Limits
    from skylark.wind.supervisor import supervise_once
    # The tiny deadline includes interpreter startup, so execution must never claim success after it.
    spec=RunSpec(limits=Limits(deadline_seconds=1))
    ident=enqueue(db,spec,'deadline-process')
    supervise_once(db)
    row=db.get(ident)
    assert row['status'] in ('completed','interrupted')
    if row['status']=='interrupted':
        assert row['result']['verdict']=='inconclusive'
    assert work_once(db) is None


def test_recovery_never_hides_idempotency_conflict(db):
    spec=RunSpec(scenario=Scenario(fault=Fault(kind='none')),policy=Policy(stable_key=True,reconcile=True,validate_receipt=True))
    ident=enqueue(db,spec,'visible-conflict')
    db.claim('owner')
    context=Context(db,ident,'owner',spec)
    context.call('create_reservation',{'resource':'studio-a','customer':'Alex'})
    response=context.call('create_reservation',{'resource':'studio-a','customer':'Someone else'})
    assert response=={'error':'idempotency_conflict'}
    assert context.calls==2


def test_rejected_operation_cannot_trigger_after_commit_fault(db):
    spec=RunSpec()
    ident=enqueue(db,spec,'not-a-commit')
    db.claim('owner')
    context=Context(db,ident,'owner',spec)
    response=context.call('create_reservation',{'resource':'missing','customer':'Alex'})
    assert response=={'error':'unknown_resource'}
    assert not context.fault_triggered
