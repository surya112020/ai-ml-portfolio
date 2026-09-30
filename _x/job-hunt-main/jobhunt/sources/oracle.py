"""Oracle Cloud (Fusion) recruiting sites.

Used by Oracle itself and by a long tail of enterprises running Oracle HCM.
The site is identified by host + siteNumber, both of which live in config.
"""

from __future__ import annotations

from urllib.parse import quote

from ..http import get_json, pace
from ..models import Job, strip_html, to_iso

NAME = "oracle"
LIST = (
    "https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    "?onlyData=true&expand=requisitionList.secondaryLocations"
    "&finder=findReqs;siteNumber={site},keyword={keyword},"
    "limit={limit},offset={offset},sortBy=POSTING_DATES_DESC"
)
# The finder key is Id (quoted), not jobId — jobId returns HTTP 400.
DETAIL = (
    "https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
    '?onlyData=true&expand=all&finder=ById;Id="{job_id}",siteNumber={site}'
)
PAGE_SIZE = 100
DEFAULT_QUERIES = ["machine learning", "artificial intelligence", "generative ai"]


def fetch(entry: dict) -> list[Job]:
    host = entry.get("host", "eeho.fa.us2.oraclecloud.com")
    site = entry.get("site", "CX_1001")
    queries = entry.get("queries") or DEFAULT_QUERIES
    max_pages = int(entry.get("max_pages", 3))
    seen: dict[str, Job] = {}

    for query in queries:
        for page in range(max_pages):
            url = LIST.format(host=host, site=site, keyword=quote(query),
                              limit=PAGE_SIZE, offset=page * PAGE_SIZE)
            data = get_json(url)
            if not isinstance(data, dict):
                break
            items = data.get("items") or []
            if not items:
                break
            block = items[0]
            rows = block.get("requisitionList") or []
            if not rows:
                break

            for row in rows:
                job_id = str(row.get("Id") or "")
                if not job_id or job_id in seen:
                    continue
                locations = [row.get("PrimaryLocation") or ""]
                locations += [
                    s.get("Name", "") for s in (row.get("secondaryLocations") or [])
                ]
                seen[job_id] = Job(
                    source=NAME,
                    company=entry["company"],
                    external_id=job_id,
                    title=row.get("Title") or "",
                    url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{job_id}",
                    bucket=entry.get("bucket", "enterprise"),
                    location=", ".join(filter(None, locations))[:200],
                    posted_at=to_iso(row.get("PostedDate")),
                    employment_type=(row.get("WorkplaceTypeCode") or "").lower(),
                    raw={"host": host, "site": site},
                )

            if (page + 1) * PAGE_SIZE >= int(block.get("TotalJobsCount") or 0):
                break
            pace()
    return list(seen.values())


def hydrate(job: Job) -> str:
    meta = job.raw or {}
    host, site = meta.get("host"), meta.get("site")
    if not host or not site:
        return job.description
    data = get_json(DETAIL.format(host=host, site=site, job_id=job.external_id))
    if not isinstance(data, dict):
        return job.description
    items = data.get("items") or []
    if not items:
        return job.description
    row = items[0]
    parts = [row.get("ExternalDescriptionStr"), row.get("ExternalQualificationsStr"),
             row.get("ExternalResponsibilitiesStr")]
    return strip_html("\n\n".join(filter(None, parts)))
