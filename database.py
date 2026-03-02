import secrets
import sqlite3
import json
from datetime import datetime, timezone
from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id                  TEXT,
            platform                TEXT,
            title                   TEXT,
            company                 TEXT,
            location                TEXT,
            salary_min              INTEGER,
            salary_max              INTEGER,
            salary_currency         TEXT DEFAULT 'GBP',
            description             TEXT,
            url                     TEXT UNIQUE,
            date_posted             TEXT,
            status                  TEXT DEFAULT 'new',
            score                   INTEGER,
            matched_skills          TEXT,
            skill_gaps              TEXT,
            red_flags               TEXT,
            rationale               TEXT,
            tailored_cv             TEXT,
            cover_letter            TEXT,
            created_at              TEXT DEFAULT (datetime('now')),
            scored_at               TEXT,
            digest_sent_at          TEXT,
            cv_path                 TEXT,
            cover_letter_path       TEXT,
            approval_token          TEXT UNIQUE,
            approved_at             TEXT,
            applied_at              TEXT,
            application_email_used  TEXT,
            dream_employer          INTEGER DEFAULT 0
        )
    """)

    # Migrate existing databases — add any columns that are missing
    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    new_cols = [
        ("cv_path",                "TEXT"),
        ("cover_letter_path",      "TEXT"),
        ("approval_token",         "TEXT"),   # UNIQUE in CREATE TABLE; ALTER TABLE doesn't support it
        ("approved_at",            "TEXT"),
        ("applied_at",             "TEXT"),
        ("application_email_used", "TEXT"),
        ("dream_employer",         "INTEGER DEFAULT 0"),
    ]
    for col, definition in new_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {definition}")

    # Backfill approval tokens for any rows that don't yet have one
    rows = conn.execute("SELECT id FROM jobs WHERE approval_token IS NULL").fetchall()
    for row in rows:
        conn.execute(
            "UPDATE jobs SET approval_token = ? WHERE id = ?",
            (secrets.token_urlsafe(24), row[0]),
        )

    conn.commit()
    conn.close()


def url_exists(url: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone()
    conn.close()
    return row is not None


def insert_job(job: dict) -> int | None:
    """Insert a new job. Returns the row id or None if the URL already exists."""
    if not job.get("url") or url_exists(job["url"]):
        return None
    token = secrets.token_urlsafe(24)
    conn = get_conn()
    cur = conn.execute(
        """
        INSERT INTO jobs
            (job_id, platform, title, company, location,
             salary_min, salary_max, salary_currency,
             description, url, date_posted, approval_token)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job.get("job_id"),
            job.get("platform"),
            job.get("title"),
            job.get("company"),
            job.get("location"),
            job.get("salary_min"),
            job.get("salary_max"),
            job.get("salary_currency", "GBP"),
            job.get("description"),
            job["url"],
            job.get("date_posted"),
            token,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_new_jobs() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM jobs WHERE status = 'new'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_score(row_id: int, result: dict):
    scoring = result.get("scoring", {})
    proceed = scoring.get("proceed", False)
    new_status = "scored" if proceed else "rejected"
    dream = 1 if result.get("dream_employer") else 0
    conn = get_conn()
    conn.execute(
        """
        UPDATE jobs SET
            status         = ?,
            score          = ?,
            matched_skills = ?,
            skill_gaps     = ?,
            red_flags      = ?,
            rationale      = ?,
            tailored_cv    = ?,
            cover_letter   = ?,
            scored_at      = ?,
            dream_employer = ?
        WHERE id = ?
        """,
        (
            new_status,
            scoring.get("overall_score", 0),
            json.dumps(scoring.get("matched_skills", [])),
            json.dumps(scoring.get("skill_gaps", [])),
            json.dumps(scoring.get("red_flags", [])),
            scoring.get("rationale"),
            result.get("tailored_cv"),
            result.get("cover_letter"),
            datetime.now(timezone.utc).isoformat(),
            dream,
            row_id,
        ),
    )
    conn.commit()
    conn.close()


def mark_documents_generated(row_id: int, cv_path: str, cover_letter_path: str):
    conn = get_conn()
    conn.execute(
        """
        UPDATE jobs SET
            status             = 'documents_generated',
            cv_path            = ?,
            cover_letter_path  = ?
        WHERE id = ?
        """,
        (cv_path, cover_letter_path, row_id),
    )
    conn.commit()
    conn.close()


def get_scored_jobs_for_digest() -> list[dict]:
    """
    Today's qualifying jobs not yet digested:
    - All jobs that passed the 75 threshold (scored / documents_generated)
    - Dream employer jobs that scored >= 60, even if otherwise rejected
    Ordered dream-first, then by score descending.
    """
    from config import DREAM_EMPLOYER_MIN_SCORE
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT * FROM jobs
        WHERE date(created_at) = date('now')
          AND (
            status IN ('scored', 'documents_generated')
            OR (dream_employer = 1 AND score >= ?)
          )
        ORDER BY dream_employer DESC, score DESC
        """,
        (DREAM_EMPLOYER_MIN_SCORE,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_digest_sent(job_ids: list[int]):
    conn = get_conn()
    placeholders = ",".join("?" * len(job_ids))
    conn.execute(
        f"""
        UPDATE jobs
        SET status = 'digest_sent', digest_sent_at = ?
        WHERE id IN ({placeholders})
        """,
        [datetime.now(timezone.utc).isoformat(), *job_ids],
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Phase 3 — approval gate
# ---------------------------------------------------------------------------

def get_job_by_token(token: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM jobs WHERE approval_token = ?", (token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_approved(row_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE jobs SET status = 'approved', approved_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), row_id),
    )
    conn.commit()
    conn.close()


def mark_applied(row_id: int, email_used: str):
    conn = get_conn()
    conn.execute(
        """UPDATE jobs SET
               status                 = 'applied',
               applied_at             = ?,
               application_email_used = ?
           WHERE id = ?""",
        (datetime.now(timezone.utc).isoformat(), email_used, row_id),
    )
    conn.commit()
    conn.close()


def mark_skipped(row_id: int):
    conn = get_conn()
    conn.execute("UPDATE jobs SET status = 'skipped' WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()


def mark_manual_required(row_id: int):
    conn = get_conn()
    conn.execute("UPDATE jobs SET status = 'manual_required' WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()


def get_applied_jobs_today() -> list[dict]:
    """Jobs that had applications sent today — for digest summary."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM jobs
           WHERE status = 'applied'
             AND date(applied_at) = date('now')
           ORDER BY applied_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
