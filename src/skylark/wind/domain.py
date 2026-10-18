from __future__ import annotations

import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = "skylark/1"
VERIFIER_VERSION = "reservation/2"


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Fault(Strict):
    kind: Literal["none", "timeout_after_commit", "timeout_before_commit", "stale_read", "incomplete_response"] = "timeout_after_commit"
    occurrence: int = Field(default=1, ge=1, le=16)


class Scenario(Strict):
    name: str = Field(default="The missing confirmation", min_length=1, max_length=100)
    resource: str = Field(default="studio-a", pattern=r"^[a-z0-9-]{1,40}$")
    customer: str = Field(default="Alex", min_length=1, max_length=80)
    intent_id: str = Field(default="booking-001", pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    capacity: int = Field(default=2, ge=1, le=20)
    seed: int = Field(default=17, ge=0, le=2147483647)
    split: Literal["development", "held_out", "control"] = "development"
    fault: Fault = Field(default_factory=Fault)


class Policy(Strict):
    stable_key: bool = False
    reconcile: bool = False
    validate_receipt: bool = False
    prompt: str = Field(default="", max_length=2000)


class Limits(Strict):
    model_turns: int = Field(default=8, ge=1, le=8)
    tool_calls: int = Field(default=16, ge=1, le=16)
    deadline_seconds: int = Field(default=120, ge=1, le=120)


class RunSpec(Strict):
    schema_version: Literal["skylark/1"] = VERSION
    scenario: Scenario = Field(default_factory=Scenario)
    policy: Policy = Field(default_factory=Policy)
    mode: Literal["fixture", "live", "regression", "local_adapter"] = "fixture"
    limits: Limits = Field(default_factory=Limits)
    source_run_id: str | None = Field(default=None, max_length=64)
    agent_version: str = Field(default="reservation-agent/1", max_length=100)
    environment_version: str = Field(default="reservation/1", max_length=100)

    @model_validator(mode="after")
    def replay_source(self):
        if self.mode == "regression" and not self.source_run_id:
            raise ValueError("Regression requires a recorded source run")
        return self


class Final(Strict):
    status: Literal["completed", "incomplete", "failed"]
    reservation_id: str | None = Field(default=None, max_length=100)
    explanation: str = Field(default="", max_length=2000)


class Assertion(Strict):
    name: str = Field(min_length=1, max_length=80)
    passed: bool
    detail: str = Field(max_length=1000)


class Verdict(Strict):
    verdict: Literal["passed", "failed", "safe_incomplete", "inconclusive"]
    assertions: list[Assertion] = Field(max_length=50)
    verifier_version: str = Field(default="local/unknown", max_length=100)


class CreateArgs(Strict):
    resource: str = Field(max_length=40)
    customer: str = Field(min_length=1, max_length=80)
    operation_key: str | None = Field(default=None, max_length=160)


class AvailabilityArgs(Strict):
    resource: str = Field(max_length=40)


class StatusArgs(Strict):
    operation_key: str = Field(min_length=1, max_length=160)


ARG_TYPES = {"check_availability": AvailabilityArgs, "create_reservation": CreateArgs, "get_operation_status": StatusArgs}
TOOL_SCHEMAS = [{"type": "function", "function": {"name": name, "description": description, "parameters": ARG_TYPES[name].model_json_schema()}}
                for name, description in [
                    ("check_availability", "Check capacity for a resource. Reads may be stale."),
                    ("create_reservation", "Create a reservation. An optional stable operation_key makes retries of the SAME intent idempotent. A timeout does not imply rollback."),
                    ("get_operation_status", "Look up an operation by its key. Reads may be stale.")]]
FINAL_TOOL = {"type": "function", "function": {"name": "finish", "description": "Return the final factual outcome to the user.", "parameters": Final.model_json_schema()}}


def initial_state(scenario: Scenario) -> dict:
    return {"resource": scenario.resource, "capacity": scenario.capacity, "version": 0, "reservations": [], "operations": {}}


def freeze(spec: RunSpec, model: dict | None = None, environment=None) -> dict:
    return {"spec": spec.model_dump(), "model": model or {"id": "scripted-fixture", "revision": "1"},
            "tool_schema_hash": digest(environment.tool_schemas if environment else TOOL_SCHEMAS),
            "verifier_version": environment.verifier_version if environment else VERIFIER_VERSION,
            "initial_state_hash": digest(environment.state if environment else initial_state(spec.scenario)), "fault_schedule": spec.scenario.fault.model_dump()}


def scenario_catalog() -> list[dict]:
    descriptions = {
        "timeout_after_commit": ("The missing confirmation", "The booking succeeds. Its confirmation never arrives."),
        "stale_read": ("Yesterday's availability", "A read shows an earlier state after a booking."),
        "incomplete_response": ("The broken receipt", "The booking succeeds, but its receipt has no identifier."),
        "none": ("Clear skies", "A fault-free control. Recovery must preserve normal behavior."),
        "timeout_before_commit": ("Nothing was saved", "The same timeout, but this time no booking was created.")}
    return [{"kind": kind, "title": title, "description": description} for kind, (title, description) in descriptions.items()]
