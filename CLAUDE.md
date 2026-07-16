# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

An **AI-powered job application agent** — a personal template configured for one job seeker's profile and target roles (see `profile.json`). It fetches jobs from Reed, JSearch, Adzuna, and LinkedIn daily, scores them against the candidate's profile using Claude, stores results in SQLite, and emails an HTML digest of the top matches with one-click APPROVE/SKIP buttons.

The primary data backbone is `profile.json`. The 13 prompt files in `prompts/` drive all AI interactions.

## Commands

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies (required for CV generation via generate_cv.js)
npm install

# Run the full daily pipeline
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

# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_documents.py -v

# Run a single test class or method
python -m pytest tests/test_documents.py::TestCareerAtAGlance -v
python -m pytest tests/test_documents.py::TestParseTailoredCv::test_strips_code_fences -v
```

## Cron Schedule

```
0 8 * * *   python main.py          → logs/cron.log
0 8 * * 0   python weekly_summary.py → logs/weekly.log
```

`approvals.py` is started separately via Windows Task Scheduler → `autostart.sh`.

## Architecture

### Pipeline Flow (`main.py`)

```
init_db → fetch_all_jobs → insert_job (dedupe by URL) → score_job (Claude)
  → generate_documents → send_digest → sync_to_windows → generate_dashboard → send_heartbeat
```

### Module Responsibilities

| File | Purpose |
|------|---------|
| `main.py` | Orchestrator; also `--status`, `--ingest-only`, `--auto-apply` modes |
| `ingestion.py` | Fetches from Reed, JSearch, Adzuna, LinkedIn; applies title pre-filter before Claude |
| `database.py` | SQLite CRUD; `init_db()` handles schema migrations automatically |
| `scoring.py` | Calls Claude with master prompt; parses JSON response; enforces `role_type_match` hard gate |
| `documents.py` | Generates `.docx` CV via `generate_cv.js` (Node) + cover letter via python-docx |
| `digest.py` | Builds HTML email digest; sends via Gmail SMTP SSL; fires instant dream-employer alerts |
| `approvals.py` | Flask webhook — handles APPROVE/SKIP/browser-apply button clicks from digest email |
| `apply.py` | Extracts email from job description text; sends cover letter + `.docx` attachments |
| `browser_apply.py` | Playwright automation for Greenhouse, Lever (supported), Workday/Amazon (detected, unsupported), generic (best-effort) |
| `alerts.py` | Pipeline failure emails + heartbeat; always logs to `logs/errors.log` even without SMTP |
| `weekly_summary.py` | Sunday email: stats, applications sent, manual pending, dream activity, top pending |
| `dashboard.py` | Generates a local HTML dashboard |
| `config.py` | All settings from `.env`; single source of truth for model, thresholds, role lists, employer lists |
| `get_brand_color.py` | Looks up company brand colour for CV accent |
| `generate_cv.js` | Node.js CV renderer using the `docx` npm package; called as a subprocess by `documents.py` |

### Database Schema (`jobs.db`)

Single `jobs` table. Key columns:
- `url TEXT UNIQUE` — primary dedup key (cross-run)
- `status` flow: `new → scored/rejected → documents_generated → digest_sent → approved → applied/skipped/manual_required/browser_applied`
- `score` — Claude's 0–100 integer
- `matched_skills`, `skill_gaps`, `red_flags`, `dimensions` — JSON arrays
- `tailored_cv`, `cover_letter` — full text from Claude (only populated when `score ≥ 75`)
- `approval_token TEXT UNIQUE` — UUID used in digest email button URLs
- `cv_path`, `cover_letter_path` — paths relative to `BASE_DIR`
- `dream_employer INTEGER` — set by `scoring.py`, not by Claude

`init_db()` performs additive `ALTER TABLE` migrations so it is safe to run on existing databases.

### Scoring & Threshold Logic

- `MIN_SCORE_THRESHOLD = 75` — jobs below this are `rejected`; no documents generated
- `role_type_match = false` in Claude's JSON → hard reject regardless of score (enforced in `scoring.py`, not the prompt)
- `dream_employer` flag is computed in Python (`_is_dream_employer`) and triggers an instant email alert via `send_dream_alert()`
- Dream employer jobs with `score ≥ DREAM_EMPLOYER_MIN_SCORE (60)` appear in the digest even if rejected
- `MAX_JOBS_PER_RUN = 30` caps daily Claude API spend (~$0.014/job on sonnet-4-6)

### Document Generation

CV rendering has a two-layer architecture:
1. `documents.py` (`_extract_cv_content`) serialises profile + Claude's structured `tailored_cv` JSON into a plain dict
2. `generate_cv.js` receives that dict via stdin and renders the styled `.docx` using the npm `docx` library

The `tailored_cv` field from Claude is expected to be a JSON object with `roles`, `projects`, `summary`, and optionally `skills`. `_parse_tailored_cv()` handles code-fence stripping and gracefully falls back to profile bullets if the field is plain text or absent.

### Ingestion Pre-Filter

Before hitting Claude, `ingestion.py` drops jobs using two keyword lists in `config.py`:
- `TITLE_INCLUDE_KEYWORDS` — title must match at least one (cuts ~80% of API calls)
- `TITLE_EXCLUDE_KEYWORDS` — hard-reject terms (clinical, legal, construction, etc.)

### LinkedIn Ingestion

LinkedIn is fetched via a local MCP server at `~/linkedin-mcp-server`. The integration uses a custom JSON-RPC handshake (`asyncio` subprocess) and a bespoke parser (`_parse_linkedin_results`) to extract job cards from LinkedIn's innerText format. If the MCP server directory doesn't exist, LinkedIn ingestion is silently skipped.

## Prompt Architecture

**`prompts/00_master_pipeline_prompt.md`** is the only prompt called by the automated pipeline. It returns a single JSON object:

```json
{
  "job_id", "job_title", "company",
  "scoring": {
    "overall_score": 0–100,
    "role_type_match": true/false,
    "matched_skills": [],
    "skill_gaps": [],
    "red_flags": [],
    "dimensions": {},
    "rationale": "",
    "proceed": true/false
  },
  "tailored_cv": "JSON string or null",
  "cover_letter": "string or null"
}
```

`proceed` is only `true` when `overall_score ≥ 75`. Prompts `01`, `03`, `05` are embedded inside the master prompt; the standalone versions are reference copies only.

## API Keys Required

Four external services (all via `.env`):
- `ANTHROPIC_API_KEY` — Claude scoring
- `REED_API_KEY` — basic auth; password is always empty
- `JSEARCH_API_KEY` — RapidAPI key; free tier = 200 req/month (6 roles × 30 days = 180)
- `ADZUNA_APP_ID` + `ADZUNA_APP_KEY`
- `GMAIL_USER` + `GMAIL_APP_PASSWORD` — requires a Gmail App Password, not account password
- `APPROVAL_BASE_URL` — must point to where `approvals.py` is reachable from your email client (default: `http://localhost:5000`)

## Working in This Repo

**Updating prompts:** maintain the pattern — persona → task → output format → data placeholder. Placeholders use `[THIS SECTION IS AUTO-POPULATED FROM ... AT RUNTIME]`.

**Updating `profile.json`:** keep `key_metrics` in sync with `career_history` (metrics are derived from roles, not stored independently).

**`master_cv.docx`** is a binary reference file — do not edit programmatically.

**Documents sync to Windows** at `/mnt/c/Users/Public/Documents/JobAgent` after each pipeline run (WSL environment).
