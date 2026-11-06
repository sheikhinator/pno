"""What the AI may do: read P&O's numbers (never change them) and propose changes that the user confirms.

6.0: every number comes from the master sheet, scored exactly as the Review screen scores it (agent/facts.py).
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from .facts import KEYS, Facts

ROLE_ENUM = ["store", "deputy", "dept", "section", "tl"]
CRIT_ENUM = ["score", "sales", "productivity", "shrink", "stock_days", "leavers", "da", "nps", "rating", "name", "time_in_role"]

TOOLS: list[dict] = [
    {"name": "person", "description": "EVERYTHING about one leader (use for any question naming a person, even part of a name): designation, "
     "store, department, grade, joining date, time with the company and in the current role, who they report to, every result in the "
     "master sheet (sales vs budget, productivity, shrink, stock days, leavers, DA cases, NPS, rating) with its status, points and the "
     "benchmark, their score out of 10, category, rank among the same level, ratings by year, what is not filled yet, history.",
     "parameters": {"type": "object", "properties": {"who": {"type": "string", "description": "name (or part of it) or employee number"}},
                    "required": ["who"]}},
    {"name": "people", "description": "List and rank leaders with their score and results. Filter by store, department (Consumer Goods, "
     "Fresh Food, Heavy Household, Non Food…), section, role, format (Hypermarket / Supermarket), category (High / Good / Low / Not scored) "
     "or a name. Sort by score or by one criterion (best first; ascending=true for worst first). Use for top / bottom / who is below / lists.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"}, "store": {"type": "string"}, "dept": {"type": "string"}, "section": {"type": "string"},
         "role": {"type": "string", "enum": ROLE_ENUM, "description": "store managers, deputy managers, department heads, section managers, team leaders"},
         "format": {"type": "string", "enum": ["Hypermarket", "Supermarket"]}, "category": {"type": "string", "enum": ["High", "Good", "Low", "Not scored"]},
         "sort": {"type": "string", "enum": CRIT_ENUM}, "ascending": {"type": "boolean"}, "limit": {"type": "integer"}}}},
    {"name": "store", "description": "One store: its store manager, the store's results against the benchmarks, what is strong / weak / the "
     "focus, each department's results, and every leader in the store with their score and gaps.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "stores", "description": "All stores side by side (store league): store manager, their score and the store's results, leaders and "
     "their average score. Use to compare or rank stores.", "parameters": {"type": "object", "properties": {}}},
    {"name": "overview", "description": "The country picture for the period: country results, what is strong / weak / the focus, how many "
     "leaders are High / Good / Low, average score by level, periods loaded. Start here for general questions.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "review", "description": "The Review screen for any slice: a store, a department (Consumer Goods, Fresh Food, Heavy Household, "
     "Light Household, Textile, Non Food), a section (Bakery, Grocery…) and optionally a role. Returns each criterion with its value and "
     "green/amber/red status, strong / weak / focus notes, the level below and the people table.",
     "parameters": {"type": "object", "properties": {"store": {"type": "string"}, "dept": {"type": "string"}, "section": {"type": "string"},
                    "role": {"type": "string", "enum": ["store", "dept", "section", "tl"]}}}},
    {"name": "data_health", "description": "How complete the master sheet is: filled % per criterion and per store, and who is missing what. "
     "Use for 'what is missing', 'is the data complete', 'why has X no score'.", "parameters": {"type": "object", "properties": {}}},
    {"name": "sql", "description": "One read-only SQL SELECT over table leaders(emp, name, designation, level, role, store, format, city, "
     "department, section, grade, joined, role_since, months_in_role, manager, sales, productivity, shrink, stock_days, leavers, da, nps, "
     "rating, rating_2023, rating_2024, rating_2025, score, category) for questions the other tools cannot answer (counts, averages, "
     "custom filters). Percent columns are numbers (−7.9 means −7.9%).",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "internal_candidates", "description": "Who inside the company could fill a role (store_manager, department_head, "
     "section_manager, team_leader) in a store and department: fit with reasons and what their move leaves behind.",
     "parameters": {"type": "object", "properties": {"role": {"type": "string", "enum": ["store_manager", "department_head", "section_manager", "team_leader"]},
                    "store": {"type": "string"}, "department": {"type": "string"}, "section": {"type": "string"}}, "required": ["role"]}},
    {"name": "hiring", "description": "Hiring: open vacancies, ranked CVs for a vacancy, the talent bank and hiring analytics.",
     "parameters": {"type": "object", "properties": {"vacancy": {"type": "string"}, "search": {"type": "string"}, "skill": {"type": "string"},
                    "city": {"type": "string"}}}},
    {"name": "learning", "description": "Learning: list the courses, or make a new course for a role and topic with the hours wanted.",
     "parameters": {"type": "object", "properties": {"make": {"type": "boolean"}, "topic": {"type": "string"}, "role": {"type": "string"},
                    "hours": {"type": "number"}}}},
    {"name": "kpis", "description": "Show 3-5 headline figures as cards at the top of the answer.",
     "parameters": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
         "label": {"type": "string"}, "value": {"type": "string"}, "sub": {"type": "string"},
         "tone": {"type": "string", "enum": ["good", "warn", "bad", ""]}}, "required": ["label", "value"]}}}, "required": ["items"]}},
    {"name": "chart", "description": "Show a chart under the answer: hbar for rankings, line for trends, donut for shares, bar for comparisons.",
     "parameters": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": ["bar", "hbar", "line", "donut"]}, "title": {"type": "string"},
         "labels": {"type": "array", "items": {"type": "string"}},
         "series": {"type": "array", "items": {"type": "object", "properties": {
             "name": {"type": "string"}, "values": {"type": "array", "items": {"type": "number"}}}}}},
         "required": ["kind", "title", "labels", "series"]}},
    {"name": "propose_note", "description": "Prepare a note on a person's profile for the user to confirm.",
     "parameters": {"type": "object", "properties": {"who": {"type": "string"}, "text": {"type": "string"}}, "required": ["who", "text"]}},
]
WRITE_TOOLS = {"propose_note"}


def openai_tools() -> list[dict]:
    return [{"type": "function", "function": t} for t in TOOLS]


class Toolbox:
    def __init__(self, service, month: str | None = None, scope: dict | None = None, anonymise: bool = False):
        self.svc = service
        self.db = service.api.db
        self.month = month
        self.scope = dict(scope or {})
        self.anon = anonymise
        self.blocks: list[dict] = []        # tables and charts shown under the answer
        self.actions: list[dict] = []       # changes waiting for Confirm
        self.used: list[str] = []
        self._facts: Facts | None = None

    @property
    def facts(self) -> Facts:
        if self._facts is None:
            self._facts = Facts(self.svc.api)
        return self._facts

    def _hide(self, out):
        """Anonymised mode: names are replaced by employee numbers before anything leaves the PC."""
        if not self.anon:
            return out
        names = {p["name"]: f"Employee {p['emp']}" for p in self.facts.leaders if p["emp"]}

        def walk(x):
            if isinstance(x, str):
                return names.get(x, x)
            if isinstance(x, list):
                return [walk(y) for y in x]
            if isinstance(x, dict):
                return {k: walk(v) for k, v in x.items()}
            return x
        return walk(out)

    # ---------------------------------------------------------------- tools
    def run(self, name: str, args: dict) -> Any:
        self.used.append(name)
        fn = getattr(self, f"t_{name}", None)
        if not fn:
            return {"error": f"unknown tool {name}"}
        try:
            out = fn(**(args or {}))
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}
        except Exception as e:  # noqa: BLE001 - the model gets the reason and can try another way
            return {"error": str(e)}
        return self._hide(out) if name not in ("kpis", "chart") else out

    def _no_data(self):
        return {"note": "No master sheet has been uploaded yet (Data → Master sheet)."} if self.facts.empty else None

    def t_person(self, who: str = "", **kw) -> dict:
        if self._no_data():
            return self._no_data()
        f = self.facts
        if self.anon:
            m = re.search(r"Employee (\d+)", who or "")
            who = m.group(1) if m else who
        p, cands = f.find(who)
        if not p:
            return {"not_found": who, "did_you_mean": [f"{c['name']} ({c['designation']}, {c['store']})" for c in cands],
                    "note": "Ask which one they mean." if cands else "Nobody with that name is in the master sheet for " + f.period_label + "."}
        return f.person(p)

    def t_people(self, query: str = "", store: str = "", dept: str = "", section: str = "", role: str = "", format: str = "",
                 category: str = "", sort: str = "score", ascending: bool = False, limit: int = 30, **kw) -> dict:
        if self._no_data():
            return self._no_data()
        r = self.facts.people(query, store, dept, section, role, format, category, "", sort or "score", bool(ascending), limit)
        for p in r.get("people", []):
            p.pop("_values", None)
            p.pop("_status", None)
        return r

    def t_store(self, name: str = "", **kw) -> dict:
        if self._no_data():
            return self._no_data()
        return self.facts.store_view(name)

    def t_stores(self, **kw) -> dict:
        if self._no_data():
            return self._no_data()
        return self.facts.league()

    def t_overview(self, **kw) -> dict:
        if self._no_data():
            return self._no_data()
        return self.facts.overview()

    def t_data_health(self, **kw) -> dict:
        if self._no_data():
            return self._no_data()
        return self.facts.health()

    def t_review(self, store: str = "", dept: str = "", section: str = "", role: str = "", **kw) -> dict:
        from .. import review
        from ..po import canon
        if self._no_data():
            return self._no_data()
        api = self.svc.api
        if store:
            store = self.facts.find_store(store) or store
        names = {v.casefold(): k for k, v in review.SHORT.items()} | {k.casefold(): k for k in review.SHORT}
        dept = names.get((dept or "").casefold(), dept)
        if section:
            section = canon.section(section) or section
        r = api.api_review(store=store or None, dept=dept or None, section=section or None, role=role or None)
        if r.get("empty"):
            return {"note": "No data for that view."}
        C = r["criteria"]
        show = lambda cells, keys: {C[c["key"]]["label"]: f"{review.fmt(c['key'], c['value'])} ({c['status']})" for c in cells if c["key"] in keys and c["value"] is not None}  # noqa: E731
        return {"view": r["label"], "period": self.facts.period_label, "scorecard": show(r["tiles"], [t["key"] for t in r["tiles"]]), "notes": r["notes"],
                "next_level": {g["name"]: show(g["cells"], r["grid_keys"]) for g in r["grid"]},
                "people": [{"name": p["name"], "store": p["store"], "role": p["role"], "area": p["area"], **show(p["cells"], r["people_keys"])} for p in r["people"][:40]]}

    def t_sql(self, query: str = "", **kw) -> dict:
        q = (query or "").strip().rstrip(";")
        if not re.match(r"^\s*(WITH|SELECT)\b", q, re.I) or ";" in q:
            return {"error": "Only one SELECT statement is allowed."}
        con = self.sql_connection()
        try:
            cur = con.execute(q)
            cols = [c[0] for c in cur.description or []]
            rows = cur.fetchmany(200)
            return {"columns": cols, "rows": [list(r) for r in rows], "truncated": len(rows) == 200}
        except sqlite3.Error as e:
            return {"error": f"SQL error: {e}"}
        finally:
            con.close()

    def sql_connection(self) -> sqlite3.Connection:
        con = sqlite3.connect(":memory:")
        cols = ["emp", "name", "designation", "level", "role", "store", "format", "city", "department", "section", "grade", "joined",
                "role_since", "months_in_role", "manager", *KEYS, "rating_2023", "rating_2024", "rating_2025", "score", "category"]
        con.execute(f"CREATE TABLE leaders({', '.join(cols)})")
        rows = []
        for p in self.facts.leaders:
            yr = p["ratings"] if isinstance(p["ratings"], dict) else {}
            rows.append((p["emp"], f"Employee {p['emp']}" if self.anon else p["name"], p["designation"], p["level"], p["role"], p["store"],
                         p["format"], p["city"], p["department"], p["section"], p["grade"], p["joined"], p["role_since"], p["in_role_months"],
                         p["manager"], *[p["values"][k] for k in KEYS], yr.get("2023"), yr.get("2024"), yr.get("2025"), p["score"], p["category"]))
        con.executemany(f"INSERT INTO leaders VALUES({','.join('?' * len(cols))})", rows)
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, getattr(sqlite3, "SQLITE_RECURSIVE", 33)}
        con.set_authorizer(lambda action, *a: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        return con

    def t_internal_candidates(self, role: str = "section_manager", store: str = "", department: str = "", section: str = "", **kw) -> dict:
        from ..hiring import internal
        st = self.facts.find_store(store) if store else ""
        r = internal.search(self.svc.api, {"role": role, "store": st or "", "department": department, "section": section,
                                           "title": role.replace("_", " ").title()}, limit=6)
        return {"verdict": r["verdict"], "notes": r.get("notes", []), "candidates": [
            {k: c.get(k) for k in ("name", "designation", "store", "experience", "move", "fit", "recommend", "why", "watch")} |
            {"backfill": {k: c["backfill"].get(k) for k in ("summary", "risk", "status")},
             "chain": [f"{s['seat']} ← {s['by'] or 'hire from outside'}" for s in c["backfill"].get("steps", [])]} for c in r["candidates"]]}

    def t_learning(self, make: bool = False, topic: str = "", role: str = "", hours: float = 3, **kw) -> dict:
        L = self.svc.api.learning
        if make:
            r = (role or "").lower()
            level = 6 if "store manager" in r else 4 if "department" in r or "head" in r else 3 if "section" in r else 1 if "associate" in r or "cashier" in r else 2
            c = L.build(level=level, hours=float(hours or 3), lecture_min=25, focus=topic)
            ct = c["content"]
            return {"made": True, "course_id": c["id"], "title": ct["title"], "summary": ct["summary"], "modules": [m["title"] for m in ct["modules"]],
                    "notes": ct.get("notes", []), "where": "Open Learning to read, present or export it (PDF, PowerPoint, Word, Excel)."}
        d = L.courses()
        return {"courses": [{"title": c["title"], "audience": c["audience"], "hours": c["hours"], "assigned": c["assigned"], "completed": c["completed"],
                             "avg_score": c["avg_score"]} for c in d["rows"]][:20], "stats": L.stats(), "topics": [t["title"] for t in d["topics"]]}

    def t_hiring(self, vacancy: str = "", search: str = "", skill: str = "", city: str = "", **kw) -> dict:
        h = self.svc.api.hiring
        vacs = h.vacancies()["rows"]
        out: dict = {"open_vacancies": [{"title": v["title"], "store": v["store"], "cvs": v["cvs"], "strong": v["strong"], "days_open": v["days_open"],
                                         "status": v["status"]} for v in vacs][:20], "analytics": {k: v for k, v in h.analytics().items()
                                                                                                   if k in ("open", "time_to_hire", "offer_acceptance", "hires", "bank", "funnel")}}
        words = [w for w in vacancy.lower().split() if len(w) > 2]
        hit = next((v for v in vacs if words and all(w in f"{v['title']} {v['store']}".lower() for w in words)), None) or \
            next((v for v in vacs if words and any(w in v["title"].lower() for w in words)), None)
        if hit:
            d = h.vacancy(hit["id"], blind=self.anon)
            out["vacancy"] = {"title": d["title"], "store": d["store"], "bands": d["bands"], "candidates": [
                {"name": a["name"], "score": a["score"], "recommendation": a["band_label"], "highest_role": a["level"], "years": a["years"],
                 "retail_years": a["retail_years"], "city": a["city"], "stage": a["stage"], "checks": a["flags"] + a["knockouts"] + a["tags"]}
                for a in d["apps"][:15]], "internal_candidates": d["internal"][:5]}
            top = d["apps"][:8]
            if top:
                self.blocks.append({"type": "chart", "kind": "hbar", "title": f"{d['title']} · match score", "labels": [a["name"] for a in top],
                                    "series": [{"name": "Score", "values": [a["score"] for a in top]}]})
        if search or skill or city:
            b = h.bank(search, skill, city)
            out["talent_bank"] = [{"name": r["name"], "years": r["years"], "level": r["level"], "city": r["city"], "skills": r["skills"]} for r in b["rows"][:15]]
        return out

    def t_kpis(self, items=None, **kw) -> dict:
        clean = [{"label": str(k.get("label", ""))[:40], "value": str(k.get("value", ""))[:24], "sub": str(k.get("sub", "") or "")[:60],
                  "tone": k.get("tone") if k.get("tone") in ("good", "warn", "bad") else ""} for k in (items or [])[:6] if isinstance(k, dict)]
        if clean:
            self.blocks.insert(0, {"type": "kpis", "items": clean})
        return {"ok": True, "shown": len(clean)}

    def t_chart(self, kind="bar", title="", labels=None, series=None, **kw) -> dict:
        labels = [str(x) for x in (labels or [])][:40]
        clean = []
        for s in (series or [])[:4]:
            vals = []
            for v in (s.get("values") or [])[:len(labels)]:
                try:
                    vals.append(None if v is None else float(v))
                except (TypeError, ValueError):
                    vals.append(None)
            clean.append({"name": str(s.get("name", "")), "values": vals})
        self.blocks.append({"type": "chart", "kind": kind if kind in ("bar", "hbar", "line", "donut") else "bar", "title": str(title),
                            "labels": labels, "series": clean})
        return {"shown": True}

    def t_propose_note(self, who: str = "", text: str = "", **kw) -> dict:
        p, cands = self.facts.find(who)
        if not p:
            return {"not_found": who, "did_you_mean": [c["name"] for c in cands]}
        act = self.svc.new_action("note", f"Add a note to {p['name']}'s profile", [{"emp": p["emp"], "name": p["name"], "text": text}])
        self.actions.append(act)
        return {"prepared": 1, "note": "Waiting for the user to click Confirm."}
