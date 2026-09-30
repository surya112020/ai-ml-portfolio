"""Alert dispatch.

Two modes:
  instant — a new posting at or above the instant_alert threshold, pushed the
            moment a poll finds it. This is the whole point of the system.
  digest  — one ranked summary of everything new since yesterday.

Postings are marked 'notified' so the next poll doesn't re-alert on them.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from . import macos, telegram
from ..models import Job
from ..scoring import load_profile

log = logging.getLogger(__name__)

MAX_INSTANT = 12  # beyond this, one summary line beats twelve pings


MAX_PER_COMPANY = 3  # beyond this, one company swamps the whole alert


def _collapse(rows: list[dict]) -> list[dict]:
    """One entry per company+title, then cap how much any one company can take.

    Two separate problems, same symptom. Multi-location reqs (one U.S. Bank
    role in four cities) share a dedupe_key; genuinely separate requisitions
    for an identical role (Oracle posted "Senior Platform Software Engineer,
    AI" three times in Nashville) do not. Keying on company+title catches
    both. The per-company cap then stops one employer — Adobe had 27 of 158
    — from crowding everything else out.
    """
    merged: dict = {}
    for r in rows:
        key = (r.get("company") or "").strip().lower() + "|" + \
              (r.get("title") or "").strip().lower()
        if key in merged:
            merged[key]["_also"] += 1
        else:
            r = dict(r)
            r["_also"] = 0
            merged[key] = r
    ordered = sorted(merged.values(), key=lambda r: -(r["score"] or 0))

    out, per_co, held = [], {}, 0
    for r in ordered:
        co = (r.get("company") or "").strip().lower()
        if per_co.get(co, 0) >= MAX_PER_COMPANY:
            held += 1
            continue
        per_co[co] = per_co.get(co, 0) + 1
        out.append(r)
    if out:
        out[0]["_held"] = held
    return out


def _rows_for(conn: sqlite3.Connection, uids: list[str]) -> list[dict]:
    if not uids:
        return []
    placeholders = ",".join("?" * len(uids))
    rows = conn.execute(
        f"""SELECT * FROM jobs WHERE uid IN ({placeholders})
            AND (blockers IS NULL OR blockers='[]')
            ORDER BY score DESC""",
        uids,
    ).fetchall()
    return [dict(r) for r in rows]


def instant(conn: sqlite3.Connection, new_jobs: list[Job],
            suppress: bool = False) -> int:
    """Alert on newly-appeared postings above the instant threshold.

    `suppress` is for the first run on a new machine, where every posting
    looks new and alerting would send thousands of messages.
    """
    profile = load_profile()
    threshold = profile["thresholds"]["instant_alert"]
    rows = [
        r for r in _rows_for(conn, [j.uid for j in new_jobs])
        if r["score"] >= threshold and r["status"] == "new"
    ]
    if not rows:
        return 0

    if suppress:
        log.info("suppressing %d first-run alerts", len(rows))
        _mark_notified(conn, rows)
        return 0

    unique = _collapse(rows)

    shown = unique[:MAX_INSTANT]
    collapsed = len(rows) - len(unique)
    header = (
        f"🚨 <b>{len(unique)} new opening{'s' if len(unique) != 1 else ''}</b> "
        f"(score {threshold}+)"
    )
    if collapsed:
        header += f"\n<i>{collapsed} duplicate posting(s) merged</i>"
    parts = []
    for i, r in enumerate(shown, 1):
        text_ = telegram.format_job(r, i)
        if r.get("_also"):
            text_ += f"\n   <i>+{r['_also']} more location(s)</i>"
        parts.append(text_)
    body = "\n\n".join(parts)
    if len(unique) > MAX_INSTANT:
        body += f"\n\n<i>+{len(unique) - MAX_INSTANT} more — see the dashboard</i>"
    delivered = telegram.send(f"{header}\n\n{body}")

    top = rows[0]
    macos.send(
        f"{len(rows)} new opening{'s' if len(rows) != 1 else ''}",
        f"{top['company']} — score {top['score']:.0f}",
        top["title"],
        url=top["url"],  # clicking the banner opens the posting
    )

    # Only burn the alert if it actually went out. Marking regardless means a
    # run with a missing token silently consumes every pending alert, and the
    # postings never surface again once the token is fixed.
    if not delivered:
        log.warning(
            "telegram delivery failed — leaving %d postings unnotified so "
            "they alert on the next successful run", len(rows)
        )
        return 0

    _mark_notified(conn, rows)
    return len(unique)


def digest(conn: sqlite3.Connection, hours: int = 24, limit: int = 25) -> int:
    """Ranked summary of everything first seen in the last `hours`."""
    profile = load_profile()
    threshold = profile["thresholds"]["digest"]
    since = (datetime.now(tz=timezone.utc) - timedelta(hours=hours)).isoformat()

    raw = [dict(r) for r in conn.execute(
        """SELECT * FROM jobs
           WHERE first_seen >= ? AND score >= ? AND closed_at IS NULL
             AND (blockers IS NULL OR blockers='[]')
           ORDER BY score DESC""",
        (since, threshold),
    )]
    # Same collapse the instant alerts do. One Samsara requisition posted to
    # Remote-US, Los Angeles, Seattle and Austin filled four of twenty-five
    # digest slots with the identical role.
    rows = _collapse(raw)[:limit]

    total = conn.execute(
        """SELECT COUNT(*) FROM jobs WHERE score >= ? AND closed_at IS NULL
           AND (blockers IS NULL OR blockers='[]')""",
        (threshold,),
    ).fetchone()[0]

    if not rows:
        telegram.send(
            f"☀️ <b>Morning digest</b>\n\nNothing new above {threshold} in the "
            f"last {hours}h. {total} openings still open on the shortlist."
        )
        return 0

    header = (
        f"☀️ <b>Morning digest</b> — {len(rows)} new in {hours}h "
        f"({total} on the shortlist)"
    )
    parts = []
    for i, r in enumerate(rows, 1):
        line = telegram.format_job(r, i)
        if r.get("_also"):
            line += f"\n   <i>+{r['_also']} more location(s)</i>"
        parts.append(line)
    body = "\n\n".join(parts)
    telegram.send(f"{header}\n\n{body}")
    macos.send("Morning digest", f"{len(rows)} new openings", rows[0]["title"])
    return len(rows)


def _mark_notified(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        "UPDATE jobs SET status='notified' WHERE uid=? AND status='new'",
        [(r["uid"],) for r in rows],
    )
    conn.commit()
