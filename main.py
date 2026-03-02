import shutil
import sys
import traceback as tb_module
from pathlib import Path

from database import (
    init_db,
    insert_job,
    get_new_jobs,
    update_score,
    mark_documents_generated,
    get_scored_jobs_for_digest,
    mark_digest_sent,
    get_conn,
)
from ingestion import fetch_all_jobs
from scoring import score_job
from documents import generate_documents
from digest import send_digest, send_dream_alert
from dashboard import generate_dashboard
from alerts import send_alert, send_heartbeat
from config import MAX_JOBS_PER_RUN


BASE_DIR = Path(__file__).parent
WINDOWS_DIR = Path("/mnt/c/Users/Public/Documents/JobAgent")


def sync_to_windows():
    WINDOWS_DIR.mkdir(parents=True, exist_ok=True)

    # Copy master CV
    master_cv = BASE_DIR / "master_cv.docx"
    if master_cv.exists():
        shutil.copy2(master_cv, WINDOWS_DIR / master_cv.name)

    # Sync entire outputs directory
    outputs_dir = BASE_DIR / "outputs"
    if outputs_dir.exists():
        for f in outputs_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, WINDOWS_DIR / f.name)

    # Print per-job summary for today's processed jobs
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT title, company, cv_path, cover_letter_path FROM jobs
        WHERE status IN ('documents_generated', 'applied')
          AND cv_path IS NOT NULL
          AND (date(scored_at) = date('now') OR date(applied_at) = date('now'))
        ORDER BY scored_at DESC
        """
    ).fetchall()
    conn.close()

    if not rows:
        print(f"[Sync] No documents generated today — outputs synced to {WINDOWS_DIR}")
        return

    for row in rows:
        cv_name = Path(row["cv_path"]).name if row["cv_path"] else "—"
        cl_name = Path(row["cover_letter_path"]).name if row["cover_letter_path"] else "—"
        print(f"[Sync] Documents copied to Windows: {cv_name}, {cl_name}")


def run():
    print("=== Job Agent — Daily Pipeline ===\n")

    # 1. Initialise database
    init_db()

    # 2. Ingest jobs
    try:
        raw_jobs = fetch_all_jobs()
    except Exception as e:
        send_alert("Ingestion failed", e, tb_module.format_exc())
        raw_jobs = []

    new_count = 0
    for job in raw_jobs:
        if insert_job(job) is not None:
            new_count += 1
    print(f"\n[Pipeline] {new_count} new jobs added to database\n")

    # 3. Score new jobs with Claude (capped to control daily API cost)
    all_new = get_new_jobs()
    to_score = all_new[:MAX_JOBS_PER_RUN]
    skipped = len(all_new) - len(to_score)
    suffix = f" ({skipped} deferred to next run)" if skipped else ""
    print(f"[Pipeline] Scoring {len(to_score)} jobs{suffix}...\n")

    passed = 0
    scored_count = 0
    try:
        for job in to_score:
            label = f"{job['title']} @ {job['company']}"
            print(f"  Scoring: {label}")
            result = score_job(job)
            if result is None:
                print(f"    → Failed — skipping")
                continue
            scored_count += 1
            update_score(job["id"], result)
            scoring = result.get("scoring", {})
            score = scoring.get("overall_score", 0)
            proceed = scoring.get("proceed", False)
            status = "PASS ✓" if proceed else "FAIL ✗"
            dream_tag = " ⭐" if result.get("dream_employer") else ""
            print(f"    → {score}/100  [{status}]{dream_tag}  {scoring.get('rationale', '')}")

            if result.get("dream_employer"):
                send_dream_alert(job, score, scoring.get("rationale", ""))
            if proceed:
                passed += 1
                try:
                    cv_path, cl_path = generate_documents({**job, **result})
                    mark_documents_generated(job["id"], cv_path, cl_path)
                except Exception as e:
                    print(f"    → Document generation failed: {e}")
    except Exception as e:
        send_alert(f"Scoring failed after {scored_count} jobs", e, tb_module.format_exc())

    print(f"\n[Pipeline] {passed}/{len(to_score)} jobs passed threshold (≥75)\n")

    # 4. Build and send digest
    try:
        digest_jobs = get_scored_jobs_for_digest()
        if digest_jobs:
            print(f"[Pipeline] Sending digest with {len(digest_jobs)} job(s)...")
            if send_digest(digest_jobs):
                mark_digest_sent([j["id"] for j in digest_jobs])
        else:
            print("[Pipeline] No qualifying jobs for today's digest.")
    except Exception as e:
        send_alert("Digest failed", e, tb_module.format_exc())

    # 5. Sync documents to Windows
    print("\n[Pipeline] Syncing documents to Windows...")
    sync_to_windows()

    # 6. Regenerate dashboard
    print("\n[Pipeline] Regenerating dashboard...")
    generate_dashboard()

    # 7. Heartbeat — confirms pipeline completed
    send_heartbeat(scored_count, passed)

    print("\n=== Done ===")


def print_status():
    init_db()
    conn = get_conn()

    total       = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    applied     = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='applied'").fetchone()[0]
    pending     = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='digest_sent'").fetchone()[0]
    manual      = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='manual_required'").fetchone()[0]
    scored_today = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE date(scored_at)=date('now')"
    ).fetchone()[0]
    last_run_row = conn.execute(
        "SELECT MAX(scored_at) FROM jobs WHERE scored_at IS NOT NULL"
    ).fetchone()[0]

    conn.close()

    est_cost = scored_today * 0.014   # ~$0.014 per job scored (sonnet-4-6 estimate)
    daily_cap_cost = MAX_JOBS_PER_RUN * 0.014

    print("\n=== Job Agent Status ===\n")
    print(f"  Total jobs in DB       : {total:,}")
    print(f"  Applied                : {applied}")
    print(f"  Pending approval       : {pending}  (digest sent, awaiting APPROVE/SKIP)")
    if manual:
        print(f"  Manual required        : {manual}  (no email found — apply via listing)")
    print(f"  Last run               : {last_run_row or 'never'}")
    print(f"  Jobs scored today      : {scored_today}")
    print(f"  Est. API spend today   : ${est_cost:.2f}  (cap: ${daily_cap_cost:.2f}/day)")
    print()


if __name__ == "__main__":
    if "--status" in sys.argv:
        print_status()
    else:
        try:
            run()
        except Exception as e:
            send_alert("Pipeline crashed", e, tb_module.format_exc())
            raise
