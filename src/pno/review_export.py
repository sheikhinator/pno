"""4.2 Review exports: the screen the director presents, as a PowerPoint deck, a PDF report or a Word document.

All three carry the same content, laid out for their medium: a cover, the scorecard as coloured KPI tiles, what's strong /
weak / focus, AI-written insights (when an AI is set up), charts of the key criteria across the next level down (with the
benchmark line), where leaders fall short, the spread of scores, a heat-map of the next level down and the people
benchmark table (score next to the name). PowerPoint charts are native and editable; PDF charts are vector; Word charts
are crisp images drawn with Pillow.
"""

from __future__ import annotations

import io
import json
import re
from datetime import datetime
from typing import Any

from . import review

BROWN, GOLD, INK, MUTED, LINE, BG = "#94481A", "#B8860B", "#1D1D1F", "#86868B", "#E5E5EA", "#F5F5F7"
STATUS = {"good": "#16A34A", "warn": "#F59E0B", "bad": "#DC2626", "neutral": "#8E8E93", "none": "#C7C7CC"}
TINT = {"good": "#DCFCE7", "warn": "#FEF3C7", "bad": "#FEE2E2", "neutral": "#F2F2F7", "none": "#FFFFFF"}
INKS = {"good": "#14532D", "warn": "#78350F", "bad": "#7F1D1D", "neutral": INK, "none": MUTED}
WORD = {"good": "On or above benchmark", "warn": "Close to benchmark", "bad": "Below benchmark", "neutral": "For information", "none": "No data"}


# ---------------------------------------------------------------------------------------------- the content
def build(api, store=None, dept=None, section=None, role=None, ai: bool = True) -> dict:
    rv = api.api_review(store=store, dept=dept, section=section, role=role)
    if rv.get("empty"):
        raise ValueError("There is no data to export yet. Use Update data first.")
    C = rv["criteria"]
    lab = lambda k: C[k]["label"]  # noqa: E731
    tiles = [{**t, "text": review.fmt(t["key"], t["value"]), "bench": _bench(C, t["key"], unit=True)} for t in rv["tiles"]]
    # the criteria worth a chart: red first, then amber, then the core business ones
    order = {"bad": 0, "warn": 1, "good": 2, "neutral": 3, "none": 4}
    core = ["sales", "productivity", "oos", "shrink", "stock_days", "attendance", "growth", "waste", "nps"]
    keys = [k for k in rv["grid_keys"] if k not in ("leavers", "da")]
    keys.sort(key=lambda k: (order[next((t["status"] for t in rv["tiles"] if t["key"] == k), "none")], core.index(k) if k in core else 99))
    charts = []
    for k in keys[:4]:
        pts = [(g["name"], next(c for c in g["cells"] if c["key"] == k)) for g in rv["grid"]]
        pts = [(n, c) for n, c in pts if c["value"] is not None]
        if len(pts) >= 2:
            charts.append({"title": f"{lab(k)} by {rv['grid_kind'].rstrip('s')}", "key": k, "labels": [n for n, _ in pts],
                           "values": [c["value"] for _, c in pts], "colors": [STATUS[c["status"]] for _, c in pts],
                           "bench": C[k]["green"], "amber": C[k]["amber"], "fmt": C[k]["fmt"], "better": C[k]["better"]})
    ppl, pk = rv["people"], [k for k in rv["people_keys"] if k != "score"]
    short = []
    for k in pk:
        red = sum(1 for p in ppl if next(c for c in p["cells"] if c["key"] == k)["status"] == "bad")
        amb = sum(1 for p in ppl if next(c for c in p["cells"] if c["key"] == k)["status"] == "warn")
        if red or amb:
            short.append((lab(k), red, amb))
    short.sort(key=lambda x: -(x[1] * 2 + x[2]))
    spread = {s: sum(1 for p in ppl if next(c for c in p["cells"] if c["key"] == "score")["status"] == s) for s in ("good", "warn", "bad")}
    scores = [next(c for c in p["cells"] if c["key"] == "score")["value"] for p in ppl]
    scores = [s for s in scores if s is not None]
    out = {"title": "Department Review", "view": rv["label"], "as_of": rv["as_of"], "period": rv.get("period_label") or "",
           "generated": datetime.now().strftime("%d %b %Y, %H:%M"), "tiles": tiles, "notes": rv["notes"], "charts": charts,
           "shortfall": short[:10], "spread": spread, "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
           "grid_kind": rv["grid_kind"], "grid_keys": [k for k in rv["grid_keys"]],
           "grid": [{"name": g["name"], "cells": [{**c, "text": _cell(c)} for c in g["cells"] if c["key"] in rv["grid_keys"]]}
                    for g in rv["grid"]],
           "people_keys": ["score"] + pk,
           "people": [{"name": p["name"], "sub": f"{p['role']} · {p['area']}" + ("" if store else f" · {p['store']}"),
                       "cells": [{**c, "text": _cell(c)} for k in ["score"] + pk for c in p["cells"] if c["key"] == k]}
                      for p in ppl],
           "labels": {k: C[k]["label"] for k in C}, "short": {k: C[k].get("short", C[k]["label"]) for k in C},
           "benches": {k: _bench(C, k) for k in C}, "ai": None, "ai_engine": None}
    if ai:
        out["ai"], out["ai_engine"] = _ai_insights(api, out)
    return out


def _cell(c) -> str:
    return review.fmt(c["key"], c["value"]).replace(" pts", "")


def _bench(C, k, unit=False) -> str:
    c = C[k]
    if c["green"] is None:
        return "For information"
    if unit and k in ("leavers", "da"):
        return "Group total"
    u = {"pct0": "%", "pct1": "%", "pct1s": "%", "pct0s": "%", "pct2s": "%", "pp2s": " pts"}.get(c["fmt"], "")
    g = f"{c['green']:g}{u}"
    return f"Green {g} or {'more' if c['better'] == 'up' else 'less'}"


def _ai_insights(api, d: dict) -> tuple[list[str] | None, str | None]:
    """A few sharp, specific insights written by the AI chosen for 'insights' in Settings → AI. Only summaries are sent."""
    try:
        facts = {"view": d["view"], "as_of": d["as_of"],
                 "scorecard": {t["label"]: f"{t['text']} ({WORD[t['status']]})" for t in d["tiles"]},
                 "strong": d["notes"]["strong"], "weak": d["notes"]["weak"], "focus": d["notes"]["focus"],
                 "by_" + (d["grid_kind"] or "unit"): {g["name"]: {d["short"][c["key"]]: c["text"] for c in g["cells"] if c["value"] is not None} for g in d["grid"][:20]},
                 "leaders_short_of_benchmark": {n: {"below": r, "close": a} for n, r, a in d["shortfall"]},
                 "leader_score_spread": d["spread"], "average_leader_score": d["avg_score"]}
        prompt = ("You are an HR and retail performance analyst for MAF Carrefour Pakistan, preparing a weekly department review for the "
                  "P&O Director. From the data below write 5 short, specific insights (one or two sentences each): patterns across stores "
                  "or sections, likely links between measures, risks, and one concrete action each. Use the numbers. Do not rank or name "
                  "individual people. Reply with JSON only: {\"insights\": [\"...\", ...]}.\n\nDATA:\n" + json.dumps(facts, default=str)[:9000])
        out = api.agent.complete(prompt, system="Reply with JSON only.", max_tokens=700, allow_offline=False, task="insights")
        if not out:
            return None, None
        text, engine = out
        m = re.search(r"\{.*\}", text, re.S)
        items = json.loads(m.group(0)).get("insights") if m else None
        items = [str(x).strip() for x in (items or []) if str(x).strip()][:6]
        return (items or None), engine
    except Exception:  # noqa: BLE001 - the export never fails because the AI did
        return None, None


def talking_points(d: dict) -> list[str]:
    """When no AI is set up: discussion points worked out from the numbers."""
    pts = []
    for f in d["notes"]["focus"][:3]:
        pts.append(f"Ask the owners of {f.split(' in ', 1)[1] if ' in ' in f else 'this area'} for a recovery plan on {f.split(' in ', 1)[0].lower()}.")
    for name, red, amb in d["shortfall"][:2]:
        pts.append(f"{red} leader{'s are' if red != 1 else ' is'} below benchmark on {name.lower()}" + (f" and {amb} close to it" if amb else "") +
                   ": a shared coaching session would reach them together.")
    sp = d["spread"]
    tot = sum(sp.values())
    if tot:
        pts.append(f"{sp['good']} of {tot} leaders score 7 or more; {sp['bad']} score below 5 and need a development plan (Learning tab builds one per person).")
    return pts


# ---------------------------------------------------------------------------------------------- chart layout (shared by PDF and Word)
def _hbar_layout(ch: dict, W: float, H: float) -> list[tuple]:
    """Primitives for a horizontal bar chart, top-left origin: rect / text / line."""
    labels, vals, cols = ch["labels"], ch["values"], ch["colors"]
    n = len(labels)
    prims: list[tuple] = []
    lw = min(W * 0.34, max(len(str(x)) for x in labels) * 6.2 + 12)
    top, bottom, right = 26, 18, 54
    row = (H - top - bottom) / max(n, 1)
    bh = max(6.0, min(18.0, row * 0.62))
    lo = min([0.0] + vals + ([ch["bench"]] if ch.get("bench") is not None else []))
    hi = max([0.0] + vals + ([ch["bench"]] if ch.get("bench") is not None else []))
    if hi == lo:
        hi = lo + 1
    pad = (hi - lo) * 0.06
    lo, hi = (lo - pad if lo < 0 else lo), hi + pad
    x0, x1 = lw, W - right
    X = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)  # noqa: E731
    prims.append(("text", 0, 12, ch["title"], 11, BROWN, "start", True))
    zero = X(0)
    prims.append(("line", zero, top - 4, zero, H - bottom + 2, LINE, 1, None))
    for i, (l, v, c) in enumerate(zip(labels, vals, cols)):
        y = top + i * row + (row - bh) / 2
        a, b = sorted((zero, X(v)))
        prims.append(("rect", a, y, max(b - a, 1.5), bh, c))
        prims.append(("text", lw - 8, y + bh * 0.75, str(l)[:34], 8.5, INK, "end", False))
        t = review.fmt(ch["key"], v)
        prims.append(("text", b + 4 if v >= 0 else zero + 4, y + bh * 0.75, t, 8.5, INK, "start", True))
    if ch.get("bench") is not None:
        bx = X(ch["bench"])
        prims.append(("line", bx, top - 6, bx, H - bottom + 4, "#1D1D1F", 1.2, (3, 2)))
        prims.append(("text", bx, H - 4, f"benchmark {review.fmt(ch['key'], ch['bench'])}", 7.5, MUTED, "middle", False))
    return prims


def _stack_layout(title: str, rows: list[tuple], W: float, H: float) -> list[tuple]:
    """Stacked horizontal bars: (label, red count, amber count)."""
    prims: list[tuple] = [("text", 0, 12, title, 11, BROWN, "start", True)]
    if not rows:
        prims.append(("text", 0, 40, "Every leader in this view is on benchmark.", 9, MUTED, "start", False))
        return prims
    lw, top, bottom = 150, 26, 22
    row = (H - top - bottom) / len(rows)
    bh = max(6.0, min(16.0, row * 0.6))
    mx = max(r + a for _, r, a in rows) or 1
    x0, x1 = lw, W - 92
    for i, (l, r, a) in enumerate(rows):
        y = top + i * row + (row - bh) / 2
        wr, wa = (x1 - x0) * r / mx, (x1 - x0) * a / mx
        if r:
            prims.append(("rect", x0, y, wr, bh, STATUS["bad"]))
        if a:
            prims.append(("rect", x0 + wr, y, wa, bh, STATUS["warn"]))
        prims.append(("text", lw - 8, y + bh * 0.75, l[:26], 8.5, INK, "end", False))
        prims.append(("text", x0 + wr + wa + 4, y + bh * 0.75, f"{r} below · {a} close", 8, INK, "start", False))
    prims.append(("rect", 0, H - 12, 8, 8, STATUS["bad"]))
    prims.append(("text", 12, H - 5, "Below benchmark", 7.5, MUTED, "start", False))
    prims.append(("rect", 100, H - 12, 8, 8, STATUS["warn"]))
    prims.append(("text", 112, H - 5, "Close to benchmark", 7.5, MUTED, "start", False))
    return prims


def _spread_layout(d: dict, W: float, H: float) -> list[tuple]:
    sp = d["spread"]
    tot = sum(sp.values()) or 1
    prims: list[tuple] = [("text", 0, 12, "Leader scores", 11, BROWN, "start", True)]
    x, y, bw, bh = 0, 30, W, 26
    for s, lab in (("good", "7 or more"), ("warn", "5 to 7"), ("bad", "below 5")):
        w = bw * sp[s] / tot
        if w > 0:
            prims.append(("rect", x, y, w, bh, STATUS[s]))
            if w > 26:
                prims.append(("text", x + w / 2, y + 17, str(sp[s]), 10, "#FFFFFF", "middle", True))
        x += w
    yy = y + bh + 22
    for i, (s, lab) in enumerate((("good", "7 or more"), ("warn", "5 to 7"), ("bad", "below 5"))):
        xx = i * (W / 3)
        prims.append(("rect", xx, yy - 8, 9, 9, STATUS[s]))
        prims.append(("text", xx + 14, yy, f"{lab}: {sp[s]} ({round(100 * sp[s] / tot)}%)", 8.5, INK, "start", False))
    if d["avg_score"] is not None:
        prims.append(("text", 0, yy + 22, f"Average score {d['avg_score']:.1f} / 10 across {sum(sp.values())} leaders", 9, MUTED, "start", False))
    return prims


def _rl_drawing(prims: list[tuple], W: float, H: float):
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib.colors import HexColor
    d = Drawing(W, H)
    for p in prims:
        if p[0] == "rect":
            _, x, y, w, h, c = p
            d.add(Rect(x, H - y - h, w, h, fillColor=HexColor(c), strokeColor=None, rx=2, ry=2))
        elif p[0] == "line":
            _, x1, y1, x2, y2, c, w, dash = p
            ln = Line(x1, H - y1, x2, H - y2, strokeColor=HexColor(c), strokeWidth=w)
            if dash:
                ln.strokeDashArray = list(dash)
            d.add(ln)
        else:
            _, x, y, t, size, c, anchor, bold = p
            d.add(String(x, H - y, t, fontSize=size, fillColor=HexColor(c), textAnchor=anchor, fontName="Helvetica-Bold" if bold else "Helvetica"))
    return d


def _png(prims: list[tuple], W: float, H: float, scale: float = 3.0) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (int(W * scale), int(H * scale)), "white")
    g = ImageDraw.Draw(img)
    fonts: dict = {}

    def font(size, bold):
        k = (size, bold)
        if k not in fonts:
            f = None
            for name in (("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")):
                try:
                    f = ImageFont.truetype(name, int(size * scale))
                    break
                except OSError:
                    continue
            fonts[k] = f or ImageFont.load_default(size=int(size * scale))
        return fonts[k]
    for p in prims:
        if p[0] == "rect":
            _, x, y, w, h, c = p
            g.rounded_rectangle([x * scale, y * scale, (x + w) * scale, (y + h) * scale], radius=2 * scale, fill=c)
        elif p[0] == "line":
            _, x1, y1, x2, y2, c, w, dash = p
            if dash:
                seg, gap = dash[0] * scale, dash[1] * scale
                yy = y1 * scale
                while yy < y2 * scale:
                    g.line([(x1 * scale, yy), (x2 * scale, min(yy + seg, y2 * scale))], fill=c, width=max(1, int(w * scale)))
                    yy += seg + gap
            else:
                g.line([(x1 * scale, y1 * scale), (x2 * scale, y2 * scale)], fill=c, width=max(1, int(w * scale)))
        else:
            _, x, y, t, size, c, anchor, bold = p
            f = font(size, bold)
            tw = g.textlength(t, font=f)
            xx = x * scale - (tw if anchor == "end" else tw / 2 if anchor == "middle" else 0)
            g.text((xx, y * scale), t, fill=c, font=f, anchor="ls")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------- PDF
def render_pdf(d: dict, path: str) -> None:
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)
    from .learning.export import ASSETS
    Hx = colors.HexColor
    PW, PH = landscape(A4)
    M = 14 * mm
    CW = PW - 2 * M
    doc = SimpleDocTemplate(path, pagesize=landscape(A4), leftMargin=M, rightMargin=M, topMargin=16 * mm, bottomMargin=14 * mm,
                            title=f"{d['title']} · {d['view']}", author="People & Organisation")
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=13, textColor=Hx(INK))
    small = ParagraphStyle("s", parent=base, fontSize=8, leading=10, textColor=Hx(MUTED))
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=Hx(BROWN), spaceBefore=4, spaceAfter=6)
    h3 = ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14)
    story: list = []
    # cover band
    logo = ASSETS / "maf-logo.png"
    head = [[Paragraph(f"<font color='#FFFFFF' size='22'><b>{escape(d['title'])}</b></font><br/><font color='#F6ECD4' size='13'>{escape(d['view'])}</font><br/>"
                       f"<font color='#F6ECD4' size='9'>Data as of {escape(str(d['as_of']))}{' · ' + escape(d['period']) if d['period'] else ''} · prepared {escape(d['generated'])}</font>", base),
             Image(str(logo), width=34 * mm, height=17 * mm, kind="proportional") if logo.exists() else ""]]
    t = Table(head, colWidths=[CW - 44 * mm, 44 * mm], rowHeights=[30 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), Hx(BROWN)), ("BACKGROUND", (1, 0), (1, 0), colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (0, 0), 14), ("ALIGN", (1, 0), (1, 0), "CENTER"), ("BOX", (0, 0), (-1, -1), 0.5, Hx(LINE))]))
    story += [t, Spacer(1, 6 * mm)]
    # KPI tiles: 6 per row
    per = 6
    tw = CW / per
    cells = []
    for tl in d["tiles"]:
        cells.append(Paragraph(f"<font size='7.5' color='{MUTED}'>{escape(tl['label'].upper())}</font><br/>"
                               f"<font size='19' color='{STATUS[tl['status']] if tl['status'] in ('good', 'warn', 'bad') else INK}'><b>{escape(tl['text'])}</b></font><br/>"
                               f"<font size='7' color='{MUTED}'>{escape(tl['bench'])}</font>", ParagraphStyle("k", parent=base, leading=20)))
    rows = [cells[i:i + per] + [""] * (per - len(cells[i:i + per])) for i in range(0, len(cells), per)]
    kt = Table(rows, colWidths=[tw] * per, rowHeights=[22 * mm] * len(rows))
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 9)]
    for i, tl in enumerate(d["tiles"]):
        r, c = divmod(i, per)
        st += [("BACKGROUND", (c, r), (c, r), Hx(TINT.get(tl["status"], "#FFFFFF"))), ("LINEBEFORE", (c, r), (c, r), 4, Hx(STATUS[tl["status"]])),
               ("BOX", (c, r), (c, r), 0.5, colors.white)]
    kt.setStyle(TableStyle(st))
    story += [Paragraph("Scorecard", h2), kt, Spacer(1, 6 * mm)]
    # strong / weak / focus
    def box(title, items, col, ordered=False):
        body = "".join(f"<para leftIndent='10' bulletIndent='0'>{('%d.' % (i + 1)) if ordered else '•'}&nbsp;{escape(x)}</para>" for i, x in enumerate(items))
        return [Paragraph(f"<font color='{col}'><b>{title}</b></font>", h3)] + [Paragraph(f"{('%d. ' % (i + 1)) if ordered else '• '}{escape(x)}", base) for i, x in enumerate(items)]
    nt = Table([[box("What's strong", d["notes"]["strong"], STATUS["good"]), box("What's weak", d["notes"]["weak"], STATUS["bad"]),
                 box("Focus this week", d["notes"]["focus"], BROWN, True)]], colWidths=[CW / 3] * 3)
    nt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEABOVE", (0, 0), (0, 0), 3, Hx(STATUS["good"])),
                            ("LINEABOVE", (1, 0), (1, 0), 3, Hx(STATUS["bad"])), ("LINEABOVE", (2, 0), (2, 0), 3, Hx(BROWN)),
                            ("BACKGROUND", (0, 0), (-1, -1), Hx(BG)), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("INNERGRID", (0, 0), (-1, -1), 6, colors.white)]))
    story += [nt]
    ins = d["ai"] or talking_points(d)
    if ins:
        blk = [Spacer(1, 5 * mm), Paragraph("AI insights" if d["ai"] else "Talking points", h2)]
        if d["ai"] and d["ai_engine"]:
            blk.append(Paragraph(f"Written by {escape(d['ai_engine'])} from the summary figures above; check before sharing.", small))
        blk += [Paragraph(f"<b>{i + 1}.</b> {escape(x)}", ParagraphStyle("ai", parent=base, spaceBefore=3, leftIndent=12, firstLineIndent=-12)) for i, x in enumerate(ins)]
        story.append(KeepTogether(blk))
    # charts: two per row
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Across the " + (d["grid_kind"] or "view"), h2))
    cw, chh = CW / 2 - 6, 70 * mm
    drawings = []
    for ch in d["charts"]:
        hh = max(chh, 26 + 18 + len(ch["labels"]) * 15)
        drawings.append(_rl_drawing(_hbar_layout(ch, cw, hh), cw, hh))
    drawings.append(_rl_drawing(_stack_layout("Where leaders fall short of benchmark", d["shortfall"], cw, max(chh, 50 + len(d["shortfall"]) * 16)), cw,
                                max(chh, 50 + len(d["shortfall"]) * 16)))
    drawings.append(_rl_drawing(_spread_layout(d, cw, 46 * mm), cw, 46 * mm))
    for i in range(0, len(drawings), 2):
        pair = drawings[i:i + 2] + [""] * (2 - len(drawings[i:i + 2]))
        gt = Table([pair], colWidths=[CW / 2, CW / 2])
        gt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 12)]))
        story.append(KeepTogether(gt))
    # heat-map tables
    def heat(title, first, rows, keys, names):
        if not rows:
            return []
        hs = ParagraphStyle("hc", parent=base, fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=colors.white, alignment=1)
        cs = ParagraphStyle("cc", parent=base, fontSize=8, leading=10, alignment=2)
        data = [[Paragraph(first, ParagraphStyle("hl", parent=hs, alignment=0))] + [Paragraph(escape(names[k]), hs) for k in keys]]
        sty = [("BACKGROUND", (0, 0), (-1, 0), Hx(BROWN)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.4, colors.white),
               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        for r, row in enumerate(rows, 1):
            line = [Paragraph(f"<b>{escape(row['name'])}</b>" + (f"<br/><font size='7' color='{MUTED}'>{escape(row['sub'])}</font>" if row.get("sub") else ""), base)]
            for c in row["cells"]:
                bold = c["key"] == "score"
                line.append(Paragraph(f"<font color='{INKS.get(c['status'], INK)}'>{'<b>' if True else ''}{escape(c['text'])}</b></font>", ParagraphStyle("x", parent=cs, fontSize=9.5 if bold else 8)))
                sty.append(("BACKGROUND", (len(line) - 1, r), (len(line) - 1, r), Hx(TINT.get(c["status"], "#FFFFFF"))))
            data.append(line)
        first_w = 58 * mm
        t = Table(data, colWidths=[first_w] + [(CW - first_w) / len(keys)] * len(keys), repeatRows=1)
        if "score" in keys:
            sty.append(("LINEAFTER", (1, 0), (1, -1), 1.5, Hx(BROWN)))
        t.setStyle(TableStyle(sty))
        return [PageBreak(), Paragraph(title, h2), t]
    names = d["short"]
    story += heat(f"By {d['grid_kind'].rstrip('s')}" if d["grid_kind"] else "", (d["grid_kind"] or "").rstrip("s").capitalize(), d["grid"], d["grid_keys"], names)
    story += heat("People benchmark", "Person", d["people"], d["people_keys"], names)
    if d["people"]:
        story.append(Paragraph("Store order, not ranked. Green on or above benchmark · amber close · red below · — not measured for the role. "
                               "Score: weighted points out of 10 (Settings → Criteria).", small))

    def deco(canvas, doc_):
        canvas.saveState()
        canvas.setFillColor(Hx(BROWN))
        canvas.rect(0, PH - 5, PW, 5, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(Hx(MUTED))
        canvas.drawString(M, 8 * mm, f"P&O · {d['view']} · Confidential · Majid Al Futtaim Hypermarkets Pakistan")
        canvas.drawRightString(PW - M, 8 * mm, f"Page {doc_.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=deco, onLaterPages=deco)


# ---------------------------------------------------------------------------------------------- Word
def render_docx(d: dict, path: str) -> None:
    import docx
    from docx.enum.section import WD_ORIENT
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm, Pt, RGBColor
    from .learning.export import ASSETS
    rgb = lambda h: RGBColor.from_string(h.lstrip("#"))  # noqa: E731

    def shade(cell, color):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), color.lstrip("#"))
        tcPr.append(shd)

    def borders(table, color="FFFFFF", size=6):
        tbl = table._tbl
        pr = tbl.tblPr
        b = OxmlElement("w:tblBorders")
        for e in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{e}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(size))
            el.set(qn("w:color"), color)
            b.append(el)
        pr.append(b)

    def widths(table, mm_list):
        tblPr = table._tbl.tblPr
        lay = OxmlElement("w:tblLayout")
        lay.set(qn("w:type"), "fixed")
        tblPr.append(lay)
        table.autofit = False
        for row in table.rows:
            for c, w in zip(row.cells, mm_list):
                c.width = Mm(w)
        grid = table._tbl.tblGrid
        for gc, w in zip(grid.findall(qn("w:gridCol")), mm_list):
            gc.set(qn("w:w"), str(int(w * 56.7)))

    def run(p, text, size=10, bold=False, color=INK):
        r = p.add_run(text)
        r.bold, r.font.size, r.font.color.rgb = bold, Pt(size), rgb(color)
        return r

    doc = docx.Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Mm(297), Mm(210)
    sec.left_margin = sec.right_margin = Mm(15)
    sec.top_margin = sec.bottom_margin = Mm(14)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Segoe UI", Pt(10)
    fp = sec.footer.paragraphs[0]
    run(fp, f"P&O · {d['view']} · Confidential · Majid Al Futtaim Hypermarkets Pakistan", 7.5, color=MUTED)
    # cover
    t = doc.add_table(rows=1, cols=2)
    borders(t)
    c0, c1 = t.rows[0].cells
    shade(c0, BROWN)
    c0.width, c1.width = Mm(220), Mm(47)
    p = c0.paragraphs[0]
    run(p, d["title"], 24, True, "#FFFFFF")
    run(c0.add_paragraph(), d["view"], 14, False, "#F6ECD4")
    run(c0.add_paragraph(), f"Data as of {d['as_of']}{' · ' + d['period'] if d['period'] else ''} · prepared {d['generated']}", 9, False, "#F6ECD4")
    logo = ASSETS / "maf-logo.png"
    if logo.exists():
        c1.paragraphs[0].add_run().add_picture(str(logo), width=Mm(26))
    widths(t, [227, 40])
    doc.add_paragraph()
    # scorecard
    run(doc.add_paragraph(), "Scorecard", 15, True, BROWN)
    per = 6
    rows = [d["tiles"][i:i + per] for i in range(0, len(d["tiles"]), per)]
    kt = doc.add_table(rows=len(rows), cols=per)
    borders(kt, "FFFFFF", 18)
    for r, chunk in enumerate(rows):
        for c in range(per):
            cell = kt.cell(r, c)
            if c >= len(chunk):
                continue
            tl = chunk[c]
            shade(cell, TINT.get(tl["status"], "#FFFFFF"))
            run(cell.paragraphs[0], tl["label"].upper(), 7, True, MUTED)
            run(cell.add_paragraph(), tl["text"], 18, True, STATUS[tl["status"]] if tl["status"] in ("good", "warn", "bad") else INK)
            run(cell.add_paragraph(), tl["bench"], 7, False, MUTED)
    widths(kt, [267 / per] * per)
    doc.add_paragraph()
    nt = doc.add_table(rows=1, cols=3)
    borders(nt, "FFFFFF", 24)
    for i, (title, items, col, numbered) in enumerate((("What's strong", d["notes"]["strong"], STATUS["good"], False),
                                                     ("What's weak", d["notes"]["weak"], STATUS["bad"], False),
                                                     ("Focus this week", d["notes"]["focus"], BROWN, True))):
        cell = nt.cell(0, i)
        shade(cell, "F5F5F7")
        run(cell.paragraphs[0], title, 12, True, col)
        for j, x in enumerate(items):
            run(cell.add_paragraph(), (f"{j + 1}. " if numbered else "• ") + x, 9.5)
    widths(nt, [89, 89, 89])
    ins = d["ai"] or talking_points(d)
    if ins:
        doc.add_paragraph()
        run(doc.add_paragraph(), "AI insights" if d["ai"] else "Talking points", 15, True, BROWN)
        if d["ai"] and d["ai_engine"]:
            run(doc.add_paragraph(), f"Written by {d['ai_engine']} from the summary figures; check before sharing.", 8, False, MUTED)
        for i, x in enumerate(ins):
            p = doc.add_paragraph()
            run(p, f"{i + 1}.  ", 10, True, BROWN)
            run(p, x, 10)
    # charts
    doc.add_page_break()
    run(doc.add_paragraph(), "Across the " + (d["grid_kind"] or "view"), 15, True, BROWN)
    W = 380.0
    imgs = []
    for ch in d["charts"]:
        hh = max(200.0, 44 + len(ch["labels"]) * 17)
        imgs.append((_png(_hbar_layout(ch, W, hh), W, hh), hh))
    hs = max(200.0, 52 + len(d["shortfall"]) * 18)
    imgs.append((_png(_stack_layout("Where leaders fall short of benchmark", d["shortfall"], W, hs), W, hs), hs))
    imgs.append((_png(_spread_layout(d, W, 130), W, 130), 130))
    gt = doc.add_table(rows=(len(imgs) + 1) // 2, cols=2)
    for i, (png, hh) in enumerate(imgs):
        cell = gt.cell(i // 2, i % 2)
        cell.paragraphs[0].add_run().add_picture(io.BytesIO(png), width=Mm(128))
    widths(gt, [133, 133])

    def heat(title, first, rows, keys):
        if not rows:
            return
        doc.add_page_break()
        run(doc.add_paragraph(), title, 15, True, BROWN)
        tb = doc.add_table(rows=1, cols=len(keys) + 1)
        tb.alignment = WD_TABLE_ALIGNMENT.CENTER
        borders(tb, "FFFFFF", 6)
        hdr = tb.rows[0].cells
        for j, txt in enumerate([first] + [d["short"][k] for k in keys]):
            shade(hdr[j], BROWN)
            run(hdr[j].paragraphs[0], txt, 8, True, "#FFFFFF")
        for row in rows:
            cells = tb.add_row().cells
            run(cells[0].paragraphs[0], row["name"], 9, True)
            if row.get("sub"):
                run(cells[0].add_paragraph(), row["sub"], 7, False, MUTED)
            for j, c in enumerate(row["cells"], 1):
                shade(cells[j], TINT.get(c["status"], "#FFFFFF"))
                pp = cells[j].paragraphs[0]
                pp.alignment = 2
                run(pp, c["text"], 10 if c["key"] == "score" else 8.5, True, INKS.get(c["status"], INK))
        widths(tb, [62] + [(267 - 62) / len(keys)] * len(keys))
        trPr = tb.rows[0]._tr.get_or_add_trPr()
        th = OxmlElement("w:tblHeader")
        th.set(qn("w:val"), "true")
        trPr.append(th)
    heat(f"By {d['grid_kind'].rstrip('s')}" if d["grid_kind"] else "", (d["grid_kind"] or "").rstrip("s").capitalize(), d["grid"], d["grid_keys"])
    heat("People benchmark", "Person", d["people"], d["people_keys"])
    if d["people"]:
        run(doc.add_paragraph(), "Store order, not ranked. Green on or above benchmark · amber close · red below · — not measured for the role. "
                                 "Score: weighted points out of 10 (Settings → Criteria).", 8, False, MUTED)
    doc.save(path)


# ---------------------------------------------------------------------------------------------- PowerPoint
def render_pptx(d: dict, path: str) -> None:
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Emu, Inches, Pt
    from .learning.export import ASSETS
    rgb = lambda h: RGBColor.from_string(h.lstrip("#"))  # noqa: E731
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    FONT = "Segoe UI"
    logo = ASSETS / "maf-logo.png"

    def text(sl, x, y, w, h, t, size=14, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
        tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap, tf.vertical_anchor = True, anchor
        tf.margin_left = tf.margin_right = Inches(0.05)
        lines = t if isinstance(t, list) else [t]
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            items = line if isinstance(line, list) else [(line, size, bold, color)]
            for (s_, sz, b_, c_) in items:
                r = p.add_run()
                r.text, r.font.size, r.font.bold, r.font.name = s_, Pt(sz), b_, FONT
                r.font.color.rgb = rgb(c_)
        return tb

    def rect(sl, x, y, w, h, fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE, line=None):
        s = sl.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
        if line:
            s.line.color.rgb = rgb(line)
            s.line.width = Pt(0.75)
        else:
            s.line.fill.background()
        s.shadow.inherit = False
        if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
            s.adjustments[0] = 0.08
        return s

    def frame(title, kicker=""):
        sl = prs.slides.add_slide(blank)
        rect(sl, 0, 0, 13.333, 0.12, BROWN, MSO_SHAPE.RECTANGLE)
        text(sl, 0.55, 0.32, 10.5, 0.4, kicker or d["view"], 11, False, GOLD)
        text(sl, 0.55, 0.62, 11.5, 0.7, title, 26, True, INK)
        if logo.exists():
            sl.shapes.add_picture(str(logo), Inches(11.75), Inches(0.35), height=Inches(0.55))
        text(sl, 0.55, 7.05, 9, 0.3, f"P&O Department Review · {d['view']} · Confidential", 8, False, MUTED)
        text(sl, 11.3, 7.05, 1.5, 0.3, str(len(prs.slides._sldIdLst)), 8, False, MUTED, PP_ALIGN.RIGHT)
        return sl

    # 1 · cover
    sl = prs.slides.add_slide(blank)
    rect(sl, 0, 0, 13.333, 7.5, BROWN, MSO_SHAPE.RECTANGLE)
    rect(sl, 0, 5.9, 13.333, 1.6, "#7A3A14", MSO_SHAPE.RECTANGLE)
    if logo.exists():
        card = rect(sl, 0.75, 0.7, 2.3, 1.1, "#FFFFFF")
        sl.shapes.add_picture(str(logo), Inches(0.95), Inches(0.82), height=Inches(0.86))
    text(sl, 0.75, 2.4, 11.5, 0.5, "PEOPLE & ORGANISATION", 14, True, "#F6ECD4")
    text(sl, 0.75, 2.85, 11.5, 1.1, d["title"], 48, True, "#FFFFFF")
    text(sl, 0.75, 3.95, 11.5, 0.7, d["view"], 26, False, "#F6ECD4")
    text(sl, 0.75, 6.25, 11.5, 0.5, f"Data as of {d['as_of']}{' · ' + d['period'] if d['period'] else ''}  ·  prepared {d['generated']}", 13, False, "#F6ECD4")

    # 2 · scorecard tiles
    sl = frame("Scorecard", "How the numbers stand against benchmark")
    n = len(d["tiles"])
    cols = 4 if n <= 8 else 5 if n <= 10 else 6
    gw, gh = 12.2, 5.3
    tw, th = gw / cols - 0.18, min(2.4, gh / ((n + cols - 1) // cols) - 0.18)
    for i, tl in enumerate(d["tiles"]):
        r, c = divmod(i, cols)
        x, y = 0.55 + c * (tw + 0.18), 1.55 + r * (th + 0.18)
        rect(sl, x, y, tw, th, TINT.get(tl["status"], "#F5F5F7"))
        rect(sl, x, y, 0.09, th, STATUS[tl["status"]], MSO_SHAPE.RECTANGLE)
        text(sl, x + 0.22, y + 0.12, tw - 0.3, 0.35, tl["label"].upper(), 10, True, MUTED)
        text(sl, x + 0.22, y + 0.5, tw - 0.3, 0.85, tl["text"].replace(" pts", ""), 34 if len(tl["text"]) <= 6 else 28, True,
             STATUS[tl["status"]] if tl["status"] in ("good", "warn", "bad") else INK)
        text(sl, x + 0.22, y + th - 0.42, tw - 0.3, 0.3, tl["bench"], 9, False, MUTED)

    # 3 · strong / weak / focus
    sl = frame("What's strong, what's weak, what to focus on")
    for i, (title, items, col, numbered) in enumerate((("What's strong", d["notes"]["strong"], STATUS["good"], False),
                                                     ("What's weak", d["notes"]["weak"], STATUS["bad"], False),
                                                     ("Focus this week", d["notes"]["focus"], BROWN, True))):
        x = 0.55 + i * 4.12
        rect(sl, x, 1.55, 3.95, 5.25, "#F5F5F7")
        rect(sl, x, 1.55, 3.95, 0.09, col, MSO_SHAPE.RECTANGLE)
        text(sl, x + 0.25, 1.8, 3.5, 0.45, title, 18, True, col)
        text(sl, x + 0.25, 2.35, 3.5, 4.3, [[(f"{j + 1}.  " if numbered else "•  ", 12, True, col), (it, 12, False, INK)] for j, it in enumerate(items)], 12)

    # 4 · insights
    ins = d["ai"] or talking_points(d)
    if ins:
        sl = frame("AI insights" if d["ai"] else "Talking points", f"Written by {d['ai_engine']} from the summary figures · check before sharing" if d["ai"] else "Worked out from the numbers")
        for i, x in enumerate(ins[:6]):
            r, c = divmod(i, 2)
            xx, yy = 0.55 + c * 6.15, 1.6 + r * 1.75
            rect(sl, xx, yy, 5.95, 1.6, "#FFFFFF", line=LINE)
            circ = sl.shapes.add_shape(MSO_SHAPE.OVAL, Inches(xx + 0.22), Inches(yy + 0.25), Inches(0.5), Inches(0.5))
            circ.fill.solid()
            circ.fill.fore_color.rgb = rgb(BROWN)
            circ.line.fill.background()
            ctf = circ.text_frame
            ctf.paragraphs[0].alignment = PP_ALIGN.CENTER
            rr = ctf.paragraphs[0].add_run()
            rr.text, rr.font.size, rr.font.bold, rr.font.color.rgb, rr.font.name = str(i + 1), Pt(14), True, rgb("#FFFFFF"), FONT
            text(sl, xx + 0.9, yy + 0.18, 4.9, 1.3, x, 12.5, False, INK, anchor=MSO_ANCHOR.MIDDLE)

    # 5 · native charts, two per slide
    def bar_chart(sl, x, y, w, h, ch):
        cd = CategoryChartData()
        cd.categories = ch["labels"]
        cd.add_series(ch["title"], ch["values"])
        gf = sl.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
        c = gf.chart
        c.has_legend = False
        c.has_title = True
        c.chart_title.text_frame.text = ch["title"]
        tp = c.chart_title.text_frame.paragraphs[0]
        tp.runs[0].font.size, tp.runs[0].font.bold, tp.runs[0].font.color.rgb, tp.runs[0].font.name = Pt(13), True, rgb(BROWN), FONT
        pl = c.plots[0]
        pl.gap_width = 45
        pl.has_data_labels = True
        dl = pl.data_labels
        dl.font.size, dl.font.name = Pt(9), FONT
        dl.number_format = {"pct0": '0"%"', "pct1": '0.0"%"', "pct1s": '+0.0"%";-0.0"%"', "pct0s": '+0"%";-0"%"', "pct2s": '+0.00"%";-0.00"%"', "pp2s": '+0.00;-0.00', "dec1": "0.0"}.get(ch["fmt"], "0")
        dl.number_format_is_linked = False
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
        for i, col in enumerate(ch["colors"]):
            pt = pl.series[0].points[i]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = rgb(col)
        ca = c.category_axis
        ca.reverse_order = True
        ca.tick_label_position = XL_TICK_LABEL_POSITION.LOW          # names stay left of negative bars
        ca.tick_labels.font.size, ca.tick_labels.font.name = Pt(9), FONT
        ca.format.line.color.rgb = rgb(LINE)
        va = c.value_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = rgb("#EEEEEE")
        va.tick_labels.font.size, va.tick_labels.font.color.rgb = Pt(8), rgb(MUTED)
        va.format.line.fill.background()
        if ch.get("bench") is not None:
            text(sl, x, y + h - 0.05, w, 0.3, f"Benchmark: {review.fmt(ch['key'], ch['bench'])} ({'higher' if ch['better'] == 'up' else 'lower'} is better) · "
                 "green on or above · amber close · red below", 9, False, MUTED)

    charts = list(d["charts"])
    for i in range(0, len(charts), 2):
        sl = frame("Across the " + (d["grid_kind"] or "view"), "Key criteria, coloured against benchmark")
        for j, ch in enumerate(charts[i:i + 2]):
            bar_chart(sl, 0.55 + j * 6.2, 1.5, 6.0, 5.2, ch)
    # people shortfall + score spread
    if d["people"]:
        sl = frame("The leaders in this view", "Where they fall short, and how their scores spread")
        if d["shortfall"]:
            cd = CategoryChartData()
            cd.categories = [s[0] for s in d["shortfall"]]
            cd.add_series("Below benchmark", [s[1] for s in d["shortfall"]])
            cd.add_series("Close to benchmark", [s[2] for s in d["shortfall"]])
            gf = sl.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED, Inches(0.55), Inches(1.5), Inches(7.3), Inches(5.3), cd)
            c = gf.chart
            c.has_title = True
            c.chart_title.text_frame.text = "Leaders short of benchmark, by criterion"
            tp = c.chart_title.text_frame.paragraphs[0]
            tp.runs[0].font.size, tp.runs[0].font.bold, tp.runs[0].font.color.rgb, tp.runs[0].font.name = Pt(13), True, rgb(BROWN), FONT
            c.has_legend, c.legend.position, c.legend.include_in_layout = True, XL_LEGEND_POSITION.BOTTOM, False
            c.legend.font.size, c.legend.font.name = Pt(9), FONT
            for s_, col in zip(c.plots[0].series, (STATUS["bad"], STATUS["warn"])):
                s_.format.fill.solid()
                s_.format.fill.fore_color.rgb = rgb(col)
            c.plots[0].gap_width = 50
            c.plots[0].has_data_labels = True
            c.plots[0].data_labels.font.size = Pt(9)
            c.plots[0].data_labels.font.color.rgb = rgb("#FFFFFF")
            c.category_axis.reverse_order = True
            c.category_axis.tick_labels.font.size = Pt(10)
            c.value_axis.visible = False
            c.value_axis.has_major_gridlines = False
        sp = d["spread"]
        if sum(sp.values()):
            cd = CategoryChartData()
            cd.categories = ["Score 7 or more", "Score 5 to 7", "Score below 5"]
            cd.add_series("Leaders", [sp["good"], sp["warn"], sp["bad"]])
            gf = sl.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, Inches(8.2), Inches(1.5), Inches(4.6), Inches(4.6), cd)
            c = gf.chart
            c.has_title = True
            c.chart_title.text_frame.text = "Leader scores"
            tp = c.chart_title.text_frame.paragraphs[0]
            tp.runs[0].font.size, tp.runs[0].font.bold, tp.runs[0].font.color.rgb, tp.runs[0].font.name = Pt(13), True, rgb(BROWN), FONT
            c.has_legend, c.legend.position, c.legend.include_in_layout = True, XL_LEGEND_POSITION.BOTTOM, False
            c.legend.font.size = Pt(9)
            for i, col in enumerate((STATUS["good"], STATUS["warn"], STATUS["bad"])):
                pt = c.plots[0].series[0].points[i]
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = rgb(col)
            c.plots[0].has_data_labels = True
            c.plots[0].data_labels.font.size, c.plots[0].data_labels.font.bold = Pt(12), True
            c.plots[0].data_labels.font.color.rgb = rgb("#FFFFFF")
            if d["avg_score"] is not None:
                text(sl, 8.2, 6.25, 4.6, 0.4, f"Average score {d['avg_score']:.1f} / 10", 13, True, INK, PP_ALIGN.CENTER)

    # 6 · heat-map tables, paged
    def table_slides(title, kicker, first, rows, keys, per=10):
        for i in range(0, len(rows), per):
            chunk = rows[i:i + per]
            sl = frame(title + (f" ({i // per + 1}/{(len(rows) + per - 1) // per})" if len(rows) > per else ""), kicker)
            ncol = len(keys) + 1
            tw_ = 12.25
            first_w = 2.9
            shp = sl.shapes.add_table(len(chunk) + 1, ncol, Inches(0.55), Inches(1.5), Inches(tw_), Inches(0.42 * (len(chunk) + 1)))
            tb = shp.table
            tb.first_row = True
            tb.columns[0].width = Inches(first_w)
            for j in range(1, ncol):
                tb.columns[j].width = Emu(int(Inches((tw_ - first_w) / (ncol - 1))))

            def put(cell, t, size, bold, color, fill, align=PP_ALIGN.RIGHT, sub=None):
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(fill)
                cell.margin_left = cell.margin_right = Inches(0.06)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                tf = cell.text_frame
                tf.word_wrap = True
                p = tf.paragraphs[0]
                p.alignment = align
                r = p.add_run()
                r.text, r.font.size, r.font.bold, r.font.name = t, Pt(size), bold, FONT
                r.font.color.rgb = rgb(color)
                if sub:
                    p2 = tf.add_paragraph()
                    p2.alignment = align
                    r2 = p2.add_run()
                    r2.text, r2.font.size, r2.font.name = sub, Pt(8), FONT
                    r2.font.color.rgb = rgb(MUTED)
            put(tb.cell(0, 0), first, 10, True, "#FFFFFF", BROWN, PP_ALIGN.LEFT)
            for j, k in enumerate(keys, 1):
                put(tb.cell(0, j), d["short"][k], 9, True, "#FFFFFF", BROWN, PP_ALIGN.CENTER)
            for r_, row in enumerate(chunk, 1):
                put(tb.cell(r_, 0), row["name"], 11, True, INK, "#FFFFFF", PP_ALIGN.LEFT, row.get("sub"))
                for j, c in enumerate(row["cells"], 1):
                    put(tb.cell(r_, j), c["text"], 13 if c["key"] == "score" else 11, True, INKS.get(c["status"], INK), TINT.get(c["status"], "#FFFFFF"))
    if d["grid"]:
        table_slides(f"By {d['grid_kind'].rstrip('s')}", "Every criterion, coloured against benchmark", (d["grid_kind"] or "").rstrip("s").capitalize(),
                     d["grid"], d["grid_keys"], per=12 if len(d["grid"]) <= 14 else 10)
    if d["people"]:
        table_slides("People benchmark", "Store order, not ranked · score out of 10 from the weighted criteria", "Person", d["people"], d["people_keys"], per=9)
    prs.save(path)


def render_xlsx(d: dict, path: str) -> None:
    """The tables with their colours, for anyone who wants to work with the numbers."""
    import xlsxwriter
    wb = xlsxwriter.Workbook(path)
    hdr = wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": BROWN, "border": 1, "border_color": "#FFFFFF", "text_wrap": True, "valign": "vcenter"})
    title = wb.add_format({"bold": True, "font_size": 16, "font_color": BROWN})
    fm = {s: wb.add_format({"bg_color": TINT[s], "font_color": INKS[s], "bold": True, "align": "right", "border": 1, "border_color": "#FFFFFF"}) for s in TINT}
    name = wb.add_format({"bold": True})
    sub = wb.add_format({"font_color": MUTED, "font_size": 9})
    ws = wb.add_worksheet("Scorecard")
    ws.write(0, 0, f"{d['title']} · {d['view']}", title)
    ws.write(1, 0, f"Data as of {d['as_of']} · prepared {d['generated']}", sub)
    ws.write_row(3, 0, ["Criterion", "Result", "Status", "Benchmark"], hdr)
    for i, t in enumerate(d["tiles"], 4):
        ws.write(i, 0, t["label"], name)
        ws.write(i, 1, t["text"], fm.get(t["status"], fm["none"]))
        ws.write(i, 2, WORD[t["status"]])
        ws.write(i, 3, t["bench"])
    r = len(d["tiles"]) + 6
    for title_, items in (("What's strong", d["notes"]["strong"]), ("What's weak", d["notes"]["weak"]), ("Focus this week", d["notes"]["focus"]),
                          ("AI insights" if d["ai"] else "Talking points", d["ai"] or talking_points(d))):
        ws.write(r, 0, title_, name)
        for x in items:
            r += 1
            ws.write(r, 0, "• " + x)
        r += 2
    ws.set_column(0, 0, 40)
    ws.set_column(1, 3, 22)
    for sheet, first, rows, keys in ((d["grid_kind"].capitalize() or "Grid", "Name", d["grid"], d["grid_keys"]), ("People", "Person", d["people"], d["people_keys"])):
        if not rows:
            continue
        ws = wb.add_worksheet(sheet[:30])
        ws.write_row(0, 0, [first] + (["Role · area"] if sheet == "People" else []) + [d["short"][k] for k in keys], hdr)
        for i, row in enumerate(rows, 1):
            ws.write(i, 0, row["name"], name)
            off = 1
            if sheet == "People":
                ws.write(i, 1, row.get("sub", ""), sub)
                off = 2
            for j, c in enumerate(row["cells"]):
                ws.write(i, j + off, c["text"], fm.get(c["status"], fm["none"]))
        ws.set_column(0, 0, 28)
        ws.set_column(1, 1, 34 if sheet == "People" else 12)
        ws.set_column(2, 20, 12)
        ws.freeze_panes(1, 1)
    wb.close()


RENDER = {"pdf": render_pdf, "docx": render_docx, "pptx": render_pptx, "xlsx": render_xlsx}
