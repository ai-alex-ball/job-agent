"""
documents.py — Phase 2 document generation
Produces a tailored CV and cover letter as .docx files for every job that
scores 75+ and has proceed=true.
"""

import json
import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from config import PROFILE_PATH, BASE_DIR

OUTPUTS_DIR = BASE_DIR / "outputs"

# Load profile once
_PROFILE: dict | None = None


def _profile() -> dict:
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = json.loads(PROFILE_PATH.read_text())
    return _PROFILE


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_documents(job: dict) -> tuple[str, str]:
    """
    Generate a tailored CV and cover letter for a job that passed scoring.
    Returns (cv_path, cover_letter_path) as strings relative to BASE_DIR.
    """
    OUTPUTS_DIR.mkdir(exist_ok=True)
    profile = _profile()

    slug = _make_slug(job)
    today = date.today().strftime("%Y-%m-%d")

    cv_path = OUTPUTS_DIR / f"cv_{slug}_{today}.docx"
    cl_path = OUTPUTS_DIR / f"coverletter_{slug}_{today}.docx"

    matched_skills = json.loads(job.get("matched_skills") or "[]")

    _build_cv(profile, job, matched_skills, cv_path)
    _build_cover_letter(profile, job, cl_path)

    # Return paths relative to project root for clean display
    return str(cv_path.relative_to(BASE_DIR)), str(cl_path.relative_to(BASE_DIR))


_ROLE_WORD = re.compile(
    r"\b(Lead|Director|Manager|Officer|Head|Partner|Advisor|Associate|Consultant|Specialist|Executive)\b"
)


def _clean_job_title(title: str) -> str:
    """Insert ' / ' between two concatenated role titles if detected.

    e.g. 'Technology, Product and Innovation Lead Incubation Lead'
      -> 'Technology, Product and Innovation Lead / Incubation Lead'
    """
    matches = list(_ROLE_WORD.finditer(title))
    if len(matches) >= 2:
        end = matches[0].end()
        if re.match(r"\s+[A-Z]", title[end:]):
            return title[:end] + " /" + title[end:]
    return title


def _make_slug(job: dict) -> str:
    def clean(s: str) -> str:
        s = re.sub(r"[^\w\s]", "", s or "unknown").strip()[:32]
        return re.sub(r"\s+", "_", s).lower()

    slug = f"{clean(job.get('company'))}_{clean(job.get('title'))}"
    return re.sub(r"_+", "_", slug).strip("_")


# ---------------------------------------------------------------------------
# Shared style helpers
# ---------------------------------------------------------------------------

def _font(run, size: float, bold=False, italic=False, color: tuple | None = None):
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)


def _spacing(para, before=0, after=2, line=None):
    fmt = para.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    if line:
        fmt.line_spacing = Pt(line)


def _section_heading(doc: Document, text: str):
    """11pt bold Arial, no border, 14pt before / 3pt after — matches master_cv.docx."""
    p = doc.add_paragraph()
    _spacing(p, before=14, after=3)
    run = p.add_run(text.upper())
    _font(run, 11, bold=True)
    return p


def _remove_table_borders(tbl):
    """Strip all borders from a table (used for layout tables)."""
    tbl_el = tbl._tbl
    tbl_pr = tbl_el.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl_el.insert(0, tbl_pr)
    tbl_borders = OxmlElement("w:tblBorders")
    for name in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{name}")
        b.set(qn("w:val"), "none")
        b.set(qn("w:sz"), "0")
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), "auto")
        tbl_borders.append(b)
    tbl_pr.append(tbl_borders)


# ---------------------------------------------------------------------------
# CV builder
# ---------------------------------------------------------------------------

def _build_cv(profile: dict, job: dict, matched_skills: list[str], path: Path):
    doc = Document()

    # 0.62" margins all sides — matches master_cv.docx
    for sec in doc.sections:
        sec.top_margin = Inches(0.62)
        sec.bottom_margin = Inches(0.62)
        sec.left_margin = Inches(0.62)
        sec.right_margin = Inches(0.62)

    # Baseline: Arial 10pt
    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(2)

    personal = profile["personal"]
    metrics = profile.get("key_metrics", {})

    # ── Name ─────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    _spacing(p, before=0, after=2)
    _font(p.add_run(personal["name"].upper()), 28, bold=True)

    # ── Contact line ──────────────────────────────────────────────────────────
    parts = [
        personal.get("location", ""),
        personal.get("email", ""),
        personal.get("phone", ""),
        personal.get("linkedin", "").replace("https://www.", "").replace("https://", ""),
        personal.get("website", "").replace("https://www.", "").replace("https://", ""),
    ]
    contact_p = doc.add_paragraph()
    _spacing(contact_p, before=4, after=8)
    _font(contact_p.add_run("  |  ".join(pt for pt in parts if pt)), 9, color=(90, 90, 90))

    # ── Professional Summary ──────────────────────────────────────────────────
    _section_heading(doc, "Professional Summary")
    sp = doc.add_paragraph()
    _spacing(sp, before=3, after=6)
    _font(sp.add_run(profile["summary"]), 10)

    # ── Career at a Glance ────────────────────────────────────────────────────
    _section_heading(doc, "Career at a Glance")
    stats = [
        (f"{metrics.get('years_experience', 23)} Years", "Experience"),
        (f"{metrics.get('startups_mentored', 200)}+", "Startups Mentored"),
        (str(metrics.get("startups_incubated", 88)), "Startups Incubated"),
        (str(metrics.get("portfolio_raised", "£12m+")), "Portfolio Raised"),
        (str(metrics.get("cost_savings_delivered", "€3.2m")), "Cost Savings Delivered"),
    ]

    tbl = doc.add_table(rows=2, cols=len(stats))
    _remove_table_borders(tbl)
    for i, (value, label) in enumerate(stats):
        val_cell = tbl.rows[0].cells[i]
        val_cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        _spacing(val_cell.paragraphs[0], before=4, after=1)
        _font(val_cell.paragraphs[0].add_run(value), 14, bold=True)

        lbl_cell = tbl.rows[1].cells[i]
        lbl_cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        _spacing(lbl_cell.paragraphs[0], before=0, after=6)
        _font(lbl_cell.paragraphs[0].add_run(label), 8, color=(90, 90, 90))

    # ── Experience ────────────────────────────────────────────────────────────
    _section_heading(doc, "Experience")

    matched_lower = [s.lower() for s in matched_skills]

    # Split: recent full roles get bullets; old part-time roles go to Earlier Career
    main_roles = []
    earlier_roles = []
    for role in profile["career_history"]:
        start_year = int(str(role["start"])[:4])
        is_old_parttime = role.get("type") == "part-time" and start_year < 2020
        if start_year < 2007 or is_old_parttime:
            earlier_roles.append(role)
        else:
            main_roles.append(role)

    for role in main_roles:
        start_year = int(str(role["start"])[:4])
        max_bullets = 4 if start_year >= 2015 else 3

        # Title · Company
        rp = doc.add_paragraph()
        _spacing(rp, before=10, after=3)
        _font(rp.add_run(role["title"]), 11, bold=True)
        _font(rp.add_run("  ·  "), 10, color=(140, 140, 140))
        _font(rp.add_run(role["company"]), 11, bold=True)

        # Location  |  Dates
        mp = doc.add_paragraph()
        _spacing(mp, before=0, after=2)
        dates = f"{role['start']} – {str(role['end']).capitalize()}"
        loc = role.get("location", "")
        _font(mp.add_run(f"{loc}  |  {dates}" if loc else dates), 9,
              italic=True, color=(110, 110, 110))

        # Bullets sorted by matched-skill relevance
        bullets = list(role.get("achievements", []))
        bullets.sort(key=lambda b: -sum(1 for s in matched_lower if s in b.lower()))

        for bullet in bullets[:max_bullets]:
            bp = doc.add_paragraph()
            bp.paragraph_format.space_before = Pt(2)
            bp.paragraph_format.space_after = Pt(2)
            bp.paragraph_format.left_indent = Inches(0.25)
            bp.paragraph_format.first_line_indent = Inches(-0.15)
            _font(bp.add_run("▸  " + bullet), 10)

    # ── Earlier Career ────────────────────────────────────────────────────────
    if earlier_roles:
        ec = doc.add_paragraph()
        _spacing(ec, before=10, after=3)
        _font(ec.add_run("Earlier Career"), 10, bold=True)
        for role in earlier_roles:
            dates = f"{role['start']} – {str(role['end']).capitalize()}"
            ep = doc.add_paragraph()
            _spacing(ep, before=0, after=2)
            _font(ep.add_run(role["company"] + " — "), 10, bold=True)
            _font(ep.add_run(role["title"]), 10)
            _font(ep.add_run(f"  ({dates})"), 9, color=(110, 110, 110))

    # ── Education & Qualifications ────────────────────────────────────────────
    _section_heading(doc, "Education & Qualifications")
    for edu in profile.get("education", []):
        ep = doc.add_paragraph()
        ep.paragraph_format.space_before = Pt(2)
        ep.paragraph_format.space_after = Pt(2)
        ep.paragraph_format.left_indent = Inches(0.25)
        ep.paragraph_format.first_line_indent = Inches(-0.15)
        _font(ep.add_run("▸  " + edu), 10)

    # ── Key Skills ────────────────────────────────────────────────────────────
    _section_heading(doc, "Key Skills")
    for category, skill_list in profile.get("skills", {}).items():
        kp = doc.add_paragraph()
        _spacing(kp, before=1, after=1)
        _font(kp.add_run(category.replace("_", " ").title() + ": "), 10, bold=True)
        _font(kp.add_run(", ".join(skill_list)), 10)

    doc.save(path)
    print(f"[Documents] CV saved: {path.name}")


# ---------------------------------------------------------------------------
# Cover letter builder
# ---------------------------------------------------------------------------

def _build_cover_letter(profile: dict, job: dict, path: Path):
    doc = Document()

    for sec in doc.sections:
        sec.top_margin = Inches(1.0)
        sec.bottom_margin = Inches(1.0)
        sec.left_margin = Inches(1.15)
        sec.right_margin = Inches(1.15)

    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = Pt(11)

    personal = profile["personal"]

    def line(text: str, bold=False, italic=False, size=11,
             color: tuple | None = None, after=2):
        p = doc.add_paragraph()
        _spacing(p, before=0, after=after)
        _font(p.add_run(text), size, bold=bold, italic=italic, color=color)
        return p

    # ── Sender block ──────────────────────────────────────────────────────────
    line(personal["name"], bold=True, size=13)
    line(personal.get("location", ""), size=10, color=(90, 90, 90))
    line(personal.get("email", ""), size=10, color=(90, 90, 90))
    line(personal.get("phone", ""), size=10, color=(90, 90, 90))
    line(personal.get("linkedin", ""), size=10, color=(90, 90, 90))

    doc.add_paragraph()  # spacer

    # ── Date ──────────────────────────────────────────────────────────────────
    line(date.today().strftime("%d %B %Y"))

    doc.add_paragraph()  # spacer

    # ── Addressee block ───────────────────────────────────────────────────────
    if job.get("title"):
        line(_clean_job_title(job["title"]), bold=True)
    if job.get("company"):
        line(job["company"])

    doc.add_paragraph()  # spacer

    # ── Salutation ────────────────────────────────────────────────────────────
    line("Dear Hiring Team,")
    doc.add_paragraph()

    # ── Body ──────────────────────────────────────────────────────────────────
    cover_text = job.get("cover_letter") or ""
    if cover_text:
        # Split on double newlines; fall back to single if needed
        paras = [p.strip() for p in cover_text.split("\n\n") if p.strip()]
        if len(paras) == 1:
            paras = [p.strip() for p in cover_text.split("\n") if p.strip()]
        for para_text in paras:
            para_text = re.sub(r"\*\*(.+?)\*\*", r"\1", para_text)  # strip markdown bold
            p = doc.add_paragraph()
            _spacing(p, before=0, after=10)
            _font(p.add_run(para_text), 11)
    else:
        p = doc.add_paragraph()
        _font(p.add_run("[Cover letter text not available.]"), 11, italic=True)

    # ── Sign-off ──────────────────────────────────────────────────────────────
    line("Yours sincerely,")
    doc.add_paragraph()  # space for physical signature
    doc.add_paragraph()
    line(personal["name"], bold=True)

    doc.save(path)
    print(f"[Documents] Cover letter saved: {path.name}")
