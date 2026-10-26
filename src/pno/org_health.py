"""Organisation health: what changed between Basic Sheets, span of control, probation, rating calibration and fairness,
and ready-to-send requests for missing reports."""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from .period import month_label
from .po import canon


def _master_of(db, import_id: int) -> dict[str, dict]:
    out = {}
    for r in db.q("SELECT payload FROM po_records WHERE import_id=? AND kind='po_master'", (import_id,)):
        rec = json.loads(r[0])
        if rec.get("employee_id"):
            out[str(rec["employee_id"])] = rec
    return out


def changes(db) -> dict[str, Any]:
    """Joiners, leavers, transfers, role and manager changes between the two latest Basic Sheet (roster) imports."""
    imps = db.q("SELECT id, file_name, created_at, as_of FROM imports WHERE kind='roster' ORDER BY id DESC LIMIT 2")
    if len(imps) < 2:
        return {"has_data": False, "note": "Import a second Basic Sheet (next month's) to see who joined, left, moved or changed role."}
    new, old = _master_of(db, imps[0]["id"]), _master_of(db, imps[1]["id"])
    if not new or not old:
        return {"has_data": False, "note": "The last two Basic Sheets have no employee codes to compare."}
    same = len(new.keys() & old.keys())
    if same < 0.5 * min(len(new), len(old)):
        return {"has_data": False, "note": f"The last two Basic Sheets cover different people ({imps[1]['file_name']}: {len(old)}, "
                f"{imps[0]['file_name']}: {len(new)}, only {same} in both), so they can't be compared. Import next month's version of the same sheet."}
    joiners = [new[k] for k in new.keys() - old.keys()]
    leavers = [old[k] for k in old.keys() - new.keys()]
    transfers, roles, managers = [], [], []
    for k in new.keys() & old.keys():
        a, b = old[k], new[k]
        if (a.get("store") or "") != (b.get("store") or ""):
            transfers.append({"name": b["employee_name"], "from": a.get("store"), "to": b.get("store"), "role": b.get("designation")})
        if canon.text(a.get("designation")).lower() != canon.text(b.get("designation")).lower():
            up = canon.role_rank(b.get("designation")) > canon.role_rank(a.get("designation"))
            roles.append({"name": b["employee_name"], "from": a.get("designation"), "to": b.get("designation"), "store": b.get("store"),
                          "promotion": up})
        if canon.name_key(a.get("manager_name") or "") != canon.name_key(b.get("manager_name") or "") and b.get("manager_name"):
            managers.append({"name": b["employee_name"], "from": a.get("manager_name"), "to": b.get("manager_name"), "store": b.get("store")})
    left_turnover = set()
    for r in db.q("SELECT r.payload FROM po_records r JOIN imports i ON i.id=r.import_id WHERE i.active=1 AND r.kind='po_turnover'"):
        e = json.loads(r[0]).get("employee_id")
        if e:
            left_turnover.add(str(e))
    unexplained = [l for l in leavers if str(l.get("employee_id")) not in left_turnover]
    fmt = lambda r: {"name": r.get("employee_name"), "store": r.get("store"), "role": r.get("designation"), "id": r.get("employee_id")}  # noqa: E731
    return {"has_data": True, "from": imps[1]["file_name"], "to": imps[0]["file_name"], "from_date": (imps[1]["as_of"] or imps[1]["created_at"] or "")[:10],
            "to_date": (imps[0]["as_of"] or imps[0]["created_at"] or "")[:10], "joiners": [fmt(r) for r in joiners], "leavers": [fmt(r) for r in leavers],
            "unexplained_leavers": [fmt(r) for r in unexplained], "transfers": transfers, "roles": roles, "managers": managers,
            "promotions": sum(1 for r in roles if r["promotion"]), "headcount_old": len(old), "headcount_new": len(new)}


def span_of_control(ins) -> dict[str, Any]:
    master = ins.rows("po_master")
    by_id = {str(r.get("employee_id")): r for r in master}
    reports: dict[str, list] = defaultdict(list)
    for r in master:
        m = str(r.get("manager_id") or "") or canon.name_key(r.get("manager_name") or "")
        if m:
            reports[m].append(r)
    rows = []
    for m, team in reports.items():
        boss = by_id.get(m)
        name = boss["employee_name"] if boss else next((t.get("manager_name") for t in team if t.get("manager_name")), m)
        n = len(team)
        flag = "Too wide" if n > 15 else "Very narrow" if n < 2 else ""
        rows.append({"manager": canon.repair_name(name), "role": (boss or {}).get("designation") or "", "store": (boss or team[0]).get("store") or "",
                     "direct_reports": n, "flag": flag})
    rows.sort(key=lambda r: -r["direct_reports"])
    sizes = [r["direct_reports"] for r in rows]
    return {"rows": rows, "managers": len(rows), "avg": round(statistics.mean(sizes), 1) if sizes else None,
            "median": statistics.median(sizes) if sizes else None, "too_wide": sum(1 for r in rows if r["flag"] == "Too wide"),
            "narrow": sum(1 for r in rows if r["flag"] == "Very narrow")}


def probation(ins, months: int = 3) -> dict[str, Any]:
    """People still in (or just past) probation, from joining dates on the Basic Sheet."""
    today = date.today()
    out = []
    for r in ins.rows("po_master"):
        try:
            j = date.fromisoformat(str(r.get("joining_date"))[:10])
        except (TypeError, ValueError):
            continue
        y, m = divmod(j.month - 1 + months, 12)
        end = date(j.year + y, m + 1, min(j.day, 28))
        days = (end - today).days
        if -30 <= days <= 60:
            out.append({"name": r.get("employee_name"), "store": r.get("store"), "role": r.get("designation"), "joined": j.isoformat(),
                        "ends": end.isoformat(), "days": days, "status": "Ended: confirm or extend" if days < 0 else "Ends within 30 days" if days <= 30 else "Ends in 31–60 days"})
    out.sort(key=lambda r: r["days"])
    return {"rows": out, "months": months, "due_30": sum(1 for r in out if 0 <= r["days"] <= 30), "overdue": sum(1 for r in out if r["days"] < 0)}


def calibration(ins) -> dict[str, Any]:
    """How ratings are spread, by store and by manager, and whether they differ by gender (a fairness check)."""
    master = {str(r.get("employee_id")): r for r in ins.rows("po_master")}
    latest: dict[str, dict] = {}
    for r in ins.rows("po_rating"):
        if r.get("rating") is None:
            continue
        k = str(r.get("employee_id") or r.get("employee_name"))
        if k not in latest or (r.get("cycle") or 0) >= (latest[k].get("cycle") or 0):
            latest[k] = r
    rated = list(latest.values())
    if not rated:
        return {"has_data": False}
    dist = Counter(round(float(r["rating"])) for r in rated)
    overall = statistics.mean(float(r["rating"]) for r in rated)

    def group(key):
        g: dict[str, list[float]] = defaultdict(list)
        for r in rated:
            v = key(r)
            if v:
                g[v].append(float(r["rating"]))
        return [{"name": k, "n": len(v), "avg": round(statistics.mean(v), 2), "share_top": round(100 * sum(1 for x in v if x >= 4) / len(v)),
                 "gap": round(statistics.mean(v) - overall, 2)} for k, v in sorted(g.items(), key=lambda kv: -statistics.mean(kv[1]))]
    by_store = group(lambda r: r.get("store"))
    by_manager = [m for m in group(lambda r: canon.repair_name(r.get("manager_name")) if r.get("manager_name") else None) if m["n"] >= 3]
    gender = group(lambda r: (master.get(str(r.get("employee_id"))) or {}).get("gender") or r.get("gender"))
    flags = []
    for m in by_manager:
        if abs(m["gap"]) >= 0.6:
            flags.append(f"{m['name']} rates {'higher' if m['gap'] > 0 else 'lower'} than average ({m['avg']} vs {overall:.2f}, {m['n']} people): check calibration.")
    if len(gender) >= 2:
        hi, lo = gender[0], gender[-1]
        if hi["n"] >= 3 and lo["n"] >= 3 and hi["avg"] - lo["avg"] >= 0.4:
            flags.append(f"Average rating differs by gender ({hi['name']} {hi['avg']} vs {lo['name']} {lo['avg']}): review for bias before final ratings.")
    top_share = round(100 * sum(1 for r in rated if float(r["rating"]) >= 4) / len(rated))
    if top_share >= 50:
        flags.append(f"{top_share}% are rated 4 or 5: ratings may be inflated.")
    return {"has_data": True, "n": len(rated), "avg": round(overall, 2), "distribution": [{"rating": k, "count": dist.get(k, 0)} for k in range(1, 6)],
            "by_store": by_store, "by_manager": by_manager, "by_gender": gender, "flags": flags, "top_share": top_share}


def request_message(db, month: str, missing: list[str], lang: str = "en") -> str:
    m = month_label(month)
    if lang == "ur":
        lines = [f"السلام علیکم،", "", f"{m} کی P&O رپورٹ مکمل کرنے کے لیے درج ذیل فائلیں درکار ہیں:"] + [f"• {x}" for x in missing] + \
                ["", "براہ کرم اصل ایکسل فائلیں جلد از جلد بھیج دیں۔", "", "شکریہ،", "پیپل اینڈ آرگنائزیشن"]
    else:
        lines = ["Dear team,", "", f"To complete the P&O review for {m}, please share the following reports:"] + [f"• {x}" for x in missing] + \
                ["", "Please send the original Excel files (not screenshots) by end of day.", "", "Thank you,", "People & Organisation"]
    return "\n".join(lines)


def report(db, ins) -> dict[str, Any]:
    return {"changes": changes(db), "span": span_of_control(ins), "probation": probation(ins, int(db.get_setting("probation_months", 3) or 3)),
            "calibration": calibration(ins), "headcount": ins.headcount() or 0}

