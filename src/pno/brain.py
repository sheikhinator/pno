"""The People Brain: one page per person, store and section, built from every source P&O has, with links between them,
plus corrections that win over imported files.

Corrections
    'Ali Khan is a Section Manager, not a Team Leader' becomes a row in `corrections` (person, field, value). It is applied
    whenever data is read (P&O review records and the monthly people model), so it survives later imports, shows on
    every screen, and can be undone. Each correction keeps who made it, when, and the value it replaced.

Pages
    person  identity and job with the source of every fact; career timeline; ratings; results of their area; attendance;
            risks; development; notes; links to manager, reports, peers, store and section
    store   people by role, sections and who leads them, results, open vacancies, cases
    section the leader, team, results across stores
The graph view links people to managers, sections and stores.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from typing import Any

from .db import now
from .po import canon

FIELDS = {
    "employee_name": "Name", "designation": "Designation", "store": "Store", "section": "Section", "department": "Department",
    "manager_name": "Reports to", "grade": "Grade", "joining_date": "Joining date", "role_since": "In current role since",
    "status": "Employment status", "left_on": "Leaving date", "rating": "Performance rating",
}
STATUS = ("active", "left")


# ---------------------------------------------------------------------------------------------- corrections
def add_correction(db, emp: str, field: str, value: Any, name: str = "", note: str = "", source: str = "manual",
                   cycle: int | None = None, old: Any = None) -> int:
    if field not in FIELDS:
        raise ValueError(f"Can't correct '{field}'. Choose one of: {', '.join(FIELDS.values())}.")
    emp = str(emp or "").strip()
    if not emp:
        raise ValueError("Which employee? (employee number)")
    v = _clean(field, value)
    key = f"{field}:{cycle}" if field == "rating" and cycle else field
    db.x("UPDATE corrections SET active=0 WHERE emp=? AND field=? AND active=1", (emp, key))
    cid = db.x("INSERT INTO corrections(emp, name, field, value, old_value, note, source, created_at, active) VALUES(?,?,?,?,?,?,?,?,1)",
               (emp, name, key, json.dumps(v), json.dumps(old, default=str), note[:300], source, now())).lastrowid
    db.log("correction", f"{name or emp}: {FIELDS[field]} → {v} ({source})")
    return cid


def _clean(field: str, value: Any) -> Any:
    s = str(value).strip() if value is not None else ""
    if field in ("joining_date", "role_since", "left_on"):
        from .util import parse_date
        d = parse_date(s)
        if not d:
            raise ValueError(f"'{s}' is not a date.")
        return d.isoformat()
    if field == "rating":
        try:
            x = float(s)
        except ValueError as e:
            raise ValueError("A rating is a number from 1 to 5.") from e
        if not 0 <= x <= 5:
            raise ValueError("A rating is a number from 1 to 5.")
        return x
    if field == "status":
        s = s.casefold()
        if s not in STATUS:
            raise ValueError("Status is 'active' or 'left'.")
        return s
    if field == "store":
        return canon.store(s) or s
    if field == "section":
        return canon.section(s) or s
    if not s:
        raise ValueError("The new value is empty.")
    return s


def undo_correction(db, cid: int) -> None:
    db.x("UPDATE corrections SET active=0 WHERE id=?", (cid,))
    db.log("correction undone", str(cid))


def corrections(db, emp: str | None = None) -> list[dict]:
    sql, a = "SELECT * FROM corrections", []
    if emp:
        sql += " WHERE emp=?"
        a.append(str(emp))
    out = []
    for r in db.q(sql + " ORDER BY id DESC LIMIT 500", tuple(a)):
        d = dict(r)
        d["value"] = json.loads(d["value"]) if d["value"] else None
        d["old_value"] = json.loads(d["old_value"]) if d["old_value"] else None
        f, _, cyc = d["field"].partition(":")
        d["label"] = FIELDS.get(f, f) + (f" ({cyc})" if cyc else "")
        out.append(d)
    return out


def active_map(db) -> dict[str, dict[str, Any]]:
    """emp -> {field: value} for the corrections in force."""
    out: dict[str, dict[str, Any]] = defaultdict(dict)
    try:
        rows = db.q("SELECT emp, field, value FROM corrections WHERE active=1 ORDER BY id")
    except Exception:  # noqa: BLE001 - an old database before the table existed
        return {}
    for r in rows:
        out[str(r["emp"])][r["field"]] = json.loads(r["value"])
    return out


def apply_po(records: list[dict], kind: str, cmap: dict[str, dict[str, Any]]) -> list[dict]:
    """Corrections applied to P&O review records as they are read."""
    if not cmap:
        return records
    out = []
    for r in records:
        e = str(r.get("employee_id") or "")
        c = cmap.get(e)
        if not c:
            out.append(r)
            continue
        if c.get("status") == "left" and kind in ("po_master", "po_role"):
            continue                                        # people who have left are not on the master any more
        r = dict(r)
        if kind in ("po_master", "po_role", "po_rating", "po_turnover", "po_shift"):
            for f in ("employee_name", "designation", "store", "manager_name", "grade"):
                if f in c and (f in r or kind in ("po_master", "po_role")):
                    r[f] = c[f]
            if "section" in c:
                r["section"] = c["section"]
                if kind == "po_role":
                    r["sections_led"] = [c["section"]]
            if "department" in c and kind in ("po_master", "po_role"):
                r["department"] = c["department"]
            if kind == "po_master" and "joining_date" in c:
                r["joining_date"] = c["joining_date"]
            if kind == "po_role" and "role_since" in c:
                r["role_since"] = c["role_since"]
            if kind == "po_role" and "designation" in c:
                r["working_as"] = ""
                r["designation_mismatch"] = False
        if kind == "po_rating":
            cyc = r.get("cycle")
            if f"rating:{cyc}" in c:
                r["rating"] = c[f"rating:{cyc}"]
                r["rating_label"] = r.get("rating_label") or "Corrected"
        out.append(r)
    if kind == "po_turnover":
        have = {str(x.get("employee_id")) for x in out}
        latest = max(out, key=lambda x: x.get("_iid") or 0) if out else None
        for e, c in cmap.items():
            if c.get("status") == "left" and e not in have:
                lo = c.get("left_on")
                meta = ({k: latest[k] for k in ("_iid", "_ptype", "_pfrom", "_pto", "_period", "_sheet") if k in latest} if latest else
                        {"_iid": 0, "_ptype": "ytd", "_pfrom": (lo or date.today().isoformat())[:4] + "-01", "_pto": (lo or date.today().isoformat())[:7], "_period": "corr"})
                if latest and lo and (meta.get("_pto") or "") < lo[:7]:
                    meta["_pto"] = lo[:7]
                out.append({"employee_id": e, "employee_name": c.get("employee_name") or e, "date": lo, "store": c.get("store", ""),
                            "section": c.get("section", ""), "exit_type": "Recorded in P&O", "reason": "Corrected by P&O", "voluntary": False,
                            "_kind": "po_turnover", "_source": "Correction", **meta})
    return out


def apply_people(people: dict, cmap: dict[str, dict[str, Any]], stores_by_name: dict[str, dict]) -> None:
    """Corrections applied to the monthly people model (engine)."""
    for e, c in cmap.items():
        p = people.get(e)
        if p is None:
            continue
        if c.get("status") == "left":
            people.pop(e, None)
            continue
        if "employee_name" in c:
            p.name = c["employee_name"]
        if "designation" in c:
            p.designation = c["designation"]
        if "manager_name" in c:
            p.manager_name = c["manager_name"]
        if "grade" in c:
            p.grade = c["grade"]
        if "section" in c:
            p.section = c["section"]
        if "joining_date" in c:
            p.joining = c["joining_date"]
        if "store" in c:
            st = stores_by_name.get(c["store"]) or stores_by_name.get(canon.store(c["store"]))
            if st:
                p.store_id, p.store, p.store_format, p.city = st["id"], st["name"], st.get("format", ""), st.get("city", "")


# ---------------------------------------------------------------------------------------------- the directory
class Brain:
    """Everyone and everything P&O knows, joined by employee number."""

    def __init__(self, api):
        self.api = api
        self.db = api.db
        self.ins = api._po()
        self.cmap = active_map(self.db)
        self.people: dict[str, dict] = {}
        self._load()

    def _p(self, emp: str, name: str = "") -> dict:
        p = self.people.get(emp)
        if p is None:
            p = self.people[emp] = {"emp": emp, "name": name, "facts": {}, "sources": set(), "ratings": [], "left": None, "leader": None,
                                    "person": None}
        if name and not p["name"]:
            p["name"] = name
        return p

    def _fact(self, p: dict, field: str, value: Any, source: str, when: str | None = None) -> None:
        if value in (None, "", []):
            return
        if field not in p["facts"]:
            p["facts"][field] = {"value": value, "source": source, "when": when}
        p["sources"].add(source)

    def _load(self) -> None:
        ins = self.ins
        if not ins.empty:
            for r in ins.rows("po_master"):
                e = str(r.get("employee_id") or "")
                if not e:
                    continue
                p = self._p(e, r.get("employee_name") or "")
                src = r.get("_source") or "Basic Sheet"
                for f in ("designation", "store", "department", "section", "grade", "manager_name", "joining_date", "gender"):
                    self._fact(p, f, r.get(f), src)
            for r in ins.rows("po_role"):
                e = str(r.get("employee_id") or "")
                if not e:
                    continue
                p = self._p(e, r.get("employee_name") or "")
                src = r.get("_source") or "Time in role"
                for f in ("designation", "store", "section", "role_since", "remarks"):
                    self._fact(p, f, r.get(f), src)
            for r in ins.rows("po_rating"):
                e = str(r.get("employee_id") or "")
                if e:
                    p = self._p(e, r.get("employee_name") or "")
                    p["ratings"].append({"cycle": r.get("cycle"), "rating": r.get("rating"), "label": r.get("rating_label"), "form": r.get("form"),
                                         "manager": r.get("manager_name")})
                    self._fact(p, "manager_name", r.get("manager_name"), r.get("_source") or "Performance rating")
            for r in ins.rows("po_turnover"):
                e = str(r.get("employee_id") or "")
                if e:
                    p = self._p(e, r.get("employee_name") or "")
                    p["left"] = {"date": r.get("date"), "type": r.get("exit_type"), "reason": r.get("reason"), "store": r.get("store"), "source": r.get("_source")}
                    self._fact(p, "store", r.get("store"), r.get("_source") or "Turnover")
                    self._fact(p, "section", r.get("section"), r.get("_source") or "Turnover")
            for l in ins.leaders():
                if l.employee_id:
                    p = self._p(str(l.employee_id), l.name)
                    p["leader"] = l
        try:
            from . import analytics, engine
            ms = analytics.month_list(self.db)
            if ms:
                mm = engine.model(self.db, ms[0]["value"])
                for x in mm.people.values():
                    p = self._p(str(x.emp), x.name)
                    p["person"] = x
                    st = (canon.store(x.store) or x.store) if x.store else ""
                    if st and x.store_format == "HB" and not st.endswith("· Myli"):
                        st = f"{st.replace(' · Myli', '')} · Myli"
                    for f, v in (("designation", x.designation), ("store", st), ("section", canon.section(x.section) or x.section),
                                 ("grade", x.grade), ("manager_name", x.manager_name), ("joining_date", x.joining), ("gender", x.gender)):
                        self._fact(p, f, v, "Employee roster")
        except Exception:  # noqa: BLE001
            pass
        for e, c in self.cmap.items():                       # corrections win, and say so
            p = self._p(e, c.get("employee_name", ""))
            for f, v in c.items():
                if f.startswith("rating:"):
                    continue
                p["facts"][f] = {"value": v, "source": "Corrected by P&O", "when": None, "corrected": True}
            if c.get("status") == "left":
                p["left"] = p["left"] or {"date": c.get("left_on"), "type": "Recorded in P&O", "reason": "", "source": "Correction"}
        for p in self.people.values():
            if p["facts"].get("employee_name"):
                p["name"] = p["facts"]["employee_name"]["value"]
            p["name"] = canon.repair_name(p["name"]) or p["emp"]

    # -------------------------------------------------------------------------------------- lookups
    def find(self, q: str, limit: int = 30) -> list[dict]:
        q = str(q or "").strip().casefold()
        out = []
        for p in self.people.values():
            f = p["facts"]
            hay = " ".join([p["emp"], p["name"]] + [str(f.get(k, {}).get("value", "")) for k in ("designation", "store", "section")]).casefold()
            if not q or q in hay:
                out.append(self._row(p))
        out.sort(key=lambda r: (-(r["level"] or 0), r["name"]))
        return out[:limit]

    def _row(self, p: dict) -> dict:
        f = p["facts"]
        g = lambda k: (f.get(k) or {}).get("value", "")  # noqa: E731
        l = p["leader"]
        return {"emp": p["emp"], "name": p["name"], "designation": g("designation"), "store": g("store"), "section": g("section"),
                "level": canon.role_rank(g("designation")), "left": bool(p["left"]), "index": l.score if l else None,
                "score": p["person"].score if p["person"] else None}

    def resolve(self, who: str) -> dict | None:
        """An employee number, or a name (unique match)."""
        w = str(who or "").strip()
        if w in self.people:
            return self.people[w]
        m = re.search(r"\d{5,10}", w)
        if m and m.group(0) in self.people:
            return self.people[m.group(0)]
        k = canon.name_key(w)
        exact = [p for p in self.people.values() if canon.name_key(p["name"]) == k]
        if len(exact) == 1:
            return exact[0]
        part = [p for p in self.people.values() if k and k in canon.name_key(p["name"])]
        return part[0] if len(part) == 1 else None

    def candidates(self, who: str) -> list[dict]:
        k = canon.name_key(who)
        return [self._row(p) for p in self.people.values() if k and k in canon.name_key(p["name"])][:8]

    # -------------------------------------------------------------------------------------- pages
    def person_page(self, emp: str) -> dict:
        p = self.people.get(str(emp))
        if not p:
            raise ValueError("Person not found.")
        f = p["facts"]
        g = lambda k: (f.get(k) or {}).get("value", "")  # noqa: E731
        l, x = p["leader"], p["person"]
        facts = [{"field": k, "label": FIELDS.get(k, k.replace("_", " ").title()), **v} for k, v in f.items() if k not in ("employee_name", "gender", "status", "left_on")]
        order = ["designation", "store", "department", "section", "manager_name", "grade", "joining_date", "role_since", "remarks"]
        facts.sort(key=lambda d: order.index(d["field"]) if d["field"] in order else 99)
        today = date.today()

        def months_since(s):
            try:
                d = date.fromisoformat(str(s)[:10])
                return (today.year - d.year) * 12 + today.month - d.month
            except (TypeError, ValueError):
                return None
        service, in_role = months_since(g("joining_date")), months_since(g("role_since"))
        timeline = []
        if g("joining_date"):
            timeline.append({"date": g("joining_date"), "what": "Joined Carrefour", "kind": "join"})
        if g("role_since"):
            timeline.append({"date": g("role_since"), "what": f"Started as {g('designation') or 'current role'}", "kind": "role"})
        for r in sorted(p["ratings"], key=lambda r: r.get("cycle") or 0):
            if r.get("cycle"):
                timeline.append({"date": f"{r['cycle']}-12-31", "what": f"{r['cycle']} rating: {r['rating'] if r['rating'] is not None else 'unrated'}"
                                 + (f" ({r['label']})" if r.get("label") else ""), "kind": "rating"})
        if p["left"]:
            timeline.append({"date": p["left"].get("date") or "", "what": f"Left: {p['left'].get('type') or ''} {('· ' + p['left']['reason']) if p['left'].get('reason') else ''}".strip(), "kind": "left"})
        extra = self._activity(p)
        timeline += extra["timeline"]
        timeline.sort(key=lambda t: t["date"] or "")
        # peers and percentile
        peers = [q for q in self.people.values() if q is not p and q["leader"] is not None and canon.role_rank((q["facts"].get("designation") or {}).get("value", "")) == canon.role_rank(g("designation"))]
        pct = None
        if l and l.score is not None:
            sc = [q["leader"].score for q in peers if q["leader"].score is not None]
            pct = round(100 * sum(1 for s in sc if s < l.score) / len(sc)) if sc else None
        reports = [self._row(q) for q in self.people.values() if canon.name_key((q["facts"].get("manager_name") or {}).get("value", "")) == canon.name_key(p["name"]) and q is not p]
        manager = self.resolve(g("manager_name")) if g("manager_name") else None
        same_section = [self._row(q) for q in self.people.values() if q is not p and (q["facts"].get("section") or {}).get("value") == g("section")
                        and (q["facts"].get("store") or {}).get("value") == g("store") and g("section")][:12]
        insights = self._insights(p, pct, service, in_role, extra)
        return {"emp": p["emp"], "name": p["name"], "designation": g("designation"), "store": g("store"), "section": g("section"),
                "department": g("department") or canon.department(g("section")), "manager": g("manager_name"),
                "manager_emp": manager["emp"] if manager else None, "level": canon.role_rank(g("designation")),
                "service_months": service, "in_role_months": in_role, "left": p["left"], "facts": facts, "sources": sorted(p["sources"]),
                "ratings": sorted(p["ratings"], key=lambda r: r.get("cycle") or 0),
                "index": l.score if l else None, "index_percentile": pct, "peers": len(peers),
                "components": {k: round(v / 10, 1) for k, v in (l.components.items() if l else []) if v is not None},
                "kpis": _kpis(l), "leads": l.section_text if l else "", "acting": bool(l and l.acting),
                "person_score": x.score if x else None, "attendance": _att(x),
                "reports": sorted(reports, key=lambda r: (-(r["level"] or 0), r["name"]))[:40], "team": same_section,
                "timeline": timeline, "corrections": corrections(self.db, p["emp"]), "insights": insights, **extra["blocks"]}

    def _activity(self, p: dict) -> dict:
        db, e, n = self.db, p["emp"], p["name"]
        tl, blocks = [], {}
        try:
            notes = [dict(r) for r in db.q("SELECT kind, met_on, body, follow_up, mood FROM meetings WHERE subject_key=? OR lower(subject)=lower(?) ORDER BY met_on DESC",
                                           (e, n))]
        except Exception:  # noqa: BLE001
            notes = []
        blocks["notes"] = notes[:20]
        for m in notes:
            tl.append({"date": m["met_on"], "what": f"{m['kind']}: {(m['body'] or '')[:90]}", "kind": "note"})
        blocks["training"] = [dict(r) for r in db.q("""SELECT c.title, a.status, a.score, a.assigned_at, a.completed_at FROM assignments a JOIN courses c ON c.id=a.course_id
                                                       WHERE a.person=? OR lower(a.person_name)=lower(?) ORDER BY a.id DESC""", (e, n))]
        for t in blocks["training"]:
            tl.append({"date": (t.get("completed_at") or t.get("assigned_at") or "")[:10], "what": f"Training: {t['title']} ({t['status']})", "kind": "training"})
        blocks["actions"] = [dict(r) for r in db.q("SELECT title, status, due FROM actions WHERE lower(owner)=lower(?) ORDER BY id DESC LIMIT 15", (n,))]
        blocks["goals"] = [dict(r) for r in db.q("SELECT title, current, target, due, status FROM goals WHERE lower(owner)=lower(?) ORDER BY id DESC LIMIT 15", (n,))]
        try:
            blocks["cases"] = [dict(r) for r in db.q("SELECT id, kind, category, stage, outcome, opened_on FROM er_cases WHERE emp=? ORDER BY id DESC", (e,))]
            for c in blocks["cases"]:
                tl.append({"date": c["opened_on"], "what": f"{c['kind']} case: {c['category']} ({c['outcome'] or c['stage']})", "kind": "case"})
        except Exception:  # noqa: BLE001
            blocks["cases"] = []
        try:
            blocks["letters"] = [dict(r) for r in db.q("SELECT kind, ref, created_at FROM letters WHERE emp=? ORDER BY id DESC", (e,))]
            for x in blocks["letters"]:
                tl.append({"date": x["created_at"][:10], "what": f"Letter: {x['kind']} ({x['ref']})", "kind": "letter"})
        except Exception:  # noqa: BLE001
            blocks["letters"] = []
        blocks["hiring"] = [dict(r) for r in db.q("""SELECT v.title, a.stage, a.score FROM applications a JOIN candidates c ON c.id=a.candidate_id
                                                    JOIN vacancies v ON v.id=a.vacancy_id WHERE c.source='Internal' AND json_extract(c.parsed,'$.emp')=?""", (e,))]
        return {"timeline": tl, "blocks": blocks}

    def _insights(self, p: dict, pct, service, in_role, extra) -> dict:
        l = p["leader"]
        strengths, risks, next_steps = [], [], []
        if l and l.score is not None:
            if l.score >= 70:
                strengths.append(f"Leader index {l.score / 10:.1f}/10" + (f", better than {pct}% of peers" if pct is not None else ""))
            elif l.score < 50:
                risks.append(f"Leader index {l.score / 10:.1f}/10" + (f", below {100 - pct}% of peers" if pct is not None else ""))
            for k, label in (("sales", "Sales vs budget"), ("productivity", "Productivity"), ("shrink", "Shrinkage"), ("stock_days", "Stock days"),
                             ("retention", "Keeping people")):
                c = l.components.get(k)
                if c is None:
                    continue
                if c >= 85:
                    strengths.append(f"{label} in their area: {c / 10:.1f}/10")
                elif c < 50:
                    risks.append(f"{label} in their area: {c / 10:.1f}/10")
                    next_steps.append(f"Coaching or training on {label.lower()} (Learning Studio → Training needs)")
        rated = [r for r in p["ratings"] if r.get("rating") is not None]
        if rated:
            last = sorted(rated, key=lambda r: r.get("cycle") or 0)[-1]
            (strengths if last["rating"] >= 4 else risks if last["rating"] <= 2 else []).append(f"{last['cycle']} rating {last['rating']:g}")
            if len(rated) >= 2:
                a, b = sorted(rated, key=lambda r: r.get("cycle") or 0)[-2:]
                if b["rating"] > a["rating"]:
                    strengths.append(f"Rating improved from {a['rating']:g} to {b['rating']:g}")
                elif b["rating"] < a["rating"]:
                    risks.append(f"Rating fell from {a['rating']:g} to {b['rating']:g}")
        else:
            risks.append("No performance rating on file")
            next_steps.append("Make sure they are rated in the next cycle")
        if in_role is not None and in_role >= 36 and l and (l.score or 0) >= 65:
            next_steps.append(f"{in_role // 12} years in role with good results: discuss the next move (check Succession)")
        if in_role is not None and in_role < 6:
            next_steps.append("New in role: monthly 1:1s for the first 6 months")
        if l and l.acting:
            risks.append("Doing a bigger role without the title")
            next_steps.append("Regularise the role or the title")
        if not extra["blocks"]["notes"] and l:
            next_steps.append("No 1:1 on record: book one")
        if extra["blocks"].get("cases"):
            open_c = [c for c in extra["blocks"]["cases"] if c["stage"] != "Closed"]
            if open_c:
                risks.append(f"{len(open_c)} open employee-relations case(s)")
        try:
            from .po.people_risk import flight_risk
            fr = next((r for r in flight_risk(self.ins) if l and r["key"] == l.key), None)
        except Exception:  # noqa: BLE001
            fr = None
        if fr and fr["band"] == "High":
            risks.append("High flight risk: " + "; ".join(fr["reasons"][:2]))
            next_steps.append("Stay conversation this month")
        return {"strengths": strengths[:6], "risks": risks[:6], "next_steps": list(dict.fromkeys(next_steps))[:6],
                "flight_risk": fr["band"] if fr else None, "flight_reasons": fr["reasons"] if fr else []}

    def store_page(self, store: str) -> dict:
        people = [q for q in self.people.values() if (q["facts"].get("store") or {}).get("value") == store and not q["left"]]
        rows = sorted((self._row(q) for q in people), key=lambda r: (-(r["level"] or 0), r["name"]))
        by_section: dict[str, list] = defaultdict(list)
        for r in rows:
            by_section[r["section"] or "—"].append(r)
        card = next((c for c in (self.ins.store_scorecard() if not self.ins.empty else []) if c["store"] == store), None)
        left = [self._row(q) for q in self.people.values() if q["left"] and (q["left"].get("store") or (q["facts"].get("store") or {}).get("value")) == store]
        return {"store": store, "city": canon.store_city(store), "format": canon.store_format(store), "people": rows, "sections": dict(by_section),
                "card": card, "leavers": left[:40],
                "vacancies": [dict(r) for r in self.db.q("SELECT id, title, status FROM vacancies WHERE store=? AND status='open'", (store,))]}

    def graph(self, store: str = "", leaders_only: bool = True) -> dict:
        nodes, edges, seen = [], [], set()

        def add(nid, label, kind, extra=None):
            if nid not in seen:
                seen.add(nid)
                nodes.append({"id": nid, "label": label, "kind": kind, **(extra or {})})
        for p in self.people.values():
            r = self._row(p)
            if p["left"] or (leaders_only and (r["level"] or 0) < 1 and not p["leader"]):
                continue
            if store and r["store"] != store:
                continue
            pid = f"p:{p['emp']}"
            add(pid, p["name"], "person", {"level": r["level"], "role": r["designation"], "emp": p["emp"], "index": r["index"]})
            if r["store"]:
                add(f"s:{r['store']}", r["store"], "store")
                if r["section"]:
                    sid = f"x:{r['store']}|{r['section']}"
                    add(sid, r["section"], "section", {"store": r["store"]})
                    edges.append({"a": sid, "b": f"s:{r['store']}", "kind": "in"})
                    edges.append({"a": pid, "b": sid, "kind": "works"})
                else:
                    edges.append({"a": pid, "b": f"s:{r['store']}", "kind": "works"})
            m = self.resolve((p["facts"].get("manager_name") or {}).get("value", ""))
            if m and m is not p:
                edges.append({"a": pid, "b": f"p:{m['emp']}", "kind": "reports"})
        ids = {n["id"] for n in nodes}
        edges = [e for e in edges if e["a"] in ids and e["b"] in ids]
        return {"nodes": nodes, "edges": edges}


def _kpis(l) -> list[dict]:
    if not l:
        return []
    out = []
    for k, v in (l.kpis or {}).items():
        if isinstance(v, (int, float)) and k not in ("leaver_rows",):
            out.append({"key": k, "value": v})
    return out


def _att(x) -> dict | None:
    if not x or not x.att:
        return None
    a = x.att
    return {k: a.get(k) for k in ("worked", "absent", "leave", "off", "fixes", "presence", "compliance", "full_days", "short_days")}


# ---------------------------------------------------------------------------------------------- the profile sheet
def profile_report(page: dict, include_notes: bool = False) -> dict:
    """A complete, shareable profile: who, where, how they are doing and what to do next."""
    from .exports import table_report
    from .period import month_label  # noqa: F401
    rep = table_report("Employee profile", [], [], "Confidential · People & Organisation")
    lv = page.get("level") or 0
    sm = page.get("service_months")
    rm = page.get("in_role_months")
    yrs = lambda m: "—" if m is None else f"{m // 12} yr {m % 12} mo"  # noqa: E731
    secs: list[dict] = [{"type": "heading", "title": page["name"], "sub": f"{page['designation'] or ''} · {page['store'] or ''}" +
                         (f" · {page['section']}" if page.get("section") else "") + f" · Employee {page['emp']}"}]
    k = [{"label": "With Carrefour", "value": yrs(sm), "sub": ""}, {"label": "In current role", "value": yrs(rm), "sub": ""}]
    if page.get("index") is not None:
        k.append({"label": "Leader index", "value": f"{page['index'] / 10:.1f}/10",
                  "sub": f"better than {page['index_percentile']}% of {page['peers']} peers" if page.get("index_percentile") is not None else ""})
    rated = [r for r in page.get("ratings", []) if r.get("rating") is not None]
    if rated:
        k.append({"label": f"{rated[-1]['cycle']} rating", "value": f"{rated[-1]['rating']:g} / 5", "sub": rated[-1].get("label") or ""})
    if page.get("insights", {}).get("flight_risk"):
        k.append({"label": "Flight risk", "value": page["insights"]["flight_risk"], "sub": ""})
    secs.append({"type": "kpis", "items": k[:5]})
    facts = [[f["label"], str(f["value"]), f["source"] + (" (corrected)" if f.get("corrected") else "")] for f in page.get("facts", [])]
    secs.append({"type": "table", "title": "Profile", "columns": [("Detail", "c0", ""), ("Value", "c1", ""), ("Source", "c2", "")],
                 "rows": [{"c0": a, "c1": b, "c2": c} for a, b, c in facts]})
    ins = page.get("insights") or {}
    if ins.get("strengths"):
        secs.append({"type": "text", "title": "Strengths", "lines": ins["strengths"]})
    if ins.get("risks"):
        secs.append({"type": "text", "title": "Watch-outs", "lines": ins["risks"]})
    if ins.get("next_steps"):
        secs.append({"type": "text", "title": "Recommended next steps", "lines": ins["next_steps"]})
    if len(rated) >= 2:
        secs.append({"type": "chart", "kind": "line", "title": "Performance rating by year", "labels": [str(r["cycle"]) for r in rated],
                     "series": [{"name": "Rating (1-5)", "values": [r["rating"] for r in rated]}]})
    comp = page.get("components") or {}
    if comp:
        names = {"sales": "Sales vs budget", "productivity": "Productivity", "shrink": "Shrinkage", "stock_days": "Stock days", "rating": "Rating",
                 "retention": "Keeping people", "nps": "Customer NPS"}
        secs.append({"type": "chart", "kind": "hbar", "title": f"Results of their area ({page.get('leads') or 'area'}) · out of 10",
                     "labels": [names.get(a, a) for a in comp], "series": [{"name": "Score /10", "values": list(comp.values())}]})
    att = page.get("attendance")
    if att:
        secs.append({"type": "kpis", "title": "Attendance (latest month)", "items": [
            {"label": "Days worked", "value": str(att.get("worked") or 0), "sub": ""},
            {"label": "Absent", "value": str(att.get("absent") or 0), "sub": "unexplained"},
            {"label": "Presence", "value": f"{att['presence']:.0f}%" if att.get("presence") is not None else "—", "sub": ""},
            {"label": "Full 9-hour days", "value": f"{att['compliance']:.0f}%" if att.get("compliance") is not None else "—", "sub": ""}]})
    if page.get("timeline"):
        secs.append({"type": "table", "title": "Career and activity", "columns": [("Date", "d", ""), ("What happened", "w", "")],
                     "rows": [{"d": t["date"][:10] if t.get("date") else "", "w": t["what"]} for t in page["timeline"] if include_notes or t["kind"] != "note"]})
    if page.get("training"):
        secs.append({"type": "table", "title": "Training", "columns": [("Course", "title", ""), ("Status", "status", ""), ("Score", "score", "int")],
                     "rows": page["training"]})
    if page.get("reports"):
        secs.append({"type": "table", "title": f"Direct reports ({len(page['reports'])})", "columns": [("Name", "name", ""), ("Role", "designation", ""), ("Section", "section", "")],
                     "rows": page["reports"][:30]})
    if include_notes and page.get("notes"):
        secs.append({"type": "table", "title": "1:1s and visits", "columns": [("Date", "met_on", ""), ("Type", "kind", ""), ("Notes", "body", ""), ("Follow-up", "follow_up", "")],
                     "rows": page["notes"]})
    rep.update({"pack": "profile", "title": f"Employee profile · {page['name']}", "subtitle": f"Confidential · prepared {date.today():%d %b %Y}",
                "month_label": date.today().strftime("%d %b %Y"), "sections": secs, "sources": [f"Sources: {', '.join(page.get('sources') or [])}"]})
    return rep
