"""Read a CV (PDF, Word, text) and pull out the facts a retail recruiter screens on.

Everything runs on this PC. Personal details that must never influence a hiring decision (date of birth / age,
gender, marital status, religion, CNIC, father's name, photo) are recognised only so they can be hidden: they are
removed from the text that is scored, shown to the AI or printed in shortlists.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DATE = rf"(?:{_MON}[\s.,'-]*(\d{{4}}|'\d\d)|(\d{{1,2}})[/.-](\d{{4}})|(\d{{4}}))"
_RANGE = re.compile(rf"{_DATE}\s*(?:-|–|—|to|till|until)\s*(?:{_DATE}|(present|current|now|date|till date|todate|ongoing))", re.I)

RETAILERS = ["carrefour", "metro", "imtiaz", "al-fatah", "al fatah", "alfatah", "hyperstar", "naheed", "chase up", "chaseup",
             "jalal sons", "green valley", "lulu", "spar", "bin dawood", "panda", "hyper star", "makro", "esajee", "rahim store",
             "d. watson", "d watson", "springs", "gourmet", "keryana", "daraz", "foodpanda", "aldi", "tesco", "walmart",
             "safeway", "emax", "danube", "othaim", "nesto", "grand hyper", "hypermarket", "supermarket", "superstore",
             "cash & carry", "cash and carry", "department store", "retail"]
SKILLS: dict[str, list[str]] = {
    "Fresh food": ["fresh food", "fresh foods", "perishable"],
    "Butchery": ["butcher", "butchery", "meat"], "Bakery": ["bakery", "baker", "pastry"], "Deli": ["deli", "delicatessen", "dairy"],
    "Fruits & vegetables": ["fruit", "vegetable", "f&v", "produce"], "Fishery": ["fish", "seafood"],
    "FMCG / grocery": ["fmcg", "grocery", "groceries", "consumer goods"], "Non food": ["non food", "non-food", "household", "hardline"],
    "Textile / apparel": ["textile", "apparel", "garment", "fashion"], "Electronics": ["electronics", "appliance", "mobile phones"],
    "Cash / checkout": ["cashier", "checkout", "cash office", "pos", "till"],
    "Inventory & stock control": ["inventory", "stock count", "stock control", "cycle count", "stock take", "stocktake"],
    "Shrink & loss prevention": ["shrink", "shrinkage", "loss prevention", "pilferage", "wastage", "waste"],
    "Merchandising": ["merchandis", "planogram", "visual merchandising", "display"],
    "Receiving & logistics": ["receiving", "warehouse", "logistics", "supply chain", "replenishment"],
    "Customer service": ["customer service", "customer care", "complaint", "customer satisfaction", "nps"],
    "Food safety": ["haccp", "food safety", "hygiene", "iso 22000"],
    "Team leadership": ["team lead", "supervis", "managed a team", "team of", "staff of", "people management", "leadership"],
    "Rostering & scheduling": ["roster", "rota", "shift planning", "scheduling"],
    "Sales & KPIs": ["sales target", "kpi", "budget", "p&l", "profit", "margin", "productivity"],
    "Excel / MIS": ["excel", "mis", "reporting", "power bi", "dashboard"], "SAP / ERP": ["sap", "oracle", "erp", "ms dynamics", "odoo"],
}
LEVELS = [  # (rank, label, words)
    (6, "Store manager", ["store manager", "general manager", "branch manager", "outlet manager", "hypermarket manager"]),
    (5, "Deputy / assistant store manager", ["deputy store manager", "deputy manager", "assistant store manager", "asst. store manager", "store in-charge", "store incharge"]),
    (4, "Department head", ["department head", "department manager", "dept head", "head of department", "category manager"]),
    (3, "Section manager", ["section manager", "section head", "floor manager", "manager"]),
    (2, "Team leader / supervisor", ["team leader", "team lead", "supervisor", "shift leader", "shift incharge", "senior associate", "incharge", "in-charge"]),
    (1, "Associate", ["associate", "sales person", "salesman", "sales officer", "cashier", "stocker", "helper", "assistant", "executive", "officer", "clerk"]),
]
EDUCATION = [(5, "Master's", r"\b(m\.?b\.?a\b|masters?\b|m\.?com\b|m\.?sc\b|m\.a\.?\b|m\.s\.?\b|ms\s*\(|ms in\b|mphil)"), (4, "Bachelor's", r"\b(bachelor|b\.?com|bba|b\.?sc|b\.?s\b|b\.?a\b|bs\(|bs\s|b\.?e\b|graduat)"),
             (3, "Intermediate", r"\b(intermediate|f\.?a\b|f\.?sc|i\.?com|hssc|a.?levels?|dae)"), (2, "Matric", r"\b(matric|ssc|o.?levels?)")]
CITIES = ["Lahore", "Karachi", "Islamabad", "Rawalpindi", "Faisalabad", "Gujranwala", "Multan", "Sialkot", "Peshawar", "Hyderabad",
          "Quetta", "Sargodha", "Bahawalpur", "Sheikhupura", "Kasur", "Okara", "Sahiwal", "Gujrat", "Wah", "Abbottabad"]
SENSITIVE = re.compile(r"^\s*(date\s*of\s*birth|d\.?o\.?b|birth\s*date|age|gender|sex|marital\s*status|religion|sect|caste|cnic|n\.?i\.?c|"
                       r"national\s*id|father'?s?\s*name|f/name|s/o|d/o|w/o|husband'?s?\s*name|domicile|blood\s*group|nationality|height|weight)\b.*$",
                       re.I | re.M)


def read_text(path: str | Path) -> str:
    """Plain text of a CV file. Scanned images give little text: the caller says so."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(p))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:12])
    if ext in (".docx", ".docm"):
        import docx
        d = docx.Document(str(p))
        parts = [para.text for para in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    if ext in (".txt", ".md", ".csv", ".rtf", ".text", ".htm", ".html"):
        raw = p.read_bytes()
        for enc in ("utf-8", "utf-16", "cp1252"):
            try:
                txt = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            txt = raw.decode("utf-8", "replace")
        if ext in (".htm", ".html"):
            txt = re.sub(r"<[^>]+>", " ", txt)
        if ext == ".rtf":
            txt = re.sub(r"\\[a-z]+-?\d* ?|[{}]", " ", txt)
        return txt
    if ext == ".doc":
        raw = p.read_bytes()
        return re.sub(r"[^\x20-\x7E\n]+", " ", raw.decode("latin-1"))
    raise ValueError(f"{p.name}: CVs can be PDF, Word (.docx) or text files.")


def file_hash(path: str | Path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def redact(text: str) -> str:
    """The CV without the personal details that must not influence screening."""
    t = SENSITIVE.sub("[personal detail hidden]", text)
    t = re.sub(r"\b\d{5}-?\d{7}-?\d\b", "[ID hidden]", t)                       # CNIC numbers anywhere
    t = re.sub(r"\b(single|married|divorced|widow(?:ed)?|unmarried)\b", "[hidden]", t, flags=re.I)
    t = re.sub(r"\b(\d{1,2})\s*(?:years?|yrs?)\s*old\b", "[hidden]", t, flags=re.I)
    return t


def _year(s: str | None) -> int | None:
    if not s:
        return None
    s = s.strip("'")
    y = int(s)
    return 2000 + y if y < 100 else y


def _point(groups: tuple) -> date | None:
    mon, y1, num_m, y2, y3 = groups
    try:
        if mon and y1:
            return date(_year(y1), MONTHS[mon[:3].lower()], 1)
        if num_m and y2 and 1 <= int(num_m) <= 12:
            return date(int(y2), int(num_m), 1)
        if y3:
            return date(int(y3), 1, 1)
    except (ValueError, KeyError):
        return None
    return None


def _months(a: date, b: date) -> int:
    return max(0, (b.year - a.year) * 12 + b.month - a.month)


def jobs(text: str, today: date | None = None) -> list[dict[str, Any]]:
    """Employment periods with the lines around them (title and employer are usually on the same or next lines)."""
    today = today or date.today()
    lines = [l.strip() for l in text.splitlines()]
    out = []
    for i, line in enumerate(lines):
        for m in _RANGE.finditer(line):
            g = m.groups()
            start = _point(g[0:5])
            end = date(today.year, today.month, 1) if g[10] else _point(g[5:10])
            if not start or not end or end < start or start.year < 1975 or start > today:
                continue
            context = " ".join(x for x in lines[max(0, i - 2):i + 3] if x)[:300]
            low = context.lower()
            level = 0
            for near in (line, lines[i + 1] if i + 1 < len(lines) else "", lines[i - 1] if i else ""):
                nl = near.lower()
                level = next((rank for rank, _, words in LEVELS if any(re.search(rf"\b{re.escape(w)}\b", nl) for w in words)), 0)
                if level:
                    break
            title = next((label for rank, label, words in LEVELS if rank == level), "") if level else ""
            own = (line + " " + (lines[i + 1] if i + 1 < len(lines) else "")).lower()
            out.append({"start": start.isoformat()[:7], "end": end.isoformat()[:7], "months": _months(start, end) or 1,
                        "current": bool(g[10]), "context": context, "level": level, "title": title,
                        "retail": any(r in own for r in RETAILERS) or any(r in low for r in RETAILERS[:34])})
    # keep distinct periods (the same range is often printed twice)
    seen, uniq = set(), []
    for j in sorted(out, key=lambda j: j["start"], reverse=True):
        k = (j["start"], j["end"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(j)
    return uniq


def _span_months(periods: list[tuple[str, str]]) -> int:
    """Months covered by possibly overlapping periods (YYYY-MM start inclusive, end exclusive; one month at least)."""
    covered: set[int] = set()
    for a, b in periods:
        s = int(a[:4]) * 12 + int(a[5:7])
        e = int(b[:4]) * 12 + int(b[5:7])
        covered.update(range(s, max(e, s + 1)))
    return len(covered)


def parse(text: str, file_name: str = "") -> dict[str, Any]:
    clean = text.replace("\r", "")
    low = clean.lower()
    lines = [l.strip() for l in clean.splitlines() if l.strip()]
    email = (re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", clean) or [None])[0]
    phone_m = re.search(r"(?:\+?92[\s-]?|0)3\d{2}[\s-]?\d{7}|\+?92[\s-]?\d{2,3}[\s-]?\d{6,8}|\b0\d{2,3}[\s-]?\d{6,8}\b", clean)
    phone = re.sub(r"[\s-]", "", phone_m.group(0)) if phone_m else None
    name = _guess_name(lines, email, file_name)
    js = jobs(clean)
    total = round(_span_months([(j["start"], j["end"]) for j in js]) / 12, 1) if js else None
    retail = round(_span_months([(j["start"], j["end"]) for j in js if j["retail"]]) / 12, 1) if js else None
    if total is None:                                  # "8 years of experience" written in words
        m = re.search(r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp)", low)
        total = float(m.group(1)) if m else None
    skills = {k: [w for w in words if w in low] for k, words in SKILLS.items()}
    skills = {k: v for k, v in skills.items() if v}
    top_level = max([j["level"] for j in js] + [next((r for r, _, w in LEVELS if any(x in low for x in w)), 0)])
    edu = next(((rank, label) for rank, label, rx in EDUCATION if re.search(rx, low)), (0, ""))
    city = next((c for c in CITIES if re.search(rf"\b{c.lower()}\b", low)), "")
    team = [int(n) for pair in re.findall(r"team of (\d{1,3})|(?:managed|supervised|led|leading) (?:a team of )?(\d{1,3}) "
                                          r"(?:staff|people|employees|members|associates)", low) for n in pair if n]
    retailers = sorted({r.title() for r in RETAILERS[:34] if r in low})
    langs = [l for l in ("English", "Urdu", "Punjabi", "Pashto", "Sindhi", "Arabic") if l.lower() in low]
    return {"name": name, "email": email, "phone": phone, "city": city, "jobs": js, "years_total": total,
            "years_retail": retail, "top_level": top_level, "top_level_label": next((l for r, l, _ in LEVELS if r == top_level), ""),
            "education_rank": edu[0], "education": edu[1], "skills": skills, "team_size": max(team) if team else None,
            "retailers": retailers, "languages": langs, "flags": flags(js), "words": len(low.split()),
            "sensitive_hidden": len(SENSITIVE.findall(clean))}


def _guess_name(lines: list[str], email: str | None, file_name: str) -> str:
    skip = re.compile(r"curriculum|vitae|resume|résumé|cv\b|profile|objective|contact|address|phone|mobile|email|@|\d{4}", re.I)
    for l in lines[:8]:
        t = re.sub(r"^(name|mr\.?|ms\.?|mrs\.?|miss)\s*[:\-]?\s*", "", l, flags=re.I).strip(" :-|")
        if 2 <= len(t.split()) <= 5 and not skip.search(t) and re.fullmatch(r"[A-Za-z .'-]+", t):
            return t.title()
    stem = re.sub(r"[_\-.]+|cv|resume|\d+", " ", Path(file_name).stem, flags=re.I).strip()
    if stem and re.fullmatch(r"[A-Za-z ]+", stem):
        return stem.title()
    if email:
        return re.sub(r"[._\d]+", " ", email.split("@")[0]).strip().title()
    return "Unnamed candidate"


def flags(js: list[dict]) -> list[str]:
    """Things to ask about in interview (not reasons to reject on their own)."""
    out = []
    ordered = sorted(js, key=lambda j: j["start"])
    for a, b in zip(ordered, ordered[1:]):
        ay, am = int(a["end"][:4]), int(a["end"][5:7])
        by, bm = int(b["start"][:4]), int(b["start"][5:7])
        gap = (by - ay) * 12 + bm - am
        if gap > 6:
            out.append(f"Gap of {gap} months between {a['end']} and {b['start']}")
    short = [j for j in js if j["months"] < 12 and not j["current"]]
    if len(short) >= 3:
        out.append(f"{len(short)} jobs shorter than a year")
    cur = [j for j in js if j["current"]]
    if len(cur) > 1:
        out.append(f"{len(cur)} jobs marked as current at the same time")
    return out
