"""Extract aggregate benchmark evidence without private traces or account-wide usage."""
import argparse
import json
from pathlib import Path


PROTOCOL_FIELDS = ("kind", "mode", "split", "trials", "cases_per_fault", "freshness_guard",
                   "pack_hash", "protocol_hash", "runs")
GROUP_FIELDS = ("id", "condition", "configuration", "mode", "split", "model",
                "agent_version", "environment_version", "verifier_version", "policy_hash",
                "tool_schema_hash", "limits", "total", "passed", "failed", "safe_incomplete",
                "inconclusive", "pending", "execution_statuses", "dimensions", "fault_coverage",
                "latency_seconds", "tool_calls", "input_tokens", "output_tokens",
                "provider_requests", "accounted_usd", "uncertain_usd")
MODEL_FIELDS = ("id", "revision", "input_rate", "output_rate", "max_tokens", "temperature")
ATTEMPT_FIELDS = ("run_id", "group_id", "scenario_hash", "execution_status", "verdict",
                  "checks", "fault_triggered", "tool_calls", "elapsed_seconds",
                  "accounted_usd", "uncertain_usd")


def pick(source, fields):
    return {name: source[name] for name in fields if name in source}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    protocol = report["protocol"]
    if protocol.get("kind") != "benchmark" or report.get("comparison_id") is None:
        parser.error("Expected a report scoped to one benchmark protocol")
    groups = [pick(group, GROUP_FIELDS) for group in report["groups"]]
    for group in groups:
        group["model"] = pick(group["model"], MODEL_FIELDS)
    attempts = [pick(attempt, ATTEMPT_FIELDS) for attempt in report["attempts"]]
    run_ids = protocol["runs"]
    if len(attempts) != len(run_ids) or {a["run_id"] for a in attempts} != set(run_ids):
        parser.error("Report does not include every scheduled attempt")
    if sum(group["total"] for group in groups) != len(run_ids):
        parser.error("Group denominators do not match the protocol")
    evidence = {
        "schema_version": "skylark-public-benchmark/1",
        "protocol_id": report["comparison_id"],
        "protocol": pick(protocol, PROTOCOL_FIELDS),
        "groups": groups,
        "attempts": attempts,
        "scoped_spend": {
            "accounted_usd": round(sum(a["accounted_usd"] for a in attempts), 6),
            "uncertain_usd": round(sum(a["uncertain_usd"] for a in attempts), 6),
            "basis": "Local token-price estimate, not a provider invoice",
        },
        "limitations": "One fixed held-out variant per fault, one trial per configuration; synthetic reservation task. No reliability-rate or production-safety claim.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"{args.output}: {len(attempts)} attempts, {len(groups)} groups")


if __name__ == "__main__":
    main()
