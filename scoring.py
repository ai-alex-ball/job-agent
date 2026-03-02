import json
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, PROFILE_PATH, PROMPTS_DIR, DREAM_EMPLOYERS

# Load once at module level
_PROFILE: dict = json.loads(PROFILE_PATH.read_text())
_SYSTEM_PROMPT: str = (PROMPTS_DIR / "00_master_pipeline_prompt.md").read_text()
_CLIENT: anthropic.Anthropic | None = None


def _is_dream_employer(company: str) -> bool:
    """Partial, case-insensitive match against the dream employer list."""
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


def score_job(job: dict) -> dict | None:
    """
    Score a single job against the candidate's profile using the master pipeline prompt.
    Returns the parsed JSON result or None on error.
    """
    user_message = f"""## CANDIDATE PROFILE

{json.dumps(_PROFILE, indent=2)}

---

## JOB TO EVALUATE

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

    try:
        response = _client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw = response.content[0].text.strip()

        # Strip markdown code fences if Claude wraps the JSON
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        # Extract the first complete JSON object — handles trailing commentary
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found in response")
        raw = raw[start:end]

        result = json.loads(raw)

        # Hard gate: role_type_match=false forces reject regardless of score
        scoring = result.get("scoring", {})
        if not scoring.get("role_type_match", True):
            scoring["proceed"] = False
            scoring["rationale"] = "Role type mismatch — not in target categories"
            result["scoring"] = scoring

        # Dream employer flag — computed here, stored by update_score
        result["dream_employer"] = _is_dream_employer(job.get("company", ""))

        return result

    except json.JSONDecodeError as e:
        print(f"[Scoring] JSON parse error for '{job.get('title')}' @ {job.get('company')}: {e}")
        return None
    except Exception as e:
        print(f"[Scoring] Error scoring '{job.get('title')}' @ {job.get('company')}: {e}")
        return None
