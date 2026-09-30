"""Runtime settings from the environment, with a .env fallback.

Kept dependency-free on purpose: this has to run identically on the laptop
and on a GitHub Actions runner, where the values arrive as repo secrets.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def get(name: str, default: str = "") -> str:
    """Environment wins over .env so CI secrets override local values."""
    return os.environ.get(name) or _dotenv().get(name) or default


def telegram() -> tuple[str, str]:
    return get("TELEGRAM_BOT_TOKEN"), get("TELEGRAM_CHAT_ID")


def telegram_configured() -> bool:
    return all(telegram())


def in_ci() -> bool:
    return get("CI").lower() == "true" or bool(get("GITHUB_ACTIONS"))
