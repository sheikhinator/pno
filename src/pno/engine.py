"""The month model: everyone's role, attendance, KPIs and score for one month, built from the active imports.

Built once per month and cached until the data changes, so every screen, export and agent answer uses the same numbers.
"""

from __future__ import annotations

import copy
import math
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .db import Database
from .org import DEPT_NAMES, ROLE_LABEL, clean_manager, map_section, role_of
from .util import month_bounds, norm, prev_month

# ------------------------------------------------------------------------------------------------ settings
DEFAULT_WEIGHTS = {
    "SM":    {"sales": 25, "prod": 20, "oos": 15, "waste": 15, "team": 15, "own": 10},
    "DH":    {"sales": 25, "prod": 20, "oos": 15, "waste": 15, "team": 15, "own": 10},
    "GM":    {"sales": 25, "prod": 20, "oos": 15, "waste": 15, "team": 20, "own": 5},
    "HBM":   {"sales": 35, "oos": 20, "team": 25, "own": 20},
    "CCO":   {"prod": 40, "team": 40, "own": 20},
    "AREA":  {"sales": 30, "prod": 20, "oos": 10, "waste": 10, "team": 20, "own": 10},
    "STAFF": {"own": 70, "section": 30},
}
DEFAULT_RULES = {
    "budget": [80, 100, 115],          # % of budget scoring 0 / 7 / 10
    "productivity": [80, 100, 115],    # % of target scoring 0 / 7 / 10
    "presence": [85, 95, 100],         # % of due days worked scoring 0 / 7 / 10
    "compliance": [60, 80, 100],       # % of worked days with full hours scoring 0 / 5 / 10
    "full_day_minutes": 540,           # the 9-hour golden rule
    "grace_minutes": 0,
    "presence_weight": 70,             # attendance score = 70% presence + 30% hours compliance
    "provisional_days": 7,
    "new_joiner_days": 30,
    "min_coverage": 60,
    "min_peers": 3,
    "outlier_pct": 50,                 # sales more than ±50% from budget are flagged
    "long_absence_days": 7,
}
COMPONENT_LABEL = {"sales": "Sales vs budget", "prod": "Productivity vs target", "oos": "Out of stock",
                   "waste": "Waste", "team": "Team attendance", "own": "Own attendance", "section": "Section result"}
BANDS = [(9.0, "Outstanding", "excellent"), (7.5, "Strong", "good"), (6.0, "Meets expectation", "ok"),
         (4.0, "Needs improvement", "warn"), (0.0, "Concern", "bad")]
WORKED = {"present", "manual", "missing_in", "missing_out", "punched_absent"}
FIXES = {"missing_in", "missing_out", "punched_absent"}


def band(score: float | None) -> tuple[str, str]:
    if score is None:
        return "No score", "none"
    for lim, label, key in BANDS:
        if score >= lim:
            return label, key
    return "Concern", "bad"


def curve3(x: float, lo: float, mid: float, hi: float, mid_score: float = 7.0) -> float:
    """0 at lo, mid_score at mid, 10 at hi; straight lines between, capped."""
    if x <= lo:
        return 0.0
    if x >= hi:
        return 10.0
    if x <= mid:
        return mid_score * (x - lo) / (mid - lo)
    return mid_score + (10 - mid_score) * (x - mid) / (hi - mid)


# ------------------------------------------------------------------------------------------------ data classes
@dataclass
class Person:
    emp: str
    name: str
    store_id: int | None
    store: str = ""
    store_format: str = ""
    city: str = ""
    dept_code: str = ""
    dept: str = ""
    section: str = ""
    designation: str = ""
    grade: str = ""
    gender: str = ""
    manager_name: str = ""
    manager_emp: str | None = None
    manager_status: str = ""          # linked | uncertain | outside | none
    joining: str | None = None
    role: str = "STAFF"
    domain: dict = field(default_factory=dict)
    reports: list[str] = field(default_factory=list)
    in_roster: bool = True
    att: dict | None = None
    kpis: dict = field(default_factory=dict)
    score: float | None = None
    coverage: float = 0.0
    status: str = ""                  # scored | not_enough_data | new_joiner
    provisional: bool = False
    components: list[dict] = field(default_factory=list)
    context: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def brief(self) -> dict:
        b, bk = band(self.score)
        return {"emp": self.emp, "name": self.name, "store": self.store, "store_id": self.store_id, "format": self.store_format,
                "city": self.city, "dept": self.dept, "dept_code": self.dept_code, "section": self.section,
                "designation": self.designation, "grade": self.grade, "role": self.role, "role_label": ROLE_LABEL[self.role],
                "score": None if self.score is None else round(self.score, 1), "band": b, "band_key": bk,
                "status": self.status, "provisional": self.provisional, "coverage": round(self.coverage * 100),
                "attendance": None if not self.att else self.att.get("score"),
                "presence": None if not self.att else self.att.get("presence"),
                "absent": None if not self.att else self.att.get("absent"),
                "fixes": None if not self.att else self.att.get("fixes"), "flags": self.flags}


@dataclass
class MonthModel:
    month: str
    as_of: str | None
    data_days: int
    complete: bool
    people: dict[str, Person]
    stores: dict[int, dict]
    sales_asof: dict[int, str]
    holidays: dict[str, str]
    roster_as_of: str | None
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------------------------------------------------ cache
_CACHE: dict[tuple, MonthModel] = {}
_LOCK = threading.Lock()


def settings(db: Database) -> tuple[dict, dict]:
    w = copy.deepcopy(DEFAULT_WEIGHTS)
    for k, v in (db.get_setting("weights", {}) or {}).items():
        if k in w and isinstance(v, dict):
            w[k] = {kk: float(vv) for kk, vv in v.items() if float(vv) > 0}
    r = copy.deepcopy(DEFAULT_RULES)
    r.update(db.get_setting("rules", {}) or {})
    return w, r


def months_available(db: Database) -> list[str]:
    rows = db.q("""SELECT DISTINCT substr(day,1,7) m FROM attendance
                   UNION SELECT DISTINCT s.month FROM sales s JOIN imports i ON i.id=s.import_id AND i.active=1
                   UNION SELECT DISTINCT p.month FROM productivity p JOIN imports i ON i.id=p.import_id AND i.active=1
                   ORDER BY 1""")
    return [r[0] for r in rows if r[0]]


def model(db: Database, month: str | None = None) -> MonthModel:
    months = months_available(db)
    if month is None:
        month = months[-1] if months else date.today().strftime("%Y-%m")
    key = (str(db.path), month, db.version)
    with _LOCK:
        m = _CACHE.get(key)
        if m is None:
            for k in [k for k in _CACHE if k[0] == key[0] and k[2] != key[2]]:
                _CACHE.pop(k, None)
            m = _CACHE[key] = _build(db, month)
        return m


# ------------------------------------------------------------------------------------------------ build
def _build(db: Database, month: str) -> MonthModel:
    weights, rules = settings(db)
    m_start, m_end = month_bounds(month)
    stores = {r["id"]: dict(r) for r in db.q("SELECT * FROM stores")}
    warnings: list[str] = []

    # roster snapshot: the latest one dated within or before the month, else the earliest after it
    rid = db.val("SELECT id FROM imports WHERE kind='roster' AND active=1 AND as_of<=? ORDER BY as_of DESC, id DESC LIMIT 1",
                 (m_end.isoformat(),))
    if rid is None:
        rid = db.val("SELECT id FROM imports WHERE kind='roster' AND active=1 ORDER BY as_of ASC, id DESC LIMIT 1")
    roster_as_of = db.val("SELECT as_of FROM imports WHERE id=?", (rid,)) if rid else None
    people: dict[str, Person] = {}
    sec_over = db.get_setting("section_map", {}) or {}
    for r in db.q("SELECT * FROM roster WHERE import_id=?", (rid,)) if rid else []:
        mname, mno = clean_manager(r["manager_name"] or "")
        st = stores.get(r["store_id"], {})
        people[r["emp_no"]] = Person(
            emp=r["emp_no"], name=r["name"], store_id=r["store_id"], store=st.get("name", r["bu_raw"] or ""),
            store_format=st.get("format", ""), city=st.get("city", ""), dept_code=r["dept_code"] or "",
            dept=DEPT_NAMES.get(r["dept_code"] or "", r["dept_name"] or ""), section=r["section_raw"] or "",
            designation=r["designation"] or "", grade=r["grade"] or "", gender=r["gender"] or "", manager_name=mname,
            manager_emp=mno or None)

    # attendance people (fills joining dates; adds people the roster does not have)
    att_import = {}
    for r in db.q("""SELECT ap.* FROM att_people ap JOIN imports i ON i.id=ap.import_id AND i.active=1
                     WHERE ap.month=? ORDER BY ap.import_id""", (month,)):
        att_import[r["emp_no"]] = r
    for emp, r in att_import.items():
        p = people.get(emp)
        if p is None:
            st = stores.get(r["store_id"], {})
            p = people[emp] = Person(emp=emp, name=r["name"] or emp, store_id=r["store_id"], store=st.get("name", ""),
                                     store_format=st.get("format", ""), city=st.get("city", ""), section=r["section_raw"] or "",
                                     designation=r["designation"] or "", in_roster=False)
            if r["section_raw"]:
                pre = r["section_raw"].split(" ")[0].upper()
                from .org import PREFIX_DEPT
                p.dept_code = PREFIX_DEPT.get(pre, "")
                p.dept = DEPT_NAMES.get(p.dept_code, "")
        if r["joining_date"]:
            p.joining = r["joining_date"]
    if not rid and people:
        warnings.append("No employee roster is imported, so reporting lines and departments are limited.")

    _link_managers(people, db.get_setting("manager_overrides", {}) or {})
    for p in people.values():
        p.role = role_of(p.designation, p.store_format, p.dept_code, p.section, bool(p.reports))
        if p.role == "GM" and len({people[e].store_id for e in p.reports if e in people}) >= 2:
            p.role = "AREA"
    _domains(people, sec_over)

    # ---------------------------------------------------------------- attendance
    holidays = {r["day"]: r["name"] for r in db.q(
        "SELECT h.day, h.name FROM holidays h LEFT JOIN imports i ON i.id=h.import_id WHERE (h.import_id IS NULL OR i.active=1) "
        "AND h.day BETWEEN ? AND ?", (m_start.isoformat(), m_end.isoformat()))}
    leaves: dict[str, dict[str, str]] = defaultdict(dict)
    for r in db.q("""SELECT l.* FROM leaves l LEFT JOIN imports i ON i.id=l.import_id
                     WHERE (l.import_id IS NULL OR i.active=1) AND l.d_to>=? AND l.d_from<=?""",
                  (m_start.isoformat(), m_end.isoformat())):
        d = max(date.fromisoformat(r["d_from"]), m_start)
        while d <= min(date.fromisoformat(r["d_to"]), m_end):
            leaves[r["emp_no"]][d.isoformat()] = r["type"]
            d += timedelta(days=1)
    days_by_emp: dict[str, dict[str, Any]] = defaultdict(dict)
    for r in db.q("SELECT emp_no, day, status, minutes, t_in, t_out FROM attendance WHERE day BETWEEN ? AND ?",
                  (m_start.isoformat(), m_end.isoformat())):
        days_by_emp[r["emp_no"]][r["day"]] = r
    att_as_of = db.val("SELECT MAX(as_of) FROM imports WHERE kind='attendance' AND active=1 AND month=?", (month,))
    for emp, p in people.items():
        if emp in days_by_emp:
            p.att = attendance_summary(days_by_emp[emp], m_start, date.fromisoformat(att_as_of) if att_as_of else m_end,
                                       p.joining, holidays, leaves.get(emp, {}), bool(stores.get(p.store_id, {}).get("is_ho")),
                                       rules, att_import.get(emp))

    # ---------------------------------------------------------------- sales and productivity
    sales_asof: dict[int, str] = {}
    sales: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in db.q("""SELECT s.* FROM sales s JOIN imports i ON i.id=s.import_id AND i.active=1
                     WHERE s.month=? AND s.period='MTD' ORDER BY s.as_of, s.import_id""", (month,)):
        sid = r["store_id"]
        if sales_asof.get(sid, "") < r["as_of"]:
            sales_asof[sid] = r["as_of"]
            sales[sid] = {}
        if r["as_of"] == sales_asof[sid]:
            sales[sid][r["code"]] = dict(r)
    prod: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in db.q("""SELECT p.* FROM productivity p JOIN imports i ON i.id=p.import_id AND i.active=1
                     WHERE p.month=? ORDER BY p.import_id""", (month,)):
        prod[r["store_id"]][r["row_code"]] = dict(r)

    as_of_dates = [d for d in [att_as_of, *sales_asof.values()] if d]
    as_of = max(as_of_dates) if as_of_dates else None
    data_days = (date.fromisoformat(as_of) - m_start).days + 1 if as_of else 0
    complete = bool(as_of) and as_of >= m_end.isoformat()

    ctx = _Ctx(people, stores, sales, prod, rules, weights, data_days, m_end)
    for p in people.values():
        _score(ctx, p)
    mm = MonthModel(month=month, as_of=as_of, data_days=data_days, complete=complete, people=people, stores=stores,
                    sales_asof=sales_asof, holidays=holidays, roster_as_of=roster_as_of, warnings=warnings)
    mm.sales = sales            # type: ignore[attr-defined]
    mm.prod = prod              # type: ignore[attr-defined]
    return mm


def _link_managers(people: dict[str, Person], overrides: dict) -> None:
    by_name: dict[str, list[Person]] = defaultdict(list)
    for p in people.values():
        by_name[norm(p.name)].append(p)
    for p in people.values():
        if p.emp in overrides:
            p.manager_emp, p.manager_status = overrides[p.emp] or None, "linked" if overrides[p.emp] else "outside"
        elif p.manager_emp and p.manager_emp in people:
            p.manager_status = "linked"
        elif p.manager_name:
            cands = [c for c in by_name.get(norm(p.manager_name), []) if c.emp != p.emp]
            same = [c for c in cands if c.store_id == p.store_id]
            pick = same or cands
            if len(pick) == 1:
                p.manager_emp, p.manager_status = pick[0].emp, "linked"
            elif len(pick) > 1:
                # several people share the name: take the most senior one, but mark it for HR to confirm
                best = max(pick, key=lambda c: (c.grade or "00"))
                p.manager_emp, p.manager_status = best.emp, "uncertain"
            else:
                p.manager_emp, p.manager_status = None, "outside"
        else:
            p.manager_status = "none"
        if p.manager_emp and p.manager_emp in people:
            people[p.manager_emp].reports.append(p.emp)


def _domains(people: dict[str, Person], sec_over: dict) -> None:
    for p in people.values():
        own = map_section(p.section, p.dept_code, sec_over)
        if p.role in ("GM", "HBM"):
            p.domain = {"level": "store"}
        elif p.role == "AREA":
            p.domain = {"level": "area", "stores": sorted({people[e].store_id for e in p.reports if e in people})}
        elif p.role == "DH":
            p.domain = {"level": "dept", "dept": p.dept_code or own.get("dept", "")}
        elif p.role == "CCO":
            p.domain = {"level": "cco"}
        elif p.role == "SM":
            codes: set[str] = set(own.get("codes", []))
            depts: set[str] = {own["dept"]} if own.get("dept") else set()
            for e in p.reports:
                if e in people:
                    t = map_section(people[e].section, people[e].dept_code, sec_over)
                    codes.update(t.get("codes", []))
                    if t.get("dept"):
                        depts.add(t["dept"])
            if codes:
                p.domain = {"level": "sections", "codes": sorted(codes)}
            elif depts:
                p.domain = {"level": "dept", "dept": sorted(depts)[0]}
            elif own.get("store"):
                p.domain = {"level": "store"}
            else:
                p.role, p.domain = "STAFF", {}
        if p.role == "STAFF":
            if own.get("codes"):
                p.domain = {"level": "sections", "codes": own["codes"]}
            elif own.get("dept"):
                p.domain = {"level": "dept", "dept": own["dept"]}
            elif own.get("cco"):
                p.domain = {"level": "cco"}
            elif own.get("store") and p.store_format == "HB":
                p.domain = {"level": "store"}
            else:
                p.domain = {"level": "none", "service": bool(own.get("service"))}


# ------------------------------------------------------------------------------------------------ attendance
def attendance_summary(days: dict[str, Any], m_start: date, as_of: date, joining: str | None, holidays: dict, leave: dict,
                       is_ho: bool, rules: dict, att_row=None) -> dict:
    start = m_start
    if joining:
        try:
            start = max(start, date.fromisoformat(joining))
        except ValueError:
            pass
    end = as_of
    full = rules["full_day_minutes"] - rules["grace_minutes"]
    cal: list[dict] = []
    d = start
    while d <= end:
        iso = d.isoformat()
        r = days.get(iso)
        st = r["status"] if r else "no_punch"
        mins = r["minutes"] if r else None
        kind = "worked" if st in WORKED else ("leave" if st == "sys_leave" else "off" if st == "sys_off"
                                              else "holiday" if st == "sys_holiday" else "none")
        if kind == "none" and iso in holidays:
            kind = "holiday"
        if kind == "none" and iso in leave:
            kind = "leave"
        if kind == "none" and is_ho and d.weekday() >= 5:
            kind = "off"
        cal.append({"day": iso, "status": st, "kind": kind, "minutes": mins, "t_in": r["t_in"] if r else None,
                    "t_out": r["t_out"] if r else None, "leave": leave.get(iso), "holiday": holidays.get(iso)})
        d += timedelta(days=1)
    # weekly off for store staff: one day in every Monday–Sunday week (a Tuesday-off person really has 5 offs in a
    # month with 5 Tuesdays). The partial weeks at the start and end of the month also get one.
    if not is_ho and cal:
        weeks: dict[tuple, list[dict]] = defaultdict(list)
        for c in cal:
            weeks[date.fromisoformat(c["day"]).isocalendar()[:2]].append(c)
        for wk in sorted(weeks):
            if any(c["kind"] == "off" for c in weeks[wk]):
                continue
            cand = next((c for c in weeks[wk] if c["kind"] == "none"), None)
            if cand:
                cand["kind"] = "off"
    for c in cal:
        if c["kind"] == "none":
            c["kind"] = "absent"
    worked = [c for c in cal if c["kind"] == "worked"]
    absent = [c for c in cal if c["kind"] == "absent"]
    timed = [c for c in worked if c["minutes"]]
    full_days = sum(1 for c in timed if c["minutes"] >= full)
    run = best = 0
    for c in cal:
        if c["kind"] == "absent":
            run += 1
            best = max(best, run)
        elif c["kind"] != "off":
            run = 0
    due = len(worked) + len(absent)
    presence = len(worked) / due * 100 if due else None
    compliance = full_days / len(timed) * 100 if timed else None
    pres_s = curve3(presence, *rules["presence"]) if presence is not None else None
    lo, mid, hi = rules["compliance"]
    comp_s = curve3(compliance, lo, mid, hi, 5.0) if compliance is not None else None
    pw = rules["presence_weight"] / 100
    if pres_s is None:
        score = None
    elif comp_s is None:
        score = pres_s
    else:
        score = pw * pres_s + (1 - pw) * comp_s
    total_min = sum(c["minutes"] for c in timed)
    return {
        "calendar": cal, "days": len(cal), "worked": len(worked), "absent": len(absent),
        "leave": sum(1 for c in cal if c["kind"] == "leave"), "holiday": sum(1 for c in cal if c["kind"] == "holiday"),
        "off": sum(1 for c in cal if c["kind"] == "off"), "due": due,
        "fixes": sum(1 for c in worked if c["status"] in FIXES), "manual": sum(1 for c in worked if c["status"] == "manual"),
        "missing_in": sum(1 for c in worked if c["status"] == "missing_in"),
        "missing_out": sum(1 for c in worked if c["status"] == "missing_out"),
        "punched_absent": sum(1 for c in worked if c["status"] == "punched_absent"),
        "presence": None if presence is None else round(presence, 1),
        "compliance": None if compliance is None else round(compliance, 1),
        "full_days": full_days, "short_days": len(timed) - full_days, "minutes": total_min,
        "avg_minutes": round(total_min / len(timed)) if timed else None,
        "overtime_minutes": sum(max(0, c["minutes"] - rules["full_day_minutes"]) for c in timed),
        "night_days": sum(1 for c in timed if c["t_in"] and c["t_out"] and c["t_out"] < c["t_in"]),
        "longest_absence": best,
        "sys_absent": att_row["sys_absent"] if att_row else None, "sys_present": att_row["sys_present"] if att_row else None,
        "presence_score": None if pres_s is None else round(pres_s, 2),
        "compliance_score": None if comp_s is None else round(comp_s, 2),
        "score": None if score is None else round(score, 2),
    }


# ------------------------------------------------------------------------------------------------ KPIs and score
class _Ctx:
    def __init__(self, people, stores, sales, prod, rules, weights, data_days, m_end):
        self.people, self.stores, self.sales, self.prod = people, stores, sales, prod
        self.rules, self.weights, self.data_days, self.m_end = rules, weights, data_days, m_end
        self._peer_cache: dict = {}

    def sales_rows(self, store_id, domain) -> list[dict]:
        rows = self.sales.get(store_id, {})
        lvl = domain.get("level")
        if lvl == "store":
            return [rows["STORE"]] if "STORE" in rows else []
        if lvl == "dept":
            d = domain.get("dept", "")
            return [rows[f"D{d}"]] if f"D{d}" in rows else []
        if lvl == "sections":
            return [rows[c] for c in domain.get("codes", []) if c in rows]
        return []

    def peer_values(self, unit: tuple, metric: str, fmt: str | None) -> list[float]:
        """The same unit (store total / a department / a section) in every store that has it."""
        key = (unit, metric, fmt)
        if key not in self._peer_cache:
            vals = []
            for sid, rows in self.sales.items():
                if fmt and self.stores.get(sid, {}).get("format") != fmt:
                    continue
                r = rows.get(unit[1])
                if r and r.get(metric) is not None and (r.get("actual") or 0) > 0:
                    vals.append(r[metric])
            self._peer_cache[key] = vals
        return self._peer_cache[key]


def _rank_score(value: float, peers: list[float], lower_better: bool, min_peers: int) -> float | None:
    if len(peers) < min_peers or max(peers) - min(peers) < 1e-9:
        return None
    worse = sum(1 for v in peers if (v > value if lower_better else v < value))
    ties = sum(1 for v in peers if abs(v - value) < 1e-9) - 1
    return 10.0 * (worse + 0.5 * max(0, ties)) / (len(peers) - 1)


def _business(ctx: _Ctx, p: Person, store_ids: list[int]) -> dict[str, dict]:
    """Sales vs budget, productivity vs target, OOS and waste for the person's area."""
    r = ctx.rules
    out: dict[str, dict] = {}
    rows = [row for sid in store_ids for row in ctx.sales_rows(sid, p.domain if p.domain.get("level") != "area" else {"level": "store"})]
    budget_rows = [x for x in rows if (x.get("budget") or 0) > 0 and x.get("actual") is not None]
    if budget_rows:
        a = sum(x["actual"] for x in budget_rows)
        b = sum(x["budget"] for x in budget_rows)
        pct = a / b * 100
        flag = abs(pct - 100) > r["outlier_pct"]
        out["sales"] = {"value": pct, "display": f"{pct:.0f}% of budget", "score": curve3(pct, *r["budget"]),
                        "detail": f"{a:,.0f} sold vs {b:,.0f} budget", "flag": "Extreme variance: check for bulk or B2B sales" if flag else None}
    # context (not scored): growth vs last year and margin
    ly = sum(x["ly"] for x in rows if x.get("ly"))
    act = sum(x["actual"] for x in rows if x.get("ly"))
    if ly:
        g = (act / ly - 1) * 100
        out["_growth"] = {"value": g, "display": f"{g:+.1f}% vs last year"}
    tot = sum(x["actual"] or 0 for x in rows)
    if tot:
        mg = [x for x in rows if x.get("margin_net") is not None]
        if mg:
            m = sum(x["margin_net"] * (x["actual"] or 0) for x in mg) / tot
            out["_margin"] = {"value": m, "display": f"{m:.1f}% margin after waste"}
        out["_sales"] = {"value": tot, "display": f"Sales {tot:,.0f}"}
    # peers for OOS and waste
    for metric, key in (("oos", "oos"), ("waste", "waste")):
        parts = []
        for x in rows:
            if (x.get("actual") or 0) <= 0 or x.get(metric) is None:
                continue
            if metric == "oos" and x.get("dept") == "02" and x["level"] == "section":
                continue                                   # fresh sections are not measured for OOS
            fmt = ctx.stores.get(x["store_id"], {}).get("format") if x["level"] in ("store", "dept") else None
            peers = ctx.peer_values((x["level"], x["code"]), metric, fmt)
            s = _rank_score(x[metric], peers, True, r["min_peers"])
            if s is not None:
                parts.append((s, x[metric], x["actual"], len(peers)))
        if parts:
            w = sum(pp[2] for pp in parts)
            s = sum(pp[0] * pp[2] for pp in parts) / w
            v = sum(pp[1] * pp[2] for pp in parts) / w
            out[key] = {"value": v, "display": f"{v:.1f}%", "score": s,
                        "detail": f"compared with the same {'area' if len(parts) == 1 else 'areas'} in {max(pp[3] for pp in parts)} stores"}
    # productivity
    ratios = []
    for sid in store_ids:
        prow = ctx.prod.get(sid, {})
        lvl = p.domain.get("level")
        picked = []
        if lvl in ("store", "area"):
            picked = [prow["STORE"]] if "STORE" in prow else []
        elif lvl == "cco":
            picked = [prow["CCO"]] if "CCO" in prow else []
        elif lvl == "dept":
            d = p.domain.get("dept")
            picked = [prow[f"D{d}"]] if f"D{d}" in prow else []
            if not picked:          # Fresh (02) has no department row: use its sections' rows
                codes = {c for c, x in ctx.sales.get(sid, {}).items() if x.get("dept") == d and x["level"] == "section"}
                picked = [v for k, v in prow.items() if v.get("level") == "section" and codes & set(k.split("+"))]
        elif lvl == "sections":
            codes = set(p.domain.get("codes", []))
            picked = [v for k, v in prow.items() if codes & set(k.split("+"))]
            if not picked:
                depts = {x.get("dept") for x in ctx.sales_rows(sid, p.domain) if x.get("dept")}
                picked = [prow[f"D{d}"] for d in depts if f"D{d}" in prow]
                if not picked and "OTHER" in prow and not codes & {"S052", "S054", "S050", "S051", "S053", "S056"}:
                    picked = [prow["OTHER"]]
        ratios += [(v["actual"] / v["target"] * 100, v) for v in picked if v.get("actual") is not None and v.get("target")]
    if ratios:
        pct = sum(x[0] for x in ratios) / len(ratios)
        names = ", ".join(sorted({x[1]["row_name"] for x in ratios}))[:80]
        out["prod"] = {"value": pct, "display": f"{pct:.0f}% of target", "score": curve3(pct, *r["productivity"]),
                       "detail": names}
    return out


def _team(ctx: _Ctx, p: Person) -> list[Person]:
    ppl = ctx.people
    if p.role in ("GM", "HBM"):
        return [x for x in ppl.values() if x.store_id == p.store_id and x.emp != p.emp]
    if p.role == "DH":
        return [x for x in ppl.values() if x.store_id == p.store_id and x.dept_code == p.domain.get("dept") and x.emp != p.emp]
    if p.role == "CCO":
        return [x for x in ppl.values() if x.store_id == p.store_id and x.dept_code == "11" and x.emp != p.emp]
    return [ppl[e] for e in p.reports if e in ppl]


def _score(ctx: _Ctx, p: Person) -> None:
    r = ctx.rules
    weights = ctx.weights.get(p.role, {})
    comps: dict[str, dict] = {}
    if p.att and p.att.get("score") is not None:
        a = p.att
        comps["own"] = {"value": a["presence"], "score": a["score"],
                        "display": f"{a['presence']:.0f}% present" + (f" · {a['compliance']:.0f}% full 9h days" if a["compliance"] is not None else ""),
                        "detail": f"{a['worked']} days worked, {a['absent']} unexplained absences, {a['fixes']} punches to fix"}
    store_ids = p.domain.get("stores", []) if p.role == "AREA" else ([p.store_id] if p.store_id else [])
    biz = _business(ctx, p, store_ids) if p.role != "STAFF" else {}
    for k in ("sales", "prod", "oos", "waste"):
        if k in biz:
            comps[k] = biz[k]
    p.context = [{"key": k[1:], **v} for k, v in biz.items() if k.startswith("_")]
    if "team" in weights:
        team = [t for t in _team(ctx, p) if t.att and t.att.get("score") is not None]
        if team:
            s = sum(t.att["score"] for t in team) / len(team)
            comps["team"] = {"value": s, "score": s, "display": f"{s:.1f}/10 average", "detail": f"{len(team)} people"}
    if p.role == "STAFF" and p.domain.get("level") not in (None, "none"):
        sec = _business(ctx, p, store_ids)
        sw = ctx.weights["SM"]
        parts = [(sw[k], sec[k]["score"]) for k in ("sales", "prod", "oos", "waste") if k in sec and k in sw]
        if parts:
            s = sum(w * x for w, x in parts) / sum(w for w, _ in parts)
            comps["section"] = {"value": s, "score": s, "display": f"{s:.1f}/10", "detail": _domain_label(ctx, p)}
        p.context = [{"key": k[1:], **v} for k, v in sec.items() if k.startswith("_")]
    total_w = sum(weights.values()) or 1
    avail = {k: v for k, v in comps.items() if k in weights}
    aw = sum(weights[k] for k in avail)
    p.components = []
    for k, w in weights.items():
        c = avail.get(k)
        p.components.append({"key": k, "label": COMPONENT_LABEL[k], "weight": w, "available": c is not None,
                             "score": None if c is None else round(c["score"], 1),
                             "display": None if c is None else c["display"], "detail": None if c is None else c.get("detail"),
                             "flag": None if c is None else c.get("flag"),
                             "share": None if c is None else round(w / aw * 100) if aw else None})
    p.coverage = aw / total_w
    p.kpis = {k: v.get("value") for k, v in comps.items()}
    joined_recent = False
    if p.joining:
        try:
            joined_recent = (ctx.m_end - date.fromisoformat(p.joining)).days < r["new_joiner_days"]
        except ValueError:
            pass
    if joined_recent:
        p.score, p.status = None, "new_joiner"
    elif aw == 0 or p.coverage * 100 < r["min_coverage"]:
        p.score, p.status = None, "not_enough_data"
    else:
        p.score = sum(weights[k] * avail[k]["score"] for k in avail) / aw
        p.status = "scored"
    p.provisional = ctx.data_days < r["provisional_days"]
    if p.att:
        if p.att["longest_absence"] >= r["long_absence_days"]:
            p.flags.append(f"Absent {p.att['longest_absence']} days in a row")
        if p.att["fixes"]:
            p.flags.append(f"{p.att['fixes']} punches to fix")
    if p.manager_status == "uncertain":
        p.flags.append("Reporting manager name matches more than one person")
    if any(c.get("flag") for c in comps.values()):
        p.flags.append("Extreme sales variance")


def _domain_label(ctx: _Ctx, p: Person) -> str:
    d = p.domain
    lvl = d.get("level")
    if lvl == "store":
        return f"Total store · {p.store}"
    if lvl == "dept":
        return f"{DEPT_NAMES.get(d.get('dept', ''), 'Department ' + d.get('dept', ''))} · {p.store}"
    if lvl == "sections":
        names = []
        rows = ctx.sales.get(p.store_id, {})
        for c in d.get("codes", []):
            names.append(f"{c} {rows[c]['name']}" if c in rows else c)
        return ", ".join(names) + f" · {p.store}"
    if lvl == "cco":
        return f"CCO · {p.store}"
    if lvl == "area":
        return f"{len(d.get('stores', []))} stores"
    return "Attendance only"


def domain_label(mm: MonthModel, p: Person) -> str:
    return _domain_label(_Ctx(mm.people, mm.stores, getattr(mm, "sales", {}), getattr(mm, "prod", {}), {}, {}, 0, None), p)


def history(db: Database, months: int = 6, upto: str | None = None) -> list[MonthModel]:
    av = months_available(db)
    if upto:
        av = [m for m in av if m <= upto]
    return [model(db, m) for m in av[-months:]]


def safe_round(v, n=1):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, n)


__all__ = ["model", "months_available", "history", "band", "MonthModel", "Person", "prev_month", "COMPONENT_LABEL",
           "DEFAULT_WEIGHTS", "DEFAULT_RULES", "domain_label", "settings"]
