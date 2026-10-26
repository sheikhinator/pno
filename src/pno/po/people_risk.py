"""Flight risk and succession, from the P&O workbook data already in P&O.

Flight risk is a transparent points model, not a black box: each signal adds points and is listed as a reason, so a
director can see why someone is flagged and judge it. Signals: new in the company or role, long time in role without a
move, low or missing rating, people leaving their section, disciplinary cases in their section, acting in a role
without the title, heavy evening/weekend load, store with high turnover.

Succession looks one level below each leadership role in the same store (and the same area where possible) and marks
the role Ready now / Ready in a year / No successor.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from . import canon

LEVEL_ROLES = {6: "Store manager", 5: "Deputy store manager", 4: "Department head", 3: "Section manager", 2: "Team leader"}


def _band(score: float) -> str:
    return "High" if score >= 55 else "Medium" if score >= 35 else "Low"


def flight_risk(ins) -> list[dict[str, Any]]:
    leaders = ins.leaders()
    turnover = ins.rows("po_turnover")
    store_leavers = Counter(r.get("store") for r in ins.leavers())
    heads = {s: ins.headcount(s) or 0 for s in {l.store for l in leaders if l.store}}
    out = []
    for l in leaders:
        pts, why = 0.0, []
        if l.months_service is not None and l.months_service < 12:
            pts += 15
            why.append(f"In the company {l.months_service} months (first year is the riskiest)")
        if l.months_in_role is not None:
            if l.months_in_role < 6:
                pts += 8
                why.append(f"New in role ({l.months_in_role} months)")
            elif l.months_in_role >= 36:
                pts += 18
                why.append(f"{l.months_in_role // 12} years in the same role without a move")
            elif l.months_in_role >= 24:
                pts += 9
                why.append("2+ years in the same role")
        rating = l.latest_rating
        if rating is None:
            pts += 6 if l.ratings else 4
            why.append("No rating on file" if not l.ratings else "Last appraisal unrated")
        elif rating <= 2:
            pts += 14
            why.append(f"Low rating ({rating})")
        elif rating >= 4 and (l.months_in_role or 0) >= 24:
            pts += 12
            why.append(f"Strong rating ({rating}) but no move for {l.months_in_role // 12}+ years: may look outside")
        lv = l.kpis.get("leavers")
        if lv:
            pts += min(20, lv * 4)
            why.append(f"{lv} people left their {'store' if l.whole_store else 'section'} ({ins.leaver_window})")
        da = l.kpis.get("da")
        if da:
            pts += min(10, da * 2)
            why.append(f"{da} disciplinary case{'s' if da > 1 else ''} in their area")
        if l.acting or l.designation_mismatch:
            pts += 10
            why.append("Doing the role without the title in the HR system" if l.designation_mismatch else "Acting in the role")
        evenings = l.shifts.get("Evening", 0)
        worked = sum(v for k, v in l.shifts.items() if k not in ("Off", "Leave", "Not rostered"))
        offs = l.shifts.get("Off", 0)
        if worked >= 10 and evenings / worked >= 0.6:
            pts += 6
            why.append(f"Mostly evening shifts ({evenings} of {worked})")
        if worked >= 24 and offs <= 2:
            pts += 6
            why.append(f"Only {offs} day{'s' if offs != 1 else ''} off in the roster month")
        st_rate = store_leavers.get(l.store, 0) / heads[l.store] * 100 if heads.get(l.store) else None
        if st_rate and st_rate >= 25:
            pts += 5
            why.append(f"Store turnover is high ({st_rate:.0f}% of headcount left)")
        score = min(100.0, pts)
        if score <= 0 and not why:
            why.append("No risk signals in the data")
        from .format import leader_name
        out.append({"key": l.key, "name": leader_name(l), "store": l.store or "—", "role": l.designation or "—", "leads": l.section_text,
                    "score": round(score), "band": _band(score), "reasons": why, "index": l.score, "rating": rating,
                    "in_role_months": l.months_in_role, "service_months": l.months_service})
    _ = turnover
    return sorted(out, key=lambda r: -r["score"])


def succession(ins) -> dict[str, Any]:
    """For each leadership role in each store: the incumbents and their best successors one level below."""
    from .format import leader_name
    leaders = ins.leaders()
    by_store: dict[str, list] = defaultdict(list)
    for l in leaders:
        if l.store:
            by_store[l.store].append(l)
    roles = [6, 4, 3]
    rows, cells = [], []
    for store in ins.stores():
        ls = by_store.get(store, [])
        for lvl in roles:
            holders = [l for l in ls if _level(l) == lvl or (lvl == 6 and _level(l) == 5 and not any(_level(x) == 6 for x in ls))]
            below = [l for l in ls if _level(l) == lvl - 1 or (lvl == 6 and _level(l) == 4) or (lvl == 4 and _level(l) == 3) or (lvl == 3 and _level(l) == 2)]
            below = list({id(x): x for x in below}.values())
            ranked = sorted(below, key=lambda x: -_readiness(x))
            best = ranked[0] if ranked else None
            ready = _ready(best) if best else "No successor"
            cell = {"store": store, "role": LEVEL_ROLES[lvl], "level": lvl, "holders": [leader_name(h) for h in holders][:4],
                    "status": ready if holders or ranked else "No one in role",
                    "successors": [{"name": leader_name(x), "role": x.designation, "leads": x.section_text, "ready": _ready(x),
                                    "index": x.score, "rating": x.latest_rating, "in_role_months": x.months_in_role} for x in ranked[:3]]}
            cells.append(cell)
        rows.append(store)
    summary = Counter(c["status"] for c in cells)
    return {"stores": rows, "roles": [LEVEL_ROLES[r] for r in roles], "cells": cells, "summary": dict(summary)}


def _level(l) -> int:
    r = canon.role_rank(l.designation)
    return 6 if r >= 6 else 5 if r == 5 else r


def _readiness(l) -> float:
    s = (l.score or 0) * 0.6 + ((l.latest_rating or 3) - 1) / 4 * 30 + min(10, (l.months_in_role or 0) / 3.6)
    return s - (8 if l.acting else 0)


def _ready(l) -> str:
    if l is None:
        return "No successor"
    idx, rating, months = l.score or 0, l.latest_rating, l.months_in_role or 0
    if idx >= 70 and (rating is None or rating >= 3) and months >= 12:
        return "Ready now"
    if idx >= 55 or (rating or 0) >= 4:
        return "Ready in a year"
    return "No successor"
