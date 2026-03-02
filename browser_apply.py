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


# ---------------------------------------------------------------------------
# BrowserApplier
# ---------------------------------------------------------------------------

from playwright.sync_api import sync_playwright, Page, BrowserContext


class BrowserApplier:
    """Fills and submits job application forms via Playwright."""

    def __init__(self):
        self.profile = self._load_profile()
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Profile helpers
    # ------------------------------------------------------------------

    def _load_profile(self) -> dict:
        raw = json.loads(PROFILE_PATH.read_text())
        personal = raw.get("personal", {})
        name = personal.get("name", "")
        parts = name.split(None, 1)
        return {
            "name":       name,
            "first_name": parts[0] if parts else "",
            "last_name":  parts[1] if len(parts) > 1 else "",
            "email":      personal.get("email", ""),
            "phone":      personal.get("phone", ""),
            "linkedin":   personal.get("linkedin", ""),
            "location":   personal.get("location", ""),
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def apply(self, job: dict) -> tuple[bool, str]:
        """
        Attempt to fill and submit the application form for a job.

        Returns:
            (True, "Applied successfully")  on success
            (False, reason_string)          on failure or unsupported portal
        """
        url = job.get("url", "")
        portal = detect_portal(url)

        if portal == "workday":
            return False, "unsupported: Workday requires manual application"

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
                context = browser.new_context(
                    accept_downloads=True,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/134.0.0.0 Safari/537.36"
                    ),
                )
                try:
                    page = context.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)

                    if portal == "greenhouse":
                        success, msg = self._apply_greenhouse(page, job)
                    elif portal == "lever":
                        success, msg = self._apply_lever(page, job)
                    else:
                        success, msg = self._apply_generic(page, job)

                    if not success:
                        self._screenshot(page, job)

                    return success, msg
                finally:
                    context.close()
                    browser.close()

        except Exception as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # Screenshot helper
    # ------------------------------------------------------------------

    def _screenshot(self, page: Page, job: dict):
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_company = re.sub(r"[^\w]", "_", job.get("company", "unknown"))[:24]
        path = SCREENSHOTS_DIR / f"{safe_company}_{ts}.png"
        try:
            page.screenshot(path=str(path))
            print(f"[BrowserApply] Screenshot saved: {path.name}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Portal-specific fillers (stubs — implemented in subsequent tasks)
    # ------------------------------------------------------------------

    def _apply_greenhouse(self, page: Page, job: dict) -> tuple[bool, str]:
        raise NotImplementedError

    def _apply_lever(self, page: Page, job: dict) -> tuple[bool, str]:
        raise NotImplementedError

    def _apply_generic(self, page: Page, job: dict) -> tuple[bool, str]:
        raise NotImplementedError
