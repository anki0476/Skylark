"""Exercise the trusted local adapter handoff through the real CLI process."""
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reservation_adapter_repair_uses_same_agent_and_verifies_outcome(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "skylark", "--data", str(tmp_path / "adapter-db"),
         "adapter", str(ROOT / "examples" / "unsafe_retry_adapter.py"), "--compare-repair"],
        cwd=ROOT, capture_output=True, text=True, timeout=90, check=True,
    )
    comparison = json.loads(result.stdout)
    assert comparison["before"]["execution"] == comparison["after"]["execution"] == "completed"
    assert comparison["before"]["fault_triggered"] and comparison["after"]["fault_triggered"]
    assert comparison["before"]["evidence"] == comparison["after"]["evidence"] == "local_adapter_reported"
    assert comparison["before"]["verdict"] == "failed"
    assert comparison["before"]["reservation_count"] == 2
    assert comparison["after"]["verdict"] == "passed"
    assert comparison["after"]["reservation_count"] == 1
    assert comparison["improved_in_this_test"] is True
    assert comparison["before"]["run_id"] != comparison["after"]["run_id"]
