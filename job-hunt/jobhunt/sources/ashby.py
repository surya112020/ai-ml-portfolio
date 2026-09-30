"""Ashby job boards.

Ships `descriptionPlain` inline, so no hydrate step — but the payloads are
large (OpenAI's board is ~12 MB) because of it.
"""

from __future__ import annotations

from ..http import get_json
from ..models import Job, to_iso

NAME = "ashby"
API = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def fetch(entry: dict) -> list[Job]:
    data = get_json(API.format(slug=entry["slug"]))
    if not isinstance(data, dict):
        return []

    jobs: list[Job] = []
    for row in data.get("jobs") or []:
        if row.get("isListed") is False:
            continue
        location = row.get("location") or ""
        extra = [
            s.get("location") for s in (row.get("secondaryLocations") or [])
            if s.get("location")
        ]
        if extra:
            location = ", ".join([location, *extra][:4])

        jobs.append(Job(
            source=NAME,
            company=entry["company"],
            external_id=str(row.get("id")),
            title=row.get("title") or "",
            url=row.get("jobUrl") or row.get("applyUrl") or "",
            bucket=entry.get("bucket", "ailab"),
            location=location,
            posted_at=to_iso(row.get("publishedAt")),
            description=row.get("descriptionPlain") or "",
            employment_type=(row.get("employmentType") or "").lower(),
            remote=row.get("isRemote"),
            department=row.get("department") or row.get("team") or "",
            hydrated=True,
        ))
    return jobs
