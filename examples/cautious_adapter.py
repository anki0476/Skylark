"""Independent local agent: stable key, status reconciliation, bounded retry.

Run: python -m skylark adapter examples/cautious_adapter.py
This is explicitly a scripted local adapter, not fresh model evidence.
"""
from skylark.wind.domain import Final


class Adapter:
    name = "cautious-local-example/1"

    def create_environment(self, scenario):
        from skylark.wind.sandbox import Sandbox
        return Sandbox(scenario)

    def run(self, task, context):
        args = {"resource": task["resource"], "customer": task["customer"], "operation_key": task["intent_id"]}
        for _ in range(2):
            result = context.call("create_reservation", args)
            if result.get("reservation_id"):
                return Final(status="completed", reservation_id=result["reservation_id"])
            result = context.call("get_operation_status", {"operation_key": task["intent_id"]})
            if result.get("reservation_id"):
                return Final(status="completed", reservation_id=result["reservation_id"])
        return Final(status="incomplete", explanation="Could not verify the booking within the recovery limit.")
