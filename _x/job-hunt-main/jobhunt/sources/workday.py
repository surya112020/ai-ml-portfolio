"""Workday CXS boards — the widest-reach adapter here.

Every Workday tenant exposes the same JSON contract at
    /wday/cxs/{tenant}/{site}/jobs        (POST, paged, 20 max per page)
    /wday/cxs/{tenant}/{site}{externalPath}   (GET, one posting + JD)

The list pass carries no description, so `hydrate` does a second request per
posting. That is why the runner only hydrates jobs that pass the prescore.
"""

from __future__ import annotations

import re

from ..http import get_json, pace, post_json
from ..models import Job, strip_html, to_iso

NAME = "workday"
PAGE_SIZE = 20
DEFAULT_QUERIES = [
    "machine learning engineer",
    "AI engineer",
    "generative AI",
    "LLM",
    "deep learning",
    "MLOps",
    "applied scientist",
]
_REQ_ID = re.compile(r"_(?:R|JR|REQ)?[-\w]*?(\d{4,})\s*$", re.IGNORECASE)


def _base(entry: dict) -> str:
    return f"https://{entry['host']}.myworkdayjobs.com/wday/cxs/{entry['tenant']}/{entry['site']}"


def fetch(entry: dict) -> list[Job]:
    queries = entry.get("queries") or DEFAULT_QUERIES
    max_pages = int(entry.get("max_pages", 5))
    base = _base(entry)
    human = f"https://{entry['host']}.myworkdayjobs.com/en-US/{entry['site']}"

    seen: dict[str, Job] = {}
    for query in queries:
        for page in range(max_pages):
            payload = {
                "appliedFacets": {},
                "limit": PAGE_SIZE,
                "offset": page * PAGE_SIZE,
                "searchText": query,
            }
            data = post_json(f"{base}/jobs", payload)
            if not isinstance(data, dict):
                break
            rows = data.get("jobPostings") or []
            if not rows:
                break

            for row in rows:
                path = row.get("externalPath") or ""
                if not path:
                    continue
                bullets = row.get("bulletFields") or []
                external_id = bullets[0] if bullets else _path_id(path)
                if external_id in seen:
                    continue
                seen[external_id] = Job(
                    source=NAME,
                    company=entry["company"],
                    external_id=str(external_id),
                    title=row.get("title") or "",
                    url=f"{human}{path}",
                    bucket=entry.get("bucket", "enterprise"),
                    location=row.get("locationsText") or "",
                    posted_at=to_iso(row.get("postedOn")),
                    raw={"cxs": f"{base}{path}"},
                )

            if (page + 1) * PAGE_SIZE >= int(data.get("total") or 0):
                break
            pace()
    return list(seen.values())


def _path_id(path: str) -> str:
    match = _REQ_ID.search(path)
    return match.group(0).lstrip("_") if match else path.rsplit("/", 1)[-1]


def hydrate(job: Job) -> str:
    url = (job.raw or {}).get("cxs")
    if not url:
        return job.description
    data = get_json(url)
    if not isinstance(data, dict):
        return job.description
    info = data.get("jobPostingInfo") or {}
    return strip_html(info.get("jobDescription") or "")
