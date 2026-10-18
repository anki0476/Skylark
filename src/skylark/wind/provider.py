"""Explicit live gating, bounded inference, and conservative accounting."""
import math
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError
from .domain import canonical


class ProviderFailure(RuntimeError): pass


@dataclass(frozen=True)
class Settings:
    model: str
    input_rate: Decimal
    output_rate: Decimal
    cap_usd: Decimal
    max_tokens: int = 2048

    @classmethod
    def load(cls):
        if os.environ.get("SKYLARK_LIVE_ENABLED") != "1":
            raise ValueError("Live inference is disabled. Complete the account/model capability gate first.")
        model = os.environ.get("NEBIUS_MODEL", "")
        if not model or not os.environ.get("NEBIUS_API_KEY"):
            raise ValueError("Configure NEBIUS_MODEL and NEBIUS_API_KEY locally")
        try:
            inp = Decimal(os.environ["NEBIUS_INPUT_USD_PER_MILLION"])
            out = Decimal(os.environ["NEBIUS_OUTPUT_USD_PER_MILLION"])
            credits = Decimal(os.environ["SKYLARK_CONFIRMED_CREDITS_USD"])
            cap = Decimal(os.environ.get("SKYLARK_ALLOWANCE_USD", "2"))
        except Exception:
            raise ValueError("Configure verified prices, credited balance, and allowance locally") from None
        if not all(v.is_finite() and v > 0 for v in (inp, out, credits, cap)) or cap > credits * Decimal("0.6"):
            raise ValueError("Positive finite prices required; allowance cannot exceed 60% of confirmed credits")
        return cls(model, inp, out, cap)

    def snapshot(self):
        return {"id": self.model, "revision": "unknown", "temperature": 0, "max_tokens": self.max_tokens,
                "input_rate": str(self.input_rate), "output_rate": str(self.output_rate), "cap_usd": str(self.cap_usd)}


class Nebius:
    def __init__(self, db, run_id, settings: Settings, client=None):
        self.db, self.run_id, self.settings = db, run_id, settings
        self.client = client or OpenAI(api_key=os.environ["NEBIUS_API_KEY"], base_url="https://api.tokenfactory.nebius.com/v1/", max_retries=0, timeout=30)

    def complete(self, messages, tools, remaining=30):
        settings = self.settings
        # UTF-8 bytes plus generous protocol overhead conservatively bound input tokens.
        input_bound = len(canonical({"messages": messages, "tools": tools}).encode()) + 4096
        if input_bound > 24000:
            raise ProviderFailure("Context budget exceeded; transcript was not silently truncated")
        reservation = math.ceil(input_bound * settings.input_rate + settings.max_tokens * settings.output_rate)
        for attempt in range(2):
            if remaining <= 0:
                raise ProviderFailure("Model request deadline exhausted; no further request sent")
            ident = self.db.reserve(self.run_id, reservation, int(settings.cap_usd * 1_000_000))
            started = time.monotonic()
            try:
                response = self.client.chat.completions.create(model=settings.model, messages=messages, tools=tools,
                    temperature=0, max_tokens=settings.max_tokens, timeout=max(0.1, min(30, remaining)))
            except APIStatusError as exc:
                self.db.settle(ident, None, {"http_status": exc.status_code, "billing": "unconfirmed"})
                if attempt == 0 and exc.status_code == 429:
                    try:
                        delay = float(exc.response.headers.get("retry-after", "1"))
                    except ValueError:
                        delay = 1
                    if 0 <= delay <= min(5, remaining - (time.monotonic() - started) - 1):
                        time.sleep(delay)
                        remaining -= time.monotonic() - started
                        continue
                raise ProviderFailure(f"Provider HTTP {exc.status_code}; usage may be unconfirmed") from None
            except (APIConnectionError, APITimeoutError):
                self.db.settle(ident, None, {"billing": "unconfirmed", "error": "connection_or_timeout"})
                raise ProviderFailure("Provider connection timed out or failed; no automatic ambiguous retry") from None
            except Exception:
                self.db.settle(ident, None, {"billing": "unconfirmed", "error": "provider_error"})
                raise ProviderFailure("Provider failed; sensitive response details were not logged") from None
            counts = response.usage
            cost = None
            details = {"model": settings.model, "latency_seconds": time.monotonic() - started}
            if counts and counts.prompt_tokens >= 0 and counts.completion_tokens >= 0:
                cost = math.ceil(counts.prompt_tokens * settings.input_rate + counts.completion_tokens * settings.output_rate)
                details.update(input_tokens=counts.prompt_tokens, output_tokens=counts.completion_tokens)
            self.db.settle(ident, cost, details)
            if cost is None:
                raise ProviderFailure("Provider omitted usage; reservation retained and run stopped")
            if cost > reservation:
                raise ProviderFailure("Reported usage exceeded the reserved estimate; inspect pricing before another run")
            if not response.choices:
                raise ProviderFailure("Provider returned no choices")
            choice = response.choices[0]
            if choice.finish_reason not in ("stop", "tool_calls"):
                return {"invalid": "truncated_or_refused", "usage": details}
            message = choice.message
            if getattr(message, "refusal", None):
                return {"invalid": "refused", "usage": details}
            return {"message": message.model_dump(exclude_none=True), "usage": details}


def readiness():
    try:
        settings = Settings.load()
        return {"enabled": True, "model": settings.model, "allowance_usd": float(settings.cap_usd), "notice": "Configured locally; capability and credit balance still require verification."}
    except ValueError as exc:
        return {"enabled": False, "reason": str(exc), "key_configured": bool(os.environ.get("NEBIUS_API_KEY"))}
