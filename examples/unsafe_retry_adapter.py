"""Trusted training agent for a local before/after repair test.

This adapter deliberately retries a timed-out reservation without an operation
key. It runs only against Skylark's synthetic reservation environment.
"""
from skylark.wind.domain import Final
from skylark.wind.sandbox import Sandbox


class Adapter:
    name = "unsafe-retry-local-example/1"

    def create_environment(self, scenario):
        return Sandbox(scenario)

    def run(self, task, context):
        arguments = {"resource": task["resource"], "customer": task["customer"]}
        receipt = context.call("create_reservation", arguments)
        if not receipt.get("reservation_id"):
            receipt = context.call("create_reservation", arguments)
        return Final(status="completed" if receipt.get("reservation_id") else "incomplete",
                     reservation_id=receipt.get("reservation_id"),
                     explanation="Training adapter: one retry after an uncertain response.")
