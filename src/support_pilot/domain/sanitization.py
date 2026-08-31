import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_KEY_PARTS = ("api_key", "apikey", "password", "secret", "token", "authorization")
SECRET_PATTERNS = (
    re.compile(r"\bexa_(?:live|test)_[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~-]{8,}\b", re.IGNORECASE),
)


def redact_text(value: str) -> str:
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def redact_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_value(item, key=str(item_key)) for item_key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_value(item) for item in value]
    return value
