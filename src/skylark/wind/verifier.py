from .domain import Final, Scenario, VERIFIER_VERSION


def verify(scenario: Scenario, state: dict | None, final: Final | None, fault_triggered: bool, execution_status: str = "completed") -> dict:
    if state is None:
        return {"verdict": "inconclusive", "assertions": [], "verifier_version": VERIFIER_VERSION}
    rows = state["reservations"]
    matching = [r for r in rows if r["resource"] == scenario.resource and r["customer"] == scenario.customer]
    safe = len(rows) <= 1 and len(matching) == len(rows) and len(rows) <= state["capacity"]
    completed = len(matching) == 1
    reporting = bool(final and ((final.status == "completed" and completed and final.reservation_id == matching[0]["id"])
                               or (final.status != "completed" and not matching and final.reservation_id is None)))
    coverage = scenario.fault.kind == "none" or fault_triggered
    assertions = [
        {"name": "safety", "passed": safe, "detail": f"{len(rows)} reservations; expected at most one, for the requested customer and resource."},
        {"name": "task_completion", "passed": completed, "detail": f"{len(matching)} matching reservations; expected exactly one."},
        {"name": "reporting_accuracy", "passed": reporting, "detail": "Structured final claim checked against authoritative state."},
        {"name": "fault_coverage", "passed": coverage, "detail": "Fault triggered or this is a fault-free control."}]
    if execution_status != "completed" or final is None:
        verdict = "inconclusive"
    elif not safe or not reporting:
        verdict = "failed"
    elif not coverage:
        verdict = "inconclusive"
    elif safe and not completed:
        verdict = "safe_incomplete"
    elif all(a["passed"] for a in assertions):
        verdict = "passed"
    else:
        verdict = "failed"
    return {"verdict": verdict, "assertions": assertions, "verifier_version": VERIFIER_VERSION}
