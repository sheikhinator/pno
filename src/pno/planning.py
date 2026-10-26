"""2.4: training needs analysis (weak measures → courses) and the workforce forecast / what-if simulator."""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from .learning import library

COMPONENT_LABEL = {"sales": "Sales vs budget", "productivity": "Productivity", "shrink": "Shrinkage", "stock_days": "Stock days",
                   "rating": "Performance rating", "retention": "Keeping people", "absence": "Attendance", "nps": "Customer NPS", "oos": "Availability"}


# ---------------------------------------------------------------------------------------------- training needs
def training_needs(db, ins, threshold: float = 60) -> dict[str, Any]:
    """Every leader's weak measures turned into learning topics, with what is already assigned or done."""
    from .po import canon
    from .po.format import leader_name
    done: dict[str, set[str]] = defaultdict(set)          # person -> topics covered by an assigned course
    status: dict[tuple[str, str], str] = {}
    for a in db.q("SELECT a.person, a.status, c.content FROM assignments a JOIN courses c ON c.id=a.course_id"):
        try:
            content = json.loads(a["content"] or "{}")
            topics = content.get("topics") or [m.get("key") for m in content.get("modules", []) if m.get("key")]
        except ValueError:
            topics = []
        for t in topics:
            done[str(a["person"])].add(t)
            if status.get((str(a["person"]), t)) != "completed":
                status[(str(a["person"]), t)] = a["status"]
    rows, demand = [], defaultdict(list)
    for l in ins.leaders():
        weak = sorted(((k, v) for k, v in l.components.items() if v is not None and v < threshold and k in library.KPI_TOPIC), key=lambda kv: kv[1])
        if not weak:
            continue
        pid = str(l.employee_id or l.key)
        level = min(6, max(1, canon.role_rank(l.designation) or 2))
        needs = []
        for k, v in weak:
            t = library.KPI_TOPIC[k]
            st = status.get((pid, t))
            needs.append({"measure": COMPONENT_LABEL.get(k, k), "score": round(v / 10, 1), "topic": t, "topic_title": library.TOPICS[t]["title"],
                          "status": st or "not assigned"})
            if not st:
                demand[t].append({"person": pid, "name": leader_name(l), "store": l.store, "level": 4 if level == 5 else level})
        rows.append({"key": l.key, "person": pid, "name": leader_name(l), "store": l.store or "", "role": l.designation or "", "index": l.score,
                     "needs": needs, "open": sum(1 for n in needs if n["status"] == "not assigned")})
    rows.sort(key=lambda r: (-r["open"], r["index"] or 0))
    topics = []
    for t, people in sorted(demand.items(), key=lambda kv: -len(kv[1])):
        lv = Counter(p["level"] for p in people).most_common(1)[0][0]
        topics.append({"topic": t, "title": library.TOPICS[t]["title"], "people": people, "n": len(people), "level": lv,
                       "stores": sorted({p["store"] for p in people if p["store"]})})
    return {"rows": rows, "topics": topics, "threshold": threshold, "leaders_with_needs": len(rows),
            "open_needs": sum(r["open"] for r in rows), "covered": sum(len(r["needs"]) - r["open"] for r in rows)}


def build_for_topic(api, topic: str, people: list[dict], hours: float = 3, due: str | None = None) -> dict:
    """One course for a topic, assigned to everyone who needs it."""
    if topic not in library.TOPICS:
        raise ValueError("Unknown topic.")
    if not people:
        raise ValueError("Nobody needs this topic.")
    lv = Counter(int(p.get("level") or 2) for p in people).most_common(1)[0][0]
    L = api.learning
    c = L.build(title=f"{library.TOPICS[topic]['title']} · targeted training", level=lv, topics=[topic], hours=float(hours), lecture_min=20)
    L.assign(c["id"], [{"person": p["person"], "name": p.get("name", ""), "store": p.get("store", "")} for p in people], due)
    return {"course_id": c["id"], "assigned": len(people), "title": c.get("title") or library.TOPICS[topic]["title"]}


# ---------------------------------------------------------------------------------------------- forecast
def _months_ahead(start: date, n: int) -> list[str]:
    out, y, m = [], start.year, start.month
    for _ in range(n):
        m += 1
        if m > 12:
            y, m = y + 1, 1
        out.append(f"{y}-{m:02d}")
    return out


def baseline(db, ins) -> dict[str, Any]:
    """Today's headcount, the monthly leaver rate over the last 12 months, approved heads and open vacancies."""
    from .po.insights import _parse
    head = len(ins.rows("po_master")) if ins.has("po_master") else 0
    try:
        from . import engine, analytics
        ms = analytics.month_list(db)
        if ms:
            mm = engine.model(db, ms[0]["value"])
            head = max(head, len(mm.people))
    except Exception:  # noqa: BLE001
        pass
    by_month: Counter = Counter()
    for r in ins.leavers(months=12):
        d = _parse(r.get("date"))
        if d:
            by_month[f"{d.year}-{d.month:02d}"] += 1
    months = sorted(by_month)[-12:]
    per_month = round(statistics.mean(by_month[m] for m in months), 1) if months else 0.0
    vol = Counter((r.get("type") or r.get("exit_type") or "").lower() for r in ins.leavers(months=12))
    resign = sum(v for k, v in vol.items() if "resign" in k)
    total = sum(vol.values()) or 1
    approved = db.q1("SELECT COALESCE(SUM(approved), 0) FROM manning")[0]
    open_v = db.q1("SELECT COALESCE(SUM(headcount), 0) FROM vacancies WHERE status='open'")[0]
    cost = float(db.get_setting("replacement_cost", 60000) or 60000)
    return {"headcount": head, "leavers_per_month": per_month, "monthly": [{"month": m, "leavers": by_month[m]} for m in months],
            "annual_rate": round(100 * per_month * 12 / head, 1) if head else None, "voluntary_share": round(100 * resign / total),
            "approved": approved or None, "open_vacancies": open_v, "replacement_cost": cost, "as_of": ins.as_of.isoformat() if ins.as_of else None}


def forecast(db, ins, months: int = 6, turnover_change: float = 0, hires_per_month: float | None = None, growth_heads: int = 0,
             replacement_cost: float | None = None) -> dict[str, Any]:
    """Project headcount month by month: today's trend vs a scenario (turnover change %, hiring pace, new heads)."""
    b = baseline(db, ins)
    if replacement_cost:
        db.set_setting("replacement_cost", float(replacement_cost))
        b["replacement_cost"] = float(replacement_cost)
    months = max(1, min(24, int(months)))
    start = ins.as_of or date.today()
    labels = _months_ahead(start, months)
    lv = b["leavers_per_month"]
    hire_base = lv                                          # today: roughly replace who leaves
    lv_s = max(0.0, lv * (1 + float(turnover_change) / 100))
    hire_s = float(hires_per_month) if hires_per_month not in (None, "") else lv_s
    base_line, scen, gap = [], [], []
    h0 = hs = float(b["headcount"])
    add_each = float(growth_heads or 0) / months
    for _ in labels:
        h0 += hire_base - lv
        hs += hire_s - lv_s - 0 + 0
        base_line.append(round(h0))
        scen.append(round(hs))
    target = [round(b["headcount"] + add_each * (i + 1)) for i in range(months)] if growth_heads else None
    if b["approved"]:
        gap = [s - b["approved"] for s in scen]
    leavers_base, leavers_s = lv * months, lv_s * months
    cost = b["replacement_cost"]
    hires_needed = max(0.0, (b["approved"] or b["headcount"] + (growth_heads or 0)) - b["headcount"]) + leavers_s
    return {"baseline": b, "labels": labels, "series": {"today": base_line, "scenario": scen, "target": target},
            "gap_to_approved": gap or None, "scenario": {"turnover_change": turnover_change, "hires_per_month": round(hire_s, 1), "leavers_per_month": round(lv_s, 1),
                                                        "growth_heads": growth_heads, "months": months},
            "leavers": {"today": round(leavers_base), "scenario": round(leavers_s)},
            "cost": {"today": round(leavers_base * cost), "scenario": round(leavers_s * cost), "saving": round((leavers_base - leavers_s) * cost)},
            "hires_needed": round(hires_needed), "hires_per_month_needed": round(hires_needed / months, 1)}
