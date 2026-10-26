"""Data health: is everything for a month in, and can the numbers be trusted?

* checklist - every report P&O expects, with its status for the month: in, worked out from other periods, only an
  older period, or missing; general data (employee master, time in role, ratings) with its age.
* checks    - reconciliation across tabs (leavers still on the Basic Sheet, leaders missing from it, duplicate IDs),
  unconfirmed store names, conflicting files for the same period, report totals that do not add up, outliers.
* score     - 100 minus points per problem, so a month can be called ready before it is presented.
* locks     - a presented month can be locked so later imports cannot change it silently.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

from .period import label as period_label, month_label
from .po import derive

EXPECTED: list[tuple[str, str, str]] = [
    ("roster", "Basic Sheet · employee master", "general"),
    ("po_role", "Time in role", "general"),
    ("po_rating", "Performance ratings", "general"),
    ("attendance", "Biometric attendance", "month"),
    ("sales", "Store sales", "period"),
    ("productivity", "Section productivity", "period"),
    ("po_shrink", "Shrinkage & stock days", "period"),
    ("po_nps", "Customer NPS", "period"),
    ("po_da", "Disciplinary actions", "period"),
    ("po_turnover", "Turnover", "dated"),
    ("po_shift", "Shift roster", "dated"),
    ("leave", "Leave register", "month"),
]
STALE_DAYS = 45

# what every figure means, where it comes from and how it behaves across periods
MEASURES: list[dict[str, str]] = [
    {"name": "Sales vs budget", "formula": "Actual sales ÷ budget × 100", "source": "Store sales", "periods": "Adds up: MTD can be worked out from two YTD files"},
    {"name": "Growth vs last year", "formula": "(Actual ÷ last year − 1) × 100", "source": "Store sales", "periods": "Re-calculated from the parts for any period"},
    {"name": "Productivity vs target", "formula": "Sales per labour hour ÷ target − 1", "source": "Section productivity", "periods": "Ratio: needs that period's own file"},
    {"name": "Shrinkage vs budget", "formula": "Shrink % actual − shrink % budget (pp)", "source": "Shrinkage & stock days", "periods": "Ratio: needs that period's own file"},
    {"name": "Stock days", "formula": "Average stock ÷ daily cost of sales", "source": "Shrinkage & stock days", "periods": "Ratio: needs that period's own file"},
    {"name": "Out of stock", "formula": "Items out of stock ÷ items listed × 100", "source": "Store sales", "periods": "Ratio: needs that period's own file"},
    {"name": "Customer NPS", "formula": "% promoters − % detractors (−100 to +100)", "source": "Customer NPS", "periods": "Score: needs that period's own file"},
    {"name": "Leavers", "formula": "Exits dated inside the period", "source": "Turnover", "periods": "Cut from the rows' own dates for any period"},
    {"name": "Turnover rate (yearly)", "formula": "Leavers × 12 ÷ months in period ÷ headcount × 100", "source": "Turnover + Basic Sheet", "periods": "Annualised, so MTD and YTD compare"},
    {"name": "Disciplinary cases", "formula": "Count of DA cases", "source": "Disciplinary actions", "periods": "Adds up: MTD can be worked out from two YTD files"},
    {"name": "Headcount", "formula": "People on the Basic Sheet", "source": "Basic Sheet", "periods": "General: applies to every period"},
    {"name": "Time in role", "formula": "Months since the role start date", "source": "Time in role", "periods": "General, measured to the period end"},
    {"name": "Leader index /10", "formula": "Weighted mix of sales, productivity, shrinkage, stock days, rating, retention", "source": "Several tabs", "periods": "Uses each tab's figure for the period chosen"},
    {"name": "Person score /10", "formula": "What the person controls vs target (7 = met, 10 = clearly beat)", "source": "Roster, attendance, sales, productivity", "periods": "Monthly"},
    {"name": "Real absence", "formula": "Absent days excluding weekly offs, holidays and booked leave", "source": "Attendance + leave", "periods": "Monthly, by day"},
]


def _age(created: str | None) -> int | None:
    try:
        return (date.today() - datetime.fromisoformat(str(created)[:19]).date()).days
    except (TypeError, ValueError):
        return None


def locked_months(db) -> list[str]:
    return sorted(set(db.get_setting("locked_months", []) or []))


def set_lock(db, month: str, locked: bool) -> list[str]:
    months = set(locked_months(db))
    (months.add if locked else months.discard)(month)
    db.set_setting("locked_months", sorted(months))
    db.log("lock month" if locked else "unlock month", month)
    return sorted(months)


def months_known(db) -> list[str]:
    ms = set()
    for r in db.q("SELECT period_to, month FROM imports WHERE active=1 AND COALESCE(period_type,'') != 'general'"):
        m = r["period_to"] or r["month"]
        if m and len(m) == 7:
            ms.add(m)
    return sorted(ms)


def checklist(db, month: str) -> list[dict[str, Any]]:
    rows = [dict(r) for r in db.q("SELECT * FROM imports WHERE active=1 ORDER BY id")]
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_kind[r["kind"]].append(r)
    out = []
    for kind, name, how in EXPECTED:
        imps = by_kind.get(kind, [])
        item = {"kind": kind, "name": name, "status": "missing", "label": "", "age": None, "detail": ""}
        if how == "general":
            if imps:
                last = imps[-1]
                age = _age(last["created_at"])
                item.update(status="stale" if age is not None and age > STALE_DAYS else "ok", label="General · every period",
                            age=age, detail=f"{last['file_name']} · imported {age} day{'s' if age != 1 else ''} ago" if age is not None else last["file_name"])
        elif how == "month":
            hit = [i for i in imps if (i["month"] or i["period_to"]) == month]
            if hit:
                item.update(status="ok", label=f"{month_label(month)}", detail=hit[-1]["file_name"], age=_age(hit[-1]["created_at"]))
        else:
            def covers(i):
                f, t = i["period_from"] or i["month"], i["period_to"] or i["month"]
                return bool(f and t and f <= month <= t) if how == "dated" else t == month
            hit = [i for i in imps if covers(i)]
            if hit:
                last = hit[-1]
                item.update(status="ok", label=period_label(last["period_type"], last["period_from"], last["period_to"]) if last["period_type"] else month_label(month),
                            detail=last["file_name"], age=_age(last["created_at"]))
            else:
                prev = [i for i in imps if (i["period_to"] or i["month"] or "") < month]
                ytd_prev = [i for i in imps if i["period_type"] == "ytd" and i["period_to"] == derive.month_add(month, -1)]
                if kind in ("sales", "po_da") and ytd_prev and any(i["period_type"] == "ytd" and i["period_to"] == month for i in imps):
                    item.update(status="derived")
                elif prev:
                    last = max(prev, key=lambda i: (i["period_to"] or i["month"] or "", i["id"]))
                    lab = period_label(last["period_type"], last["period_from"], last["period_to"]) if last["period_type"] else (last["month"] or "")
                    item.update(status="older", label=lab, detail=f"latest is {lab}")
        out.append(item)
    return out


def checks(db, ins, month: str) -> list[dict[str, Any]]:
    """Problems worth fixing before the numbers are presented, biggest first."""
    out: list[dict[str, Any]] = []

    def add(level: str, area: str, message: str, count: int = 0, go: str = "", tab: str = "", items: list | None = None):
        out.append({"level": level, "area": area, "message": message, "count": count, "go": go, "tab": tab,
                    "items": (items or [])[:12]})

    unsure = db.q("SELECT raw, source FROM store_aliases WHERE confirmed=0")
    if unsure:
        add("warn", "Stores", f"{len(unsure)} store name{'s' if len(unsure) > 1 else ''} matched with less certainty: confirm them.",
            len(unsure), "settings", "stores", [f"{r['raw']} ({r['source']})" for r in unsure])

    master = ins.rows("po_master")
    master_ids = Counter(str(r.get("employee_id") or "") for r in master if r.get("employee_id"))
    dup = [k for k, n in master_ids.items() if n > 1]
    if dup:
        add("bad", "People", f"{len(dup)} employee number{'s' if len(dup) > 1 else ''} appear more than once on the Basic Sheet.",
            len(dup), "import", "", dup)
    if master:
        names = {str(r.get("employee_id")): r.get("employee_name") for r in master}
        left = {}
        for r in ins._full.get("po_turnover") or ins.rows("po_turnover"):
            e = str(r.get("employee_id") or "")
            if e and e in names:
                left[e] = f"{r.get('employee_name')} · left {r.get('date')}"
        if left:
            add("warn", "People", f"{len(left)} leaver{'s' if len(left) > 1 else ''} still on the Basic Sheet: the employee master may be "
                "older than the turnover tab.", len(left), "retention", "", list(left.values()))
        missing_role = [f"{r.get('employee_name')} · {r.get('store') or 'store not given'}" for r in ins.rows("po_role")
                        if r.get("employee_id") and str(r["employee_id"]) not in names]
        if missing_role:
            add("info", "People", f"{len(missing_role)} leader{'s' if len(missing_role) > 1 else ''} in Time in role are not on the Basic Sheet.",
                len(missing_role), "talent", "", missing_role)
        shift_ids = {str(r.get("employee_id")): r for r in ins.rows("po_shift") if r.get("employee_id")}
        not_master = [f"{r.get('employee_name')} · {r.get('store')}" for e, r in shift_ids.items() if e not in names]
        if not_master:
            add("info", "People", f"{len(not_master)} people on the shift roster are not on the Basic Sheet.", len(not_master),
                "shifts", "", not_master)
    no_id = [r.get("employee_name") for r in ins.rows("po_role") if not r.get("employee_id")]
    if no_id:
        add("info", "People", f"{len(no_id)} leader{'s' if len(no_id) > 1 else ''} without an employee number yet (new joiners?).",
            len(no_id), "talent", "", no_id)
    unknown = sorted({r.get("store") for k in ("po_shift", "po_role", "po_master") for r in ins.rows(k)
                      if r.get("store") and r.get("store") not in set(ins.stores(include_myli=True))} - {""})
    if unknown:
        add("warn", "Stores", f"{len(unknown)} store name{'s' if len(unknown) > 1 else ''} not recognised: {', '.join(unknown[:5])}.",
            len(unknown), "settings", "stores", unknown)

    # conflicting files for the same report and period
    seen: dict[tuple, list] = defaultdict(list)
    for r in db.q("SELECT id, kind, file_name, file_hash, period_type, period_from, period_to, month FROM imports WHERE active=1"):
        if r["kind"] in ("attendance", "leave", "dataset", "holiday", "manual"):
            continue
        seen[(r["kind"], r["period_type"], r["period_from"], r["period_to"] or r["month"])].append(r)
    for (kind, pt, pf, pto), group in seen.items():
        if len({g["file_hash"] for g in group}) > 1:
            lab = period_label(pt, pf, pto) if pt else (pto or "")
            add("warn", "Files", f"{len(group)} different {kind.replace('po_', '').replace('_', ' ')} files for {lab}: the newest is used. "
                "Undo the wrong one on the Import screen.", len(group), "import", "", [g["file_name"] for g in group])

    # report totals: store total vs sum of its sections
    bad_totals = []
    sales = ins.rows("po_sales")
    for store in {r["store"] for r in sales}:
        rows = [r for r in sales if r["store"] == store]
        total = next((r for r in rows if r.get("line") in ("Total Store", "Total")), None)
        parts = sum(r.get("actual") or 0 for r in rows if r.get("level") == "section")
        if total and total.get("actual") and parts and abs(parts - total["actual"]) / abs(total["actual"]) > 0.02:
            bad_totals.append(f"{store}: sections {parts:,.0f} vs total {total['actual']:,.0f}")
    if bad_totals:
        add("info", "Totals", f"Sales sections do not add up to the store total in {len(bad_totals)} store"
            f"{'s' if len(bad_totals) > 1 else ''} (some lines may be missing from the report).", len(bad_totals), "review", "", bad_totals)

    # outliers: productivity far from the same section elsewhere
    by_sec: dict[str, list] = defaultdict(list)
    for r in ins.rows("po_productivity"):
        if isinstance(r.get("productivity"), (int, float)) and r.get("section"):
            by_sec[r["section"]].append(r)
    odd = []
    for sec, rs in by_sec.items():
        vals = [r["productivity"] for r in rs]
        if len(vals) >= 4:
            med = statistics.median(vals)
            for r in rs:
                if med and (r["productivity"] > 5 * med or r["productivity"] < med / 5):
                    odd.append(f"{r['store']} · {sec}: {r['productivity']:,.1f} (others ≈ {med:,.1f})")
    if odd:
        add("warn", "Outliers", f"{len(odd)} productivity figure{'s' if len(odd) > 1 else ''} look out of line (decimal or unit error?).",
            len(odd), "review", "", odd)

    for c in checklist(db, month):
        if c["status"] == "stale":
            add("info", "Freshness", f"{c['name']} was imported {c['age']} days ago: import the latest one.", 1, "import")
    order = {"bad": 0, "warn": 1, "info": 2}
    return sorted(out, key=lambda c: (order[c["level"]], -c["count"]))


def score(items: list[dict], found: list[dict]) -> int:
    pts = 100
    for c in items:
        pts -= {"missing": 6, "older": 3, "stale": 2, "derived": 0, "ok": 0}[c["status"]]
    for f in found:
        pts -= {"bad": 8, "warn": 4, "info": 1}[f["level"]]
    return max(0, min(100, pts))


def report(db, ins, month: str | None = None) -> dict[str, Any]:
    months = months_known(db)
    default = ins.available.get("default_to") if hasattr(ins, "available") else None
    month = month if month and len(month) == 7 else (default or (months[-1] if months else date.today().strftime("%Y-%m")))
    items = checklist(db, month)
    found = checks(db, ins, month)
    s = score(items, found)
    ready = sum(1 for c in items if c["status"] in ("ok", "derived"))
    return {"month": month, "month_label": month_label(month), "months": [{"value": m, "label": month_label(m)} for m in months],
            "checklist": items, "checks": found, "score": s, "ready": ready, "expected": len(items),
            "locked": month in locked_months(db), "locked_months": locked_months(db), "measures": MEASURES,
            "verdict": "Ready to present" if s >= 85 else "Usable, with gaps" if s >= 60 else "Needs data"}


def lock_message(db, kind: str, ptype: str, pto: str | None, month: str | None) -> str | None:
    """Why an import would change a locked month, or None."""
    if ptype == "general":
        return None
    m = pto or month
    if m and m in locked_months(db):
        return (f"{month_label(m)} is locked (already presented). Unlock it on the Data health screen to change it.")
    return None

