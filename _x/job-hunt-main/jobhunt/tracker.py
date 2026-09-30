"""One long-lived Excel tracker you mark up by hand.

Unlike `jobhunt excel`, which rewrites a fresh report every run, this file is
append-only and **never overwrites your edits**. New postings are added at
the bottom with the date they appeared; the Status, Applied on and Notes
columns belong to you and are read back into the database, so marking a row
Applied here also removes it from the board's shortlist and stops it being
alerted again.

Rows are matched by the posting id in the last column. Don't sort that column
away — everything else is safe to sort, filter and recolour.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from . import pipeline, store

TRACKER_PATH = Path(__file__).resolve().parent.parent / "data" / "tracker.xlsx"
SHEET = "Tracker"

# (header, width). The three you edit sit first so they're reachable without
# scrolling; the id lives last and is what rows are matched on.
COLUMNS = [
    ("Date added", 12), ("Status", 13), ("Applied on", 12), ("Notes", 34),
    ("Score", 7), ("Company", 20), ("Title", 56), ("Location", 28),
    ("Type", 12), ("H-1B", 9), ("Remote", 8), ("Locs", 6), ("Link", 44),
    ("id", 11),
]
COL = {name: i + 1 for i, (name, _) in enumerate(COLUMNS)}
ID_COL = COL["id"]
STATUSES = ["", "Interested", "Applied", "Skipped", "Rejected", "Interview"]
EDITABLE = ("Status", "Applied on", "Notes")

HEADER_FILL = PatternFill("solid", fgColor="0E3B34")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
MINE_FILL = PatternFill("solid", fgColor="E8F3F0")   # your columns
HOT = PatternFill("solid", fgColor="FDE8D7")


def _local_day(stamp: object) -> str | None:
    """UTC timestamp -> the date it was on *here*.

    first_seen is stored in UTC, so anything found after 8pm Eastern carries
    tomorrow's date. In a spreadsheet a human reads, that is just wrong.
    """
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(str(stamp))
    except ValueError:
        return str(stamp)[:10]
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().date().isoformat()


def _read_existing(path: Path) -> tuple[dict[str, dict], list[str]]:
    """Existing rows keyed by posting id, preserving whatever you typed."""
    if not path.exists():
        return {}, []
    book = load_workbook(path)
    if SHEET not in book.sheetnames:
        return {}, []
    sheet = book[SHEET]
    kept: dict[str, dict] = {}
    order: list[str] = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row or len(row) < ID_COL:
            continue
        uid = row[ID_COL - 1]
        if not uid:
            continue
        uid = str(uid).strip()
        kept[uid] = {
            "Date added": row[COL["Date added"] - 1],
            "Status": row[COL["Status"] - 1],
            "Applied on": row[COL["Applied on"] - 1],
            "Notes": row[COL["Notes"] - 1],
        }
        order.append(uid)
    return kept, order


def _sync_to_db(conn: sqlite3.Connection, existing: dict[str, dict]) -> int:
    """Push your Applied/Skipped marks back into the database."""
    changed = 0
    for uid, values in existing.items():
        status = str(values.get("Status") or "").strip().lower()
        if status not in ("applied", "skipped"):
            continue
        applied_on = values.get("Applied on")
        if isinstance(applied_on, datetime):
            applied_on = applied_on.date().isoformat()
        elif applied_on:
            applied_on = str(applied_on)[:10]
        cur = conn.execute(
            """UPDATE jobs SET status=?, applied_at=COALESCE(?, applied_at),
                   notes=? WHERE uid LIKE ? AND status <> ?""",
            (status, applied_on, str(values.get("Notes") or "") or None,
             uid + "%", status),
        )
        changed += cur.rowcount
    conn.commit()
    return changed


def update(conn: sqlite3.Connection, path: Path = TRACKER_PATH,
           min_score: float = 0) -> dict:
    existing, order = _read_existing(path)
    synced = _sync_to_db(conn, existing)

    rows = pipeline.shortlist(conn, limit=10000, min_score=min_score)
    by_id = {r["uid"][:8]: r for r in rows}

    new_ids = [uid for uid in by_id if uid not in existing]
    # Highest-scoring first among the newcomers, appended below what's there.
    new_ids.sort(key=lambda u: -(by_id[u]["score"] or 0))

    book = Workbook()
    sheet = book.active
    sheet.title = SHEET

    for index, (name, width) in enumerate(COLUMNS, 1):
        cell = sheet.cell(row=1, column=index, value=name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
        sheet.column_dimensions[get_column_letter(index)].width = width

    def write(row_no: int, uid: str, saved: dict | None) -> None:
        job = by_id.get(uid)
        saved = saved or {}
        # first_seen from the database, so a row added to this file today
        # still shows the day the pipeline actually found it.
        discovered = _local_day(job["first_seen"]) if job else None
        sheet.cell(row=row_no, column=COL["Date added"],
                   value=saved.get("Date added") or discovered
                   or date.today().isoformat())
        for name in EDITABLE:
            sheet.cell(row=row_no, column=COL[name], value=saved.get(name))
        if job:
            sheet.cell(row=row_no, column=COL["Score"], value=round(job["score"] or 0))
            sheet.cell(row=row_no, column=COL["Company"], value=job["company"])
            sheet.cell(row=row_no, column=COL["Title"], value=job["title"])
            sheet.cell(row=row_no, column=COL["Location"],
                       value=(job["location"] or "")[:90])
            sheet.cell(row=row_no, column=COL["Type"], value=job["bucket"])
            sheet.cell(row=row_no, column=COL["H-1B"],
                       value=job.get("h1b_approvals") or 0)
            sheet.cell(row=row_no, column=COL["Remote"],
                       value="yes" if job["remote"] else "")
            # One row per role; this says how many locations it was posted in,
            # so a "1" is not mistaken for the whole picture.
            sheet.cell(row=row_no, column=COL["Locs"],
                       value=job.get("duplicate_count", 1))
            link = sheet.cell(row=row_no, column=COL["Link"],
                              value=(job["url"] or "")[:250])
            if job["url"]:
                link.hyperlink = job["url"]
                link.font = Font(color="1F6FEB", underline="single", size=10)
        else:
            # Posting has closed, but the row stays — it may be one you applied to.
            sheet.cell(row=row_no, column=COL["Company"], value="(posting closed)")
        sheet.cell(row=row_no, column=ID_COL, value=uid)
        for name in EDITABLE:
            sheet.cell(row=row_no, column=COL[name]).fill = MINE_FILL

    line = 2
    for uid in order:                      # keep your existing rows in place
        write(line, uid, existing[uid])
        line += 1
    for uid in new_ids:                    # newcomers appended at the bottom
        write(line, uid, None)
        line += 1

    last = line - 1
    sheet.freeze_panes = "E2"              # your columns stay visible
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(last, 1)}"

    validation = DataValidation(
        type="list", formula1='"' + ",".join(STATUSES[1:]) + '"', allow_blank=True
    )
    sheet.add_data_validation(validation)
    validation.add(f"B2:B{max(last, 2)}")

    score_col = get_column_letter(COL["Score"])
    sheet.conditional_formatting.add(
        f"{score_col}2:{score_col}{max(last, 2)}",
        CellIsRule(operator="greaterThanOrEqual", formula=["70"], fill=HOT),
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    return {
        "path": path,
        "total": last - 1,
        "added": len(new_ids),
        "synced": synced,
        "kept": len(order),
    }
