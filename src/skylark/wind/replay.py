"""Validate the entire deterministic tool transcript without inference or imports."""
from copy import deepcopy
from .domain import RunSpec, Final, digest, TOOL_SCHEMAS, VERIFIER_VERSION
from .sandbox import Sandbox
from .verifier import verify, verify_v2, verify_v3, verify_v4

TOOL_EVENTS = {"tool_requested", "tool_effect", "tool_observed", "agent_observed", "runtime_guard"}


class ReplayJournal:
    """In-memory context sink; no files, provider requests, or customer code."""
    def __init__(self):
        self.events = []

    def execution_state(self, _):
        return {"owner": "replay", "status": "running", "cancel_requested": False}

    def append(self, run_id, owner, kind, payload, **kwargs):
        self.events.append({"kind": kind, "payload": deepcopy(payload)})
        return len(self.events)


def normalize_invocations(events):
    identities, output = {}, []
    for event in events:
        if event["kind"] not in TOOL_EVENTS:
            continue
        payload = deepcopy(event["payload"])
        ident = payload.get("invocation_id")
        if not isinstance(ident, str) or not ident:
            raise ValueError("Tool event is missing its invocation identity")
        if event["kind"] == "tool_requested":
            if ident in identities:
                raise ValueError("Duplicated tool invocation")
            identities[ident] = len(identities)
        if ident not in identities:
            raise ValueError("Tool event has no preceding request")
        payload["invocation_id"] = identities[ident]
        output.append({"kind": event["kind"], "payload": payload})
    return output


def replay_record(run, events):
    from .runner import Context
    snapshot = run["snapshot"]
    if snapshot["tool_schema_hash"] != digest(TOOL_SCHEMAS) or snapshot["verifier_version"] not in ("reservation/2", "reservation/3", "reservation/4", VERIFIER_VERSION):
        raise ValueError("Tool or verifier version changed")
    if run["status"] != "completed":
        raise ValueError("Incomplete evidence cannot be replayed as a complete regression")
    spec = RunSpec.model_validate(snapshot["spec"])
    if spec.environment_version != "reservation/1":
        raise ValueError("Custom environment replay requires its trusted adapter; automatic code import is disabled")
    sim = Sandbox(spec.scenario)
    if digest(sim.state) != snapshot["initial_state_hash"] or snapshot["fault_schedule"] != spec.scenario.fault.model_dump():
        raise ValueError("Initial state or fault schedule differs from the frozen snapshot")
    if len(events) < 3 or events[0]["kind"] != "started" or events[-1]["kind"] != "verification":
        raise ValueError("Incomplete trace: start and terminal verification are required")
    if events[-1]["payload"] != run["result"]:
        raise ValueError("Recorded verification differs from the run result")
    claims = [e for e in events if e["kind"] == "final_claim"]
    if len(claims) != 1 or events[-2] != claims[0] or claims[0]["payload"] != run["result"].get("final"):
        raise ValueError("Missing or inconsistent structured final claim")
    identities = set()
    for sequence, event in enumerate(events, 1):
        if event["sequence"] != sequence or event["id"] in identities or event["run_id"] != run["id"]:
            raise ValueError("Incomplete event sequence")
        identities.add(event["id"])
    recorded = normalize_invocations(events)
    journal = ReplayJournal()
    context = Context(journal, run["id"], "replay", spec, sim)
    for event in events:
        if event["kind"] == "tool_requested" and event["payload"].get("origin") == "agent":
            payload = event["payload"]
            context.call(payload["name"], payload["arguments"])
    if normalize_invocations(journal.events) != recorded:
        raise ValueError("Recorded tool trace differs from replay: requests, effects, faults, safeguards, or agent observations changed")
    if run["result"].get("fault_triggered") != context.fault_triggered or run["result"].get("tool_calls") != context.calls:
        raise ValueError("Recorded fault coverage or call count differs from replay")
    final = Final.model_validate(run["result"]["final"]) if run["result"].get("final") else None
    verifier = {"reservation/2": verify_v2, "reservation/3": verify_v3, "reservation/4": verify_v4, VERIFIER_VERSION: verify}[snapshot["verifier_version"]]
    result = verifier(spec.scenario, sim.state, final, context.fault_triggered)
    result["matches_recorded"] = all(result[key] == run["result"].get(key) for key in ("verdict", "assertions", "verifier_version")) and sim.state == run["state"]
    result["evidence"] = "recorded_regression"
    return result
