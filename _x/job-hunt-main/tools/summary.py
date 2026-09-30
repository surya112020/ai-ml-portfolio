"""Quick health + shortlist summary of what's currently in the DB."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhunt import store  # noqa: E402

OPEN = "closed_at IS NULL AND (blockers IS NULL OR blockers = '[]')"
SPONSOR_BLOCKED = "blockers LIKE '%sponsorship%'"
CLEARANCE_BLOCKED = "blockers LIKE '%clearance%'"


def main() -> None:
    conn = store.connect()

    def count(where: str) -> int:
        return conn.execute(f"SELECT COUNT(*) FROM jobs WHERE {where}").fetchone()[0]

    print(f"total postings tracked  : {count('1=1'):,}")
    print(f"passed title filter     : {count('score > 0'):,}")
    print(f"shortlist (55+)         : {count(f'score >= 55 AND {OPEN}'):,}")
    print(f"act-now (70+)           : {count(f'score >= 70 AND {OPEN}'):,}")
    print(f"blocked - no sponsorship: {count(SPONSOR_BLOCKED):,}")
    print(f"blocked - clearance     : {count(CLEARANCE_BLOCKED):,}")

    print("\n--- shortlist 55+ by company ---")
    rows = conn.execute(
        f"""SELECT company, COUNT(*) n, MAX(score) top FROM jobs
            WHERE score >= 55 AND {OPEN}
            GROUP BY company ORDER BY n DESC LIMIT 20"""
    ).fetchall()
    for row in rows:
        print(f"  {row['company']:<16} {row['n']:>4}   top {row['top']:.0f}")

    print("\n--- boards returning zero (need fixing) ---")
    dead = conn.execute(
        "SELECT name, last_count, last_error FROM source_health "
        "WHERE last_count = 0 OR last_count IS NULL ORDER BY name"
    ).fetchall()
    for row in dead:
        note = f" — {row['last_error'][:60]}" if row["last_error"] else ""
        print(f"  {row['name']}{note}")
    if not dead:
        print("  (none)")


if __name__ == "__main__":
    main()
