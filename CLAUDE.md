# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

An **AI-powered job application agent** for Jane Doe (Innovation/Programme Director targeting £100k+ roles in AI, fintech, and startups). It fetches jobs from Reed and JSearch daily, scores them against the candidate's profile using Claude, stores results in SQLite, and emails an HTML digest of the top matches.

The primary data source is `profile.json`. The 13 prompt files in `prompts/` drive all AI interactions.

## Running the Agent

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in credentials
cp .env.example .env

# Run the full daily pipeline
python main.py
```

## Python Module Responsibilities

| File | Purpose |
|------|---------|
| `main.py` | Orchestrator — runs init → ingest → score → digest in sequence |
| `ingestion.py` | Fetches jobs from Reed API and JSearch (RapidAPI); normalises to a common dict schema; deduplicates by URL within a batch |
| `database.py` | SQLite CRUD — `jobs` table with status flow: `new → scored/rejected → digest_sent` |
| `scoring.py` | Calls Claude with the master pipeline prompt; parses JSON response; handles markdown code-fence stripping |
| `digest.py` | Builds HTML email digest; sends via Gmail SMTP SSL (port 465); falls back to writing `digest.html` if credentials are missing |
| `config.py` | All settings loaded from `.env` via `python-dotenv`; single source of truth for model name, thresholds, target roles |

## Database Schema

Single table `jobs` in `jobs.db`. Key columns:
- `url TEXT UNIQUE` — primary deduplication key (cross-run)
- `status` — `new` | `scored` | `rejected` | `digest_sent`
- `score` — Claude's 0–100 integer; only jobs ≥75 become `scored`
- `matched_skills`, `skill_gaps`, `red_flags` — stored as JSON arrays
- `tailored_cv`, `cover_letter` — full text from Claude, only populated when `score ≥ 75`

## API Keys Required

See `.env.example`. Three external services:
- **Anthropic** — Claude scoring (`ANTHROPIC_API_KEY`)
- **Reed** (`REED_API_KEY`) — basic auth; password is always empty
- **JSearch via RapidAPI** (`JSEARCH_API_KEY`) — `X-RapidAPI-Key` header
- **Gmail** — requires an App Password, not the account password

## Prompt Architecture

There are three categories of prompts:

**Run once (setup):**
- `02_achievement_quantifier.md` — Transform raw CV bullets into quantified power bullets (run this first)
- `04_professional_summary.md` — Generate professional summary options
- `07_linkedin_optimizer.md` — LinkedIn profile rewrite
- `09_executive_brand.md`, `10_career_pivot.md`, `12_career_portfolio.md` — Optional positioning work

**Run per application (daily pipeline):**
- `00_master_pipeline_prompt.md` — The core agent: takes a job description, returns a single JSON object containing job fit score, tailored CV, and cover letter. Prompts 01, 03, and 05 are embedded in this master prompt; reference-only versions exist as standalone files.

**Run on demand (event-triggered):**
- `06_salary_negotiation.md` — When an offer is received
- `08_behavioral_interview.md` — When an interview is confirmed
- `11_case_study_prep.md` — For finance/strategy/consulting interviews

## Master Pipeline Output Schema

`00_master_pipeline_prompt.md` returns this JSON structure:

```json
{
  "job_id": "string",
  "job_title": "string",
  "company": "string",
  "scoring": {
    "overall_score": 0,
    "matched_skills": [],
    "skill_gaps": [],
    "red_flags": [],
    "rationale": "string",
    "proceed": false
  },
  "tailored_cv": "string or null",
  "cover_letter": "string or null"
}
```

`proceed` is `true` only when `overall_score >= 75`. `tailored_cv` and `cover_letter` are `null` when `proceed = false`.

## profile.json Structure

The candidate profile is the data backbone injected into every prompt. Key sections:
- `personal_info` — Contact, location, availability
- `career_preferences` — Target salary (£100k+), industries, role types, work modes
- `career_history` — 9 roles spanning 2002–present (23 years)
- `key_metrics` — Headline numbers (88 startups incubated, £12m+ raised, 200+ startups mentored)
- `skills` — Grouped by category (programme leadership, venture, innovation, technology, AI)
- `cover_letter_context` — Unique value propositions and positioning statements
- `ai_safety_views` — Candidate's stance on responsible AI (relevant for Anthropic-aligned roles)

## Working in This Repo

When updating prompts, maintain the existing structure: persona introduction → task specification → output format → data placeholder. Placeholders use the pattern `[THIS SECTION IS AUTO-POPULATED FROM ... AT RUNTIME]`.

When updating `profile.json`, keep the key metrics section in sync with career history (metrics are derived from roles, not stored separately).

The `master_cv.docx` is a binary file — do not attempt to edit it programmatically.
