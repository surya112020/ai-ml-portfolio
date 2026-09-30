"""SQLite store. Its one critical job: tell us which postings are NEW.

Everything else in the system is downstream of `upsert` returning the rows it
inserted for the first time — that set is what gets pushed to Telegram.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Job

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uid             TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    company         TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    title           TEXT NOT NULL,
    url             TEXT NOT NULL,
    bucket          TEXT NOT NULL,
    location        TEXT,
    department      TEXT,
    posted_at       TEXT,
    employment_type TEXT,
    remote          INTEGER,
    description     TEXT,
    dedupe_key      TEXT,
    score           REAL    DEFAULT 0,
    score_reasons   TEXT,
    blockers        TEXT,           -- sponsorship / clearance hard-stops
    h1b_approvals   INTEGER DEFAULT 0,  -- USCIS filings by this employer
    first_seen      TEXT NOT NULL,  -- when WE first saw it (drives alerts)
    last_seen       TEXT NOT NULL,
    closed_at       TEXT,           -- set when it disappears from the board
    status          TEXT DEFAULT 'new',   -- new|notified|applied|skipped|closed
    applied_at      TEXT,
    notes           TEXT,
    raw             TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_score      ON jobs(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status     ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_dedupe     ON jobs(dedupe_key);
CREATE INDEX IF NOT EXISTS idx_jobs_company    ON jobs(company);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    seen        INTEGER DEFAULT 0,
    new         INTEGER DEFAULT 0,
    errors      TEXT
);

CREATE TABLE IF NOT EXISTS source_health (
    name         TEXT PRIMARY KEY,
    last_ok      TEXT,
    last_error   TEXT,
    last_count   INTEGER,
    fail_streak  INTEGER DEFAULT 0
);
"""


def now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


# Columns added after the initial schema shipped. CREATE TABLE IF NOT EXISTS
# won't add them to a database that already exists.
_ADDED_COLUMNS = (
    ("h1b_approvals", "INTEGER DEFAULT 0"),
)


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    for name, ddl in _ADDED_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}")
    conn.commit()


def upsert(conn: sqlite3.Connection, jobs: list[Job]) -> list[Job]:
    """Insert/refresh postings. Returns only those never seen before."""
    stamp = now()
    fresh: list[Job] = []
    existing = {
        row[0]
        for row in conn.execute(
            f"SELECT uid FROM jobs WHERE uid IN ({','.join('?' * len(jobs))})",
            [j.uid for j in jobs],
        )
    } if jobs else set()

    # A uid can repeat *within* one batch: several aggregator searches return
    # the same posting, and `existing` is a snapshot taken before any insert.
    batch_seen: set[str] = set()

    for job in jobs:
        if job.uid in batch_seen:
            continue
        batch_seen.add(job.uid)
        if job.uid in existing:
            # Refresh the cheap fields; never touch first_seen or status.
            conn.execute(
                """UPDATE jobs SET last_seen=?, title=?, url=?, location=?,
                   posted_at=COALESCE(?, posted_at),
                   description=CASE WHEN ?<>'' THEN ? ELSE description END,
                   closed_at=NULL
                   WHERE uid=?""",
                (stamp, job.title, job.url, job.location, job.posted_at,
                 job.description, job.description, job.uid),
            )
            continue
        conn.execute(
            """INSERT INTO jobs (uid, source, company, external_id, title, url,
                   bucket, location, department, posted_at, employment_type,
                   remote, description, dedupe_key, first_seen, last_seen, raw)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job.uid, job.source, job.company, job.external_id, job.title,
             job.url, job.bucket, job.location, job.department, job.posted_at,
             job.employment_type, int(job.is_remote()), job.description,
             job.dedupe_key, stamp, stamp, json.dumps(job.raw)[:20000]),
        )
        fresh.append(job)
    conn.commit()
    return fresh


def save_score(conn: sqlite3.Connection, uid: str, score: float,
               reasons: list[str], blockers: list[str]) -> None:
    conn.execute(
        "UPDATE jobs SET score=?, score_reasons=?, blockers=? WHERE uid=?",
        (score, json.dumps(reasons), json.dumps(blockers), uid),
    )


def save_description(conn: sqlite3.Connection, uid: str, text: str) -> None:
    conn.execute("UPDATE jobs SET description=? WHERE uid=?", (text, uid))


def mark_closed(conn: sqlite3.Connection, seen_uids: set[str],
                boards: set[tuple[str, str]]) -> int:
    """Postings on a board we just polled that no longer appear = closed.

    Scoped to (source, company) pairs, NOT to source alone. Scoping by source
    means polling one Greenhouse company marks every other Greenhouse
    company's postings closed, since none of their uids are in seen_uids.

    Only boards that actually returned data are considered, so a transient
    fetch failure can't mass-close a company's whole board either.
    """
    if not boards:
        return 0
    conditions = " OR ".join(["(source = ? AND company = ?)"] * len(boards))
    params = [value for pair in boards for value in pair]
    rows = conn.execute(
        f"""SELECT uid FROM jobs
            WHERE ({conditions}) AND closed_at IS NULL""",
        params,
    ).fetchall()
    gone = [r["uid"] for r in rows if r["uid"] not in seen_uids]
    if gone:
        conn.executemany(
            "UPDATE jobs SET closed_at=?, status='closed' WHERE uid=?",
            [(now(), uid) for uid in gone],
        )
        conn.commit()
    return len(gone)


def record_health(conn: sqlite3.Connection, name: str, count: int | None,
                  error: str | None) -> None:
    if error is None:
        conn.execute(
            """INSERT INTO source_health (name, last_ok, last_count, fail_streak)
               VALUES (?,?,?,0)
               ON CONFLICT(name) DO UPDATE SET
                 last_ok=excluded.last_ok, last_count=excluded.last_count,
                 fail_streak=0, last_error=NULL""",
            (name, now(), count or 0),
        )
    else:
        conn.execute(
            """INSERT INTO source_health (name, last_error, fail_streak)
               VALUES (?,?,1)
               ON CONFLICT(name) DO UPDATE SET
                 last_error=excluded.last_error,
                 fail_streak=source_health.fail_streak + 1""",
            (name, error[:300]),
        )
    conn.commit()


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO runs (started_at) VALUES (?)", (now(),))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, seen: int, new: int,
               errors: list[str]) -> None:
    conn.execute(
        "UPDATE runs SET finished_at=?, seen=?, new=?, errors=? WHERE id=?",
        (now(), seen, new, json.dumps(errors)[:4000], run_id),
    )
    conn.commit()
