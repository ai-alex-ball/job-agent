"""
browser_apply.py — Phase 4 browser automation for portal-based job applications.

Supports: Greenhouse, Lever (full); Workday (detected, unsupported); Generic (best-effort).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from config import BASE_DIR, PROFILE_PATH, PLAYWRIGHT_HEADLESS, SCREENSHOTS_DIR


# ---------------------------------------------------------------------------
# Portal detection
# ---------------------------------------------------------------------------

_PORTAL_PATTERNS: list[tuple[str, list[str]]] = [
    ("greenhouse", ["greenhouse.io"]),
    ("lever",      ["lever.co"]),
    ("workday",    ["myworkday.com", "workdayjobs.com"]),
]


def detect_portal(url: str | None) -> str:
    """Return the ATS portal name for a job URL, or 'generic'."""
    if not url:
        return "generic"
    url_lower = url.lower()
    for portal, patterns in _PORTAL_PATTERNS:
        if any(p in url_lower for p in patterns):
            return portal
    return "generic"
