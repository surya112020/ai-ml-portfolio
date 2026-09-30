# jobhunt

Polls company career APIs directly, detects postings the moment they appear,
ranks them against a candidate profile, and alerts. Built for a fast,
targeted application loop — not for mass auto-apply.

91 direct boards plus Indeed/LinkedIn via JobSpy. ~18k postings per sweep in
about 2.5 minutes.

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp config/identity.example.yml config/identity.yml   # then fill it in

./.venv/bin/python -m jobhunt poll --notify
./.venv/bin/python -m jobhunt dashboard --open
```

> **The runbook is [CLAUDE.md](CLAUDE.md), not this file.**
> Status, what's due, what every file does, fixed bugs and why, the waitlist,
> and known limits all live there. Read it before changing anything.
