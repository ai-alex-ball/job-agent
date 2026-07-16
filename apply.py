"""
apply.py — Phase 3 application email sender

Called by approvals.py when the user clicks APPROVE in the digest email.
Extracts a target email from the job listing, sends the cover letter as the
email body, and attaches the generated CV and cover letter .docx files.
"""

import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

import json

from config import (
    GMAIL_USER,
    GMAIL_APP_PASSWORD,
    DEFAULT_APPLICATION_EMAIL,
    BASE_DIR,
    PROFILE_PATH,
)

# Matches most valid email addresses in free text
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Addresses that are never suitable for job applications
_SKIP_PATTERNS = (
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "notifications@", "unsubscribe@", "support@", "info@reed",
    "jobs@reed", "@lever.co", "@greenhouse.io", "@workday.com",
)


def extract_application_email(text: str) -> str | None:
    """Return the first plausible application email found in job description text."""
    for match in _EMAIL_RE.finditer(text or ""):
        email = match.group().lower()
        if not any(p in email for p in _SKIP_PATTERNS):
            return match.group()
    return None


def send_application(job: dict) -> tuple[bool, str]:
    """
    Send an application email for the given job.

    Returns:
        (True, email_address)  on success
        (False, error_message) on failure
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return False, "Gmail credentials not configured"

    to_email = (
        extract_application_email(job.get("description", ""))
        or DEFAULT_APPLICATION_EMAIL
    )
    if not to_email:
        return False, "no_email"

    title = job.get("title", "this position")
    try:
        with open(PROFILE_PATH) as fh:
            candidate_name = json.load(fh).get("personal", {}).get("name", "")
    except (FileNotFoundError, json.JSONDecodeError):
        candidate_name = ""

    # ── Build message ────────────────────────────────────────────────────────
    msg = MIMEMultipart()
    msg["Subject"] = f"Application for {title} — {candidate_name}"
    msg["From"] = GMAIL_USER
    msg["To"] = to_email

    # Body: cover letter text with salutation and sign-off
    cover_text = job.get("cover_letter") or ""
    cover_text = re.sub(r"\*\*(.+?)\*\*", r"\1", cover_text)  # strip markdown bold
    if cover_text:
        body = (
            f"Dear Hiring Team,\n\n"
            f"{cover_text.strip()}\n\n"
            f"Yours sincerely,\n{candidate_name}\n\n"
            f"---\nPlease find my CV and cover letter attached."
        )
    else:
        body = (
            f"Dear Hiring Team,\n\n"
            f"Please find my application for {title} attached.\n\n"
            f"Yours sincerely,\n{candidate_name}"
        )
    msg.attach(MIMEText(body, "plain"))

    # ── Attach .docx files ───────────────────────────────────────────────────
    for path_key in ("cv_path", "cover_letter_path"):
        path_str = job.get(path_key)
        if not path_str:
            continue
        path = BASE_DIR / path_str
        if path.exists():
            with open(path, "rb") as fh:
                part = MIMEApplication(fh.read(), Name=path.name)
                part["Content-Disposition"] = f'attachment; filename="{path.name}"'
                msg.attach(part)

    # ── Send ─────────────────────────────────────────────────────────────────
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, to_email, msg.as_string())
        print(f"[Apply] Application sent to {to_email} for: {title} @ {job.get('company')}")
        return True, to_email
    except Exception as exc:
        print(f"[Apply] Send failed: {exc}")
        return False, str(exc)
