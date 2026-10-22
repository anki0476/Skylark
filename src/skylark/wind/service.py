import uuid
import math
from .domain import RunSpec, Policy, freeze, TOOL_SCHEMAS, digest, VERIFIER_VERSION
from .provider import Settings
from .db import Conflict


def enqueue(db, spec: RunSpec, key: str, comparison_id=None):
    if spec.environment_version != "reservation/1":
        raise ValueError("Custom environments must be frozen and launched through the local adapter CLI")
    if spec.mode == "live":
        model = Settings.load().snapshot()
    elif spec.mode == "regression":
        source = db.get(spec.source_run_id)
        if not source or source["status"] != "completed":
            raise ValueError("Completed source run required")
        if source["snapshot"]["tool_schema_hash"] != digest(TOOL_SCHEMAS) or source["snapshot"]["verifier_version"] != VERIFIER_VERSION:
            raise Conflict("Recorded schema/verifier changed; replay is disabled")
        model = {"id": "recorded-decisions", "revision": "1", "source": source["id"]}
    elif spec.mode == "local_adapter":
        model = {"id": spec.agent_version, "revision": "locally-reported"}
    else:
        model = None
    return db.enqueue(freeze(spec, model), key, comparison_id)


REPAIR_PROMPT = "Use one stable operation key per user intent. After an ambiguous create response, check its status. A not_found read can be stale. Retry creates only with the same key. Require a valid reservation identifier before reporting completion; otherwise report uncertainty."
STALE_READ_REPAIR_PROMPT = "After creating a reservation, check the operation status for its version before reporting availability. If an availability response has an older version, read availability again. Do not state a numeric availability when freshness cannot be confirmed."


def require_current_dependencies(run):
    snapshot = run["snapshot"]
    if snapshot["spec"].get("environment_version", "reservation/1") != "reservation/1" or snapshot["tool_schema_hash"] != digest(TOOL_SCHEMAS) or snapshot["verifier_version"] != VERIFIER_VERSION:
        raise Conflict("Environment, tools, or verifier changed. Run a new incident before applying the reservation repair catalogue.")
    if snapshot["spec"]["mode"] == "live" and snapshot["model"] != Settings.load().snapshot():
        raise Conflict("Model or settings changed. Run a new incident before diagnosis or comparison.")


def propose(db, run_id, kind="runtime"):
    run = db.get(run_id)
    if not run or run["status"] not in ("completed", "failed"):
        raise ValueError("Inspect a finished run before proposing a repair")
    require_current_dependencies(run)
    if kind not in ("runtime", "prompt"):
        raise ValueError("Unknown repair kind")
    spec = RunSpec.model_validate(run["snapshot"]["spec"])
    evidence = [e for e in db.read_events(run_id) if e["kind"] == "tool_observed" and e["payload"].get("fault")]
    if not evidence:
        raise ValueError("No triggered fault in this run; use a fault scenario first")
    fault = evidence[0]["payload"]["fault"]
    explanation = (f"The injected {fault} changed what the agent saw from the tool. "
        "The proposed runtime configuration adds a stable operation key, reconciles ambiguous create results, "
        "and validates the receipt. Fresh comparison runs are needed to measure its effect.")
    limitation = "No arbitrary code is generated or executed. Approval creates a new configuration; existing evidence remains unchanged."
    if fault == "stale_read" and kind == "runtime":
        explanation = ("The injected stale read changed the availability response. This runtime configuration "
            "corroborates post-booking reads against the operation version and refreshes an older "
            "availability response before delivering it to the agent. Fresh trials are needed to measure its effect.")
        limitation += " Freshness is checked against the local operation record; repeated stale corroboration yields an uncertain response."
    if kind == "prompt":
        guidance = STALE_READ_REPAIR_PROMPT if fault == "stale_read" else REPAIR_PROMPT
        new = spec.policy.model_copy(update={"prompt": guidance})
        explanation = (f"The injected {fault} changed what the agent saw from the tool. "
            "The proposed prompt adds bounded recovery guidance; only fresh model trials can evaluate its effect.")
    else:
        new = spec.policy.model_copy(update={"stable_key": True, "reconcile": True, "validate_receipt": True,
                                     "validate_freshness": fault == "stale_read" or spec.policy.validate_freshness})
    provenance = "deterministic_catalogue"
    return db.save_repair(run_id, {"kind": kind, "before": spec.policy.model_dump(), "after": new.model_dump(),
        "explanation": explanation, "provenance": provenance, "evidence_event_ids": [e["id"] for e in evidence],
        "limitation": limitation})


def compare(db, repair_id, trials=1):
    repair = db.get_repair(repair_id)
    if not repair or not repair["approved"]:
        raise ValueError("An approved repair is required")
    source = db.get(repair["run_id"])
    require_current_dependencies(source)
    spec = RunSpec.model_validate(source["snapshot"]["spec"])
    if spec.mode in ("local_adapter", "regression"):
        raise ValueError("Use the CLI adapter or explicit regression run for this source")
    if repair["payload"]["kind"] == "prompt" and spec.mode != "live":
        raise ValueError("A prompt repair requires fresh live-model evaluation")
    if not 1 <= trials <= 3:
        raise ValueError("Use one to three trials")
    if spec.mode == "live":
        settings = Settings.load()
        per_call = math.ceil(24000 * settings.input_rate + settings.max_tokens * settings.output_rate)
        upper = per_call * spec.limits.model_turns * 2 * trials * 2
        if db.budget(include_attempts=False)["accounted_micros"] + upper > int(settings.cap_usd * 1_000_000):
            raise ValueError("Comparison projected maximum exceeds remaining allowance; reduce trials or configure a verified allowance")
    comparison_id = uuid.uuid4().hex
    pairs = []
    snapshots = []
    model = Settings.load().snapshot() if spec.mode == "live" else None
    for trial in range(trials):
        before = uuid.uuid4().hex
        repaired_version = spec.agent_version[:80] + "+repair-" + digest(repair["payload"]["after"])[:8]
        repaired = spec.model_copy(update={"policy": Policy.model_validate(repair["payload"]["after"]), "agent_version": repaired_version})
        after = uuid.uuid4().hex
        snapshots.extend([(before, freeze(spec, model)), (after, freeze(repaired, model))])
        pairs.append({"trial": trial + 1, "before": before, "after": after})
    payload = {"repair_id": repair_id, "pairs": pairs, "mode": spec.mode, "repair_kind": repair["payload"]["kind"]}
    db.schedule_comparison(comparison_id, payload, snapshots)
    return {"id": comparison_id, **payload}


def results(db, comparison_id=None):
    from .reporting import report
    return report(db, comparison_id, include_attempts=False)
