"""
dashboard.py — Generate a static dashboard.html from the jobs database.

Run manually:  python3 dashboard.py
Auto-runs at the end of every main.py pipeline.
"""

import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from database import get_conn

BASE_DIR   = Path(__file__).parent
OUT_PATH   = BASE_DIR / "dashboard.html"
WINDOWS_DIR = Path("/mnt/c/Users/Public/Documents/JobAgent")


# ── helpers ───────────────────────────────────────────────────────────────────

def _esc(v: object) -> str:
    if v is None:
        return ""
    return (str(v)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _salary(row: dict) -> str:
    lo, hi = row.get("salary_min"), row.get("salary_max")
    if lo and hi:
        return f"£{int(lo):,}–£{int(hi):,}"
    if lo:
        return f"£{int(lo):,}+"
    return "—"


def _fmt_date(iso: str | None) -> str:
    return iso[:10] if iso else "—"


def _score_badge(score: int | None) -> str:
    if score is None:
        return '<span class="badge badge-gray">—</span>'
    if score >= 90:
        return f'<span class="badge badge-green">{score}</span>'
    if score >= 75:
        return f'<span class="badge badge-blue">{score}</span>'
    if score >= 60:
        return f'<span class="badge badge-amber">{score}</span>'
    return f'<span class="badge badge-gray">{score}</span>'


def _status_badge(status: str) -> str:
    mapping = {
        "applied":            ("badge-green",  "Applied"),
        "documents_generated":("badge-blue",   "Docs ready"),
        "scored":             ("badge-blue",   "Scored"),
        "digest_sent":        ("badge-amber",  "Pending"),
        "approved":           ("badge-amber",  "Approved"),
        "manual_required":    ("badge-orange", "Manual req."),
        "rejected":           ("badge-gray",   "Rejected"),
        "rejected_after_apply": ("badge-gray", "Rejected after apply"),
        "skipped":            ("badge-gray",   "Skipped"),
        "new":                ("badge-gray",   "New"),
    }
    cls, label = mapping.get(status, ("badge-gray", status.replace("_", " ").title()))
    return f'<span class="badge {cls}">{label}</span>'


# ── data layer ────────────────────────────────────────────────────────────────

def _fetch_data() -> dict:
    conn = get_conn()

    funnel = {
        "fetched": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
        "scored":  conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE score IS NOT NULL").fetchone()[0],
        "passed":  conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE score >= 75").fetchone()[0],
        "docs":    conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE cv_path IS NOT NULL").fetchone()[0],
        "applied": conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'applied'").fetchone()[0],
    }

    stats = {
        "total":   funnel["fetched"],
        "applied": funnel["applied"],
        "pending": conn.execute(
            "SELECT COUNT(*) FROM jobs "
            "WHERE status IN ('scored','documents_generated','digest_sent','approved')"
        ).fetchone()[0],
        "dream": conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE dream_employer = 1").fetchone()[0],
        "last_run": conn.execute(
            "SELECT MAX(scored_at) FROM jobs WHERE scored_at IS NOT NULL"
        ).fetchone()[0],
    }

    # Applications tab — all scored jobs
    apps = [dict(r) for r in conn.execute("""
        SELECT id, title, company, score, salary_min, salary_max,
               status, url, created_at, applied_at, dream_employer,
               cv_path, cover_letter_path, rationale, platform
        FROM jobs
        WHERE score IS NOT NULL
        ORDER BY score DESC, created_at DESC
    """).fetchall()]

    # Pipeline tab — 75+ jobs
    pipeline = [dict(r) for r in conn.execute("""
        SELECT title, company, score, status, created_at, scored_at,
               applied_at, cv_path, url, dream_employer
        FROM jobs
        WHERE score >= 75
        ORDER BY COALESCE(scored_at, created_at) DESC
    """).fetchall()]

    # Weekly stats (last 10 weeks)
    weekly = [dict(r) for r in conn.execute("""
        SELECT
            strftime('%Y-W%W', created_at)                                   AS week,
            MIN(date(created_at))                                            AS week_start,
            COUNT(*)                                                         AS fetched,
            COUNT(CASE WHEN score IS NOT NULL THEN 1 END)                    AS scored,
            COUNT(CASE WHEN score >= 75 THEN 1 END)                          AS passed,
            COUNT(CASE WHEN status = 'applied' THEN 1 END)                   AS applied_count,
            ROUND(AVG(CASE WHEN score IS NOT NULL THEN CAST(score AS FLOAT) END), 1) AS avg_score
        FROM jobs
        GROUP BY week
        ORDER BY week DESC
        LIMIT 10
    """).fetchall()]

    # Top companies with at least one qualifying job
    companies = [dict(r) for r in conn.execute("""
        SELECT company,
               COUNT(*)                                                          AS total_seen,
               COUNT(CASE WHEN score >= 75 THEN 1 END)                          AS passed,
               CAST(ROUND(AVG(CAST(score AS FLOAT)), 0) AS INTEGER)             AS avg_score
        FROM jobs
        WHERE score IS NOT NULL AND TRIM(COALESCE(company,'')) != ''
        GROUP BY company
        HAVING passed > 0
        ORDER BY passed DESC, avg_score DESC
        LIMIT 15
    """).fetchall()]

    # Daily API cost (last 14 days)
    daily_cost = [dict(r) for r in conn.execute("""
        SELECT date(scored_at)  AS day,
               COUNT(*)         AS jobs_scored,
               ROUND(COUNT(*) * 0.014, 2) AS cost_usd
        FROM jobs
        WHERE scored_at IS NOT NULL
        GROUP BY day
        ORDER BY day DESC
        LIMIT 14
    """).fetchall()]

    conn.close()
    return dict(funnel=funnel, stats=stats, apps=apps, pipeline=pipeline,
                weekly=weekly, companies=companies, daily_cost=daily_cost)


# ── chart builders ────────────────────────────────────────────────────────────

def _svg_weekly_bars(weekly: list[dict]) -> str:
    weeks = list(reversed(weekly[:8]))
    if not weeks:
        return "<p style='color:#9ca3af;padding:20px'>No data yet.</p>"

    W, H = 640, 200
    pl, pr, pt, pb = 44, 12, 24, 36
    cw, ch = W - pl - pr, H - pt - pb

    max_val = max((w["fetched"] or 0) for w in weeks) or 1
    gw = cw / len(weeks)
    bw = gw * 0.32

    rects = ""
    labels = ""
    for i, w in enumerate(weeks):
        xc = pl + (i + 0.5) * gw
        for val, colour, dx in [
            (w["fetched"], "#bfdbfe", -bw * 0.55),
            (w["passed"],  "#16a34a", +bw * 0.05),
        ]:
            if not val:
                continue
            h = (val / max_val) * ch
            x = xc + dx
            y = pt + ch - h
            rects += (f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                      f'height="{h:.1f}" fill="{colour}" rx="2"/>')
            rects += (f'<text x="{x + bw/2:.1f}" y="{y - 3:.1f}" '
                      f'text-anchor="middle" font-size="9" fill="#374151">{val}</text>')
        lbl = w.get("week_start", w["week"])[:7]
        labels += (f'<text x="{xc:.1f}" y="{H - 4}" '
                   f'text-anchor="middle" font-size="9" fill="#6b7280">{lbl}</text>')

    grid = ""
    for pct in (0.25, 0.5, 0.75, 1.0):
        y = pt + ch * (1 - pct)
        v = int(max_val * pct)
        grid += (f'<line x1="{pl}" y1="{y:.1f}" x2="{W-pr}" y2="{y:.1f}" '
                 f'stroke="#f3f4f6" stroke-width="1"/>')
        grid += (f'<text x="{pl-4}" y="{y+3:.1f}" text-anchor="end" '
                 f'font-size="9" fill="#9ca3af">{v}</text>')

    legend = (
        f'<rect x="{pl}" y="4" width="10" height="10" fill="#bfdbfe" rx="1"/>'
        f'<text x="{pl+13}" y="13" font-size="10" fill="#374151">Fetched</text>'
        f'<rect x="{pl+65}" y="4" width="10" height="10" fill="#16a34a" rx="1"/>'
        f'<text x="{pl+78}" y="13" font-size="10" fill="#374151">Passed 75+</text>'
    )

    return (f'<svg viewBox="0 0 {W} {H}" style="width:100%;max-height:{H}px">'
            f'{grid}{rects}{labels}{legend}</svg>')


def _avg_score_bars(weekly: list[dict]) -> str:
    """Horizontal CSS bars for average score by week."""
    weeks = [w for w in reversed(weekly[:8]) if w.get("avg_score")]
    if not weeks:
        return "<p style='color:#9ca3af'>No data yet.</p>"
    rows = ""
    for w in weeks:
        lbl = w.get("week_start", w["week"])[:7]
        avg = w["avg_score"] or 0
        colour = "#16a34a" if avg >= 75 else "#2563eb" if avg >= 60 else "#d97706"
        rows += (
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
            f'<span style="width:70px;font-size:11px;color:#6b7280;flex-shrink:0">{lbl}</span>'
            f'<div style="flex:1;background:#f3f4f6;border-radius:4px;height:18px">'
            f'<div style="width:{avg}%;background:{colour};height:100%;border-radius:4px;'
            f'display:flex;align-items:center;padding-left:6px">'
            f'<span style="font-size:10px;color:#fff;font-weight:600">{avg}</span></div></div>'
            f'</div>'
        )
    return rows


# ── section builders ──────────────────────────────────────────────────────────

def _html_header(stats: dict) -> str:
    last = (stats["last_run"] or "never")[:16].replace("T", " ")
    return f"""
<div class="header-bar">
  <div>
    <div class="header-title">Job Agent Dashboard</div>
    <div class="header-sub">Last updated: {_esc(last)}</div>
  </div>
  <div class="quick-stats">
    <div class="qs-item"><span class="qs-num">{stats['total']:,}</span><span class="qs-lbl">Total</span></div>
    <div class="qs-item"><span class="qs-num qs-green">{stats['applied']}</span><span class="qs-lbl">Applied</span></div>
    <div class="qs-item"><span class="qs-num qs-amber">{stats['pending']}</span><span class="qs-lbl">Pending</span></div>
    <div class="qs-item"><span class="qs-num qs-gold">{'⭐ ' if stats['dream'] else ''}{stats['dream']}</span><span class="qs-lbl">Dream</span></div>
  </div>
</div>"""


def _html_funnel(f: dict) -> str:
    total = f["fetched"] or 1
    stages = [
        ("Fetched",    f["fetched"], "#2563eb"),
        ("Scored",     f["scored"],  "#7c3aed"),
        ("Passed 75+", f["passed"],  "#d97706"),
        ("Docs ready", f["docs"],    "#0891b2"),
        ("Applied",    f["applied"], "#16a34a"),
    ]
    items = ""
    for i, (label, count, colour) in enumerate(stages):
        pct = int(count / total * 100) if total else 0
        arrow = '<div class="funnel-arrow">›</div>' if i < len(stages) - 1 else ""
        items += f"""
    <div class="funnel-stage">
      <div class="funnel-count" style="color:{colour}">{count:,}</div>
      <div class="funnel-bar-wrap">
        <div class="funnel-bar" style="width:{pct}%;background:{colour}"></div>
      </div>
      <div class="funnel-label">{label}</div>
    </div>{arrow}"""
    return f'<div class="card"><div class="funnel-row">{items}</div></div>'


def _html_apps_table(apps: list[dict]) -> str:
    rows = ""
    for i, j in enumerate(apps):
        status = j.get("status", "")
        dream  = j.get("dream_employer", 0)
        score  = j.get("score")
        url    = _esc(j.get("url", "#"))
        ds     = "dream" if dream else "nodream"
        # sort keys: score/-1 for nulls, numeric salary, ISO date, lowercased text
        sk_score   = score if score is not None else -1
        sk_salary  = j.get("salary_min") or 0
        sk_date    = (j.get("created_at") or "")[:10]
        sk_company = _esc((j.get("company") or "").lower())
        sk_role    = _esc((j.get("title") or "").lower())
        rows += f"""
<tr data-status="{_esc(status)}" data-dream="{ds}" data-default-order="{i}"
    data-score="{sk_score}" data-company="{sk_company}" data-role="{sk_role}"
    data-salary="{sk_salary}" data-date="{sk_date}">
  <td class="tc">{_score_badge(score)}</td>
  <td class="tc">{"⭐" if dream else ""}</td>
  <td>{_esc(j.get("company"))}</td>
  <td><a href="{url}" target="_blank" class="job-link">{_esc(j.get("title"))}</a></td>
  <td class="mono">{_salary(j)}</td>
  <td class="mono">{_fmt_date(j.get("created_at"))}</td>
  <td>{_status_badge(status)}</td>
  <td><a href="{url}" target="_blank" class="btn-link">View ↗</a></td>
</tr>"""

    return f"""
<div id="tab-applications" class="tab-pane">
  <div class="filter-bar">
    <button class="filter-btn active" onclick="filterApps(this,'all')">All ({len(apps)})</button>
    <button class="filter-btn" onclick="filterApps(this,'applied')">Applied</button>
    <button class="filter-btn" onclick="filterApps(this,'pending')">Pending</button>
    <button class="filter-btn" onclick="filterApps(this,'dream')">⭐ Dream</button>
  </div>
  <div class="table-wrap">
    <table id="apps-table">
      <thead>
        <tr>
          <th class="sortable" data-col="score" data-numeric="1" onclick="sortApps(this)">Score</th>
          <th>⭐</th>
          <th class="sortable" data-col="company" onclick="sortApps(this)">Company</th>
          <th class="sortable" data-col="role" onclick="sortApps(this)">Role</th>
          <th class="sortable" data-col="salary" data-numeric="1" onclick="sortApps(this)">Salary</th>
          <th class="sortable" data-col="date" onclick="sortApps(this)">Date</th>
          <th class="sortable" data-col="status" onclick="sortApps(this)">Status</th>
          <th>Link</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>"""


def _html_pipeline(pipeline: list[dict]) -> str:
    if not pipeline:
        return '<div id="tab-pipeline" class="tab-pane"><p class="empty">No jobs have passed the threshold yet.</p></div>'

    # Group by ISO week of scored_at / created_at
    from collections import defaultdict
    by_week: dict[str, list] = defaultdict(list)
    for j in pipeline:
        ts = j.get("scored_at") or j.get("created_at") or ""
        week = ts[:7] if ts else "Unknown"  # YYYY-MM as week label
        by_week[week].append(j)

    sections = ""
    for week in sorted(by_week.keys(), reverse=True):
        jobs = by_week[week]
        rows = ""
        for j in jobs:
            status  = j.get("status", "")
            dream   = j.get("dream_employer", 0)
            url     = _esc(j.get("url", "#"))
            created = j.get("created_at") or ""
            applied = j.get("applied_at") or ""
            # Days in pipeline
            try:
                d0 = datetime.fromisoformat(created.replace("Z", "+00:00"))
                d1 = (datetime.fromisoformat(applied.replace("Z", "+00:00"))
                      if applied else datetime.now(timezone.utc))
                days = (d1 - d0).days
            except Exception:
                days = "—"
            docs = "✓" if j.get("cv_path") else "—"
            rows += f"""
<tr>
  <td class="tc">{_score_badge(j.get("score"))}</td>
  <td class="tc">{"⭐" if dream else ""}</td>
  <td><a href="{url}" target="_blank" class="job-link">{_esc(j.get("title"))}</a></td>
  <td>{_esc(j.get("company"))}</td>
  <td>{_status_badge(status)}</td>
  <td class="tc">{docs}</td>
  <td class="tc mono">{days}d</td>
</tr>"""
        sections += f"""
<div class="week-section">
  <div class="week-header">{week} &nbsp;<span style="color:#9ca3af;font-weight:400">({len(jobs)} job{"s" if len(jobs)!=1 else ""})</span></div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>Score</th><th>⭐</th><th>Role</th><th>Company</th>
        <th>Status</th><th>Docs</th><th>Age</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>"""

    return f'<div id="tab-pipeline" class="tab-pane" style="display:none">{sections}</div>'


def _html_stats(weekly: list[dict], companies: list[dict],
                daily_cost: list[dict]) -> str:
    # Weekly bar chart
    chart = _svg_weekly_bars(weekly)
    avg_bars = _avg_score_bars(weekly)

    # Companies table
    co_rows = ""
    for c in companies:
        co_rows += (
            f'<tr><td>{_esc(c["company"])}</td>'
            f'<td class="tc">{c["total_seen"]}</td>'
            f'<td class="tc">{c["passed"]}</td>'
            f'<td class="tc">{_score_badge(c.get("avg_score"))}</td></tr>'
        )
    co_table = f"""
<div class="table-wrap">
  <table>
    <thead><tr><th>Company</th><th>Seen</th><th>Passed 75+</th><th>Avg score</th></tr></thead>
    <tbody>{co_rows if co_rows else '<tr><td colspan="4" class="empty">No data</td></tr>'}</tbody>
  </table>
</div>"""

    # Cost table
    total_cost = sum(r["cost_usd"] for r in daily_cost)
    cost_rows = "".join(
        f'<tr><td class="mono">{_esc(r["day"])}</td>'
        f'<td class="tc">{r["jobs_scored"]}</td>'
        f'<td class="mono">${r["cost_usd"]:.2f}</td></tr>'
        for r in daily_cost
    )
    cost_table = f"""
<div class="table-wrap">
  <table>
    <thead><tr><th>Date</th><th>Jobs scored</th><th>Est. cost</th></tr></thead>
    <tbody>
      {cost_rows if cost_rows else '<tr><td colspan="3" class="empty">No data</td></tr>'}
      <tr style="font-weight:700;border-top:2px solid #e5e7eb">
        <td colspan="2">Total (shown period)</td>
        <td class="mono">${total_cost:.2f}</td>
      </tr>
    </tbody>
  </table>
</div>"""

    return f"""
<div id="tab-stats" class="tab-pane" style="display:none">
  <div class="stats-grid">
    <div class="card">
      <div class="card-title">📊 Jobs fetched vs passed — by week</div>
      {chart}
    </div>
    <div class="card">
      <div class="card-title">📈 Average score by week</div>
      {avg_bars}
    </div>
    <div class="card">
      <div class="card-title">🏢 Top companies (passing jobs)</div>
      {co_table}
    </div>
    <div class="card">
      <div class="card-title">💰 API cost tracker (est. $0.014 / job)</div>
      {cost_table}
    </div>
  </div>
</div>"""


# ── main HTML builder ─────────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f3f4f6; color: #111827; font-size: 14px; }

/* Header */
.header-bar { background: #111827; color: #fff; padding: 16px 24px;
              display: flex; justify-content: space-between; align-items: center;
              position: sticky; top: 0; z-index: 100; }
.header-title { font-size: 20px; font-weight: 700; }
.header-sub { color: #9ca3af; font-size: 12px; margin-top: 2px; }
.quick-stats { display: flex; gap: 24px; }
.qs-item { text-align: center; }
.qs-num { display: block; font-size: 22px; font-weight: 800; }
.qs-lbl { font-size: 11px; color: #9ca3af; }
.qs-green { color: #4ade80; }
.qs-amber { color: #fbbf24; }
.qs-gold  { color: #f59e0b; }

/* Content wrapper */
.content { max-width: 1100px; margin: 0 auto; padding: 20px 16px; }

/* Cards */
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
        padding: 20px; margin-bottom: 16px; }
.card-title { font-weight: 700; font-size: 13px; color: #374151;
              margin-bottom: 14px; }

/* Funnel */
.funnel-row { display: flex; align-items: center; gap: 0; }
.funnel-stage { flex: 1; padding: 4px 8px; }
.funnel-count { font-size: 26px; font-weight: 800; line-height: 1; }
.funnel-label { font-size: 11px; color: #6b7280; margin-top: 4px; }
.funnel-bar-wrap { background: #f3f4f6; border-radius: 3px; height: 6px;
                   margin: 5px 0; overflow: hidden; }
.funnel-bar { height: 100%; border-radius: 3px; min-width: 2px; }
.funnel-arrow { font-size: 24px; color: #d1d5db; padding: 0 2px; flex-shrink: 0; }

/* Tabs */
.tab-nav { display: flex; gap: 0; margin-bottom: 0;
           border-bottom: 2px solid #e5e7eb; }
.tab-btn { background: none; border: none; padding: 10px 22px; font-size: 14px;
           font-weight: 600; color: #6b7280; cursor: pointer; border-bottom: 2px solid transparent;
           margin-bottom: -2px; }
.tab-btn.active { color: #2563eb; border-bottom-color: #2563eb; }
.tab-btn:hover { color: #374151; }
.tab-pane { padding-top: 20px; }

/* Filter buttons */
.filter-bar { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.filter-btn { background: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 20px;
              padding: 5px 14px; font-size: 12px; font-weight: 600; color: #374151;
              cursor: pointer; }
.filter-btn.active { background: #2563eb; color: #fff; border-color: #2563eb; }
.filter-btn:hover:not(.active) { background: #e5e7eb; }

/* Tables */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; background: #fff;
        border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }
th { padding: 8px 12px; font-size: 11px; font-weight: 700; color: #6b7280;
     text-align: left; background: #f9fafb; border-bottom: 1px solid #e5e7eb; }
th.sortable { cursor: pointer; user-select: none; }
th.sortable:hover { background: #eff6ff; color: #374151; }
th.sort-asc::after  { content: ' ↑'; color: #2563eb; font-weight: 400; }
th.sort-desc::after { content: ' ↓'; color: #2563eb; font-weight: 400; }
td { padding: 9px 12px; border-top: 1px solid #f3f4f6; vertical-align: middle; }
tr:hover td { background: #fafafa; }
.tc { text-align: center; }
.mono { font-family: monospace; font-size: 12px; }

/* Badges */
.badge { padding: 2px 8px; border-radius: 10px; font-size: 11px;
         font-weight: 700; display: inline-block; }
.badge-green  { background: #dcfce7; color: #15803d; }
.badge-blue   { background: #dbeafe; color: #1d4ed8; }
.badge-amber  { background: #fef3c7; color: #92400e; }
.badge-orange { background: #ffedd5; color: #c2410c; }
.badge-gray   { background: #f3f4f6; color: #6b7280; }

/* Links */
.job-link { color: #1d4ed8; text-decoration: none; font-weight: 500; }
.job-link:hover { text-decoration: underline; }
.btn-link { background: #f3f4f6; color: #374151; padding: 3px 10px;
            border-radius: 5px; text-decoration: none; font-size: 12px;
            border: 1px solid #e5e7eb; white-space: nowrap; }
.btn-link:hover { background: #e5e7eb; }

/* Pipeline */
.week-section { margin-bottom: 24px; }
.week-header { font-size: 14px; font-weight: 700; color: #374151;
               margin-bottom: 8px; padding-bottom: 6px;
               border-bottom: 2px solid #e5e7eb; }

/* Stats grid */
.stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 700px) { .stats-grid { grid-template-columns: 1fr; } }

/* Misc */
.empty { color: #9ca3af; font-style: italic; text-align: center; padding: 20px; }
"""

_JS = """
function showTab(name) {
  document.querySelectorAll('.tab-pane').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).style.display = '';
  event.currentTarget.classList.add('active');
}

function filterApps(btn, filter) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const pending = ['scored','documents_generated','digest_sent','approved'];
  document.querySelectorAll('#apps-table tbody tr').forEach(row => {
    const status = row.dataset.status;
    const dream  = row.dataset.dream === 'dream';
    let show = false;
    if (filter === 'all')     show = true;
    if (filter === 'applied') show = status === 'applied';
    if (filter === 'pending') show = pending.includes(status);
    if (filter === 'dream')   show = dream;
    row.style.display = show ? '' : 'none';
  });
}

let _sortCol = null, _sortDir = 0;

function sortApps(th) {
  const col = th.dataset.col;
  const numeric = th.dataset.numeric === '1';

  // Cycle: new col → asc; same col asc → desc; same col desc → reset default
  if (_sortCol === col) {
    if (_sortDir === 1) _sortDir = -1;
    else { _sortDir = 0; _sortCol = null; }
  } else {
    _sortCol = col;
    _sortDir = 1;
  }

  // Update header indicators
  document.querySelectorAll('#apps-table th[data-col]').forEach(h =>
    h.classList.remove('sort-asc', 'sort-desc')
  );
  if (_sortDir !== 0) {
    th.classList.add(_sortDir === 1 ? 'sort-asc' : 'sort-desc');
  }

  const tbody = document.querySelector('#apps-table tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));

  if (_sortDir === 0) {
    // Restore original SQL order (score desc)
    rows.sort((a, b) => +a.dataset.defaultOrder - +b.dataset.defaultOrder);
  } else {
    rows.sort((a, b) => {
      const av = a.dataset[col], bv = b.dataset[col];
      if (numeric) return _sortDir * ((+av || 0) - (+bv || 0));
      return _sortDir * av.localeCompare(bv);
    });
  }
  rows.forEach(r => tbody.appendChild(r));
}
"""


def build_dashboard_html(data: dict) -> str:
    now = datetime.now().strftime("%d %b %Y %H:%M")

    header    = _html_header(data["stats"])
    funnel    = _html_funnel(data["funnel"])
    apps      = _html_apps_table(data["apps"])
    pipeline  = _html_pipeline(data["pipeline"])
    stats_tab = _html_stats(data["weekly"], data["companies"], data["daily_cost"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Job Agent Dashboard — {now}</title>
  <style>{_CSS}</style>
</head>
<body>

{header}

<div class="content">

  {funnel}

  <div class="card" style="padding:0 20px 0">
    <div class="tab-nav">
      <button class="tab-btn active" onclick="showTab('applications')">Applications</button>
      <button class="tab-btn" onclick="showTab('pipeline')">Pipeline</button>
      <button class="tab-btn" onclick="showTab('stats')">Stats</button>
    </div>
    {apps}
    {pipeline}
    {stats_tab}
  </div>

  <div style="text-align:center;color:#9ca3af;font-size:11px;padding:16px 0 8px">
    Job Agent &bull; Generated {now} &bull; Powered by Claude AI
  </div>

</div>

<script>{_JS}</script>
</body>
</html>"""


# ── entry point ───────────────────────────────────────────────────────────────

def generate_dashboard() -> None:
    data = _fetch_data()
    html = build_dashboard_html(data)

    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"[Dashboard] Written → {OUT_PATH}  "
          f"({len(data['apps'])} scored jobs, {len(data['pipeline'])} passed threshold)")

    # Mirror to Windows
    try:
        WINDOWS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT_PATH, WINDOWS_DIR / "dashboard.html")
        print(f"[Dashboard] Copied  → {WINDOWS_DIR / 'dashboard.html'}")
    except Exception as e:
        print(f"[Dashboard] Windows copy skipped: {e}")


if __name__ == "__main__":
    generate_dashboard()
