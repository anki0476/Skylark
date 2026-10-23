"""Independent, model-driven booking agent used for the real-agent pilot.

This module has no Skylark imports. Its retry middleware intentionally treats an
unknown create result as a failed create, the bug the pilot asks Skylark to find.
The adapter in ``nebius_agent_adapter.py`` supplies a model and a test tool.
"""

import json


CREATE_TOOL = {
    "type": "function",
    "function": {
        "name": "create_reservation",
        "description": "Reserve one resource for one customer. A missing confirmation does not prove that the booking failed.",
        "parameters": {
            "type": "object",
            "properties": {
                "resource": {"type": "string"},
                "customer": {"type": "string"},
            },
            "required": ["resource", "customer"],
            "additionalProperties": False,
        },
    },
}


class BookingAgent:
    """A small agent with a genuine model decision and a faulty retry layer."""

    def run(self, task, *, complete, call, record_decision):
        messages = [
            {"role": "system", "content": "You are a booking agent. To fulfil the user's request, call create_reservation with the exact resource and customer. The application handles the tool response and final report."},
            {"role": "user", "content": json.dumps({"resource": task["resource"], "customer": task["customer"],
                                                   "request": task["instruction"]})},
        ]
        for attempt in range(2):
            response = complete(messages, [CREATE_TOOL])
            if response.get("invalid"):
                return {"status": "incomplete", "explanation": "The model did not return a usable decision."}
            message = response["message"]
            record_decision(message)
            calls = message.get("tool_calls", [])
            if len(calls) == 1 and calls[0].get("function", {}).get("name") == "create_reservation":
                try:
                    arguments = json.loads(calls[0]["function"]["arguments"])
                except (KeyError, TypeError, ValueError):
                    return {"status": "incomplete", "explanation": "The model supplied invalid booking arguments."}
                if (isinstance(arguments, dict) and set(arguments) == {"resource", "customer"}
                        and arguments["resource"] == task["resource"] and arguments["customer"] == task["customer"]):
                    break
                return {"status": "incomplete", "explanation": "The model changed the requested booking details."}
            if attempt == 1:
                return {"status": "incomplete", "explanation": "The model did not request the booking tool."}
            messages.append({"role": "user", "content": "Call create_reservation once with the exact resource and customer."})

        first = call("create_reservation", arguments)
        if first.get("reservation_id"):
            return {"status": "completed", "reservation_id": first["reservation_id"]}
        if first.get("outcome") == "unknown" or (first.get("status") == "completed" and not first.get("reservation_id")):
            # Deliberate real-agent defect: an uncertain response is retried without
            # a stable operation key. Skylark's tested runtime guard can fix this.
            second = call("create_reservation", arguments)
            if second.get("reservation_id"):
                return {"status": "completed", "reservation_id": second["reservation_id"],
                        "explanation": "Client retry after an uncertain confirmation."}
        return {"status": "incomplete", "explanation": "The agent could not confirm the booking."}
