"""6.0 The master sheet: one upload with everything the Review needs, one row per leader.

Columns (any order, any spelling close to these; extra columns are ignored):
  Sr · Employee No · Employee Name · DOJ · Grade · BU · Section · Designation · Tenure in Current Role ·
  Sales vs bud. · Productivity · Shrink · Stock days · Leavers · DA cases · NPS · Rating
  (or one rating column per year — Rating 2023 · Rating 2024 · Rating 2025: the latest year is scored, all are kept;
   "Unrated" counts as not rated yet)

Each upload is one period: year to date (Jan → month) or one month. Every value is read as it is shown:
  (15.2%) → −15.2      ▲ 3% → 3      ▼ -1% → −1      130% → 130      #N/A, —, blank, #VALUE! → not filled yet
  numbers Excel keeps as fractions (0.152 shown as 15.2%) are turned back into percentages column by column.
A rating of 0 means "not rated yet".
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from .po import canon
from .reader import Sheet
from .util import clean_text, norm

# field: (label, header patterns on the normalised title)
FIELDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "emp": ("Employee No", (r"^EMP(LOYEE)? ?(NO|NUMBER|CODE|ID|#)\b", r"^EMPLOYEE NO", r"^EMP ?ID", r"^STAFF ?(NO|ID)")),
    "name": ("Employee Name", (r"^EMP(LOYEE)? ?NAME", r"^NAME$", r"^FULL NAME")),
    "doj": ("DOJ", (r"^DOJ$", r"DATE OF JOIN", r"JOINING")),
    "grade": ("Grade", (r"^GRADE", r"PAY ?GRADE")),
    "bu": ("BU", (r"^BU$", r"BUSINESS UNIT", r"^STORE", r"^BRANCH")),
    "section": ("Section", (r"^SECTION", r"^SUB ?DEPT", r"^DEPARTMENT")),
    "designation": ("Designation", (r"^DESIGNATION", r"^POSITION", r"^ROLE$", r"^JOB TITLE")),
    "sales": ("Sales vs bud.", (r"SALES",)),
    "productivity": ("Productivity", (r"PRODUCT[A-Z]*", r"^PROD\b")),
    "shrink": ("Shrink", (r"SHRINK",)),
    "stock_days": ("Stock days", (r"STOCK ?DAYS", r"\bDOH\b", r"DAYS OF STOCK")),
    "leavers": ("Leavers", (r"LEAVER", r"TURNOVER", r"EXITS?$")),
    "da": ("DA cases", (r"^DA\b", r"DISCIPLIN")),
    "nps": ("NPS", (r"\bNPS\b",)),
    "rating": ("Rating", (r"RATING", r"APPRAISAL")),
    "role_since": ("Tenure in current role", (r"TENURE IN (THE )?(CURRENT )?ROLE", r"(IN )?(CURRENT )?ROLE SINCE", r"TIME IN (CURRENT )?ROLE",
                                              r"CURRENT ROLE")),
}
MEASURES = ["sales", "productivity", "shrink", "stock_days", "leavers", "da", "nps", "rating"]
PCT = {"sales", "productivity", "shrink", "stock_days"}
COUNTS = {"leavers", "da"}
REQUIRED = ("emp", "name", "bu", "designation")
EMPTY = re.compile(r"^\s*(#N/?A|#VALUE!?|#REF!?|#DIV/0!?|#NAME\??|N/?A|NA|NIL|-|—|–|\.|)\s*$", re.I)


def _header(sheet: Sheet) -> tuple[int, dict[str, int]] | None:
    for i, row in enumerate(sheet.rows[:30]):
        heads = [norm(c) for c in row]
        found: dict[str, int] = {}
        for f, (_, pats) in FIELDS.items():
            for j, h in enumerate(heads):
                if j in found.values() or not h:
                    continue
                if any(re.search(p, h) for p in pats):
                    found[f] = j
                    break
        if all(f in found for f in ("emp", "designation")) and sum(1 for f in MEASURES if f in found) >= 3:
            years = {int(m.group(0)): j for j, h in enumerate(heads) if re.search(r"RATING|APPRAISAL", h or "")
                     for m in [re.search(r"\b(19|20)\d{2}\b", h)] if m}
            if years:                                        # one rating column per year: score the latest, keep them all
                found["rating"] = years[max(years)]
                found["_years"] = years
            multi = next((j for j, h in enumerate(heads) if re.search(r"RATING", h or "") and re.search(r"LAST|THREE|3 ?Y|AVERAGE|AVG", h)), None)
            if multi is not None and multi != found.get("rating"):
                found["_rating_avg"] = multi
            return i, found
    return None


def score(sheet: Sheet) -> tuple[float, int]:
    hit = _header(sheet)
    return (0.99, hit[0]) if hit else (0.0, -1)


def number(v: Any) -> tuple[float | None, bool]:
    """A shown value → (number, was it written as a percentage)."""
    if v is None:
        return None, False
    if isinstance(v, bool):
        return None, False
    if isinstance(v, (int, float)):
        return float(v), False
    s = str(v).strip()
    if EMPTY.match(s):
        return None, False
    neg = False
    s = s.replace("▲", "").replace("△", "").replace("↑", "")
    if "▼" in s or "↓" in s or "▽" in s:
        s = s.replace("▼", "").replace("↓", "").replace("▽", "")
        neg = True
    s = s.strip()
    if s.startswith("(") and s.endswith(")"):
        s, neg = s[1:-1], True
    pct = "%" in s
    s = s.replace("%", "").replace(",", "").replace("−", "-").replace("pts", "").replace("pt", "").strip()
    try:
        x = float(s)
    except ValueError:
        return None, False
    if neg and x > 0:
        x = -x
    return x, pct


def _date(v: Any) -> str | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (int, float)) and 20000 < v < 80000:            # an Excel serial date
        from datetime import timedelta
        return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat()
    s = str(v).strip()
    for f in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y", "%m/%d/%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:10] if f == "%Y-%m-%d" else s, f).date().isoformat()
        except ValueError:
            continue
    return None


def _emp(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = clean_text(v)
    return "" if EMPTY.match(s) else re.sub(r"\.0$", "", s)


def parse(sheet: Sheet) -> dict:
    """Rows of the master sheet, cleaned, with every problem listed."""
    hit = _header(sheet)
    if not hit:
        return {"rows": [], "columns": {}, "warnings": ["This doesn't look like the master sheet: no Employee No / Designation / measure columns found."],
                "missing_columns": [FIELDS[f][0] for f in FIELDS]}
    hi, col = hit
    raw = []
    for row in sheet.rows[hi + 1:]:
        g = (lambda r: (lambda f: r[col[f]] if f in col and isinstance(col[f], int) and col[f] < len(r) else None))(row)
        emp, name = _emp(g("emp")), clean_text(g("name"))
        if not emp and not name:
            continue
        if re.match(r"^(grand\s*)?total", name or "", re.I):
            continue
        raw.append((emp, name, g, (lambda r: (lambda j: r[j] if j < len(r) else None))(row)))
    # percentages Excel keeps as fractions (0.152 for 15.2%): scaled per column when every value is small
    scale = {}
    for f in PCT:
        if f not in col:
            continue
        vals = [number(g(f)) for _, _, g, _ in raw]
        nums = [x for x, p in vals if x is not None]
        texty = any(p for _, p in vals)
        scale[f] = 100.0 if nums and not texty and max(abs(x) for x in nums) <= 3 else 1.0
    rows, seen, warnings = [], {}, []
    unknown_store, unknown_role = set(), set()
    for emp, name, g, g_idx in raw:
        bu_raw = clean_text(g("bu"))
        store = canon.store(bu_raw) if bu_raw else ""
        if bu_raw and not canon.store_city(store):
            unknown_store.add(bu_raw)
        sec_raw = clean_text(g("section"))
        sec = canon.section(sec_raw) if sec_raw else ""
        dept = canon.department(sec) if sec else ""
        desig = re.sub(r"\s+", " ", clean_text(g("designation")))
        level = canon.role_rank(desig)
        if desig and not level:
            unknown_role.add(desig)
        vals: dict[str, float | None] = {}
        for f in MEASURES:
            if f not in col:
                vals[f] = None
                continue
            x, _ = number(g(f))
            if x is not None and f in PCT:
                x = round(x * scale.get(f, 1.0), 2)
            if f == "rating" and x is not None and x <= 0:
                x = None                                      # 0 = not rated yet
            if f in COUNTS and x is not None:
                x = int(round(x))
            vals[f] = x
        gr = g("grade")
        years = {}
        for y, j in sorted((col.get("_years") or {}).items()):
            x, _ = number(g_idx(j))
            years[str(y)] = x if x is not None and x > 0 else None
        ravg = number(g_idx(col["_rating_avg"]))[0] if "_rating_avg" in col else None
        rs = g("role_since")
        role_since = _date(rs)
        rec = {"emp": emp, "name": canon.repair_name(name) or name, "doj": _date(g("doj")), "grade": _emp(gr) if gr is not None else "",
               "bu": bu_raw, "store": store, "format": canon.store_format(store) if store else "", "city": canon.store_city(store) if store else "",
               "section_raw": sec_raw, "section": sec, "department": dept, "designation": desig, "level": level,
               "role_since": role_since, "ratings": years, "rating_avg": ravg if ravg and ravg > 0 else None, **vals}
        key = emp or f"name:{canon.name_key(name)}"
        if key in seen:
            warnings.append(f"{name} ({emp}) appears twice; the last row is used.")
            rows[seen[key]] = rec
            continue
        seen[key] = len(rows)
        rows.append(rec)
    if unknown_store:
        warnings.append("Stores not recognised: " + ", ".join(sorted(unknown_store)[:6]) + " (Settings → Stores links them).")
    if unknown_role:
        warnings.append("Designations not recognised as a leader level: " + ", ".join(sorted(unknown_role)[:6]) + ".")
    missing_cols = [FIELDS[f][0] for f in FIELDS if f not in col and f != "role_since"]
    return {"rows": rows, "columns": {f: clean_text(sheet.rows[hi][j]) for f, j in col.items() if isinstance(j, int)}, "warnings": warnings,
            "missing_columns": missing_cols, "scaled": [FIELDS[f][0] for f, s in scale.items() if s != 1.0]}


def coverage(rows: list[dict]) -> dict:
    """How complete the sheet is: per measure, per store, per role, and who is missing what."""
    n = len(rows)
    per = {f: sum(1 for r in rows if r.get(f) is not None) for f in MEASURES}
    stores: dict[str, dict] = {}
    for r in rows:
        s = stores.setdefault(r["store"] or r["bu"] or "?", {"people": 0, "filled": 0, "cells": 0})
        s["people"] += 1
        s["cells"] += len(MEASURES)
        s["filled"] += sum(1 for f in MEASURES if r.get(f) is not None)
    roles: dict[str, dict] = {}
    for r in rows:
        k = r["designation"] or "?"
        x = roles.setdefault(k, {"people": 0, "filled": 0, "cells": 0})
        x["people"] += 1
        x["cells"] += len(MEASURES)
        x["filled"] += sum(1 for f in MEASURES if r.get(f) is not None)
    gaps = [{"emp": r["emp"], "name": r["name"], "store": r["store"], "designation": r["designation"],
             "missing": [FIELDS[f][0] for f in MEASURES if r.get(f) is None]} for r in rows]
    gaps = [g for g in gaps if g["missing"]]
    total = n * len(MEASURES)
    filled = sum(per.values())
    return {"people": n, "filled_pct": round(100 * filled / total) if total else 0,
            "measures": [{"key": f, "label": FIELDS[f][0], "filled": per[f], "of": n, "pct": round(100 * per[f] / n) if n else 0} for f in MEASURES],
            "stores": [{"name": k, **v, "pct": round(100 * v["filled"] / v["cells"]) if v["cells"] else 0} for k, v in sorted(stores.items())],
            "roles": [{"name": k, **v, "pct": round(100 * v["filled"] / v["cells"]) if v["cells"] else 0} for k, v in sorted(roles.items(), key=lambda kv: -kv[1]["people"])],
            "gaps": gaps}


# ---------------------------------------------------------------------------------------------- storage
def save(db, rows: list[dict], file_name: str, file_hash: str, ptype: str, pfrom: str, pto: str, source: str = "file", replace: bool = True) -> int:
    from .db import now
    with db.tx():
        if replace:
            for (iid,) in db.conn.execute("SELECT id FROM imports WHERE active=1 AND kind='master' AND period_type=? AND period_to=?", (ptype, pto)).fetchall():
                db.conn.execute("UPDATE imports SET active=0 WHERE id=?", (iid,))
        lab = f"{len(rows)} leaders · {len({r['store'] for r in rows})} stores"
        cur = db.conn.execute(
            "INSERT INTO imports(kind, file_name, file_hash, month, as_of, rows, summary, warnings, source, created_at, period_type, period_from, period_to) "
            "VALUES('master',?,?,?,?,?,?,?,?,?,?,?,?)",
            (file_name, file_hash, pto, None, len(rows), lab, "[]", source, now(), ptype, pfrom, pto))
        iid = cur.lastrowid
        db.conn.executemany("INSERT INTO master_rows(import_id, emp, payload) VALUES(?,?,?)",
                            [(iid, r["emp"], json.dumps(r)) for r in rows])
    db.version += 1
    return iid


def periods(db) -> list[dict]:
    out = []
    for r in db.q("""SELECT id, period_type, period_from, period_to, file_name, created_at, rows FROM imports
                     WHERE active=1 AND kind='master' ORDER BY period_to, period_type DESC, id DESC"""):
        out.append(dict(r))
    return out


def label(ptype: str, pfrom: str | None, pto: str) -> str:
    ml = lambda m: date(int(m[:4]), int(m[5:7]), 1).strftime("%b %Y")  # noqa: E731
    if ptype == "ytd":
        return f"YTD {date(int((pfrom or pto)[:4]), int((pfrom or pto)[5:7]), 1):%b}–{ml(pto)}"
    return f"{ml(pto)} (MTD)"


def chosen(db) -> dict | None:
    """The period on screen: the one picked on the Review's period bar, else the newest upload (a month beats the YTD of the same month)."""
    ps = periods(db)
    if not ps:
        return None
    v = db.get_setting("master_view", None) or {}
    hit = next((p for p in reversed(ps) if p["period_type"] == v.get("type") and p["period_to"] == v.get("to")), None)
    if hit:
        return hit
    return sorted(ps, key=lambda p: (p["period_to"], p["period_type"] == "mtd", p["id"]))[-1]


def rows_for(db, period: dict | None = None) -> list[dict]:
    p = period or chosen(db)
    if not p:
        return []
    return [json.loads(r[0]) for r in db.q("SELECT payload FROM master_rows WHERE import_id=? ORDER BY id", (p["id"],))]


# ---------------------------------------------------------------------------------------------- leaders for hiring, learning, the assistant
class Leader:
    """One leader of the master sheet, shaped like the P&O review's leaders so hiring, learning and the assistant work unchanged."""

    def __init__(self, r: dict, score: float | None, period_label: str, as_of: date):
        self.key = r["emp"] or r["name"]
        self.employee_id = r["emp"]
        self.name = r["name"]
        self.store = r["store"] or r["bu"]
        self.designation = r["designation"]
        self.sections = [r["section"]] if r["section"] and r["level"] < 5 else []
        self.section_text = r["section_raw"] or r["section"] or ""
        self.whole_store = r["level"] >= 5
        self.acting = False
        self.designation_mismatch = False
        self.system_designation = ""
        self.role_since = None
        self.months_in_role = None
        self.remarks = ""
        self.grade = r.get("grade") or ""
        self.manager_name = ""
        self.joining_date = date.fromisoformat(r["doj"]) if r.get("doj") else None
        self.months_service = ((as_of.year - self.joining_date.year) * 12 + as_of.month - self.joining_date.month) if self.joining_date else None
        rt = r.get("rating")
        self.ratings = [{"cycle": period_label, "rating": rt, "rating_label": ""}] if rt is not None else []
        self.latest_rating = rt
        self.rating_label = ""
        self.score = round(score * 10, 1) if score is not None else None          # 0-100 like the old leader index
        self.kpis = {"da": r.get("da") or 0, "leavers": r.get("leavers") or 0}
        self.components = {}
        self.shifts = {}
        self.row = r


class Insights:
    """The few things other screens ask of the P&O data, answered from the master sheet."""

    def __init__(self, api):
        from . import review
        self.api = api
        self.period = chosen(api.db)
        self.mrows = rows_for(api.db, self.period)
        self.empty = not self.mrows
        self.as_of = date.fromisoformat(self.period["period_to"] + "-%02d" % __import__("calendar").monthrange(int(self.period["period_to"][:4]), int(self.period["period_to"][5:7]))[1]) if self.period else date.today()
        self.view_label = label(self.period["period_type"], self.period["period_from"], self.period["period_to"]) if self.period else ""
        self.view = {"type": self.period["period_type"], "to": self.period["period_to"]} if self.period else {"type": "latest"}
        self._leaders = None
        self._review = review
        self._full: dict = {}
        self.coverage: list = []
        self.notes: list = []
        self.periods: dict = {}

    def leaders(self) -> list[Leader]:
        if self._leaders is None:
            rv = self._review.Review(self.api)
            out = []
            for r in self.mrows:
                row = rv.leader_row(r)
                sc = next((c["value"] for c in row["cells"] if c["key"] == "score"), None)
                out.append(Leader(r, sc, self.view_label, self.as_of))
            self._leaders = sorted(out, key=lambda l: (-(l.score if l.score is not None else -1), l.name))
        return self._leaders

    def stores(self, include_myli: bool = True) -> list[str]:
        return sorted({r["store"] for r in self.mrows if r["store"]})

    def has(self, kind: str) -> bool:
        return not self.empty

    def rows_of(self, kind: str) -> list:
        return []

    def rows(self, kind: str) -> list:                                   # noqa: D401 - old tab rows don't exist any more
        return []

    def __getattr__(self, name):
        # anything else the old screens asked for (league tables, NPS by city…) has no source now: answer empty
        return lambda *a, **k: [] if name.endswith("s") else None
