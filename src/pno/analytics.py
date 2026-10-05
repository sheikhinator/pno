"""Screen-ready numbers built from the month model: dashboard, people, stores, attendance, org chart, history."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from .db import Database
from .engine import BANDS, MonthModel, Person, band, domain_label, model, months_available
from .org import DEPT_NAMES, ROLE_LABEL
from .stores import CITIES, FORMAT_LABEL
from .util import fmt_minutes, month_label, prev_month


# ------------------------------------------------------------------------------------------------ scope
def in_scope(p: Person, scope: dict | None) -> bool:
    if not scope:
        return True
    if scope.get("city") and p.city != scope["city"]:
        return False
    if scope.get("format") and p.store_format != scope["format"]:
        return False
    if scope.get("store_id") and p.store_id != int(scope["store_id"]):
        return False
    if scope.get("dept") and p.dept_code != scope["dept"]:
        return False
    if scope.get("section") and p.section != scope["section"]:
        return False
    return True


def store_in_scope(st: dict, scope: dict | None) -> bool:
    if not scope:
        return True
    if scope.get("city") and st.get("city") != scope["city"]:
        return False
    if scope.get("format") and st.get("format") != scope["format"]:
        return False
    if scope.get("store_id") and st["id"] != int(scope["store_id"]):
        return False
    return True


def scope_label(mm: MonthModel, scope: dict | None) -> str:
    parts = ["Pakistan"]
    scope = scope or {}
    if scope.get("city"):
        parts.append(CITIES.get(scope["city"], scope["city"]))
    if scope.get("format"):
        parts.append(FORMAT_LABEL.get(scope["format"], scope["format"]))
    if scope.get("store_id"):
        st = mm.stores.get(int(scope["store_id"]))
        if st:
            parts.append(st["name"])
    if scope.get("dept"):
        parts.append(DEPT_NAMES.get(scope["dept"], scope["dept"]))
    if scope.get("section"):
        parts.append(scope["section"])
    return " › ".join(parts)


def options(mm: MonthModel, scope: dict | None) -> dict:
    """What the filter dropdowns offer, narrowed by the choices already made."""
    scope = scope or {}
    stores = [s for s in mm.stores.values() if s["format"] != "HO" or True]
    cities = sorted({s["city"] for s in stores if s["city"]})
    formats = sorted({s["format"] for s in stores if s["format"]})
    st_list = sorted([s for s in stores if store_in_scope(s, {k: scope.get(k) for k in ("city", "format")})],
                     key=lambda s: (s["format"], s["name"]))
    ppl = [p for p in mm.people.values() if in_scope(p, {k: scope.get(k) for k in ("city", "format", "store_id")})]
    depts = sorted({p.dept_code for p in ppl if p.dept_code})
    secs = sorted({p.section for p in ppl if p.section and (not scope.get("dept") or p.dept_code == scope["dept"])})
    return {"cities": [{"value": c, "label": CITIES.get(c, c)} for c in cities],
            "formats": [{"value": f, "label": FORMAT_LABEL.get(f, f)} for f in formats],
            "stores": [{"value": s["id"], "label": s["name"], "format": s["format"], "city": s["city"]} for s in st_list],
            "depts": [{"value": d, "label": f"{d} · {DEPT_NAMES.get(d, d)}"} for d in depts],
            "sections": [{"value": s, "label": s} for s in secs]}


# ------------------------------------------------------------------------------------------------ store-level figures
def _sales_rows(mm: MonthModel, scope: dict | None) -> list[dict]:
    scope = scope or {}
    out = []
    code = f"D{scope['dept']}" if scope.get("dept") else "STORE"
    for sid, rows in getattr(mm, "sales", {}).items():
        st = mm.stores.get(sid)
        if st and store_in_scope(st, scope) and code in rows:
            out.append(rows[code])
    return out


def sales_vs_budget(mm: MonthModel, scope: dict | None) -> dict | None:
    rows = [r for r in _sales_rows(mm, scope) if (r.get("budget") or 0) > 0]
    if not rows:
        return None
    a, b = sum(r["actual"] or 0 for r in rows), sum(r["budget"] for r in rows)
    ly = sum(r["ly"] or 0 for r in rows if r.get("ly"))
    al = sum(r["actual"] or 0 for r in rows if r.get("ly"))
    return {"pct": a / b * 100, "actual": a, "budget": b, "growth": (al / ly - 1) * 100 if ly else None, "stores": len(rows)}


def productivity(mm: MonthModel, scope: dict | None) -> dict | None:
    scope = scope or {}
    code = f"D{scope['dept']}" if scope.get("dept") else "STORE"
    ratios = []
    for sid, rows in getattr(mm, "prod", {}).items():
        st = mm.stores.get(sid)
        if st and store_in_scope(st, scope) and code in rows and rows[code].get("target"):
            ratios.append(rows[code]["actual"] / rows[code]["target"] * 100)
    return {"pct": mean(ratios), "stores": len(ratios)} if ratios else None


def attendance_totals(people: list[Person]) -> dict:
    a = [p.att for p in people if p.att]
    due = sum(x["due"] for x in a)
    absent = sum(x["absent"] for x in a)
    sys_abs = sum(x["sys_absent"] or 0 for x in a if x["sys_absent"] is not None)
    sys_den = sum((x["sys_absent"] or 0) + (x["sys_present"] or 0) for x in a if x["sys_absent"] is not None)
    timed = sum(x["full_days"] + x["short_days"] for x in a)
    return {
        "people": len(a), "due": due, "worked": sum(x["worked"] for x in a), "absent": absent,
        "absence_pct": absent / due * 100 if due else None,
        "system_absence_pct": sys_abs / sys_den * 100 if sys_den else None, "system_absent": sys_abs,
        "fixes": sum(x["fixes"] for x in a), "leave": sum(x["leave"] for x in a), "off": sum(x["off"] for x in a),
        "holiday": sum(x["holiday"] for x in a),
        "compliance_pct": sum(x["full_days"] for x in a) / timed * 100 if timed else None,
        "avg_minutes": round(sum(x["minutes"] for x in a) / timed) if timed else None,
        "overtime_hours": round(sum(x["overtime_minutes"] for x in a) / 60),
        "long_absence": sum(1 for x in a if x["longest_absence"] >= 7),
    }


def _avg_score(people: list[Person]) -> float | None:
    s = [p.score for p in people if p.score is not None]
    return mean(s) if s else None


def _delta(cur, prev):
    return None if cur is None or prev is None else cur - prev


# ------------------------------------------------------------------------------------------------ dashboard
def dashboard(db: Database, month: str | None, scope: dict | None, compare: str | None = None, hide: bool = False) -> dict:
    mm = model(db, month)
    av = months_available(db)
    cmp_month = compare or (prev_month(mm.month) if prev_month(mm.month) in av else None)
    pm = model(db, cmp_month) if cmp_month and cmp_month in av else None
    ppl = [p for p in mm.people.values() if in_scope(p, scope)]
    pppl = [p for p in pm.people.values() if in_scope(p, scope)] if pm else []
    att, patt = attendance_totals(ppl), attendance_totals(pppl) if pm else {}
    sb, psb = sales_vs_budget(mm, scope), sales_vs_budget(pm, scope) if pm else None
    pr, ppr = productivity(mm, scope), productivity(pm, scope) if pm else None
    avg, pavg = _avg_score(ppl), _avg_score(pppl) if pm else None
    cards = [
        {"key": "headcount", "label": "Headcount", "value": len(ppl), "fmt": "int",
         "delta": len(ppl) - len(pppl) if pm else None, "good": None,
         "sub": f"{sum(1 for p in ppl if p.role != 'STAFF')} managers"},
        {"key": "absence", "label": "Real absence", "value": att["absence_pct"], "fmt": "pct",
         "delta": _delta(att["absence_pct"], patt.get("absence_pct")), "good": "down",
         "sub": (f"System shows {att['system_absence_pct']:.1f}%" if att["system_absence_pct"] is not None else "Unexplained absence")},
        {"key": "score", "label": "Average score", "value": avg, "fmt": "score", "delta": _delta(avg, pavg), "good": "up",
         "sub": f"{sum(1 for p in ppl if p.score is not None)} people scored"},
        {"key": "sales", "label": "Sales vs budget", "value": sb and sb["pct"], "fmt": "pct0",
         "delta": _delta(sb and sb["pct"], psb and psb["pct"]), "good": "up",
         "sub": (f"{sb['growth']:+.1f}% vs last year" if sb and sb.get("growth") is not None else "No sales report")},
        {"key": "productivity", "label": "Productivity vs target", "value": pr and pr["pct"], "fmt": "pct0",
         "delta": _delta(pr and pr["pct"], ppr and ppr["pct"]), "good": "up",
         "sub": f"{pr['stores']} stores" if pr else "No productivity report"},
    ]
    dist = Counter(band(p.score)[1] for p in ppl if p.score is not None)
    distribution = [{"key": k, "label": lbl, "count": dist.get(k, 0)} for _, lbl, k in BANDS]
    scored = sorted([p for p in ppl if p.score is not None], key=lambda p: -p.score)
    league = store_league(mm, scope)
    alerts = _alerts(mm, ppl, scope)
    trend = []
    for m in av[-6:]:
        if m > mm.month:
            continue
        x = model(db, m)
        xp = [p for p in x.people.values() if in_scope(p, scope)]
        xa = attendance_totals(xp)
        xs = sales_vs_budget(x, scope)
        trend.append({"month": m, "label": month_label(m)[:3] + " " + m[2:4], "score": _avg_score(xp),
                      "absence": xa["absence_pct"], "sales": xs and xs["pct"]})
    return {
        "month": mm.month, "month_label": month_label(mm.month), "compare": cmp_month, "as_of": mm.as_of,
        "data_days": mm.data_days, "complete": mm.complete, "provisional": mm.data_days < 7 and not mm.complete,
        "scope_label": scope_label(mm, scope), "cards": cards, "distribution": distribution,
        "top": [_person_row(p, hide) for p in scored[:10]], "bottom": [_person_row(p, hide) for p in scored[-10:][::-1]],
        "league": league, "alerts": alerts, "trend": trend, "attendance": att, "warnings": mm.warnings,
        "has_data": bool(mm.people) or bool(getattr(mm, "sales", {})),
    }


def _person_row(p: Person, hide: bool = False) -> dict:
    b = p.brief()
    if hide:
        b["name"] = f"Employee {p.emp}"
    return b


def store_league(mm: MonthModel, scope: dict | None) -> list[dict]:
    out = []
    for sid, st in mm.stores.items():
        if not store_in_scope(st, scope):
            continue
        ppl = [p for p in mm.people.values() if p.store_id == sid and in_scope(p, scope)]
        sales = getattr(mm, "sales", {}).get(sid, {})
        prod = getattr(mm, "prod", {}).get(sid, {})
        if not ppl and not sales:
            continue
        gm = next((p for p in ppl if p.role in ("GM", "HBM")), None)
        tot = sales.get(f"D{scope['dept']}" if scope and scope.get("dept") else "STORE")
        att = attendance_totals(ppl)
        pr = prod.get("STORE")
        out.append({
            "store_id": sid, "store": st["name"], "format": st["format"], "city": st["city"], "people": len(ppl),
            "score": _avg_score(ppl), "gm": gm.name if gm else None, "gm_emp": gm.emp if gm else None,
            "gm_score": gm.score if gm else None,
            "sales_pct": tot["actual"] / tot["budget"] * 100 if tot and tot.get("budget") else None,
            "sales": tot["actual"] if tot else None, "growth": tot["growth"] if tot else None,
            "prod_pct": pr["actual"] / pr["target"] * 100 if pr and pr.get("target") else None,
            "absence_pct": att["absence_pct"], "fixes": att["fixes"],
        })
    out.sort(key=lambda r: -(r["score"] if r["score"] is not None else -1))
    return out


def _alerts(mm: MonthModel, ppl: list[Person], scope: dict | None) -> list[dict]:
    out = []
    long_abs = [p for p in ppl if p.att and p.att["longest_absence"] >= 7]
    if long_abs:
        out.append({"key": "long_absence", "level": "bad", "count": len(long_abs),
                    "text": f"{len(long_abs)} people absent 7+ days in a row (possible leavers or long leave)",
                    "people": [p.emp for p in sorted(long_abs, key=lambda p: -p.att["longest_absence"])[:50]]})
    fixes = sum(p.att["fixes"] for p in ppl if p.att)
    if fixes:
        n = sum(1 for p in ppl if p.att and p.att["fixes"])
        out.append({"key": "fixes", "level": "warn", "count": fixes, "text": f"{fixes} missing punches to fix for {n} people",
                    "people": []})
    extreme = []
    for sid, rows in getattr(mm, "sales", {}).items():
        st = mm.stores.get(sid)
        if not st or not store_in_scope(st, scope):
            continue
        for r in rows.values():
            if r["level"] == "section" and (r.get("budget") or 0) > 0 and r.get("actual"):
                v = r["actual"] / r["budget"] * 100 - 100
                if abs(v) > 50:
                    extreme.append(f"{st['name']} {r['code']} {r['name']} {v:+.0f}%")
    if extreme:
        out.append({"key": "variance", "level": "info", "count": len(extreme),
                    "text": f"{len(extreme)} sections more than ±50% from budget (capped in scores)", "items": extreme[:30]})
    newj = [p for p in ppl if p.status == "new_joiner"]
    if newj:
        out.append({"key": "new_joiners", "level": "info", "count": len(newj), "text": f"{len(newj)} new joiners (not scored yet)",
                    "people": [p.emp for p in newj]})
    unsure = [p for p in ppl if p.manager_status == "uncertain"]
    if unsure:
        out.append({"key": "managers", "level": "warn", "count": len(unsure),
                    "text": f"{len(unsure)} reporting lines need confirming (manager name matches several people)",
                    "people": [p.emp for p in unsure]})
    return out


# ------------------------------------------------------------------------------------------------ people
def people_list(db: Database, month: str | None, scope: dict | None, q: str = "", role: str = "", band_key: str = "",
                sort: str = "score", desc: bool = True, limit: int = 500, offset: int = 0, hide: bool = False,
                flag: str = "") -> dict:
    mm = model(db, month)
    ppl = [p for p in mm.people.values() if in_scope(p, scope)]
    if q:
        nq = q.strip().lower()
        ppl = [p for p in ppl if nq in p.name.lower() or nq in p.emp or nq in p.designation.lower() or nq in p.store.lower()]
    if role:
        ppl = [p for p in ppl if p.role == role or (role == "MANAGERS" and p.role != "STAFF")]
    if band_key:
        ppl = [p for p in ppl if band(p.score)[1] == band_key]
    if flag == "long_absence":
        ppl = [p for p in ppl if p.att and p.att["longest_absence"] >= 7]
    elif flag == "fixes":
        ppl = [p for p in ppl if p.att and p.att["fixes"]]
    elif flag == "managers":
        ppl = [p for p in ppl if p.manager_status == "uncertain"]
    elif flag == "new_joiners":
        ppl = [p for p in ppl if p.status == "new_joiner"]
    pm = model(db, prev_month(mm.month)) if prev_month(mm.month) in months_available(db) else None
    key = {
        "score": lambda p: (p.score is not None, p.score or 0),
        "name": lambda p: p.name.lower(), "store": lambda p: (p.store, p.name),
        "attendance": lambda p: (p.att is not None and p.att.get("score") is not None, (p.att or {}).get("score") or 0),
        "absent": lambda p: ((p.att or {}).get("absent") or 0), "role": lambda p: (p.role, p.name),
        "fixes": lambda p: ((p.att or {}).get("fixes") or 0),
    }.get(sort, lambda p: (p.score is not None, p.score or 0))
    ppl.sort(key=key, reverse=desc if sort not in ("name", "store", "role") else not desc)
    rows = []
    for p in ppl[offset:offset + limit]:
        r = _person_row(p, hide)
        if pm and p.emp in pm.people and pm.people[p.emp].score is not None and p.score is not None:
            r["delta"] = round(p.score - pm.people[p.emp].score, 1)
        rows.append(r)
    roles = Counter(p.role for p in mm.people.values() if in_scope(p, scope))
    return {"month": mm.month, "total": len(ppl), "rows": rows,
            "roles": [{"value": k, "label": ROLE_LABEL[k], "count": v} for k, v in sorted(roles.items())]}


def person(db: Database, month: str | None, emp: str, hide: bool = False) -> dict:
    mm = model(db, month)
    p = mm.people.get(emp)
    if p is None:
        raise ValueError("This person is not in the selected month's data.")
    hist = []
    for m in months_available(db)[-12:]:
        x = model(db, m).people.get(emp)
        if x:
            hist.append({"month": m, "label": month_label(m)[:3] + " " + m[2:4], "score": x.score,
                         "attendance": x.att and x.att.get("score"), "presence": x.att and x.att.get("presence")})
    chain = []
    cur, seen = p, set()
    while cur.manager_emp and cur.manager_emp in mm.people and cur.manager_emp not in seen and len(chain) < 6:
        seen.add(cur.manager_emp)
        cur = mm.people[cur.manager_emp]
        chain.append({"emp": cur.emp, "name": cur.name, "designation": cur.designation})
    if cur.manager_name and cur.manager_status == "outside":
        chain.append({"emp": None, "name": cur.manager_name, "designation": "Outside the roster"})
    team = sorted([mm.people[e] for e in p.reports if e in mm.people], key=lambda x: -(x.score or -1))
    leaves = [dict(r) for r in db.q("""SELECT l.id, l.d_from, l.d_to, l.type, l.note FROM leaves l LEFT JOIN imports i ON i.id=l.import_id
                                       WHERE l.emp_no=? AND (l.import_id IS NULL OR i.active=1) ORDER BY l.d_from DESC LIMIT 30""", (emp,))]
    notes = [dict(r) for r in db.q("SELECT id, day, text, created_at FROM notes WHERE emp_no=? ORDER BY id DESC LIMIT 30", (emp,))]
    b = _person_row(p, hide)
    att = None
    if p.att:
        att = {k: v for k, v in p.att.items() if k != "calendar"}
        att["calendar"] = [{**c, "hours": fmt_minutes(c["minutes"]) if c["minutes"] else None} for c in p.att["calendar"]]
        att["avg_hours"] = fmt_minutes(p.att["avg_minutes"]) if p.att.get("avg_minutes") else None
        att["total_hours"] = round(p.att["minutes"] / 60, 1)
        att["overtime_hours"] = round(p.att["overtime_minutes"] / 60, 1)
    return {
        **b, "month": mm.month, "month_label": month_label(mm.month), "gender": p.gender, "joining": p.joining,
        "manager": {"name": p.manager_name, "emp": p.manager_emp, "status": p.manager_status},
        "domain": domain_label(mm, p), "components": p.components, "context": p.context, "attendance_detail": att,
        "history": hist, "chain": chain, "team": [_person_row(t, hide) for t in team], "leaves": leaves, "notes": notes,
        "in_roster": p.in_roster,
    }


# ------------------------------------------------------------------------------------------------ stores
def store_detail(db: Database, month: str | None, store_id: int, hide: bool = False) -> dict:
    mm = model(db, month)
    st = mm.stores.get(int(store_id))
    if not st:
        raise ValueError("Store not found.")
    ppl = [p for p in mm.people.values() if p.store_id == st["id"]]
    sales = getattr(mm, "sales", {}).get(st["id"], {})
    prod = getattr(mm, "prod", {}).get(st["id"], {})
    managers: dict[str, list[str]] = defaultdict(list)
    dept_heads: dict[str, list[str]] = defaultdict(list)
    for p in ppl:
        if p.role in ("SM", "STAFF") and p.domain.get("level") == "sections" and p.role == "SM":
            for c in p.domain.get("codes", []):
                managers[c].append(p.name if not hide else f"Employee {p.emp}")
        if p.role == "DH":
            dept_heads[p.domain.get("dept", "")].append(p.name if not hide else f"Employee {p.emp}")
    sections, depts = [], []
    for code, r in sorted(sales.items(), key=lambda kv: kv[0]):
        if r["level"] not in ("section", "dept"):
            continue
        if r["level"] == "section" and not (r.get("actual") or r.get("budget")):
            continue
        pr = next((v for k, v in prod.items() if code in k.split("+")), None) if r["level"] == "section" else prod.get(code)
        row = {"code": code, "name": r["name"], "dept": r["dept"], "actual": r["actual"], "budget": r["budget"],
               "sales_pct": r["actual"] / r["budget"] * 100 if r.get("budget") else None, "growth": r["growth"],
               "margin": r["margin_net"], "waste": r["waste"], "oos": None if r["dept"] == "02" and r["level"] == "section" else r["oos"],
               "customers": r["customers"], "prod_pct": pr["actual"] / pr["target"] * 100 if pr and pr.get("target") else None,
               "managers": managers.get(code, []) if r["level"] == "section" else dept_heads.get(r["dept"], [])}
        (sections if r["level"] == "section" else depts).append(row)
    depts.sort(key=lambda r: r["code"])
    by_section = defaultdict(list)
    for p in ppl:
        by_section[p.section or "—"].append(p)
    att_sections = [{"section": s, **attendance_totals(v)} for s, v in sorted(by_section.items())]
    gm = next((p for p in ppl if p.role in ("GM", "HBM")), None)
    tot = sales.get("STORE")
    return {
        "store_id": st["id"], "store": st["name"], "format": st["format"], "format_label": FORMAT_LABEL.get(st["format"], ""),
        "city": CITIES.get(st["city"], st["city"]), "code": st["code"], "month": mm.month, "month_label": month_label(mm.month),
        "sales_as_of": mm.sales_asof.get(st["id"]), "gm": _person_row(gm, hide) if gm else None,
        "gm_components": gm.components if gm else [], "people": len(ppl), "score": _avg_score(ppl),
        "total": None if not tot else {"actual": tot["actual"], "budget": tot["budget"], "growth": tot["growth"],
                                       "sales_pct": tot["actual"] / tot["budget"] * 100 if tot.get("budget") else None,
                                       "margin": tot["margin_net"], "waste": tot["waste"], "oos": tot["oos"],
                                       "customers": tot["customers"], "basket": tot["avg_basket"]},
        "productivity": [{"row": v["row_name"], "actual": v["actual"], "target": v["target"], "ly": v["ly"],
                          "forecast": v["forecast"], "pct": v["actual"] / v["target"] * 100 if v.get("target") else None}
                         for v in prod.values()],
        "departments": depts, "sections": sections, "attendance": attendance_totals(ppl), "attendance_sections": att_sections,
        "managers": [_person_row(p, hide) for p in sorted(ppl, key=lambda p: (p.role == "STAFF", -(p.score or -1))) if p.role != "STAFF"],
    }


# ------------------------------------------------------------------------------------------------ attendance
def attendance_view(db: Database, month: str | None, scope: dict | None, hide: bool = False) -> dict:
    mm = model(db, month)
    ppl = [p for p in mm.people.values() if in_scope(p, scope) and p.att]
    totals = attendance_totals(ppl)
    daily: dict[str, Counter] = defaultdict(Counter)
    fixes = []
    for p in ppl:
        for c in p.att["calendar"]:
            daily[c["day"]][c["kind"]] += 1
            if c["status"] in ("missing_in", "missing_out", "punched_absent"):
                fixes.append({"emp": p.emp, "name": p.name if not hide else f"Employee {p.emp}", "store": p.store,
                              "section": p.section, "day": c["day"], "kind": c["status"],
                              "t_in": c["t_in"], "t_out": c["t_out"], "hours": fmt_minutes(c["minutes"]) if c["minutes"] else None})
    days = [{"day": d, "label": d[8:], "worked": v["worked"], "absent": v["absent"], "off": v["off"], "leave": v["leave"],
             "holiday": v["holiday"]} for d, v in sorted(daily.items())]
    long_abs = sorted([p for p in ppl if p.att["longest_absence"] >= 7], key=lambda p: -p.att["longest_absence"])
    low = sorted([p for p in ppl if p.att.get("compliance") is not None], key=lambda p: p.att["compliance"])[:25]
    by_store = []
    for sid, st in mm.stores.items():
        sp = [p for p in ppl if p.store_id == sid]
        if sp:
            by_store.append({"store_id": sid, "store": st["name"], "format": st["format"], **attendance_totals(sp)})
    by_store.sort(key=lambda r: -(r["absence_pct"] or 0))

    def row(p):
        a = p.att
        return {**_person_row(p, hide), "worked": a["worked"], "absent": a["absent"], "longest": a["longest_absence"],
                "compliance": a["compliance"], "avg_hours": fmt_minutes(a["avg_minutes"]) if a["avg_minutes"] else None,
                "sys_absent": a["sys_absent"], "leave": a["leave"], "off": a["off"]}

    return {"month": mm.month, "month_label": month_label(mm.month), "as_of": mm.as_of, "totals": totals, "daily": days,
            "fixes": sorted(fixes, key=lambda f: (f["store"], f["name"], f["day"])), "long_absence": [row(p) for p in long_abs],
            "low_compliance": [row(p) for p in low], "by_store": by_store,
            "register": [row(p) for p in sorted(ppl, key=lambda p: (p.store, p.name))]}


# ------------------------------------------------------------------------------------------------ org chart
def org_chart(db: Database, month: str | None, store_id: int | None, hide: bool = False) -> dict:
    mm = model(db, month)
    ppl = [p for p in mm.people.values() if store_id is None or p.store_id == int(store_id)]
    ids = {p.emp for p in ppl}

    def node(p: Person, depth=0) -> dict:
        kids = sorted([mm.people[e] for e in p.reports if e in ids],
                      key=lambda x: (x.role == "STAFF", x.designation, x.name))
        return {"emp": p.emp, "name": p.name if not hide else f"Employee {p.emp}", "designation": p.designation,
                "role": p.role, "score": None if p.score is None else round(p.score, 1), "band": band(p.score)[1],
                "children": [node(k, depth + 1) for k in kids] if depth < 8 else []}

    roots = [p for p in ppl if not p.manager_emp or p.manager_emp not in ids]
    roots.sort(key=lambda p: ({"GM": 0, "HBM": 0, "AREA": 0, "DH": 1, "CCO": 2, "SM": 3}.get(p.role, 4), p.name))
    external: dict[str, list] = defaultdict(list)
    for r in roots:
        external[r.manager_name or "No manager recorded"].append(node(r))
    tree = [{"emp": None, "name": k, "designation": "Reports outside this store" if k != "No manager recorded" else "",
             "role": "EXT", "score": None, "band": "none", "children": v} for k, v in external.items()]
    tree.sort(key=lambda n: -len(n["children"]))
    return {"month": mm.month, "tree": tree, "people": len(ppl)}


def month_list(db: Database) -> list[dict]:
    return [{"value": m, "label": month_label(m)} for m in months_available(db)][::-1]


def summarise_any(value: Any) -> Any:
    return value
