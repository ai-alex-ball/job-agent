import json
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import (
    GMAIL_USER,
    GMAIL_APP_PASSWORD,
    DIGEST_RECIPIENT,
    DREAM_ALERT_RECIPIENT,
    APPROVAL_BASE_URL,
)
from database import get_applied_jobs_today


def _format_salary(job: dict) -> str:
    lo = job.get("salary_min")
    hi = job.get("salary_max")
    if lo and hi:
        return f"£{lo:,} – £{hi:,}"
    if lo:
        return f"£{lo:,}+"
    return "Not disclosed"


def _score_color(score: int) -> str:
    if score >= 90:
        return "#16a34a"  # green
    if score >= 80:
        return "#2563eb"  # blue
    return "#d97706"      # amber


def _pill(text: str, bg: str, fg: str) -> str:
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;'
        f'border-radius:12px;font-size:12px;margin:2px;display:inline-block">'
        f"{text}</span>"
    )


def _action_buttons(job: dict) -> str:
    """Render APPROVE / SKIP buttons, or a status badge for already-actioned jobs."""
    status = job.get("status", "")
    token = job.get("approval_token", "")

    if status == "applied":
        email = job.get("application_email_used", "")
        return (
            f'<div style="margin-top:16px;padding:12px;background:#f0fdf4;'
            f'border:1px solid #bbf7d0;border-radius:8px;font-size:13px;color:#15803d">'
            f'<strong>✓ Application sent</strong>'
            f'{" to " + email if email else ""}'
            f"</div>"
        )

    if status == "skipped":
        return (
            '<div style="margin-top:16px;padding:10px;background:#f9fafb;'
            'border:1px solid #e5e7eb;border-radius:8px;font-size:13px;color:#6b7280">'
            "⊘ Skipped"
            "</div>"
        )

    if status == "manual_required":
        url = job.get("url", "#")
        return (
            f'<div style="margin-top:16px;padding:12px;background:#fffbeb;'
            f'border:1px solid #fde68a;border-radius:8px;font-size:13px;color:#92400e">'
            f'📋 <strong>Manual application required</strong> — no email found in listing. '
            f'<a href="{url}" target="_blank" style="color:#92400e;font-weight:600">Apply via listing &rarr;</a>'
            f"</div>"
        )

    if not token:
        return ""

    approve_url = f"{APPROVAL_BASE_URL}/approve/{token}"
    skip_url = f"{APPROVAL_BASE_URL}/skip/{token}"

    return f"""<div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
  <a href="{approve_url}"
     style="background:#16a34a;color:#fff;padding:10px 22px;border-radius:8px;
            text-decoration:none;font-size:14px;font-weight:600">
    Approve &amp; Apply &rarr;
  </a>
  <a href="{skip_url}"
     style="background:#f3f4f6;color:#374151;padding:10px 22px;border-radius:8px;
            text-decoration:none;font-size:14px;font-weight:600;
            border:1px solid #e5e7eb">
    Skip
  </a>
  <a href="{job.get('url','#')}"
     style="background:#f3f4f6;color:#6b7280;padding:10px 22px;border-radius:8px;
            text-decoration:none;font-size:14px;
            border:1px solid #e5e7eb">
    View listing &rarr;
  </a>
</div>"""


def _job_card(job: dict) -> str:
    score = job.get("score", 0)
    matched = json.loads(job.get("matched_skills") or "[]")
    gaps = json.loads(job.get("skill_gaps") or "[]")
    flags = json.loads(job.get("red_flags") or "[]")

    cover = job.get("cover_letter") or ""
    cover_snippet = (cover[:600] + "…") if len(cover) > 600 else cover

    matched_html = "".join(_pill(s, "#dcfce7", "#15803d") for s in matched[:6])
    gaps_html = "".join(_pill(s, "#fef3c7", "#92400e") for s in gaps[:4])
    flags_html = "".join(_pill(f, "#fee2e2", "#991b1b") for f in flags)

    gaps_row = (
        f'<div style="margin-bottom:8px"><strong>Gaps:</strong> {gaps_html}</div>'
        if gaps else ""
    )
    flags_row = (
        f'<div style="margin-top:8px"><strong>Red flags:</strong> {flags_html}</div>'
        if flags else ""
    )

    cv_path = job.get("cv_path")
    cl_path = job.get("cover_letter_path")
    if cv_path and cl_path:
        cv_name = cv_path.split("/")[-1]
        cl_name = cl_path.split("/")[-1]
        docs_row = f"""
  <div style="margin-top:16px;background:#f0fdf4;border:1px solid #bbf7d0;
              border-radius:8px;padding:12px">
    <div style="font-weight:600;font-size:13px;color:#15803d;margin-bottom:6px">
      Documents ready
    </div>
    <div style="font-family:monospace;font-size:12px;color:#166534;line-height:1.8">
      {cv_name}<br>{cl_name}
    </div>
  </div>"""
    else:
        docs_row = ""

    is_dream = bool(job.get("dream_employer"))
    card_border = "2px solid #f59e0b" if is_dream else "1px solid #e5e7eb"
    dream_badge = (
        '<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;'
        'padding:5px 12px;margin-bottom:12px;font-weight:700;font-size:12px;'
        'color:#92400e;display:inline-block">⭐ DREAM EMPLOYER</div>'
        if is_dream else ""
    )

    return f"""
<div style="background:#fff;border:{card_border};border-radius:12px;
            padding:24px;margin-bottom:24px;font-family:sans-serif">
  {dream_badge}
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
    <div>
      <h2 style="margin:0;font-size:18px;color:#111827">{job.get('title','')}</h2>
      <div style="color:#6b7280;font-size:14px;margin-top:4px">
        {job.get('company','')} &bull; {job.get('location','')} &bull; {_format_salary(job)}
      </div>
    </div>
    <div style="background:{_score_color(score)};color:#fff;font-size:22px;font-weight:bold;
                padding:8px 16px;border-radius:8px;min-width:56px;text-align:center">
      {score}
    </div>
  </div>
  <div style="margin-bottom:10px;font-size:13px;color:#374151">{job.get('rationale','')}</div>
  <div style="margin-bottom:8px"><strong>Matched:</strong> {matched_html}</div>
  {gaps_row}
  {flags_row}
  <details style="margin-top:16px">
    <summary style="cursor:pointer;color:#2563eb;font-weight:600;font-size:14px">
      Cover letter opening
    </summary>
    <div style="margin-top:10px;background:#f9fafb;border-left:3px solid #2563eb;
                padding:12px;font-size:13px;line-height:1.6;white-space:pre-wrap">
{cover_snippet}
    </div>
  </details>
  {docs_row}
  {_action_buttons(job)}
</div>
"""


def _applications_summary(applied: list[dict]) -> str:
    """Green summary block shown when applications were already sent today."""
    if not applied:
        return ""
    rows = "".join(
        f'<div style="padding:8px 0;border-bottom:1px solid #bbf7d0;font-size:14px">'
        f'<strong>{j["title"]}</strong> at {j["company"]}'
        f' &rarr; <span style="color:#166534">{j.get("application_email_used","—")}</span>'
        f"</div>"
        for j in applied
    )
    return f"""
<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;
            padding:20px;margin-bottom:24px;font-family:sans-serif">
  <div style="font-weight:700;font-size:15px;color:#15803d;margin-bottom:12px">
    ✓ {len(applied)} application{'s' if len(applied) != 1 else ''} sent today
  </div>
  {rows}
</div>"""


def build_html_digest(jobs: list[dict]) -> str:
    today = date.today().strftime("%A, %d %B %Y")
    count = len(jobs)
    cards = "".join(_job_card(j) for j in jobs)
    applied_today = get_applied_jobs_today()
    empty = (
        '<div style="text-align:center;color:#6b7280;padding:48px">'
        "No jobs scored 75+ today."
        "</div>"
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="background:#f3f4f6;margin:0;padding:24px;font-family:sans-serif">
  <div style="max-width:700px;margin:0 auto">
    <div style="background:#111827;color:#fff;padding:24px;border-radius:12px;margin-bottom:24px">
      <h1 style="margin:0;font-size:24px">Job Agent Digest</h1>
      <div style="color:#9ca3af;margin-top:4px">
        {today} &bull; {count} job{"s" if count != 1 else ""} scored 75+
      </div>
    </div>
    {_applications_summary(applied_today)}
    {cards if jobs else empty}
    <div style="text-align:center;color:#9ca3af;font-size:12px;padding:16px">
      Job Agent &bull; Powered by Claude AI &bull;
      Approval server must be running at {APPROVAL_BASE_URL}
    </div>
  </div>
</body>
</html>"""


def send_dream_alert(job: dict, score: int, rationale: str) -> None:
    """Fire an instant plain-HTML email for a dream employer match."""
    title   = job.get("title", "")
    company = job.get("company", "")
    url     = job.get("url", "#")
    subject = f"⭐ Dream employer match: {company} — {title}"

    body = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
  <div style="background:#fef3c7;border:2px solid #f59e0b;border-radius:12px;padding:20px;margin-bottom:20px">
    <div style="font-size:22px;font-weight:700;color:#92400e">⭐ Dream Employer Match</div>
  </div>
  <h2 style="margin:0 0 4px">{title}</h2>
  <div style="color:#6b7280;margin-bottom:16px">{company}</div>
  <div style="font-size:28px;font-weight:bold;color:{_score_color(score)};margin-bottom:8px">{score}/100</div>
  <div style="background:#f9fafb;border-left:3px solid #f59e0b;padding:12px;
              font-size:14px;color:#374151;margin-bottom:20px">{rationale}</div>
  <a href="{url}" style="background:#f59e0b;color:#fff;padding:12px 24px;
     border-radius:8px;text-decoration:none;font-weight:700;font-size:15px">
    View listing &rarr;
  </a>
</body>
</html>"""

    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print(f"[Alert] Dream employer match logged: {company} — {title} ({score}/100)")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = DREAM_ALERT_RECIPIENT
    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, DREAM_ALERT_RECIPIENT, msg.as_string())
        print(f"[Alert] Dream employer alert sent to {DREAM_ALERT_RECIPIENT}: {company} — {title}")
    except Exception as e:
        print(f"[Alert] Failed to send dream employer alert: {e}")


def send_digest(jobs: list[dict]) -> bool:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[Digest] Gmail credentials not set — saving digest to digest.html instead")
        with open("digest.html", "w") as f:
            f.write(build_html_digest(jobs))
        print("[Digest] Saved to digest.html")
        return True

    today = date.today().strftime("%d %b %Y")
    count = len(jobs)
    subject = f"Job Digest {today} — {count} match{'es' if count != 1 else ''}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = DIGEST_RECIPIENT
    msg.attach(MIMEText(build_html_digest(jobs), "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, DIGEST_RECIPIENT, msg.as_string())
        print(f"[Digest] Email sent to {DIGEST_RECIPIENT}")
        return True
    except Exception as e:
        print(f"[Digest] Email send failed: {e}")
        return False
