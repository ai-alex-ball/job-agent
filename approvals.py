"""
approvals.py — Phase 3 approval webhook server

Run this alongside the cron job so APPROVE / SKIP clicks in the digest
email are handled in real time:

    cd /home/theboss/job-agent && python3 approvals.py

Listens on 127.0.0.1:{FLASK_PORT} (default: 5000).
The APPROVE and SKIP links in the digest email point to this server.

NOTE: The digest email buttons link to http://localhost:5000/... so this
server must be running on the same machine where you read your email.
"""

from flask import Flask, abort

from database import (
    get_job_by_token,
    mark_approved,
    mark_applied,
    mark_skipped,
    mark_manual_required,
    mark_browser_applied,
    mark_browser_apply_failed,
)
from browser_apply import BrowserApplier, detect_portal
from apply import send_application
from config import FLASK_PORT

app = Flask(__name__)

# Statuses that mean the job is already fully actioned
_TERMINAL = {"applied", "skipped", "manual_required"}


def _no_email_page(title: str, company: str, job_url: str, token: str, portal: str) -> str:
    auto_apply_html = ""
    if portal in ("greenhouse", "lever", "generic"):
        label = "Auto-Apply (Experimental)" if portal == "generic" else "Auto-Apply"
        auto_apply_html = f"""
  <a href="/browser-apply/{token}"
     style="display:inline-block;margin-top:12px;background:#2563eb;color:#fff;
            padding:12px 28px;border-radius:8px;text-decoration:none;
            font-size:15px;font-weight:600">
    {label} &rarr;
  </a>
  <p style="font-size:13px;color:#6b7280;margin-top:8px">
    Attempts to fill the application form automatically
  </p>"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Apply Manually</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="font-family:sans-serif;max-width:560px;margin:80px auto;padding:24px;text-align:center">
  <div style="font-size:48px;margin-bottom:16px">📋</div>
  <h1 style="color:#d97706;margin:0 0 12px">No Email Found</h1>
  <p style="font-size:16px;color:#374151;line-height:1.6">
    No application email address was found in the listing for
    <strong>{title}</strong> at <strong>{company}</strong>.<br><br>
    Please apply manually via the job listing, or try auto-apply below.
  </p>
  <a href="{job_url}" target="_blank"
     style="display:inline-block;margin-top:24px;background:#111827;color:#fff;
            padding:12px 28px;border-radius:8px;text-decoration:none;
            font-size:15px;font-weight:600">
    View &amp; Apply on Listing &rarr;
  </a>
  {auto_apply_html}
  <p style="margin-top:32px">
    <a href="javascript:window.close()"
       style="color:#9ca3af;font-size:14px;text-decoration:none">Close this tab</a>
  </p>
</body>
</html>"""


def _page(title: str, body: str, color: str = "#16a34a") -> str:
    """Minimal confirmation HTML page."""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="font-family:sans-serif;max-width:560px;margin:80px auto;padding:24px;text-align:center">
  <div style="font-size:48px;margin-bottom:16px">{'✓' if color == '#16a34a' else '⊘' if color == '#6b7280' else '✗'}</div>
  <h1 style="color:{color};margin:0 0 12px">{title}</h1>
  <p style="font-size:16px;color:#374151;line-height:1.6">{body}</p>
  <p style="margin-top:32px">
    <a href="javascript:window.close()"
       style="color:#9ca3af;font-size:14px;text-decoration:none">Close this tab</a>
  </p>
</body>
</html>"""


@app.route("/approve/<token>")
def approve(token: str):
    job = get_job_by_token(token)
    if not job:
        abort(404)

    # Idempotency guards
    if job["status"] == "applied":
        return _page(
            "Already Applied",
            f"Your application to <strong>{job['company']}</strong> was already sent "
            f"to <strong>{job.get('application_email_used', '—')}</strong>.",
            "#2563eb",
        )
    if job["status"] == "skipped":
        return _page(
            "Job Was Skipped",
            f"<strong>{job['title']}</strong> at <strong>{job['company']}</strong> "
            f"was previously skipped. No action taken.",
            "#6b7280",
        )

    if job["status"] == "manual_required":
        job_url = job.get("url", "#")
        portal = detect_portal(job_url)
        return _no_email_page(job["title"], job["company"], job_url, token, portal)

    mark_approved(job["id"])
    success, result = send_application(job)

    if success:
        mark_applied(job["id"], result)
        return _page(
            "Application Sent",
            f"Your application for <strong>{job['title']}</strong> at "
            f"<strong>{job['company']}</strong> has been sent to "
            f"<strong>{result}</strong>.",
        )

    if result == "no_email":
        mark_manual_required(job["id"])
        job_url = job.get("url", "#")
        portal = detect_portal(job_url)
        return _no_email_page(job["title"], job["company"], job_url, token, portal)

    # Any other failure — leave as 'approved' so it can be retried
    return _page(
        "Send Failed",
        f"Application to <strong>{job['company']}</strong> could not be sent.<br>"
        f"<span style='font-size:13px;color:#6b7280'>{result}</span><br><br>"
        f"Check that GMAIL credentials are set and try again.",
        "#dc2626",
    )


@app.route("/skip/<token>")
def skip(token: str):
    job = get_job_by_token(token)
    if not job:
        abort(404)

    if job["status"] in _TERMINAL:
        return _page(
            "Already Actioned",
            f"<strong>{job['title']}</strong> at <strong>{job['company']}</strong> "
            f"has already been <strong>{job['status']}</strong>.",
            "#6b7280",
        )

    mark_skipped(job["id"])
    return _page(
        "Job Skipped",
        f"<strong>{job['title']}</strong> at <strong>{job['company']}</strong> "
        f"has been skipped and will not be applied to.",
        "#6b7280",
    )


@app.route("/browser-apply/<token>")
def browser_apply_route(token: str):
    job = get_job_by_token(token)
    if not job:
        abort(404)

    if job["status"] == "browser_applied":
        return _page(
            "Already Applied",
            f"This application was already submitted automatically for "
            f"<strong>{job['title']}</strong> at <strong>{job['company']}</strong>.",
            "#2563eb",
        )

    if job["status"] not in ("manual_required", "approved"):
        return _page(
            "Not Available",
            f"This job has status <strong>{job['status']}</strong> and cannot be auto-applied.",
            "#6b7280",
        )

    applier = BrowserApplier()
    success, msg = applier.apply(job)

    if success:
        mark_browser_applied(job["id"])
        return _page(
            "Auto-Apply Submitted",
            f"Application for <strong>{job['title']}</strong> at "
            f"<strong>{job['company']}</strong> was submitted automatically.",
        )

    if "unsupported" in msg:
        return _page(
            "Portal Not Supported",
            f"Workday and some portals require manual application.<br>"
            f"<a href='{job.get('url', '#')}' target='_blank' "
            f"style='color:#2563eb'>Apply on the job listing &rarr;</a>",
            "#d97706",
        )

    if "cancelled by user" in msg:
        return _page(
            "Cancelled",
            f"Auto-apply for <strong>{job['title']}</strong> at "
            f"<strong>{job['company']}</strong> was cancelled.<br>"
            f"<a href='{job.get('url', '#')}' target='_blank' "
            f"style='color:#2563eb'>Apply manually on the listing &rarr;</a>",
            "#6b7280",
        )

    mark_browser_apply_failed(job["id"], msg)
    return _page(
        "Auto-Apply Failed",
        f"Could not automatically submit the application for "
        f"<strong>{job['title']}</strong> at <strong>{job['company']}</strong>.<br>"
        f"<span style='font-size:13px;color:#6b7280'>{msg[:200]}</span><br><br>"
        f"<a href='{job.get('url', '#')}' target='_blank' "
        f"style='color:#2563eb'>Apply manually on the listing &rarr;</a>",
        "#dc2626",
    )


if __name__ == "__main__":
    print(f"[Approvals] Webhook server running on http://127.0.0.1:{FLASK_PORT}")
    print("[Approvals] Keep this running while you action jobs from the digest email.")
    print("[Approvals] Press Ctrl+C to stop.")
    app.run(host="127.0.0.1", port=FLASK_PORT, debug=False)
