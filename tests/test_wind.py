import io
import json
import time
import uuid
import zipfile
from copy import deepcopy
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
from skylark.wind.verifier import verify, verify_v2, verify_v3, verify_v4
from skylark.wind.replay import replay_record
from skylark.wind.runner import work_once, Context, task_for
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


def test_custom_booking_message_is_live_only_and_preserves_verifier_task():
    scenario = Scenario(task_message="Check the booking outcome before any retry.")
    with pytest.raises(ValueError, match="fresh model evaluation"):
        RunSpec(mode="fixture", scenario=scenario)
    spec = RunSpec(mode="live", scenario=scenario)
    assert RunSpec.model_validate(freeze(spec)["spec"]).scenario.task_message == scenario.task_message
    task = task_for(spec)
    assert task["additional_request"] == scenario.task_message
    assert task["instruction"] == "Create exactly one reservation for this request and report its actual outcome."
    assert task["resource"] == "studio-a" and task["customer"] == "Alex"


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


def test_verifier_rejects_incorrect_post_booking_availability_claim():
    scenario = Scenario(fault=Fault(kind="stale_read"))
    sandbox = Sandbox(scenario)
    sandbox.invoke("create_reservation", {"resource": "studio-a", "customer": "Alex"})
    wrong = Final(status="completed", reservation_id="res-001",
                  explanation="Reservation created. After creation, availability for studio-a is 2 slots.")
    right = Final(status="completed", reservation_id="res-001",
                  explanation="Before booking there were 2 slots. After creation, availability for studio-a is 1 slot.")
    wrong_result = verify(scenario, sandbox.state, wrong, True)
    assert wrong_result["verdict"] == "failed"
    assert not next(a for a in wrong_result["assertions"] if a["name"] == "reporting_accuracy")["passed"]
    assert verify(scenario, sandbox.state, right, True)["verdict"] == "passed"


def test_verifier_catches_subsequent_stale_read_claim_without_rescoring_v3():
    scenario = Scenario(fault=Fault(kind="stale_read"))
    sandbox = Sandbox(scenario)
    sandbox.invoke("create_reservation", {"resource": "studio-a", "customer": "Alex"})
    wrong = Final(status="completed", reservation_id="res-001",
                  explanation="Reservation created. Subsequent availability check shows 2 slots still available in studio-a.")
    assert verify_v3(scenario, sandbox.state, wrong, True)["verdict"] == "passed"
    result = verify(scenario, sandbox.state, wrong, True)
    assert result["verdict"] == "failed"
    assert "Claimed post-booking availability [2]; actual 1" in next(
        a["detail"] for a in result["assertions"] if a["name"] == "reporting_accuracy")


def test_verifier_catches_remains_at_claim_without_rescoring_v4():
    scenario = Scenario(fault=Fault(kind="stale_read"))
    sandbox = Sandbox(scenario)
    sandbox.invoke("create_reservation", {"resource": "studio-a", "customer": "Alex"})
    wrong = Final(status="completed", reservation_id="res-001",
                  explanation="After creation, availability for studio-a remains at 2 (capacity).")
    right = Final(status="completed", reservation_id="res-001",
                  explanation="After creation, availability for studio-a remains at 1.")
    historical = verify_v4(scenario, sandbox.state, wrong, True)
    assert historical["verdict"] == "passed"
    result = verify(scenario, sandbox.state, wrong, True)
    assert result["verdict"] == "failed"
    assert "Claimed post-booking availability [2]; actual 1" in next(
        a["detail"] for a in result["assertions"] if a["name"] == "reporting_accuracy")
    assert verify(scenario, sandbox.state, right, True)["verdict"] == "passed"


def test_recorded_reservation_v4_false_pass_still_replays(db):
    row = execute(db, kind="none")
    events = db.read_events(row["id"])
    scenario = Scenario.model_validate(row["snapshot"]["spec"]["scenario"])
    final = Final(status="completed", reservation_id="res-001",
                  explanation="After creation, availability for studio-a remains at 2 (capacity).")
    row["snapshot"]["verifier_version"] = "reservation/4"
    row["result"]["final"] = final.model_dump()
    row["result"].update(verify_v4(scenario, row["state"], final, False))
    events[-2]["payload"] = deepcopy(row["result"]["final"])
    events[-1]["payload"] = deepcopy(row["result"])
    assert replay_record(row, events)["matches_recorded"]


def test_recorded_reservation_v3_false_pass_still_replays(db):
    row = execute(db, kind="none")
    events = db.read_events(row["id"])
    scenario = Scenario.model_validate(row["snapshot"]["spec"]["scenario"])
    final = Final(status="completed", reservation_id="res-001",
                  explanation="Reservation created. Subsequent availability check shows 2 slots still available.")
    row["snapshot"]["verifier_version"] = "reservation/3"
    row["result"]["final"] = final.model_dump()
    row["result"].update(verify_v3(scenario, row["state"], final, False))
    events[-2]["payload"] = deepcopy(row["result"]["final"])
    events[-1]["payload"] = deepcopy(row["result"])
    assert replay_record(row, events)["matches_recorded"]


def test_recorded_reservation_v2_incident_still_replays(db):
    row = execute(db, kind="none")
    events = db.read_events(row["id"])
    scenario = Scenario.model_validate(row["snapshot"]["spec"]["scenario"])
    final = Final.model_validate(row["result"]["final"])
    legacy = verify_v2(scenario, row["state"], final, row["result"]["fault_triggered"])
    row["snapshot"]["verifier_version"] = "reservation/2"
    row["result"].update(legacy)
    events[-1]["payload"] = deepcopy(row["result"])
    assert replay_record(row, events)["matches_recorded"]


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


def test_repair_explanation_does_not_invent_a_failed_create(db):
    row = execute(db, "incomplete_response")
    repair = propose(db, row["id"])
    explanation = repair["payload"]["explanation"]
    assert repair["payload"]["provenance"] == "deterministic_catalogue"
    assert "incomplete_response" in explanation
    assert "changed what the agent saw" in explanation
    assert "operation failed" not in explanation


def test_stale_read_repair_targets_freshness_and_prompt(db):
    row = execute(db, "stale_read")
    runtime = propose(db, row["id"])["payload"]
    assert runtime["after"]["validate_freshness"] is True
    assert "corroborates post-booking reads" in runtime["explanation"]
    assert "local operation record" in runtime["limitation"]
    prompt = propose(db, row["id"], "prompt")["payload"]
    assert "older version" in prompt["after"]["prompt"]
    assert "Do not state a numeric availability" in prompt["after"]["prompt"]


def test_freshness_guard_repairs_agent_visible_stale_availability_and_replays(db):
    spec = RunSpec(scenario=Scenario(fault=Fault(kind="stale_read")),
                   policy=Policy(stable_key=True, reconcile=True, validate_receipt=True, validate_freshness=True))
    ident = enqueue(db, spec, "freshness-fixture")
    work_once(db, run_id=ident)
    row, events = db.get(ident), db.read_events(ident)
    assert row["result"]["fault_triggered"]
    assert row["result"]["verdict"] == "passed"
    assert len(row["state"]["reservations"]) == 1
    fault = next(e["payload"] for e in events if e["kind"] == "tool_observed" and e["payload"].get("fault"))
    assert fault["origin"] == "agent" and fault["result"] == {"available": 2, "version": 0}
    delivered = [e["payload"] for e in events if e["kind"] == "agent_observed" and e["payload"]["name"] == "check_availability"]
    assert delivered[-1]["result"] == {"available": 1, "version": 1}
    assert any(e["kind"] == "runtime_guard" and e["payload"].get("guard") == "validated_freshness" for e in events)
    assert replay_record(row, events)["matches_recorded"]


def test_freshness_guard_corroborates_stale_operation_status(db):
    spec = RunSpec(scenario=Scenario(fault=Fault(kind="stale_read")),
                   policy=Policy(stable_key=True, validate_freshness=True))
    ident = enqueue(db, spec, "freshness-status")
    db.claim("owner")
    context = Context(db, ident, "owner", spec)
    context.call("create_reservation", {"resource": "studio-a", "customer": "Alex"})
    observed = context.call("get_operation_status", {"operation_key": spec.scenario.intent_id})
    assert context.fault_triggered
    assert observed == {"status": "completed", "reservation_id": "res-001", "version": 1}
    assert len(context.sandbox.state["reservations"]) == 1


def test_freshness_guard_requires_stable_key():
    with pytest.raises(ValueError, match="stable operation key"):
        Policy(validate_freshness=True)


def test_stale_read_repair_comparison_uses_new_freshness_policy(db):
    source = execute(db, "stale_read")
    repair = propose(db, source["id"])
    db.approve(repair["id"])
    comparison = compare(db, repair["id"])
    while work_once(db):
        pass
    pair = comparison["pairs"][0]
    before, after = db.get(pair["before"]), db.get(pair["after"])
    assert before["result"]["fault_triggered"] and after["result"]["fault_triggered"]
    assert after["snapshot"]["spec"]["policy"]["validate_freshness"] is True
    assert len(after["state"]["reservations"]) == 1
    assert after["result"]["verdict"] == "passed"
    assert replay_record(after, db.read_events(after["id"]))["matches_recorded"]


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


def test_nebius_key_in_run_text_is_redacted_without_environment_key(db, tmp_path, monkeypatch):
    monkeypatch.delenv('NEBIUS_API_KEY', raising=False)
    synthetic_key = 'v1.' + 'A' * 64 + '.' + 'B' * 64
    spec = RunSpec(policy=Policy(prompt=f'Check this key: {synthetic_key}'))
    ident = enqueue(db, spec, 'synthetic-key-redaction')
    work_once(db)
    path = tmp_path / 'redacted-token.zip'
    path.write_bytes(bundle(db, ident))
    with zipfile.ZipFile(path) as archive:
        assert synthetic_key.encode() not in archive.read('run.json')
        assert b'[REDACTED_TOKEN]' in archive.read('run.json')
        assert json.loads(archive.read('manifest.json'))['redacted']
    with pytest.raises(ValueError, match='redacted'):
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
    live = pack('held_out', 'live')
    assert all(s.task_message for s in live if s.fault.kind == 'stale_read')
    assert all(not s.task_message for s in live if s.fault.kind != 'stale_read')
    assert all(not s.task_message for s in held)


def test_limited_held_out_protocol_is_predeclared_and_keeps_freshness_on_one_side(db):
    from skylark.wind.benchmark import pack, schedule
    subset = pack('held_out', cases_per_fault=1)
    assert len(subset) == 3
    assert [s.intent_id for s in subset] == [s.intent_id for s in pack('held_out')[::4]]
    with pytest.raises(ValueError, match='1 to 4'):
        pack('held_out', cases_per_fault=0)
    with pytest.raises(ValueError, match='1 to 1'):
        pack('development', cases_per_fault=2)
    result = schedule(db, split='held_out', trials=1, cases_per_fault=1, freshness_guard=True)
    assert len(result['runs']) == 12  # Three faults x two configurations, plus six controls.
    assert result['cases_per_fault'] == 1 and result['freshness_guard'] is True
    full = schedule(db, split='held_out', trials=1)
    assert result['pack_hash'] != full['pack_hash']
    assert result['protocol_hash'] != full['protocol_hash']
    baseline = schedule(db, split='held_out', trials=1, cases_per_fault=1)
    assert result['pack_hash'] == baseline['pack_hash']
    assert result['protocol_hash'] != baseline['protocol_hash']
    snapshots = [db.get(run_id)['snapshot'] for run_id in result['runs']]
    assert sum(s['spec']['policy']['validate_freshness'] for s in snapshots) == 6
    assert all(not s['spec']['policy']['validate_freshness'] for s in snapshots[::2])
    assert all(s['spec']['policy']['validate_freshness'] for s in snapshots[1::2])


def test_limited_held_out_fixture_runs_and_replays_as_a_scoped_protocol(db):
    from skylark.wind.benchmark import schedule
    from skylark.wind.reporting import report
    protocol = schedule(db, split='held_out', trials=1, cases_per_fault=1, freshness_guard=True)
    while work_once(db):
        pass
    rows = [db.get(run_id) for run_id in protocol['runs']]
    assert all(row['status'] == 'completed' for row in rows)
    assert all(replay_record(row, db.read_events(row['id']))['matches_recorded'] for row in rows)
    evidence = report(db, protocol['id'])
    assert evidence['protocol']['protocol_hash'] == protocol['protocol_hash']
    assert {attempt['run_id'] for attempt in evidence['attempts']} == set(protocol['runs'])
    assert sum(group['total'] for group in evidence['groups']) == 12


def test_benchmark_browser_scope_excludes_unrelated_runs_and_comparisons(db):
    from skylark.wind.benchmark import schedule
    from skylark.wind.service import results

    unrelated = execute(db, 'none')['id']
    held = schedule(db, split='held_out', trials=1, cases_per_fault=1)
    dev = schedule(db, split='development', trials=1)
    recent = db.list_benchmarks()
    assert [item['id'] for item in recent] == [dev['id'], held['id']]
    assert recent[1]['run_count'] == 12 and recent[1]['protocol_hash'] == held['protocol_hash']
    assert {row['id'] for row in db.list_runs(comparison_id=held['id'])} == set(held['runs'])
    assert unrelated not in {row['id'] for row in db.list_runs(comparison_id=held['id'])}
    summary = results(db, held['id'])
    assert summary['comparison_id'] == held['id']
    assert sum(group['total'] for group in summary['groups']) == 12
    assert 'attempts' not in summary


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
