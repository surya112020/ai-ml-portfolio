"""Probe candidate job-board endpoints and report which ones actually work.

Run this before adding a company to config/companies.yml — it confirms the
tenant/slug guesses against the live service instead of us assuming.

    python3 tools/probe_sources.py            # probe everything
    python3 tools/probe_sources.py workday    # probe one family
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# (family, label, method, url, body)
PROBES: list[tuple[str, str, str, str, dict | None]] = []


def get(family: str, label: str, url: str) -> None:
    PROBES.append((family, label, "GET", url, None))


def post(family: str, label: str, url: str, body: dict) -> None:
    PROBES.append((family, label, "POST", url, body))


# ---------------------------------------------------------------- greenhouse
for slug in [
    "anthropic", "databricks", "stripe", "figma", "discord", "reddit",
    "robinhood", "coinbase", "doordash", "instacart", "cruise", "waymo",
    "samsara", "airtable", "gitlab", "cloudflare", "datadog", "twosigma",
    "pinterest", "lyft", "affirm", "brex", "ramp", "plaid", "checkr",
    "duolingo", "grammarly", "hugging-face", "runwayml", "perplexityai",
]:
    get("greenhouse", slug, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")

# --------------------------------------------------------------------- ashby
for slug in [
    "openai", "ramp", "linear", "vanta", "notion", "cohere", "elevenlabs",
    "mistral", "together-ai", "sierra", "harvey", "glean", "clay",
    "deepgram", "modal", "baseten", "fireworksai", "weights-biases",
]:
    get("ashby", slug, f"https://api.ashbyhq.com/posting-api/job-board/{slug}")

# --------------------------------------------------------------------- lever
for slug in [
    "scale", "scaleai", "netflix", "palantir", "nuro", "attentive",
    "fetch", "matchgroup", "voleon", "kraken",
]:
    get("lever", slug, f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=2")

# ------------------------------------------------------------- smartrecruiters
for slug in ["Visa", "Bosch", "Ubisoft", "McDonalds", "Avery"]:
    get(
        "smartrecruiters",
        slug,
        f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=2",
    )

# ------------------------------------------------------------------- workday
# (label, tenant-host, tenant, site) — all guesses until proven here.
WORKDAY = [
    ("nvidia", "nvidia.wd5", "nvidia", "NVIDIAExternalCareerSite"),
    ("salesforce", "salesforce.wd12", "salesforce", "External_Career_Site"),
    ("adobe", "adobe.wd5", "adobe", "external_experienced"),
    ("capitalone", "capitalone.wd12", "capitalone", "Capital_One"),
    ("intuit", "intuit.wd1", "intuit", "IntuitExternalCareerSite"),
    ("snowflake", "snowflake.wd1", "snowflake", "careers"),
    ("servicenow", "servicenow.wd1", "servicenow", "ServiceNow"),
    ("workday", "workday.wd5", "workday", "Workday"),
    ("dell", "dell.wd1", "dell", "External"),
    ("hpe", "hpe.wd5", "hpe", "Jobsathpe"),
    ("cisco", "cisco.wd1", "cisco", "External"),
    ("paypal", "paypal.wd1", "paypal", "jobs"),
    ("mastercard", "mastercard.wd1", "mastercard", "CorporateCareers"),
    ("blackrock", "blackrock.wd1", "blackrock", "BlackRock_Professional"),
    ("verizon", "verizon.wd12", "verizon", "verizon-careers"),
    ("comcast", "comcast.wd5", "comcast", "Comcast_Careers"),
    ("target", "target.wd5", "target", "targetcareers"),
    ("walmart", "walmart.wd5", "walmart", "WalmartExternal"),
    ("nike", "nike.wd1", "nike", "nike"),
    ("gm", "gm.wd5", "gm", "Careers_GM"),
]
for label, host, tenant, site in WORKDAY:
    post(
        "workday",
        label,
        f"https://{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs",
        {"appliedFacets": {}, "limit": 2, "offset": 0, "searchText": "engineer"},
    )

# -------------------------------------------------------------- direct/bespoke
get("direct", "amazon", "https://www.amazon.jobs/en/search.json?base_query=machine+learning&result_limit=2")
get("direct", "microsoft", "https://gcsservices.careers.microsoft.com/search/api/v1/search?q=machine%20learning&l=en_us&pg=1&pgSz=2&lang=en_us")
get("direct", "google", "https://careers.google.com/api/v3/search/?q=machine%20learning&page_size=2")
get("direct", "apple-v1", "https://jobs.apple.com/api/v1/search?query=machine+learning")
post("direct", "apple-role", "https://jobs.apple.com/api/role/search", {"query": "machine learning", "filters": {}, "page": 1})
get("direct", "tesla", "https://www.tesla.com/cua-api/apps/careers/state")
get("direct", "ibm", "https://www-api.ibm.com/search/api/v2?q=machine+learning")
get("direct", "oracle", "https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&limit=2&finder=findReqs;siteNumber=CX_1001,keyword=machine%20learning")

# ------------------------------------------------------------------- staffing
get("staffing", "kforce", "https://www.kforce.com/api/jobsearch/search?keyword=machine%20learning&pageSize=2")
get("staffing", "insightglobal", "https://jobs.insightglobal.com/api/jobs?search=machine%20learning&limit=2")
get("staffing", "roberthalf", "https://www.roberthalf.com/bin/jobSearchServlet?country=us&keywords=machine%20learning&pagesize=2")
get("staffing", "randstad", "https://www.randstadusa.com/api/job-search/?q=machine%20learning&limit=2")
get("staffing", "teksystems", "https://www.teksystems.com/api/jobsearch?keyword=machine%20learning")
get("staffing", "dice", "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search?q=machine+learning&countryCode2=US&pageSize=2")
get("staffing", "motionrecruitment", "https://motionrecruitment.com/wp-json/wp/v2/jobs?per_page=2")
get("staffing", "jobot-gh", "https://boards-api.greenhouse.io/v1/boards/jobot/jobs")


def probe(item: tuple[str, str, str, str, dict | None]) -> str:
    family, label, method, url, body = item
    headers = {"User-Agent": UA, "Accept": "application/json"}
    try:
        resp = requests.request(
            method, url, json=body, headers=headers, timeout=25, allow_redirects=False
        )
    except Exception as exc:  # noqa: BLE001 - probe reports whatever went wrong
        return f"FAIL {family:16s} {label:22s} {type(exc).__name__}: {str(exc)[:60]}"

    if resp.status_code != 200:
        loc = resp.headers.get("Location", "")
        tail = f" -> {loc[:50]}" if loc else ""
        return f"FAIL {family:16s} {label:22s} HTTP {resp.status_code}{tail}"
    try:
        note = count_hint(resp.json())
    except (json.JSONDecodeError, ValueError):
        note = "non-JSON"
    size = len(resp.content)
    return f"OK   {family:16s} {label:22s} 200 {size:>9,}b  {note}"


def count_hint(parsed: object) -> str:
    """Best-effort 'how many postings did this return' across payload shapes."""
    if isinstance(parsed, list):
        return f"{len(parsed)} items"
    if isinstance(parsed, dict):
        for key in ("total", "totalFound", "hits", "totalCount", "count"):
            if isinstance(parsed.get(key), int):
                return f"{parsed[key]} total"
        for key in ("jobs", "jobPostings", "content", "data", "results", "postings"):
            value = parsed.get(key)
            if isinstance(value, list):
                return f"{len(value)} in '{key}'"
        return f"keys={list(parsed)[:5]}"
    return ""


def main() -> None:
    wanted = sys.argv[1] if len(sys.argv) > 1 else None
    items = [p for p in PROBES if not wanted or p[0] == wanted]
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(probe, items))
    for line in sorted(results):
        print(line)
    ok = sum(1 for line in results if line.startswith("OK"))
    print(f"\n{ok}/{len(results)} reachable")


if __name__ == "__main__":
    main()
