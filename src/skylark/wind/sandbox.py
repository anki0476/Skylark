"""Deterministic business simulator. No external side effects."""
from copy import deepcopy
from .domain import Scenario, CreateArgs, initial_state, ARG_TYPES, TOOL_SCHEMAS, VERIFIER_VERSION


class Sandbox:
    version = "reservation/1"
    verifier_version = VERIFIER_VERSION
    arg_types = ARG_TYPES
    tool_schemas = TOOL_SCHEMAS

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.state = initial_state(scenario)
        self.history = [deepcopy(self.state)]

    def fault_eligible(self, kind, name):
        return ((kind in ("timeout_after_commit", "timeout_before_commit", "incomplete_response") and name == "create_reservation")
                or (kind == "stale_read" and name in ("check_availability", "get_operation_status") and self.state["version"] > 0))

    def verify(self, final, triggered, execution_status):
        from .verifier import verify
        return verify(self.scenario, self.state, final, triggered, execution_status)

    def invoke(self, name: str, args: dict) -> dict:
        if name == "check_availability":
            if args["resource"] != self.scenario.resource:
                return {"error": "unknown_resource"}
            return {"available": max(0, self.state["capacity"] - len(self.state["reservations"])), "version": self.state["version"]}
        if name == "get_operation_status":
            row = self.state["operations"].get(args["operation_key"])
            return {"status": "completed", "reservation_id": row["reservation_id"], "version": self.state["version"]} if row else {"status": "not_found", "version": self.state["version"]}
        request = CreateArgs.model_validate(args)
        payload = {"resource": request.resource, "customer": request.customer}
        key = request.operation_key
        if key and key in self.state["operations"]:
            old = self.state["operations"][key]
            if old["payload"] != payload:
                return {"error": "idempotency_conflict"}
            return {"status": "completed", "reservation_id": old["reservation_id"], "deduplicated": True}
        if request.resource != self.scenario.resource:
            return {"error": "unknown_resource"}
        if len(self.state["reservations"]) >= self.state["capacity"]:
            return {"error": "capacity_exceeded"}
        row = {**payload, "id": f"res-{len(self.state['reservations']) + 1:03}", "operation_key": key}
        self.state["reservations"].append(row)
        self.state["version"] += 1
        if key:
            self.state["operations"][key] = {"payload": payload, "reservation_id": row["id"]}
        self.history.append(deepcopy(self.state))
        return {"status": "completed", "reservation_id": row["id"], "deduplicated": False}

    def stale(self, name: str, args: dict) -> dict:
        current = self.state
        self.state = deepcopy(self.history[-2]) if len(self.history) > 1 else deepcopy(self.history[0])
        try:
            return {**self.invoke(name, args), "version": self.state["version"]}
        finally:
            self.state = current
