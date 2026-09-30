"""Greenhouse job boards.

One request returns the whole board including JD text (`content=true`), so
there is no hydrate step. The `content` field is HTML that has been entity
-escaped a second time on the way into JSON, hence the unescape-then-strip.
"""

from __future__ import annotations

import html

from ..http import get_json
from ..models import Job, strip_html, to_iso

NAME = "greenhouse"
API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def fetch(entry: dict) -> list[Job]:
    data = get_json(API.format(slug=entry["slug"]))
    if not isinstance(data, dict):
        return []

    jobs: list[Job] = []
    for row in data.get("jobs") or []:
        offices = row.get("offices") or []
        location = (row.get("location") or {}).get("name") or ""
        if not location and offices:
            location = offices[0].get("location") or offices[0].get("name") or ""
        departments = row.get("departments") or []

        jobs.append(Job(
            source=NAME,
            company=entry.get("company") or row.get("company_name") or entry["slug"],
            external_id=str(row.get("id")),
            title=row.get("title") or "",
            url=row.get("absolute_url") or "",
            bucket=entry.get("bucket", "ailab"),
            location=location,
            posted_at=to_iso(row.get("first_published") or row.get("updated_at")),
            description=strip_html(html.unescape(row.get("content") or "")),
            department=departments[0].get("name") if departments else "",
            hydrated=True,
            raw={"requisition_id": row.get("requisition_id")},
        ))
    return jobs
