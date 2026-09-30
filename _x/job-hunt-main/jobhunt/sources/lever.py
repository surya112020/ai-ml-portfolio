"""Lever job boards. Full JD text arrives inline."""

from __future__ import annotations

from ..http import get_json
from ..models import Job, to_iso

NAME = "lever"
API = "https://api.lever.co/v0/postings/{slug}?mode=json"


def fetch(entry: dict) -> list[Job]:
    data = get_json(API.format(slug=entry["slug"]))
    if not isinstance(data, list):
        return []

    jobs: list[Job] = []
    for row in data:
        categories = row.get("categories") or {}
        locations = categories.get("allLocations") or []
        location = categories.get("location") or ""
        if len(locations) > 1:
            location = ", ".join(locations[:4])

        body = "\n\n".join(filter(None, [
            row.get("descriptionPlain"),
            *[block.get("text", "") for block in (row.get("lists") or [])],
            row.get("additionalPlain"),
        ]))

        jobs.append(Job(
            source=NAME,
            company=entry["company"],
            external_id=str(row.get("id")),
            title=row.get("text") or "",
            url=row.get("hostedUrl") or row.get("applyUrl") or "",
            bucket=entry.get("bucket", "ailab"),
            location=location,
            posted_at=to_iso(row.get("createdAt")),
            description=body,
            employment_type=(categories.get("commitment") or "").lower(),
            remote=(row.get("workplaceType") or "").lower() == "remote",
            department=categories.get("team") or "",
            hydrated=True,
            raw={"country": row.get("country")},
        ))
    return jobs
