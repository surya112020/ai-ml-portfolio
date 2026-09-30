"""H-1B sponsorship history from the USCIS Employer Data Hub.

A JD that doesn't say "we won't sponsor" still tells you nothing about
whether the employer *ever* files. This does: USCIS publishes per-employer
petition counts, so an employer with 800 approvals last year is a very
different bet from one with none on record.

That matters more than usual here — the realistic H-1B cap season is March
2027, so an employer who has never filed is a dead end no matter how good
the role looks.

Source: https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub
The 2023 export is the newest one still served at a stable URL; newer years
404. Filing behaviour is stable year to year, so this is a reasonable proxy.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from functools import lru_cache
from pathlib import Path

from ..http import session

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CSV_URL = "https://www.uscis.gov/sites/default/files/document/data/h1b_datahubexport-{year}.csv"
DEFAULT_YEAR = 2023

# Corporate noise that stops "Adobe" matching "ADOBE INC".
_SUFFIXES = re.compile(
    r"\b(?:INC|INCORPORATED|LLC|L\.L\.C|LP|LLP|LTD|LIMITED|CORP|CORPORATION|"
    r"CO|COMPANY|PLC|GMBH|NV|SA|AG|HOLDINGS?|GROUP|USA|US|AMERICA|AMERICAS|"
    r"NORTH|INTERNATIONAL|TECHNOLOGIES|TECHNOLOGY|SERVICES|SOLUTIONS|"
    r"SYSTEMS|LABS?|SOFTWARE)\b",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[^A-Z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize(name: str) -> str:
    text = (name or "").upper()
    text = _PUNCT.sub(" ", text)
    text = _SUFFIXES.sub(" ", text)
    return _WS.sub(" ", text).strip()


def csv_path(year: int = DEFAULT_YEAR) -> Path:
    return DATA_DIR / f"h1b_{year}.csv"


def download(year: int = DEFAULT_YEAR, force: bool = False) -> Path:
    path = csv_path(year)
    if path.exists() and not force and path.stat().st_size > 100_000:
        return path
    log.info("downloading USCIS H-1B data for FY%s", year)
    resp = session().get(CSV_URL.format(year=year), timeout=120)
    resp.raise_for_status()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return path


@lru_cache(maxsize=1)
def _index(year: int = DEFAULT_YEAR) -> dict[str, int]:
    """normalized employer name -> total approvals (initial + continuing)."""
    path = csv_path(year)
    if not path.exists():
        try:
            download(year)
        except Exception as exc:  # noqa: BLE001 - enrichment is optional
            log.warning("could not fetch H-1B data: %s", exc)
            return {}

    totals: dict[str, int] = {}
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            employer = normalize(row.get("Employer", ""))
            if not employer:
                continue
            approvals = 0
            for column in ("Initial Approval", "Continuing Approval"):
                try:
                    approvals += int((row.get(column) or "0").replace(",", ""))
                except ValueError:
                    pass
            if approvals:
                totals[employer] = totals.get(employer, 0) + approvals
    log.info("indexed %d H-1B employers", len(totals))
    return totals


@lru_cache(maxsize=512)
def approvals_for(company: str, year: int = DEFAULT_YEAR,
                  allow_prefix: bool | None = None) -> tuple[int, str]:
    """Total approvals for a company, plus the employer name(s) that matched.

    Matching is prefix-on-token with a trailing space, never substring, so
    "VISA " cannot reach "VISALIA UNIFIED SCHOOL DISTRICT".

    Single-token queries default to exact-match only. Prefix matching on one
    common word is genuinely ambiguous: "SIERRA " legitimately matches SIERRA
    CONSULTING and SIERRA CEDAR, and "HARVEY " matches HARVEY MUDD COLLEGE —
    none of which are the companies we mean. Multi-token queries like
    "CAPITAL ONE" are specific enough to be safe. Companies whose filings
    genuinely sit under subsidiaries (Amazon) opt into prefix matching via
    h1b.employer_aliases in profile.yml.
    """
    index = _index(year)
    if not index:
        return 0, ""

    query = normalize(company)
    if not query:
        return 0, ""

    if allow_prefix is None:
        allow_prefix = " " in query  # multi-token is specific enough

    matches: dict[str, int] = {}
    if query in index:
        matches[query] = index[query]
    if allow_prefix:
        prefix = query + " "
        # Do NOT return early on an exact hit: "BLACKROCK" exists on its own
        # with 3 approvals while BLACKROCK FINANCIAL MANAGEMENT has 91.
        matches.update(
            {name: n for name, n in index.items() if name.startswith(prefix)}
        )
    if not matches:
        return 0, ""

    total = sum(matches.values())
    best = max(matches, key=lambda k: matches[k])
    label = best if len(matches) == 1 else f"{best} (+{len(matches) - 1} entities)"
    return total, label


def bonus_for(company: str, config: dict) -> tuple[float, str]:
    """Score adjustment for an employer's sponsorship track record."""
    if not config.get("enabled", True):
        return 0.0, ""

    year = int(config.get("fiscal_year", DEFAULT_YEAR))
    total, matched = approvals_for(company, year)

    if total <= 0:
        penalty = float(config.get("no_record_penalty", 0))
        if penalty:
            return -penalty, f"-{penalty:.0f} no H-1B filings on record (FY{year})"
        return 0.0, ""

    for tier in sorted(config.get("tiers", []), key=lambda t: -t["min"]):
        if total >= tier["min"]:
            bonus = float(tier["bonus"])
            return bonus, f"+{bonus:.0f} H-1B: {total:,} approvals FY{year} ({matched})"
    return 0.0, ""
