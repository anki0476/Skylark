"""Connect the independent pilot agent to Skylark's supervised local test.

This adapter makes real Nebius Nemotron calls with the locally configured key.
It must be run only with test credentials and the synthetic reservation tool.
"""

import sys
import time
from pathlib import Path

from skylark.wind.domain import Final
from skylark.wind.provider import Nebius, Settings
from skylark.wind.sandbox import Sandbox

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pilot_booking_agent import BookingAgent  # noqa: E402


class Adapter:
    name = "independent-nemotron-booking-agent/1"

    def model_snapshot(self):
        return Settings.load().snapshot()

    def create_environment(self, scenario):
        return Sandbox(scenario)

    def run(self, task, context):
        settings = Settings.load()
        if settings.snapshot() != context.db.get(context.run_id)["snapshot"]["model"]:
            raise ValueError("Pilot model configuration changed after this run was queued")
        provider = Nebius(context.db, context.run_id, settings, owner=context.owner,
                          purpose="independent_agent_pilot")
        agent = BookingAgent()

        def complete(messages, tools):
            context.check()
            remaining = context.spec.limits.deadline_seconds - (time.monotonic() - context.started)
            response = provider.complete(messages, tools, remaining)
            context.emit("model_usage", response.get("usage", {}))
            return response

        def record_decision(message):
            context.emit("model_decision", {"tool_calls": message.get("tool_calls", []),
                                            "content": message.get("content"),
                                            "notice": "Observable output, not private model reasoning."})

        final = agent.run(task, complete=complete, call=context.call,
                          record_decision=record_decision)
        return Final.model_validate(final)
