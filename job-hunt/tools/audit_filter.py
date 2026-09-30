"""Where do 11k postings go? Funnel + false-negative hunt.

The shortlist is only trustworthy if we know what it discarded. This prints
the drop reason for every posting and then samples the discards that mention
AI/ML keywords — those are the likely false negatives.

    python3 tools/audit_filter.py            # funnel + samples
    python3 tools/audit_filter.py --all      # every suspicious drop
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhunt import store  # noqa: E402
from jobhunt.models import Job  # noqa: E402
from jobhunt.scoring import excluded, is_us, load_profile, title_tier  # noqa: E402

# If a title mentions any of these, a human would at least glance at it.
# Anything dropped that matches is a false-negative candidate.
RELEVANT = re.compile(
    r"\b(machine\s*learning|ml|ai|a\.i\.|artificial\s+intelligence|llm|genai|"
    r"generative|deep\s*learning|nlp|computer\s+vision|mlops|neural|"
    r"data\s+scien|applied\s+scien|research\s+engineer|perception|"
    r"recommendation|ranking|inference|model)\b",
    re.IGNORECASE,
)


def classify(row: dict, profile: dict) -> str:
    title = row["title"]
    hit = excluded(title, profile)
    if hit:
        return f"excluded-title:{hit}"
    tier, _ = title_tier(title, profile)
    if tier == 0:
        return "no-target-title"
    if profile["locations"].get("require_us") and not is_us(row["location"] or ""):
        return "non-US"
    if row["blockers"] and row["blockers"] != "[]":
        kind = "sponsorship" if "sponsorship" in row["blockers"] else "clearance"
        return f"blocked:{kind}"
    if row["score"] < 55:
        return f"below-55 (tier{tier})"
    return "KEPT"


def main() -> None:
    show_all = "--all" in sys.argv
    profile = load_profile()
    conn = store.connect()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM jobs WHERE closed_at IS NULL"
    )]

    buckets: Counter[str] = Counter()
    suspicious: dict[str, list[dict]] = {}
    for row in rows:
        reason = classify(row, profile)
        buckets[reason] += 1
        if reason != "KEPT" and RELEVANT.search(row["title"] or ""):
            suspicious.setdefault(reason.split(" ")[0], []).append(row)

    total = len(rows)
    print(f"{'stage':<34}{'count':>8}{'%':>8}")
    print("-" * 50)
    for reason, count in buckets.most_common():
        print(f"{reason:<34}{count:>8,}{100 * count / total:>7.1f}%")
    print("-" * 50)
    print(f"{'TOTAL':<34}{total:>8,}")

    print("\n\n=== FALSE-NEGATIVE CANDIDATES ===")
    print("(dropped, but the title mentions AI/ML — would you want these?)\n")
    for reason, items in sorted(suspicious.items(),
                                key=lambda kv: -len(kv[1])):
        print(f"\n### {reason}  ({len(items):,} such postings)")
        seen_titles = set()
        shown = 0
        for row in sorted(items, key=lambda r: -r["score"]):
            key = (row["title"] or "").lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            print(f"  [{row['score']:>3.0f}] {row['company']:<14} {row['title'][:64]}")
            shown += 1
            if not show_all and shown >= 15:
                remaining = len(items) - shown
                if remaining > 0:
                    print(f"  ... +{remaining:,} more (--all to see)")
                break


if __name__ == "__main__":
    main()
