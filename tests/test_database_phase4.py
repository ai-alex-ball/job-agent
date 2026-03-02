import sqlite3
import pytest
from pathlib import Path
import sys

# Point at the project root so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Isolated DB fixture — patches config.DB_PATH so get_conn() uses a temp file."""
    db_file = tmp_path / "test.db"
    import config as cfg
    import database as db_mod
    monkeypatch.setattr(cfg, "DB_PATH", db_file)
    db_mod.init_db()
    return db_mod


def _insert_manual(db):
    """Insert a manual_required job and return its id."""
    conn = db.get_conn()
    cur = conn.execute(
        """INSERT INTO jobs (title, company, url, status, approval_token)
           VALUES ('Test Job', 'Test Co', 'https://example.com/job/1', 'manual_required', 'tok123')"""
    )
    conn.commit()
    job_id = cur.lastrowid
    conn.close()
    return job_id


def test_init_db_creates_browser_apply_columns(db):
    conn = db.get_conn()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    conn.close()
    assert "browser_apply_status" in cols
    assert "browser_apply_error" in cols


def test_mark_browser_applied_sets_status(db):
    job_id = _insert_manual(db)
    db.mark_browser_applied(job_id)
    conn = db.get_conn()
    row = conn.execute("SELECT status, browser_apply_status, applied_at FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    assert row[0] == "browser_applied"
    assert row[1] == "success"
    assert row[2] is not None  # applied_at was stamped


def test_mark_browser_apply_failed_leaves_manual(db):
    job_id = _insert_manual(db)
    db.mark_browser_apply_failed(job_id, "Element not found: #first_name")
    conn = db.get_conn()
    row = conn.execute(
        "SELECT status, browser_apply_status, browser_apply_error FROM jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    conn.close()
    assert row[0] == "manual_required"
    assert row[1] == "failed"
    assert "Element not found" in row[2]


def test_get_manual_required_jobs_returns_only_manual(db):
    job_id = _insert_manual(db)
    # Insert a non-manual job
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO jobs (title, company, url, status, approval_token) VALUES ('Other', 'Co', 'https://x.com', 'applied', 'tok999')"
    )
    conn.commit()
    conn.close()

    jobs = db.get_manual_required_jobs()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
