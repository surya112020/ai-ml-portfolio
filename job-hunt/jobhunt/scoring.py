"""Score a posting against the candidate profile.

Two-stage by design. `prescore` runs on the cheap list payload (title +
location only) to decide which of ~15k postings are worth spending an HTTP
request on. `score` runs after the description is hydrated and can then see
sponsorship and clearance blockers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import yaml

from .models import Job

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
PROFILE_PATH = CONFIG_DIR / "profile.yml"
IDENTITY_PATH = CONFIG_DIR / "identity.yml"

# Used when config/identity.yml is absent (fresh clone, or CI without the
# secret). Conservative: assume clearance is out of reach so clearance-gated
# postings are still filtered out rather than silently ranked.
IDENTITY_FALLBACK = {
    "identity": {},
    "work_authorization": {
        "status": "",
        "requires_sponsorship_now": False,
        "requires_sponsorship_future": True,
        "clearance_eligible": False,
    },
}

US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
}

NON_US = {
    "india", "bangalore", "bengaluru", "hyderabad", "pune", "chennai", "delhi",
    "gurgaon", "noida", "mumbai", "canada", "toronto", "vancouver", "montreal",
    "ottawa", "waterloo", "united kingdom", "london", "manchester", "cambridge, uk",
    "ireland", "dublin", "germany", "berlin", "munich", "france", "paris",
    "netherlands", "amsterdam", "spain", "madrid", "barcelona", "portugal",
    "lisbon", "poland", "warsaw", "krakow", "romania", "bucharest", "israel",
    "tel aviv", "japan", "tokyo", "china", "beijing", "shanghai", "shenzhen",
    "singapore", "australia", "sydney", "melbourne", "brazil", "sao paulo",
    "mexico", "guadalajara", "mexico city", "argentina", "costa rica",
    "philippines", "manila", "korea", "seoul", "taiwan", "taipei", "vietnam",
    "switzerland", "zurich", "sweden", "stockholm", "norway", "denmark",
    "copenhagen", "finland", "helsinki", "italy", "milan", "rome", "belgium",
    "brussels", "austria", "vienna", "czech", "prague", "hungary", "budapest",
    "greece", "athens", "turkey", "istanbul", "uae", "dubai", "abu dhabi",
    "saudi", "riyadh", "egypt", "cairo", "south africa", "nigeria", "kenya",
    "new zealand", "auckland", "emea", "apac", "latam", "united arab",
}

_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)\b")


@dataclass
class Verdict:
    score: float
    reasons: list[str]
    blockers: list[str]

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)


@lru_cache(maxsize=1)
def load_profile(path: str | None = None) -> dict:
    """Search config plus personal details, which live in a gitignored file."""
    with open(path or PROFILE_PATH) as handle:
        profile = yaml.safe_load(handle)

    merged = dict(IDENTITY_FALLBACK)
    if IDENTITY_PATH.exists():
        with open(IDENTITY_PATH) as handle:
            merged = {**merged, **(yaml.safe_load(handle) or {})}
    return {**profile, **merged}


@lru_cache(maxsize=1)
def _compiled_blockers() -> dict[str, list[re.Pattern]]:
    raw = load_profile()["blockers"]
    return {
        kind: [re.compile(p, re.IGNORECASE) for p in patterns]
        for kind, patterns in raw.items()
    }


def is_us(location: str) -> bool:
    """True unless the location clearly names somewhere outside the US."""
    text = (location or "").lower()
    if not text:
        return True  # unknown — don't discard on a guess
    if "remote" in text and not any(c in text for c in NON_US):
        return True
    for country in NON_US:
        if country in text:
            return False
    # "Austin, TX" / "Seattle, WA, United States"
    codes = set(re.findall(r",\s*([a-z]{2})\b", text))
    if codes & US_STATES:
        return True
    # Nothing named a foreign country, so treat it as US rather than silently
    # dropping a posting whose location string we simply don't recognize.
    return True


@lru_cache(maxsize=4)
def _compositional() -> tuple[re.Pattern, dict[str, re.Pattern]]:
    config = load_profile().get("compositional") or {}
    nouns = config.get("role_nouns") or []
    noun_re = re.compile(
        r"\b(?:" + "|".join(re.escape(n) for n in nouns) + r")s?\b", re.IGNORECASE
    ) if nouns else re.compile(r"(?!x)x")

    domains = {}
    for tier, key in (("tier1", "domains_tier1"), ("tier2", "domains_tier2")):
        # Entries may already be regex (\bml\b) or plain text (machine learning).
        parts = [
            p if p.startswith("\\b") or "\\" in p else re.escape(p)
            for p in (config.get(key) or [])
        ]
        domains[tier] = (
            re.compile("|".join(parts), re.IGNORECASE) if parts
            else re.compile(r"(?!x)x")
        )
    return noun_re, domains


def title_tier(title: str, profile: dict) -> tuple[int, str]:
    lowered = (title or "").lower()
    targets = profile["target_titles"]
    for tier, weight in (("tier1", 1), ("tier2", 2)):
        for phrase in targets.get(tier) or []:
            if phrase in lowered:
                return weight, phrase

    # Compositional runs BEFORE the tier3 phrases. "Software Engineer, ML
    # Platform" matches the tier3 phrase "software engineer", and returning
    # that would bury a genuine ML role at the lowest weight.
    noun_re, domains = _compositional()
    noun = noun_re.search(lowered)
    if noun:
        for tier, weight in (("tier1", 1), ("tier2", 2)):
            domain = domains[tier].search(lowered)
            if domain:
                return weight, f"{noun.group(0)}+{domain.group(0).strip()}"

    for phrase in targets.get("tier3") or []:
        if phrase in lowered:
            return 3, phrase
    return 0, ""


def excluded(title: str, profile: dict) -> str | None:
    lowered = (title or "").lower()
    for phrase in profile["exclude_titles"]:
        # Word-boundary match so "Manager" doesn't kill "Engineering Manager
        # of ML Platform"... actually it should, but it must not kill
        # "Product Management Engineer" via a bare substring hit on "manage".
        if re.search(rf"\b{re.escape(phrase)}", lowered):
            return phrase
    return None


def prescore(job: Job, profile: dict | None = None) -> Verdict:
    """Cheap pass over title + location. No description needed."""
    profile = profile or load_profile()
    reasons: list[str] = []
    blockers: list[str] = []

    hit = excluded(job.title, profile)
    if hit:
        return Verdict(0, [], [f"title excludes: {hit}"])

    weights = profile["weights"]
    tier, phrase = title_tier(job.title, profile)
    if tier == 0:
        return Verdict(0, [], ["title not a target role"])
    score = float(weights[f"title_tier{tier}"])
    reasons.append(f"title tier{tier} ({phrase})")

    if profile["locations"].get("require_us") and not is_us(job.location):
        return Verdict(0, [], [f"non-US location: {job.location}"])

    loc = (job.location or "").lower()
    best_city, best_weight = "", 0.0
    for city, weight in profile["locations"]["preferred"].items():
        if city in loc or (city == "remote" and job.is_remote()):
            if weight > best_weight:
                best_city, best_weight = city, float(weight)
    if best_weight:
        gain = best_weight * float(weights["location_scale"])
        score += gain
        reasons.append(f"location {best_city} (+{gain:.0f})")

    bonus = float(weights["bucket"].get(job.bucket, 0))
    if bonus:
        score += bonus
        reasons.append(f"{job.bucket} (+{bonus:.0f})")

    lowered = (job.title or "").lower()
    for word in profile["seniority"]["prefer"]:
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            score += float(weights["seniority_match"])
            reasons.append(f"seniority match ({word})")
            break
    else:
        # Only when nothing in `prefer` matched — a "Senior ML Engineer II"
        # should not be docked.
        for word in profile["seniority"].get("demote") or []:
            if re.search(rf"\b{re.escape(word)}\b", lowered):
                pen = float(weights.get("senior_title_penalty", 0))
                if pen:
                    score -= pen
                    reasons.append(f"-{pen:.0f} senior title ({word})")
                break

    score += _freshness(job.posted_at, reasons, weights)
    return Verdict(min(score, 100.0), reasons, blockers)


def score(job: Job, profile: dict | None = None) -> Verdict:
    """Full pass. Requires job.description to be populated."""
    profile = profile or load_profile()
    base = prescore(job, profile)
    if base.blocked:
        return base

    text = (job.description or "").lower()
    if not text:
        return base

    found: list[str] = []
    for kind, patterns in _compiled_blockers().items():
        if kind == "clearance" and profile["work_authorization"]["clearance_eligible"]:
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                found.append(f"{kind}: \"{match.group(0).strip()[:60]}\"")
                break
    if found:
        return Verdict(base.score, base.reasons, found)

    total = base.score
    reasons = list(base.reasons)
    skills = profile["skills"]
    weights = profile["weights"]

    high = sorted({s for s in skills["high_value"] if s in text})
    if high:
        gain = min(len(high) * float(weights["skill_high_each"]),
                   float(weights["skill_high_cap"]))
        total += gain
        reasons.append(f"+{gain:.0f} core skills: {', '.join(high[:6])}")

    standard = {s for s in skills["standard"] if s in text}
    if standard:
        gain = min(len(standard) * float(weights["skill_std_each"]),
                   float(weights["skill_std_cap"]))
        total += gain
        reasons.append(f"+{gain:.0f} stack overlap ({len(standard)} matches)")

    # Domain clusters. Counting keywords independently cannot tell a job that
    # merely mentions fraud from a job that IS fraud modelling. A cluster pays
    # out only once the posting clears min_hits, so depth wins over vocabulary.
    for name, cfg in (profile.get("domain_clusters") or {}).items():
        hits = sorted({t for t in (cfg.get("terms") or []) if t in text})
        need = int(cfg.get("min_hits", 2))
        if len(hits) >= need:
            gain = float(cfg.get("bonus", 0))
            total += gain
            total_label = cfg.get("label", name)
            reasons.append(
                f"+{gain:.0f} {total_label} ({len(hits)} signals: "
                f"{', '.join(hits[:4])})"
            )

    # His entire resume is financial services. A bank posting an ML role is a
    # better fit than a games studio posting the identical title.
    company_l = (job.company or "").lower()
    for name, cfg in (profile.get("sector_bonus") or {}).items():
        if any(c in company_l for c in (cfg.get("companies") or [])):
            gain = float(cfg.get("bonus", 0))
            total += gain
            reasons.append(f"+{gain:.0f} {name.replace('_', ' ')} employer")
            break

    # An explicit sponsorship-friendly statement is worth a lot to him.
    if re.search(
        r"\b(?:will|do|can|happy to|able to)\s+sponsor"
        r"|sponsorship\s+(?:is\s+)?available"
        r"|visa\s+sponsorship\s+(?:is\s+)?(?:offered|provided|available)", text
    ):
        total += float(weights["sponsors_stated"])
        reasons.append(f"+{weights['sponsors_stated']} states it sponsors visas")

    # A PhD offered as an ALTERNATIVE to a master's is not a barrier — he has
    # the MS. Only penalise when the doctorate is the floor.
    phd_or_ms = re.search(
        r"\b(?:m\.?s\.?|m\.?eng\.?|master'?s?)\b[^.]{0,50}\bor\b[^.]{0,30}"
        r"\b(?:ph\.?\s?d\.?|doctorate)\b"
        r"|\b(?:ph\.?\s?d\.?|doctorate)\b[^.]{0,30}\bor\b[^.]{0,50}"
        r"\b(?:m\.?s\.?|m\.?eng\.?|master'?s?)\b", text)
    phd_needed = re.search(
        r"\b(?:ph\.?\s?d\.?|doctoral|doctorate)\b[^.]{0,60}"
        r"\b(?:required|is required|must have|mandatory)\b"
        r"|\brequire[sd]?\b[^.]{0,40}\b(?:ph\.?\s?d\.?|doctorate)\b"
        r"|\b(?:ph\.?\s?d\.?|doctorate)\s+(?:degree\s+)?in\b", text)
    if phd_needed and not phd_or_ms:
        penalty = float(weights["phd_required_penalty"])
        total -= penalty
        reasons.append(f"-{penalty:.0f} PhD required (he has an MS)")

    years = [int(y) for y in _YEARS.findall(text)]
    if years:
        required = min(years)  # JDs list a range; the floor is what gates you
        cap = profile["seniority"]["max_reasonable_years"]
        # `>=`, not `>`. "7+ years" parses as 7, and with a cap of 7 a strict
        # `>` let every 7+ posting through unpenalised — which is how a role
        # demanding 7 years came top of the list for a 4.5-year candidate.
        if required >= cap:
            over = required - cap + 1
            base = float(weights["overqualified_penalty"])
            step = float(weights.get("overqualified_step", 6))
            # Scale with the size of the gap: a job wanting 12 years is not
            # the same miss as one wanting 6. Capped so it can't erase a role
            # that is otherwise a perfect match.
            penalty = min(base + step * (over - 1), base * 2.5)
            total -= penalty
            reasons.append(
                f"-{penalty:.0f} wants {required}+ yrs "
                f"(he has {profile['seniority']['years_experience']})"
            )

    return Verdict(max(0.0, min(total, 100.0)), reasons, [])


def _freshness(posted_at: str | None, reasons: list[str], weights: dict) -> float:
    if not posted_at:
        return 0.0
    try:
        when = datetime.fromisoformat(posted_at)
    except ValueError:
        return 0.0
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(tz=timezone.utc) - when).total_seconds() / 86400
    for limit, key, label in ((1, "fresh_24h", "<24h"), (3, "fresh_3d", "<3d"),
                              (7, "fresh_7d", "<7d")):
        if age_days <= limit:
            points = float(weights[key])
            reasons.append(f"fresh {label} (+{points:.0f})")
            return points
    return 0.0
