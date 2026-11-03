from __future__ import annotations

import re

_HOST_PROMPT = re.compile(
    r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+(?:\s+[^%$\n]*?)?\s+[%$]\s*"
)
_SIMPLE_PROMPT = re.compile(r"^(?:>>>|>|\$|%)\s*")
_TRAILING_MARKDOWN = re.compile(r"(?:`+|\*\*|__|~~)+$")


def sanitize_text(
    value: str,
    *,
    field_name: str,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text.")

    sanitized = value.strip()
    while True:
        prompted = _HOST_PROMPT.sub("", sanitized, count=1)
        if prompted == sanitized:
            prompted = _SIMPLE_PROMPT.sub("", sanitized, count=1)
        if prompted == sanitized:
            break
        sanitized = prompted.lstrip()

    while True:
        cleaned = _TRAILING_MARKDOWN.sub("", sanitized).rstrip()
        if cleaned == sanitized:
            break
        sanitized = cleaned

    if not allow_empty and not sanitized:
        raise ValueError(f"{field_name} cannot be empty.")
    return sanitized
