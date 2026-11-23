"""Masking of secrets in arbitrary text (logs, diagnostics, audit)."""
from __future__ import annotations

import re

_SECRET_QUERY = re.compile(r"(secret=)([0-9a-fA-F]{16,})")
_SECRET_BANNER = re.compile(r"(Secret:\s*)([0-9a-fA-F]{16,})")
_ENV_SECRET = re.compile(r"(TG_SECRET[=:]\s*[\"']?)([^\"'\s,]+)")
_BOT_TOKEN = re.compile(r"(bot\d{5,}:[A-Za-z0-9_-]{10,})")


def mask_secret_value(value: str) -> str:
    if not value:
        return value
    if len(value) > 12:
        return value[:4] + "…" + value[-4:]
    return "***"


def mask_text(text: str) -> str:
    if not text:
        return text
    text = _SECRET_QUERY.sub(lambda m: m.group(1) + m.group(2)[:4] + "…****", text)
    text = _SECRET_BANNER.sub(lambda m: m.group(1) + m.group(2)[:4] + "…****", text)
    text = _ENV_SECRET.sub(lambda m: m.group(1) + m.group(2)[:4] + "…****", text)
    text = _BOT_TOKEN.sub("bot***:***", text)
    return text
