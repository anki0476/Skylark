"""Exercise the independent agent and adapter before using paid live inference."""

import importlib.util
import json
import uuid
from pathlib import Path

from skylark.wind.db import Database
from skylark.wind.domain import Fault, Policy, RunSpec, Scenario, freeze
from skylark.wind.runner import work_once


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_independent_agent_retry_defect_and_guarded_result():
    agent = load_module("pilot_booking_agent_test", ROOT / "examples" / "pilot_booking_agent.py").BookingAgent()
    task = {"resource": "studio-a", "customer": "Alex", "instruction": "Book once"}
    decision = {"message": {"role": "assistant", "tool_calls": [
        {"id": "choice-1", "function": {"name": "create_reservation",
         "arguments": json.dumps({"resource": "studio-a", "customer": "Alex"})}}]}}
    for responses, expected_calls in [([{"error": "timeout", "outcome": "unknown"}, {"reservation_id": "r-2"}], 2),
                                      ([{"reservation_id": "r-1"}], 1)]:
        calls = []

        def call(name, arguments):
            calls.append((name, arguments))
            return responses[len(calls) - 1]

        final = agent.run(task, complete=lambda *_: decision, call=call,
                          record_decision=lambda _: None)
        assert final["status"] == "completed"
        assert len(calls) == expected_calls


def test_independent_agent_uses_supervised_adapter_and_independent_verifier(tmp_path, monkeypatch):
    module = load_module("nebius_agent_adapter_test", ROOT / "examples" / "nebius_agent_adapter.py")

    class FakeSettings:
        @classmethod
        def load(cls):
            return cls()

        def snapshot(self):
            return {"id": "fake-test-model", "revision": "test"}

    class FakeNebius:
        def __init__(self, db, run_id, settings, **kwargs):
            pass

        def complete(self, messages, tools, remaining):
            request = json.loads(messages[1]["content"])
            return {"message": {"role": "assistant", "tool_calls": [
                {"id": "choice-1", "function": {"name": "create_reservation",
                 "arguments": json.dumps({"resource": request["resource"], "customer": request["customer"]})}}]},
                "usage": {"model": "fake-test-model", "input_tokens": 20, "output_tokens": 10}}

    monkeypatch.setattr(module, "Settings", FakeSettings)
    monkeypatch.setattr(module, "Nebius", FakeNebius)
    adapter = module.Adapter()
    db = Database(tmp_path / "pilot-db")
    scenario = Scenario(fault=Fault(kind="timeout_after_commit"))
    rows = []
    for policy in (Policy(), Policy(stable_key=True, reconcile=True, validate_receipt=True)):
        environment = adapter.create_environment(scenario)
        spec = RunSpec(mode="local_adapter", agent_version=adapter.name, scenario=scenario, policy=policy)
        run_id = db.enqueue(freeze(spec, adapter.model_snapshot(), environment), uuid.uuid4().hex)
        work_once(db, adapter=adapter, run_id=run_id)
        rows.append(db.get(run_id))
        events = db.read_events(run_id)
        assert any(event["kind"] == "model_decision" for event in events)
        assert any(event["kind"] == "model_usage" for event in events)
        assert rows[-1]["result"]["fault_triggered"] is True
    assert [row["result"]["verdict"] for row in rows] == ["failed", "passed"]
    assert [len(row["state"]["reservations"]) for row in rows] == [2, 1]
