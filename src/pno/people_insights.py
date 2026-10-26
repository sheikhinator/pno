"""2.8 deeper people insights: absence patterns, wellbeing (long hours, no rest), early and regrettable attrition,
gender mix by level, anniversaries, who's off this week, and what goes together with turnover across stores.

Everything here is aggregate or about work patterns. Groups smaller than MIN_GROUP are never broken down by gender,
and correlations are reported as 'goes together with', never as causes.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from .po import canon

MIN_GROUP = 5
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BANDS = [(5, "Store leadership"), (4, "Department heads"), (3, "Section managers"), (1, "Team leaders & supervisors"), (0, "Staff")]


def band(designation: Any) -> str:
    r = canon.role_rank(designation)
    return next(label for lo, label in BANDS if r >= lo)


def _model(api):
    from . import analytics, engine
    ms = analytics.month_list(api.db)
    return engine.model(api.db, ms[0]["value"]) if ms else None


def _store_of(p) -> str:
    st = (canon.store(p.store) or p.store) if p.store else ""
    return f"{st} · Myli" if st and p.store_format == "HB" and not st.endswith("Myli") else st


# ------------------------------------------------------------------------------------------- absence
def absence(api, mm=None) -> dict:
    """When absences happen (weekday), who has the spread-out pattern (Bradford factor), and absences next to an off day."""
    mm = mm or _model(api)
    if not mm:
        return {"available": False}
    due_by = Counter()
    abs_by = Counter()
    people = []
    for p in mm.people.values():
        a = p.att
        if not a or not a.get("calendar"):
            continue
        cal = a["calendar"]
        spells, run, bridge = 0, 0, 0
        # in a week whose day off was guessed (no roster), any of the missed days could have been the off day: share it out
        missed = Counter(date.fromisoformat(c["day"]).isocalendar()[:2] for c in cal if c["kind"] == "absent" or c.get("implied"))
        guessed = {date.fromisoformat(c["day"]).isocalendar()[:2] for c in cal if c.get("implied")}
        for i, c in enumerate(cal):
            dd = date.fromisoformat(c["day"])
            wd, wk = dd.weekday(), dd.isocalendar()[:2]
            if c["kind"] == "worked":
                due_by[wd] += 1
            elif c["kind"] == "absent" or c.get("implied"):
                w = (missed[wk] - 1) / missed[wk] if wk in guessed else 1.0
                due_by[wd] += w
                abs_by[wd] += w
            if c["kind"] == "absent":
                if run == 0:
                    spells += 1
                run += 1
                near = [cal[j] for j in (i - 1, i + 1) if 0 <= j < len(cal)]
                if any(n["kind"] in ("off", "holiday") and not n.get("implied") for n in near):
                    bridge += 1
            elif c["kind"] != "off":
                run = 0
        days = a["absent"]
        if days:
            people.append({"emp": p.emp, "name": p.name, "store": _store_of(p), "designation": p.designation, "days": days, "spells": spells,
                           "bradford": spells * spells * days, "next_to_off": bridge})
    rate = {WEEKDAYS[d]: round(100 * abs_by[d] / due_by[d], 1) for d in range(7) if due_by[d] >= 20}
    avg = sum(abs_by.values()) / max(1, sum(due_by.values())) * 100
    peak = max(rate.items(), key=lambda x: x[1]) if rate else None
    people.sort(key=lambda r: -r["bradford"])
    total_abs = sum(r["days"] for r in people)
    return {"available": bool(due_by), "month": mm.month, "by_weekday": rate, "average": round(avg, 1),
            "peak": {"day": peak[0], "rate": peak[1], "x": round(peak[1] / avg, 1) if avg else None} if peak and avg and peak[1] >= avg * 1.25 else None,
            "bradford": people[:25], "bradford_high": sum(1 for r in people if r["bradford"] >= 125),
            "next_to_off_share": round(100 * sum(r["next_to_off"] for r in people) / total_abs) if total_abs else None,
            "absent_people": len(people)}


# ------------------------------------------------------------------------------------------- wellbeing
def wellbeing(api, mm=None, long_day: int = 11 * 60, streak: int = 12) -> dict:
    """People working very long days, many hours over, or without a day of rest for a long stretch."""
    mm = mm or _model(api)
    if not mm:
        return {"available": False}
    rows = []
    for p in mm.people.values():
        a = p.att
        if not a or not a.get("calendar"):
            continue
        cal = a["calendar"]
        longd = sum(1 for c in cal if c["kind"] == "worked" and (c.get("minutes") or 0) >= long_day)
        run = best = 0
        for c in cal:
            if c["kind"] == "worked":
                run += 1
                best = max(best, run)
            else:
                run = 0
        ot = round((a.get("overtime_minutes") or 0) / 60, 1)
        flags = []
        if longd >= 4:
            flags.append(f"{longd} days of 11h+")
        if best >= streak:
            flags.append(f"{best} days in a row without rest")
        if ot >= 40:
            flags.append(f"{ot:g}h over the month")
        if flags:
            rows.append({"emp": p.emp, "name": p.name, "store": _store_of(p), "designation": p.designation, "long_days": longd,
                         "streak": best, "overtime_h": ot, "avg_h": round((a.get("avg_minutes") or 0) / 60, 1), "flags": flags})
    rows.sort(key=lambda r: (-(len(r["flags"])), -r["streak"], -r["long_days"]))
    by_store = Counter(r["store"] for r in rows).most_common(8)
    return {"available": True, "month": mm.month, "rows": rows[:40], "n": len(rows), "by_store": by_store,
            "no_rest": sum(1 for r in rows if r["streak"] >= streak), "long": sum(1 for r in rows if r["long_days"] >= 4)}


# ------------------------------------------------------------------------------------------- attrition
def attrition(api) -> dict:
    """Early leavers (under 90 days / under a year) and regrettable losses (strong performers)."""
    b = api._brain()
    ins = b.ins
    if ins.empty or not ins.has("po_turnover"):
        return {"available": False}
    out = []
    for r in ins.rows("po_turnover"):
        p = b.people.get(str(r.get("employee_id") or ""))
        jd = r.get("joining_date") or (((p or {}).get("facts", {}).get("joining_date") or {}).get("value") if p else None)
        try:
            ten = (date.fromisoformat(str(r["date"])[:10]) - date.fromisoformat(str(jd)[:10])).days if jd and r.get("date") else None
        except ValueError:
            ten = None
        rated = [x for x in (p or {}).get("ratings", []) if x.get("rating") is not None] if p else []
        l = (p or {}).get("leader") if p else None
        regret = []
        if rated and rated[-1]["rating"] >= 4:
            regret.append(f"rated {rated[-1]['rating']:g}")
        if l is not None and l.score is not None and l.score >= 70:
            regret.append(f"leader index {l.score / 10:.1f}")
        out.append({"emp": r.get("employee_id"), "name": r.get("employee_name"), "store": r.get("store"), "section": r.get("section"),
                    "date": r.get("date"), "voluntary": r.get("voluntary"), "reason": r.get("reason"), "tenure_days": ten,
                    "regrettable": " and ".join(regret)})
    known = [x for x in out if x["tenure_days"] is not None]
    early = [x for x in known if x["tenure_days"] < 90]
    first_year = [x for x in known if x["tenure_days"] < 365]
    bands = Counter("< 3 months" if t < 90 else "3-12 months" if t < 365 else "1-3 years" if t < 1095 else "3+ years"
                    for t in (x["tenure_days"] for x in known))
    early_by_store = Counter(x["store"] for x in early).most_common(8)
    reg = [x for x in out if x["regrettable"]]
    return {"available": True, "n": len(out), "known_tenure": len(known),
            "early": len(early), "early_pct": round(100 * len(early) / len(known)) if known else None,
            "first_year_pct": round(100 * len(first_year) / len(known)) if known else None,
            "tenure_bands": [[k, bands.get(k, 0)] for k in ("< 3 months", "3-12 months", "1-3 years", "3+ years")],
            "early_by_store": early_by_store, "early_reasons": Counter(x["reason"] or "Not given" for x in early).most_common(6),
            "regrettable": sorted(reg, key=lambda x: x["date"] or "", reverse=True)[:25], "regrettable_n": len(reg),
            "regrettable_voluntary": sum(1 for x in reg if x["voluntary"])}


# ------------------------------------------------------------------------------------------- diversity
def gender_mix(api) -> dict:
    """Women and men at each level (current staff). Bands with fewer than MIN_GROUP people are not split."""
    b = api._brain()
    by = defaultdict(Counter)
    for p in b.people.values():
        if p["left"]:
            continue
        f = p["facts"]
        g = str((f.get("gender") or {}).get("value", "")).strip().casefold()
        g = "Women" if g in ("f", "female", "woman") else "Men" if g in ("m", "male", "man") else ""
        if not g:
            continue
        by[band((f.get("designation") or {}).get("value", ""))][g] += 1
    rows = []
    for _, label in BANDS:
        c = by.get(label)
        if not c:
            continue
        n = sum(c.values())
        rows.append({"band": label, "n": n, "women_pct": round(100 * c["Women"] / n) if n >= MIN_GROUP else None,
                     "women": c["Women"] if n >= MIN_GROUP else None, "men": c["Men"] if n >= MIN_GROUP else None})
    tot = sum(sum(c.values()) for c in by.values())
    women = sum(c["Women"] for c in by.values())
    staff = next((r for r in rows if r["band"] == "Staff"), None)
    lead = [r for r in rows if r["band"] != "Staff" and r["women_pct"] is not None]
    lead_n = sum(r["n"] for r in lead)
    lead_w = round(100 * sum(r["women"] for r in lead) / lead_n) if lead_n else None
    note = None
    if staff and staff["women_pct"] is not None and lead_w is not None and staff["women_pct"] - lead_w >= 10:
        note = f"Women are {staff['women_pct']}% of staff but {lead_w}% of leaders: the pipeline narrows at promotion."
    return {"available": tot > 0, "rows": rows, "n": tot, "women_pct": round(100 * women / tot) if tot else None, "leaders_women_pct": lead_w,
            "note": note, "min_group": MIN_GROUP}


# ------------------------------------------------------------------------------------------- calendar
def this_week(api, today: date | None = None) -> dict:
    """Work anniversaries in the next 7 days and who is on approved leave this week."""
    t = today or date.today()
    end = t + timedelta(days=6)
    b = api._brain()
    ann = []
    for p in b.people.values():
        if p["left"]:
            continue
        jd = (p["facts"].get("joining_date") or {}).get("value")
        try:
            j = date.fromisoformat(str(jd)[:10])
        except (TypeError, ValueError):
            continue
        for y in (t.year, t.year + 1):
            try:
                d = j.replace(year=y)
            except ValueError:
                d = date(y, 3, 1)
            yrs = y - j.year
            if t <= d <= end and yrs >= 1:
                f = p["facts"]
                ann.append({"emp": p["emp"], "name": p["name"], "years": yrs, "on": d.isoformat(),
                            "store": (f.get("store") or {}).get("value", ""), "designation": (f.get("designation") or {}).get("value", ""),
                            "milestone": yrs in (1, 5, 10, 15, 20, 25)})
    ann.sort(key=lambda a: (not a["milestone"], a["on"], -a["years"]))
    off = []
    try:
        for r in api.db.q("SELECT emp_no, d_from, d_to, type FROM leaves WHERE d_from <= ? AND d_to >= ? ORDER BY d_from", (end.isoformat(), t.isoformat())):
            p = b.people.get(str(r["emp_no"]))
            if p and not p["left"]:
                f = p["facts"]
                off.append({"emp": p["emp"], "name": p["name"], "from": r["d_from"], "to": r["d_to"], "type": r["type"],
                            "store": (f.get("store") or {}).get("value", ""), "designation": (f.get("designation") or {}).get("value", ""),
                            "level": canon.role_rank((f.get("designation") or {}).get("value", ""))})
    except Exception:  # noqa: BLE001
        pass
    off.sort(key=lambda r: (-r["level"], r["from"]))
    return {"from": t.isoformat(), "to": end.isoformat(), "anniversaries": ann[:30], "off": off[:40], "off_leaders": sum(1 for r in off if r["level"] >= 3)}


# ------------------------------------------------------------------------------------------- drivers
def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 6:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if not sx or not sy:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


METRICS = {"turnover": "Turnover per 100 staff", "absence": "Absence rate %", "leader_index": "Average leader index",
           "sales_vs_budget": "Sales vs budget %", "nps": "Customer NPS", "da_cases": "Disciplinary cases", "long_hours": "People on long hours",
           "rating": "Average rating"}


def drivers(api, mm=None) -> dict:
    """Across stores: which measures move together with turnover and with sales. Associations, not causes."""
    ins = api._po()
    if ins.empty:
        return {"available": False}
    mm = mm or _model(api)
    st: dict[str, dict] = {}
    for r in ins.store_scorecard():
        hc = ins.headcount(r["store"])
        st[r["store"]] = {"turnover": 100 * r["leavers_12m"] / hc if r.get("leavers_12m") is not None and hc else None,
                          "leader_index": r["avg_leader_score"] / 10 if r.get("avg_leader_score") is not None else None,
                          "sales_vs_budget": r["sales_vs_budget_pct"], "nps": r["nps"], "da_cases": r["da_cases"], "rating": r["avg_rating"]}
    if mm:
        wb = {x["emp"] for x in wellbeing(api, mm)["rows"]}
        due, ab, lh = Counter(), Counter(), Counter()
        for p in mm.people.values():
            if not p.att:
                continue
            s = _store_of(p)
            due[s] += p.att.get("due") or 0
            ab[s] += p.att.get("absent") or 0
            lh[s] += p.emp in wb
        for s in due:
            if s in st and due[s] >= 50:
                st[s]["absence"] = 100 * ab[s] / due[s]
                st[s]["long_hours"] = lh[s]
    found = []
    for target in ("turnover", "sales_vs_budget"):
        for m in METRICS:
            if m == target:
                continue
            pairs = [(v[m], v[target]) for v in st.values() if v.get(m) is not None and v.get(target) is not None]
            r = _pearson([a for a, _ in pairs], [b for _, b in pairs])
            if r is not None and abs(r) >= 0.4:
                found.append({"target": target, "metric": m, "r": round(r, 2), "n": len(pairs),
                              "text": f"Stores with {'higher' if r > 0 else 'lower'} {METRICS[m].lower()} tend to have higher {METRICS[target].lower()} "
                                      f"({'strong' if abs(r) >= 0.7 else 'moderate'} link, {len(pairs)} stores)."})
    found.sort(key=lambda f: -abs(f["r"]))
    return {"available": True, "drivers": found[:8], "stores": len(st), "labels": METRICS,
            "points": {k: [[s, v.get(k)] for s, v in st.items()] for k in METRICS}}


def report(api) -> dict:
    mm = None
    try:
        mm = _model(api)
    except Exception:  # noqa: BLE001
        pass
    out = {}
    for k, fn in (("absence", lambda: absence(api, mm)), ("wellbeing", lambda: wellbeing(api, mm)), ("attrition", lambda: attrition(api)),
                  ("gender", lambda: gender_mix(api)), ("week", lambda: this_week(api)), ("drivers", lambda: drivers(api, mm))):
        try:
            out[k] = fn()
        except Exception as e:  # noqa: BLE001 - one missing source never hides the rest
            out[k] = {"available": False, "error": str(e)}
    return out
