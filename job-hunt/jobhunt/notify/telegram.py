"""Telegram push — the channel that reaches him during work hours."""

from __future__ import annotations

import html
import logging

from .. import settings
from ..http import session

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"
# Telegram hard-rejects messages over 4096 chars.
LIMIT = 4000


def send(text: str, disable_preview: bool = True) -> bool:
    token, chat_id = settings.telegram()
    if not token or not chat_id:
        log.warning("telegram not configured — set TELEGRAM_BOT_TOKEN/CHAT_ID")
        return False

    ok = True
    for chunk in _split(text):
        resp = session().post(
            API.format(token=token, method="sendMessage"),
            json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": disable_preview,
            },
            timeout=20,
        )
        if resp.status_code != 200:
            log.error("telegram %s: %s", resp.status_code, resp.text[:200])
            ok = False
    return ok


def _split(text: str) -> list[str]:
    """Split on line boundaries so an entry is never cut mid-way."""
    if len(text) <= LIMIT:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > LIMIT:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


def format_job(row: dict, rank: int | None = None) -> str:
    """One posting as a Telegram HTML block."""
    title = html.escape(row["title"])
    company = html.escape(row["company"])
    location = html.escape((row["location"] or "")[:60])
    prefix = f"{rank}. " if rank else ""
    tags = []
    if row.get("duplicate_count", 1) > 1:
        tags.append(f"{row['duplicate_count']} locations")
    if row.get("remote"):
        tags.append("remote")
    suffix = f"  <i>{' · '.join(tags)}</i>" if tags else ""
    return (
        f"{prefix}<b>{row['score']:.0f}</b> · <a href=\"{html.escape(row['url'])}\">"
        f"{title}</a>\n     {company} — {location}{suffix}"
    )
