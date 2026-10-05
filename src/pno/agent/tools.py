"""What the AI may do: read PNO's numbers (never change them) and propose changes that the user confirms."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from .. import analytics, engine
from ..org import ROLE_LABEL
from ..util import norm, parse_date

SQL_HELP = """Tables (SQLite, read-only):
  people(emp, name, store, city, format, dept_code, dept, section, designation, grade, gender, role, role_label, score,
         band, coverage, attendance_score, presence_pct, compliance_pct, worked_days, absent_days, leave_days, off_days,
         punches_to_fix, longest_absence, avg_hours, sales_vs_budget_pct, productivity_vs_target_pct, oos_pct, waste_pct,
         manager_emp, manager_name, joining)      -- one row per person for the selected month
  attendance(emp_no, day, status, minutes, t_in, t_out)  -- status: present|manual|missing_in|missing_out|punched_absent|no_punch
  sales(store, month, as_of, level, code, name, dept, actual, budget, growth, ly, waste, oos, margin_net, customers)
        -- level: section|dept|store; latest MTD per month; code: S011.., D01..D05, STORE
  productivity(store, month, row_code, row_name, actual, target, ly)
  stores(id, name, format, city)
  leaves(emp_no, d_from, d_to, type)   holidays(day, name)"""

TOOLS: list[dict] = [
    {"name": "overview", "description": "Headline numbers for the month and filters: headcount, real absence, average score, "
     "sales vs budget, productivity, score bands, store league, alerts. Start here for general questions.",
     "parameters": {"type": "object", "properties": {
         "month": {"type": "string", "description": "YYYY-MM; omit for the month on screen"},
         "city": {"type": "string"}, "store": {"type": "string", "description": "store name"},
         "format": {"type": "string", "enum": ["HM", "SM", "HB"]}, "dept": {"type": "string", "description": "01..06, 11, 99"}}}},
    {"name": "find_people", "description": "List people with their score, role, store and attendance, filtered and sorted. "
     "Use for rankings (top / bottom), searching by name and lists like 'most absent'.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "part of a name, an employee number or designation"},
         "store": {"type": "string"}, "city": {"type": "string"}, "dept": {"type": "string"},
         "role": {"type": "string", "enum": ["GM", "HBM", "DH", "SM", "CCO", "STAFF", "MANAGERS"]},
         "sort": {"type": "string", "enum": ["score", "attendance", "absent", "fixes", "name"]},
         "ascending": {"type": "boolean"}, "limit": {"type": "integer"}, "month": {"type": "string"}}}},
    {"name": "person", "description": "Everything about one person: score breakdown, attendance, manager, team, history.",
     "parameters": {"type": "object", "properties": {"who": {"type": "string", "description": "name or employee number"},
                                                     "month": {"type": "string"}}, "required": ["who"]}},
    {"name": "store", "description": "One store: GM, departments and sections with their managers, KPIs, attendance.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "month": {"type": "string"}}, "required": ["name"]}},
    {"name": "attendance", "description": "Attendance health for the filters: real vs system absence, punches to fix, "
     "long absences, 9-hour compliance, worst stores.",
     "parameters": {"type": "object", "properties": {"month": {"type": "string"}, "store": {"type": "string"},
                                                     "city": {"type": "string"}, "dept": {"type": "string"}}}},
    {"name": "trend", "description": "Month-by-month history (up to 12 months) of average score, absence and sales vs budget.",
     "parameters": {"type": "object", "properties": {"store": {"type": "string"}, "city": {"type": "string"}, "dept": {"type": "string"}}}},
    {"name": "sql", "description": "Run one read-only SQL SELECT for questions the other tools cannot answer. " + SQL_HELP,
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "month": {"type": "string"}}, "required": ["query"]}},
    {"name": "chart", "description": "Show a chart under the answer. Use for comparisons and trends.",
     "parameters": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": ["bar", "hbar", "line"]}, "title": {"type": "string"},
         "labels": {"type": "array", "items": {"type": "string"}},
         "series": {"type": "array", "items": {"type": "object", "properties": {
             "name": {"type": "string"}, "values": {"type": "array", "items": {"type": "number"}}}}}},
         "required": ["kind", "title", "labels", "series"]}},
    {"name": "propose_leave", "description": "Prepare leave entries for the user to confirm (nothing is saved until they click Confirm).",
     "parameters": {"type": "object", "properties": {"entries": {"type": "array", "items": {"type": "object", "properties": {
         "who": {"type": "string", "description": "employee number or exact name"}, "from": {"type": "string", "description": "YYYY-MM-DD"},
         "to": {"type": "string", "description": "YYYY-MM-DD"}, "type": {"type": "string"}}, "required": ["who", "from"]}}},
         "required": ["entries"]}},
    {"name": "propose_holiday", "description": "Prepare a gazetted holiday for the user to confirm.",
     "parameters": {"type": "object", "properties": {"day": {"type": "string", "description": "YYYY-MM-DD"},
                                                     "name": {"type": "string"}}, "required": ["day", "name"]}},
    {"name": "propose_note", "description": "Prepare a note on a person's profile for the user to confirm.",
     "parameters": {"type": "object", "properties": {"who": {"type": "string"}, "text": {"type": "string"}}, "required": ["who", "text"]}},
]
WRITE_TOOLS = {"propose_leave", "propose_holiday", "propose_note"}


def openai_tools() -> list[dict]:
    return [{"type": "function", "function": t} for t in TOOLS]


class Toolbox:
    def __init__(self, service, month: str | None, scope: dict, anonymise: bool):
        self.svc = service
        self.db = service.api.db
        self.month = month
        self.scope = dict(scope or {})
        self.anon = anonymise
        self.blocks: list[dict] = []        # tables and charts shown under the answer
        self.actions: list[dict] = []       # changes waiting for Confirm
        self.used: list[str] = []

    # ---------------------------------------------------------------- helpers
    def _mm(self, month=None):
        return engine.model(self.db, month or self.month)

    def _nm(self, p) -> str:
        return f"Employee {p.emp}" if self.anon else p.name

    def _scope(self, args: dict) -> dict:
        sc = dict(self.scope)
        mm = self._mm(args.get("month"))
        if args.get("store"):
            st = self.find_store(mm, args["store"])
            if st:
                sc["store_id"] = st["id"]
        if args.get("city"):
            c = norm(args["city"])
            from ..stores import CITIES
            sc["city"] = next((k for k, v in CITIES.items() if c in (k, norm(v))), c[:3])
        if args.get("format"):
            sc["format"] = args["format"]
        if args.get("dept"):
            sc["dept"] = str(args["dept"]).zfill(2)
        return sc

    @staticmethod
    def find_store(mm, name: str) -> dict | None:
        n = norm(name)
        best, score = None, 0
        for s in mm.stores.values():
            sn = norm(s["name"])
            sc = 3 if sn == n else 2 if n in sn or sn in n else len(set(n.split()) & set(sn.split())) / 2
            if sc > score:
                best, score = s, sc
        return best if score >= 0.5 else None

    def find_person(self, mm, who: str):
        w = str(who).strip()
        if w in mm.people:
            return mm.people[w], []
        m = re.search(r"\d{6,}", w)
        if m and m.group(0) in mm.people:
            return mm.people[m.group(0)], []
        n = norm(w)
        exact = [p for p in mm.people.values() if norm(p.name) == n]
        if len(exact) == 1:
            return exact[0], []
        part = exact or [p for p in mm.people.values() if n and n in norm(p.name)]
        if len(part) == 1:
            return part[0], []
        return None, part[:10]

    def _row(self, p) -> dict:
        a = p.att or {}
        return {"emp": p.emp, "name": self._nm(p), "role": ROLE_LABEL[p.role], "designation": p.designation, "store": p.store,
                "dept": p.dept, "score": None if p.score is None else round(p.score, 1), "band": engine.band(p.score)[0],
                "attendance": a.get("score"), "presence_pct": a.get("presence"), "absent_days": a.get("absent"),
                "punches_to_fix": a.get("fixes")}

    # ---------------------------------------------------------------- tools
    def run(self, name: str, args: dict) -> Any:
        self.used.append(name)
        fn = getattr(self, f"t_{name}", None)
        if not fn:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**(args or {}))
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def t_overview(self, month=None, **kw) -> dict:
        sc = self._scope(kw)
        d = analytics.dashboard(self.db, month or self.month, sc, None, self.anon)
        return {"month": d["month_label"], "scope": d["scope_label"], "data_up_to": d["as_of"],
                "cards": [{c["label"]: c["value"], "change_vs_last_month": c["delta"], "note": c["sub"]} for c in d["cards"]],
                "bands": {x["label"]: x["count"] for x in d["distribution"]},
                "store_league": [{k: r[k] for k in ("store", "format", "people", "score", "gm", "gm_score", "sales_pct", "absence_pct")}
                                 for r in d["league"][:20]],
                "alerts": [a["text"] for a in d["alerts"]]}

    def t_find_people(self, query="", store=None, city=None, dept=None, role="", sort="score", ascending=False, limit=15,
                      month=None) -> dict:
        sc = self._scope({"store": store, "city": city, "dept": dept, "month": month})
        res = analytics.people_list(self.db, month or self.month, sc, query or "", role or "", "", sort or "score",
                                    not ascending, max(1, min(int(limit or 15), 60)), 0, self.anon)
        keep = ("emp", "name", "role_label", "designation", "store", "dept", "score", "band", "attendance", "presence", "absent", "fixes", "delta")
        return {"total_matching": res["total"], "people": [{k: r.get(k) for k in keep} for r in res["rows"]]}

    def t_person(self, who, month=None) -> dict:
        mm = self._mm(month)
        p, cands = self.find_person(mm, who)
        if not p:
            return {"not_found": who, "did_you_mean": [f"{self._nm(c)} ({c.emp}, {c.store})" for c in cands]}
        d = analytics.person(self.db, mm.month, p.emp, self.anon)
        a = d["attendance_detail"] or {}
        return {"emp": d["emp"], "name": d["name"], "designation": d["designation"], "role": d["role_label"], "store": d["store"],
                "measured_on": d["domain"], "score": d["score"], "band": d["band"], "status": d["status"],
                "coverage_pct": d["coverage"], "provisional": d["provisional"],
                "components": [{k: c[k] for k in ("label", "weight", "score", "display", "detail")} for c in d["components"]],
                "context_not_scored": [c["display"] for c in d["context"]],
                "attendance": {k: a.get(k) for k in ("worked", "absent", "leave", "off", "holiday", "fixes", "presence",
                                                    "compliance", "avg_hours", "total_hours", "longest_absence", "sys_absent")},
                "absent_days": [c["day"] for c in a.get("calendar", []) if c["kind"] == "absent"][:31],
                "manager": d["manager"]["name"], "team_size": len(d["team"]),
                "history": [{h["month"]: h["score"]} for h in d["history"]]}

    def t_store(self, name, month=None) -> dict:
        mm = self._mm(month)
        st = self.find_store(mm, name)
        if not st:
            return {"not_found": name, "stores": sorted(s["name"] for s in mm.stores.values())}
        d = analytics.store_detail(self.db, mm.month, st["id"], self.anon)
        return {"store": d["store"], "format": d["format_label"], "city": d["city"], "store_score": d["score"],
                "gm": d["gm"] and {"name": d["gm"]["name"], "score": d["gm"]["score"]}, "total": d["total"],
                "departments": [{k: r[k] for k in ("code", "name", "sales_pct", "growth", "waste", "oos", "prod_pct", "managers")}
                                for r in d["departments"]],
                "sections": [{k: r[k] for k in ("code", "name", "sales_pct", "growth", "waste", "oos", "prod_pct", "managers")}
                             for r in d["sections"]],
                "attendance": {k: d["attendance"][k] for k in ("absence_pct", "system_absence_pct", "fixes", "compliance_pct", "long_absence")},
                "managers": [{k: m[k] for k in ("name", "designation", "score")} for m in d["managers"]]}

    def t_attendance(self, month=None, **kw) -> dict:
        sc = self._scope(kw)
        d = analytics.attendance_view(self.db, month or self.month, sc, self.anon)
        return {"month": d["month_label"], "up_to": d["as_of"], "totals": d["totals"],
                "worst_stores": [{k: r[k] for k in ("store", "absence_pct", "system_absence_pct", "fixes", "compliance_pct")}
                                 for r in d["by_store"][:10]],
                "long_absences": [{k: r[k] for k in ("emp", "name", "store", "longest", "absent")} for r in d["long_absence"][:15]],
                "punches_to_fix_sample": d["fixes"][:15]}

    def t_trend(self, **kw) -> dict:
        sc = self._scope(kw)
        out = []
        for mm in engine.history(self.db, 12):
            ppl = [p for p in mm.people.values() if analytics.in_scope(p, sc)]
            a = analytics.attendance_totals(ppl)
            s = analytics.sales_vs_budget(mm, sc)
            sc_ = [p.score for p in ppl if p.score is not None]
            out.append({"month": mm.month, "avg_score": round(sum(sc_) / len(sc_), 2) if sc_ else None,
                        "real_absence_pct": a["absence_pct"], "sales_vs_budget_pct": s and s["pct"], "headcount": len(ppl)})
        return {"months": out}

    def t_sql(self, query: str, month=None) -> dict:
        q = query.strip().rstrip(";")
        if not re.match(r"^\s*(WITH|SELECT)\b", q, re.I) or ";" in q:
            return {"error": "Only one SELECT statement is allowed."}
        con = self.svc.sql_connection(month or self.month, self.anon)
        try:
            cur = con.execute(q)
            cols = [c[0] for c in cur.description or []]
            rows = cur.fetchmany(200)
            return {"columns": cols, "rows": [list(r) for r in rows], "truncated": len(rows) == 200}
        except sqlite3.Error as e:
            return {"error": f"SQL error: {e}"}
        finally:
            con.close()

    def t_chart(self, kind, title, labels, series) -> dict:
        labels = [str(x) for x in labels][:40]
        clean = []
        for s in series[:4]:
            vals = []
            for v in (s.get("values") or [])[:len(labels)]:
                try:
                    vals.append(None if v is None else float(v))
                except (TypeError, ValueError):
                    vals.append(None)
            clean.append({"name": str(s.get("name", "")), "values": vals})
        self.blocks.append({"type": "chart", "kind": kind if kind in ("bar", "hbar", "line") else "bar", "title": str(title),
                            "labels": labels, "series": clean})
        return {"shown": True}

    # ---------------------------------------------------------------- proposals (need Confirm)
    def t_propose_leave(self, entries: list) -> dict:
        mm = self._mm()
        items, problems = [], []
        for e in entries[:200]:
            p, cands = self.find_person(mm, e.get("who", ""))
            a = parse_date(e.get("from"))
            b = parse_date(e.get("to") or e.get("from"))
            if not p:
                problems.append(f"{e.get('who')}: not found" + (f" (did you mean {', '.join(self._nm(c) for c in cands[:3])}?)" if cands else ""))
                continue
            if not a or not b:
                problems.append(f"{self._nm(p)}: dates not understood")
                continue
            items.append({"emp": p.emp, "name": p.name, "from": min(a, b).isoformat(), "to": max(a, b).isoformat(),
                          "type": e.get("type") or "Leave"})
        if items:
            act = self.svc.new_action("leave", f"Add {len(items)} leave record{'s' if len(items) != 1 else ''}", items)
            self.actions.append(act)
        return {"prepared": len(items), "problems": problems, "note": "Waiting for the user to click Confirm."}

    def t_propose_holiday(self, day, name) -> dict:
        d = parse_date(day)
        if not d:
            return {"error": "date not understood"}
        act = self.svc.new_action("holiday", f"Add holiday: {name} on {d:%d %b %Y}", [{"day": d.isoformat(), "name": name}])
        self.actions.append(act)
        return {"prepared": 1, "note": "Waiting for the user to click Confirm."}

    def t_propose_note(self, who, text) -> dict:
        mm = self._mm()
        p, cands = self.find_person(mm, who)
        if not p:
            return {"not_found": who}
        act = self.svc.new_action("note", f"Add a note to {p.name}'s profile", [{"emp": p.emp, "name": p.name, "text": text}])
        self.actions.append(act)
        return {"prepared": 1, "note": "Waiting for the user to click Confirm."}
