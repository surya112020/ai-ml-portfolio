"""Normalized job posting shared by every source adapter."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Amazon posts the same role under 30 locations; Workday appends req numbers.
# Strip that noise so one logical role collapses to one dedupe key.
_NOISE = re.compile(
    r"""
    \s*[\(\[][^)\]]*[\)\]]      # (Remote), [US], (Multiple Locations)
    | \s*[-–—,|]\s*(?:req|job)?\s*\#?\d{3,}\b   # trailing req numbers
    | \s*\b(?:remote|hybrid|onsite|on-site)\b
    | \s*\b(?:us|usa|united\s+states)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_ROMAN = re.compile(r"\s+\b(?:i{1,3}|iv|v|vi{1,3}|ix|x)\b\s*$", re.IGNORECASE)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


@dataclass
class Job:
    """One posting, normalized across ATS vendors."""

    source: str  # adapter name: greenhouse, workday, amazon, ...
    company: str  # display name: "Anthropic"
    external_id: str  # the ATS's own id
    title: str
    url: str
    bucket: str  # bigtech | ailab | enterprise | staffing
    location: str = ""
    posted_at: str | None = None  # ISO8601
    description: str = ""
    employment_type: str = ""  # fulltime | contract | unknown
    remote: bool | None = None
    department: str = ""
    # Set by the hydrate pass, not the list pass.
    hydrated: bool = False
    raw: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        """Stable identity for this exact posting. Survives re-polls."""
        key = f"{self.source}|{_slug(self.company)}|{self.external_id}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    @property
    def dedupe_key(self) -> str:
        """Collapses the same role posted across many locations/req ids."""
        title = _NOISE.sub(" ", self.title or "")
        title = _ROMAN.sub("", title)
        title = re.sub(r"\s+", " ", title).strip()
        return f"{_slug(self.company)}|{_slug(title)}"

    def is_remote(self) -> bool:
        if self.remote is not None:
            return self.remote
        blob = f"{self.title} {self.location}".lower()
        return "remote" in blob or "virtual" in blob or "work from home" in blob


def to_iso(value: object) -> str | None:
    """Best-effort date normalization across the shapes ATSs actually emit."""
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):
        # Milliseconds vs seconds since epoch.
        seconds = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
        except (OSError, ValueError, OverflowError):
            return None
    text = str(value).strip()
    if not text:
        return None
    # Workday emits relative strings: "Posted 3 Days Ago", "Posted Today".
    lowered = text.lower()
    if lowered.startswith("posted"):
        if "today" in lowered:
            days = 0
        elif "yesterday" in lowered:
            days = 1
        else:
            match = re.search(r"(\d+)\+?\s*day", lowered)
            if match:
                days = int(match.group(1))
            elif re.search(r"(\d+)\+?\s*month", lowered):
                days = 30 * int(re.search(r"(\d+)\+?\s*month", lowered).group(1))
            else:
                return None
        stamp = datetime.now(tz=timezone.utc).timestamp() - days * 86400
        return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(text.replace("Z", "+0000"), fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        return None


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")


def strip_html(html: str) -> str:
    """Enough to make JD text greppable for sponsorship/clearance phrases."""
    if not html:
        return ""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h[1-6]>", "\n", text)
    text = _TAG.sub(" ", text)
    for entity, char in (
        ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", '"'), ("&#39;", "'"), ("&rsquo;", "'"), ("&mdash;", "—"),
    ):
        text = text.replace(entity, char)
    text = _WS.sub(" ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
