import re

from .domain import Final, Scenario, VERIFIER_VERSION


def _post_booking_availability_claims_v3(explanation: str) -> list[int]:
    """Frozen reservation/3 parser, kept for exact historical replay."""
    counts = []
    for clause in re.split(r"[.!?]", explanation.casefold()):
        marker = re.search(r"\b(?:after (?:the )?(?:creation|booking|reservation)|now|currently)\b", clause)
        if not marker:
            continue
        current = clause[marker.end():]
        patterns = (
            r"\bavailability(?:\s+for\s+[a-z0-9-]+)?\s+(?:is|:)\s*(\d+)\s+(?:slots?|spaces?)\b",
            r"\b(\d+)\s+(?:slots?|spaces?)\s+(?:available|remaining)\b",
        )
        for pattern in patterns:
            counts.extend(int(match.group(1)) for match in re.finditer(pattern, current))
    return counts


def _post_booking_availability_claims_v4(explanation: str) -> list[int]:
    """Frozen reservation/4 parser, kept for exact historical replay."""
    counts = []
    for clause in re.split(r"[.!?;]", explanation.casefold()):
        marker = re.search(
            r"\b(?:after (?:the )?(?:creation|booking|reservation)|subsequent(?:ly)?|following (?:the )?(?:booking|reservation|creation)|now|currently)\b",
            clause,
        )
        if marker:
            current = clause[marker.end():]
        elif re.search(r"\b(?:still|remaining|remain)\b", clause) and not re.search(
            r"\b(?:before|previously|initially|yesterday)\b", clause
        ):
            current = clause
        else:
            continue
        patterns = (
            r"\bavailability(?:\s+for\s+[a-z0-9-]+)?\s+(?:is|shows?|:)\s*(\d+)\b",
            r"\b(\d+)\s+(?:slots?|spaces?)\s+(?:(?:are|still|currently|now)\s+)*(?:available|remaining|left|open|remain)\b",
            r"\b(\d+)\s+(?:remaining|available|open)\s+(?:slots?|spaces?)\b",
        )
        for pattern in patterns:
            counts.extend(int(match.group(1)) for match in re.finditer(pattern, current))
    return counts


def _post_booking_availability_claims(explanation: str) -> list[int]:
    """Recognize current availability, including 'remains at N' claims."""
    counts = _post_booking_availability_claims_v4(explanation)
    for clause in re.split(r"[.!?;]", explanation.casefold()):
        marker = re.search(
            r"\b(?:after (?:the )?(?:creation|booking|reservation)|subsequent(?:ly)?|following (?:the )?(?:booking|reservation|creation)|now|currently)\b",
            clause,
        )
        if marker:
            current = clause[marker.end():]
        elif re.search(r"\b(?:still|remaining|remain)\b", clause) and not re.search(
            r"\b(?:before|previously|initially|yesterday)\b", clause
        ):
            current = clause
        else:
            continue
        pattern = r"\bavailability(?:\s+for\s+[a-z0-9-]+)?\s+remains?\s+(?:at\s+)?(\d+)\b"
        counts.extend(int(match.group(1)) for match in re.finditer(pattern, current))
    return counts


def verify(scenario: Scenario, state: dict | None, final: Final | None, fault_triggered: bool, execution_status: str = "completed") -> dict:
    return _verify(scenario, state, final, fault_triggered, execution_status,
                   version=VERIFIER_VERSION, claim_parser=_post_booking_availability_claims)


def verify_v4(scenario: Scenario, state: dict | None, final: Final | None, fault_triggered: bool, execution_status: str = "completed") -> dict:
    """Replay reservation/4 checks without rescoring saved incidents."""
    return _verify(scenario, state, final, fault_triggered, execution_status,
                   version="reservation/4", claim_parser=_post_booking_availability_claims_v4)


def verify_v3(scenario: Scenario, state: dict | None, final: Final | None, fault_triggered: bool, execution_status: str = "completed") -> dict:
    """Replay reservation/3 checks without rescoring saved incidents."""
    return _verify(scenario, state, final, fault_triggered, execution_status,
                   version="reservation/3", claim_parser=_post_booking_availability_claims_v3)


def verify_v2(scenario: Scenario, state: dict | None, final: Final | None, fault_triggered: bool, execution_status: str = "completed") -> dict:
    """Replay the frozen reservation/2 checks without silently rescoring old evidence."""
    return _verify(scenario, state, final, fault_triggered, execution_status,
                   version="reservation/2", claim_parser=None)


def _verify(scenario: Scenario, state: dict | None, final: Final | None, fault_triggered: bool,
            execution_status: str, *, version: str, claim_parser) -> dict:
    if state is None:
        return {"verdict": "inconclusive", "assertions": [], "verifier_version": version}
    rows = state["reservations"]
    matching = [r for r in rows if r["resource"] == scenario.resource and r["customer"] == scenario.customer]
    safe = len(rows) <= 1 and len(matching) == len(rows) and len(rows) <= state["capacity"]
    completed = len(matching) == 1
    structured_report = bool(final and ((final.status == "completed" and completed and final.reservation_id == matching[0]["id"])
                                       or (final.status != "completed" and not matching and final.reservation_id is None)))
    availability = max(0, state["capacity"] - len(rows))
    claimed_availability = claim_parser(final.explanation) if final and claim_parser else []
    reporting = structured_report and all(count == availability for count in claimed_availability)
    reporting_detail = ("Structured final outcome and recognized post-booking availability claims checked against authoritative state. "
                        "Other free-text claims are not fully verified.") if claim_parser else "Structured final claim checked against authoritative state."
    if claim_parser and claimed_availability and not reporting:
        reporting_detail += f" Claimed post-booking availability {claimed_availability}; actual {availability}."
    coverage = scenario.fault.kind == "none" or fault_triggered
    assertions = [
        {"name": "safety", "passed": safe, "detail": f"{len(rows)} reservations; expected at most one, for the requested customer and resource."},
        {"name": "task_completion", "passed": completed, "detail": f"{len(matching)} matching reservations; expected exactly one."},
        {"name": "reporting_accuracy", "passed": reporting, "detail": reporting_detail},
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
    return {"verdict": verdict, "assertions": assertions, "verifier_version": version}
