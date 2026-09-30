"""Static HTML board — the thing he actually looks at.

Two views: a ranked shortlist, and every posting we hold with the reason it
was skipped. The second one is the safety net; a ranking can be wrong, and
nothing should be invisible just because it scored badly.

Self-contained (no CDN), so it opens from a file:// URL on any machine,
including a locked-down work laptop.
"""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import pipeline

CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#252a34;--fg:#e6e8ec;--dim:#8b93a1;
--hot:#f5a524;--good:#22c55e;--ok:#3b82f6;--warn:#ef4444;--accent:#6366f1;}
@media(prefers-color-scheme:light){:root{--bg:#f6f7f9;--card:#fff;--line:#e3e6ea;
--fg:#14171f;--dim:#5f6773;}}
*{box-sizing:border-box}
body{margin:0;padding:20px;background:var(--bg);color:var(--fg);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
h1{font-size:20px;margin:0 0 4px}
.sub{color:var(--dim);margin-bottom:16px;font-size:13px}
.tabs{display:flex;gap:4px;margin-bottom:14px;border-bottom:1px solid var(--line)}
.tab{padding:9px 16px;cursor:pointer;border:none;background:none;color:var(--dim);
font-size:13px;font-weight:600;border-bottom:2px solid transparent}
.tab.on{color:var(--fg);border-bottom-color:var(--accent)}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;align-items:center}
input,select{background:var(--card);color:var(--fg);border:1px solid var(--line);
border-radius:7px;padding:7px 10px;font-size:13px}
input[type=search]{min-width:280px}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:16px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:9px;
padding:9px 15px;min-width:92px}
.stat b{display:block;font-size:19px}
.stat span{color:var(--dim);font-size:10px;text-transform:uppercase;
letter-spacing:.05em}
table{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:9px;overflow:hidden}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
color:var(--dim);padding:9px;border-bottom:1px solid var(--line);
position:sticky;top:0;background:var(--card);cursor:pointer;user-select:none;z-index:1}
td{padding:9px;border-bottom:1px solid var(--line);vertical-align:top}
tr.row:hover{background:rgba(127,127,127,.07)}
a{color:inherit;text-decoration:none}
a.title{font-weight:600}
a.title:hover{text-decoration:underline}
.score{font-weight:700;font-variant-numeric:tabular-nums}
.s-hot{color:var(--hot)}.s-good{color:var(--good)}.s-ok{color:var(--ok)}
.s-no{color:var(--dim)}
.tag{display:inline-block;font-size:10px;padding:2px 7px;border-radius:20px;
border:1px solid var(--line);color:var(--dim);margin-right:4px;white-space:nowrap}
.tag.new{border-color:var(--good);color:var(--good)}
.tag.bigtech{border-color:var(--ok);color:var(--ok)}
.tag.h1b{border-color:var(--hot);color:var(--hot)}
.tag.keep{border-color:var(--good);color:var(--good);font-weight:700}
.tag.cut{border-color:var(--warn);color:var(--warn)}
tr.filtered td{opacity:.5}
tr.filtered:hover td{opacity:1}
.tag.uid{font-family:ui-monospace,Menlo,monospace;user-select:all;cursor:text}
.dim{color:var(--dim);font-size:12px}
.why{color:var(--dim);font-size:11px;margin-top:3px;display:none}
tr.open .why{display:block}
.wrap{overflow-x:auto}
.view{display:none}.view.on{display:block}
.skip{color:var(--warn);font-size:11px}
"""

JS = """
const views={s:document.getElementById('v-s'),a:document.getElementById('v-a')};
let cur='s';
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  cur=t.dataset.v;
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===t));
  Object.entries(views).forEach(([k,v])=>v.classList.toggle('on',k===cur));
  apply();});

const q=document.getElementById('q'),b=document.getElementById('bucket'),
      m=document.getElementById('minscore'),k=document.getElementById('kept');
function apply(){
  const t=q.value.toLowerCase(),bk=b.value,ms=+m.value,kp=k.value;
  const rows=views[cur].querySelectorAll('tr.row');let n=0;
  rows.forEach(r=>{const ok=(!t||r.dataset.search.includes(t))&&
    (!bk||r.dataset.bucket===bk)&&(+r.dataset.score>=ms)&&
    (kp===''||r.dataset.kept===kp);
    r.style.display=ok?'':'none';if(ok)n++;});
  document.getElementById('count').textContent=n;}
[q,b,m,k].forEach(e=>e.addEventListener('input',apply));

// Delegation: the unfiltered view has ~11k rows, so per-row listeners are out.
document.addEventListener('click',e=>{
  if(e.target.closest('a'))return;
  const r=e.target.closest('tr.row');if(r)r.classList.toggle('open');});

document.querySelectorAll('th[data-k]').forEach(th=>{let asc=false;
 th.onclick=()=>{asc=!asc;const k=th.dataset.k,tb=th.closest('table').tBodies[0];
  [...tb.rows].sort((x,y)=>{const a=x.dataset[k],c=y.dataset[k];
   const na=parseFloat(a),nc=parseFloat(c);
   const v=(!isNaN(na)&&!isNaN(nc))?na-nc:String(a).localeCompare(String(c));
   return asc?v:-v;}).forEach(r=>tb.appendChild(r));};});
apply();
"""


def _age(stamp: str) -> str:
    try:
        seen = datetime.fromisoformat(stamp)
    except (ValueError, TypeError):
        return "?"
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    hours = (datetime.now(tz=timezone.utc) - seen).total_seconds() / 3600
    if hours < 1:
        return f"{int(hours * 60)}m ago"
    if hours < 48:
        return f"{int(hours)}h ago"
    return f"{int(hours / 24)}d ago"


def _row_html(row: dict, show_reason: bool = False,
              kept: set[str] | None = None) -> str:
    score = row["score"] or 0
    cls = ("s-hot" if score >= 75 else "s-good" if score >= 62
           else "s-ok" if score >= 45 else "s-no")
    # Score reasons only on the shortlist. Emitting them for all ~11k rows in
    # the unfiltered view pushed the page past 9 MB.
    reasons = [] if show_reason else json.loads(row["score_reasons"] or "[]")
    search = " ".join([row["title"] or "", row["company"], row["location"] or "",
                       row["bucket"], row.get("reason") or ""]).lower()

    tags = []
    if row["status"] == "new":
        tags.append("<span class='tag new'>new</span>")
    if row["bucket"] == "bigtech":
        tags.append("<span class='tag bigtech'>big tech</span>")
    if (row.get("h1b_approvals") or 0) >= 250:
        tags.append(f"<span class='tag h1b'>H-1B {row['h1b_approvals']:,}</span>")
    if row.get("duplicate_count", 1) > 1:
        tags.append(f"<span class='tag'>{row['duplicate_count']} locations</span>")
    if row["remote"]:
        tags.append("<span class='tag'>remote</span>")
    # The id needed for `jobhunt tailor <id>`; without it there is no path
    # from a row you like to generating its application material.
    tags.append(f"<span class='tag uid' title='jobhunt tailor {row["uid"][:8]}'>"
                f"{row['uid'][:8]}</span>")

    # On the unfiltered view, say plainly whether a row already made the
    # shortlist so he isn't re-reading rows the scorer already vetted.
    reason_cell = ""
    on_shortlist = True
    if show_reason:
        text = row.get("reason") or ""
        on_shortlist = not text and row["uid"] in (kept or set())
        if on_shortlist:
            reason_cell = "<td><span class='tag keep'>✓ shortlist</span></td>"
        elif text:
            reason_cell = f"<td><span class='tag cut'>{html.escape(text[:38])}</span></td>"
        else:
            reason_cell = (
                f"<td><span class='tag'>below cutoff ({score:.0f})</span></td>"
            )

    # The unfiltered view is ~11k rows; the sort-key attributes are only
    # meaningful on the shortlist, and repeating them here cost ~3 MB.
    sort_attrs = "" if show_reason else (
        f"data-company='{html.escape(row['company'])}' "
        f"data-title='{html.escape(row['title'] or '')}' "
        f"data-location='{html.escape(row['location'] or '')}' "
        f"data-age='{html.escape(row['first_seen'] or '')}' "
    )
    return (
        f"<tr class='row{'' if on_shortlist else ' filtered'}' "
        f"data-score='{score:.0f}' data-kept='{1 if on_shortlist else 0}' "
        f"data-bucket='{html.escape(row['bucket'])}' "
        f"{sort_attrs}"
        f"data-search='{html.escape(search[:110])}'>"
        f"<td class='score {cls}'>{score:.0f}</td>"
        f"{reason_cell}"
        f"<td>{html.escape(row['company'])}<div class='dim'>{html.escape(row['source'])}</div></td>"
        f"<td><a class='title' href='{html.escape(row['url'] or '')}' target='_blank' "
        f"rel='noopener'>{html.escape(row['title'] or '')}</a>"
        f"<div>{''.join(tags)}</div>"
        f"<div class='why'>{html.escape(' · '.join(reasons))}</div></td>"
        f"<td class='dim'>{html.escape((row['location'] or '')[:44])}</td>"
        f"<td class='dim'>{_age(row['first_seen'])}</td></tr>"
    )


def render(conn: sqlite3.Connection, path: Path, min_score: float = 55,
           limit: int = 5000) -> Path:
    short = pipeline.shortlist(conn, limit=limit, min_score=min_score)
    everything = pipeline.all_rows(conn)
    # Every posting the shortlist covers, including the duplicates it folded
    # away — otherwise a role's other locations look "filtered out".
    kept_keys = {r["dedupe_key"] for r in short}
    kept_uids = {
        r["uid"] for r in everything
        if r["dedupe_key"] in kept_keys and not r["reason"]
    }

    totals = conn.execute(
        """SELECT COUNT(*) total, SUM(closed_at IS NULL) live,
                  SUM(score>=70 AND closed_at IS NULL
                      AND (blockers IS NULL OR blockers='[]')) strong
           FROM jobs"""
    ).fetchone()
    blocked = conn.execute(
        "SELECT COUNT(*) c FROM jobs WHERE blockers LIKE '%sponsorship%'"
    ).fetchone()["c"]
    buckets = sorted({r["bucket"] for r in everything})

    head = (
        "<th data-k='score'>score</th>{reason}<th data-k='company'>company</th>"
        "<th data-k='title'>role</th><th data-k='location'>location</th>"
        "<th data-k='age'>first seen</th>"
    )

    body = [
        "<h1>Openings</h1>",
        f"<div class='sub'>updated {datetime.now().strftime('%b %d, %Y %H:%M')} · "
        f"<span id='count'>{len(short)}</span> shown in this view</div>",
        "<div class='stats'>",
        f"<div class='stat'><b>{totals['live'] or 0:,}</b><span>tracked</span></div>",
        f"<div class='stat'><b>{len(short):,}</b><span>shortlist</span></div>",
        f"<div class='stat'><b>{totals['strong'] or 0}</b><span>score 70+</span></div>",
        f"<div class='stat'><b>{blocked}</b><span>no-sponsorship</span></div>",
        "</div>",
        "<div class='tabs'>",
        f"<button class='tab on' data-v='s'>Shortlist ({len(short):,})</button>",
        f"<button class='tab' data-v='a'>Everything, unfiltered ({len(everything):,})</button>",
        "</div>",
        "<div class='bar'>",
        "<input type='search' id='q' placeholder='filter by title, company, location…'>",
        "<select id='bucket'><option value=''>all buckets</option>",
        *[f"<option>{html.escape(b)}</option>" for b in buckets],
        "</select>",
        "<select id='minscore'>",
        *[f"<option value='{v}'{' selected' if v == 0 else ''}>score {v}+</option>"
          for v in (0, 40, 45, 55, 65, 75, 85)],
        "</select>",
        "<select id='kept'><option value=''>shortlist + filtered</option>"
        "<option value='1'>shortlist only</option>"
        "<option value='0'>filtered-out only</option></select>",
        "</div>",

        "<div class='view on' id='v-s'><div class='wrap'><table><thead><tr>",
        head.format(reason=""),
        "</tr></thead><tbody>",
        *[_row_html(r) for r in short],
        "</tbody></table></div></div>",

        "<div class='view' id='v-a'><div class='wrap'><table><thead><tr>",
        head.format(reason="<th data-k='kept'>status</th>"),
        "</tr></thead><tbody>",
        *[_row_html(r, show_reason=True, kept=kept_uids) for r in everything],
        "</tbody></table></div></div>",
    ]

    page = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Openings</title><style>" + CSS + "</style></head><body>"
        + "".join(body) + "<script>" + JS + "</script></body></html>"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path
