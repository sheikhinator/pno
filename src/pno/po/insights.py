"""Cross-tab P&O insights: store scorecards, leader 360°, talent, turnover, roster.

Everything here is computed from the imported workbook tabs. Values that a
tab does not provide stay ``None`` — they are never filled with zero — and
every derived figure states the rule that produced it.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from . import canon, derive

DEFAULT_WEIGHTS: dict[str, float] = {
    "sales": 30.0,
    "productivity": 20.0,
    "shrink": 15.0,
    "stock_days": 10.0,
    "rating": 15.0,
    "retention": 10.0,
}
WEIGHT_LABELS = {
    "sales": "Sales vs budget",
    "productivity": "Productivity vs target",
    "shrink": "Shrinkage vs budget",
    "stock_days": "Stock days vs budget",
    "rating": "Performance rating",
    "retention": "Team retention",
}
BUSINESS_COMPONENTS = ("sales", "productivity", "shrink", "stock_days")
PACK_LABELS = {
    "po_master": "Basic Sheet (employee master)", "po_role": "Time in current role", "po_rating": "Performance ratings",
    "po_shift": "Shift roster", "po_sales": "Store performance (sales)", "po_productivity": "Section productivity",
    "po_shrink": "Shrinkage & stock days", "po_nps": "Customer NPS", "po_turnover": "Turnover", "po_da": "Disciplinary actions",
}
DEPARTMENT_SECTIONS = {"Consumer Goods", "Fresh Food", "Non Food", "Overall", "Other Sections"}


DATED = {"po_turnover", "po_shift"}
SHORT = {"general": "General", "mtd": "MTD", "ytd": "YTD"}
_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _ml(ym: str | None) -> str:
    return f"{_MON[int(ym[5:7]) - 1]} {ym[:4]}" if ym and len(ym) >= 7 else "—"


def view_label(v: dict[str, Any]) -> str:
    if v["type"] == "latest":
        return "Latest data"
    if v["type"] == "mtd":
        return f"MTD {_ml(v['to'])}"
    if v["from"][:4] == v["to"][:4]:
        return f"YTD {_MON[int(v['from'][5:7]) - 1]}–{_ml(v['to'])}"
    return f"{_ml(v['from'])} – {_ml(v['to'])}"


def _info(i: dict[str, Any]) -> dict[str, Any]:
    if i["type"] == "mtd":
        lab = f"MTD {_ml(i['to'])}"
    elif i["from"] and i["from"] != i["to"]:
        lab = view_label({"type": "ytd", "from": i["from"], "to": i["to"]})
    else:
        lab = f"YTD {_ml(i['to'])}"
    return {"type": i["type"], "from": i["from"], "to": i["to"], "label": lab, "iid": i.get("iid")}


def _split_imports(kind: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows grouped by import; a sales report holding both MTD and YTD lines counts as two."""
    out: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        ptype, pfrom, pto = r.get("_ptype") or "mtd", r.get("_pfrom"), r.get("_pto")
        line_period = str(r.get("period") or "").upper() if kind == "po_sales" else ""
        if line_period in ("MTD", "YTD") and ptype != "general":
            if line_period == "MTD":
                ptype, pfrom = "mtd", pto
            else:
                ptype = "ytd"
                pfrom = str(r.get("period_from") or "")[:7] or (pfrom if pfrom and pfrom != pto else f"{(pto or '')[:4]}-01")
        key = (r.get("_iid"), ptype)
        g = out.setdefault(key, {"iid": r.get("_iid") or 0, "type": ptype, "from": pfrom, "to": pto, "rows": []})
        g["rows"].append(r)
    return list(out.values())


def _month_add(ym: str, n: int) -> str:
    y, m = divmod(int(ym[:4]) * 12 + int(ym[5:7]) - 1 + n, 12)
    return f"{y:04d}-{m + 1:02d}"


def available_periods(by_kind: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Months and period types the imported tabs can be read for (a continuous run of months, newest last)."""
    ends: set[str] = set()
    starts: set[str] = set()
    types: set[str] = set()
    ytd_from: dict[str, str] = {}
    dated: set[str] = set()
    for kind, rows in by_kind.items():
        for i in _split_imports(kind, rows):
            if i["type"] == "general":
                continue
            types.add(i["type"])
            if kind in DATED:
                dated.update(str(r.get("date") or "")[:7] for r in i["rows"] if len(str(r.get("date") or "")) >= 7)
                continue
            if i["to"]:
                ends.add(i["to"])
            if i["from"]:
                starts.add(i["from"])
            if i["type"] == "ytd" and i["to"] and i["from"]:
                ytd_from[i["to"]] = min(ytd_from.get(i["to"], i["from"]), i["from"])
    last = max(ends | dated) if (ends or dated) else None
    if not last:
        return {"months": [], "types": sorted(types), "ytd_from": ytd_from, "default_to": None}
    first = min(starts | ends) if ends else min(dated)
    first = max(first, _month_add(last, -35), f"{_month_add(last, -11)[:4]}-01" if not ends else first)
    months, m = [], first
    while m <= last:
        months.append(m)
        m = _month_add(m, 1)
    # the month most summary tabs reach (not a roster planned into next month)
    default_to = max(ends) if ends else last
    return {"months": months, "types": sorted(types), "ytd_from": ytd_from, "default_to": default_to}


def normalise_view(view: dict[str, Any] | None, available: dict[str, Any]) -> dict[str, Any]:
    v = dict(view or {})
    t = v.get("type") if v.get("type") in ("latest", "mtd", "ytd") else "latest"
    months = available.get("months") or []
    if t == "latest" or not months:
        return {"type": "latest", "from": None, "to": None}
    to = v.get("to") if v.get("to") and len(str(v.get("to"))) == 7 else (available.get("default_to") or months[-1])
    if t == "mtd":
        return {"type": "mtd", "from": to, "to": to}
    frm = v.get("from") if v.get("from") and len(str(v["from"])) == 7 else available.get("ytd_from", {}).get(to) or f"{to[:4]}-01"
    if frm > to:
        frm, to = to, frm
    return {"type": "ytd", "from": frm, "to": to}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return 100.0 * numerator / denominator


def _mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def _parse(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _months_between(start: date | None, end: date) -> int | None:
    if not start:
        return None
    return max(0, (end.year - start.year) * 12 + end.month - start.month - (end.day < start.day))


def tenure_text(months: int | None) -> str:
    if months is None:
        return "—"
    years, rest = divmod(months, 12)
    if years and rest:
        return f"{years} yr {rest} mo"
    return f"{years} yr" if years else f"{rest} mo"


@dataclass
class Leader:
    key: str
    employee_id: str
    name: str
    store: str
    designation: str
    grade: str = ""
    sections: list[str] = field(default_factory=list)
    role_since: date | None = None
    months_in_role: int | None = None
    joining_date: date | None = None
    months_service: int | None = None
    manager_name: str = ""
    remarks: str = ""
    acting: bool = False
    designation_mismatch: bool = False
    system_designation: str = ""                       # the title in the HR system when the person works as another
    whole_store: bool = False
    ratings: list[dict[str, Any]] = field(default_factory=list)
    shifts: Counter = field(default_factory=Counter)
    kpis: dict[str, Any] = field(default_factory=dict)
    components: dict[str, float] = field(default_factory=dict)
    score: float | None = None
    business: float | None = None

    @property
    def latest_rating(self) -> float | None:
        rated = [r for r in self.ratings if r.get("rating") is not None]
        if not rated:
            return None
        return sorted(rated, key=lambda r: (r.get("cycle") or 0, not r.get("role_change")))[-1]["rating"]

    @property
    def rating_label(self) -> str:
        rated = [r for r in self.ratings if r.get("rating") is not None]
        if not rated:
            return "Unrated" if self.ratings else "No rating on file"
        return sorted(rated, key=lambda r: (r.get("cycle") or 0, not r.get("role_change")))[-1].get("rating_label", "")

    @property
    def section_text(self) -> str:
        if self.whole_store:
            return "Whole store"
        return " & ".join(self.sections) if self.sections else "—"


class Insights:
    """Loads the latest imported month of every P&O tab once, then answers questions."""

    def __init__(self, store: Any, weights: dict[str, float] | None = None, as_of: date | None = None,
                 view: dict[str, Any] | None = None):
        self.weights = dict(DEFAULT_WEIGHTS)
        if weights:
            self.weights.update({k: float(v) for k, v in weights.items() if k in DEFAULT_WEIGHTS})
        self.data: dict[str, list[dict[str, Any]]] = {}
        self.periods: dict[str, str] = {}
        self.sources: dict[str, str] = {}
        self.coverage: list[dict[str, Any]] = []       # what each tab contributes to the period on screen
        self.notes: list[str] = []                      # tabs that had no data for that exact period
        self._cut: set[str] = set()
        self._full: dict[str, list[dict[str, Any]]] = {}
        records = store.records() if store is not None else []
        by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            kind = str(record.get("_kind", ""))
            if kind.startswith("po_"):
                by_kind[kind].append(record)
        self.available = available_periods(by_kind)
        self.view = normalise_view(view, self.available)
        for kind, rows in by_kind.items():
            chosen, info = self._select(kind, rows)
            if not chosen and info.get("cut") and kind == "po_turnover":
                self._cut.add(kind)                     # the file covers the period: nobody left in it is a real 0
                self.periods[kind] = info["label"]
            if not chosen:
                if info.get("note"):
                    self.notes.append(info["note"])
                self.coverage.append({"kind": kind, **info, "rows": 0})
                continue
            self.data[kind] = chosen
            self.periods[kind] = info["label"]
            self.sources[kind] = f"{chosen[0].get('_source', '')} · {chosen[0].get('_sheet', '')} · {info['label']}"
            self.coverage.append({"kind": kind, **info, "rows": len(chosen)})
            if info.get("note"):
                self.notes.append(info["note"])
        self.as_of = as_of or self._view_as_of() or self._infer_as_of()
        self._leaders: list[Leader] | None = None

    # ---------------------------------------------------------- periods --

    def _select(self, kind: str, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """The rows of one tab that answer the period on screen.

        General tabs (employee master, time in role, ratings) count for every period: the latest one is used.
        Dated tabs (turnover, shift roster) are cut to the period's months from their own dates.
        Summary tabs (sales, productivity, shrinkage, NPS, DA) use the import whose period matches; when none does, the
        closest one is used and a note says so, so a YTD figure is never passed off as a month's."""
        name = PACK_LABELS.get(kind, kind)
        imports = _split_imports(kind, rows)
        general = [i for i in imports if i["type"] == "general"]
        timed = [i for i in imports if i["type"] != "general"]
        v = self.view
        if general and not timed:
            pick = max(general, key=lambda i: i["iid"])
            return pick["rows"], {"type": "general", "label": "every period", "from": None, "to": None, "iid": pick["iid"]}
        if not timed:
            return [], {"type": "", "label": "", "from": None, "to": None}
        if v["type"] == "latest":
            pick = max(timed, key=lambda i: (i["to"] or "", i["type"] == "ytd", i["iid"]))
            return pick["rows"], _info(pick)
        vf, vt = v["from"], v["to"]
        if kind in DATED:
            overlap = [i for i in timed if (i["from"] or "") <= vt and (i["to"] or "9999") >= vf]
            if not overlap:
                return [], {"type": v["type"], "label": "", "from": vf, "to": vt,
                            "note": f"{name}: nothing dated between {_ml(vf)} and {_ml(vt)}."}
            pick = max(overlap, key=lambda i: ((i["to"] or "") >= vt and (i["from"] or "") <= vf, i["iid"]))
            self._full[kind] = pick["rows"]                # whole file, for trends that show the months around the period
            date_key = "date"
            kept = [r for r in pick["rows"] if vf <= str(r.get(date_key) or "")[:7] <= vt]
            undated = [r for r in pick["rows"] if not r.get(date_key)]
            kept += undated
            info = {"type": v["type"], "from": vf, "to": vt, "label": f"{view_label(v)} · cut from dated rows", "cut": True, "iid": pick["iid"]}
            if (pick["from"] or "") > vf or (pick["to"] or "") < vt:
                info["note"] = f"{name}: the file only covers {_ml(pick['from'])}–{_ml(pick['to'])}."
            return kept, info
        exact = [i for i in timed if i["type"] == v["type"] and i["to"] == vt]
        same_window = [i for i in exact if i["from"] == vf]
        if same_window:
            pick = max(same_window, key=lambda i: i["iid"])
            return pick["rows"], _info(pick)
        worked = derive.derive(kind, timed, vf, vt)          # e.g. MTD Sep = YTD Sep − YTD Aug
        if worked:
            rows_d, how = worked
            return rows_d, {"type": v["type"], "from": vf, "to": vt, "label": f"{view_label(v)} · worked out", "how": how,
                            "derived": True}
        if exact:
            pick = max(exact, key=lambda i: i["iid"])
            return pick["rows"], _info(pick)
        before = [i for i in timed if (i["to"] or "") <= vt]
        pool = before or timed
        pick = max(pool, key=lambda i: (i["type"] == v["type"], i["to"] or "", i["iid"]))
        info = _info(pick)
        hint = "" if derive.can_derive(kind) else " (percentages can't be worked out from other periods: import that period's file)"
        info["note"] = f"{name}: no {SHORT[v['type']]} data for {_ml(vt)}; showing {info['label']}{hint}."
        return pick["rows"], info

    def _view_as_of(self) -> date | None:
        if self.view["type"] == "latest" or not self.view.get("to"):
            return None
        y, m = int(self.view["to"][:4]), int(self.view["to"][5:7])
        end = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        dated = self._infer_as_of()
        return min(end, max(dated, date(y, m, 1))) if dated else min(end, date.today())

    @property
    def window_months(self) -> int:
        """Months the leaver window covers (12 for the latest view)."""
        if self.view["type"] == "latest":
            return 12
        return len(derive.months(self.view["from"], self.view["to"]))

    def _rate(self, leavers: list[dict[str, Any]]) -> dict[str, Any]:
        """Yearly turnover rate, only over the stores the Basic Sheet covers (leavers and headcount from the same stores)."""
        covered = {r.get("store") for r in self.rows("po_master") if r.get("store")}
        heads = self.headcount_total()
        if not covered or not heads or not self.window_months:
            return {"headcount": heads or None, "rate_annualised": None, "rate_scope": ""}
        inside = [r for r in leavers if r.get("store") in covered]
        all_stores = {r.get("store") for r in (self._full.get("po_turnover") or self.rows("po_turnover")) if r.get("store")} | set(self.stores())
        scope = "all stores" if all_stores <= covered else f"{len(covered)} of {len(all_stores)} stores on the Basic Sheet"
        return {"headcount": heads, "rate_annualised": round(100 * len(inside) * 12 / self.window_months / heads, 1),
                "rate_scope": scope, "rate_leavers": len(inside)}

    def headcount_total(self) -> int:
        return self.headcount() or 0

    @property
    def leaver_window(self) -> str:
        return view_label(self.view) if self.view["type"] != "latest" else "last 12 months"

    @property
    def view_label(self) -> str:
        if self.view["type"] == "latest":
            timed = {c["label"] for c in self.coverage if c.get("type") not in ("general", "") and c.get("label")}
            return "Latest data" + (f" ({', '.join(sorted(timed))})" if 0 < len(timed) <= 2 else "")
        return view_label(self.view)

    # ---------------------------------------------------------- basics --

    def has(self, kind: str) -> bool:
        return bool(self.data.get(kind)) or kind in self._cut

    @property
    def empty(self) -> bool:
        return not self.data

    def rows(self, kind: str) -> list[dict[str, Any]]:
        return self.data.get(kind, [])

    def _infer_as_of(self) -> date:
        candidates: list[date] = []
        for kind in ("po_turnover", "po_shift"):
            dates = [_parse(r.get("date")) for r in self.rows(kind)]
            dates = [d for d in dates if d]
            if dates:
                candidates.append(max(dates))
        for r in self.rows("po_sales")[:1]:
            d = _parse(r.get("period_to"))
            if d:
                candidates.append(d)
        return max(candidates) if candidates else date.today()

    def stores(self, include_myli: bool = False) -> list[str]:
        names: set[str] = set()
        for kind in ("po_sales", "po_productivity", "po_shrink", "po_master", "po_role"):
            names.update(r.get("store", "") for r in self.rows(kind))
        names.discard("")
        if not include_myli:
            names = {n for n in names if not n.endswith("· Myli")}
        known = [s[0] for s in canon._STORES]
        return sorted(names, key=lambda n: (known.index(n.replace(" · Myli", "")) if n.replace(" · Myli", "") in known else 99, n))

    # ------------------------------------------------------- per-metric --

    def sales_total(self, store: str) -> dict[str, Any] | None:
        rows = [r for r in self.rows("po_sales") if r["store"] == store]
        for label in ("Total Store", "Total"):
            for r in rows:
                if r.get("line") == label:
                    return r
        return None

    def sales_section(self, store: str, section: str) -> dict[str, Any] | None:
        """Sum section-level sales lines for one canonical section (never subtotals)."""
        if section in {"Consumer Goods", "Fresh Food", "Non Food"}:
            members = {s for s, d in canon.DEPARTMENT_OF.items() if d == section or (section == "Non Food" and d in {"Light Household", "Heavy Household", "Textile"})}
        else:
            members = {section}
        rows = [r for r in self.rows("po_sales") if r["store"] == store and r.get("level") == "section" and r.get("section") in members]
        if not rows:
            return None
        actual = sum(r["actual"] or 0 for r in rows)
        budget_rows = [r for r in rows if r.get("budget") is not None]
        budget = sum(r["budget"] for r in budget_rows) if budget_rows else None
        ly_rows = [r for r in rows if r.get("last_year") is not None]
        last_year = sum(r["last_year"] for r in ly_rows) if len(ly_rows) == len(rows) else None

        def weighted(field_name: str) -> float | None:
            pairs = [(r.get(field_name), r["actual"] or 0) for r in rows if r.get(field_name) is not None]
            total = sum(w for _, w in pairs)
            return sum(v * w for v, w in pairs) / total if total else None

        return {
            "actual": actual,
            "budget": budget,
            "last_year": last_year,
            "vs_budget_pct": _pct(actual, budget),
            "growth_pct": (_pct(actual - last_year, last_year) if last_year else None),
            "margin_pct": weighted("margin_pct"),
            "waste_pct": weighted("waste_pct"),
            "oos_pct": weighted("oos_pct"),
            "lines": len(rows),
        }

    def productivity(self, store: str, section: str) -> dict[str, Any] | None:
        rows = [r for r in self.rows("po_productivity") if r["store"] == store]
        exact = [r for r in rows if r["section"] == section]
        fallback_used = False
        if not exact:
            dept = canon.department(section)
            exact = [r for r in rows if r["section"] == dept]
            fallback_used = bool(exact)
            if not exact and dept in {"Light Household", "Heavy Household", "Textile"}:
                exact = [r for r in rows if r["section"] == "Other Sections"]
                fallback_used = bool(exact)
            if not exact and section in canon.DEPARTMENT_OF and canon.department(section) == "Consumer Goods":
                exact = [r for r in rows if r["section"] == "Other Sections"]
                fallback_used = bool(exact)
        if not exact:
            return None
        r = exact[0]
        return {
            "actual": r["productivity"], "target": r.get("target"), "ly": r.get("productivity_ly"),
            "forecast": r.get("forecast"),
            "vs_target_pct": _pct((r["productivity"] - r["target"]) if r.get("target") else None, r.get("target")),
            "vs_ly_pct": _pct((r["productivity"] - r["productivity_ly"]) if r.get("productivity_ly") else None, r.get("productivity_ly")),
            "level": r["section"], "fallback": fallback_used,
        }

    def shrink(self, store: str, section: str) -> dict[str, Any] | None:
        rows = [r for r in self.rows("po_shrink") if r["store"] == store]
        exact = [r for r in rows if r["section"] == section]
        fallback = False
        if not exact:
            dept = canon.department(section)
            exact = [r for r in rows if r["section"] == dept]
            fallback = bool(exact)
        if not exact:
            return None
        r = exact[0]
        days_ratio = None
        if r.get("stock_days_budget") and r.get("stock_days_actual") is not None:
            days_ratio = r["stock_days_actual"] / r["stock_days_budget"]
        return {**{k: r.get(k) for k in ("shrink_budget_pct", "shrink_actual_pct", "shrink_variance_pct", "stock_days_budget", "stock_days_actual")},
                "days_ratio": days_ratio, "level": r["section"], "fallback": fallback}

    def nps(self, city: str, section: str | None = None) -> dict[str, Any] | None:
        rows = [r for r in self.rows("po_nps") if r.get("city") == city and r.get("nps") is not None]
        if not rows:
            return None
        latest = max(r["year"] or 0 for r in rows)
        previous = [r for r in rows if r["year"] == latest - 1]
        current = [r for r in rows if r["year"] == latest]
        if section:
            current = [r for r in current if r["section"] == section]
            previous = [r for r in previous if r["section"] == section]
        if not current:
            return None
        score = _mean([r["nps"] for r in current])
        prior = _mean([r["nps"] for r in previous])
        return {"nps": score, "year": latest, "previous": prior, "change": (score - prior) if prior is not None and score is not None else None, "categories": len(current)}

    def leavers(self, store: str | None = None, section: str | None = None, months: int = 12) -> list[dict[str, Any]]:
        start = self.as_of - timedelta(days=round(months * 30.44))
        if self.view["type"] != "latest":                  # the period on screen decides the window
            start = date(int(self.view["from"][:4]), int(self.view["from"][5:7]), 1)
        out = []
        for r in self.rows("po_turnover"):
            d = _parse(r.get("date"))
            if not d or d < start or d > self.as_of:
                continue
            if store and r.get("store") != store:
                continue
            if section and r.get("section") != section and canon.department(r.get("section", "")) != section:
                continue
            out.append(r)
        return out

    def da_count(self, store: str, section: str | None = None) -> int:
        total = 0
        for r in self.rows("po_da"):
            if r.get("store") != store:
                continue
            if section and r.get("section") != section:
                continue
            total += int(r.get("count") or 0)
        return total

    def headcount(self, store: str | None = None) -> int | None:
        rows = self.rows("po_master")
        if not rows:
            return None
        return sum(1 for r in rows if store is None or r.get("store") == store)

    # -------------------------------------------------------- scorecard --

    def store_scorecard(self) -> list[dict[str, Any]]:
        output = []
        for name in self.stores():
            sales = self.sales_total(name)
            prod = self.productivity(name, "Overall")
            shrink_rows = [r for r in self.rows("po_shrink") if r["store"] == name and r["section"] not in DEPARTMENT_SECTIONS]
            variances = [r["shrink_variance_pct"] for r in shrink_rows if r.get("shrink_variance_pct") is not None]
            over_days = [r for r in shrink_rows if r.get("stock_days_budget") and r.get("stock_days_actual") and r["stock_days_actual"] > r["stock_days_budget"] * 1.2]
            worst = min(shrink_rows, key=lambda r: r.get("shrink_variance_pct") if r.get("shrink_variance_pct") is not None else 0, default=None)
            city = canon.store_city(name)
            nps = self.nps(city) if city else None
            leavers = self.leavers(name)
            leaders = [l for l in self.leaders() if l.store == name]
            ratings = [l.latest_rating for l in leaders if l.latest_rating is not None]
            scored = [l.score for l in leaders if l.score is not None]
            row = {
                "store": name,
                "format": canon.store_format(name),
                "city": city,
                "sales": sales.get("actual") if sales else None,
                "budget": sales.get("budget") if sales else None,
                "sales_vs_budget_pct": _pct(sales["actual"], sales["budget"]) if sales and sales.get("budget") else None,
                "growth_pct": sales.get("growth_pct") if sales else None,
                "margin_pct": sales.get("margin_pct") if sales else None,
                "waste_pct": sales.get("waste_pct") if sales else None,
                "oos_pct": sales.get("oos_pct") if sales else None,
                "customers": sales.get("customers") if sales else None,
                "customers_growth_pct": sales.get("customers_growth_pct") if sales else None,
                "basket": sales.get("basket") if sales else None,
                "productivity": prod["actual"] if prod else None,
                "productivity_target": prod["target"] if prod else None,
                "productivity_vs_target_pct": prod["vs_target_pct"] if prod else None,
                "shrink_variance_avg": _mean(variances),
                "shrink_worst_section": worst["section"] if worst and worst.get("shrink_variance_pct") is not None and worst["shrink_variance_pct"] < 0 else None,
                "shrink_worst_variance": worst.get("shrink_variance_pct") if worst else None,
                "sections_over_stock_days": len(over_days),
                "nps": nps["nps"] if nps else None,
                "leavers_12m": len(leavers) if self.has("po_turnover") else None,
                "da_cases": self.da_count(name) if self.has("po_da") else None,
                "leaders": len(leaders),
                "avg_rating": _mean(ratings),
                "avg_leader_score": _mean(scored),
            }
            row["status"] = self._store_status(row)
            output.append(row)
        return output

    @staticmethod
    def _store_status(row: dict[str, Any]) -> str:
        points = 0
        checks = 0
        for value, good, bad in (
            (row.get("sales_vs_budget_pct"), 100, 92),
            (100 + row["productivity_vs_target_pct"] if row.get("productivity_vs_target_pct") is not None else None, 100, 92),
        ):
            if value is None:
                continue
            checks += 1
            points += 2 if value >= good else (1 if value >= bad else 0)
        if row.get("shrink_variance_avg") is not None:
            checks += 1
            points += 2 if row["shrink_variance_avg"] >= 0 else (1 if row["shrink_variance_avg"] > -1 else 0)
        if not checks:
            return "No data"
        ratio = points / (2 * checks)
        return "On track" if ratio >= 0.75 else ("Watch" if ratio >= 0.4 else "At risk")

    def section_matrix(self, metric: str) -> tuple[list[str], list[str], dict[tuple[str, str], float | None]]:
        stores = self.stores()
        sections = list(canon.SECTION_ORDER)
        values: dict[tuple[str, str], float | None] = {}
        for store_name in stores:
            for section_name in sections:
                value = None
                if metric == "sales_vs_budget":
                    s = self.sales_section(store_name, section_name)
                    value = s["vs_budget_pct"] if s else None
                elif metric == "growth":
                    s = self.sales_section(store_name, section_name)
                    value = s["growth_pct"] if s else None
                elif metric == "productivity_vs_target":
                    p = self.productivity(store_name, section_name)
                    value = p["vs_target_pct"] if p and not p["fallback"] else None
                elif metric == "shrink_variance":
                    s = self.shrink(store_name, section_name)
                    value = s["shrink_variance_pct"] if s and not s["fallback"] else None
                elif metric == "stock_days":
                    s = self.shrink(store_name, section_name)
                    value = (100 * s["days_ratio"]) if s and s.get("days_ratio") and not s["fallback"] else None
                elif metric == "oos":
                    s = self.sales_section(store_name, section_name)
                    value = s["oos_pct"] if s else None
                elif metric == "margin":
                    s = self.sales_section(store_name, section_name)
                    value = s["margin_pct"] if s else None
                values[(store_name, section_name)] = value
        used = [s for s in sections if any(values[(st, s)] is not None for st in stores)]
        return stores, used, values

    # ---------------------------------------------------------- leaders --

    def leaders(self) -> list[Leader]:
        if self._leaders is not None:
            return self._leaders
        people: dict[str, Leader] = {}

        def key_for(emp: str, name: str) -> str:
            return emp or f"name:{canon.name_key(name)}"

        master = {r["employee_id"]: r for r in self.rows("po_master")}
        for r in self.rows("po_role"):
            key = key_for(r.get("employee_id", ""), r["employee_name"])
            system = canon.text(r.get("designation"))
            if system.startswith("#"):
                system = ""
            working = r.get("working_as") or canon.working_role(r.get("remarks", ""), system)
            people[key] = Leader(
                key=key, employee_id=r.get("employee_id", ""), name=r["employee_name"], store=r["store"],
                designation=working or system, sections=list(r.get("sections_led") or []),
                role_since=_parse(r.get("role_since")), remarks=r.get("remarks", ""),
                acting=bool(r.get("acting")) or bool(working and not canon.is_leader(system)),
                designation_mismatch=bool(r.get("designation_mismatch")) or bool(working and system),
                system_designation=system if working else "",
            )
        for r in self.rows("po_master"):
            if not canon.is_leader(r.get("designation")):
                continue
            key = r["employee_id"]
            if key not in people:
                section = r.get("section")
                people[key] = Leader(key=key, employee_id=key, name=r["employee_name"], store=r["store"],
                                     designation=r.get("designation", ""),
                                     sections=[section] if section in canon.DEPARTMENT_OF and section not in {"Management", "Services"} else [])
        for r in self.rows("po_shift"):
            key = r["employee_id"]
            if key not in people and canon.is_leader(r.get("designation")):
                section = r.get("section")
                people[key] = Leader(key=key, employee_id=key, name=r["employee_name"], store=r["store"],
                                     designation=r.get("designation", ""),
                                     sections=[section] if section in canon.DEPARTMENT_OF and section not in {"Management", "Services"} else [])
        # people the role tab could not place (new joiners not in the system yet): find them by name elsewhere
        by_name = {}
        for kind in ("po_master", "po_shift"):
            for r in self.rows(kind):
                by_name.setdefault(canon.name_key(r.get("employee_name", "")), r)
        for leader in people.values():
            if leader.store and leader.employee_id:
                continue
            hit = by_name.get(canon.name_key(leader.name))
            if hit:
                leader.store = leader.store or hit.get("store", "")
                if not leader.employee_id and hit.get("employee_id"):
                    leader.employee_id = hit["employee_id"]
                if not leader.sections and hit.get("section") in canon.DEPARTMENT_OF and hit["section"] not in {"Management", "Services"}:
                    leader.sections = [hit["section"]]
        # store managers and deputies run the whole store: measured on the three departments together
        for leader in people.values():
            if not leader.sections and canon.role_rank(leader.designation) >= canon.STORE_LEVEL:
                leader.sections = ["Consumer Goods", "Fresh Food", "Non Food"]
                leader.whole_store = True
        # enrich
        latest_month = None
        shift_dates = [r["date"][:7] for r in self.rows("po_shift") if r.get("date")]
        if shift_dates:
            latest_month = max(shift_dates)
        for leader in people.values():
            m = master.get(leader.employee_id)
            if m:
                leader.grade = m.get("grade", "")
                leader.joining_date = _parse(m.get("joining_date"))
                leader.manager_name = m.get("manager_name", "")
                if not leader.store:
                    leader.store = m.get("store", "")
            leader.months_in_role = _months_between(leader.role_since, self.as_of)
            leader.months_service = _months_between(leader.joining_date, self.as_of)
        for r in self.rows("po_rating"):
            key = r["employee_id"]
            if key in people:
                people[key].ratings.append(r)
                if not people[key].grade:
                    people[key].grade = r.get("grade", "")
                if not people[key].manager_name:
                    people[key].manager_name = r.get("manager_name", "")
        for r in self.rows("po_shift"):
            if latest_month and r.get("date", "")[:7] != latest_month:
                continue
            key = r["employee_id"]
            if key in people:
                people[key].shifts[r["shift"]] += 1
        for leader in people.values():
            self._score_leader(leader)
        self._leaders = sorted(people.values(), key=lambda l: (-(l.score if l.score is not None else -1), l.name))
        return self._leaders

    def _score_leader(self, leader: Leader) -> None:
        kpis: dict[str, Any] = {}
        sales_parts, prod_parts, shrink_parts, days_parts = [], [], [], []
        for section in leader.sections:
            s = self.sales_section(leader.store, section)
            if s:
                sales_parts.append((section, s))
            members = [section]
            if section == "Non Food":
                members = ["Light Household", "Heavy Household", "Textile"]
            elif section == "Fresh Food" and not self.productivity(leader.store, section):
                members = ["Bakery", "Butchery", "Fishery", "Deli", "Fruits & Vegetables"]
            for member in members:
                p = self.productivity(leader.store, member)
                if p and not (p["fallback"] and member != section and p["level"] in {"Other Sections"}):
                    prod_parts.append((member, p))
            for member in (members if section == "Non Food" else [section]):
                sh = self.shrink(leader.store, member)
                if sh:
                    shrink_parts.append((member, sh))
        kpis["sales"] = sales_parts
        kpis["productivity"] = prod_parts
        kpis["shrink"] = shrink_parts
        city = canon.store_city(leader.store)
        kpis["nps"] = [(sec, n) for sec in leader.sections if (n := self.nps(city, sec))] if city else []
        leavers = []
        for section in leader.sections or [""]:
            leavers.extend(self.leavers(leader.store, section or None))
        kpis["leavers"] = {id(r): r for r in leavers}.values().__len__() if leavers else (0 if self.has("po_turnover") else None)
        kpis["leaver_rows"] = list({id(r): r for r in leavers}.values())
        kpis["da"] = sum(self.da_count(leader.store, s) for s in leader.sections) if self.has("po_da") else None
        leader.kpis = kpis

        components: dict[str, float] = {}
        actual = sum(s["actual"] for _, s in sales_parts)
        budget = sum(s["budget"] for _, s in sales_parts if s.get("budget")) if sales_parts else 0
        if budget:
            components["sales"] = _clamp((100 * actual / budget - 80) / 40 * 100)
        ratios = [p["actual"] / p["target"] for _, p in prod_parts if p.get("target")]
        if ratios:
            components["productivity"] = _clamp((sum(ratios) / len(ratios) - 0.8) / 0.4 * 100)
        variances = [sh["shrink_variance_pct"] for _, sh in shrink_parts if sh.get("shrink_variance_pct") is not None]
        if variances:
            components["shrink"] = _clamp(100 + min(0.0, sum(variances) / len(variances)) * 20)
        day_ratios = [sh["days_ratio"] for _, sh in shrink_parts if sh.get("days_ratio")]
        if day_ratios:
            components["stock_days"] = _clamp(100 - (sum(day_ratios) / len(day_ratios) - 1) * 200)
        if leader.latest_rating is not None:
            components["rating"] = _clamp((leader.latest_rating - 1) / 4 * 100)
        if kpis["leavers"] is not None and leader.sections:
            components["retention"] = _clamp(100 - kpis["leavers"] * 10)
        leader.components = components
        used = {k: self.weights.get(k, 0) for k in components if self.weights.get(k, 0) > 0}
        if len(used) >= 3:
            total = sum(used.values())
            leader.score = sum(components[k] * w for k, w in used.items()) / total
        business = [components[k] for k in BUSINESS_COMPONENTS if k in components]
        leader.business = sum(business) / len(business) if business else None

    def find_leader(self, query: str) -> list[Leader]:
        q = canon.name_key(query)
        if not q:
            return []
        leaders = self.leaders()
        exact = [l for l in leaders if l.employee_id == query.strip() or canon.name_key(l.name) == q]
        if exact:
            return exact
        tokens = q.split()
        return [l for l in leaders if all(t in canon.name_key(l.name) for t in tokens)]

    # ----------------------------------------------------------- talent --

    @staticmethod
    def talent_box(leader: Leader) -> tuple[int, int] | None:
        """(column, row) on a 3×3 grid: column = business results, row = rating."""
        if leader.business is None or leader.latest_rating is None:
            return None
        col = 0 if leader.business < 40 else (1 if leader.business < 70 else 2)
        row = 0 if leader.latest_rating < 3 else (1 if leader.latest_rating < 4 else 2)
        return col, row

    TALENT_NAMES = {
        (2, 2): "Star", (1, 2): "High performer", (0, 2): "Rated high, results low",
        (2, 1): "Results ahead of rating", (1, 1): "Core player", (0, 1): "Needs support",
        (2, 0): "Under-recognised", (1, 0): "Inconsistent", (0, 0): "Action needed",
    }

    def bench(self) -> list[dict[str, Any]]:
        flags = []
        for leader in self.leaders():
            reasons = []
            if not leader.employee_id:
                reasons.append(("High", "Not in HR system yet"))
            if leader.acting:
                reasons.append(("High", "Acting / delegated role (DOA)"))
            if leader.designation_mismatch:
                reasons.append(("Medium", "System designation differs from actual role"))
            if leader.months_in_role is not None and leader.months_in_role < 6:
                reasons.append(("Medium", f"New in role ({tenure_text(leader.months_in_role)})"))
            if leader.ratings and leader.latest_rating is None:
                reasons.append(("Low", "Latest appraisal unrated"))
            if leader.latest_rating is not None and leader.latest_rating <= 2:
                reasons.append(("High", f"Rated {leader.latest_rating:g} ({leader.rating_label})"))
            for severity, reason in reasons:
                flags.append({"severity": severity, "leader": leader, "reason": reason})
        order = {"High": 0, "Medium": 1, "Low": 2}
        return sorted(flags, key=lambda f: (order[f["severity"]], f["leader"].store, f["leader"].name))

    # --------------------------------------------------------- turnover --

    def turnover_summary(self, months: int = 12) -> dict[str, Any]:
        rows = self.leavers(months=months)
        all_rows = self._full.get("po_turnover") or self.rows("po_turnover")
        by_store = Counter(r["store"] for r in rows)
        by_section = Counter(r["section"] for r in rows)
        by_reason = Counter(r["reason"] or "Not stated" for r in rows)
        by_type = Counter(r["exit_type"] or "Not stated" for r in rows)
        hotspots = Counter((r["store"], r["section"]) for r in rows)
        monthly: dict[str, int] = defaultdict(int)
        start = date(self.as_of.year - 2, self.as_of.month, 1)
        cursor = start
        while cursor <= self.as_of:
            monthly[f"{cursor:%Y-%m}"] = 0
            cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        for r in all_rows:
            d = _parse(r.get("date"))
            if d and f"{d:%Y-%m}" in monthly:
                monthly[f"{d:%Y-%m}"] += 1
        voluntary = sum(1 for r in rows if r.get("voluntary"))
        rate = {}
        for store_name, count in by_store.items():
            heads = self.headcount(store_name)
            rate[store_name] = (100 * count / heads) if heads else None
        return {
            "months": months, "total": len(rows), "all_time": len(all_rows), "window": self.leaver_window,
            "window_months": self.window_months,
            "annualised": round(len(rows) * 12 / self.window_months, 1) if self.window_months else None,
            **self._rate(rows),
            "voluntary_pct": _pct(voluntary, len(rows)) if rows else None,
            "by_store": by_store.most_common(), "by_section": by_section.most_common(),
            "by_reason": by_reason.most_common(), "by_type": by_type.most_common(),
            "hotspots": [(s, sec, n) for (s, sec), n in hotspots.most_common(10)],
            "monthly": sorted(monthly.items()), "rate": rate,
        }

    # ----------------------------------------------------------- roster --

    def roster_summary(self) -> dict[str, Any]:
        rows = self.rows("po_shift")
        if not rows:
            return {"days": [], "stores": [], "coverage": {}, "gaps": [], "leave": []}
        days = sorted({r["date"] for r in rows})
        stores = sorted({r["store"] for r in rows})
        coverage: dict[tuple[str, str], Counter] = defaultdict(Counter)
        for r in rows:
            coverage[(r["store"], r["date"])][r["shift"]] += 1
        # department gaps: every rostered leader of a department off/leave on a day
        dept_day: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        for r in rows:
            dept = canon.department(r["section"]) or r["section"]
            dept_day[(r["store"], dept, r["date"])].append(r["shift"])
        gaps = []
        for (store_name, dept, day), shifts in sorted(dept_day.items()):
            if len(shifts) >= 2 and all(s in {"Off", "Leave"} for s in shifts):
                gaps.append({"store": store_name, "department": dept, "date": day, "leaders": len(shifts)})
        no_cover_evening = []
        for (store_name, day), counter in sorted(coverage.items()):
            working = counter["Morning"] + counter["Mid"] + counter["Evening"]
            if working and counter["Evening"] == 0:
                no_cover_evening.append({"store": store_name, "date": day})
        leave = Counter()
        names = {}
        for r in rows:
            if r["shift"] == "Leave":
                leave[r["employee_id"]] += 1
                names[r["employee_id"]] = (r["employee_name"], r["store"])
        return {
            "days": days, "stores": stores, "coverage": coverage, "gaps": gaps,
            "no_evening": no_cover_evening,
            "leave": [(names[e][0], names[e][1], n) for e, n in leave.most_common()],
            "people": len({r["employee_id"] for r in rows}),
            "mix": Counter(r["shift"] for r in rows),
        }

    # ----------------------------------------------------------- alerts --

    def alerts(self, limit: int | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []

        def add(severity: str, area: str, store_name: str, message: str, value: float = 0.0) -> None:
            out.append({"severity": severity, "area": area, "store": store_name, "message": message, "weight": abs(value)})

        for row in self.store_scorecard():
            vs = row.get("sales_vs_budget_pct")
            if vs is not None and vs < 92:
                add("High", "Sales", row["store"], f"Sales at {vs:.0f}% of budget", 100 - vs)
            if row.get("oos_pct") is not None and row["oos_pct"] >= 15:
                add("Medium", "Availability", row["store"], f"Out-of-stock at {row['oos_pct']:.1f}%", row["oos_pct"])
        for r in self.rows("po_productivity"):
            if r["section"] in {"Overall", "Other Sections"} or not r.get("target"):
                continue
            gap = 100 * (r["productivity"] - r["target"]) / r["target"]
            if gap <= -20:
                add("High" if gap <= -30 else "Medium", "Productivity", r["store"],
                    f"{r['section']} productivity {gap:.0f}% vs target ({r['productivity']:g} vs {r['target']:g})", gap)
        for r in self.rows("po_shrink"):
            v = r.get("shrink_variance_pct")
            if v is None or r["section"] in DEPARTMENT_SECTIONS:
                continue
            if v <= -1.5:
                add("High" if v <= -3 else "Medium", "Shrinkage", r["store"],
                    f"{r['section']} shrinkage {r['shrink_actual_pct']:.1f}% vs budget {r['shrink_budget_pct']:.1f}%", v * 3)
            elif v >= 8:
                add("Low", "Stock control", r["store"],
                    f"{r['section']} shrinkage swing +{v:.1f}pp — check stock accounting", v / 2)
            if r.get("stock_days_budget") and r.get("stock_days_actual") and r["stock_days_actual"] >= 1.5 * r["stock_days_budget"]:
                add("Medium", "Stock days", r["store"],
                    f"{r['section']} holding {r['stock_days_actual']:g} days vs {r['stock_days_budget']:g} budget",
                    100 * (r["stock_days_actual"] / r["stock_days_budget"] - 1) / 4)
        if self.has("po_turnover"):
            for store_name, section, n in self.turnover_summary()["hotspots"]:
                if n >= 4:
                    add("High" if n >= 8 else "Medium", "Turnover", store_name, f"{n} leavers in {section} ({self.leaver_window})", n * 3)
        for flag in self.bench():
            if flag["severity"] == "High":
                leader = flag["leader"]
                add("Medium", "People", leader.store, f"{leader.name} ({leader.section_text}): {flag['reason']}", 10)
        gaps = self.roster_summary().get("gaps", [])
        gap_count = Counter((g["store"], g["department"]) for g in gaps)
        for (store_name, dept), n in gap_count.most_common(5):
            add("Low", "Roster", store_name, f"{dept}: all leaders off on {n} day(s) this month", n)
        order = {"High": 0, "Medium": 1, "Low": 2}
        out.sort(key=lambda a: (order[a["severity"]], -a["weight"]))
        return out[:limit] if limit else out

    # ------------------------------------------------------- headlines --

    def headline(self) -> dict[str, Any]:
        cards = self.store_scorecard()
        sales = sum(c["sales"] for c in cards if c.get("sales") is not None)
        budget = sum(c["budget"] for c in cards if c.get("budget") is not None and c.get("sales") is not None)
        ly = 0.0
        ly_ok = True
        for c in cards:
            total = self.sales_total(c["store"])
            if total and total.get("last_year") is not None:
                ly += total["last_year"]
            elif c.get("sales") is not None:
                ly_ok = False
        prod = [c["productivity_vs_target_pct"] for c in cards if c.get("productivity_vs_target_pct") is not None]
        leaders = self.leaders()
        rated = [l.latest_rating for l in leaders if l.latest_rating is not None]
        turnover = self.turnover_summary() if self.has("po_turnover") else None
        return {
            "stores": len(cards),
            "sales": sales if self.has("po_sales") else None,
            "sales_vs_budget_pct": _pct(sales, budget) if budget else None,
            "growth_pct": _pct(sales - ly, ly) if ly and ly_ok else None,
            "productivity_vs_target_pct": _mean(prod),
            "stores_on_track": sum(1 for c in cards if c["status"] == "On track"),
            "stores_at_risk": sum(1 for c in cards if c["status"] == "At risk"),
            "leaders": len(leaders),
            "avg_rating": _mean(rated),
            "leavers_12m": turnover["total"] if turnover else None,
            "voluntary_pct": turnover["voluntary_pct"] if turnover else None,
            "da_cases": sum(int(r.get("count") or 0) for r in self.rows("po_da")) if self.has("po_da") else None,
            "headcount": self.headcount(),
            "as_of": self.as_of,
        }
