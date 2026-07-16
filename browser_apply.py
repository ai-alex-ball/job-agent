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
    ("amazon",     ["jobs.amazon.com", "amazon.jobs", "aws.amazon", "amazon.com/jobs"]),
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

        if portal in ("workday", "amazon"):
            return False, f"unsupported: {portal.capitalize()} requires manual application via listing"

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
                    nav_timeout = 45_000 if portal == "generic" else 30_000
                    page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout)

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
        """Fill a standard Greenhouse application form."""
        try:
            page.wait_for_selector("input#first_name", timeout=15_000)
        except Exception:
            return False, "Greenhouse form fields not found — page may require login or have changed"

        # Required text fields
        page.locator("input#first_name").fill(self.profile["first_name"])
        page.locator("input#last_name").fill(self.profile["last_name"])
        page.locator("input#email").fill(self.profile["email"])
        page.locator("input#phone").fill(self.profile["phone"])

        # Resume upload (only if cv_path is set and file exists)
        cv_path = job.get("cv_path")
        if cv_path and page.locator('input[type="file"]').count():
            full_path = BASE_DIR / cv_path
            if full_path.exists():
                page.locator('input[type="file"]').set_input_files(str(full_path))

        # Cover letter textarea (first one on page)
        cover = job.get("cover_letter") or ""
        if cover and page.locator("textarea").count():
            page.locator("textarea").first.fill(cover)

        # LinkedIn field
        linkedin_loc = page.locator("input[aria-label*='LinkedIn'], input[placeholder*='LinkedIn']")
        if linkedin_loc.count():
            linkedin_loc.first.fill(self.profile["linkedin"])

        # --- Confirmation before submit ---
        print(f"\n[BrowserApply] About to submit Greenhouse application:")
        print(f"  Job   : {job.get('title')} at {job.get('company')}")
        print(f"  URL   : {job.get('url')}")
        print(f"  Name  : {self.profile['first_name']} {self.profile['last_name']}")
        print(f"  Email : {self.profile['email']}")
        print(f"  CV    : {cv_path or '(none)'}")
        answer = input("\nSubmit this application? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            return False, "cancelled by user"

        # Submit
        submit = page.locator('input[type="submit"]')
        if submit.count():
            submit.click()
        else:
            page.locator('button[type="submit"]').click()

        page.wait_for_load_state("networkidle", timeout=15_000)
        return True, "Applied via Greenhouse form"

    def _apply_lever(self, page: Page, job: dict) -> tuple[bool, str]:
        """Fill a standard Lever application form."""
        try:
            page.wait_for_selector('input[name="name"]', timeout=15_000)
        except Exception:
            return False, "Lever form fields not found"

        page.locator('input[name="name"]').fill(self.profile["name"])
        page.locator('input[name="email"]').fill(self.profile["email"])
        page.locator('input[name="phone"]').fill(self.profile["phone"])
        page.locator('input[name="urls[LinkedIn]"]').fill(self.profile["linkedin"])

        # Current organisation (optional on some Lever forms)
        org_loc = page.locator('input[name="org"]')
        if org_loc.count():
            org_loc.fill("Independent / Open to Opportunities")

        # Resume upload
        cv_path = job.get("cv_path")
        if cv_path:
            full_path = BASE_DIR / cv_path
            if full_path.exists() and page.locator('input[type="file"]').count():
                page.locator('input[type="file"]').set_input_files(str(full_path))

        # Cover letter
        cover = job.get("cover_letter") or ""
        if cover:
            page.locator('textarea[name="comments"]').fill(cover)

        # --- Confirmation before submit ---
        print(f"\n[BrowserApply] About to submit Lever application:")
        print(f"  Job      : {job.get('title')} at {job.get('company')}")
        print(f"  URL      : {job.get('url')}")
        print(f"  Name     : {self.profile['name']}")
        print(f"  Email    : {self.profile['email']}")
        print(f"  LinkedIn : {self.profile['linkedin']}")
        print(f"  CV       : {cv_path or '(none)'}")
        print(f"  Cover    : {'yes' if cover else '(none)'}")
        answer = input("\nSubmit this application? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            return False, "cancelled by user"

        page.locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle", timeout=15_000)
        return True, "Applied via Lever form"

    def _apply_generic(self, page: Page, job: dict) -> tuple[bool, str]:
        """
        Best-effort filler for unknown portal types.
        Always returns (False, ...) — never claims full success.
        User must verify the application was submitted correctly.
        """
        filled: list[str] = []

        if page.locator('input[type="email"]').count():
            page.locator('input[type="email"]').fill(self.profile["email"])
            filled.append("email")

        for name_sel in (
            'input[placeholder*="name" i]',
            'input[aria-label*="name" i]',
            'input[name*="name" i]',
        ):
            if page.locator(name_sel).count():
                page.locator(name_sel).first.fill(self.profile["name"])
                filled.append("name")
                break

        cv_path = job.get("cv_path")
        if cv_path and page.locator('input[type="file"]').count():
            full_path = BASE_DIR / cv_path
            if full_path.exists():
                page.locator('input[type="file"]').set_input_files(str(full_path))
                filled.append("resume")

        filled_summary = ", ".join(filled) if filled else "nothing"

        # --- Confirmation before submit attempt ---
        print(f"\n[BrowserApply] Generic form — partial fill for:")
        print(f"  Job    : {job.get('title')} at {job.get('company')}")
        print(f"  URL    : {job.get('url')}")
        print(f"  Filled : {filled_summary}")
        print(f"  NOTE   : Generic filler cannot guarantee completeness.")
        print(f"           Please verify the application on the listing after submission.")
        answer = input("\nAttempt submit anyway? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            return False, "cancelled by user"

        # Best-effort submit click
        for submit_sel in ('button[type="submit"]', 'input[type="submit"]'):
            submit_loc = page.locator(submit_sel)
            if submit_loc.count():
                submit_loc.click()
                break

        return False, f"partial fill via generic filler: {filled_summary} — verify on listing"
