"""Render the openings board as a publishable Artifact page.

Differs from dashboard.py in two ways: it emits page-content only (the
Artifact host supplies the document skeleton), and it carries only postings
that cleared the title filter. The local dashboard and the xlsx hold all
~18k; shipping those over the network would be a multi-megabyte page for
rows that are sales and warehouse roles.

No personal data is rendered here. Everything in config/identity.yml —
name, contact, visa status — stays out of the page.
"""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import pipeline

CSS = """
:root{
  --ink:#0E1418; --paper:#F4F6F5; --surface:#FFFFFF; --sunken:#EDF0EF;
  --line:#DBE1E0; --text:#0E1418; --muted:#5F6E73; --faint:#8A979B;
  --accent:#0B7A6B; --accent-soft:#E2F0ED;
  --hot:#C2461A; --warm:#9A6A08; --cool:#2F6E86; --dim:#7C8A8E;
  --cut:#A8443A;
}
@media (prefers-color-scheme:dark){
  :root{
    --ink:#F1F5F4; --paper:#0C1114; --surface:#131A1D; --sunken:#0F1619;
    --line:#243033; --text:#E8EEEC; --muted:#94A5A9; --faint:#6E8085;
    --accent:#3FBFA8; --accent-soft:#12312C;
    --hot:#F0764A; --warm:#D8A43C; --cool:#6FB3CC; --dim:#849498;
    --cut:#E0776B;
  }
}
:root[data-theme="light"]{
  --ink:#0E1418; --paper:#F4F6F5; --surface:#FFFFFF; --sunken:#EDF0EF;
  --line:#DBE1E0; --text:#0E1418; --muted:#5F6E73; --faint:#8A979B;
  --accent:#0B7A6B; --accent-soft:#E2F0ED;
  --hot:#C2461A; --warm:#9A6A08; --cool:#2F6E86; --dim:#7C8A8E; --cut:#A8443A;
}
:root[data-theme="dark"]{
  --ink:#F1F5F4; --paper:#0C1114; --surface:#131A1D; --sunken:#0F1619;
  --line:#243033; --text:#E8EEEC; --muted:#94A5A9; --faint:#6E8085;
  --accent:#3FBFA8; --accent-soft:#12312C;
  --hot:#F0764A; --warm:#D8A43C; --cool:#6FB3CC; --dim:#849498; --cut:#E0776B;
}

*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--text);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.page{max-width:1360px;margin:0 auto;padding:32px 24px 80px;
  display:flex;flex-direction:column;gap:22px}
.mono{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
  font-variant-numeric:tabular-nums}

header{display:flex;flex-direction:column;gap:5px}
.eyebrow{font-size:11px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--accent);font-weight:650}
h1{margin:0;font-size:27px;line-height:1.15;letter-spacing:-.018em;
  text-wrap:balance;font-weight:660}
.stamp{color:var(--muted);font-size:13px}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;
  padding:13px 15px;display:flex;flex-direction:column;gap:3px}
.tile .n{font-size:25px;font-weight:660;letter-spacing:-.02em;line-height:1.05}
.tile .k{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--faint)}
.tile.lead .n{color:var(--hot)}
.tile.cut .n{color:var(--cut)}

.tabs{display:flex;gap:2px;border-bottom:1px solid var(--line)}
.tab{appearance:none;background:none;border:0;padding:10px 15px;cursor:pointer;
  font:inherit;font-size:13px;font-weight:620;color:var(--muted);
  border-bottom:2px solid transparent;margin-bottom:-1px}
.tab[aria-selected="true"]{color:var(--text);border-bottom-color:var(--accent)}
.tab:focus-visible{outline:2px solid var(--accent);outline-offset:-2px;border-radius:4px}

.rail{position:sticky;top:0;z-index:5;background:var(--paper);
  padding:11px 0;display:flex;gap:9px;flex-wrap:wrap;align-items:center;
  border-bottom:1px solid var(--line)}
input,select{font:inherit;font-size:13px;background:var(--surface);
  color:var(--text);border:1px solid var(--line);border-radius:8px;padding:7px 11px}
input[type="search"]{min-width:270px;flex:1 1 270px;max-width:420px}
input:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.hits{margin-left:auto;color:var(--muted);font-size:12.5px}

.board{background:var(--surface);border:1px solid var(--line);
  border-radius:11px;overflow:hidden}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:840px}
th{text-align:left;font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--faint);font-weight:640;padding:10px 12px;background:var(--sunken);
  border-bottom:1px solid var(--line);white-space:nowrap;cursor:pointer;user-select:none}
th:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
td{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--sunken)}

/* severity stripe: urgency reads before the number does */
td.sc{position:relative;width:52px;font-weight:670;font-size:15px;padding-left:16px}
td.sc::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:currentColor}
.v-hot{color:var(--hot)} .v-warm{color:var(--warm)}
.v-cool{color:var(--cool)} .v-dim{color:var(--dim)}

.role{font-weight:600;color:var(--text);text-decoration:none;display:inline-block}
.role:hover{text-decoration:underline;text-underline-offset:2px}
.role:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:3px}
.co{font-weight:560}
.src{color:var(--faint);font-size:11.5px}
.loc{color:var(--muted);font-size:12.5px}
.when{color:var(--faint);font-size:12px;white-space:nowrap}

.chips{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}
.chip{font-size:10px;letter-spacing:.045em;padding:1.5px 7px;border-radius:99px;
  border:1px solid var(--line);color:var(--muted);white-space:nowrap}
.chip.on{border-color:var(--accent);color:var(--accent);background:var(--accent-soft);font-weight:640}
.chip.off{border-color:var(--cut);color:var(--cut)}
.chip.h1b{border-color:var(--warm);color:var(--warm)}
.why{margin-top:5px;font-size:11.5px;color:var(--faint);display:none}
tr.open .why{display:block}

.note{color:var(--muted);font-size:12.5px;padding:13px 15px;
  background:var(--sunken);border:1px solid var(--line);border-radius:9px}
.note b{color:var(--text)}
[hidden]{display:none !important}
@media (prefers-reduced-motion:reduce){*{transition:none !important;animation:none !important}}
@media (max-width:640px){.page{padding:22px 14px 60px}h1{font-size:22px}}
"""

JS = """
(function(){
  var views={s:document.getElementById('view-s'),a:document.getElementById('view-a')};
  var cur='s';
  var q=document.getElementById('q'), bk=document.getElementById('bk'),
      ms=document.getElementById('ms'), st=document.getElementById('st'),
      hits=document.getElementById('hits');

  function apply(){
    var t=q.value.toLowerCase().trim(), b=bk.value, m=+ms.value, s=st.value;
    var rows=views[cur].querySelectorAll('tbody tr'), n=0;
    for(var i=0;i<rows.length;i++){
      var r=rows[i], d=r.dataset;
      var ok=(!t||d.s.indexOf(t)>-1)&&(!b||d.b===b)&&(+d.v>=m)&&(s===''||d.k===s);
      r.hidden=!ok; if(ok)n++;
    }
    hits.textContent=n.toLocaleString()+' shown';
  }
  [q,bk,ms,st].forEach(function(el){el.addEventListener('input',apply);});

  document.querySelectorAll('.tab').forEach(function(tab){
    tab.addEventListener('click',function(){
      cur=tab.dataset.v;
      document.querySelectorAll('.tab').forEach(function(t){
        t.setAttribute('aria-selected', String(t===tab));
      });
      views.s.hidden = cur!=='s'; views.a.hidden = cur!=='a';
      st.disabled = cur==='s';
      apply();
    });
  });

  // Delegated: thousands of rows, so no per-row listeners.
  document.addEventListener('click',function(e){
    if(e.target.closest('a')) return;
    var tr=e.target.closest('tbody tr'); if(tr) tr.classList.toggle('open');
  });

  document.querySelectorAll('th[data-k]').forEach(function(th){
    var asc=false;
    th.tabIndex=0;
    function sort(){
      asc=!asc;
      var tb=th.closest('table').tBodies[0], k=th.dataset.k;
      var rows=[].slice.call(tb.rows);
      rows.sort(function(x,y){
        var a=x.dataset[k]||'', c=y.dataset[k]||'';
        var na=parseFloat(a), nc=parseFloat(c), r;
        r=(!isNaN(na)&&!isNaN(nc))?na-nc:String(a).localeCompare(String(c));
        return asc?r:-r;
      });
      rows.forEach(function(r){tb.appendChild(r);});
    }
    th.addEventListener('click',sort);
    th.addEventListener('keydown',function(e){
      if(e.key==='Enter'||e.key===' '){e.preventDefault();sort();}
    });
  });
  apply();
})();
"""


def _age(stamp: str | None) -> str:
    try:
        seen = datetime.fromisoformat(stamp or "")
    except ValueError:
        return "—"
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    hours = (datetime.now(tz=timezone.utc) - seen).total_seconds() / 3600
    if hours < 1:
        return f"{max(int(hours * 60), 1)} min"
    if hours < 48:
        return f"{int(hours)} hr"
    return f"{int(hours / 24)} d"


def _band(score: float) -> str:
    if score >= 78:
        return "v-hot"
    if score >= 65:
        return "v-warm"
    if score >= 50:
        return "v-cool"
    return "v-dim"


def _row(row: dict, kept: set[str] | None, with_status: bool) -> str:
    score = row["score"] or 0
    esc = html.escape
    chips = []
    keep = True

    if with_status:
        reason = row.get("reason") or ""
        keep = not reason and row["uid"] in (kept or set())
        if keep:
            chips.append("<span class='chip on'>shortlist</span>")
        elif reason:
            chips.append(f"<span class='chip off'>{esc(reason[:34])}</span>")
        else:
            chips.append(f"<span class='chip'>below cutoff</span>")

    if row["status"] == "new":
        chips.append("<span class='chip on'>new</span>")
    if row["bucket"] == "bigtech":
        chips.append("<span class='chip'>big tech</span>")
    if (row.get("h1b_approvals") or 0) >= 250:
        chips.append(f"<span class='chip h1b'>H-1B {row['h1b_approvals']:,}</span>")
    if row.get("duplicate_count", 1) > 1:
        chips.append(f"<span class='chip'>{row['duplicate_count']} locations</span>")
    if row["remote"]:
        chips.append("<span class='chip'>remote</span>")

    why = ""
    if not with_status:
        reasons = json.loads(row["score_reasons"] or "[]")
        if reasons:
            why = f"<div class='why'>{esc(' · '.join(reasons))}</div>"

    search = " ".join([row["title"] or "", row["company"], row["location"] or "",
                       row["bucket"]]).lower()[:120]

    return (
        f"<tr data-v='{score:.0f}' data-b='{esc(row['bucket'])}' "
        f"data-k='{1 if keep else 0}' data-s='{esc(search)}' "
        f"data-co='{esc(row['company'])}' data-ti='{esc(row['title'] or '')}' "
        f"data-ag='{esc(row['first_seen'] or '')}'>"
        f"<td class='sc mono {_band(score)}'>{score:.0f}</td>"
        f"<td><span class='co'>{esc(row['company'])}</span>"
        f"<div class='src'>{esc(row['source'])}</div></td>"
        f"<td><a class='role' href='{esc(row['url'] or '#')}' target='_blank' "
        f"rel='noopener noreferrer'>{esc(row['title'] or 'Untitled')}</a>"
        f"<div class='chips'>{''.join(chips)}</div>{why}</td>"
        f"<td class='loc'>{esc((row['location'] or '')[:46])}</td>"
        f"<td class='when mono'>{_age(row['first_seen'])}</td></tr>"
    )


def render(conn: sqlite3.Connection, path: Path, min_score: float = 55) -> Path:
    short = pipeline.shortlist(conn, limit=5000, min_score=min_score)
    considered = [r for r in pipeline.all_rows(conn) if (r["score"] or 0) > 0]

    kept_keys = {r["dedupe_key"] for r in short}
    kept_uids = {r["uid"] for r in considered
                 if r["dedupe_key"] in kept_keys and not r["reason"]}

    tracked = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE closed_at IS NULL"
    ).fetchone()[0]
    strong = sum(1 for r in short if (r["score"] or 0) >= 70)
    blocked = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE blockers IS NOT NULL AND blockers <> '[]'"
    ).fetchone()[0]
    buckets = sorted({r["bucket"] for r in considered})

    def head(status: bool) -> str:
        return (
            "<tr><th data-k='v'>Score</th><th data-k='co'>Company</th>"
            "<th data-k='ti'>Role" + (" &amp; status" if status else "") +
            "</th><th>Location</th><th data-k='ag'>Seen</th></tr>"
        )

    parts = [
        "<title>Openings Board</title>",
        f"<style>{CSS}</style>",
        "<div class='page'>",
        "<header>",
        "<div class='eyebrow'>AI / ML openings · live board</div>",
        "<h1>Ranked openings, refreshed hourly</h1>",
        f"<div class='stamp mono'>Updated {datetime.now().strftime('%d %b %Y, %H:%M')}"
        f" · {tracked:,} postings tracked across 91 boards</div>",
        "</header>",

        "<div class='tiles'>",
        f"<div class='tile lead'><span class='n mono'>{strong}</span>"
        "<span class='k'>Act now · 70+</span></div>",
        f"<div class='tile'><span class='n mono'>{len(short):,}</span>"
        "<span class='k'>Shortlist</span></div>",
        f"<div class='tile'><span class='n mono'>{len(considered):,}</span>"
        "<span class='k'>Passed title filter</span></div>",
        f"<div class='tile cut'><span class='n mono'>{blocked:,}</span>"
        "<span class='k'>Blocked · visa / clearance</span></div>",
        "</div>",

        "<div class='tabs' role='tablist'>",
        f"<button class='tab' role='tab' aria-selected='true' data-v='s'>"
        f"Shortlist ({len(short):,})</button>",
        f"<button class='tab' role='tab' aria-selected='false' data-v='a'>"
        f"Everything considered ({len(considered):,})</button>",
        "</div>",

        "<div class='rail'>",
        "<input type='search' id='q' placeholder='Filter by role, company, location'"
        " aria-label='Filter openings'>",
        "<select id='bk' aria-label='Company type'><option value=''>All types</option>",
        *[f"<option value='{html.escape(b)}'>{html.escape(b)}</option>" for b in buckets],
        "</select>",
        "<select id='ms' aria-label='Minimum score'>",
        *[f"<option value='{v}'>Score {v}+</option>" for v in (0, 45, 55, 65, 75, 85)],
        "</select>",
        "<select id='st' aria-label='Shortlist status' disabled>"
        "<option value=''>Shortlist + filtered</option>"
        "<option value='1'>Shortlist only</option>"
        "<option value='0'>Filtered out only</option></select>",
        "<span class='hits mono' id='hits'></span>",
        "</div>",

        "<div id='view-s'><div class='board'><div class='scroll'><table>",
        f"<thead>{head(False)}</thead><tbody>",
        *[_row(r, None, False) for r in short],
        "</tbody></table></div></div></div>",

        "<div id='view-a' hidden><div class='board'><div class='scroll'><table>",
        f"<thead>{head(True)}</thead><tbody>",
        *[_row(r, kept_uids, True) for r in considered],
        "</tbody></table></div></div></div>",

        "<p class='note'>Click any row to see how it scored. This board carries "
        f"the <b>{len(considered):,}</b> postings that cleared the title filter; "
        f"the remaining {tracked - len(considered):,} are non-engineering roles "
        "(sales, management, design) and live in the spreadsheet export. "
        "Scores weigh title fit, location, skill overlap with the résumé, "
        "posting freshness, and the employer's H-1B filing history.</p>",
        "</div>",
        f"<script>{JS}</script>",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts), encoding="utf-8")
    return path
