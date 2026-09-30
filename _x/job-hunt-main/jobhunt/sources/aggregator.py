"""Indeed + LinkedIn via JobSpy.

The direct-API adapters cover employers who run their own board. Staffing
firms mostly don't — Kforce, Insight Global, Randstad, TEKsystems and Robert
Half publish to the aggregators, and their own sites returned 404/401/403 to
every endpoint we tried. This adapter reaches them where they actually post.

Verified working: indeed, linkedin. Not working as of the last check:
google (0 rows), zip_recruiter (HTTP 403), glassdoor (HTTP 400).

Caveat: LinkedIn and Indeed rate-limit aggressively and block datacenter IP
ranges, so this is expected to be flaky on a GitHub Actions runner and
reliable on the laptop. It fails soft — a blocked scrape returns nothing and
the rest of the poll is unaffected.
"""

from __future__ import annotations

import logging

from ..models import Job, strip_html, to_iso

NAME = "aggregator"
log = logging.getLogger(__name__)

DEFAULT_SITES = ["indeed", "linkedin"]
DEFAULT_TERMS = [
    "machine learning engineer",
    "AI engineer",
    "LLM engineer",
    "generative AI engineer",
    "MLOps engineer",
]
# Companies to file under the 'staffing' bucket rather than 'enterprise'.
STAFFING = (
    "kforce", "insight global", "randstad", "teksystems", "robert half",
    "motion recruitment", "apex systems", "collabera", "cybercoders",
    "jobot", "tekwissen", "kavaliro", "diverse lynx", "infosys", "tcs",
    "cognizant", "accenture", "hcl", "wipro", "capgemini", "deloitte",
    "compunnel", "mindlance", "artech", "aditi", "judge group", "beacon hill",
)
BIGTECH = (
    "amazon", "google", "alphabet", "microsoft", "apple", "meta", "nvidia",
    "salesforce", "adobe", "netflix", "oracle", "ibm", "intel", "qualcomm",
    "tesla", "uber", "airbnb", "linkedin",
)
AILAB = (
    "openai", "anthropic", "databricks", "scale ai", "cohere", "mistral",
    "hugging face", "perplexity", "runway", "cerebras", "together ai",
    "deepmind", "waymo", "figure ai",
)


def _bucket(company: str, default: str) -> str:
    """Bucket per row, not per config entry.

    The aggregators return everyone, not just staffing firms — this feed is
    where Apple, Microsoft and Meta first showed up, and the staffing bucket
    carries a 0 weight that would unfairly bury them.
    """
    lowered = (company or "").lower()
    if any(s in lowered for s in STAFFING):
        return "staffing"
    if any(b in lowered for b in BIGTECH):
        return "bigtech"
    if any(a in lowered for a in AILAB):
        return "ailab"
    return default


def _text(value: object) -> str:
    """pandas fills missing cells with NaN (a float), not None or ''."""
    if value is None or isinstance(value, float):  # NaN is the only float here
        return ""
    return str(value).strip()


def fetch(entry: dict) -> list[Job]:
    try:
        from jobspy import scrape_jobs
    except ImportError:
        log.warning("python-jobspy not installed — skipping aggregator source")
        return []

    sites = entry.get("sites") or DEFAULT_SITES
    terms = entry.get("terms") or DEFAULT_TERMS
    wanted = int(entry.get("results_per_term", 40))
    hours_old = int(entry.get("hours_old", 336))  # two weeks
    default_bucket = entry.get("bucket", "staffing")

    seen: dict[str, Job] = {}
    for term in terms:
        try:
            frame = scrape_jobs(
                site_name=sites,
                search_term=term,
                location=entry.get("location", "United States"),
                results_wanted=wanted,
                country_indeed="USA",
                hours_old=hours_old,
                verbose=0,
            )
        except Exception as exc:  # noqa: BLE001 - rate limits are routine here
            log.warning("aggregator %r failed: %s", term, exc)
            continue
        if frame is None or frame.empty:
            continue

        for record in frame.to_dict("records"):
            company = _text(record.get("company"))
            url = _text(record.get("job_url_direct")) or _text(record.get("job_url"))
            job_id = _text(record.get("id")) or url
            title = _text(record.get("title"))
            if not company or not title or not job_id or job_id in seen:
                continue

            description = record.get("description")
            description = description if isinstance(description, str) else ""

            remote = record.get("is_remote")
            seen[job_id] = Job(
                source=NAME,
                company=company,
                external_id=job_id,
                title=title,
                url=url,
                bucket=_bucket(company, default_bucket),
                location=_text(record.get("location")),
                posted_at=to_iso(_text(record.get("date_posted"))),
                description=strip_html(description),
                employment_type=_text(record.get("job_type")).lower(),
                remote=None if remote is None or isinstance(remote, float)
                else bool(remote),
                hydrated=bool(description),
                raw={"site": _text(record.get("site"))},
            )
    return list(seen.values())
