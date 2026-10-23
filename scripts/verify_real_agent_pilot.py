"""Check the stored evidence behind one live independent-agent comparison."""

import argparse
import hashlib
import json
from pathlib import Path

from skylark.wind.db import Database


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "examples" / "nebius_agent_adapter.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--data", type=Path, default=ROOT / ".cache" / "ux-preview")
    args = parser.parse_args()

    report_bytes = args.report.read_bytes()
    # Windows PowerShell 5.1 Tee-Object writes UTF-16; PowerShell 7 uses UTF-8.
    encoding = "utf-16" if report_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    pair = json.loads(report_bytes.decode(encoding))
    db = Database(args.data)
    before = db.get(pair["before"]["run_id"])
    after = db.get(pair["after"]["run_id"])
    if before is None or after is None:
        parser.error("The report's run IDs are not in the selected database")

    def model_evidence(row):
        events = db.read_events(row["id"])
        usage = [event["payload"] for event in events if event["kind"] == "model_usage"]
        decisions = [event["payload"] for event in events if event["kind"] == "model_decision"]
        return (bool(usage) and all(item.get("input_tokens", 0) > 0 and
                                    item.get("output_tokens", 0) > 0 for item in usage)
                and any(call.get("function", {}).get("name") == "create_reservation"
                        for item in decisions for call in item.get("tool_calls", [])))

    checks = {
        "same_adapter_file": pair["adapter_sha256"] == hashlib.sha256(ADAPTER.read_bytes()).hexdigest(),
        "same_agent": before["snapshot"]["spec"]["agent_version"] ==
                      after["snapshot"]["spec"]["agent_version"] == pair["agent"],
        "same_model": before["snapshot"]["model"] == after["snapshot"]["model"],
        "live_model": before["snapshot"]["model"]["id"].startswith("nvidia/"),
        "two_completed_runs": before["id"] != after["id"] and
                              before["status"] == after["status"] == "completed",
        "fresh_model_calls": model_evidence(before) and model_evidence(after),
        "fault_reached_twice": bool(before["result"]["fault_triggered"] and
                                    after["result"]["fault_triggered"]),
        "duplicate_before": before["result"]["verdict"] == "failed" and
                            len(before["state"]["reservations"]) == 2,
        "single_booking_after": after["result"]["verdict"] == "passed" and
                                len(after["state"]["reservations"]) == 1,
        "comparison_reported_improved": pair["improved_in_this_test"] is True,
    }
    print(json.dumps({"passed": all(checks.values()), "checks": checks,
                      "run_ids": [before["id"], after["id"]]}, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
