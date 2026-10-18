"""Reports preserve denominators, unknown evidence, and incompatible configurations."""
from collections import Counter
from math import sqrt
from statistics import median
from .domain import digest

DIMENSIONS = ("safety", "task_completion", "reporting_accuracy", "fault_coverage")
NOTICE = ("Fixtures and recorded regressions do not establish live-model reliability. "
          "Rates use observed checks only; unknown checks and infrastructure failures are reported separately. "
          "Wilson intervals are descriptive under an independent-trial assumption. Repeated scenarios are correlated; "
          "these intervals do not establish universal safety.")


def proportion(passed, failed, unknown, not_applicable=0):
    n = passed + failed
    interval = None
    if n:
        rate, z = passed / n, 1.959963984540054
        denominator = 1 + z * z / n
        center = (rate + z * z / (2 * n)) / denominator
        radius = z * sqrt(rate * (1-rate) / n + z*z / (4*n*n)) / denominator
        interval = [round(max(0, center-radius), 6), round(min(1, center+radius), 6)]
    return {"passed": passed, "failed": failed, "unknown": unknown, "not_applicable": not_applicable,
            "observed": n, "rate": passed/n if n else None, "wilson_95": interval}


def distribution(values):
    return {"observed": len(values), "median": median(values) if values else None,
            "min": min(values) if values else None, "max": max(values) if values else None}


def report(db, comparison_id=None):
    protocol = db.get_comparison(comparison_id) if comparison_id else None
    if comparison_id and not protocol:
        raise ValueError("Comparison or benchmark not found")
    rows = [row for row in db.list_runs(None) if not comparison_id or row["comparison_id"] == comparison_id]
    budget = db.budget()
    usage_by_run = {}
    for attempt in budget["attempts"]:
        usage_by_run.setdefault(attempt["run_id"], []).append(attempt)
    groups, attempts = {}, []
    for row in rows:
        snapshot, result = row["snapshot"], row["result"] or {}
        spec, policy = snapshot["spec"], snapshot["spec"]["policy"]
        scenario = spec["scenario"]
        guard = any(policy.get(k) for k in ("stable_key", "reconcile", "validate_receipt"))
        configuration = "runtime_and_prompt" if guard and policy.get("prompt") else "runtime_guard" if guard else "prompt" if policy.get("prompt") else "original"
        identity = {"mode": spec["mode"], "condition": scenario["fault"]["kind"], "split": scenario["split"],
                    "model": snapshot["model"], "policy_hash": digest(policy), "agent_version": spec["agent_version"],
                    "environment_version": spec.get("environment_version", "reservation/1"), "verifier_version": snapshot["verifier_version"],
                    "tool_schema_hash": snapshot["tool_schema_hash"], "limits": spec["limits"]}
        key = digest(identity)
        group = groups.setdefault(key, {**identity, "id": key, "configuration": configuration,
            "total": 0, "passed": 0, "failed": 0, "safe_incomplete": 0, "inconclusive": 0, "pending": 0,
            "execution_statuses": Counter(), "scenario_hashes": set(), "checks": {d: Counter() for d in DIMENSIONS},
            "latencies": [], "calls": [], "accounted_micros": 0, "uncertain_micros": 0, "input_tokens": 0,
            "output_tokens": 0, "provider_requests": 0})
        group["total"] += 1
        group["execution_statuses"][row["status"]] += 1
        group["scenario_hashes"].add(digest(scenario))
        verdict = "pending" if row["status"] in ("queued", "running") else result.get("verdict", "inconclusive")
        # An interrupted run's partial assertions must not become a successful trial.
        if row["status"] != "completed" and verdict == "passed":
            verdict = "inconclusive"
        group[verdict] += 1
        assertions = {a["name"]: a["passed"] for a in result.get("assertions", [])} if row["status"] == "completed" else {}
        checks = {}
        for dimension in DIMENSIONS:
            value = assertions.get(dimension)
            label = "not_applicable" if dimension == "fault_coverage" and scenario["fault"]["kind"] == "none" else "unknown" if value is None else "passed" if value else "failed"
            group["checks"][dimension][label] += 1
            checks[dimension] = label
        if result.get("elapsed_seconds") is not None:
            group["latencies"].append(result["elapsed_seconds"])
        if result.get("tool_calls") is not None:
            group["calls"].append(result["tool_calls"])
        usage = usage_by_run.get(row["id"], [])
        accounted = sum(u["accounted_micros"] for u in usage)
        uncertain = sum(u["accounted_micros"] for u in usage if u["status"] in ("reserved", "uncertain"))
        group["accounted_micros"] += accounted
        group["uncertain_micros"] += uncertain
        group["provider_requests"] += len(usage)
        group["input_tokens"] += sum(u["payload"].get("input_tokens", 0) for u in usage)
        group["output_tokens"] += sum(u["payload"].get("output_tokens", 0) for u in usage)
        attempts.append({"run_id": row["id"], "group_id": key, "scenario_hash": digest(scenario),
            "execution_status": row["status"], "verdict": verdict, "checks": checks,
            "fault_triggered": result.get("fault_triggered"), "tool_calls": result.get("tool_calls"),
            "elapsed_seconds": result.get("elapsed_seconds"), "accounted_usd": accounted/1e6, "uncertain_usd": uncertain/1e6})
    output = []
    for group in groups.values():
        group["dimensions"] = {d: proportion(c["passed"], c["failed"], c["unknown"], c["not_applicable"]) for d, c in group.pop("checks").items()}
        group["latency_seconds"] = distribution(group.pop("latencies"))
        group["tool_calls"] = distribution(group.pop("calls"))
        group["unique_scenarios"] = len(group.pop("scenario_hashes"))
        group["accounted_usd"] = group.pop("accounted_micros") / 1e6
        group["uncertain_usd"] = group.pop("uncertain_micros") / 1e6
        output.append(group)
    return {"schema_version": "skylark-report/1", "comparison_id": comparison_id,
            "protocol": protocol["payload"] if protocol else None, "groups": output, "attempts": attempts,
            "notice": NOTICE, "cost_scope": "All provider calls attributed to each run, including any diagnosis; unreported tokens are unknown, not zero-cost.",
            "budget": budget}
