"""
alerts.py — Pipeline failure alerts and heartbeat emails for Job Agent.
"""

import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

from config import GMAIL_USER, GMAIL_APP_PASSWORD, DREAM_ALERT_RECIPIENT

ALERT_RECIPIENT = DREAM_ALERT_RECIPIENT   # jobseeker@example.com
ERROR_LOG = Path(__file__).parent / "logs" / "errors.log"


def _log_error(timestamp: str, step: str, exc: BaseException, traceback: str) -> None:
    ERROR_LOG.parent.mkdir(exist_ok=True)
    with open(ERROR_LOG, "a") as f:
        f.write(f"\n{'=' * 60}\n")
        f.write(f"[{timestamp}] STEP: {step}\n")
        f.write(f"Error: {exc}\n")
        if traceback:
            f.write(traceback)
        f.write("\n")


def _smtp_send(subject: str, body: str) -> bool:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return False
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = ALERT_RECIPIENT
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, ALERT_RECIPIENT, msg.as_string())
        return True
    except Exception as e:
        print(f"[Alert] SMTP send failed: {e}")
        return False


def send_alert(step: str, exc: BaseException, traceback: str = "") -> None:
    """
    Log the error and email an immediate failure alert.
    Always logs to errors.log even when SMTP is unavailable.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _log_error(timestamp, step, exc, traceback)
    print(f"[Alert] ⚠️  {step}: {exc}")

    subject = f"⚠️ Job Agent Pipeline Failed — {timestamp}"
    body = (
        f"Job Agent pipeline failure detected at {timestamp}.\n"
        f"\n"
        f"Step:  {step}\n"
        f"Error: {exc}\n"
    )
    if traceback:
        body += f"\nTraceback:\n{traceback}"
    body += f"\nFull log: ~/job-agent/logs/cron.log\n"

    if _smtp_send(subject, body):
        print(f"[Alert] Failure email sent to {ALERT_RECIPIENT}")
    else:
        print(f"[Alert] Gmail not configured — error logged to {ERROR_LOG}")


def send_heartbeat(scored: int, passed: int) -> None:
    """Send a brief daily confirmation that the pipeline completed successfully."""
    if scored == 0:
        return  # nothing ran — don't spam

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = f"✅ Job Agent ran successfully — {scored} jobs scored, {passed} passed"
    body = (
        f"Pipeline completed successfully at {timestamp}.\n"
        f"\n"
        f"  Jobs scored : {scored}\n"
        f"  Passed 75+  : {passed}\n"
    )

    if _smtp_send(subject, body):
        print(f"[Heartbeat] Confirmation sent to {ALERT_RECIPIENT}")
    else:
        print(f"[Heartbeat] {subject}")
