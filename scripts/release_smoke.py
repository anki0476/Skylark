"""Portable offline release check. Never sends model requests or reuses user data."""
import argparse
import json
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
from skylark.wind.db import Database
from skylark.wind.domain import RunSpec, Scenario, Fault, Policy
from skylark.wind.service import enqueue
from skylark.wind.runner import work_once
from skylark.wind.artifacts import bundle, replay_zip
from skylark.wind.reporting import report
from skylark.wind.backup import create_backup, restore_backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".cache/release-smoke"))
    args = parser.parse_args()
    root = args.output.resolve() / uuid.uuid4().hex[:12]
    db = Database(root / "database")
    checks = []
    for kind in ("timeout_after_commit", "incomplete_response", "stale_read", "none", "timeout_before_commit"):
        for repaired in (False, True):
            spec = RunSpec(scenario=Scenario(fault=Fault(kind=kind)), policy=Policy(stable_key=repaired, reconcile=repaired, validate_receipt=repaired))
            ident = enqueue(db, spec, uuid.uuid4().hex)
            work_once(db)
            row = db.get(ident)
            expected = "passed" if repaired or kind in ("none", "timeout_before_commit") else "failed"
            assert row["status"] == "completed" and row["result"]["verdict"] == expected, row
            path = root / f"{kind}-{'repaired' if repaired else 'original'}.zip"
            path.write_bytes(bundle(db, ident))
            assert replay_zip(path)["matches_recorded"]
            checks.append({"condition": kind, "repaired": repaired, "verdict": expected, "bundle": path.name})
    # This archive was just generated locally; still extract only the known members.
    extracted = root / "exported-test"
    extracted.mkdir()
    with zipfile.ZipFile(path) as archive:
        for name in ("manifest.json", "run.json", "events.json", "README.txt", "test_incident.py"):
            (extracted / name).write_bytes(archive.read(name))
    subprocess.run([sys.executable, "-m", "pytest", "test_incident.py", "-q", "--basetemp", str(root / "pytest-temp")], cwd=extracted, check=True)
    assert db.budget()["accounted_usd"] == 0
    create_backup(db, root / "backup")
    recovery = restore_backup(root / "backup", root / "restored")
    assert recovery["suspended_runs"] == 0
    restored = Database(root / "restored")
    try:
        assert len(restored.list_runs()) == len(checks)
        assert bundle(restored, ident) == path.read_bytes()
    finally:
        restored.engine.dispose()
    (root / "results.json").write_text(json.dumps(report(db), indent=2) + "\n", encoding="utf-8")
    summary = {"evidence": "offline_scripted_fixtures", "checks": checks, "exported_regression": "passed", "backup_restore": "passed", "api_spend": 0, "output": str(root)}
    (root / "verification.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
