"""Repeat the included reservation-adapter repair test in an isolated workspace.

This exercises Skylark's local handoff and verifier, not a deployed third-party
agent. The intentionally unsafe adapter only calls the synthetic reservation tool.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

from skylark.wind.db import Database


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "examples" / "unsafe_retry_adapter.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.trials <= 100:
        parser.error("--trials must be between 1 and 100")

    data = ROOT / ".cache" / f"adapter-stress-{uuid.uuid4().hex[:10]}"
    data.mkdir(parents=True)
    db = Database(data)
    adapter_hash = hashlib.sha256(ADAPTER.read_bytes()).hexdigest()
    failures = []
    started = time.monotonic()

    for trial in range(1, args.trials + 1):
        try:
            command = [sys.executable, "-m", "skylark", "--data", str(data),
                       "adapter", str(ADAPTER), "--compare-repair"]
            completed = subprocess.run(command, cwd=ROOT, capture_output=True,
                                       text=True, timeout=60, check=True)
            pair = json.loads(completed.stdout)
            before = db.get(pair["before"]["run_id"])
            after = db.get(pair["after"]["run_id"])
            checks = {
                "same_adapter_file": pair["adapter_sha256"] == adapter_hash,
                "same_agent": before["snapshot"]["spec"]["agent_version"] == after["snapshot"]["spec"]["agent_version"],
                "completed": before["status"] == after["status"] == "completed",
                "local_evidence": pair["before"]["evidence"] == pair["after"]["evidence"] == "local_adapter_reported",
                "fault_reached": pair["before"]["fault_triggered"] and pair["after"]["fault_triggered"],
                "before_failed_with_duplicate": before["result"]["verdict"] == "failed" and len(before["state"]["reservations"]) == 2,
                "after_passed_without_duplicate": after["result"]["verdict"] == "passed" and len(after["state"]["reservations"]) == 1,
                "distinct_runs": before["id"] != after["id"],
            }
            if not all(checks.values()):
                failures.append({"trial": trial, "checks": checks,
                                 "run_ids": [before["id"], after["id"]]})
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as exc:
            failures.append({"trial": trial, "error": str(exc)})
        if trial % 5 == 0 or trial == args.trials:
            print(f"{trial}/{args.trials} pairs checked; {len(failures)} failures", flush=True)

    runs = db.list_runs(limit=2 * args.trials + 1)
    report = {"training_adapter_only": True, "repair_pairs": args.trials,
              "failed_pairs": len(failures), "unfinished_runs": sum(row["status"] in ("queued", "running") for row in runs),
              "elapsed_seconds": round(time.monotonic() - started, 2),
              "data_directory": str(data), "failures": failures}
    (data / "stress-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if failures or report["unfinished_runs"] or len(runs) != 2 * args.trials:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
