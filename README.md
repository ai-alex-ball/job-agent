# job-agent

An AI-powered job application agent. It fetches jobs daily from Reed, JSearch, Adzuna, and LinkedIn, scores each one against a candidate profile using Claude, generates a tailored CV and cover letter for the strong matches, and emails an HTML digest with one-click APPROVE/SKIP buttons. Approving a job either emails the application directly or, for portal-based ATS systems (Greenhouse, Lever), can be pushed through with Playwright browser automation.

This is a personal template — it's built around one candidate's profile (`profile.json`, gitignored) and one set of target roles, but everything data-driven lives in `profile.json` and `.env`, so it can be reconfigured for a different candidate or role focus.

## Features

- **Multi-source ingestion** — Reed, JSearch (RapidAPI), Adzuna, and LinkedIn (via a local MCP server), deduplicated by URL
- **Title pre-filter** — keyword include/exclude lists in `config.py` cut ~80% of API calls before anything reaches Claude
- **Two-stage AI scoring** — a fast Haiku pre-filter followed by a full Sonnet scoring pass, with prompt caching to control API cost
- **Tailored documents** — a styled `.docx` CV (rendered via a Node.js `docx` renderer) and cover letter generated only for jobs that pass the score threshold
- **HTML digest email** — top matches with APPROVE/SKIP buttons, plus instant alerts for "dream employer" matches
- **Approval webhook** — a Flask server handles the button clicks and either emails the application or flags it for manual/browser-assisted follow-up
- **Browser automation** — Playwright-driven form filling for supported ATS platforms (Greenhouse, Lever), with detection (but no automation) for Workday/Amazon
- **Weekly summary email** — stats, applications sent, manual pending, and dream-employer activity
- **Local dashboard** — a static HTML dashboard of pipeline state

## Prerequisites

- Python 3.10+
- Node.js (for CV rendering via `generate_cv.js`)
- API keys: Anthropic, Reed, JSearch (RapidAPI), Adzuna, and a Gmail account with an [App Password](https://myaccount.google.com/apppasswords)
- (Optional) a local `linkedin-mcp-server` install for LinkedIn ingestion (expected at `~/linkedin-mcp-server`) — if it's not present, LinkedIn ingestion is silently skipped

## Setup

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies (required for CV generation)
npm install

# Configure credentials
cp .env.example .env
# then fill in .env with your API keys — see .env.example for what each one is and where to get it

# Configure your candidate profile
cp profile.example.json profile.json
# then fill in profile.json with your real name, career history, target roles, etc.
```

`profile.json` and `.env` are both gitignored — they hold personal data and secrets and are never committed.

## Usage

```bash
# Run the full daily pipeline (ingest → score → generate documents → digest email)
python main.py

# Check pipeline status and API cost estimate
python main.py --status

# Ingest jobs without scoring (useful for testing ingestion)
python main.py --ingest-only

# Batch-process manual_required jobs via browser automation
python main.py --auto-apply

# Run the approval webhook server (must be running for digest email buttons to work)
python approvals.py

# Send the weekly summary email manually
python weekly_summary.py

# Run the test suite
python -m pytest tests/ -v
```

### Scheduling

The intended cron schedule:

```
0 8 * * *   python main.py           → logs/cron.log
0 8 * * 0   python weekly_summary.py → logs/weekly.log
```

`approvals.py` needs to run continuously (it's the webhook target for the digest email's APPROVE/SKIP links) — see `start.sh` / `autostart.sh` for one way to keep it running.

## Architecture

```
init_db → fetch_all_jobs → insert_job (dedupe by URL) → score_job (Claude)
  → generate_documents → send_digest → generate_dashboard → send_heartbeat
```

| File | Purpose |
|------|---------|
| `main.py` | Orchestrator; also `--status`, `--ingest-only`, `--auto-apply` modes |
| `ingestion.py` | Fetches from Reed, JSearch, Adzuna, LinkedIn; applies title pre-filter before Claude |
| `database.py` | SQLite CRUD; `init_db()` handles schema migrations automatically |
| `scoring.py` | Two-stage Haiku/Sonnet Claude scoring; enforces a `role_type_match` hard gate |
| `documents.py` | Generates the `.docx` CV via `generate_cv.js` (Node) and the cover letter via python-docx |
| `digest.py` | Builds the HTML email digest; sends via Gmail SMTP SSL; fires instant dream-employer alerts |
| `approvals.py` | Flask webhook — handles APPROVE/SKIP/browser-apply button clicks from the digest email |
| `apply.py` | Extracts an email address from the job description and sends the application |
| `browser_apply.py` | Playwright automation for Greenhouse and Lever; detects (but doesn't automate) Workday/Amazon |
| `alerts.py` | Pipeline failure emails and heartbeat |
| `weekly_summary.py` | Sunday email: stats, applications sent, manual pending, dream activity |
| `dashboard.py` | Generates a local HTML dashboard |
| `config.py` | All settings, loaded from `.env` |
| `generate_cv.js` | Node.js CV renderer (uses the `docx` npm package), invoked as a subprocess by `documents.py` |

The scoring/document-generation prompts live in `prompts/`; `prompts/00_master_pipeline_prompt.md` is the only one called by the automated pipeline. See `CLAUDE.md` for a deeper architecture writeup (schema details, prompt conventions, scoring thresholds).

## Notes

- The pipeline was built and is primarily run under WSL; `main.py` includes an optional step that copies generated documents to a Windows-accessible directory (`/mnt/c/Users/Public/Documents/JobAgent`) — this is a no-op convenience for WSL setups and isn't required for the pipeline to work elsewhere, though the sync step itself assumes that path is creatable and may need adjusting (or removing) on non-WSL systems.
- LinkedIn ingestion depends on a separately-run local MCP server; without it, the pipeline still works using Reed, JSearch, and Adzuna.
