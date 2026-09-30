"""Build application material for one posting.

Deliberately deterministic — it reorders and selects his real bullets by
overlap with the job description. It does not invent experience, and it does
not rewrite his claims. Every line in the output is something already in
config/resume.yml.

The gap report is the useful part: it names what the JD asks for that the
résumé never mentions, so he can decide whether it's a real gap, a wording
mismatch, or a reason to skip the role.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from ..scoring import load_profile

CONFIG = Path(__file__).resolve().parent.parent.parent / "config"
RESUME_PATH = CONFIG / "resume.yml"

# Things a JD commonly asks for. Used for the gap report, so the vocabulary
# matters more than completeness — a term absent here is simply not checked.
CHECK_TERMS = [
    "pytorch", "tensorflow", "jax", "kubernetes", "docker", "terraform",
    "aws", "gcp", "azure", "spark", "kafka", "airflow", "ray", "flink",
    "langchain", "langgraph", "llamaindex", "rag", "vector database",
    "fine-tuning", "lora", "peft", "rlhf", "dpo", "sft", "pretraining",
    "deepspeed", "fsdp", "vllm", "triton", "onnx", "tensorrt", "quantization",
    "transformers", "diffusion", "multimodal", "computer vision", "nlp",
    "speech", "recommendation", "ranking", "search relevance", "embeddings",
    "mlops", "mlflow", "kubeflow", "sagemaker", "vertex ai", "bedrock",
    "ci/cd", "observability", "drift", "a/b testing", "experimentation",
    "python", "go", "rust", "java", "scala", "c++", "sql", "typescript",
    "fastapi", "grpc", "microservices", "distributed systems", "gpu",
    "agentic", "agents", "tool calling", "evaluation", "guardrails",
    "responsible ai", "privacy", "pii", "snowflake", "databricks", "dbt",
]

_WORD = re.compile(r"[a-z0-9+#./-]+")


@dataclass
class Tailored:
    job: dict
    matched: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    bullets: list[tuple[str, str, str]] = field(default_factory=list)
    skill_order: list[str] = field(default_factory=list)


def load_resume(path: Path = RESUME_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — copy your résumé content there first."
        )
    with open(path) as handle:
        return yaml.safe_load(handle)


def _mentions(text: str, term: str) -> bool:
    """Word-ish boundary match; plain 'in' makes 'go' match 'algorithm'."""
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def analyse(job: dict, resume: dict) -> Tailored:
    jd = (job.get("description") or "").lower()
    result = Tailored(job=job)
    if not jd:
        return result

    resume_blob = " ".join([
        resume.get("summary_base", ""),
        *[b["text"] for role in resume["experience"] for b in role["bullets"]],
        *[t for role in resume["experience"] for b in role["bullets"]
          for t in b.get("tags", [])],
        *[s for group in resume["skills"].values() for s in group],
    ]).lower()

    for term in CHECK_TERMS:
        if not _mentions(jd, term):
            continue
        (result.matched if _mentions(resume_blob, term) else result.gaps).append(term)

    # Rank his real bullets by how much of the JD's vocabulary they carry.
    scored: list[tuple[int, str, str, str]] = []
    for role in resume["experience"]:
        for bullet in role["bullets"]:
            haystack = (bullet["text"] + " " +
                        " ".join(bullet.get("tags", []))).lower()
            hits = sum(1 for term in result.matched if _mentions(haystack, term))
            # Tag hits count double: they are the curated signal.
            hits += sum(1 for tag in bullet.get("tags", []) if _mentions(jd, tag))
            scored.append((hits, role["company"], role["title"], bullet["text"]))

    scored.sort(key=lambda item: -item[0])
    result.bullets = [(c, t, b) for hits, c, t, b in scored if hits > 0][:12]

    # Put the skill groups the JD actually talks about first.
    group_hits = []
    for name, items in resume["skills"].items():
        hits = sum(1 for item in items if _mentions(jd, item.lower()))
        group_hits.append((hits, name))
    group_hits.sort(key=lambda item: -item[0])
    result.skill_order = [name for hits, name in group_hits if hits > 0]

    return result


def render_markdown(t: Tailored, resume: dict, profile: dict) -> str:
    job = t.job
    ident = profile.get("identity", {})
    name = ident.get("name", "")
    contact = " · ".join(filter(None, [
        ident.get("email"), ident.get("phone"), ident.get("base_location"),
    ]))

    lines = [
        f"# {name}", f"{contact}", "",
        f"**Tailored for:** {job['title']} — {job['company']}  ",
        f"**Posting:** {job['url']}  ",
        f"**Match score:** {job['score']:.0f}",
        "", "---", "",
        "## Summary", "", resume["summary_base"].strip(), "",
    ]

    if t.matched:
        lines += [
            "> Emphasize in the summary line: "
            + ", ".join(t.matched[:8]) + ".", "",
        ]

    lines += ["## Experience", ""]
    if t.bullets:
        # Group by role and keep roles in reverse-chronological order. Sorting
        # bullets purely by relevance and emitting a header on every change
        # repeats the same employer several times down the page.
        chosen: dict[str, list[str]] = {}
        for company, _title, text in t.bullets:
            chosen.setdefault(company, []).append(text)

        for role in resume["experience"]:
            picked = chosen.get(role["company"])
            if not picked:
                continue
            span = f"{role['start']} – {role.get('end') or 'Present'}"
            lines += [
                f"### {role['title']} — {role['company']}",
                f"_{role['location']} · {span}_",
                "",
                *[f"- {text.strip()}" for text in picked],
                "",
            ]
        lines += [
            f"_Bullets above are the {len(t.bullets)} of "
            f"{sum(len(r['bullets']) for r in resume['experience'])} that "
            "overlap this posting, ordered by relevance within each role._",
            "",
        ]
    else:
        lines += ["_No description captured for this posting — "
                  "bullet ranking skipped._", ""]

    if t.skill_order:
        lines += ["## Skills — lead with these groups", ""]
        for group in t.skill_order[:5]:
            items = ", ".join(resume["skills"][group])
            lines += [f"**{group}:** {items}", ""]

    lines += ["## Gap check", ""]
    if t.gaps:
        lines += [
            "The posting asks for these and the résumé never mentions them:",
            "",
            *[f"- **{g}**" for g in t.gaps],
            "",
            "_Decide per item: real gap, wording mismatch, or a reason to skip._",
            "",
        ]
    else:
        lines += ["Nothing the posting asks for is missing from the résumé.", ""]

    lines += ["## Education", ""]
    for school in resume["education"]:
        lines += [f"- **{school['school']}** — {school['degree']}, "
                  f"{school['location']} ({school['ended']})"]
    lines += ["", "## Certifications", ""]
    lines += [f"- {c}" for c in resume["certifications"]]
    return "\n".join(lines) + "\n"


def render_cover_letter(t: Tailored, resume: dict, profile: dict) -> str:
    job = t.job
    ident = profile.get("identity", {})
    top = [text for _, _, text in t.bullets[:3]]
    highlights = "\n".join(f"- {b.strip()}" for b in top) if top else ""
    focus = ", ".join(t.matched[:5]) if t.matched else "AI/ML engineering"

    return f"""{ident.get('name', '')}
{ident.get('email', '')} · {ident.get('phone', '')}
{date.today().strftime('%B %d, %Y')}

Re: {job['title']} — {job['company']}

Hello,

I'm applying for the {job['title']} role. I'm an AI/ML engineer with five
years building agentic and GenAI systems that run in production, and the
overlap with what this role calls for — {focus} — is close to what I do daily.

Most relevant:

{highlights}

At Akoncagua AI I lead fine-tuning across CPT and SFT stages and own the
document-intelligence pipelines feeding LLM pretraining; before that, at
ServiceNow, I built LangChain agent workflows that raised self-service ticket
resolution by 35%. I care about the unglamorous half of this work — evaluation
harnesses, drift monitoring, and keeping inference costs sane.

I'd welcome the chance to talk about {job['company']}'s work here.

Thanks for your time,
{ident.get('name', '')}

---
DRAFT — read it before sending. Replace the closing paragraph with something
specific to {job['company']}: a product, a paper, a system they've written
about. A letter that could be sent to any company reads like one that was.
"""


def render_answers(profile: dict) -> str:
    """The ATS questions every application asks, answered once."""
    ident = profile.get("identity", {})
    auth = profile.get("work_authorization", {})
    needs_now = auth.get("requires_sponsorship_now")
    needs_later = auth.get("requires_sponsorship_future")

    return f"""# Application answer pack

Copy-paste for ATS forms. Keep this file current; it is the single source of
truth so answers never contradict each other across applications.

## Identity

| Field | Value |
|---|---|
| Full name | {ident.get('name', '')} |
| Email | {ident.get('email', '')} |
| Phone | {ident.get('phone', '')} |
| Location | {ident.get('base_location', '')} |
| Willing to relocate | {'Yes' if ident.get('open_to_relocate') else 'No'} |
| LinkedIn | {ident.get('linkedin') or '(add to config/identity.yml)'} |
| GitHub | {ident.get('github') or '(add to config/identity.yml)'} |

## Work authorization — the questions that actually gate you

**"Are you legally authorized to work in the United States?"**
> Yes.

**"Will you now or in the future require sponsorship for employment visa
status (e.g. H-1B)?"**
> {'Yes.' if needs_later else 'No.'}

This is the one people get wrong. Answering "No" because you can work today
is inaccurate — the question asks about the future, and a mismatch discovered
later is far more damaging than an honest Yes. Current status:
{auth.get('status', 'unknown')}, work authorization valid through
{auth.get('ead_valid_through', 'unknown')}.

**"Do you currently require sponsorship?"** (a different question)
> {'Yes.' if needs_now else 'No — I hold valid work authorization and can start immediately.'}

**If there is a free-text box, this is the framing to use:**
> I'm authorized to work in the US on STEM OPT through February 2028 and can
> start immediately with no sponsorship required today. I will need H-1B
> sponsorship before that authorization ends.

**Security clearance**
> {'Eligible.' if auth.get('clearance_eligible') else 'Not eligible — I am not a US citizen. Skip roles requiring clearance or ITAR access.'}

## Standard fields

| Question | Answer |
|---|---|
| Notice period | Two weeks |
| Earliest start | Two weeks from offer |
| Have you worked here before? | No |
| Referred by anyone? | (fill per application) |
| Non-compete restrictions? | No |

## Compensation

Give a range, not a number, and only when the field is required. Anchor it to
the posting's own band when one is published.
> Base target: $ ___ – $ ___ , flexible on the mix of base, bonus and equity
> for the right role.

## Voluntary self-identification (EEO)

These are optional, cannot lawfully be used against you, and are usually
reported in aggregate. "I don't wish to answer" is always a valid choice.

| Field | Suggested |
|---|---|
| Gender | your choice |
| Race / ethnicity | your choice |
| Veteran status | I am not a protected veteran |
| Disability | your choice |

## References

Do not list references on the résumé. Supply them when asked, late in the
process, after telling each person the role and company.
"""


def find(conn: sqlite3.Connection, needle: str) -> list[dict]:
    """Look a posting up by uid prefix, URL, or words from company/title.

    Copying a 16-char hex uid off a dashboard is a poor way to start an
    application, so `tailor` accepts whatever is easiest to grab.
    """
    row = conn.execute(
        "SELECT * FROM jobs WHERE uid = ? OR uid LIKE ?", (needle, needle + "%")
    ).fetchone()
    if row:
        return [dict(row)]

    if needle.startswith("http"):
        rows = conn.execute("SELECT * FROM jobs WHERE url = ?", (needle,)).fetchall()
        if rows:
            return [dict(r) for r in rows]

    # Every word must appear somewhere in company + title.
    words = [w for w in re.split(r"\s+", needle.strip()) if w]
    if not words:
        return []
    clause = " AND ".join(["(company || ' ' || title) LIKE ?"] * len(words))
    rows = conn.execute(
        f"""SELECT * FROM jobs WHERE {clause} AND closed_at IS NULL
            ORDER BY score DESC LIMIT 10""",
        [f"%{w}%" for w in words],
    ).fetchall()
    return [dict(r) for r in rows]


def build(conn: sqlite3.Connection, uid: str, out_root: Path) -> Path:
    matches = find(conn, uid)
    if not matches:
        raise KeyError(f"nothing matched {uid!r}")
    if len(matches) > 1:
        lines = "\n".join(
            f"  {m['uid'][:8]}  [{m['score']:>3.0f}]  {m['company']} — {m['title'][:52]}"
            for m in matches
        )
        raise KeyError(
            f"{len(matches)} postings matched {uid!r} — be more specific "
            f"or use a uid:\n{lines}"
        )
    job = matches[0]

    resume = load_resume()
    profile = load_profile()
    analysis = analyse(job, resume)

    slug = re.sub(r"[^a-z0-9]+", "-",
                  f"{job['company']} {job['title']}".lower()).strip("-")[:70]
    out = out_root / slug
    out.mkdir(parents=True, exist_ok=True)

    (out / "resume.md").write_text(render_markdown(analysis, resume, profile))

    # The .docx is the file that actually gets uploaded; the .md is the
    # working notes (gap check, what to emphasise) that never leave the machine.
    from . import docx_out
    docx_out.render(analysis, resume, profile, out / "resume.docx")

    (out / "cover-letter.md").write_text(
        render_cover_letter(analysis, resume, profile))
    (out / "answers.md").write_text(render_answers(profile))
    (out / "posting.md").write_text(
        f"# {job['title']} — {job['company']}\n\n"
        f"{job['location']}\n\n{job['url']}\n\n---\n\n"
        f"{job.get('description') or '(no description captured)'}\n"
    )
    return out
