"""
weekly_summary.py — Weekly job-agent digest.

Sends every Sunday at 08:00 via cron.  Can also be triggered manually:
    python3 weekly_summary.py
"""

import smtplib
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import GMAIL_USER, GMAIL_APP_PASSWORD, DREAM_ALERT_RECIPIENT
from database import get_conn


# ── helpers ──────────────────────────────────────────────────────────────────

def _week_start() -> date:
    """Monday of the current week."""
    today = date.today()
    return today - timedelta(days=today.weekday())


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    return iso[:10]  # yyyy-mm-dd is enough


def _score_chip(score: int | None) -> str:
    if score is None:
        return "—"
    if score >= 90:
        colour = "#16a34a"
    elif score >= 75:
        colour = "#2563eb"
    elif score >= 60:
        colour = "#d97706"
    else:
        colour = "#6b7280"
    return (
        f'<span style="background:{colour};color:#fff;padding:2px 8px;'
        f'border-radius:10px;font-size:12px;font-weight:700">{score}</span>'
    )


def _stat_block(label: str, value: int, accent: str = "#111827") -> str:
    return (
        f'<td style="text-align:center;padding:16px 20px;background:#fff;'
        f'border-radius:8px;border:1px solid #e5e7eb">'
        f'<div style="font-size:28px;font-weight:800;color:{accent}">{value}</div>'
        f'<div style="font-size:12px;color:#6b7280;margin-top:4px">{label}</div>'
        f'</td>'
    )


def _section_header(emoji: str, title: str) -> str:
    return (
        f'<h2 style="font-size:16px;font-weight:700;color:#111827;'
        f'margin:32px 0 12px;padding-bottom:8px;border-bottom:2px solid #e5e7eb">'
        f'{emoji} {title}</h2>'
    )


def _empty_row(cols: int, msg: str = "None this week") -> str:
    return (
        f'<tr><td colspan="{cols}" style="padding:12px;color:#9ca3af;'
        f'font-style:italic;text-align:center">{msg}</td></tr>'
    )


# ── database queries ──────────────────────────────────────────────────────────

def _query_week() -> dict:
    """Single connection, all queries for the past 7 days."""
    conn = get_conn()
    since = (date.today() - timedelta(days=6)).isoformat()  # inclusive 7-day window
    try:
        stats = {}

        stats["fetched"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE date(created_at) >= ?", (since,)
        ).fetchone()[0]

        stats["scored"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE scored_at IS NOT NULL AND date(scored_at) >= ?",
            (since,),
        ).fetchone()[0]

        stats["passed"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE score >= 75 AND date(scored_at) >= ?",
            (since,),
        ).fetchone()[0]

        stats["dream_matches"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE dream_employer = 1 AND date(created_at) >= ?",
            (since,),
        ).fetchone()[0]

        stats["applied"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'applied' AND date(applied_at) >= ?",
            (since,),
        ).fetchone()[0]

        stats["manual"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'manual_required'"
        ).fetchone()[0]

        applications = [
            dict(r) for r in conn.execute(
                """SELECT title, company, score, applied_at, application_email_used, url
                   FROM jobs
                   WHERE status = 'applied' AND date(applied_at) >= ?
                   ORDER BY applied_at DESC""",
                (since,),
            ).fetchall()
        ]

        manual_pending = [
            dict(r) for r in conn.execute(
                """SELECT title, company, score, created_at, url
                   FROM jobs
                   WHERE status = 'manual_required'
                   ORDER BY score DESC NULLS LAST"""
            ).fetchall()
        ]

        dream_activity = [
            dict(r) for r in conn.execute(
                """SELECT title, company, score, status, created_at, url
                   FROM jobs
                   WHERE dream_employer = 1 AND date(created_at) >= ?
                   ORDER BY score DESC NULLS LAST""",
                (since,),
            ).fetchall()
        ]

        top_pending = [
            dict(r) for r in conn.execute(
                """SELECT title, company, score, status, url
                   FROM jobs
                   WHERE status NOT IN ('applied', 'skipped', 'rejected')
                     AND score >= 75
                   ORDER BY score DESC
                   LIMIT 5"""
            ).fetchall()
        ]

        return {
            "stats":        stats,
            "applications": applications,
            "manual":       manual_pending,
            "dream":        dream_activity,
            "top_pending":  top_pending,
        }
    finally:
        conn.close()


# ── HTML sections ─────────────────────────────────────────────────────────────

def _html_stats(stats: dict) -> str:
    return f"""
{_section_header("📊", "Pipeline Stats")}
<table style="border-spacing:8px;border-collapse:separate;width:100%">
  <tr>
    {_stat_block("Fetched", stats["fetched"])}
    {_stat_block("Scored", stats["scored"])}
    {_stat_block("Passed 75+", stats["passed"], "#2563eb")}
    {_stat_block("Dream matches", stats["dream_matches"], "#d97706")}
    {_stat_block("Applied", stats["applied"], "#16a34a")}
    {_stat_block("Manual pending", stats["manual"], "#dc2626")}
  </tr>
</table>"""


def _html_applications(rows: list[dict]) -> str:
    header = _section_header("✅", "Applications Sent This Week")
    th = "style='padding:8px 12px;text-align:left;font-size:12px;color:#6b7280;font-weight:600'"
    td = "style='padding:10px 12px;font-size:13px;border-top:1px solid #f3f4f6'"

    if not rows:
        body = f"<table style='width:100%'>{_empty_row(5)}</table>"
    else:
        trs = ""
        for r in rows:
            trs += (
                f"<tr>"
                f"<td {td}><a href='{r['url']}' style='color:#2563eb;text-decoration:none'>"
                f"{r['title']}</a></td>"
                f"<td {td}>{r['company']}</td>"
                f"<td {td}>{_score_chip(r['score'])}</td>"
                f"<td {td}>{_fmt_date(r['applied_at'])}</td>"
                f"<td {td} style='color:#6b7280'>{r['application_email_used'] or '—'}</td>"
                f"</tr>"
            )
        body = f"""
<table style="width:100%;border-collapse:collapse;background:#fff;
              border-radius:8px;border:1px solid #e5e7eb;overflow:hidden">
  <tr>
    <th {th}>Role</th>
    <th {th}>Company</th>
    <th {th}>Score</th>
    <th {th}>Applied</th>
    <th {th}>Email used</th>
  </tr>
  {trs}
</table>"""
    return header + body


def _html_manual(rows: list[dict]) -> str:
    header = _section_header("📋", "Manual Applications Pending")
    th = "style='padding:8px 12px;text-align:left;font-size:12px;color:#6b7280;font-weight:600'"
    td = "style='padding:10px 12px;font-size:13px;border-top:1px solid #f3f4f6'"

    if not rows:
        body = f"<table style='width:100%'>{_empty_row(4, 'None pending')}</table>"
    else:
        trs = ""
        for r in rows:
            trs += (
                f"<tr>"
                f"<td {td}>{r['title']}</td>"
                f"<td {td}>{r['company']}</td>"
                f"<td {td}>{_score_chip(r['score'])}</td>"
                f"<td {td}>"
                f"<a href='{r['url']}' style='color:#2563eb;text-decoration:none;font-weight:600'>"
                f"Apply &rarr;</a></td>"
                f"</tr>"
            )
        body = f"""
<table style="width:100%;border-collapse:collapse;background:#fff;
              border-radius:8px;border:1px solid #e5e7eb;overflow:hidden">
  <tr>
    <th {th}>Role</th><th {th}>Company</th><th {th}>Score</th><th {th}>Link</th>
  </tr>
  {trs}
</table>"""
    return header + body


def _html_dream(rows: list[dict]) -> str:
    header = _section_header("⭐", "Dream Employer Activity")
    th = "style='padding:8px 12px;text-align:left;font-size:12px;color:#6b7280;font-weight:600'"
    td = "style='padding:10px 12px;font-size:13px;border-top:1px solid #f3f4f6'"

    if not rows:
        body = f"<table style='width:100%'>{_empty_row(4, 'No dream employer jobs this week')}</table>"
    else:
        trs = ""
        for r in rows:
            status_label = r["status"].replace("_", " ").title()
            trs += (
                f"<tr>"
                f"<td {td}><a href='{r['url']}' style='color:#2563eb;text-decoration:none'>"
                f"{r['title']}</a></td>"
                f"<td {td}><strong>{r['company']}</strong></td>"
                f"<td {td}>{_score_chip(r['score'])}</td>"
                f"<td {td}>{status_label}</td>"
                f"</tr>"
            )
        body = f"""
<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;
            padding:2px;margin-bottom:4px">
<table style="width:100%;border-collapse:collapse;background:#fffbeb;
              border-radius:6px;overflow:hidden">
  <tr>
    <th {th}>Role</th><th {th}>Company</th><th {th}>Score</th><th {th}>Status</th>
  </tr>
  {trs}
</table>
</div>"""
    return header + body


def _html_top_pending(rows: list[dict]) -> str:
    header = _section_header("📈", "Top Scoring Jobs — Pending Action")
    th = "style='padding:8px 12px;text-align:left;font-size:12px;color:#6b7280;font-weight:600'"
    td = "style='padding:10px 12px;font-size:13px;border-top:1px solid #f3f4f6'"

    if not rows:
        body = f"<table style='width:100%'>{_empty_row(3, 'No pending jobs')}</table>"
    else:
        trs = ""
        for r in rows:
            trs += (
                f"<tr>"
                f"<td {td}><a href='{r['url']}' style='color:#2563eb;text-decoration:none'>"
                f"{r['title']}</a></td>"
                f"<td {td}>{r['company']}</td>"
                f"<td {td}>{_score_chip(r['score'])}</td>"
                f"</tr>"
            )
        body = f"""
<table style="width:100%;border-collapse:collapse;background:#fff;
              border-radius:8px;border:1px solid #e5e7eb;overflow:hidden">
  <tr>
    <th {th}>Role</th><th {th}>Company</th><th {th}>Score</th>
  </tr>
  {trs}
</table>"""
    return header + body


# ── main builder ──────────────────────────────────────────────────────────────

def build_weekly_html(data: dict) -> str:
    wc = _week_start().strftime("%d %b %Y")
    today = date.today().strftime("%A, %d %B %Y")

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="background:#f3f4f6;margin:0;padding:24px;font-family:sans-serif">
  <div style="max-width:700px;margin:0 auto">

    <div style="background:#111827;color:#fff;padding:24px;border-radius:12px;margin-bottom:24px">
      <h1 style="margin:0;font-size:22px">Job Agent — Weekly Summary</h1>
      <div style="color:#9ca3af;margin-top:6px">Week commencing {wc} &bull; Generated {today}</div>
    </div>

    {_html_stats(data["stats"])}
    {_html_applications(data["applications"])}
    {_html_manual(data["manual"])}
    {_html_dream(data["dream"])}
    {_html_top_pending(data["top_pending"])}

    <div style="text-align:center;color:#9ca3af;font-size:12px;padding:24px 0 8px">
      Job Agent &bull; Powered by Claude AI
    </div>
  </div>
</body>
</html>"""


def generate_weekly_summary() -> bool:
    """Build and send the weekly summary email. Returns True on success."""
    data = _query_week()
    html = build_weekly_html(data)
    wc   = _week_start().strftime("%d %b %Y")
    subject = f"Job Agent Weekly Summary — w/c {wc}"

    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        path = "weekly_summary.html"
        with open(path, "w") as f:
            f.write(html)
        print(f"[Weekly] Gmail not configured — saved to {path}")
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = DREAM_ALERT_RECIPIENT
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, DREAM_ALERT_RECIPIENT, msg.as_string())
        s = data["stats"]
        print(
            f"[Weekly] Email sent to {DREAM_ALERT_RECIPIENT} — "
            f"{s['fetched']} fetched, {s['scored']} scored, "
            f"{s['applied']} applied, {s['dream_matches']} dream matches"
        )
        return True
    except Exception as e:
        print(f"[Weekly] Email send failed: {e}")
        return False


if __name__ == "__main__":
    generate_weekly_summary()
