"""Course exports in one corporate style: PDF learner book, PDF answer key, PowerPoint trainer deck, Word (editable),
Excel quiz bank + tracker, PDF certificates, and a zip "learning pack" with all of them."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

BROWN, BROWN2, GOLD, GOLD_SOFT, INK, MUTED, LINE, BG = "#2A1A11", "#94481A", "#B8860B", "#F6ECD4", "#1F1915", "#766C63", "#E7E2DC", "#FAF8F5"
GOOD, WARN, BAD, BLUE = "#2E7D4F", "#B7791F", "#B3261E", "#3A6EA5"
PAL = ["#94481A", "#B8860B", "#3A6EA5", "#2E7D4F", "#8E5BA8", "#C2410C"]
ASSETS = Path(__file__).resolve().parents[1] / "assets"


def safe_name(s: str) -> str:
    return re.sub(r"[^\w\-& ]+", "", s).strip()[:80] or "Course"


def _questions(content: dict) -> list[tuple[str, int, dict]]:
    out = []
    for mi, m in enumerate(content.get("modules", [])):
        for q in m.get("quiz", []):
            out.append((m["title"], mi + 1, q))
    for q in content.get("exam", []):
        out.append(("Final assessment", 0, q))
    return out


def _answer_text(q: dict) -> str:
    if q["type"] in ("mcq", "tf"):
        return f"{'ABCDEFGH'[q['answer']]}. {q['options'][q['answer']]}"
    return str(q.get("answer", ""))


# ============================================================================================== PDF
def _pdf(content: dict, path: str, answers: bool = False) -> None:
    from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (CondPageBreak, Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    C = colors.HexColor
    PW, PH = A4
    W = PW - 36 * mm
    base = dict(fontName="Helvetica", textColor=C(INK))
    s_body = ParagraphStyle("b", fontSize=10.2, leading=15, spaceAfter=5, **base)
    s_small = ParagraphStyle("sm", fontSize=8.6, leading=11.5, textColor=C(MUTED), fontName="Helvetica")
    s_h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=C(BROWN), spaceAfter=6)
    s_h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=C(BROWN), spaceBefore=6, spaceAfter=6)
    s_h3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=C(BROWN2), spaceBefore=8, spaceAfter=4)
    s_cell = ParagraphStyle("c", fontSize=8.8, leading=11.5, **base)
    s_cellh = ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=8.8, leading=11.5, textColor=colors.white)

    def esc(s: Any) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def boxed(flow, bg, border, pad=9, left=None):
        t = Table([[flow]], colWidths=[W])
        st = [("BACKGROUND", (0, 0), (-1, -1), C(bg)), ("LEFTPADDING", (0, 0), (-1, -1), pad + 2), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
              ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad), ("BOX", (0, 0), (-1, -1), 0.6, C(border))]
        if left:
            st.append(("LINEBEFORE", (0, 0), (0, -1), 3.2, C(left)))
        t.setStyle(TableStyle(st))
        return t

    def bullets(items, color=GOLD):
        return ListFlowable([ListItem(Paragraph(esc(i), s_body), leftIndent=12, value="circle") for i in items], bulletType="bullet",
                            bulletColor=C(color), bulletFontSize=7, leftIndent=14)

    def chart(b):
        if b["kind"] == "hbar" and any(v < 0 for s_ in b["series"] for v in s_["values"]):
            b = dict(b, kind="bar")                           # negative bars read better upright
        labels = [str(x) for x in b["labels"]]
        series = b["series"]
        h = 62 * mm if b["kind"] != "hbar" else max(40 * mm, 9 * mm * len(labels) + 16 * mm)
        d = Drawing(W, h)
        allv = [v for s in series for v in s["values"]] or [0]
        lo, hi = min(0, min(allv)), max(allv) or 1
        if b["kind"] == "line":
            c = HorizontalLineChart()
            c.x, c.y, c.width, c.height = 40, 26, W - 70, h - 46
            c.data = [s["values"] for s in series]
            c.categoryAxis.categoryNames = labels
            for i in range(len(series)):
                c.lines[i].strokeColor = C(PAL[i % len(PAL)])
                c.lines[i].strokeWidth = 2.2
        elif b["kind"] == "hbar":
            c = HorizontalBarChart()
            c.x, c.y, c.width, c.height = 110, 14, W - 150, h - 24
            c.data = [s["values"] for s in series]
            c.categoryAxis.categoryNames = labels
            c.bars.strokeColor = None
            for i in range(len(series)):
                c.bars[i].fillColor = C(PAL[i % len(PAL)])
            c.barLabelFormat = "%.0f"
            c.barLabels.fontSize = 7.5
            c.barLabels.nudge = 8
        else:
            c = VerticalBarChart()
            c.x, c.y, c.width, c.height = 40, 26, W - 70, h - 46
            c.data = [s["values"] for s in series]
            c.categoryAxis.categoryNames = labels
            c.bars.strokeColor = None
            c.groupSpacing = 8
            for i in range(len(series)):
                c.bars[i].fillColor = C(PAL[i % len(PAL)])
            c.barLabelFormat = "%.0f"
            c.barLabels.fontSize = 7.5
            c.barLabels.nudge = 7
        c.valueAxis.valueMin = lo * 1.15 if lo < 0 else 0
        c.valueAxis.valueMax = hi * 1.18
        c.valueAxis.labels.fontSize = 7.5
        c.valueAxis.strokeColor = C(LINE)
        c.valueAxis.gridStrokeColor = C(LINE)
        c.valueAxis.visibleGrid = True
        c.categoryAxis.labels.fontSize = 7.8
        c.categoryAxis.strokeColor = C(LINE)
        d.add(c)
        if len(series) > 1:
            x = 40
            for i, s in enumerate(series):
                d.add(Rect(x, h - 10, 8, 8, fillColor=C(PAL[i % len(PAL)]), strokeColor=None))
                d.add(String(x + 11, h - 9, s["name"], fontSize=7.5, fillColor=C(MUTED)))
                x += 16 + 5 * len(s["name"])
        title = Paragraph(f"<b>{esc(b.get('title', ''))}</b>" + (f" <font color='{MUTED}' size=8>({esc(b['unit'])})</font>" if b.get("unit") else ""), s_cell)
        return KeepTogether([title, Spacer(1, 2 * mm), d, Paragraph("Example figures for learning.", s_small), Spacer(1, 3 * mm)])

    def steps(b):
        items = b["items"]
        per = 4 if len(items) > 3 else len(items)
        rows = [items[i:i + per] for i in range(0, len(items), per)]
        bw, gap = (W - (per - 1) * 9 * mm) / per, 9 * mm
        bh = 30 * mm
        d = Drawing(W, len(rows) * (bh + 6 * mm))
        n = 0
        for r, row in enumerate(rows):
            y = d.height - (r + 1) * (bh + 6 * mm) + 6 * mm
            for i, txt in enumerate(row):
                x = i * (bw + gap)
                n += 1
                d.add(Rect(x, y, bw, bh, rx=7, ry=7, fillColor=C(GOLD_SOFT if n % 2 else "#FFFFFF"), strokeColor=C(GOLD), strokeWidth=0.9))
                d.add(Rect(x + 6, y + bh - 17, 13, 13, rx=6.5, ry=6.5, fillColor=C(BROWN), strokeColor=None))
                d.add(String(x + 12.5, y + bh - 13.5, str(n), fontSize=8, fillColor=colors.white, textAnchor="middle", fontName="Helvetica-Bold"))
                words, lines, cur = txt.split(), [], ""
                maxc = max(14, int(bw / 4.3))
                for w in words:
                    if len(cur) + len(w) + 1 > maxc:
                        lines.append(cur)
                        cur = w
                    else:
                        cur = (cur + " " + w).strip()
                lines.append(cur)
                for li, line in enumerate(lines[:4]):
                    d.add(String(x + 7, y + bh - 28 - li * 9.5, line, fontSize=7.8, fillColor=C(INK)))
                if i < len(row) - 1:
                    ax = x + bw + 1.5
                    d.add(Line(ax, y + bh / 2, ax + gap - 4, y + bh / 2, strokeColor=C(BROWN2), strokeWidth=1.2))
                    d.add(Polygon([ax + gap - 4, y + bh / 2 + 3, ax + gap - 1, y + bh / 2, ax + gap - 4, y + bh / 2 - 3], fillColor=C(BROWN2), strokeColor=None))
        return KeepTogether([Paragraph(f"<b>{esc(b.get('title', ''))}</b>", s_h3), d, Spacer(1, 3 * mm)])

    def table(b):
        cols = b["columns"]
        data = [[Paragraph(esc(c), s_cellh) for c in cols]] + [[Paragraph(esc(v), s_cell) for v in r] for r in b["rows"]]
        t = Table(data, colWidths=[W / len(cols)] * len(cols), repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(BROWN)), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C(BG)]),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.4, C(LINE)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return KeepTogether([Paragraph(f"<b>{esc(b.get('title', ''))}</b>", s_h3), t, Spacer(1, 3 * mm)])

    def kpis(b):
        items = b["items"]
        cells = [[Paragraph(f"<font size=7.5 color='{MUTED}'><b>{esc(i['label']).upper()}</b></font><br/><font size=17 color='{BROWN}'>"
                            f"<b>{esc(i['value'])}</b></font><br/><font size=7.5 color='{MUTED}'>{esc(i.get('sub', ''))}</font>",
                            ParagraphStyle("k", leading=19)) for i in items]]
        t = Table(cells, colWidths=[W / len(items)] * len(items))
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, C(LINE)), ("INNERGRID", (0, 0), (-1, -1), 0.6, C(LINE)),
                               ("LINEABOVE", (0, 0), (-1, 0), 2.5, C(GOLD)), ("TOPPADDING", (0, 0), (-1, -1), 6),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
        return KeepTogether([t, Spacer(1, 4 * mm)])

    def block(b):
        t = b["type"]
        if t == "para":
            return [Paragraph(esc(b["text"]), s_body)]
        if t == "points":
            return ([Paragraph(f"<b>{esc(b['title'])}</b>", s_h3)] if b.get("title") else []) + [bullets(b["items"]), Spacer(1, 2 * mm)]
        if t == "formula":
            inner = [Paragraph(f"<font color='{MUTED}' size=8><b>FORMULA</b></font>", s_cell),
                     Paragraph(f"<b>{esc(b['name'])}</b>", ParagraphStyle("fn", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=C(BROWN))),
                     Paragraph(f"<font face='Courier-Bold' size=12.5>{esc(b['name'])} = {esc(b['expr'])}</font>", ParagraphStyle("fx", leading=17, spaceBefore=3, spaceAfter=4))]
            inner += [Paragraph("• " + esc(w), s_cell) for w in b.get("where", [])]
            if b.get("example"):
                inner.append(Paragraph(f"<i>Example: {esc(b['example'])}</i>", ParagraphStyle("fe", fontSize=9.4, leading=13, textColor=C(BROWN2), spaceBefore=4)))
            return [KeepTogether([boxed(inner, GOLD_SOFT, GOLD, left=BROWN), Spacer(1, 4 * mm)])]
        if t == "example":
            inner = [Paragraph(f"<font color='{BLUE}'><b>WORKED EXAMPLE · {esc(b.get('title', ''))}</b></font>", s_cell)] + \
                    [Paragraph(esc(x), s_body) for x in b["lines"]]
            return [KeepTogether([boxed(inner, "#EEF3F9", "#C9D8EA", left=BLUE), Spacer(1, 4 * mm)])]
        if t == "callout":
            col, bg, lab = {"warn": (WARN, "#FDF1DD", "WATCH OUT"), "tip": (GOOD, "#E4F2E8", "TIP")}.get(b.get("kind"), (BROWN, GOLD_SOFT, "KEY POINT"))
            return [KeepTogether([boxed([Paragraph(f"<font color='{col}'><b>{lab}</b></font>", s_cell), Paragraph(esc(b["text"]), s_body)], bg, bg, left=col),
                                  Spacer(1, 4 * mm)])]
        if t == "dodont":
            cell = lambda items, col, head: [Paragraph(f"<font color='{col}'><b>{head}</b></font>", s_cell)] + [Paragraph(("✓ " if col == GOOD else "✗ ") + esc(i), s_cell) for i in items]  # noqa: E731
            tt = Table([[cell(b["do"], GOOD, "DO"), cell(b["dont"], BAD, "DON'T")]], colWidths=[W / 2] * 2)
            tt.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), C("#E4F2E8")), ("BACKGROUND", (1, 0), (1, 0), C("#FBE5E2")),
                                    ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
            return [KeepTogether([tt, Spacer(1, 4 * mm)])]
        if t == "chart":
            return [chart(b)]
        if t == "steps":
            return [steps(b)]
        if t == "table":
            return [table(b)]
        if t == "kpis":
            return [kpis(b)]
        return []

    def question(i, q, show):
        parts = [Paragraph(f"<b>{i}. {esc(q['q'])}</b>", s_body)]
        if q["type"] in ("mcq", "tf"):
            for oi, o in enumerate(q["options"]):
                mark = "■" if show and oi == q["answer"] else "□"
                parts.append(Paragraph(f"&nbsp;&nbsp;&nbsp;{mark} {'ABCDEFGH'[oi]}. {esc(o)}", s_body))
        elif not show:
            parts.append(Paragraph("&nbsp;" * 4 + "_" * 70, s_small))
            parts.append(Spacer(1, 6 * mm if q["type"] == "scenario" else 3 * mm))
        if show:
            parts.append(boxed([Paragraph(f"<b>Answer:</b> {esc(_answer_text(q))}", s_cell), Paragraph(esc(q.get("explain", "")), s_small)], "#E4F2E8", "#E4F2E8", pad=6, left=GOOD))
        parts.append(Spacer(1, 3 * mm))
        return KeepTogether(parts)

    title = content.get("title", "Course")
    story: list = []
    # cover
    logo = ASSETS / "maf-logo.png"
    story.append(Spacer(1, 30 * mm))
    if logo.exists():
        story.append(Image(str(logo), width=46 * mm, height=46 * mm * 0.52, kind="proportional"))
        story.append(Spacer(1, 14 * mm))
    story += [Paragraph("ANSWER KEY" if answers else "LEARNER BOOK", ParagraphStyle("cv", fontName="Helvetica-Bold", fontSize=10, textColor=C(GOLD), leading=14)),
              Paragraph(esc(title), ParagraphStyle("ct", fontName="Helvetica-Bold", fontSize=30, leading=36, textColor=C(BROWN), spaceAfter=8)),
              Paragraph(esc(content.get("audience", "")) + " · " + esc(content.get("summary", "")), ParagraphStyle("cs", fontSize=11.5, leading=16, textColor=C(MUTED))),
              Spacer(1, 10 * mm)]
    if content.get("for"):
        f = content["for"]
        story.append(boxed([Paragraph(f"<b>Prepared for {esc(f['name'])}</b> · {esc(f.get('store', ''))} · {esc(f.get('leads', ''))}", s_body),
                            Paragraph("Focus areas: " + esc(", ".join(f.get("why", []))), s_small)], GOLD_SOFT, GOLD, left=BROWN))
        story.append(Spacer(1, 6 * mm))
    if content.get("objectives") and not answers:
        story += [Paragraph("By the end you will be able to", s_h3), bullets(content["objectives"])]
    story.append(PageBreak())
    if not answers:
        story.append(Paragraph("Contents", s_h2))
        rows = []
        for mi, m in enumerate(content["modules"]):
            rows.append([Paragraph(f"<b>Module {mi + 1}</b>", s_cell), Paragraph(f"<b>{esc(m['title'])}</b>", s_cell),
                         Paragraph(f"{sum(l.get('minutes', 0) for l in m['lessons'])} min", s_cell)])
            for li, l in enumerate(m["lessons"]):
                rows.append(["", Paragraph(f"{mi + 1}.{li + 1}&nbsp;&nbsp;{esc(l['title'])}", s_cell), Paragraph(f"{l.get('minutes', 0)} min", s_small)])
        rows.append([Paragraph("<b>Final</b>", s_cell), Paragraph(f"<b>Final assessment</b> · {len(content.get('exam', []))} questions · pass mark {content.get('pass_mark', 70)}%", s_cell), ""])
        tc = Table(rows, colWidths=[24 * mm, W - 48 * mm, 24 * mm])
        tc.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, C(LINE)), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story += [tc, PageBreak()]
        for mi, m in enumerate(content["modules"]):
            band = Table([[Paragraph(f"<font color='{GOLD}' size=10><b>MODULE {mi + 1}</b></font><br/><font color='white' size=20><b>{esc(m['title'])}</b></font>"
                                     f"<br/><font color='#E9DCCB' size=10>{esc(m.get('summary', ''))}</font>", ParagraphStyle("mb", leading=24))]], colWidths=[W])
            band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(BROWN)), ("LEFTPADDING", (0, 0), (-1, -1), 16), ("TOPPADDING", (0, 0), (-1, -1), 16),
                                      ("BOTTOMPADDING", (0, 0), (-1, -1), 16), ("LINEBELOW", (0, 0), (-1, -1), 3, C(GOLD))]))
            story += [band, Spacer(1, 6 * mm)]
            for li, l in enumerate(m["lessons"]):
                story += [CondPageBreak(60 * mm), Paragraph(f"{mi + 1}.{li + 1}  {esc(l['title'])}", s_h2),
                          Paragraph(f"{l.get('minutes', 0)} minutes" + (" · written by AI" if l.get("source") == "AI" else ""), s_small), Spacer(1, 2 * mm)]
                if l.get("objectives"):
                    story.append(boxed([Paragraph(f"<font color='{MUTED}' size=8><b>OBJECTIVES</b></font>", s_cell)] +
                                       [Paragraph("→ " + esc(o), s_cell) for o in l["objectives"]], "#FFFFFF", LINE, pad=7))
                    story.append(Spacer(1, 4 * mm))
                for b in l["blocks"]:
                    story += block(b)
            if m.get("quiz"):
                story += [CondPageBreak(80 * mm), Paragraph(f"Module {mi + 1} check", s_h2)]
                story += [question(i + 1, q, False) for i, q in enumerate(m["quiz"])]
            if m.get("activity"):
                story += [boxed([Paragraph(f"<font color='{GOOD}'><b>ON-THE-FLOOR ACTIVITY</b></font>", s_cell), Paragraph(esc(m["activity"]), s_body),
                                 Paragraph("Manager sign-off: ______________________   Date: ____________", s_small)], "#E4F2E8", "#E4F2E8", left=GOOD)]
            story.append(PageBreak())
        if content.get("exam"):
            story += [Paragraph("Final assessment", s_h1), Paragraph(f"Pass mark {content.get('pass_mark', 70)}%. Name: ____________________  Store: ____________  Date: ________", s_small), Spacer(1, 4 * mm)]
            story += [question(i + 1, q, False) for i, q in enumerate(content["exam"])]
    else:
        current = None
        n = 0
        for mod, _, q in _questions(content):
            if mod != current:
                story.append(Paragraph(esc(mod), s_h2))
                current, n = mod, 0
            n += 1
            story.append(question(n, q, True))

    def deco(canvas, doc):
        canvas.saveState()
        if doc.page > 1:
            canvas.setFillColor(C(BROWN))
            canvas.rect(0, PH - 8 * mm, PW, 8 * mm, stroke=0, fill=1)
            canvas.setFillColor(C(GOLD))
            canvas.rect(0, PH - 8.7 * mm, PW, 0.7 * mm, stroke=0, fill=1)
            canvas.setFillColor(colors.white)
            canvas.setFont("Helvetica-Bold", 8.5)
            canvas.drawString(18 * mm, PH - 5.4 * mm, "P&O Learning  ·  Majid Al Futtaim")
            canvas.setFont("Helvetica", 8)
            canvas.drawRightString(PW - 18 * mm, PH - 5.4 * mm, title[:80])
            canvas.setFillColor(C(MUTED))
            canvas.setFont("Helvetica", 7.5)
            canvas.drawString(18 * mm, 9 * mm, ("Answer key · trainers only" if answers else "Learner book") + "  ·  Internal training material")
            canvas.drawRightString(PW - 18 * mm, 9 * mm, f"Page {doc.page}")
        else:
            canvas.setFillColor(C(GOLD))
            canvas.rect(0, 0, 9 * mm, PH, stroke=0, fill=1)
            canvas.setFillColor(C(BROWN))
            canvas.rect(9 * mm, 0, 2 * mm, PH, stroke=0, fill=1)
            canvas.setFillColor(C(MUTED))
            canvas.setFont("Helvetica", 8)
            canvas.drawString(18 * mm, 14 * mm, f"P&O · People & Organisation · {datetime.now():%B %Y}")
        canvas.restoreState()

    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=title + (" · Answer key" if answers else ""), author="P&O Learning")
    doc.build(story, onFirstPage=deco, onLaterPages=deco)


def pdf_book(content: dict, path: str) -> None:
    _pdf(content, path, answers=False)


def pdf_answers(content: dict, path: str) -> None:
    _pdf(content, path, answers=True)


def certificate(name: str, course: str, path: str, score: str = "", hours: Any = None, on: str = "") -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as cv

    C = colors.HexColor
    PW, PH = landscape(A4)
    c = cv.Canvas(path, pagesize=(PW, PH))
    c.setFillColor(C("#FFFDF8"))
    c.rect(0, 0, PW, PH, stroke=0, fill=1)
    c.setStrokeColor(C(GOLD))
    c.setLineWidth(3)
    c.rect(12 * mm, 12 * mm, PW - 24 * mm, PH - 24 * mm)
    c.setLineWidth(0.8)
    c.rect(15 * mm, 15 * mm, PW - 30 * mm, PH - 30 * mm)
    logo = ASSETS / "maf-logo.png"
    if logo.exists():
        c.drawImage(str(logo), PW / 2 - 25 * mm, PH - 58 * mm, width=50 * mm, height=26 * mm, preserveAspectRatio=True, mask="auto")
    c.setFillColor(C(GOLD))
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(PW / 2, PH - 72 * mm, "CERTIFICATE OF COMPLETION")
    c.setFillColor(C(MUTED))
    c.setFont("Helvetica", 12)
    c.drawCentredString(PW / 2, PH - 86 * mm, "This certifies that")
    c.setFillColor(C(BROWN))
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(PW / 2, PH - 102 * mm, name)
    c.setFillColor(C(MUTED))
    c.setFont("Helvetica", 12)
    c.drawCentredString(PW / 2, PH - 116 * mm, "has successfully completed")
    c.setFillColor(C(INK))
    c.setFont("Helvetica-Bold", 17)
    c.drawCentredString(PW / 2, PH - 129 * mm, course[:80])
    c.setFont("Helvetica", 11)
    extra = " · ".join(x for x in (f"Score {score}" if score else "", f"{hours:g} hours" if isinstance(hours, (int, float)) and hours else "", on or datetime.now().strftime("%d %B %Y")) if x)
    c.drawCentredString(PW / 2, PH - 141 * mm, extra)
    c.setStrokeColor(C(LINE))
    c.line(PW / 2 - 110 * mm, 40 * mm, PW / 2 - 30 * mm, 40 * mm)
    c.line(PW / 2 + 30 * mm, 40 * mm, PW / 2 + 110 * mm, 40 * mm)
    c.setFillColor(C(MUTED))
    c.setFont("Helvetica", 9)
    c.drawCentredString(PW / 2 - 70 * mm, 34 * mm, "P&O Director")
    c.drawCentredString(PW / 2 + 70 * mm, 34 * mm, "Trainer")
    c.setFont("Helvetica", 8)
    c.drawCentredString(PW / 2, 22 * mm, "Majid Al Futtaim · Carrefour Pakistan · People & Organisation")
    c.showPage()
    c.save()


# ============================================================================================== PowerPoint
def pptx_deck(content: dict, path: str) -> None:
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches, Pt

    def rgb(h):
        return RGBColor.from_string(h.lstrip("#"))

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    SW, SH = prs.slide_width, prs.slide_height

    def rect(sl, x, y, w, h, color, shape=MSO_SHAPE.RECTANGLE, line=None):
        s = sl.shapes.add_shape(shape, x, y, w, h)
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(color)
        if line:
            s.line.color.rgb = rgb(line)
        else:
            s.line.fill.background()
        s.shadow.inherit = False
        return s

    def text(sl, x, y, w, h, t, size=18, bold=False, color=INK, align=None):
        tb = sl.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        lines = t if isinstance(t, list) else [t]
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            r = p.add_run()
            r.text = str(line)
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.color.rgb = rgb(color)
            r.font.name = "Segoe UI"
            p.space_after = Pt(6)
            if align is not None:
                p.alignment = align
        return tb

    def slide(title, kicker="", notes=""):
        sl = prs.slides.add_slide(blank)
        rect(sl, 0, 0, SW, Inches(0.12), GOLD)
        text(sl, Inches(0.6), Inches(0.35), Inches(12), Inches(0.4), kicker.upper(), 11, True, GOLD)
        text(sl, Inches(0.6), Inches(0.68), Inches(12), Inches(0.9), title, 28, True, BROWN)
        text(sl, Inches(0.6), SH - Inches(0.45), Inches(9), Inches(0.3), "P&O Learning · Majid Al Futtaim", 9, False, MUTED)
        if notes:
            sl.notes_slide.notes_text_frame.text = notes
        return sl

    logo = ASSETS / "maf-logo.png"
    sl = prs.slides.add_slide(blank)
    rect(sl, 0, 0, SW, SH, BROWN)
    rect(sl, 0, SH - Inches(0.25), SW, Inches(0.25), GOLD)
    if logo.exists():
        rect(sl, Inches(0.8), Inches(0.8), Inches(2.3), Inches(1.4), "#FFFFFF", MSO_SHAPE.ROUNDED_RECTANGLE)
        sl.shapes.add_picture(str(logo), Inches(0.95), Inches(0.95), width=Inches(2.0))
    text(sl, Inches(0.8), Inches(3.0), Inches(11.5), Inches(1.6), content["title"], 44, True, "#FFFFFF")
    text(sl, Inches(0.8), Inches(4.7), Inches(11.5), Inches(0.8), f"{content.get('audience', '')} · {content.get('summary', '')}", 16, False, "#E9DCCB")
    sl.notes_slide.notes_text_frame.text = "Welcome the group, introduce yourself and the purpose of the course. Explain timings, breaks and the final assessment."
    if content.get("objectives"):
        s2 = slide("What you will be able to do", "Objectives", "Read each objective and ask the group which one matters most in their store today.")
        text(s2, Inches(0.8), Inches(1.8), Inches(11.8), Inches(5), [f"→  {o}" for o in content["objectives"]], 20)
    for mi, m in enumerate(content["modules"]):
        sm = prs.slides.add_slide(blank)
        rect(sm, 0, 0, SW, SH, BROWN2)
        text(sm, Inches(0.8), Inches(2.4), Inches(11), Inches(0.5), f"MODULE {mi + 1}", 16, True, GOLD)
        text(sm, Inches(0.8), Inches(2.9), Inches(11.5), Inches(1.6), m["title"], 40, True, "#FFFFFF")
        text(sm, Inches(0.8), Inches(4.4), Inches(11.5), Inches(1), m.get("summary", ""), 16, False, "#F3E6D3")
        for li, l in enumerate(m["lessons"]):
            kick = f"Module {mi + 1} · lesson {li + 1} · {l.get('minutes', 0)} min"
            paras = [b["text"] for b in l["blocks"] if b["type"] == "para"]
            s = slide(l["title"], kick, " ".join(paras)[:1800] or "Talk through the lesson with examples from your store.")
            if l.get("objectives"):
                text(s, Inches(0.8), Inches(1.7), Inches(11.8), Inches(1.5), [f"✓  {o}" for o in l["objectives"]], 18, False, INK)
            for b in l["blocks"]:
                t = b["type"]
                if t == "points":
                    s = slide(b.get("title") or l["title"], kick, "Ask for one example of each point from the group.")
                    text(s, Inches(0.8), Inches(1.8), Inches(11.8), Inches(5), [f"•  {i}" for i in b["items"]], 20)
                elif t == "formula":
                    s = slide(b["name"], kick + " · formula", "Work the example on a flipchart, then ask them to calculate their own section's figure.")
                    card = rect(s, Inches(0.8), Inches(1.8), Inches(11.7), Inches(1.5), GOLD_SOFT, MSO_SHAPE.ROUNDED_RECTANGLE, GOLD)
                    text(s, Inches(1.1), Inches(2.15), Inches(11.2), Inches(1), f"{b['name']} = {b['expr']}", 28, True, BROWN)
                    text(s, Inches(0.8), Inches(3.6), Inches(11.7), Inches(2), [f"•  {w}" for w in b.get("where", [])] + ([f"Example: {b['example']}"] if b.get("example") else []), 18)
                    del card
                elif t == "example":
                    s = slide(b.get("title") or "Worked example", kick + " · example", "Let the group work it out before showing the answer.")
                    rect(s, Inches(0.8), Inches(1.7), Inches(0.12), Inches(4.5), BLUE)
                    text(s, Inches(1.1), Inches(1.7), Inches(11.3), Inches(4.5), b["lines"], 20)
                elif t == "chart":
                    s = slide(b.get("title") or "Chart", kick, "Ask: what does this chart tell us, and what would you do about it?")
                    cd = CategoryChartData()
                    cd.categories = b["labels"]
                    for se in b["series"]:
                        cd.add_series(se["name"], se["values"])
                    kind = {"hbar": XL_CHART_TYPE.BAR_CLUSTERED, "line": XL_CHART_TYPE.LINE_MARKERS}.get(b["kind"], XL_CHART_TYPE.COLUMN_CLUSTERED)
                    gf = s.shapes.add_chart(kind, Inches(0.8), Inches(1.7), Inches(11.7), Inches(5.1), cd)
                    ch = gf.chart
                    ch.has_legend = len(b["series"]) > 1
                    if ch.has_legend:
                        ch.legend.position = XL_LEGEND_POSITION.BOTTOM
                        ch.legend.include_in_layout = False
                    for i, se in enumerate(ch.plots[0].series):
                        fill = se.format.fill if b["kind"] != "line" else None
                        if fill is not None:
                            fill.solid()
                            fill.fore_color.rgb = rgb(PAL[i % len(PAL)])
                        else:
                            se.format.line.color.rgb = rgb(PAL[i % len(PAL)])
                    if b["kind"] != "line":
                        ch.plots[0].has_data_labels = True
                        ch.plots[0].data_labels.font.size = Pt(11)
                elif t == "steps":
                    s = slide(b.get("title") or "Steps", kick, "Walk through each step; ask who does it in their store today.")
                    n = len(b["items"])
                    per = min(n, 4)
                    bw = (Inches(11.7) - (per - 1) * Inches(0.35)) / per
                    for i, it in enumerate(b["items"]):
                        r, col = divmod(i, per)
                        x = Inches(0.8) + col * (bw + Inches(0.35))
                        y = Inches(1.8) + r * Inches(2.4)
                        rect(s, x, y, bw, Inches(2.0), GOLD_SOFT if i % 2 == 0 else "#FFFFFF", MSO_SHAPE.ROUNDED_RECTANGLE, GOLD)
                        circ = rect(s, x + Inches(0.15), y + Inches(0.15), Inches(0.45), Inches(0.45), BROWN, MSO_SHAPE.OVAL)
                        circ.text_frame.text = str(i + 1)
                        circ.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
                        circ.text_frame.paragraphs[0].runs[0].font.bold = True
                        text(s, x + Inches(0.15), y + Inches(0.65), bw - Inches(0.3), Inches(1.3), it, 14)
                elif t == "table":
                    s = slide(b.get("title") or "Table", kick, "")
                    rows, cols = len(b["rows"]) + 1, len(b["columns"])
                    tbl = s.shapes.add_table(rows, cols, Inches(0.8), Inches(1.8), Inches(11.7), Inches(0.5) * rows).table
                    for ci, cn in enumerate(b["columns"]):
                        tbl.cell(0, ci).text = cn
                    for ri, row in enumerate(b["rows"]):
                        for ci, v in enumerate(row):
                            tbl.cell(ri + 1, ci).text = str(v)
                elif t == "kpis":
                    s = slide("Key numbers", kick, "These are example figures: ask the group for their real ones.")
                    n = len(b["items"])
                    w = (Inches(11.7) - (n - 1) * Inches(0.3)) / n
                    for i, it in enumerate(b["items"]):
                        x = Inches(0.8) + i * (w + Inches(0.3))
                        rect(s, x, Inches(2.2), w, Inches(2.6), "#FFFFFF", MSO_SHAPE.ROUNDED_RECTANGLE, LINE)
                        rect(s, x, Inches(2.2), w, Inches(0.08), GOLD)
                        text(s, x + Inches(0.2), Inches(2.45), w - Inches(0.4), Inches(0.5), it["label"].upper(), 12, True, MUTED)
                        text(s, x + Inches(0.2), Inches(3.0), w - Inches(0.4), Inches(1), it["value"], 40, True, BROWN)
                        text(s, x + Inches(0.2), Inches(4.1), w - Inches(0.4), Inches(0.5), it.get("sub", ""), 13, False, MUTED)
                elif t == "dodont":
                    s = slide("Do and don't", kick, "Ask for a real example of each from their store.")
                    rect(s, Inches(0.8), Inches(1.8), Inches(5.7), Inches(4.8), "#E4F2E8", MSO_SHAPE.ROUNDED_RECTANGLE)
                    rect(s, Inches(6.8), Inches(1.8), Inches(5.7), Inches(4.8), "#FBE5E2", MSO_SHAPE.ROUNDED_RECTANGLE)
                    text(s, Inches(1.1), Inches(2.0), Inches(5.2), Inches(4.4), ["DO"] + [f"✓ {x}" for x in b["do"]], 18, False, GOOD)
                    text(s, Inches(7.1), Inches(2.0), Inches(5.2), Inches(4.4), ["DON'T"] + [f"✗ {x}" for x in b["dont"]], 18, False, BAD)
                elif t == "callout":
                    s = slide({"warn": "Watch out", "tip": "Tip"}.get(b.get("kind"), "Key point"), kick, "")
                    rect(s, Inches(0.8), Inches(2.3), Inches(11.7), Inches(2.6), GOLD_SOFT, MSO_SHAPE.ROUNDED_RECTANGLE, GOLD)
                    text(s, Inches(1.2), Inches(2.6), Inches(11), Inches(2.2), b["text"], 26, True, BROWN)
        if m.get("quiz"):
            for qi, q in enumerate(m["quiz"]):
                s = slide(q["q"], f"Module {mi + 1} check · question {qi + 1}", f"Answer: {_answer_text(q)}. {q.get('explain', '')}")
                if q.get("options"):
                    text(s, Inches(0.8), Inches(2.2), Inches(11.7), Inches(4), [f"{'ABCDEFGH'[i]}.  {o}" for i, o in enumerate(q["options"])], 22)
        if m.get("activity"):
            s = slide("On the floor", f"Module {mi + 1} · activity", "Agree when each person will do the activity and when you will review it.")
            text(s, Inches(0.8), Inches(1.9), Inches(11.7), Inches(4), m["activity"], 24)
    s = slide("Thank you", "Close", "Collect the final assessments, thank the group and agree follow-up dates.")
    text(s, Inches(0.8), Inches(2.0), Inches(11.7), Inches(3), ["Questions?", "Final assessment next: " + str(len(content.get("exam", []))) + " questions"], 26, True, BROWN)
    prs.save(path)


# ============================================================================================== Word
def docx_doc(content: dict, path: str) -> None:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm, Pt, RGBColor

    def rgb(h):
        return RGBColor.from_string(h.lstrip("#"))

    d = docx.Document()
    for sec in d.sections:
        sec.left_margin = sec.right_margin = Mm(20)
        sec.top_margin = sec.bottom_margin = Mm(18)
    st = d.styles["Normal"]
    st.font.name = "Segoe UI"
    st.font.size = Pt(10.5)
    for name, size, color in (("Heading 1", 22, BROWN), ("Heading 2", 15, BROWN), ("Heading 3", 12, BROWN2)):
        s = d.styles[name]
        s.font.name = "Segoe UI"
        s.font.size = Pt(size)
        s.font.color.rgb = rgb(color)

    def shade(cell, color):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), color.lstrip("#"))
        tcPr.append(shd)

    def box(lines, fill, label=None, label_color=BROWN):
        t = d.add_table(rows=1, cols=1)
        c = t.cell(0, 0)
        shade(c, fill)
        p = c.paragraphs[0]
        if label:
            r = p.add_run(label.upper())
            r.bold = True
            r.font.size = Pt(8.5)
            r.font.color.rgb = rgb(label_color)
            p = c.add_paragraph()
        for i, line in enumerate(lines):
            if i:
                p = c.add_paragraph()
            if isinstance(line, tuple):
                r = p.add_run(line[0])
                r.bold = True
                r.font.size = Pt(line[1])
                r.font.color.rgb = rgb(BROWN)
            else:
                p.add_run(str(line))
        d.add_paragraph()

    logo = ASSETS / "maf-logo.png"
    if logo.exists():
        d.add_picture(str(logo), width=Mm(45))
    p = d.add_paragraph()
    r = p.add_run("LEARNER BOOK")
    r.bold, r.font.size, r.font.color.rgb = True, Pt(10), rgb(GOLD)
    d.add_heading(content["title"], 0).runs[0].font.color.rgb = rgb(BROWN)
    d.add_paragraph(f"{content.get('audience', '')} · {content.get('summary', '')}")
    if content.get("objectives"):
        d.add_heading("By the end you will be able to", 3)
        for o in content["objectives"]:
            d.add_paragraph(o, style="List Bullet")
    d.add_page_break()
    for mi, m in enumerate(content["modules"]):
        d.add_heading(f"Module {mi + 1} · {m['title']}", 1)
        if m.get("summary"):
            d.add_paragraph(m["summary"]).runs[0].italic = True
        for li, l in enumerate(m["lessons"]):
            d.add_heading(f"{mi + 1}.{li + 1}  {l['title']}", 2)
            d.add_paragraph(f"{l.get('minutes', 0)} minutes").runs[0].font.color.rgb = rgb(MUTED)
            if l.get("objectives"):
                box([f"→ {o}" for o in l["objectives"]], "FFFFFF", "Objectives", MUTED)
            for b in l["blocks"]:
                t = b["type"]
                if t == "para":
                    d.add_paragraph(b["text"])
                elif t == "points":
                    if b.get("title"):
                        d.add_heading(b["title"], 3)
                    for it in b["items"]:
                        d.add_paragraph(it, style="List Bullet")
                elif t == "formula":
                    box([(b["name"], 12), (f"{b['name']} = {b['expr']}", 13)] + [f"• {w}" for w in b.get("where", [])] +
                        ([f"Example: {b['example']}"] if b.get("example") else []), "F6ECD4", "Formula")
                elif t == "example":
                    box([b.get("title", "")] + b["lines"], "EEF3F9", "Worked example", BLUE)
                elif t == "callout":
                    box([b["text"]], {"warn": "FDF1DD", "tip": "E4F2E8"}.get(b.get("kind"), "F6ECD4"),
                        {"warn": "Watch out", "tip": "Tip"}.get(b.get("kind"), "Key point"))
                elif t == "steps":
                    d.add_heading(b.get("title", "Steps"), 3)
                    tb = d.add_table(rows=1, cols=len(b["items"]))
                    tb.style = "Table Grid"
                    for i, it in enumerate(b["items"]):
                        c = tb.cell(0, i)
                        shade(c, "F6ECD4" if i % 2 == 0 else "FFFFFF")
                        r = c.paragraphs[0].add_run(f"{i + 1}  ")
                        r.bold, r.font.color.rgb = True, rgb(BROWN)
                        c.paragraphs[0].add_run(it).font.size = Pt(9)
                    d.add_paragraph()
                elif t in ("table", "chart", "kpis"):
                    if t == "chart":
                        cols = ["", *[s["name"] for s in b["series"]], "Chart"]
                        mx = max([abs(v) for s in b["series"] for v in s["values"]] or [1]) or 1
                        rows = [[lab, *[f"{s['values'][i]:g}" for s in b["series"]], "█" * max(1, round(20 * abs(b["series"][0]["values"][i]) / mx))]
                                for i, lab in enumerate(b["labels"])]
                        title = b.get("title", "") + (f" ({b['unit']})" if b.get("unit") else "")
                    elif t == "kpis":
                        cols, rows, title = [i["label"] for i in b["items"]], [[f"{i['value']}  {i.get('sub', '')}" for i in b["items"]]], "Key numbers"
                    else:
                        cols, rows, title = b["columns"], b["rows"], b.get("title", "")
                    if title:
                        d.add_heading(title, 3)
                    tb = d.add_table(rows=len(rows) + 1, cols=len(cols))
                    tb.style = "Table Grid"
                    for ci, cn in enumerate(cols):
                        c = tb.cell(0, ci)
                        shade(c, BROWN)
                        run = c.paragraphs[0].add_run(str(cn))
                        run.bold, run.font.color.rgb = True, rgb("#FFFFFF")
                    for ri, row in enumerate(rows):
                        for ci, v in enumerate(row):
                            run = tb.cell(ri + 1, ci).paragraphs[0].add_run(str(v))
                            if t == "chart" and ci == len(row) - 1:
                                run.font.color.rgb = rgb(PAL[0])
                    d.add_paragraph()
                elif t == "dodont":
                    tb = d.add_table(rows=1, cols=2)
                    for ci, (items, fill, head, mark) in enumerate(((b["do"], "E4F2E8", "DO", "✓"), (b["dont"], "FBE5E2", "DON'T", "✗"))):
                        c = tb.cell(0, ci)
                        shade(c, fill)
                        c.paragraphs[0].add_run(head).bold = True
                        for it in items:
                            c.add_paragraph(f"{mark} {it}")
                    d.add_paragraph()
        if m.get("quiz"):
            d.add_heading(f"Module {mi + 1} check", 2)
            for qi, q in enumerate(m["quiz"]):
                d.add_paragraph(f"{qi + 1}. {q['q']}").runs[0].bold = True
                for oi, o in enumerate(q.get("options", [])):
                    d.add_paragraph(f"☐ {'ABCDEFGH'[oi]}. {o}")
                if not q.get("options"):
                    d.add_paragraph("_" * 80)
        if m.get("activity"):
            box([m["activity"], "Manager sign-off: ______________   Date: ________"], "E4F2E8", "On-the-floor activity", GOOD)
        d.add_page_break()
    if content.get("exam"):
        d.add_heading("Final assessment", 1)
        d.add_paragraph(f"Pass mark {content.get('pass_mark', 70)}%.  Name: ____________  Store: ________  Date: ______")
        for qi, q in enumerate(content["exam"]):
            d.add_paragraph(f"{qi + 1}. {q['q']}").runs[0].bold = True
            for oi, o in enumerate(q.get("options", [])):
                d.add_paragraph(f"☐ {'ABCDEFGH'[oi]}. {o}")
            if not q.get("options"):
                d.add_paragraph("_" * 80)
        d.add_page_break()
    d.add_heading("Answer key (trainers)", 1)
    for mod, _, q in _questions(content):
        p = d.add_paragraph()
        p.add_run(f"[{mod}] {q['q']}  ").bold = True
        p.add_run(f"Answer: {_answer_text(q)}. {q.get('explain', '')}")
    for s in d.sections:
        fp = s.footer.paragraphs[0]
        fp.text = f"P&O Learning · {content['title']} · Internal training material"
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.save(path)


# ============================================================================================== Excel
def xlsx_bank(content: dict, path: str, assignments: list[dict] | None = None) -> None:
    import xlsxwriter

    wb = xlsxwriter.Workbook(path)
    h = wb.add_format({"bold": True, "font_color": "white", "bg_color": BROWN, "border": 1, "text_wrap": True, "valign": "top"})
    w = wb.add_format({"text_wrap": True, "valign": "top", "border": 1})
    title = wb.add_format({"bold": True, "font_size": 16, "font_color": BROWN})
    ws = wb.add_worksheet("Quiz bank")
    ws.write(0, 0, f"{content['title']} · quiz bank", title)
    cols = ["Section", "Type", "Question", "Option A", "Option B", "Option C", "Option D", "Answer", "Explanation"]
    for i, c in enumerate(cols):
        ws.write(2, i, c, h)
    ws.set_column(0, 0, 26)
    ws.set_column(1, 1, 9)
    ws.set_column(2, 2, 60)
    ws.set_column(3, 6, 22)
    ws.set_column(7, 8, 34)
    r = 3
    for mod, _, q in _questions(content):
        opts = (q.get("options") or []) + [""] * 4
        ws.write_row(r, 0, [mod, q["type"].upper(), q["q"], *opts[:4], _answer_text(q), q.get("explain", "")], w)
        r += 1
    ws.autofilter(2, 0, r - 1, len(cols) - 1)
    ws.freeze_panes(3, 0)
    tr = wb.add_worksheet("Tracker")
    tr.write(0, 0, f"{content['title']} · training tracker", title)
    tcols = ["Employee", "Name", "Store", "Assigned", "Due", "Status", "Score %", "Passed", "Notes"]
    for i, c in enumerate(tcols):
        tr.write(2, i, c, h)
    tr.set_column(0, 8, 16)
    tr.set_column(1, 1, 26)
    tr.set_column(8, 8, 34)
    rows = assignments or []
    pm = content.get("pass_mark", 70)
    for i, a in enumerate(rows or [{}] * 15):
        rr = 3 + i
        tr.write_row(rr, 0, [a.get("person", ""), a.get("person_name", ""), a.get("store", ""), (a.get("assigned_at") or "")[:10], a.get("due") or "",
                             a.get("status", ""), a.get("score") if a.get("score") is not None else ""], w)
        tr.write_formula(rr, 7, f'=IF(G{rr + 1}="","",IF(G{rr + 1}>={pm},"Yes","No"))', w)
        tr.write(rr, 8, a.get("notes") or "", w)
    tr.data_validation(3, 5, 3 + max(15, len(rows)), 5, {"validate": "list", "source": ["assigned", "in progress", "completed"]})
    tr.conditional_format(3, 6, 3 + max(15, len(rows)), 6, {"type": "data_bar", "bar_color": GOLD})
    wb.close()


def pack_zip(content: dict, path: str, assignments: list[dict] | None = None) -> None:
    """Everything for one course in one file, ready to email."""
    name = safe_name(content["title"])
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for fn, maker in ((f"{name} - Learner book.pdf", pdf_book), (f"{name} - Answer key.pdf", pdf_answers), (f"{name} - Trainer deck.pptx", pptx_deck),
                          (f"{name} - Editable.docx", docx_doc)):
            tmp = io.BytesIO()
            maker(content, tmp)
            z.writestr(fn, tmp.getvalue())
        tmp = io.BytesIO()
        xlsx_bank(content, tmp, assignments)
        z.writestr(f"{name} - Quiz bank and tracker.xlsx", tmp.getvalue())


EXPORTERS = {"pdf": pdf_book, "answers": pdf_answers, "pptx": pptx_deck, "docx": docx_doc, "xlsx": xlsx_bank, "zip": pack_zip}
EXT = {"pdf": "pdf", "answers": "pdf", "pptx": "pptx", "docx": "docx", "xlsx": "xlsx", "zip": "zip"}
SUFFIX = {"pdf": "Learner book", "answers": "Answer key", "pptx": "Trainer deck", "docx": "Editable", "xlsx": "Quiz bank and tracker", "zip": "Learning pack"}
