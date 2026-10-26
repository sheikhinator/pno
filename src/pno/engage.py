"""2.3: engagement pulse surveys, recognition (stars of the month with certificates) and the month-close pack.

Surveys are anonymous: results for a store or department are shown only when at least MIN_GROUP people answered,
and comments are never linked to a person. A survey file is any sheet with one row per answer: optional Store and
Department columns, question columns scored 1-5, an optional 0-10 'recommend' (eNPS) column and optional comments.
"""

from __future__ import annotations

import csv
import io
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from .db import now

MIN_GROUP = 5

QUESTIONS = [
    ("I know what is expected of me at work.", "مجھے معلوم ہے کہ کام پر مجھ سے کیا توقع کی جاتی ہے۔", "Clarity"),
    ("I have the tools and equipment to do my job well.", "میرے پاس اپنا کام اچھی طرح کرنے کے لیے ضروری سامان موجود ہے۔", "Resources"),
    ("My manager treats me with respect.", "میرا مینیجر میرے ساتھ عزت سے پیش آتا ہے۔", "Manager"),
    ("My manager gives me useful feedback.", "میرا مینیجر مجھے مفید رائے دیتا ہے۔", "Manager"),
    ("My shift schedule is fair and shared in time.", "میرا شفٹ شیڈول منصفانہ ہے اور وقت پر بتایا جاتا ہے۔", "Scheduling"),
    ("My workload is manageable.", "میرے کام کا بوجھ قابلِ برداشت ہے۔", "Workload"),
    ("I have received the training I need.", "مجھے ضروری تربیت ملی ہے۔", "Growth"),
    ("I can see a future for myself in this company.", "مجھے اس کمپنی میں اپنا مستقبل نظر آتا ہے۔", "Growth"),
    ("I am recognised when I do good work.", "اچھا کام کرنے پر میری تعریف کی جاتی ہے۔", "Recognition"),
    ("I feel safe at work.", "میں کام پر خود کو محفوظ محسوس کرتا / کرتی ہوں۔", "Wellbeing"),
    ("I am paid fairly for the work I do.", "مجھے اپنے کام کا مناسب معاوضہ ملتا ہے۔", "Pay"),
    ("I would like to be working here in a year.", "میں ایک سال بعد بھی یہیں کام کرنا چاہوں گا / گی۔", "Intent to stay"),
]
ENPS_Q = ("How likely are you to recommend Carrefour as a place to work? (0-10)", "آپ کیرفور کو کام کی جگہ کے طور پر کتنا تجویز کریں گے؟ (0 سے 10)")

THEMES = {
    "Pay": r"salar|pay\b|wage|increment|bonus|overtime|\bot\b|money|تنخواہ",
    "Manager": r"manager|supervisor|boss|team lead|respect|behaviou?r|shout|favou?rit|مینیجر",
    "Schedule & hours": r"shift|schedule|roster|hours|late night|off day|weekend|leave|holiday|چھٹی|شفٹ",
    "Workload & staffing": r"workload|staff|short|pressure|busy|tired|too much|manpower",
    "Growth & training": r"promot|growth|career|training|learn|develop|future",
    "Facilities & transport": r"transport|pick ?up|canteen|food|water|washroom|locker|break room|uniform|ac\b|air",
    "Recognition": r"recogni|appreciat|thank|reward|award",
    "Safety": r"safe|injur|harass|security|danger",
}


# ---------------------------------------------------------------------------------------------- reading
def _rows_from_file(path: str) -> list[list[Any]]:
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    raw = p.read_bytes().decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(raw[:4000], delimiters=",\t;") if raw.strip() else csv.excel
    return [r for r in csv.reader(io.StringIO(raw), dialect)]


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.match(r"^\s*(\d+(?:\.\d+)?)", str(v))
    if m:
        return float(m.group(1))
    words = {"strongly agree": 5, "agree": 4, "neutral": 3, "neither": 3, "disagree": 2, "strongly disagree": 1}
    s = str(v).strip().lower()
    for k in sorted(words, key=len, reverse=True):
        if s.startswith(k):
            return float(words[k])
    return None


def parse(rows: list[list[Any]]) -> dict:
    """Find the header row and classify columns: store, department, 1-5 questions, 0-10 eNPS, comments."""
    rows = [r for r in rows if r and any(c not in (None, "") for c in r)]
    if len(rows) < 2:
        raise ValueError("The survey file has no answers.")
    hi = 0
    for i, r in enumerate(rows[:10]):
        texts = sum(1 for c in r if isinstance(c, str) and len(c.strip()) > 1 and _num(c) is None)
        if texts >= max(2, len([c for c in r if c not in (None, "")]) * 0.6):
            hi = i
            break
    head = [str(c or "").strip() for c in rows[hi]]
    body = rows[hi + 1:]
    cols = {"store": None, "dept": None, "questions": [], "enps": None, "comments": []}
    for j, h in enumerate(head):
        hl = h.lower()
        vals = [r[j] for r in body if j < len(r) and r[j] not in (None, "")]
        nums = [_num(v) for v in vals]
        numeric = [x for x in nums if x is not None]
        if re.search(r"\b(store|branch|location|business unit)\b", hl) and cols["store"] is None:
            cols["store"] = j
        elif re.search(r"\b(dep(artmen)?t|section|team)\b", hl) and cols["dept"] is None and len(numeric) < len(vals) * 0.5:
            cols["dept"] = j
        elif re.search(r"recommend|enps|e-nps|0\s*-\s*10", hl) and numeric and max(numeric) <= 10:
            cols["enps"] = j
        elif vals and len(numeric) >= len(vals) * 0.8 and numeric and max(numeric) <= 5 and min(numeric) >= 1:
            cols["questions"].append(j)
        elif vals and len(numeric) < len(vals) * 0.3 and statistics.mean(len(str(v)) for v in vals) > 12 and not re.search(r"name|emp|id\b|code|date|time|email", hl):
            cols["comments"].append(j)
    if not cols["questions"] and cols["enps"] is None:
        raise ValueError("No question columns scored 1-5 (or a 0-10 'recommend' column) were found.")
    answers = []
    for r in body:
        g = lambda j: (r[j] if j is not None and j < len(r) else None)  # noqa: E731
        a = {"store": str(g(cols["store"]) or "").strip(), "dept": str(g(cols["dept"]) or "").strip(),
             "q": [_num(g(j)) for j in cols["questions"]], "enps": _num(g(cols["enps"])),
             "comments": [str(g(j)).strip() for j in cols["comments"] if g(j) not in (None, "") and len(str(g(j)).strip()) > 2]}
        if any(x is not None for x in a["q"]) or a["enps"] is not None or a["comments"]:
            answers.append(a)
    return {"questions": [head[j] for j in cols["questions"]], "has_enps": cols["enps"] is not None, "answers": answers,
            "has_store": cols["store"] is not None, "has_dept": cols["dept"] is not None}


def add_survey(db, path: str, title: str = "", wave: str = "") -> int:
    from .po import canon
    parsed = parse(_rows_from_file(path))
    for a in parsed["answers"]:
        if a["store"]:
            a["store"] = canon.store(a["store"]) or a["store"]
    title = (title or re.sub(r"[_-]+", " ", Path(path).stem)).strip()[:120]
    wave = wave or date.today().strftime("%Y-%m")
    return db.x("INSERT INTO surveys(title, wave, questions, has_enps, answers, n, created_at) VALUES(?,?,?,?,?,?,?)",
                (title, wave, json.dumps(parsed["questions"]), int(parsed["has_enps"]), json.dumps(parsed["answers"]), len(parsed["answers"]),
                 now())).lastrowid


# ---------------------------------------------------------------------------------------------- results
def _enps(vals: list[float]) -> float | None:
    v = [x for x in vals if x is not None]
    if not v:
        return None
    return round(100 * (sum(1 for x in v if x >= 9) - sum(1 for x in v if x <= 6)) / len(v))


def _fav(vals: list[float]) -> float | None:
    v = [x for x in vals if x is not None]
    return round(100 * sum(1 for x in v if x >= 4) / len(v)) if v else None


def _theme(text: str) -> list[str]:
    return [k for k, rx in THEMES.items() if re.search(rx, text, re.I)] or ["Other"]


def results(db, survey_id: int | None = None) -> dict:
    surveys = [dict(r) for r in db.q("SELECT id, title, wave, n, has_enps, created_at FROM surveys ORDER BY wave, id")]
    if not surveys:
        return {"has_data": False, "surveys": [], "template_questions": [q[0] for q in QUESTIONS], "min_group": MIN_GROUP}
    sid = survey_id or surveys[-1]["id"]
    s = db.q1("SELECT * FROM surveys WHERE id=?", (sid,))
    qs, ans = json.loads(s["questions"]), json.loads(s["answers"])
    per_q = []
    for i, q in enumerate(qs):
        v = [a["q"][i] for a in ans if i < len(a["q"]) and a["q"][i] is not None]
        if v:
            dist = Counter(int(round(x)) for x in v)
            per_q.append({"question": q, "n": len(v), "avg": round(statistics.mean(v), 2), "favourable": _fav(v),
                          "unfavourable": round(100 * sum(1 for x in v if x <= 2) / len(v)), "dist": [dist.get(k, 0) for k in range(1, 6)]})
    overall_fav = round(statistics.mean([q["favourable"] for q in per_q])) if per_q else None

    def groups(key):
        g: dict[str, list] = defaultdict(list)
        for a in ans:
            if a.get(key):
                g[a[key]].append(a)
        out = []
        for k, items in sorted(g.items()):
            if len(items) < MIN_GROUP:
                out.append({"name": k, "n": len(items), "hidden": True})
                continue
            row = {"name": k, "n": len(items), "hidden": False, "enps": _enps([a["enps"] for a in items]),
                   "favourable": round(statistics.mean([f for f in (_fav([a["q"][i] for a in items if i < len(a["q"])]) for i in range(len(qs))) if f is not None]))
                   if qs else None,
                   "by_q": [_fav([a["q"][i] for a in items if i < len(a["q"])]) for i in range(len(qs))]}
            out.append(row)
        return out

    comments = [c for a in ans for c in a["comments"]]
    themes = Counter(t for c in comments for t in _theme(c))
    trend = []
    for sv in surveys:
        r = db.q1("SELECT questions, answers FROM surveys WHERE id=?", (sv["id"],))
        a2, q2 = json.loads(r["answers"]), json.loads(r["questions"])
        favs = [f for f in (_fav([a["q"][i] for a in a2 if i < len(a["q"])]) for i in range(len(q2))) if f is not None]
        trend.append({"id": sv["id"], "wave": sv["wave"], "title": sv["title"], "n": sv["n"], "enps": _enps([a["enps"] for a in a2]),
                      "favourable": round(statistics.mean(favs)) if favs else None})
    strengths = sorted(per_q, key=lambda q: -q["favourable"])[:3]
    concerns = sorted(per_q, key=lambda q: q["favourable"])[:3]
    return {"has_data": True, "surveys": surveys, "survey": {"id": s["id"], "title": s["title"], "wave": s["wave"], "n": s["n"]},
            "enps": _enps([a["enps"] for a in ans]) if s["has_enps"] else None, "favourable": overall_fav, "questions": per_q,
            "stores": groups("store"), "depts": groups("dept"), "themes": themes.most_common(),
            "comments": [{"text": c, "themes": _theme(c)} for c in comments][:400], "trend": trend,
            "strengths": strengths, "concerns": concerns, "min_group": MIN_GROUP,
            "response_counts": {"answers": len(ans), "with_comment": sum(1 for a in ans if a["comments"])}}


def delete_survey(db, survey_id: int) -> None:
    db.x("DELETE FROM surveys WHERE id=?", (survey_id,))


def template_xlsx(path: str, stores: list[str]) -> None:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Answers"
    head = ["Store", "Department"] + [f"{q[0]}\n{q[1]}" for q in QUESTIONS] + [f"{ENPS_Q[0]}\n{ENPS_Q[1]}", "Anything else you want to tell us?\nکچھ اور کہنا چاہیں؟"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="6B3A1E")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[1].height = 90
    for i in range(1, len(head) + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 22 if i > 2 else 20
    dv = DataValidation(type="whole", operator="between", formula1="1", formula2="5", showErrorMessage=True, error="Answer 1 (strongly disagree) to 5 (strongly agree)")
    ws.add_data_validation(dv)
    dv.add(f"C2:{openpyxl.utils.get_column_letter(2 + len(QUESTIONS))}2000")
    dv2 = DataValidation(type="whole", operator="between", formula1="0", formula2="10")
    ws.add_data_validation(dv2)
    col = openpyxl.utils.get_column_letter(3 + len(QUESTIONS))
    dv2.add(f"{col}2:{col}2000")
    if stores:
        ls = wb.create_sheet("Stores")
        for s in stores:
            ls.append([s])
        dv3 = DataValidation(type="list", formula1=f"=Stores!$A$1:$A${len(stores)}")
        ws.add_data_validation(dv3)
        dv3.add("A2:A2000")
    ws.freeze_panes = "C2"
    g = wb.create_sheet("How to use", 0)
    for line in ["P&O pulse survey (anonymous)", "", "• One row per person. Do not write names or employee numbers.",
                 "• Questions 1-5: 1 = strongly disagree, 5 = strongly agree.", "• Recommend question: 0-10.",
                 f"• Results for a store or department are only shown when {MIN_GROUP} or more people answered.",
                 "• When done, import this file in P&O → Engagement → Import results."]:
        g.append([line])
    g["A1"].font = Font(bold=True, size=14, color="6B3A1E")
    g.column_dimensions["A"].width = 90
    wb.save(path)


# ---------------------------------------------------------------------------------------------- recognition
def stars(ins, mm=None) -> dict:
    """Stars of the month: the best leader in each store by leader index, the most consistent attendance, top NPS sections."""
    from .po.format import leader_name
    out: list[dict] = []
    by_store: dict[str, list] = defaultdict(list)
    for l in ins.leaders():
        if l.score is not None and l.store:
            by_store[l.store].append(l)
    for store, ls in sorted(by_store.items()):
        best = max(ls, key=lambda l: l.score)
        if best.score >= 60:
            out.append({"name": leader_name(best), "store": store, "role": best.designation, "award": "Leader of the month",
                        "why": f"Highest leader index in {store} ({best.score / 10:.1f}/10) leading {best.section_text or 'the store'}", "score": round(best.score, 1)})
    top = sorted([l for ls in by_store.values() for l in ls], key=lambda l: -(l.score or 0))[:3]
    for i, l in enumerate(top):
        out.append({"name": leader_name(l), "store": l.store, "role": l.designation, "award": ["Country champion", "Country runner-up", "Country third place"][i],
                    "why": f"#{i + 1} leader index in the country ({l.score / 10:.1f}/10)", "score": round(l.score, 1)})
    if mm is not None:
        perfect = []
        for p in mm.people.values():
            a = getattr(p, "att", None)
            if a and a.get("worked", 0) >= 20 and not a.get("absent") and not a.get("fixes") and not a.get("short_days"):
                perfect.append(p)
        for p in sorted(perfect, key=lambda p: -p.att.get("worked", 0))[:10]:
            out.append({"name": p.name, "store": p.store, "role": getattr(p, "designation", "") or "", "award": "Perfect attendance",
                        "why": f"{p.att.get('worked')} days worked: no absence, no short day, no punch to fix", "score": None})
    return {"stars": out, "month": getattr(mm, "month", None)}


def certificates_pdf(path: str, people: list[dict], period: str) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as cv
    from .learning.export import ASSETS, BROWN, GOLD, MUTED
    C = colors.HexColor
    PW, PH = landscape(A4)
    c = cv.Canvas(path, pagesize=(PW, PH))
    for p in people:
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
        c.drawCentredString(PW / 2, PH - 72 * mm, "CERTIFICATE OF RECOGNITION")
        c.setFillColor(C(MUTED))
        c.setFont("Helvetica", 12)
        c.drawCentredString(PW / 2, PH - 86 * mm, "Presented to")
        c.setFillColor(C(BROWN))
        c.setFont("Helvetica-Bold", 30)
        c.drawCentredString(PW / 2, PH - 102 * mm, str(p["name"])[:48])
        c.setFillColor(C(MUTED))
        c.setFont("Helvetica", 12)
        c.drawCentredString(PW / 2, PH - 114 * mm, f"{p.get('role') or ''}{' · ' if p.get('role') and p.get('store') else ''}{p.get('store') or ''}")
        c.setFillColor(C(GOLD))
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(PW / 2, PH - 132 * mm, p["award"])
        c.setFillColor(C(MUTED))
        c.setFont("Helvetica", 11)
        c.drawCentredString(PW / 2, PH - 143 * mm, str(p.get("why") or "")[:120])
        c.setFont("Helvetica", 10)
        c.drawString(30 * mm, 30 * mm, period)
        c.line(PW - 95 * mm, 34 * mm, PW - 30 * mm, 34 * mm)
        c.drawCentredString(PW - 62 * mm, 28 * mm, "Director, People & Organisation")
        c.showPage()
    c.save()
