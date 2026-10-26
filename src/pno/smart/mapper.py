"""Decide what a sheet is from its columns, map every column to a field, and rewrite the sheet into the layout P&O's
readers know, so a file from any HR system, any export or any hand-made Excel is read like the original report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..reader import Sheet
from .profile import Column, Table, find_tables, to_num
from .schema import FIELDS, KINDS, field_score, header_score


@dataclass
class Match:
    kind: str
    score: float
    mapping: dict[str, int]                       # field -> column index
    scores: dict[str, float] = field(default_factory=dict)
    table: Table | None = None
    why: list[str] = field(default_factory=list)
    date_cols: list[int] = field(default_factory=list)

    def describe(self) -> list[dict]:
        cols = {c.index: c for c in self.table.columns} if self.table else {}
        out = []
        for f, j in sorted(self.mapping.items(), key=lambda kv: kv[1]):
            c = cols.get(j)
            out.append({"field": f, "label": FIELDS[f]["label"], "column": j, "header": c.header if c else "",
                        "examples": (c.examples[:3] if c else []), "score": round(self.scores.get(f, 0), 2)})
        return out


def _assign(cols: list[Column], fields: list[str], fixed: dict[str, int] | None = None) -> tuple[dict[str, int], dict[str, float]]:
    """Best column for each field, one column per field (greedy on the strongest pairs)."""
    fixed = dict(fixed or {})
    pairs = []
    used_cols = set(fixed.values())
    for c in cols:
        if c.index in used_cols or c.header_date:
            continue
        for f in fields:
            if f in fixed:
                continue
            s = field_score(c, f)
            if s >= 0.3:
                pairs.append((s, c.index, f))
    pairs.sort(key=lambda t: (-t[0], t[1]))
    mapping, scores = dict(fixed), {f: 1.0 for f in fixed}
    for s, j, f in pairs:
        if f in mapping or j in mapping.values():
            continue
        mapping[f], scores[f] = j, s
    return mapping, scores


def _kind_score(kind: str, mapping: dict[str, int], scores: dict[str, float], context: str,
                cols: list[Column] | None = None) -> tuple[float, list[str]]:
    spec = KINDS[kind]
    why = []
    total = 0.0
    for need in spec["need"]:
        opts = need if isinstance(need, tuple) else (need,)
        best = max((scores.get(o, 0) for o in opts if o in mapping), default=0)
        if best < 0.3:
            return 0.0, [f"no {FIELDS[opts[0]]['label'].lower()} column"]
        total += best
        why.append(f"{FIELDS[[o for o in opts if o in mapping][0]]['label']}")
    need_score = total / len(spec["need"])
    wants = [w for w in spec["want"] if w in mapping and scores.get(w, 0) >= 0.35]
    if len(wants) < spec.get("min_want", 0):
        return 0.0, [f"only {len(wants)} supporting columns"]
    # a column *named* like another report's field (a 'Rating' column in a leavers list) counts against this type
    never = [n for n in spec.get("never", []) if any(header_score(c.header, n) >= 0.8 and c.n for c in (cols or []))]
    s = 0.6 * need_score + 0.4 * min(1.0, len(wants) / max(1, min(4, len(spec["want"]))))
    if never:
        s -= 0.25 * len(never)
    ctx = spec.get("context")
    if ctx:
        s = s + 0.15 if re.search(ctx, context, re.I) else s - 0.3
    why += [FIELDS[w]["label"] for w in wants]
    return max(0.0, min(1.0, s)), why


def _shift_dates(t: Table) -> list[int]:
    out = []
    for c in t.columns:
        if c.header_date and c.n and c.f("shift") + (1 if not c.n else 0) >= 0.5:
            out.append(c.index)
    return out


def analyse(sheet: Sheet, file_name: str = "", fixed: dict[str, int] | None = None, kind: str | None = None) -> list[Match]:
    """Every report type this sheet could be, best first."""
    tables = find_tables(sheet.rows)
    if not tables:
        return []
    t = tables[0]
    context = f"{file_name} {sheet.name} {t.title}"
    if not kind or kind == "po_shift":
        mapping, scores = _assign(t.columns, list(FIELDS), fixed)
    else:
        mapping, scores = dict(fixed or {}), {}
    out: list[Match] = []
    for k in (KINDS if not kind else [kind]):
        if k not in KINDS:
            continue
        fields = sorted(set(f for n in KINDS[k]["need"] for f in (n if isinstance(n, tuple) else (n,))) | set(KINDS[k]["want"]) |
                        {"employee_name", "employee_id", "store", "section", "department", "designation"} |
                        (set(HEADERS.get(k, {})) if k in HEADERS else set()))
        if fixed:                                        # the user said which column is which: use exactly that
            m2, s2 = dict(fixed), {f: 1.0 for f in fixed}
        else:
            m2, s2 = _assign(t.columns, fields, fixed)   # a fresh assignment for this kind's fields only
        sc, why = _kind_score(k, m2, s2, context, t.columns)
        if k == "sales_simple" and sc > 0:
            # a store sales table has one line per store; weekly or by-department data is kept as 'Other data' with its charts
            sc_col = next((c for c in t.columns if c.index == m2.get("store")), None)
            multi_dim = any((c.f("date") > 0.8 or c.f("section") > 0.6 or c.f("month") > 0.8) and c.distinct > 1 for c in t.columns)
            if sc_col is None or sc_col.distinct < 0.9 * sc_col.n or multi_dim:
                sc = 0.0
        if kind and sc == 0:
            sc = 0.05
        if sc > 0:
            out.append(Match(kind=k, score=sc, mapping={f: j for f, j in m2.items() if f in fields}, scores=s2, table=t, why=why))
    # wide shift roster: one column per day with M / E / OFF codes
    dcols = _shift_dates(t)
    if len(dcols) >= 5 and "employee_id" in mapping and (not kind or kind == "po_shift"):
        m = {f: mapping[f] for f in ("employee_id", "employee_name", "designation", "store", "section", "department") if f in mapping}
        out.append(Match(kind="po_shift", score=0.9, mapping=m, scores=scores, table=t, why=[f"{len(dcols)} day columns with shift codes"], date_cols=dcols))
    out.sort(key=lambda m: -m.score)
    return out


# --------------------------------------------------------------------------------- rewriting into a known layout
HEADERS = {
    "roster": {"employee_id": "Employee Number", "employee_name": "Employee Name", "store": "Business Unit", "department": "Department",
               "section": "Section", "designation": "Designation", "grade": "Grade", "gender": "Gender", "manager_name": "Reporting Manager",
               "manager_id": "Reporting Manager Number", "joining_date": "Joining Date"},
    "po_role": {"employee_id": "Employee Number", "store": "Business Unit", "department": "Department", "section": "Section",
                "employee_name": "Employee Name", "designation": "Designation", "role_since": "Since when on this role", "remarks": "Remarks"},
    "po_rating": {"status": "User Status", "cycle": "Form Template Name", "employee_id": "Subject Employee ID", "employee_name": "Subject Full Name",
                  "store": "Subject Division/Entity", "designation": "Subject Position Title", "section": "Subject Department",
                  "grade": "Subject Pay Grade", "manager_name": "Manager Full Name", "rating": "Overall Performance Rating",
                  "rating_label": "Overall Performance Rating Description"},
    "po_turnover": {"employee_id": "Emp. No.", "employee_name": "Emp. Name", "exit_date": "Requested Date", "store": "Business Unit",
                    "department": "Dept.", "section": "Sect.", "exit_type": "End of Service Type", "reason": "Reason", "salary_period": "Salary Period"},
    "leave": {"employee_id": "Employee Number", "employee_name": "Employee Name", "leave_type": "Leave Type", "leave_from": "From Date",
              "leave_to": "To Date", "status": "Status"},
    "attendance": {"employee_id": "Employee Number", "employee_name": "Employee Name", "store": "Business Unit", "section": "Section",
                   "designation": "Designation", "date": "Date", "time_in": "Time In", "time_out": "Time Out", "hours": "Working Hours",
                   "status": "Status"},
    "po_shift": {"employee_id": "Employee Number", "employee_name": "Employee Name", "store": "Business Unit", "department": "Department",
                 "section": "Section", "designation": "Designation"},
}
ALWAYS = {"roster": ["Employee Number", "Employee Name", "Designation", "Reporting Manager", "Joining Date"],
          "po_role": ["Employee Number", "Since when on this role"],
          "po_rating": ["Subject Employee ID", "Form Template Name", "Overall Performance Rating"],
          "po_turnover": ["Emp. No.", "End of Service Type"],
          "leave": ["Employee Number", "From Date", "Leave Type"],
          "attendance": ["Employee Number", "Date", "Time In"],
          "po_shift": ["Employee Number", "Employee Name", "Designation"]}


def _cycle_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float)) and 2000 <= v <= 2100:
        return f"{int(v)} Performance Review"
    s = str(v)
    return s if re.search(r"20\d\d", s) else s


def rewrite(m: Match, sheet: Sheet) -> Sheet:
    """The same data under the column names P&O's report readers expect."""
    heads = HEADERS[m.kind]
    order = [(heads[f], j) for f, j in m.mapping.items() if f in heads]
    have = {h for h, _ in order}
    for h in ALWAYS.get(m.kind, []):
        if h not in have:
            order.append((h, None))
    header = [h for h, _ in order]
    date_cols = m.date_cols if m.kind == "po_shift" else []
    header += [m.table.columns[j].header_date for j in date_cols]
    # a plain punch file has no 'working hours': work them out from in and out, so the day counts as worked
    make_wh = m.kind == "attendance" and "hours" not in m.mapping and "time_in" in m.mapping and "time_out" in m.mapping
    if make_wh:
        header.append("Working Hours")
    rows: list[list[Any]] = [header]
    cyc = m.mapping.get("cycle")
    for r in m.table.body:
        out = []
        for h, j in order:
            v = r[j] if j is not None and j < len(r) else None
            if j is not None and j == cyc:
                v = _cycle_value(v)
            out.append(v)
        out += [r[j] if j < len(r) else None for j in date_cols]
        if make_wh:
            from ..util import parse_clock, span_minutes
            gi, go = m.mapping["time_in"], m.mapping["time_out"]
            mins = span_minutes(parse_clock(r[gi] if gi < len(r) else None), parse_clock(r[go] if go < len(r) else None))
            out.append(f"{mins // 60:02d}:{mins % 60:02d}" if mins else None)
        rows.append(out)
    return Sheet(name=sheet.name, rows=rows, hidden=sheet.hidden, kind=sheet.kind)


# --------------------------------------------------------------------------------- reports built straight from the mapping
def build_records(m: Match) -> list[dict]:
    """Report types whose original is a pivot or a block report (DA, simple sales): records made directly."""
    from ..po import canon
    t, mp = m.table, m.mapping
    g = lambda r, f: (r[mp[f]] if f in mp and mp[f] < len(r) else None)  # noqa: E731
    if m.kind == "po_da":
        counts: dict[tuple, float] = {}
        raw: dict[tuple, tuple] = {}
        for r in t.body:
            st_raw = g(r, "store")
            if not st_raw or re.match(r"^\s*(grand )?total", str(st_raw), re.I):
                continue
            sec_raw = str(g(r, "section") or g(r, "department") or "").strip()
            n = to_num(g(r, "count")) if "count" in mp else 1.0
            if not n:
                continue
            key = (canon.store(st_raw), canon.section(sec_raw) if sec_raw else "")
            counts[key] = counts.get(key, 0) + n
            raw[key] = (str(st_raw), sec_raw)
        return [{"store": k[0], "store_raw": raw[k][0], "section": k[1], "section_raw": raw[k][1], "count": int(v)} for k, v in counts.items()]
    if m.kind == "sales_simple":
        out = []
        for r in t.body:
            st = g(r, "store")
            a = to_num(g(r, "sales_actual"))
            if not st or a is None or re.match(r"^\s*(grand )?total", str(st), re.I):
                continue
            b = to_num(g(r, "sales_budget"))
            ly = to_num(g(r, "sales_ly"))
            out.append({"level": "store", "code": "STORE", "name": "Total Store", "dept": "", "store_raw": str(st).strip(), "actual": a,
                        "budget": b, "ly": ly, "growth": round(100 * (a / ly - 1), 1) if ly else None,
                        "var_pct": round(100 * (a / b - 1), 1) if b else None})
        return out
    return []


def today() -> date:
    return date.today()
