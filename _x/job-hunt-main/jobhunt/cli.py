"""Command line entry point.

    python -m jobhunt poll                 fetch every source, score, store
    python -m jobhunt list --min 60        ranked openings
    python -m jobhunt dashboard --open     write + open the HTML board
    python -m jobhunt health               per-source status from last run
    python -m jobhunt show <uid>           one posting in full
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import webbrowser
from pathlib import Path

from . import dashboard, notify, pipeline, settings, state, store, tracker

ROOT = Path(__file__).resolve().parent.parent


def _fmt_age(first_seen: str) -> str:
    from datetime import datetime, timezone
    try:
        seen = datetime.fromisoformat(first_seen)
    except ValueError:
        return "?"
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    hours = (datetime.now(tz=timezone.utc) - seen).total_seconds() / 3600
    if hours < 1:
        return f"{int(hours * 60)}m"
    if hours < 48:
        return f"{int(hours)}h"
    return f"{int(hours / 24)}d"


def cmd_poll(args: argparse.Namespace) -> int:
    conn = store.connect()
    entries = pipeline.load_companies()
    if args.only:
        wanted = {s.lower() for s in args.only.split(",")}
        entries = [
            e for e in entries
            if e["source"].lower() in wanted
            or e.get("company", "").lower() in wanted
        ]
        if not entries:
            print(f"no sources matched {args.only!r}")
            return 1

    # A machine with no prior state would treat all ~11k postings as new.
    first_run = not state.STATE_PATH.exists()

    result = pipeline.poll(conn, entries, hydrate_cap=args.hydrate_cap)
    restored = state.import_state(conn)

    print(f"\nfetched {result.fetched} postings from {len(entries)} boards")
    print(f"  new         {len(result.new)}")
    print(f"  hydrated    {result.hydrated}")
    print(f"  closed      {result.closed}")
    if restored:
        print(f"  restored    {restored} from saved state")
    if result.errors:
        print(f"  errors      {len(result.errors)}")
        for err in result.errors:
            print(f"    ! {err}")

    if args.notify:
        sent = notify.instant(conn, result.new, suppress=first_run)
        if first_run:
            print("  alerts      suppressed (first run — no prior state)")
        else:
            print(f"  alerted     {sent}")

    saved = state.export_state(conn)
    print(f"  state       {saved} postings saved")

    top = pipeline.shortlist(conn, limit=args.top, min_score=args.min_score)
    if top:
        print(f"\ntop {len(top)} matches:")
        _print_table(top)
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    conn = store.connect()
    if not settings.telegram_configured():
        print("telegram not configured — run tools/telegram_setup.py first")
    sent = notify.digest(conn, hours=args.hours, limit=args.limit)
    print(f"digest sent: {sent} openings from the last {args.hours}h")
    return 0


def cmd_test_alert(args: argparse.Namespace) -> int:
    conn = store.connect()
    rows = pipeline.shortlist(conn, limit=3, min_score=0)
    if not rows:
        print("no postings in the db — run `poll` first")
        return 1
    from .notify import telegram as tg
    body = "\n\n".join(tg.format_job(r, i) for i, r in enumerate(rows, 1))
    ok = tg.send(f"🔔 <b>jobhunt test alert</b>\n\n{body}")
    from .notify import macos
    mac_ok = macos.send("jobhunt test", f"{len(rows)} sample openings",
                        rows[0]["title"], url=rows[0]["url"])
    print("telegram:", "sent" if ok else "FAILED (check .env)")
    print(f"macos   : {'sent' if mac_ok else 'FAILED'} via {macos.backend()}")
    if "osascript" in macos.backend():
        print("          if no banner appears, its alert style is set to None:")
        print("          brew install terminal-notifier   (recommended), or")
        print("          open -a 'Script Editor' then set it to Banners in Settings")
    return 0 if ok else 1


def cmd_list(args: argparse.Namespace) -> int:
    conn = store.connect()
    rows = pipeline.shortlist(
        conn, limit=args.limit, min_score=args.min_score,
        only_new=args.new, include_blocked=args.blocked,
    )
    if not rows:
        print("nothing matched — try --min lower, or run `poll` first")
        return 0
    _print_table(rows, show_url=args.urls)
    print(f"\n{len(rows)} openings")
    return 0


def _print_table(rows: list[dict], show_url: bool = False) -> None:
    print(f"{'score':>5}  {'age':>4}  {'company':<16} {'title':<52} location")
    print("-" * 118)
    for row in rows:
        dupes = row.get("duplicate_count", 1)
        title = row["title"][:50] + ("…" if len(row["title"]) > 50 else "")
        if dupes > 1:
            title = f"{title} (+{dupes - 1})"
        loc = (row["location"] or "")[:30]
        print(f"{row['score']:>5.0f}  {_fmt_age(row['first_seen']):>4}  "
              f"{row['company'][:16]:<16} {title:<52} {loc}")
        if show_url:
            print(f"       {row['url']}")


def cmd_dashboard(args: argparse.Namespace) -> int:
    conn = store.connect()
    path = dashboard.render(conn, ROOT / "data" / "dashboard.html",
                            min_score=args.min_score)
    print(f"wrote {path}")
    if args.open:
        webbrowser.open(path.as_uri())
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """CSV of the shortlist — for tracking applications in a spreadsheet."""
    import csv

    conn = store.connect()
    rows = pipeline.shortlist(conn, limit=args.limit, min_score=args.min_score)
    path = ROOT / "data" / "openings.csv"
    path.parent.mkdir(parents=True, exist_ok=True)

    columns = ["score", "company", "title", "location", "bucket", "url",
               "first_seen", "posted_at", "locations_count", "status",
               "applied?", "notes"]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([
                f"{row['score']:.0f}", row["company"], row["title"],
                row["location"], row["bucket"], row["url"],
                (row["first_seen"] or "")[:16], (row["posted_at"] or "")[:10],
                row.get("duplicate_count", 1), row["status"], "", "",
            ])
    print(f"wrote {path}  ({len(rows)} openings)")
    return 0


def cmd_excel(args: argparse.Namespace) -> int:
    from . import excel

    conn = store.connect()
    path = excel.render(conn, ROOT / "data" / "openings.xlsx",
                        min_score=args.min_score)
    short = len(pipeline.shortlist(conn, limit=5000, min_score=args.min_score))
    total = len(pipeline.all_rows(conn))
    print(f"wrote {path}")
    print(f"  Shortlist    {short:,} rows (score {args.min_score:.0f}+)")
    print(f"  All postings {total:,} rows (nothing filtered)")
    if args.open:
        subprocess.call(["open", str(path)])
    return 0


def cmd_tailor(args: argparse.Namespace) -> int:
    from .apply import tailor

    conn = store.connect()
    try:
        out = tailor.build(conn, args.uid, ROOT / "out")
    except (KeyError, FileNotFoundError) as exc:
        # str(KeyError) reprs its argument, which escapes the newlines in the
        # multi-match list into a single unreadable line.
        print(exc.args[0] if exc.args else exc)
        return 1
    print(f"wrote {out}")
    for name in sorted(p.name for p in out.iterdir()):
        print(f"  {name}")
    if args.open:
        subprocess.call(["open", str(out)])
    return 0


def cmd_answers(args: argparse.Namespace) -> int:
    from .apply import tailor

    from .scoring import load_profile
    path = ROOT / "out" / "answers.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tailor.render_answers(load_profile()))
    print(f"wrote {path}")
    return 0


def cmd_applied(args: argparse.Namespace) -> int:
    """Mark a posting applied so it stops competing for attention."""
    from datetime import datetime, timezone

    from .apply import tailor

    conn = store.connect()
    matches = tailor.find(conn, args.query)
    if not matches:
        print(f"nothing matched {args.query!r}")
        return 1
    if len(matches) > 1 and not args.all:
        print(f"{len(matches)} postings matched — narrow it, or pass --all:")
        for m in matches:
            print(f"  {m['uid'][:8]}  [{m['score']:>3.0f}]  {m['company']} — "
                  f"{m['title'][:52]}")
        return 1

    stamp = datetime.now(tz=timezone.utc).isoformat()
    status = "skipped" if args.skip else "applied"
    conn.executemany(
        "UPDATE jobs SET status=?, applied_at=?, notes=? WHERE uid=?",
        [(status, stamp, args.note or "", m["uid"]) for m in matches],
    )
    conn.commit()
    from . import state
    state.export_state(conn)

    print(f"marked {len(matches)} posting(s) {status}:")
    for m in matches:
        print(f"  {m['company']} — {m['title'][:60]}")
    return 0


def cmd_applications(args: argparse.Namespace) -> int:
    conn = store.connect()
    rows = conn.execute(
        """SELECT company, title, score, applied_at, status, notes, url
           FROM jobs WHERE status IN ('applied','skipped')
           ORDER BY applied_at DESC"""
    ).fetchall()
    if not rows:
        print("no applications tracked yet — mark one with:\n"
              "  python -m jobhunt applied \"adobe machine learning\"")
        return 0
    print(f"{'when':<12}{'status':<9}{'score':>5}  {'company':<14} title")
    print("-" * 96)
    for r in rows:
        print(f"{(r['applied_at'] or '')[:10]:<12}{r['status']:<9}"
              f"{r['score']:>5.0f}  {r['company'][:14]:<14} {r['title'][:44]}")
    applied = sum(1 for r in rows if r["status"] == "applied")
    print(f"\n{applied} applied, {len(rows) - applied} skipped")
    return 0


def cmd_site(args: argparse.Namespace) -> int:
    from . import site

    conn = store.connect()
    out = site.build(conn)
    print(f"wrote {out}")
    for path in sorted(out.rglob("*")):
        if path.is_file():
            rel = path.relative_to(out)
            print(f"  {str(rel):<22} {path.stat().st_size / 1024:>7.0f} KB")
    if args.open:
        subprocess.call(["open", str(out / "public" / "index.html")])
    return 0


def cmd_tracker(args: argparse.Namespace) -> int:
    conn = store.connect()
    result = tracker.update(conn, min_score=args.min_score)
    print(f"wrote {result['path']}")
    print(f"  rows           {result['total']:,}")
    print(f"  new this run   {result['added']:,}")
    print(f"  kept from file {result['kept']:,}")
    if result["synced"]:
        print(f"  marks imported {result['synced']} "
              "(Applied/Skipped pulled back into the database)")
    state.export_state(conn)
    if args.open:
        subprocess.call(["open", str(result["path"])])
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """What to run when you sit down: get the cloud's state, poll, update Excel.

    The tracker reads the local database, and CI's runs only update the hosted
    board — so without this the spreadsheet silently falls behind.
    """
    print("1/3  pulling state from GitHub…")
    # --autostash: a dirty working tree must not stop the sync.
    subprocess.call(["git", "-C", str(ROOT), "pull", "--rebase",
                     "--autostash", "-q"])

    print("2/3  polling all boards…")
    conn = store.connect()
    result = pipeline.poll(conn, pipeline.load_companies())
    state.import_state(conn)
    print(f"     {result.fetched:,} postings, {len(result.new)} new to this machine")

    print("3/3  updating the tracker…")
    stats = tracker.update(conn)
    state.export_state(conn)
    print(f"     {stats['total']:,} rows  ·  {stats['added']} added  "
          f"·  {stats['synced']} of your marks pushed to the database")
    print(f"\n{stats['path']}")
    if args.open:
        subprocess.call(["open", str(stats["path"])])
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    conn = store.connect()
    rows = conn.execute(
        "SELECT * FROM source_health ORDER BY fail_streak DESC, name"
    ).fetchall()
    if not rows:
        print("no runs yet")
        return 0
    print(f"{'source':<36} {'jobs':>6}  status")
    print("-" * 80)
    for row in rows:
        if row["fail_streak"]:
            status = f"FAIL x{row['fail_streak']}: {(row['last_error'] or '')[:40]}"
        else:
            status = f"ok ({row['last_ok'][:16]})"
        print(f"{row['name']:<36} {row['last_count'] or 0:>6}  {status}")

    run = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if run:
        print(f"\nlast run: {run['seen']} seen, {run['new']} new, "
              f"started {run['started_at'][:19]}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    conn = store.connect()
    row = conn.execute(
        "SELECT * FROM jobs WHERE uid=? OR uid LIKE ?", (args.uid, args.uid + "%")
    ).fetchone()
    if not row:
        print(f"no posting with uid {args.uid!r}")
        return 1
    print(f"{row['title']} — {row['company']}")
    print(f"{row['location']}   score {row['score']:.0f}   {row['url']}\n")
    for reason in json.loads(row["score_reasons"] or "[]"):
        print(f"  + {reason}")
    for blocker in json.loads(row["blockers"] or "[]"):
        print(f"  ! {blocker}")
    print("\n" + (row["description"] or "(no description)")[:4000])
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    script = ROOT / "tools" / "probe_sources.py"
    cmd = [sys.executable, str(script)] + ([args.family] if args.family else [])
    return subprocess.call(cmd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobhunt")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("poll", help="fetch all sources and score")
    p.add_argument("--only", help="comma-separated source or company filter")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--min-score", dest="min_score", type=float, default=55)
    p.add_argument("--hydrate-cap", dest="hydrate_cap", type=int, default=400)
    p.add_argument("--notify", action="store_true",
                   help="push instant alerts for new high-score postings")
    p.set_defaults(func=cmd_poll)

    p = sub.add_parser("digest", help="send the ranked morning digest")
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_digest)

    p = sub.add_parser("test-alert", help="verify Telegram + macOS wiring")
    p.set_defaults(func=cmd_test_alert)

    p = sub.add_parser("list", help="ranked openings already in the db")
    p.add_argument("--limit", type=int, default=60)
    p.add_argument("--min", dest="min_score", type=float, default=45)
    p.add_argument("--new", action="store_true", help="only unseen postings")
    p.add_argument("--blocked", action="store_true", help="include blocked ones")
    p.add_argument("--urls", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("dashboard", help="render the HTML board")
    p.add_argument("--min", dest="min_score", type=float, default=45)
    p.add_argument("--open", action="store_true")
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("export", help="CSV of the shortlist for tracking")
    p.add_argument("--min", dest="min_score", type=float, default=55)
    p.add_argument("--limit", type=int, default=1000)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("excel", help="xlsx: shortlist sheet + unfiltered sheet")
    p.add_argument("--min", dest="min_score", type=float, default=55)
    p.add_argument("--open", action="store_true")
    p.set_defaults(func=cmd_excel)

    p = sub.add_parser("tailor", help="application material for one posting")
    p.add_argument("uid", help="posting uid (prefix is enough)")
    p.add_argument("--open", action="store_true")
    p.set_defaults(func=cmd_tailor)

    p = sub.add_parser("answers", help="the ATS answer pack on its own")
    p.set_defaults(func=cmd_answers)

    p = sub.add_parser("applied", help="mark a posting applied (or skipped)")
    p.add_argument("query", help="uid, URL, or words from company/title")
    p.add_argument("--all", action="store_true",
                   help="mark every match, not just a unique one")
    p.add_argument("--skip", action="store_true", help="mark skipped instead")
    p.add_argument("--note", help="free-text note")
    p.set_defaults(func=cmd_applied)

    p = sub.add_parser("applications", help="what you've applied to")
    p.set_defaults(func=cmd_applications)

    p = sub.add_parser("site", help="build the static site for Cloudflare Pages")
    p.add_argument("--open", action="store_true")
    p.set_defaults(func=cmd_site)

    p = sub.add_parser("tracker", help="update the long-lived Excel tracker")
    # 0 = everything that cleared the title filter, matching the board. A
    # higher floor hides rows without saying so.
    p.add_argument("--min", dest="min_score", type=float, default=0)
    p.add_argument("--open", action="store_true")
    p.set_defaults(func=cmd_tracker)

    p = sub.add_parser("sync", help="pull, poll, refresh tracker — one command")
    p.add_argument("--open", action="store_true", help="open the tracker after")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("health", help="per-source status")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("show", help="one posting in full")
    p.add_argument("uid")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("probe", help="re-verify endpoints")
    p.add_argument("family", nargs="?")
    p.set_defaults(func=cmd_probe)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)-7s %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
