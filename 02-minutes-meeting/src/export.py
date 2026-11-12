"""Export minutes as Markdown or a styled Word document."""
from __future__ import annotations

import io
import re

NAVY = "1B2A49"
GOLD = "B08D57"
INK = "2B2B2B"
MUTED = "6B6B6B"
LINE = "D9D4C7"
SOFT = "F4F0E6"

FOOTER = "Generated locally with Whisper and Llama 3.2 · Reviewed by a human before circulation"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text or "").strip("-").lower()
    return slug[:60] or "meeting-minutes"


def _dash(value: str) -> str:
    return value if value else "—"


def _meta_lines(meta: dict) -> list[tuple[str, str]]:
    rows = [
        ("Date", meta.get("date", "")),
        ("Source", meta.get("source", "")),
        ("Duration", meta.get("duration", "")),
        ("Attendees", meta.get("attendees", "")),
    ]
    return [(k, v) for k, v in rows if v]


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def to_markdown(minutes: dict, meta: dict) -> str:
    title = meta.get("title") or minutes.get("title") or "Meeting Minutes"
    out = [f"# {title}", ""]
    for key, value in _meta_lines(meta):
        out.append(f"**{key}:** {value}  ")
    out.append("")

    if minutes["executive_summary"]:
        out += ["## Executive Summary", "", minutes["executive_summary"], ""]
    if minutes["participants"]:
        out += ["## Participants", ""] + [f"- {p}" for p in minutes["participants"]] + [""]
    if minutes["discussion_points"]:
        out += ["## Discussion", ""]
        for p in minutes["discussion_points"]:
            stamp = f"[{p.get('timestamp')}] " if p.get("timestamp") else ""
            out.append(f"- {stamp}**{p['topic']}** — {p['detail']}" if p["topic"] else f"- {stamp}{p['detail']}")
        out.append("")
    if minutes["decisions"]:
        out += ["## Decisions", ""] + [f"- {d}" for d in minutes["decisions"]] + [""]
    if minutes["action_items"]:
        out += ["## Action Items", "", "| Task | Owner | Deadline |", "|---|---|---|"]
        for a in minutes["action_items"]:
            task = a["task"].replace("|", "/")
            out.append(f"| {task} | {_dash(a['owner'])} | {_dash(a['deadline'])} |")
        out.append("")
    if minutes["open_questions"]:
        out += ["## Open Questions", ""] + [f"- {q}" for q in minutes["open_questions"]] + [""]

    out += ["---", f"*{FOOTER}*", ""]
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Word (.docx)
# --------------------------------------------------------------------------- #
def _rgb(hex_color: str):
    from docx.shared import RGBColor

    return RGBColor.from_string(hex_color)


def _shade(cell, fill: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _bottom_rule(paragraph, color: str = GOLD, size: str = "8") -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), size)
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)
    p_pr.append(borders)


def _table_borders(table, color: str = LINE) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    tbl_pr.append(borders)


def _run(paragraph, text, *, font="Calibri", size=10.5, bold=False, italic=False, color=INK):
    from docx.shared import Pt

    run = paragraph.add_run(text)
    run.font.name = font
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = _rgb(color)
    return run


def _heading(doc, text):
    from docx.shared import Pt

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    _run(p, text.upper(), font="Georgia", size=11.5, bold=True, color=NAVY)
    _bottom_rule(p, color=LINE, size="6")
    return p


def _bullet(doc, text, topic=""):
    from docx.shared import Pt

    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    if topic:
        _run(p, topic, bold=True, color=NAVY)
        _run(p, f" — {text}")
    else:
        _run(p, text)
    return p


def to_docx_bytes(minutes: dict, meta: dict) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    doc = Document()
    section = doc.sections[0]
    section.left_margin = section.right_margin = Cm(2.3)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)

    title = meta.get("title") or minutes.get("title") or "Meeting Minutes"

    kicker = doc.add_paragraph()
    _run(kicker, "MEETING MINUTES", font="Calibri", size=9, bold=True, color=GOLD)
    kicker.paragraph_format.space_after = Pt(2)

    head = doc.add_paragraph()
    _run(head, title, font="Georgia", size=24, bold=True, color=NAVY)
    head.paragraph_format.space_after = Pt(4)
    _bottom_rule(head, color=GOLD, size="12")

    meta_rows = _meta_lines(meta)
    if meta_rows:
        table = doc.add_table(rows=0, cols=2)
        table.autofit = True
        for key, value in meta_rows:
            cells = table.add_row().cells
            cells[0].width = Cm(3.0)
            _run(cells[0].paragraphs[0], key.upper(), size=8.5, bold=True, color=MUTED)
            _run(cells[1].paragraphs[0], value, size=10)

    if minutes["executive_summary"]:
        _heading(doc, "Executive summary")
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = 1.2
        _run(p, minutes["executive_summary"], size=11)

    if minutes["participants"]:
        _heading(doc, "Participants")
        for name in minutes["participants"]:
            _bullet(doc, name)

    if minutes["discussion_points"]:
        _heading(doc, "Discussion")
        for pt in minutes["discussion_points"]:
            prefix = f"[{pt.get('timestamp')}] " if pt.get("timestamp") else ""
            _bullet(doc, prefix + pt["detail"], topic=pt["topic"])

    if minutes["decisions"]:
        _heading(doc, "Decisions")
        for d in minutes["decisions"]:
            _bullet(doc, d)

    if minutes["action_items"]:
        _heading(doc, "Action items")
        table = doc.add_table(rows=1, cols=3)
        _table_borders(table)
        widths = (Cm(9.0), Cm(3.6), Cm(3.6))
        for i, label in enumerate(("TASK", "OWNER", "DEADLINE")):
            cell = table.rows[0].cells[i]
            cell.width = widths[i]
            _shade(cell, NAVY)
            _run(cell.paragraphs[0], label, size=9, bold=True, color="FFFFFF")
        for n, item in enumerate(minutes["action_items"]):
            cells = table.add_row().cells
            for i, value in enumerate((item["task"], _dash(item["owner"]), _dash(item["deadline"]))):
                cells[i].width = widths[i]
                if n % 2:
                    _shade(cells[i], SOFT)
                _run(cells[i].paragraphs[0], value, size=10)

    if minutes["open_questions"]:
        _heading(doc, "Open questions")
        for q in minutes["open_questions"]:
            _bullet(doc, q)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(footer, FOOTER, size=8, italic=True, color=MUTED)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def to_pdf_bytes(minutes: dict, meta: dict) -> bytes:
    """Create a compact PDF export using ReportLab."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    except ImportError as exc:
        raise RuntimeError("PDF export requires reportlab. Install it with: pip install reportlab") from exc
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.8*cm, leftMargin=1.8*cm, topMargin=1.7*cm, bottomMargin=1.7*cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="MeetingTitle", parent=styles["Title"], textColor=colors.HexColor("#"+NAVY), fontName="Helvetica-Bold", fontSize=21, leading=25, alignment=0, spaceAfter=8))
    styles.add(ParagraphStyle(name="SectionHead", parent=styles["Heading2"], textColor=colors.HexColor("#"+NAVY), fontSize=12, leading=15, spaceBefore=12, spaceAfter=5))
    styles.add(ParagraphStyle(name="SmallBody", parent=styles["BodyText"], fontSize=9, leading=13, spaceAfter=4))
    esc = lambda x: (str(x or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")).replace("\n", "<br/>")
    story = [Paragraph(esc(meta.get("title") or minutes.get("title") or "Meeting Minutes"), styles["MeetingTitle"])]
    for k, v in _meta_lines(meta): story.append(Paragraph(f"<b>{esc(k)}:</b> {esc(v)}", styles["SmallBody"]))
    def section(title, values):
        if values:
            story.append(Paragraph(esc(title), styles["SectionHead"]))
            for value in values: story.append(Paragraph("• " + esc(value), styles["SmallBody"]))
    if minutes.get("executive_summary"): section("Executive Summary", [minutes["executive_summary"]])
    section("Participants", minutes.get("participants", []))
    points = [((f"[{p.get('timestamp')}] " if p.get("timestamp") else "") + ((p.get("topic") + ": ") if p.get("topic") else "") + p.get("detail", "")) for p in minutes.get("discussion_points", [])]
    section("Discussion", points)
    section("Decisions", minutes.get("decisions", []))
    actions = minutes.get("action_items", [])
    if actions:
        story.append(Paragraph("Action Items", styles["SectionHead"]))
        data = [["Task", "Owner", "Deadline"]] + [[Paragraph(esc(a.get("task")), styles["SmallBody"]), Paragraph(esc(a.get("owner") or "—"), styles["SmallBody"]), Paragraph(esc(a.get("deadline") or "—"), styles["SmallBody"])] for a in actions]
        table = Table(data, colWidths=[9.2*cm, 3.1*cm, 3.1*cm], repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#"+NAVY)),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#"+LINE)),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#"+SOFT)]),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6)]))
        story.append(table)
    section("Open Questions", minutes.get("open_questions", []))
    doc.build(story)
    return buffer.getvalue()
