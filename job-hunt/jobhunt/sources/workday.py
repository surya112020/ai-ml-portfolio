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


# Workday reports multi-city reqs as "2 Locations" / "3 Locations" and drops the
# actual places. That is not cosmetic: a role in Noida or Yokneam then looks
# location-less, sails past the US check, and lands at the top of the board.
# The primary city IS in the posting path — /job/Noida/Machine-Learning-Engineer-3
# — so recover it from there and keep the count for context.
_VAGUE_LOC = re.compile(r"^\s*\d+\s+locations?\s*$", re.IGNORECASE)
_PATH_LOC = re.compile(r"/job/([^/]+)/")


def _location(row: dict, path: str) -> str:
    text = (row.get("locationsText") or "").strip()
    if not _VAGUE_LOC.match(text):
        return text
    found = _PATH_LOC.search(path or "")
    if not found:
        return text
    # "USA-CA-Pleasanton" -> "USA CA Pleasanton"; "India-Noida" -> "India Noida"
    place = found.group(1).replace("-", " ").replace("_", " ").strip()
    return f"{place} ({text})" if place else text


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
                    location=_location(row, path),
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
