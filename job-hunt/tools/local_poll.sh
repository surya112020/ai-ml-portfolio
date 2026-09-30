#!/bin/bash
# Local refresh, driven by launchd every 30 minutes while the Mac is awake.
#
# This is the ONLY thing that updates data/tracker.xlsx. CI runs in the cloud
# against a throwaway database and never touches the spreadsheet, because the
# Status/Notes columns are hand-edited and a cloud job overwriting them would
# destroy work. So the tracker refreshes here or not at all.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p logs
exec >>"logs/poll.log" 2>&1
echo "--- $(date '+%Y-%m-%d %H:%M:%S') ---"

# Skip while the workbook is open in Excel — openpyxl would read a file
# mid-save, and the rewrite would race whatever is being typed.
if ls data/~\$tracker.xlsx >/dev/null 2>&1; then
  echo "tracker.xlsx is open in Excel; skipping this run"
else
  ./.venv/bin/python -m jobhunt poll --notify --top 10 --min-score 70
  ./.venv/bin/python -m jobhunt tracker
  ./.venv/bin/python -m jobhunt dashboard --min 55
fi

# Keep the log from growing without bound.
if [ "$(wc -l < logs/poll.log)" -gt 5000 ]; then
  tail -2000 logs/poll.log > logs/poll.log.tmp && mv logs/poll.log.tmp logs/poll.log
fi
