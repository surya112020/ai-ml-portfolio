"""SmartRecruiters job boards.

The list endpoint is paged at 100 and carries no JD text, so descriptions are
fetched per-posting in `hydrate` (only for jobs that survive the prescore).
"""

from __future__ import annotations

from ..http import get_json, pace
from ..models import Job, strip_html, to_iso

NAME = "smartrecruiters"
LIST = "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}"
DETAIL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings/{job_id}"
PAGE_LIMIT = 20  # 2000 postings is more than any single board we track


def fetch(entry: dict) -> list[Job]:
    slug = entry["slug"]
    jobs: list[Job] = []
    offset = 0

    for _ in range(PAGE_LIMIT):
        data = get_json(LIST.format(slug=slug, offset=offset))
        if not isinstance(data, dict):
            break
        rows = data.get("content") or []
        if not rows:
            break

        for row in rows:
            loc = row.get("location") or {}
            jobs.append(Job(
                source=NAME,
                company=entry.get("company", slug),
                external_id=str(row.get("id")),
                title=row.get("name") or "",
                url=f"https://jobs.smartrecruiters.com/{slug}/{row.get('id')}",
                bucket=entry.get("bucket", "enterprise"),
                location=loc.get("fullLocation") or ", ".join(
                    filter(None, [loc.get("city"), loc.get("region"),
                                  (loc.get("country") or "").upper()])
                ),
                posted_at=to_iso(row.get("releasedDate")),
                employment_type=((row.get("typeOfEmployment") or {})
                                 .get("label") or "").lower(),
                remote=bool(loc.get("remote")),
                department=(row.get("department") or {}).get("label") or "",
                raw={"slug": slug},
            ))

        offset += len(rows)
        if offset >= int(data.get("totalFound") or 0):
            break
        pace()
    return jobs


def hydrate(job: Job) -> str:
    slug = (job.raw or {}).get("slug")
    if not slug:
        return job.description
    data = get_json(DETAIL.format(slug=slug, job_id=job.external_id))
    if not isinstance(data, dict):
        return job.description

    sections = ((data.get("jobAd") or {}).get("sections") or {})
    parts = [
        (sections.get(key) or {}).get("text", "")
        for key in ("companyDescription", "jobDescription", "qualifications",
                    "additionalInformation")
    ]
    return strip_html("\n\n".join(filter(None, parts)))
