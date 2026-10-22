"""Best-effort export redaction; never claimed to find every kind of personal data."""
import os
import re

SENSITIVE_KEYS = re.compile(r"^(authorization|api[_-]?key|password|access[_-]?token|refresh[_-]?token|secret)$", re.I)
TOKEN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9_.-]+)\b")
NEBIUS_KEY = re.compile(r"\bv1\.[A-Za-z0-9_-]{40,}\.[A-Za-z0-9_-]{40,}\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def redact(value):
    changed = False
    secrets = [v for k,v in os.environ.items() if k in ("NEBIUS_API_KEY", "NEBIUS_TOKEN_FACTORY_KEY") and v]
    def visit(item):
        nonlocal changed
        if isinstance(item, dict):
            result = {}
            for key, value in item.items():
                if SENSITIVE_KEYS.match(key):
                    result[key] = "[REDACTED]"
                    changed = True
                else:
                    result[key] = visit(value)
            return result
        if isinstance(item, list):
            return [visit(v) for v in item]
        if isinstance(item, str):
            output = item
            for secret in secrets:
                output = output.replace(secret, "[REDACTED]")
            output = EMAIL.sub("[REDACTED_EMAIL]", TOKEN.sub("[REDACTED_TOKEN]",
                NEBIUS_KEY.sub("[REDACTED_TOKEN]", output)))
            changed = changed or output != item
            return output
        return item
    return visit(value), lambda: changed
