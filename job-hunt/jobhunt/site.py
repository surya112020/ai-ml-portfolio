"""Build the static site that Cloudflare Pages serves.

Deliberately split into a shell and a data file. The single-file dashboard is
7 MB; committing that three times a day would bloat the repo within weeks.
Here `index.html` is a few KB and rarely changes, while `data.json` carries
the postings as row arrays — no repeated JSON keys — and Cloudflare gzips it
on the wire.

The page fetches its data same-origin, which is exactly what a published
Artifact cannot do: the Artifact CSP blocks it, so a hosted Artifact is
always a snapshot. Pages has no such restriction, so this one is live.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import pipeline

SITE_DIR = Path(__file__).resolve().parent.parent / "site"

# Row arrays keyed by this header. Repeating field names on ~5k rows costs
# more than the values themselves.
COLS = ["s", "co", "t", "loc", "u", "id", "seen", "st", "h1b", "n", "rm",
        "why", "b", "src"]


def _rows(conn: sqlite3.Connection) -> tuple[list, dict]:
    short = pipeline.shortlist(conn, limit=5000, min_score=0)
    considered = [r for r in pipeline.all_rows(conn) if (r["score"] or 0) > 0]

    kept_keys = {r["dedupe_key"] for r in short if (r["score"] or 0) >= 55}
    kept = {r["uid"] for r in considered
            if r["dedupe_key"] in kept_keys and not r["reason"]}
    dupes = {r["dedupe_key"]: r.get("duplicate_count", 1) for r in short}

    out = []
    for r in considered:
        out.append([
            round(r["score"] or 0),
            r["company"],
            r["title"] or "",
            (r["location"] or "")[:70],
            r["url"] or "",
            r["uid"][:8],
            (r["first_seen"] or "")[:16],   # to the minute
            r["status"] or "new",
            r.get("h1b_approvals") or 0,
            dupes.get(r["dedupe_key"], 1),
            1 if r["remote"] else 0,
            (r["reason"] or "")[:40] if r["reason"] else
            ("" if r["uid"] in kept else "below cutoff"),
            r["bucket"],
            r["source"],
        ])
    out.sort(key=lambda x: -x[0])

    tracked = conn.execute(
        """SELECT COUNT(*) FROM jobs WHERE status IN ('applied','skipped')"""
    ).fetchone()[0]
    meta = {
        "generated": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "tracked_total": conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE closed_at IS NULL").fetchone()[0],
        "boards": len(pipeline.load_companies()),
        "applications": tracked,
    }
    return out, meta


def build(conn: sqlite3.Connection, out_dir: Path = SITE_DIR) -> Path:
    rows, meta = _rows(conn)
    # Assets live in public/ with wrangler.toml beside it, not inside it.
    # Pointing the assets directory at the config file's own folder made
    # wrangler fail with "could not detect a directory containing static
    # files"; this is the layout Cloudflare documents.
    public = out_dir / "public"
    public.mkdir(parents=True, exist_ok=True)
    # Finder drops .DS_Store into any folder you open, and everything in
    # public/ gets deployed. Clear junk before writing.
    for junk in out_dir.rglob(".DS_Store"):
        junk.unlink()

    (public / "data.json").write_text(
        json.dumps({"cols": COLS, "meta": meta, "rows": rows},
                   separators=(",", ":")),
        encoding="utf-8",
    )
    (public / "index.html").write_text(INDEX, encoding="utf-8")
    # Never cache the data; always revalidate the shell.
    (public / "_headers").write_text(
        "/data.json\n  Cache-Control: no-store\n\n"
        "/index.html\n  Cache-Control: no-cache\n",
        encoding="utf-8",
    )
    # Cloudflare's git integration creates a Worker, not a Pages project, and
    # runs `npx wrangler deploy`. Without an assets binding that command has
    # no idea the static files exist. `name` must match the Worker in the
    # dashboard or the deploy fails on a name mismatch.
    (out_dir / "wrangler.toml").write_text(
        'name = "job-hunt"\n'
        'compatibility_date = "2026-08-01"\n'
        "\n"
        "[assets]\n"
        'directory = "./public"\n',
        encoding="utf-8",
    )
    return out_dir


INDEX = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Openings</title>
<style>
:root{
  --ink:#0E1418; --paper:#F4F6F5; --surface:#FFF; --sunken:#EDF0EF;
  --line:#DBE1E0; --text:#0E1418; --muted:#5F6E73; --faint:#8A979B;
  --accent:#0B7A6B; --accent-soft:#E2F0ED;
  --hot:#C2461A; --warm:#9A6A08; --cool:#2F6E86; --dim:#7C8A8E; --cut:#A8443A;
}
@media (prefers-color-scheme:dark){:root{
  --ink:#F1F5F4; --paper:#0C1114; --surface:#131A1D; --sunken:#0F1619;
  --line:#243033; --text:#E8EEEC; --muted:#94A5A9; --faint:#6E8085;
  --accent:#3FBFA8; --accent-soft:#12312C;
  --hot:#F0764A; --warm:#D8A43C; --cool:#6FB3CC; --dim:#849498; --cut:#E0776B;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--text);
 font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
 -webkit-font-smoothing:antialiased}
.page{max-width:1400px;margin:0 auto;padding:26px 20px 70px;
 display:flex;flex-direction:column;gap:18px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
 font-variant-numeric:tabular-nums}
.eyebrow{font-size:11px;letter-spacing:.13em;text-transform:uppercase;
 color:var(--accent);font-weight:650}
h1{margin:0;font-size:25px;letter-spacing:-.018em;font-weight:660}
.stamp{color:var(--muted);font-size:12.5px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:11px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;
 padding:12px 14px;display:flex;flex-direction:column;gap:2px}
.tile b{font-size:23px;font-weight:660;line-height:1.05}
.tile span{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--faint)}
.tile.lead b{color:var(--hot)} .tile.ok b{color:var(--accent)}
.tabs{display:flex;gap:2px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.tab{background:none;border:0;padding:10px 15px;cursor:pointer;font:inherit;
 font-size:13px;font-weight:620;color:var(--muted);
 border-bottom:2px solid transparent;margin-bottom:-1px}
.tab[aria-selected=true]{color:var(--text);border-bottom-color:var(--accent)}
.rail{position:sticky;top:0;z-index:5;background:var(--paper);padding:10px 0;
 display:flex;gap:8px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--line)}
input,select{font:inherit;font-size:13px;background:var(--surface);color:var(--text);
 border:1px solid var(--line);border-radius:8px;padding:7px 10px}
input[type=search]{min-width:250px;flex:1 1 250px;max-width:400px}
:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.hits{margin-left:auto;color:var(--muted);font-size:12.5px}
.board{background:var(--surface);border:1px solid var(--line);border-radius:11px;overflow:hidden}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:820px}
th{text-align:left;font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
 color:var(--faint);font-weight:640;padding:10px 12px;background:var(--sunken);
 border-bottom:1px solid var(--line);white-space:nowrap;cursor:pointer;user-select:none}
td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--sunken)}
td.sc{position:relative;width:50px;font-weight:670;font-size:15px;padding-left:15px}
td.sc::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:currentColor}
.v-hot{color:var(--hot)}.v-warm{color:var(--warm)}.v-cool{color:var(--cool)}.v-dim{color:var(--dim)}
a.role{font-weight:600;color:var(--text);text-decoration:none}
a.role:hover{text-decoration:underline;text-underline-offset:2px}
.co{font-weight:560}.src{color:var(--faint);font-size:11.5px}
.loc{color:var(--muted);font-size:12.5px}.when{color:var(--faint);font-size:12px;white-space:nowrap}
.chips{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}
.chip{font-size:10px;padding:1.5px 7px;border-radius:99px;border:1px solid var(--line);
 color:var(--muted);white-space:nowrap}
.chip.on{border-color:var(--accent);color:var(--accent);background:var(--accent-soft);font-weight:640}
.chip.off{border-color:var(--cut);color:var(--cut)}
.chip.h1b{border-color:var(--warm);color:var(--warm)}
.chip.id{font-family:ui-monospace,Menlo,monospace;user-select:all}
.chip.app{border-color:var(--accent);background:var(--accent);color:#fff;font-weight:650}
tr.done td{opacity:.55}
.note{color:var(--muted);font-size:12.5px;padding:12px 14px;background:var(--sunken);
 border:1px solid var(--line);border-radius:9px}
.note code{font-family:ui-monospace,Menlo,monospace;font-size:11.5px}
.empty{padding:34px;text-align:center;color:var(--muted)}
@media(max-width:640px){.page{padding:18px 12px 50px}h1{font-size:21px}}
</style>
</head>
<body>
<div class="page">
  <header>
    <div class="eyebrow">AI / ML openings · live</div>
    <h1>Openings board</h1>
    <div class="stamp mono" id="stamp">loading…</div>
  </header>

  <div class="tiles">
    <div class="tile lead"><b id="k-strong">–</b><span>Act now · 70+</span></div>
    <div class="tile"><b id="k-short">–</b><span>Shortlist</span></div>
    <div class="tile ok"><b id="k-new">–</b><span>New in 24h</span></div>
    <div class="tile ok"><b id="k-app">–</b><span>Applied</span></div>
    <div class="tile"><b id="k-total">–</b><span>AI/ML roles</span></div>
  </div>

  <div class="tabs" role="tablist">
    <button class="tab" role="tab" aria-selected="true" data-v="short">Shortlist</button>
    <button class="tab" role="tab" aria-selected="false" data-v="applied">Applied &amp; skipped</button>
    <button class="tab" role="tab" aria-selected="false" data-v="all">Everything considered</button>
  </div>

  <div class="rail">
    <input type="search" id="q" placeholder="Filter by role, company, location" aria-label="Filter">
    <select id="bk" aria-label="Company type"><option value="">All types</option></select>
    <select id="age" aria-label="First seen">
      <option value="">Any time</option>
      <option value="6">Last 6 hours</option>
      <option value="24">Last 24 hours</option>
      <option value="72">Last 3 days</option>
      <option value="168">Last 7 days</option>
    </select>
    <select id="ms" aria-label="Minimum score">
      <option value="55">Score 55+</option><option value="0">Any score</option>
      <option value="45">Score 45+</option><option value="65">Score 65+</option>
      <option value="75">Score 75+</option><option value="85">Score 85+</option>
    </select>
    <span class="hits mono" id="hits"></span>
  </div>

  <div class="board"><div class="scroll"><table>
    <thead><tr>
      <th data-k="0">Score</th><th data-k="1">Company</th><th data-k="2">Role</th>
      <th data-k="3">Location</th><th data-k="6">First seen</th>
    </tr></thead>
    <tbody id="body"></tbody>
  </table></div></div>

  <p class="note" id="note"></p>
</div>

<script>
const C = {s:0,co:1,t:2,loc:3,u:4,id:5,seen:6,st:7,h1b:8,n:9,rm:10,why:11,b:12,src:13};
let ROWS = [], META = {}, view = "short";
// Generous cap: a few thousand table rows render fine, and the
// previous 1,200 silently hid results the filters said existed.
const RENDER_CAP = 6000;
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function band(s){ return s>=78?"v-hot":s>=65?"v-warm":s>=50?"v-cool":"v-dim"; }

// `seen` is "YYYY-MM-DDTHH:MM" in UTC; without the Z, Safari parses it as
// local time and every row looks hours off.
function hoursSince(d){
  if(!d) return Infinity;
  const t = Date.parse(d.length > 10 ? d + "Z" : d + "T00:00:00Z");
  return isNaN(t) ? Infinity : (Date.now() - t) / 3600000;
}
function ago(d){
  const h = hoursSince(d);
  if(h === Infinity) return "—";
  if(h < 1)  return "just now";
  if(h < 24) return Math.floor(h) + " h";
  const days = Math.floor(h / 24);
  return days === 1 ? "yesterday" : days + " d";
}

function inView(r){
  const applied = r[C.st]==="applied" || r[C.st]==="skipped";
  if(view==="applied") return applied;
  if(view==="short")   return !applied && !r[C.why];
  return true;
}

function render(){
  const t = $("q").value.toLowerCase().trim(), bk = $("bk").value,
        ms = +$("ms").value, maxAge = $("age").value ? +$("age").value : Infinity;
  const out = [];
  let shown = 0;
  for(const r of ROWS){
    if(!inView(r)) continue;
    if(r[C.s] < ms) continue;
    if(hoursSince(r[C.seen]) > maxAge) continue;
    if(bk && r[C.b] !== bk) continue;
    if(t && !(r[C.co]+" "+r[C.t]+" "+r[C.loc]).toLowerCase().includes(t)) continue;
    shown++;
    if(shown > RENDER_CAP) continue;

    const chips = [];
    if(r[C.st]==="applied") chips.push('<span class="chip app">applied</span>');
    else if(r[C.st]==="skipped") chips.push('<span class="chip">skipped</span>');
    else if(r[C.why]) chips.push('<span class="chip off">'+esc(r[C.why])+'</span>');
    if(r[C.b]==="bigtech") chips.push('<span class="chip">big tech</span>');
    if(r[C.h1b]>=250) chips.push('<span class="chip h1b">H-1B '+r[C.h1b].toLocaleString()+'</span>');
    if(r[C.n]>1) chips.push('<span class="chip">'+r[C.n]+' locations</span>');
    if(r[C.rm]) chips.push('<span class="chip">remote</span>');
    chips.push('<span class="chip id">'+esc(r[C.id])+'</span>');

    out.push('<tr class="'+(r[C.st]==="applied"||r[C.st]==="skipped"?"done":"")+'">'
      +'<td class="sc mono '+band(r[C.s])+'">'+r[C.s]+'</td>'
      +'<td><span class="co">'+esc(r[C.co])+'</span><div class="src">'+esc(r[C.src])+'</div></td>'
      +'<td><a class="role" href="'+esc(r[C.u])+'" target="_blank" rel="noopener noreferrer">'
      +esc(r[C.t])+'</a><div class="chips">'+chips.join("")+'</div></td>'
      +'<td class="loc">'+esc(r[C.loc])+'</td>'
      +'<td class="when mono">'+ago(r[C.seen])+'</td></tr>');
  }
  $("body").innerHTML = out.length ? out.join("")
    : '<tr><td colspan="5" class="empty">Nothing matches these filters.</td></tr>';
  $("hits").textContent = shown.toLocaleString() + " shown"
    + (shown>RENDER_CAP ? ` (first ${RENDER_CAP.toLocaleString()} rendered)` : "");
}

function sortBy(k){
  const num = k===0;
  const dir = sortBy.last===k ? -(sortBy.dir||1) : -1;
  sortBy.last = k; sortBy.dir = dir;
  ROWS.sort((a,b)=> num ? (a[k]-b[k])*dir : String(a[k]).localeCompare(String(b[k]))*dir);
  render();
}

fetch("data.json?t=" + Date.now()).then(r=>r.json()).then(d=>{
  ROWS = d.rows; META = d.meta;
  const when = new Date(META.generated);
  const mins = Math.round((Date.now()-when)/60000);
  // Two different numbers, and conflating them is confusing: tracked_total
  // is every role at every company (sales, HR, warehouse included), while
  // ROWS holds only what cleared the title filter.
  $("stamp").innerHTML = "Updated " + when.toLocaleString()
    + "  ·  " + (mins<90 ? mins+" min ago" : Math.round(mins/60)+" hr ago")
    + "  ·  <b>" + ROWS.length.toLocaleString() + "</b> AI/ML roles"
    + " &nbsp;<span style='opacity:.7'>(filtered from "
    + META.tracked_total.toLocaleString() + " total postings across "
    + META.boards + " boards)</span>";

  const live = ROWS.filter(r=>!r[C.why] && r[C.st]!=="applied" && r[C.st]!=="skipped");
  $("k-strong").textContent = live.filter(r=>r[C.s]>=70).length;
  $("k-short").textContent  = live.filter(r=>r[C.s]>=55).length.toLocaleString();
  $("k-app").textContent    = ROWS.filter(r=>r[C.st]==="applied").length;
  $("k-new").textContent    = ROWS.filter(r=>hoursSince(r[C.seen]) <= 24).length.toLocaleString();
  $("k-total").textContent  = ROWS.length.toLocaleString();

  const buckets = [...new Set(ROWS.map(r=>r[C.b]))].sort();
  $("bk").innerHTML = '<option value="">All types</option>'
    + buckets.map(b=>'<option>'+esc(b)+'</option>').join("");

  $("note").innerHTML = 'Showing score 55+ by default \u2014 switch to '
    + '<b>Any score</b> to include staffing-firm roles (Kforce, Insight Global, '
    + 'TEKsystems and similar mostly score 40\u201355). '
    + 'Click a column header to sort. The monospace code on each '
    + 'row is its id — mark one applied from your Mac with '
    + '<code>python -m jobhunt applied &lt;id&gt;</code>, and it shows here on the '
    + 'next run. This page rebuilds three times a day.';
  render();
}).catch(e=>{
  $("stamp").textContent = "Could not load data.json — " + e;
});

["q","bk","ms","age"].forEach(id=>$(id).addEventListener("input",render));
document.querySelectorAll(".tab").forEach(tab=>tab.addEventListener("click",()=>{
  view = tab.dataset.v;
  document.querySelectorAll(".tab").forEach(t=>t.setAttribute("aria-selected", String(t===tab)));
  $("ms").value = view==="short" ? "55" : "0";
  render();
}));
document.querySelectorAll("th[data-k]").forEach(th=>
  th.addEventListener("click",()=>sortBy(+th.dataset.k)));
</script>
</body>
</html>
"""
