"""amazon.jobs search API.

Covers Amazon, AWS, and the subsidiaries that post through the same board.
Description plus both qualification blocks come back in the list payload, so
no hydrate step is needed.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from ..http import get_json, pace
from ..models import Job, strip_html

NAME = "amazon"
BASE = "https://www.amazon.jobs/en/search.json"
PAGE_SIZE = 100
DEFAULT_QUERIES = [
    "machine learning engineer",
    "applied scientist",
    "generative AI",
    "LLM",
    "deep learning",
    "MLOps",
    "AI engineer",
]


def fetch(entry: dict) -> list[Job]:
    queries = entry.get("queries") or DEFAULT_QUERIES
    max_pages = int(entry.get("max_pages", 3))
    seen: dict[str, Job] = {}

    for query in queries:
        for page in range(max_pages):
            params = {
                "base_query": query,
                "result_limit": PAGE_SIZE,
                "offset": page * PAGE_SIZE,
                "sort": "recent",
                "normalized_country_code[]": "USA",
            }
            data = get_json(f"{BASE}?{urlencode(params)}")
            if not isinstance(data, dict):
                break
            rows = data.get("jobs") or []
            if not rows:
                break

            for row in rows:
                job_id = str(row.get("id_icims") or row.get("id") or "")
                if not job_id or job_id in seen:
                    continue
                body = "\n\n".join(filter(None, [
                    row.get("description"),
                    row.get("basic_qualifications"),
                    row.get("preferred_qualifications"),
                ]))
                seen[job_id] = Job(
                    source=NAME,
                    company=entry.get("company", "Amazon"),
                    external_id=job_id,
                    title=row.get("title") or "",
                    url="https://www.amazon.jobs" + (row.get("job_path") or ""),
                    bucket=entry.get("bucket", "bigtech"),
                    location=row.get("normalized_location") or row.get("location") or "",
                    posted_at=_amazon_date(row.get("posted_date")),
                    description=strip_html(body),
                    employment_type=(row.get("job_schedule_type") or "").lower(),
                    department=row.get("job_family") or row.get("business_category") or "",
                    hydrated=True,
                )

            if (page + 1) * PAGE_SIZE >= int(data.get("hits") or 0):
                break
            pace()
    return list(seen.values())


def _amazon_date(value: str | None) -> str | None:
    """amazon.jobs emits 'April  1, 2026' — note the padded day."""
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None
