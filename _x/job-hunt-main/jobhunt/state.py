"""Portable first_seen / application state.

The SQLite DB is disposable — every poll re-fetches all ~11k postings. The
only thing that genuinely cannot be recomputed is *when we first saw a
posting* and *what he has done about it*. That's what travels between the
laptop and CI, as a small gzipped JSON file committed to the repo.

Committing the whole DB instead would mean a multi-megabyte binary diff
every 15 minutes.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "state.json.gz"

# Columns worth preserving across machines. Everything else is re-derived.
FIELDS = ("first_seen", "status", "applied_at", "notes")


def export_state(conn: sqlite3.Connection, path: Path = STATE_PATH) -> int:
    rows = conn.execute(
        f"SELECT uid, {', '.join(FIELDS)} FROM jobs WHERE closed_at IS NULL"
        "    OR status IN ('applied', 'skipped')"
    ).fetchall()
    payload = {
        row["uid"]: {f: row[f] for f in FIELDS if row[f] is not None}
        for row in rows
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
    return len(payload)


def import_state(conn: sqlite3.Connection, path: Path = STATE_PATH) -> int:
    """Restore first_seen/status for postings already present in the DB.

    Runs after the first poll on a fresh machine, so the rows exist and only
    need their history reapplied. Without this, every posting looks brand new
    on a CI runner and the first run would alert on all 11k of them.
    """
    if not path.exists():
        return 0
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)

    applied = 0
    for uid, values in payload.items():
        sets = [f"{f}=?" for f in FIELDS if f in values]
        if not sets:
            continue
        params = [values[f] for f in FIELDS if f in values]
        cur = conn.execute(
            f"UPDATE jobs SET {', '.join(sets)} WHERE uid=?", (*params, uid)
        )
        applied += cur.rowcount
    conn.commit()
    return applied


def seen_before(path: Path = STATE_PATH) -> set[str]:
    """UIDs known from a previous run — used to suppress first-run alert floods."""
    if not path.exists():
        return set()
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return set(json.load(handle))
