import json
import anthropic
from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_HAIKU_MODEL,
    MIN_SCORE_THRESHOLD, HAIKU_PREFILTER_THRESHOLD,
    PROFILE_PATH, PROMPTS_DIR, DREAM_EMPLOYERS,
)

# Load once at module level
_PROFILE: dict = json.loads(PROFILE_PATH.read_text())
_SYSTEM_PROMPT: str = (PROMPTS_DIR / "00_master_pipeline_prompt.md").read_text()
_SCORING_PROMPT: str = (PROMPTS_DIR / "00_scoring_only_prompt.md").read_text()
_CLIENT: anthropic.Anthropic | None = None

# Pre-rendered stable sections used as cache prefixes.
# Stage 1 (Haiku): scoring prompt + profile merged into one system block (~4,900 tokens).
# Haiku requires ≥4,096 tokens to cache; neither section alone clears that bar,
# but combined they do — so we use a single breakpoint instead of two.
_PROFILE_SECTION = f"## CANDIDATE PROFILE\n\n{json.dumps(_PROFILE, indent=2)}\n\n---\n\n"
_STAGE1_SYSTEM = f"{_SCORING_PROMPT}\n\n{_PROFILE_SECTION}"

_CACHE_HEADER = {"anthropic-beta": "prompt-caching-2024-07-31"}


def _is_dream_employer(company: str) -> bool:
    company_lower = company.lower()
    return any(d.lower() in company_lower or company_lower in d.lower()
               for d in DREAM_EMPLOYERS)


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _CLIENT


def _format_salary(job: dict) -> str:
    lo = job.get("salary_min")
    hi = job.get("salary_max")
    cur = job.get("salary_currency", "GBP")
    if lo and hi:
        return f"{cur} {lo:,} – {hi:,}"
    if lo:
        return f"{cur} {lo:,}+"
    return "Not specified"


def _build_job_section(job: dict) -> str:
    return f"""## JOB TO EVALUATE

Job ID: {job.get('job_id', 'N/A')}
Title: {job.get('title', 'N/A')}
Company: {job.get('company', 'N/A')}
Location: {job.get('location', 'N/A')}
Salary: {_format_salary(job)}
Platform: {job.get('platform', 'N/A')}
URL: {job.get('url', 'N/A')}

Job Description:
{job.get('description', 'No description provided')}
"""


def _log_cache(usage) -> None:
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_created = getattr(usage, "cache_creation_input_tokens", 0) or 0
    if cache_read or cache_created:
        print(f"[Scoring] Cache — read: {cache_read:,} tokens, written: {cache_created:,} tokens")


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in response")
    return json.loads(raw[start:end])


def _stage1_score(job: dict) -> dict | None:
    """Stage 1: Haiku scoring only. Returns parsed result or None on error."""
    try:
        response = _client().messages.create(
            model=CLAUDE_HAIKU_MODEL,
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": _STAGE1_SYSTEM,  # scoring prompt + profile, ~4,900 tokens — above Haiku cache threshold
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": _build_job_section(job)}],
            extra_headers=_CACHE_HEADER,
        )
        _log_cache(response.usage)
        return _parse_json(response.content[0].text)
    except json.JSONDecodeError as e:
        print(f"[Scoring/S1] JSON parse error for '{job.get('title')}' @ {job.get('company')}: {e}")
        return None
    except Exception as e:
        print(f"[Scoring/S1] Error for '{job.get('title')}' @ {job.get('company')}: {e}")
        return None


def _stage2_score(job: dict) -> dict | None:
    """Stage 2: Sonnet full pipeline (scoring + CV + cover letter). Returns parsed result or None."""
    try:
        response = _client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": [
                {
                    "type": "text",
                    "text": _PROFILE_SECTION,
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": _build_job_section(job),
                },
            ]}],
            extra_headers=_CACHE_HEADER,
        )
        _log_cache(response.usage)
        result = _parse_json(response.content[0].text)

        # Hard gate: role_type_match=false forces reject regardless of score
        scoring = result.get("scoring", {})
        if not scoring.get("role_type_match", True):
            scoring["proceed"] = False
            scoring["rationale"] = "Role type mismatch — not in target categories"
            result["scoring"] = scoring

        # Override proceed based on configurable threshold
        overall = scoring.get("overall_score", 0)
        if (scoring.get("proceed") is False
                and scoring.get("role_type_match", True)
                and overall >= MIN_SCORE_THRESHOLD):
            scoring["proceed"] = True
            result["scoring"] = scoring

        result["dream_employer"] = _is_dream_employer(job.get("company", ""))
        return result

    except json.JSONDecodeError as e:
        print(f"[Scoring/S2] JSON parse error for '{job.get('title')}' @ {job.get('company')}: {e}")
        return None
    except Exception as e:
        print(f"[Scoring/S2] Error for '{job.get('title')}' @ {job.get('company')}: {e}")
        return None


def score_job(job: dict) -> dict | None:
    """
    Two-stage pipeline: Haiku pre-filter, then Sonnet for passing jobs.
    Returns the parsed JSON result or None on error.
    """
    # Stage 1: cheap Haiku pre-filter
    s1 = _stage1_score(job)
    if s1 is None:
        return None

    scoring = s1.get("scoring", {})
    overall = scoring.get("overall_score", 0)
    role_match = scoring.get("role_type_match", True)

    if not role_match or overall < HAIKU_PREFILTER_THRESHOLD:
        # Hard reject — no Stage 2 call needed
        if not role_match:
            scoring["rationale"] = "Role type mismatch — not in target categories"
        scoring["proceed"] = False
        result = {
            "scoring": scoring,
            "tailored_cv": None,
            "cover_letter": None,
            "dream_employer": _is_dream_employer(job.get("company", "")),
        }
        print(f"[Scoring] S1 reject  score={overall} role_match={role_match} — '{job.get('title')}' @ {job.get('company')}")
        return result

    print(f"[Scoring] S1 pass score={overall} — running S2 for '{job.get('title')}' @ {job.get('company')}")

    # Stage 2: full Sonnet pipeline (also re-scores with higher accuracy)
    return _stage2_score(job)
