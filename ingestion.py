import asyncio
import json
import re
from pathlib import Path
from urllib.parse import quote_plus

import requests

from config import (
    REED_API_KEY,
    JSEARCH_API_KEY,
    TARGET_ROLES,
    LOCATION,
    REED_DISTANCE_MILES,
    RESULTS_PER_QUERY,
    TITLE_INCLUDE_KEYWORDS,
    TITLE_EXCLUDE_KEYWORDS,
)

LINKEDIN_MCP_DIR = Path.home() / "linkedin-mcp-server"


# ---------------------------------------------------------------------------
# Reed API
# ---------------------------------------------------------------------------

def fetch_reed_jobs() -> list[dict]:
    if not REED_API_KEY:
        print("[Reed] REED_API_KEY not set — skipping")
        return []

    jobs = []
    base_url = "https://www.reed.co.uk/api/1.0/search"

    for role in TARGET_ROLES:
        try:
            resp = requests.get(
                base_url,
                auth=(REED_API_KEY, ""),
                params={
                    "keywords": role,
                    "location": LOCATION,
                    "distancefromlocation": REED_DISTANCE_MILES,
                    "resultsToTake": RESULTS_PER_QUERY,
                    "minimumSalary": 60000,  # broad filter to reduce noise
                },
                timeout=15,
            )
            resp.raise_for_status()
            for item in resp.json().get("results", []):
                jobs.append(_normalize_reed(item))
        except Exception as e:
            print(f"[Reed] Error fetching '{role}': {e}")

    return jobs


def _normalize_reed(item: dict) -> dict:
    return {
        "job_id": str(item.get("jobId", "")),
        "platform": "reed",
        "title": item.get("jobTitle", ""),
        "company": item.get("employerName", ""),
        "location": item.get("locationName", ""),
        "salary_min": item.get("minimumSalary"),
        "salary_max": item.get("maximumSalary"),
        "salary_currency": "GBP",
        "description": item.get("jobDescription", ""),
        "url": item.get("jobUrl", ""),
        "date_posted": item.get("date", ""),
    }


# ---------------------------------------------------------------------------
# JSearch API (via RapidAPI)
# ---------------------------------------------------------------------------

def fetch_jsearch_jobs() -> list[dict]:
    if not JSEARCH_API_KEY:
        print("[JSearch] JSEARCH_API_KEY not set — skipping")
        return []

    jobs = []
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": JSEARCH_API_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }

    for role in TARGET_ROLES:
        try:
            resp = requests.get(
                url,
                headers=headers,
                params={
                    "query": f"{role} {LOCATION} UK",
                    "num_pages": "1",
                    "date_posted": "today",
                    "country": "GB",
                },
                timeout=15,
            )
            resp.raise_for_status()
            for item in resp.json().get("data", []):
                jobs.append(_normalize_jsearch(item))
        except Exception as e:
            print(f"[JSearch] Error fetching '{role}': {e}")

    return jobs


def _normalize_jsearch(item: dict) -> dict:
    url = item.get("job_apply_link") or item.get("job_google_link", "")
    return {
        "job_id": item.get("job_id", ""),
        "platform": "jsearch",
        "title": item.get("job_title", ""),
        "company": item.get("employer_name", ""),
        "location": item.get("job_city") or item.get("job_state", ""),
        "salary_min": item.get("job_min_salary"),
        "salary_max": item.get("job_max_salary"),
        "salary_currency": item.get("job_salary_currency", "GBP"),
        "description": item.get("job_description", ""),
        "url": url,
        "date_posted": item.get("job_posted_at_datetime_utc", ""),
    }


# ---------------------------------------------------------------------------
# LinkedIn via MCP server
# ---------------------------------------------------------------------------

# Matches the work-type suffix LinkedIn appends to every location line
_WORK_TYPE_RE = re.compile(
    r"\s*\((Hybrid|Remote|On-?site|Contract|Temporary|Full-?time|Part-?time)\)\s*$",
    re.IGNORECASE,
)
# Strip "with verification" duplicate suffix from repeated title lines
_VERIF_SUFFIX = re.compile(r"\s+with verification$", re.IGNORECASE)
# Header / UI chrome to discard when seen as a title candidate
_TITLE_NOISE = re.compile(
    r"^(\d[\d,]*\+?\s+results?|set (job )?alert|jump to active|sign in|join now|"
    r"easy apply|promoted.*|save.*|share|show more options|promoted by hirer|"
    r"responses managed|matches your|assessing your|follow|\d+)$",
    re.IGNORECASE,
)


def _parse_linkedin_results(raw: str, search_url: str) -> list[dict]:
    """
    Parse the compact job-card list from a LinkedIn search innerText.

    LinkedIn renders each card in the left-hand list as exactly 3–4 lines:
        Title
        Title [with verification]   ← same title, sometimes with suffix
        Company
        Location, Country (WorkType)

    A second "detail pane" section follows, starting with the sequence
    '<number>\\nCompany\\nShare\\nShow more options'. We truncate there.
    """
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    # Truncate at the start of the right-hand detail pane
    compact: list[str] = []
    for k, line in enumerate(lines):
        if line == "Share" and k + 1 < len(lines) and lines[k + 1] == "Show more options":
            break
        compact.append(line)

    jobs: list[dict] = []
    seen_titles: set[str] = set()

    for i, line in enumerate(compact):
        # Location lines are our reliable anchors
        if not _WORK_TYPE_RE.search(line):
            continue

        location = _WORK_TYPE_RE.sub("", line).strip().rstrip(",").strip()

        # Work backwards: look at the 3 lines before this location line
        # to determine title and company.
        if i < 2:
            continue

        prev1 = compact[i - 1]  # almost always Company
        prev2 = compact[i - 2]  # title OR title-repeated

        # Detect the 4-line pattern: if prev3 == prev2 (ignoring " with verification")
        # then prev2 is the duplicate title line and prev1 is the company.
        if i >= 3:
            prev3 = compact[i - 3]
            clean3 = _VERIF_SUFFIX.sub("", prev3).strip()
            clean2 = _VERIF_SUFFIX.sub("", prev2).strip()
            if clean3.lower() == clean2.lower():
                # 4-line card: title / title+verif / company / location
                title   = clean3
                company = prev1
            else:
                # 3-line card: title / company / location
                title   = _VERIF_SUFFIX.sub("", prev2).strip()
                company = prev1
        else:
            title   = _VERIF_SUFFIX.sub("", prev2).strip()
            company = prev1

        if len(title) < 5 or _TITLE_NOISE.match(title):
            continue

        key = (title.lower(), company.lower())
        if key in seen_titles:
            continue
        seen_titles.add(key)

        jobs.append({
            "title":      title,
            "company":    company,
            "location":   location or LOCATION,
            "search_url": search_url,
        })

    return jobs


def _normalize_linkedin(raw: dict) -> dict:
    title   = raw["title"]
    company = raw["company"]
    # Stable pseudo-URL used as the deduplication key (no real job ID available)
    url = (
        "https://www.linkedin.com/jobs/view/"
        f"?title={quote_plus(title)}&company={quote_plus(company)}"
    )
    desc = (
        f"LinkedIn listing: {title} at {company}, {raw.get('location', '')}. "
        f"Source: {raw.get('search_url', '')}"
    )
    return {
        "job_id":          f"li_{quote_plus(title[:24])}_{quote_plus(company[:24])}",
        "platform":        "linkedin",
        "title":           title,
        "company":         company,
        "location":        raw.get("location", ""),
        "salary_min":      None,
        "salary_max":      None,
        "salary_currency": "GBP",
        "description":     desc,
        "url":             url,
        "date_posted":     "",
    }


async def _run_linkedin_searches(roles: list[str], location: str) -> list[dict]:
    """
    Spawn one LinkedIn MCP server subprocess and run all role searches through it.
    Browser startup is expensive (~15 s) so we amortise it across all queries.
    """
    cmd = [
        "uv", "run",
        "--directory", str(LINKEDIN_MCP_DIR),
        "-m", "linkedin_mcp_server",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"[LinkedIn] Failed to start MCP server: {e}")
        return []

    async def send(msg: dict) -> None:
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        await proc.stdin.drain()

    async def recv(timeout: float = 30.0) -> dict:
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
        return json.loads(line.decode())

    raw_jobs: list[dict] = []
    msg_id = 0

    try:
        # ── Handshake ──────────────────────────────────────────────────────────
        await send({
            "jsonrpc": "2.0", "id": msg_id, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "job-agent", "version": "1.0"},
            },
        })
        await recv(timeout=30)  # initialize response (discard)

        # notifications/initialized has no id — server sends no response
        await send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        # ── Search each role ───────────────────────────────────────────────────
        for role in roles:
            msg_id += 1
            search_url = (
                "https://www.linkedin.com/jobs/search/"
                f"?keywords={quote_plus(role)}&location={quote_plus(location)}"
            )
            await send({
                "jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
                "params": {
                    "name": "search_jobs",
                    "arguments": {"keywords": role, "location": location},
                },
            })

            try:
                resp = await recv(timeout=90)  # browser navigation can be slow
            except asyncio.TimeoutError:
                print(f"[LinkedIn] Timeout for role '{role}' — skipping")
                continue
            except json.JSONDecodeError as e:
                print(f"[LinkedIn] Bad JSON for role '{role}': {e}")
                continue

            # RPC-level error
            if "error" in resp:
                print(f"[LinkedIn] RPC error for '{role}': {resp['error']}")
                continue

            # Extract text content
            content = resp.get("result", {}).get("content", [])
            text_item = next((c for c in content if c.get("type") == "text"), None)
            if not text_item:
                continue

            # The text is a JSON-encoded payload from the tool
            try:
                payload = json.loads(text_item["text"])
            except json.JSONDecodeError:
                # Plain text error message
                print(f"[LinkedIn] Non-JSON tool response for '{role}': {text_item['text'][:120]}")
                continue

            if isinstance(payload, dict) and "error" in payload:
                print(f"[LinkedIn] Tool error for '{role}': {payload.get('message', payload['error'])}")
                continue

            raw_text = payload.get("sections", {}).get("search_results", "")
            if not raw_text:
                print(f"[LinkedIn] No search_results text for role '{role}'")
                continue

            found = _parse_linkedin_results(raw_text, search_url)
            print(f"[LinkedIn] '{role}': {len(found)} jobs parsed")
            raw_jobs.extend(found)

    except Exception as e:
        print(f"[LinkedIn] Unexpected error: {e}")

    finally:
        try:
            proc.stdin.close()
            await asyncio.wait_for(proc.wait(), timeout=5)
        except Exception:
            proc.kill()

    return raw_jobs


def fetch_linkedin_jobs() -> list[dict]:
    if not LINKEDIN_MCP_DIR.exists():
        print("[LinkedIn] MCP server not found — skipping")
        return []

    raw = asyncio.run(_run_linkedin_searches(TARGET_ROLES, LOCATION))
    return [_normalize_linkedin(j) for j in raw]


# ---------------------------------------------------------------------------
# Title pre-filter
# ---------------------------------------------------------------------------

def _title_matches(title: str) -> bool:
    """Return True if the job title contains at least one target keyword."""
    lower = title.lower()
    return any(kw in lower for kw in TITLE_INCLUDE_KEYWORDS)


def _title_excluded(title: str) -> bool:
    """Return True if the job title contains a hard-reject red-flag term."""
    lower = title.lower()
    return any(kw in lower for kw in TITLE_EXCLUDE_KEYWORDS)


# ---------------------------------------------------------------------------
# Combined fetch + deduplication + pre-filter
# ---------------------------------------------------------------------------

def fetch_all_jobs() -> list[dict]:
    print("[Ingestion] Fetching from Reed...")
    reed_jobs = fetch_reed_jobs()
    print(f"[Ingestion] Reed: {len(reed_jobs)} jobs fetched")

    print("[Ingestion] Fetching from JSearch...")
    jsearch_jobs = fetch_jsearch_jobs()
    print(f"[Ingestion] JSearch: {len(jsearch_jobs)} jobs fetched")

    print("[Ingestion] Fetching from LinkedIn...")
    linkedin_jobs = fetch_linkedin_jobs()
    print(f"[Ingestion] LinkedIn: {len(linkedin_jobs)} jobs fetched")

    # Deduplicate within this batch by URL
    seen: set[str] = set()
    unique: list[dict] = []
    for job in reed_jobs + jsearch_jobs + linkedin_jobs:
        url = job.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(job)

    # Title pre-filter — drop obvious mismatches before hitting Claude
    before = len(unique)
    unique = [
        j for j in unique
        if _title_matches(j.get("title", "")) and not _title_excluded(j.get("title", ""))
    ]
    print(f"[Ingestion] {len(unique)} jobs after title filter (dropped {before - len(unique)})")

    return unique
