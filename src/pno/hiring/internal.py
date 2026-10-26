"""Internal talent first: for a vacancy, who already in the company could take it, why, and what their move leaves behind.

A move is never judged on the person alone. Moving the best Department Head out of Fortress leaves Fortress without
one, so every candidate comes with:
  * their seat's backfill: who below them in the same store could take it, and how ready they are;
  * the chain of moves the promotion sets off (Department Head → Section Manager steps up → a Team Leader steps up …)
    until a seat can only be filled from outside, and how many outside hires that means;
  * a risk rating for the store they leave (critical seats: store manager, deputy, department head; a store losing
    two leaders at once; a seat with no one ready).
The recommendation weighs the person's fit against that risk, then says whether to promote, promote and backfill
from outside, develop someone (acting / interim), or hire externally.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from ..po import canon
from . import templates

LEVEL_NAME = {6: "Store Manager", 5: "Deputy Store Manager", 4: "Department Head", 3: "Section Manager", 2: "Team Leader", 1: "Supervisor", 0: "Associate"}
CRITICAL = 4                                   # seats from department head up are critical to a store


def _level_of(designation: str) -> int:
    r = canon.role_rank(designation)
    return 6 if r >= 6 else r


def _target(v: dict) -> dict:
    role = v.get("role") or "associate"
    spec = templates.ROLES.get(role, templates.ROLES["associate"])
    level = {1: 0, 2: 2, 3: 3, 4: 4, 6: 6}.get(spec["level"], spec["level"])
    if role == "cashier":
        level = 0
    store = canon.store(v.get("store") or "") if v.get("store") else ""
    section = canon.section(v.get("section") or "") if v.get("section") else ""
    return {"level": level, "title": v.get("title") or spec["title"], "store": store, "section": section,
            "department": canon.department(section) if section else "", "city": canon.store_city(store) if store else ""}


def _pct(x: float | None) -> float:
    return max(0.0, min(100.0, x or 0.0))


class Pool:
    """Everyone P&O knows: leaders from the P&O review (with index, ratings, KPIs) and all staff from the employee master."""

    def __init__(self, api):
        self.api = api
        self.ins = api._po()
        self.leaders = list(self.ins.leaders()) if not self.ins.empty else []
        self.by_id = {str(l.employee_id): l for l in self.leaders if l.employee_id}
        from ..po.people_risk import flight_risk
        self.risk = {r["key"]: r for r in (flight_risk(self.ins) if self.leaders else [])}
        self.staff = self._staff()
        self.training = self._training()
        self.notes = self._notes()

    def _staff(self) -> list[dict]:
        """Non-leaders from the employee master and the latest month's people scores."""
        out: dict[str, dict] = {}
        try:
            for r in self.ins.rows("po_master"):
                e = str(r.get("employee_id") or "")
                if e and e not in self.by_id:
                    out[e] = {"emp": e, "name": canon.repair_name(r.get("employee_name")), "store": r.get("store") or "", "section": canon.section(r.get("section")),
                              "designation": r.get("designation") or "", "grade": r.get("grade") or "", "joining": r.get("joining_date"),
                              "manager": r.get("manager_name") or "", "score": None}
        except Exception:  # noqa: BLE001
            pass
        try:
            from .. import analytics, engine
            ms = analytics.month_list(self.api.db)
            if ms:
                mm = engine.model(self.api.db, ms[0]["value"])
                for p in mm.people.values():
                    if str(p.emp) in self.by_id:
                        continue
                    d = out.setdefault(str(p.emp), {"emp": str(p.emp), "name": p.name, "store": canon.store(p.store) or p.store,
                                                    "section": canon.section(p.section), "designation": p.designation, "grade": p.grade,
                                                    "joining": p.joining, "manager": p.manager_name, "score": None})
                    d["score"] = p.score
                    d["attendance"] = (p.att or {}).get("presence")
        except Exception:  # noqa: BLE001
            pass
        return list(out.values())

    def _training(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for r in self.api.db.q("SELECT a.person, a.status, c.title FROM assignments a JOIN courses c ON c.id=a.course_id"):
            out[str(r["person"])].append(f"{r['title']} ({r['status']})")
        return out

    def _notes(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        try:
            for r in self.api.db.q("SELECT subject_key, subject FROM meetings"):
                out[str(r["subject_key"] or r["subject"]).casefold()] += 1
        except Exception:  # noqa: BLE001
            pass
        return out

    # ---------------------------------------------------------------------------------------------- succession helpers
    def below(self, store: str, level: int, department: str = "", exclude: set[str] | None = None) -> list[Any]:
        """People one level below a seat in the same store, best prepared first."""
        from ..po.people_risk import _readiness
        exclude = exclude or set()
        lv_below = {6: (5, 4), 5: (4,), 4: (3,), 3: (2,), 2: (1, 0)}.get(level, ())
        cands = [l for l in self.leaders if l.store == store and _level_of(l.designation) in lv_below and l.key not in exclude]
        if department:
            same = [l for l in cands if any(canon.department(s) == department for s in l.sections)]
            cands = same + [l for l in cands if l not in same]
        return sorted(cands, key=lambda l: -_readiness(l))

    def ready(self, l) -> str:
        from ..po.people_risk import _ready
        return _ready(l)


def _seat(l) -> dict:
    lv = _level_of(l.designation)
    sec = l.sections[0] if l.sections else ""
    return {"level": lv, "title": LEVEL_NAME.get(lv, l.designation), "store": l.store, "section": l.section_text,
            "department": canon.department(sec) if sec else "", "holder": l}


def chain(pool: Pool, l, limit: int = 4) -> dict:
    """The moves one promotion sets off, until a seat has to be filled from outside."""
    from ..po.format import leader_name
    steps, used = [], {l.key}
    seat = _seat(l)
    first = None
    for _ in range(limit):
        if seat["level"] <= 1:
            steps.append({"seat": f"{seat['title']} · {seat['section']} · {seat['store']}", "by": None, "how": "external",
                          "note": "Entry-level seat: quick to fill from outside or the talent bank"})
            break
        succ = pool.below(seat["store"], seat["level"], seat["department"], used)
        best = succ[0] if succ else None
        if best is None:
            steps.append({"seat": f"{seat['title']} · {seat['section']} · {seat['store']}", "by": None, "how": "external",
                          "note": "No one below this seat in the store: hire from outside or move someone from another store"})
            break
        rd = pool.ready(best)
        steps.append({"seat": f"{seat['title']} · {seat['section']} · {seat['store']}", "by": leader_name(best), "by_role": best.designation,
                      "ready": rd, "how": "internal" if rd == "Ready now" else ("acting" if rd == "Ready in a year" else "stretch"),
                      "note": {"Ready now": "Ready now", "Ready in a year": "Could act up with support; ready in about a year"}.get(rd, "Not ready: a stretch")})
        if first is None:
            first = {"name": leader_name(best), "role": best.designation, "ready": rd, "index": best.score}
        used.add(best.key)
        seat = _seat(best)
    else:
        steps.append({"seat": f"{seat['title']} · {seat['section']} · {seat['store']}", "by": None, "how": "external", "note": "End of the chain"})
    external = sum(1 for s in steps if s["how"] == "external")
    weak = sum(1 for s in steps if s["how"] in ("acting", "stretch"))
    origin = _seat(l)
    if first is None:
        status = "gap"
        risk = "High" if origin["level"] >= CRITICAL else "Medium"
    elif first["ready"] == "Ready now":
        status, risk = "covered", "Low"
    elif first["ready"] == "Ready in a year":
        status, risk = "interim", "Medium" if origin["level"] >= CRITICAL else "Low"
    else:
        status, risk = "weak", "High" if origin["level"] >= CRITICAL else "Medium"
    leaders_left = sum(1 for x in pool.leaders if x.store == l.store and _level_of(x.designation) >= 3)
    if leaders_left <= 3 and origin["level"] >= 3:
        risk = "High" if status != "covered" else "Medium"
    return {"seat": f"{origin['title']} · {origin['section']} · {origin['store']}", "status": status, "risk": risk, "successor": first,
            "steps": steps, "external_hires": external, "weak_links": weak,
            "summary": {"covered": f"{first['name']} can take over now" if first else "",
                        "interim": f"{first['name']} could act up while being developed" if first else "",
                        "weak": f"Only {first['name']} below, not ready yet" if first else "",
                        "gap": "No one ready to take over: the store would need an outside hire"}[status]}


def search(api, v: dict, limit: int = 12) -> dict:
    """Everyone inside who could fill this vacancy, scored, explained, with the effect of moving them."""
    from ..po.format import leader_name
    t = _target(v)
    pool = Pool(api)
    out = []
    if t["level"] <= 1:
        return {"target": {k: t[k] for k in ("title", "level", "store", "section", "department", "city")}, "level_name": LEVEL_NAME.get(t["level"], ""),
                "candidates": [], "pool": {"leaders": len(pool.leaders), "staff": len(pool.staff)}, "method": "",
                "verdict": {"decision": "external", "title": "Entry-level role: hire from outside",
                            "text": "Associate and cashier seats are filled from outside. Screen CVs below and check the talent bank for past applicants."}}
    for l in pool.leaders:
        lv = _level_of(l.designation)
        if t["level"] >= 2:
            step = t["level"] - lv
            if step not in (0, 1, 2) or (step == 0 and l.store == t["store"]) or (t["level"] == 6 and lv < 4):
                continue
        elif lv > 2:
            continue
        out.append(_score_leader(pool, l, t, lv))
    if t["level"] <= 2:                                           # team leader / associate seats: strong staff can step up
        for s in pool.staff:
            if _level_of(s["designation"]) > 1:
                continue
            out.append(_score_staff(pool, s, t))
    for c in out:
        gap = {"covered": 0, "interim": 6, "weak": 14, "gap": 22}.get((c.get("backfill") or {}).get("status", "covered"), 0) * (1.0 if c["level"] >= CRITICAL else 0.5)
        growth = 5 if c["move"] == "Promotion" else -8           # a promotion grows someone; a transfer only moves the gap
        reloc = -6 if t["store"] and c.get("city") and t["city"] and c["city"] != t["city"] else 0
        c["recommend"] = round(max(0.0, c["fit"] - gap + growth + reloc), 1)
    out.sort(key=lambda c: -c["recommend"])
    out = out[:limit]
    verdict = _verdict(t, out)
    notes = []
    holders = [leader_name(l) for l in pool.leaders if l.store == t["store"] and _level_of(l.designation) == t["level"]
               and (not t["department"] or t["level"] >= 5 or any(canon.department(x) == t["department"] or x == t["section"] for x in l.sections))]
    if holders and t["store"]:
        notes.append(f"{t['store']} already has a {LEVEL_NAME.get(t['level'], t['title'])}{' for ' + (t['section'] or t['department']) if t['department'] and t['level'] < 5 else ''}: "
                     f"{', '.join(holders[:3])}. If this is a replacement, check their succession; if it is a new seat, check the approved manning.")
    if t["level"] <= 2 and not pool.staff:
        notes.append("Only leaders from the P&O review are in the pool. Import the employee roster and attendance so strong associates are considered too.")
    return {"target": {k: t[k] for k in ("title", "level", "store", "section", "department", "city")}, "level_name": LEVEL_NAME.get(t["level"], ""),
            "candidates": out, "verdict": verdict, "pool": {"leaders": len(pool.leaders), "staff": len(pool.staff)}, "notes": notes,
            "method": "Fit = readiness 35% · performance 20% · experience 15% · area 15% · location 5% · conduct 10%. "
                      "The recommendation then subtracts the risk of the seat each person leaves behind."}


def _parts(readiness, performance, experience, area, location, conduct) -> list[dict]:
    p = [("Readiness", readiness, 35), ("Performance", performance, 20), ("Experience", experience, 15), ("Area match", area, 15),
         ("Location", location, 5), ("Conduct", conduct, 10)]
    return [{"label": a, "score": round(_pct(b)), "weight": w} for a, b, w in p]


def _fit(parts: list[dict]) -> float:
    return round(sum(p["score"] * p["weight"] for p in parts) / 100, 1)


def _area(t: dict, sections: list[str]) -> tuple[float, str]:
    if not t["section"]:
        return 70.0, ""
    if t["section"] in sections:
        return 100.0, f"Already runs {t['section']}"
    if t["department"] and any(canon.department(s) == t["department"] for s in sections):
        return 75.0, f"Works in the same department ({t['department']})"
    return 35.0, "Comes from another area: needs a handover in the new section"


def _location(t: dict, store: str) -> tuple[float, str]:
    if not t["store"]:
        return 80.0, ""
    if store == t["store"]:
        return 100.0, "Already in this store"
    if canon.store_city(store) and canon.store_city(store) == t["city"]:
        return 75.0, f"Same city ({t['city']}): an easy transfer"
    return 35.0, f"Would relocate from {canon.store_city(store) or store} to {t['city'] or t['store']}"


def _score_leader(pool: Pool, l, t: dict, lv: int) -> dict:
    from ..po.format import leader_name
    why, watch = [], []
    step = t["level"] - lv
    move = "Promotion" if step >= 1 else "Transfer at the same level"
    readiness = l.score if l.score is not None else 50.0
    if step == 2 and t["level"] == 6 and lv == 4:
        readiness -= 8
        watch.append("Skips the deputy level: support them in the first months")
    elif step == 2:
        readiness -= 20
        watch.append(f"Two levels up from {l.designation}: a big step")
    rating = l.latest_rating
    performance = ((rating - 1) / 4 * 100) if rating is not None else 50.0
    if rating is None:
        watch.append("No rating on file")
    elif rating >= 4:
        why.append(f"Rated {rating:g} ({l.rating_label})")
    elif rating <= 2:
        watch.append(f"Rated {rating:g} ({l.rating_label})")
    m = l.months_in_role
    experience = 50.0 if m is None else 30.0 if m < 6 else 60.0 if m < 12 else 100.0 if m <= 48 else 85.0
    if m is not None and m >= 12:
        why.append(f"{m // 12} yr{'s' if m >= 24 else ''} {m % 12} mo as {l.designation}")
    elif m is not None:
        watch.append(f"Only {m} months in the current role")
    area, a_txt = _area(t, l.sections)
    (why if area >= 75 else watch).append(a_txt) if a_txt else None
    location, loc_txt = _location(t, l.store)
    (why if location >= 75 else watch).append(loc_txt) if loc_txt else None
    da = l.kpis.get("da") or 0
    conduct = 100 - min(70, da * 12)
    if da >= 3:
        watch.append(f"{da} disciplinary cases in their area")
    if l.score is not None and l.score >= 70:
        why.insert(0, f"Leader index {l.score / 10:.1f}/10 (top performers start at 7)")
    elif l.score is not None and l.score < 50:
        watch.insert(0, f"Leader index {l.score / 10:.1f}/10")
    for k, label in (("sales", "sales vs budget"), ("productivity", "productivity"), ("shrink", "shrinkage")):
        c = l.components.get(k)
        if c is not None and c >= 80:
            why.append(f"Strong {label} in their area ({c / 10:.1f}/10)")
    fr = pool.risk.get(l.key)
    if fr and fr["band"] == "High" and step >= 1:
        why.append("At risk of leaving: a promotion would help keep them")
    if l.acting:
        why.append("Already acting in a bigger role")
    parts = _parts(readiness, performance, experience, area, location, conduct)
    bf = chain(pool, l)
    if step == 0:
        watch.append("A sideways move: it fills this seat but opens the same gap in their store")
    if bf["status"] in ("gap", "weak") and lv >= CRITICAL:
        watch.append(f"Their move leaves {bf['seat']} without a ready successor")
    return {"source": "leader", "key": l.key, "emp": l.employee_id, "name": leader_name(l), "designation": l.designation, "level": lv,
            "store": l.store, "city": canon.store_city(l.store), "leads": l.section_text, "grade": l.grade, "manager": l.manager_name,
            "joined": l.joining_date.isoformat() if l.joining_date else None, "service_months": l.months_service,
            "in_role_months": l.months_in_role, "role_since": l.role_since.isoformat() if l.role_since else None,
            "ratings": [{"cycle": r.get("cycle"), "rating": r.get("rating"), "label": r.get("rating_label")} for r in sorted(l.ratings, key=lambda r: r.get("cycle") or 0)],
            "index": l.score, "components": {k: round(v / 10, 1) for k, v in l.components.items() if v is not None},
            "flight_risk": fr["band"] if fr else None, "training": pool.training.get(str(l.employee_id), [])[:5],
            "notes": pool.notes.get(str(l.key).casefold(), 0) + pool.notes.get(leader_name(l).casefold(), 0),
            "move": move, "parts": parts, "fit": _fit(parts), "why": why[:6], "watch": watch[:5], "backfill": bf}


def _score_staff(pool: Pool, s: dict, t: dict) -> dict:
    why, watch = [], []
    sc = s.get("score")
    readiness = sc * 10 if sc is not None else 45.0
    if sc is not None and sc >= 7.5:
        why.append(f"Person score {sc:.1f}/10 this month")
    elif sc is None:
        watch.append("No monthly score yet")
    service = None
    try:
        service = (date.today() - date.fromisoformat(str(s.get("joining"))[:10])).days // 30
    except (TypeError, ValueError):
        pass
    experience = 50.0 if service is None else 25.0 if service < 6 else 65.0 if service < 18 else 100.0
    if service is not None and service >= 18:
        why.append(f"{service // 12} years with Carrefour")
    area, a_txt = _area(t, [s["section"]] if s.get("section") else [])
    (why if area >= 75 else watch).append(a_txt) if a_txt else None
    location, loc_txt = _location(t, s.get("store") or "")
    (why if location >= 75 else watch).append(loc_txt) if loc_txt else None
    att = s.get("attendance")
    conduct = att if att is not None else 70.0
    if att is not None and att >= 95:
        why.append(f"Attendance {att:.0f}%")
    parts = _parts(readiness, 50.0, experience, area, location, conduct)
    return {"source": "staff", "key": s["emp"], "emp": s["emp"], "name": s["name"], "designation": s.get("designation") or "Associate", "level": 0,
            "store": s.get("store") or "", "city": canon.store_city(s.get("store") or ""), "leads": s.get("section") or "", "grade": s.get("grade") or "",
            "manager": s.get("manager") or "", "joined": s.get("joining"), "service_months": service, "in_role_months": None, "ratings": [],
            "index": None, "components": {}, "flight_risk": None, "training": pool.training.get(s["emp"], [])[:5], "notes": 0,
            "move": "Promotion", "parts": parts, "fit": _fit(parts), "why": why[:5], "watch": watch[:4],
            "backfill": {"status": "covered", "risk": "Low", "summary": "Associate seat: quick to refill from outside", "steps": [], "external_hires": 1,
                         "seat": f"{s.get('designation') or 'Associate'} · {s.get('store')}", "successor": None, "weak_links": 0}}


def _verdict(t: dict, cands: list[dict]) -> dict:
    if not cands:
        return {"decision": "external", "title": "Hire from outside",
                "text": "No one in the company is at the level below this role in P&O's data. Start the external search; the talent bank is checked below."}
    best = cands[0]
    bf = best.get("backfill") or {}
    verb = "Promote" if best["move"] == "Promotion" else "Transfer"
    rec = best["recommend"]
    if rec >= 70 and bf.get("status") == "covered":
        return {"decision": "internal", "title": f"{verb} from within: {best['name']}",
                "text": f"{best['name']} ({best['designation']}, {best['store']}) fits {best['fit']:.0f}/100 and their seat is covered: {bf.get('summary')}. "
                        + (f"The chain of moves ends with {bf.get('external_hires')} entry-level hire." if bf.get("external_hires") else "")}
    if rec >= 65:
        return {"decision": "internal_backfill", "title": f"{verb} {best['name']} and backfill from outside",
                "text": f"{best['name']} fits {best['fit']:.0f}/100, but in their current seat: {bf.get('summary', '')}. Recruit externally for {bf.get('seat')} "
                        "before the move, or pick the next candidate whose seat is covered."}
    if rec >= 55:
        return {"decision": "develop", "title": f"Develop {best['name']}; hire or appoint an interim",
                "text": f"The best internal option is {best['name']} (fit {best['fit']:.0f}/100, {best['move'].lower()}): close, but moving them costs too much or they are "
                        "not ready. Give them an acting role with a development plan, or hire externally now if the seat can't wait."}
    return {"decision": "external", "title": "Hire from outside",
            "text": f"No internal candidate is a good move (best: {best['name']}, fit {best['fit']:.0f}/100, {best['move'].lower()}). Hire externally; "
                    f"keep {best['name']} on a development plan for next time."}
