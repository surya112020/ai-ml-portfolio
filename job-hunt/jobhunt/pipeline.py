"""The poll loop: fetch -> store -> prescore -> hydrate -> score.

Hydration is the expensive part (one HTTP request per posting on Workday,
SmartRecruiters and Oracle), so it only runs for postings whose title and
location already look right. Everything else is judged on the list payload.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import settings, sources, store
from .enrich import h1b
from .models import Job
from .scoring import load_profile, prescore, score

log = logging.getLogger(__name__)

COMPANIES_PATH = Path(__file__).resolve().parent.parent / "config" / "companies.yml"


@dataclass
class PollResult:
    fetched: int
    new: list[Job]
    hydrated: int
    closed: int
    errors: list[str]
    per_source: dict[str, int]


def load_companies(path: Path | str = COMPANIES_PATH) -> list[dict]:
    with open(path) as handle:
        return yaml.safe_load(handle) or []


def _label(entry: dict) -> str:
    return f"{entry['source']}:{entry.get('company', entry.get('slug', '?'))}"


def poll(conn: sqlite3.Connection, entries: list[dict] | None = None,
         workers: int = 8, hydrate_workers: int = 6,
         hydrate_cap: int = 400) -> PollResult:
    entries = entries if entries is not None else load_companies()

    # Sources marked ci_skip are pointless on a hosted runner — LinkedIn and
    # Indeed block datacenter IPs, so the scrape fails after burning minutes.
    # Dropping them keeps the hourly job inside the free Actions allowance.
    if settings.in_ci():
        skipped = [e for e in entries if e.get("ci_skip")]
        if skipped:
            entries = [e for e in entries if not e.get("ci_skip")]
            log.info("CI: skipping %d source(s) marked ci_skip", len(skipped))

    profile = load_profile()
    run_id = store.start_run(conn)

    all_jobs: list[Job] = []
    errors: list[str] = []
    per_source: dict[str, int] = {}
    # (source, company) pairs that returned data — the only boards eligible
    # to have missing postings marked closed.
    healthy_boards: set[tuple[str, str]] = set()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(sources.fetch, e): e for e in entries}
        for future in as_completed(futures):
            entry = futures[future]
            label = _label(entry)
            try:
                found = future.result()
            except Exception as exc:  # noqa: BLE001 - one board must not kill the run
                msg = f"{label}: {type(exc).__name__}: {exc}"
                errors.append(msg)
                log.warning(msg)
                store.record_health(conn, label, None, str(exc))
                continue
            per_source[label] = len(found)
            all_jobs.extend(found)
            healthy_boards.update((j.source, j.company) for j in found)
            store.record_health(conn, label, len(found), None)
            log.info("%-34s %4d", label, len(found))

    fresh = store.upsert(conn, all_jobs)

    # Only spend requests on postings that already look like a fit.
    floor = profile["thresholds"]["ignore_below"]
    needs_jd = [
        job for job in all_jobs
        if not job.description and not prescore(job, profile).blocked
        and prescore(job, profile).score >= floor
    ][:hydrate_cap]

    hydrated = 0
    if needs_jd:
        with ThreadPoolExecutor(max_workers=hydrate_workers) as pool:
            futures = {pool.submit(sources.hydrate, j): j for j in needs_jd}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    text = future.result()
                except Exception:  # noqa: BLE001
                    continue
                if text and text != job.description:
                    job.description = text
                    job.hydrated = True
                    store.save_description(conn, job.uid, text)
                    hydrated += 1
        conn.commit()

    h1b_config = profile.get("h1b") or {}
    rows = []
    for job in all_jobs:
        verdict = score(job, profile)
        approvals = 0
        if not verdict.blocked and verdict.score > 0:
            bonus, note = h1b.bonus_for(job.company, h1b_config)
            if note:
                verdict.score = max(0.0, min(100.0, verdict.score + bonus))
                verdict.reasons.append(note)
                approvals = h1b.approvals_for(
                    job.company, int(h1b_config.get("fiscal_year", 2023))
                )[0]
        rows.append((verdict.score, json.dumps(verdict.reasons),
                     json.dumps(verdict.blockers), approvals, job.uid))
    conn.executemany(
        "UPDATE jobs SET score=?, score_reasons=?, blockers=?, h1b_approvals=? "
        "WHERE uid=?", rows
    )
    conn.commit()

    closed = store.mark_closed(conn, {j.uid for j in all_jobs}, healthy_boards)
    store.finish_run(conn, run_id, len(all_jobs), len(fresh), errors)

    return PollResult(len(all_jobs), fresh, hydrated, closed, errors, per_source)


def drop_reason(row: dict, profile: dict | None = None) -> str:
    """Why a posting isn't on the shortlist — '' means it is."""
    from .scoring import excluded, is_us, title_tier

    profile = profile or load_profile()
    hit = excluded(row["title"] or "", profile)
    if hit:
        return f"excluded: {hit}"
    tier, _ = title_tier(row["title"] or "", profile)
    if tier == 0:
        return "not a target role"
    if profile["locations"].get("require_us") and not is_us(row["location"] or ""):
        return "outside the US"
    blockers = row.get("blockers")
    if blockers and blockers != "[]":
        try:
            first = json.loads(blockers)[0]
        except (json.JSONDecodeError, IndexError):
            first = "blocked"
        return first
    return ""


def all_rows(conn: sqlite3.Connection, include_closed: bool = False) -> list[dict]:
    """Every posting we hold, with its drop reason. Nothing filtered out.

    This is the safety net: the shortlist is a ranking decision, and a
    ranking decision can be wrong. This view lets you check what it skipped.
    """
    profile = load_profile()
    where = "" if include_closed else "WHERE closed_at IS NULL"
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM jobs {where} ORDER BY score DESC, company, title"
    )]
    for row in rows:
        row["reason"] = drop_reason(row, profile)
    return rows


def shortlist(conn: sqlite3.Connection, limit: int = 50, min_score: float = 45,
              only_new: bool = False, include_blocked: bool = False) -> list[dict]:
    """Ranked, de-duplicated openings worth his time."""
    clauses = ["closed_at IS NULL", "score >= ?"]
    params: list[object] = [min_score]
    if not include_blocked:
        clauses.append("(blockers IS NULL OR blockers = '[]')")
    if only_new:
        clauses.append("status = 'new'")

    rows = conn.execute(
        f"""SELECT * FROM jobs WHERE {' AND '.join(clauses)}
            ORDER BY score DESC, first_seen DESC""",
        params,
    ).fetchall()

    # Collapse the same role posted across many locations into one row.
    best: dict[str, dict] = {}
    for row in rows:
        record = dict(row)
        key = record["dedupe_key"] or record["uid"]
        if key not in best:
            record["duplicate_count"] = 1
            best[key] = record
        else:
            best[key]["duplicate_count"] += 1
    ranked = sorted(best.values(), key=lambda r: (-r["score"], r["company"]))
    return ranked[:limit]
