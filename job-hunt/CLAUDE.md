# jobhunt — runbook

**This file is the source of truth for the project.** Status, decisions,
every file's purpose, bugs already fixed, and the waitlist all live here.
README.md is only a short public-facing intro. Keep this updated as work
lands — anything not written down here gets re-derived wrong later.

Last updated: 2026-08-12 (end of session 3)

---

## 0. How it works, end to end

```
  91 career-site APIs                  3x/day via GitHub Actions:
  Greenhouse · Ashby · Lever ·         08:00 digest, 12:00 + 18:00 poll (ET)
  Workday · SmartRecruiters ·
  Oracle · amazon.jobs ·               ~18.4k postings per sweep, ~2.5 min
  Indeed + LinkedIn (JobSpy)
          |
          v
  1  FETCH      one adapter per ATS, run in parallel
          |
  2  STORE      upsert into SQLite. Returns ONLY postings never seen
          |     before — that set is what drives alerts.
          v
  3  PRESCORE   title + location, cheap, over all 18k
          |     drops ~80%: wrong role, outside the US, excluded title
          v
  4  HYDRATE    fetch the full JD, but ONLY for survivors. Workday,
          |     SmartRecruiters and Oracle need one request per posting,
          |     so this is the expensive step and it is rationed.
          v
  5  SCORE      + skill overlap with the resume
          |     + H-1B filing history (USCIS)
          |     - PhD required, wants far more years than he has
          |     x sponsorship / clearance blockers -> hard reject
          v
  6  ALERT      new AND score >= 70  -> Telegram immediately
          |     everything >= 40     -> one 08:00 ET digest
          v
  7  PUBLISH    jobhunt-board-exf.pages.dev (deployed from CI each run)
          |     plus data/tracker.xlsx locally
          |
  8  STATE      first_seen + status -> data/state.json.gz, committed,
                so the next run knows what was already seen and alerted
```

Why the two-stage split at 3/4: scoring needs the job description, but
fetching 18k descriptions would be ~18k HTTP requests an hour. Prescoring on
the cheap list payload cuts that to a few hundred.

## 0.1 Daily routine

1. **Telegram pings** on a new 70+ posting, or the 8am digest for the 40+
   band. Tap through and read it.
2. Or open the board: **https://jobhunt-board-exf.pages.dev**. Default filter
   is score 55+; switch to **Any score** to see staffing-firm roles, which
   mostly land 40–55 under the current `staffing: +0` weight.
3. Apply on the company site, pasting from
   `application-kit/workday-work-history.md` (work history, credential IDs,
   work-authorization answers).
4. Mark it in **`data/tracker.xlsx`** — Status / Applied on / Notes. Those
   three columns are his and survive every rebuild.
5. When he sits down, one command does the lot — **close the tracker in Excel
   first**, an open workbook leaves a `~$` lock file:

   ```bash
   cd ~/jobhunt && ./.venv/bin/python -m jobhunt sync --open
   ```

   Pulls state from GitHub, polls all 91 boards, appends new roles to the
   tracker with the date they were found, pushes his Applied/Skipped marks
   into the database, and opens the file.

**Why `sync` exists:** the tracker reads the *local* database, while CI only
updates the hosted board. Without it the spreadsheet silently falls behind
and looks like nothing new is arriving.

One résumé is used for everything — per-job tailoring was tried and dropped
(see "Decided in session 2").

---

## 1. Who this is for

Vishnu Sai — AI/ML Engineer, ~5 yrs. AI Systems Engineer at Akoncagua AI
(Tampa, FL). Prior: ServiceNow, Neon IT Systems. MS Data Analytics,
Northeastern (Dec 2024). Strengths: LLM fine-tuning (CPT/SFT/LoRA/PEFT),
agentic systems (LangChain/LangGraph), RAG, document intelligence, MLOps.

**F-1 STEM OPT, EAD through Feb 2028.** Can work today without sponsorship,
needs H-1B before then → **March 2027 is the realistic cap season**. Cannot
hold a security clearance, so clearance/ITAR postings are hard rejects.

Priorities, in his words: full-time at big companies first; open to W2 with
staffing vendors (Kforce, Randstad, Insight Global); open to AI Platform
Engineer roles; sponsorship required eventually.

Works 8:30–5 weekdays. The system must find and rank openings unattended.

---

## 2. Status

### Done

| # | Item | Notes |
|---|---|---|
| 1 | Core pipeline | 91 boards + 3 aggregator feeds, ~18.4k postings, full sweep ~2.5 min |
| 2 | Ranked list + links | dashboard, Excel, CSV, terminal |
| 3 | All dead sources reached | direct APIs where possible, aggregators otherwise (§6) |
| 4 | Alerting code | Telegram + macOS + morning digest |
| 5 | Scheduling | Actions 3x/day — 08:00 digest, 12:00 + 18:00 **Eastern**. UTC crons 12/16/22; shift an hour earlier when EST returns in November. |
| 6 | H-1B sponsorship scoring | USCIS FY2023, 26,737 employers indexed |
| 7 | Scoring accuracy fix | shortlist 419 → 1,017; strong 44 → 189 |
| 8 | OSS evaluation | JobSpy adopted as the `aggregator` source |
| 9 | Telegram alerts | Live. Bot `@Vishnujobhunt_bot`, credentials in `.env`. |
| 10 | Actions secrets | Set. First bot state commit landed 2026-08-09 22:45 UTC. |
| 11 | ~~Artifact board~~ | Superseded by #14/#17. A one-off snapshot exists but does not refresh; use the Pages board. |
| 12 | Application answer pack | `out/*/answers.md` — the sponsorship/EEO/comp answers. Believed good; not challenged. |
| 13 | Application tracker | `jobhunt applied <id>` / `jobhunt applications`; status rides in `state.json.gz` and shows on the board. |
| 14 | Live dashboard | **https://jobhunt-board-exf.pages.dev** — rebuilt and deployed on every run. |
| 15 | Excel tracker | `jobhunt tracker` → `data/tracker.xlsx`. Append-only, preserves your edits, syncs Applied/Skipped back to the DB. |
| 16 | Cloudflare deploy | From CI via `wrangler pages deploy`, not Cloudflare's git integration (§6). |
| 17 | Board is private | Cloudflare Access, email one-time PIN. Verified: `/` and `/data.json` both 302 to the Access login; unauthenticated fetch returns no postings. |
| 18 | Freshness filter | Board has a First seen filter (6h/24h/3d/7d) and a "New in 24h" tile. `first_seen` kept to the minute in data.json. |
| 19 | `jobhunt sync` | One command: pull state, poll, refresh the tracker. |

### Refinement backlog — next working session

Vishnu's read at the end of session 1: the build is good, but preferences,
company coverage and similar need tuning before it's right. Nothing here is
known to be broken; it is calibration. **None of the below has been
validated by him** — these are assumptions the system currently runs on.

**Preferences / scoring — all assumed, none confirmed**
- Bucket weights (`profile.yml` → `weights.bucket`): bigtech +7, ailab +6,
  enterprise +4, staffing +0. Encodes "big companies first". ailab may be
  where he is strongest; raising it would reorder the whole board.
- Location weights: remote 30, Tampa 25, Florida 22, then hubs. Invented
  from "FL, open to relocate" — never checked against how he actually feels
  about moving.
- `exclude_titles` contains `manager`, dropping ~3,566 postings. A sample of
  25 was inspected and all were genuine people/program management roles —
  **that is a sample, not an audit**, and it rules out the management track
  entirely either way.
- Thresholds: instant alert 70, digest 40, ignore below 25. The 70 bar was
  chosen before the scoring fix moved the distribution, so it is stale.
- `max_reasonable_years` 9, over-qualified penalty -12. Guessed.
- Skill lists in `profile.yml` were lifted from the résumé PDF, not reviewed.

**Coverage**
- 91 direct boards is not "every US company". The aggregator layer is
  keyword-driven, so Microsoft/Google/Meta/Apple/Tesla and the staffing
  firms are covered for AI/ML roles, not exhaustively.
- Tesla has no Greenhouse/Ashby/Lever board and its own site 403s.
- Microsoft's direct API is decommissioned (cert is for *.azureedge.net).
- `tools/probe_sources.py` is the way to add more: probe first, add only
  what returns 200.
- Likely biggest blind spot: `no-target-title` is ~30% of all postings.
  Worth reading that bucket via `tools/audit_filter.py` before adding
  sources — coverage recovered there is cheaper than a new adapter.

**Also open**
- Résumé output rejected — see "Needs rework" above. Ask first.

### Decided in session 2

**One résumé, no per-job tailoring.** Vishnu rejected the generated résumé
output and does not want to edit it per application. Agreed: the ROI on
rewriting per posting is low. `jobhunt tailor` stays, but its value is the
**gap check** — a signal for *whether* to apply — not the résumé it emits.
Do not rebuild per-JD résumé generation unless he asks.

**The answer pack and `application-kit/` are the useful artefacts:**
`application-kit/workday-work-history.md` holds ready-to-paste work history
for all three roles plus the three credential IDs, and he confirmed Workday
work-history descriptions are worth filling in (recruiters filter on the
typed fields, not the attached PDF).

### Needs rework — start here next session

**Résumé tailoring (`jobhunt tailor`).** Built and working end to end, but
Vishnu reviewed the output and **was not happy with it**. The specific
objection was not captured before we stopped — **ask him what was wrong
before changing anything.** Guessing will waste the session.

What exists today:
- `jobhunt/apply/tailor.py` — selects and reorders his real bullets by JD
  overlap, writes `resume.md`, `cover-letter.md`, `answers.md`, `posting.md`
- `jobhunt/apply/docx_out.py` — uploadable `resume.docx`, verified ATS-safe
  (0 tables, 1 column, no page-header text, real List Bullet style)
- `config/resume.yml` — his résumé as structured data, bullets carry `tags`

Plausible directions, none confirmed:
- The Markdown résumé is working notes, not a document — maybe only the
  .docx should exist
- Bullet selection may be too aggressive (12 of 22) or the ordering wrong
- The cover letter is generic by construction; it may not be worth shipping
- Layout/typography of the .docx was never visually reviewed — no
  LibreOffice or pandoc on this machine, so it was only checked structurally
- He may want it to match the formatting of his existing PDF résumé

The answer pack (`answers.md`) is a separate artifact and was not the thing
he objected to as far as we know.

### Blocked on Vishnu

| Item | What's needed |
|---|---|
| **🔴 Rotate the Cloudflare token** | The API token was pasted into a chat transcript on 2026-08-11 and must be treated as compromised. Delete it at dash.cloudflare.com → API Tokens, create a new one (Pages = Edit, **no IP filter**), then `gh secret set CLOUDFLARE_API_TOKEN`. |
| launchd agent | Optional now that CI runs the aggregators. Only needed for polling more often than 3x/day. |

### Due / not started

| # | Item | Why it matters |
|---|---|---|
| 9 | Gmail SMTP notifications | Fallback channel to vishnug1820@gmail.com. Needs a Gmail **app password** in `.env` as `SMTP_USER`/`SMTP_PASS`, set by Vishnu — never hardcoded, never committed. |
| — | Application tracker | Mark applied/skipped from Telegram or the dashboard and persist it in `state.json.gz` (the schema already has `status`, `applied_at`, `notes`). |
| — | Cloudflare Pages setup | **Vishnu's step.** Pages → connect repo → production branch `site`, no build command, output `/`. Then Zero Trust → Access → self-hosted app on the `*.pages.dev` host → Allow policy on his email. Free tier: Pages unlimited, Access up to 50 users. **Until the Access policy exists the URL is public.** |

### Dropped

**macOS notifications.** Delivered but never shown: `osascript` banners are
attributed to Script Editor, whose alert style is None by default on Sequoia
(ncprefs flags 8206), and that app is absent from System Settings until
launched once. `terminal-notifier` support is in the code if it's ever wanted
— `brew install terminal-notifier` and it is picked up automatically. Not
worth more effort: Telegram is the channel that reaches him at work.

---

## 3. Waitlist — researched, not adopted

### OSS tools evaluated

| Tool | Verdict |
|---|---|
| **JobSpy** (`python-jobspy`) | **Adopted** as `jobhunt/sources/aggregator.py`. Only `indeed` and `linkedin` scrapers work — `google` returns 0 rows, `zip_recruiter` 403s, `glassdoor` 400s. Returns full descriptions, so sponsorship blocking still applies. |
| JobFunnel | **Named from memory, never run.** Still unevaluated. |
| AIHawk / Jobs_Applier_AI_Agent | **Rejected on purpose.** Auto-submits applications; see §5. Not run. |
| [Feashliaa/job-board-aggregator](https://github.com/Feashliaa/job-board-aggregator) | Closest thing to this project found: 1M+ positions from 20k companies across Greenhouse/Lever/Ashby/Workday, Python ETL, daily GitHub Actions. Worth reading for its company lists — ours is 91 boards, theirs is 20k. Not run. |
| Apify ATS actors | Hosted/paid actors covering Greenhouse, Lever, Ashby, Workable, Recruitee, SmartRecruiters. Useful as a list of which ATS families are worth adapters; not worth paying for. |

**Honest note on this survey:** it was done at the *end* of session 1, after
the build. JobSpy was the only tool actually installed and run. Everything
else above is desk research. A proper survey before building might have
changed the design.

### ATS families not yet covered — concrete next step for coverage

| Family | Status |
|---|---|
| **Workable** | **Viable, URL shape proven.** `https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true` returned HTTP 200 for `deel`. Needs real company slugs — the ones guessed all missed. |
| **Recruitee** | Unproven. `https://{slug}.recruitee.com/api/offers/` 404'd on every slug tried; may need a real customer subdomain to confirm the shape. |
| Workable/Recruitee are the two families the comparable projects poll that we do not. Adding Workable is the cheapest coverage win available. |

### Claude skills/plugins considered

| Skill | Verdict |
|---|---|
| **Artifact** | **Superseded by Cloudflare Pages.** A published Artifact cannot refresh itself: its CSP blocks the same-origin fetch a live page needs, and the only runtime capabilities available on this account are `downloads` and `mcp` (with no connectors attached). It is a snapshot that only changes when a session republishes it. `jobhunt/artifact.py` still works if a one-off snapshot is ever wanted. |
| **docx** | **Still due.** `tailor` emits Markdown; many ATSs parse .docx better than PDF. |
| **pdf** | Lower priority — .docx covers the ATS case better. |
| **dataviz** | Maybe later — charts for application funnel / postings over time. |
| **xlsx** | Skipped. openpyxl already does this directly with less indirection. |
| pptx, others | Not relevant. |

### Ideas not yet scheduled

- Referral finder: match shortlisted companies against his LinkedIn network.
- Salary enrichment (levels.fyi / H-1B LCA wage data) to filter low offers.
- Re-check `no-target-title` drops periodically; it is the largest bucket
  (~30%) and the most likely place a real role hides.
- USCIS only publishes through FY2023 at a stable URL. Revisit for newer data.

---

## 4. What each file does

### Config

| File | Purpose |
|---|---|
| `config/profile.yml` | **All scoring config**: target titles, compositional matching, exclusions, skills, location weights, blocker regexes, weights, H-1B tiers, thresholds. Tune here, never in code. Contains no personal data — safe to commit. |
| `config/identity.yml` | **Gitignored.** Name, contact, visa status, clearance eligibility. |
| `config/identity.example.yml` | Template for the above. |
| `config/companies.yml` | Every board polled. Only add entries `tools/probe_sources.py` returns 200 for. Entries marked `ci_skip: true` are dropped on hosted runners. |
| `config/resume.yml` | **Gitignored.** Résumé bullets with `tags`; the tags drive per-job bullet selection. |

### Core

| File | Purpose |
|---|---|
| `jobhunt/models.py` | `Job` dataclass, stable `uid`, `dedupe_key` (collapses one role posted across many locations), date normalization, HTML stripping. |
| `jobhunt/store.py` | SQLite. Its critical job is `upsert` returning **only newly-seen** postings — that set drives alerts. Also `mark_closed`, health tracking, column migrations. |
| `jobhunt/scoring.py` | Two-stage scoring. `prescore` = title + location (cheap, all 18k). `score` = adds skills and blockers (needs the JD). |
| `jobhunt/pipeline.py` | The poll loop: fetch → store → prescore → hydrate → score → H-1B → close. Also `shortlist`, `all_rows`, `drop_reason`. |
| `jobhunt/http.py` | One shared `requests` session: retries, pacing, real UA. **All HTTP goes through here.** |
| `jobhunt/settings.py` | Env vars with `.env` fallback. Environment wins, so CI secrets override local. |
| `jobhunt/state.py` | Export/import of `first_seen` + application status as `data/state.json.gz`. This is what travels between laptop and CI. |
| `jobhunt/cli.py` | All commands (§7). |
| `jobhunt/dashboard.py` | Two-tab HTML: shortlist, and everything unfiltered with a status tag per row. |
| `jobhunt/excel.py` | Two-sheet xlsx, same split. |
| `jobhunt/artifact.py` | One-off snapshot render for a published Artifact. Superseded by site.py. |
| `jobhunt/site.py` | The live board: `index.html` shell (11 KB) + `data.json` row arrays (~900 KB, 162 KB gzipped). Split so committing it 3x/day doesn't bloat the repo. |
| `jobhunt/apply/tailor.py` | Per-posting résumé/cover-letter/answer-pack. Deterministic — selects and reorders his real bullets by JD overlap, never invents experience. |

### Sources — one adapter per ATS

| File | Covers | Descriptions |
|---|---|---|
| `sources/greenhouse.py` | ~45 boards incl. Anthropic, xAI, SpaceX, Scale AI | inline (`content=true`) |
| `sources/ashby.py` | ~25 boards incl. OpenAI, Cursor, LangChain | inline (`descriptionPlain`) |
| `sources/workday.py` | 11 tenants incl. NVIDIA, Salesforce, Adobe, Capital One | needs `hydrate` (1 req/posting) |
| `sources/amazon.py` | Amazon + AWS | inline |
| `sources/lever.py` | Palantir, Match Group | inline |
| `sources/smartrecruiters.py` | Visa | needs `hydrate` |
| `sources/oracle.py` | Oracle Fusion | needs `hydrate` |
| `sources/aggregator.py` | Indeed + LinkedIn via JobSpy — staffing firms, Microsoft, Google, Meta, Apple, Tesla | inline |

### Enrichment / tools

| File | Purpose |
|---|---|
| `jobhunt/enrich/h1b.py` | USCIS Employer Data Hub lookup → sponsorship score bonus. |
| `jobhunt/notify/telegram.py` | Telegram push, 4096-char chunking on line boundaries. |
| `jobhunt/notify/macos.py` | `osascript` banners. |
| `jobhunt/notify/__init__.py` | Dispatch: `instant` (new high-score) and `digest` (daily). Marks `notified` so nothing re-alerts. |
| `tools/probe_sources.py` | **Run before adding any company.** Verifies endpoints live. |
| `tools/audit_filter.py` | **Run after any scoring change.** Funnel + false-negative hunt. This is what caught the tier3 burial bug. |
| `tools/summary.py` | Quick counts and per-company breakdown. |
| `tools/telegram_setup.py` | Finds chat id, sends a test, writes `.env`. |
| `tools/local_poll.sh` + `com.jobhunt.poll.plist` | launchd agent, every 10 min while the Mac is awake. |
| `.github/workflows/poll.yml` | Hourly poll + alerts, commits state back. |
| `.github/workflows/digest.yml` | 11:00 UTC (07:00 ET) digest. |

### Generated (gitignored except state)

`data/jobs.db` · `data/state.json.gz` (committed) · `data/dashboard.html` ·
`data/openings.xlsx` · `data/openings.csv` · `data/h1b_2023.csv`

---

## 5. Design decisions — do not undo

**No auto-submitting applications.** Workday and Greenhouse bot-detect it,
and a killed Workday account is shared across every company on that tenant —
losing it costs Amazon *and* Microsoft *and* Salesforce at once. Amazon also
dedupes candidates across reqs, so blasting 40 listings hurts. The edge is
detection speed plus pre-filled material: ~3 min per application, not 20.

**Sponsorship blockers require an explicit negation.** "Will you now or in the
future require sponsorship" is the standard ATS *question* and appears on jobs
that sponsor happily. Substring-matching it discards most good employers.

**Scoring weights must not saturate.** An early set summed past the 100 cap and
pinned nine unrelated roles at exactly 100. Strong matches should land 70–88.

**Personal data never enters git.** `identity.yml` is gitignored; history was
rewritten once to remove it before the first push.

---

## 6. Fixed bugs — with the reason, so they don't come back

| Bug | Cause | Fix |
|---|---|---|
| 4,839 postings wrongly closed | `mark_closed` scoped by `source` (the ATS vendor), so polling one Greenhouse company closed every other Greenhouse company's postings | scope by `(source, company)` |
| Real roles buried below cutoff | tier1 needed an exact phrase, so "Engineer, Machine Learning" never matched; tier3 "software engineer" matched first | compositional matching (role noun + domain), runs **before** tier3 |
| Nine roles tied at exactly 100 | weights summed to ~148 pre-cap | retuned, moved into `profile.yml` |
| Oracle hydration 400 on every request | finder key is `Id="<id>"`, not `jobId=` | corrected URL |
| `UNIQUE constraint failed: jobs.uid` | multiple aggregator searches return the same posting; `existing` is a snapshot taken before any insert, so in-batch duplicates collided | dedupe within the batch |
| All aggregator rows tagged `staffing` | bucket taken from the config entry, not the row — gave Apple/Microsoft the staffing bucket's 0 weight | per-row bucketing |
| BlackRock showed 3 H-1B approvals | exact match returned early, hiding `BLACKROCK FINANCIAL MANAGEMENT` (91) | sum exact + prefix matches |
| Sierra → SIERRA CONSULTING, Harvey → HARVEY MUDD | single-token prefix matching is genuinely ambiguous | single-token queries are exact-match only |
| Every HTTP call failed with `CERTIFICATE_VERIFY_FAILED` | python.org Python 3.13 on macOS ships without root certs | everything goes through `requests`/`certifi`; never `urllib` |
| Staffing firms returned 0 rows | generic keyword searches surface product companies | company-targeted aggregator terms |
| Staffing firms absent from the hosted board | aggregators were `ci_skip: true` to protect free-tier minutes when polling hourly — but CI is what builds the board | ci_skip removed; at 3x/day the minutes aren't the constraint |
| Board said "3,174 shown (first 1,200 rendered)" | arbitrary render cap hid rows the filter said existed | raised to 6,000 |
| Header said 17,405 while table said 3,174 | two different counts conflated: every posting vs. those clearing the title filter | header leads with the AI/ML count, raw total in parentheses |
| Cleared spreadsheet cells stayed populated | `ws.cell(row, col, value=None)` does **not** clear a cell — openpyxl skips the assignment when value is None | assign `cell.value = None` instead |
| Dates showed a day ahead | `first_seen` is stored UTC; anything found after 8pm Eastern rendered as tomorrow (21:33 EDT on the 12th showed `2026-08-13`). Data correct, display wrong. | convert to local date for display |
| Tracker "Date added" identical on every row | it stamped the day the spreadsheet was built, not when the pipeline found the posting | use `first_seen` |
| Tracker never gained new jobs | it reads the local DB; CI only updates the hosted board | `jobhunt sync` |
| digest job 403 on the site-branch push | `digest.yml` had no `permissions: contents: write` (poll.yml did). The failure skipped the deploy, so the board went stale while poll + Telegram had both succeeded | add the permission; make the branch push non-fatal |
| Cloudflare deploys failed 5x | their git integration built `main` (ran `pip install -r requirements.txt`) and created a **Worker** running `npx wrangler deploy`, not a Pages project — the production-branch setting doesn't stop other branches building | deploy from CI with `wrangler pages deploy`; no git integration |

Also fixed outside the repo: `~` was a git repo with 10k staged files
including `.ssh/config` (removed, 1.6 GB reclaimed); `~/.ssh/config` had a
repo path in the `Port` field breaking all SSH; the machine's default SSH key
belongs to `vishnug-6712`, so pushing uses the `github-garneni` host alias.

---

## 7. Operating it

```bash
./.venv/bin/python -m jobhunt poll --notify        # fetch, score, alert
./.venv/bin/python -m jobhunt list --min 70 --urls
./.venv/bin/python -m jobhunt dashboard --open     # 2 tabs
./.venv/bin/python -m jobhunt excel --open         # 2 sheets
./.venv/bin/python -m jobhunt export               # CSV
./.venv/bin/python -m jobhunt digest               # morning summary
./.venv/bin/python -m jobhunt health               # per-source status
./.venv/bin/python -m jobhunt show <uid>           # one posting + why
./.venv/bin/python -m jobhunt test-alert           # verify notifications
./.venv/bin/python tools/probe_sources.py          # verify endpoints
./.venv/bin/python tools/audit_filter.py           # what got dropped, and why
```

Scheduling: three Actions runs a day — digest at 13:00 UTC (08:00 CDT),
poll at 17:00 and 23:00 (12:00 and 18:00 CDT). Reduced from hourly on
2026-08-10 while preferences are still being validated.

Hourly was not reliable anyway. GitHub scheduled workflows are best-effort:
observed runs fired at :40-:44 against a requested :07, and two consecutive
hours were skipped with no error. Fewer, well-spaced runs make the delay
irrelevant. Cost was never the binding constraint at hourly (~1,440 of 2,000
free minutes); reliability was.

**Cron is UTC and ignores DST.** These times are Central Daylight; they
shift an hour when CST returns in November. Vishnu is in Tampa (Eastern) but
asked for Central — worth confirming which he meant.

---

## 7.1 Housekeeping gotchas

- **Close `data/tracker.xlsx` before running `sync`.** An open workbook leaves
  a `~$tracker.xlsx` lock file; it briefly got committed. Now gitignored.
- **`.DS_Store`** appears in any folder Finder opens, and everything under
  `site/public/` is deployed. `site.py` strips it before writing.
- **`data/state.json.gz` conflicts on rebase** because it's binary and CI
  rewrites it 3x/day. Resolve by taking CI's copy (`git checkout --ours` mid
  rebase) — state is regenerated every run, so nothing is lost.
- Triggering a CI run pushes state, which leaves the local branch behind. Pull
  with `--rebase --autostash` before pushing again.

## 8. Known limits — state these honestly, don't paper over them

- The 91 direct boards are **exhaustive** per company. The aggregator layer is
  **keyword-driven**, so coverage of Microsoft/Google/Meta/Apple/Tesla and the
  staffing firms is *AI/ML roles at* those companies, not every req.
- Microsoft's own API is decommissioned — `gcsservices.careers.microsoft.com`
  serves a cert for `*.azureedge.net`. There is no direct path to restore.
- LinkedIn and Indeed rate-limit datacenter IPs, so the aggregator source is
  expected to be flaky on GitHub Actions and reliable on the laptop. It fails
  soft and never blocks the rest of a poll.
- USCIS H-1B data is FY2023, the newest at a stable URL. Employer name
  matching is imperfect; `no_record_penalty` is 0 so a miss never demotes.
- `no-target-title` is ~30% of all postings — the largest drop bucket and the
  likeliest place a real role is being missed. Re-audit it periodically.

---

## 9. Session log

### Session 1 — 2026-08-09

Built the whole pipeline from nothing. Ended with 91 boards, ~18.4k postings
per sweep, 1,017 shortlisted, 189 scoring 70+.

Live and verified: hourly GitHub Actions poll, 07:00 digest, Telegram alerts
(proved from GitHub's own runner, not just the laptop), the H-1B enrichment,
the private hosted board, dashboard and Excel with filtered + unfiltered
views.

Two bugs worth remembering because both were silent:
- `mark_closed` scoped by ATS vendor closed 4,839 postings from companies
  that were never polled.
- `instant()` marked postings notified even when Telegram delivery failed,
  which burned 164 alerts during the run that happened before the secrets
  were set. Found only because a later run reported "alerted 0".

Ended on the résumé output being rejected — see "Needs rework" above. That
is the first thing to pick up.
