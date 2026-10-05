"""Ask PNO: the chat agent. Groq (fast, cloud), the offline model (on this PC) or the built-in assistant.

Mode 'auto' uses Groq when a key is set, else the offline model when it is installed, else the built-in assistant, and
falls back down that list when a service fails. Changes the agent prepares are saved only after the user confirms.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path

from .. import engine, importers
from ..db import now
from . import basic, llm, local
from .secrets import mask, protect, unprotect
from .tools import Toolbox, openai_tools

SYSTEM = """You are "Ask PNO", the analyst inside PNO, an HR performance app for MAF Carrefour Pakistan used by the HR Director.
Answer from PNO's data only, using the tools. Never invent names or numbers; if the data is missing, say so.

How PNO works (explain when asked):
- Every person gets a score out of 10 from KPIs they control. 7 = met target, 10 = clearly beat it.
- Store Manager: Total Store. Department Head: their department. Section Manager / Supervisor / Team Leader: the sections their
  team works in. CCO manager: CCO. Staff: 70% own attendance + 30% their section's result.
- Scored KPIs: sales vs budget, productivity vs target, out-of-stock % and waste % (compared with the same area in other
  stores), team attendance, own attendance. Growth vs last year and margin are context only (not controllable).
- Attendance: real absence = no punch on a due day after removing 1 weekly off per week (Sat+Sun for head office),
  gazetted holidays and booked leave. Missing punches count as worked but are listed to fix. The golden rule is 9 hours a day.
- Bands: 9+ Outstanding, 7.5+ Strong, 6+ Meets expectation, 4+ Needs improvement, below 4 Concern.

Style: short, clear, executive. Lead with the answer, then 2-5 bullets. Use **bold** for key numbers. Use the chart tool
for comparisons or trends with 3+ values. Mention the month. When the user asks to record leave, holidays or notes, use the
propose_* tools; nothing is saved until they click Confirm, so tell them to confirm. If asked in Urdu, answer in Urdu."""


class AgentService:
    def __init__(self, api):
        self.api = api
        self.pending: dict[str, dict] = {}

    @property
    def db(self):
        return self.api.db

    # ---------------------------------------------------------------- settings
    def _cfg(self) -> dict:
        c = {"mode": "auto", "model": llm.GROQ_MODELS[0], "anonymise": False, "key": ""}
        c.update(self.db.get_setting("ai", {}) or {})
        return c

    def save_settings(self, mode=None, model=None, anonymise=None, key=None, clear_key=False) -> dict:
        c = self._cfg()
        if mode in ("auto", "groq", "offline", "basic"):
            c["mode"] = mode
        if model:
            c["model"] = model
        if anonymise is not None:
            c["anonymise"] = bool(anonymise)
        if key:
            c["key"] = protect(key.strip())
        if clear_key:
            c["key"] = ""
        self.db.set_setting("ai", c)
        return self.status()

    def _key(self) -> str:
        return unprotect(self._cfg().get("key", ""))

    def offline_ready(self) -> bool:
        return bool(local.find_runtime() and local.model_path(self.db))

    def public_status(self) -> dict:
        c = self._cfg()
        key = self._key()
        active = self._choose(c, key)
        return {"mode": c["mode"], "active": active, "groq": bool(key), "offline": self.offline_ready(),
                "label": {"groq": "Groq · fast", "offline": "Offline AI · on this PC", "basic": "Built-in assistant"}[active]}

    def status(self) -> dict:
        c = self._cfg()
        key = self._key()
        return {**self.public_status(), "model": c["model"], "models": llm.GROQ_MODELS, "anonymise": c["anonymise"],
                "key_masked": mask(key), "offline_status": self.offline_status()}

    def _choose(self, c: dict, key: str) -> str:
        m = c["mode"]
        if m == "groq":
            return "groq" if key else "basic"
        if m == "offline":
            return "offline" if self.offline_ready() else "basic"
        if m == "basic":
            return "basic"
        if key:
            return "groq"
        return "offline" if self.offline_ready() else "basic"

    def test(self) -> dict:
        key = self._key()
        if not key:
            return {"ok": False, "message": "Add a Groq API key first (free at console.groq.com/keys)."}
        t = time.time()
        try:
            models = llm.list_models(llm.GROQ_URL, key)
            msg = llm.chat(llm.GROQ_URL, key, self._cfg()["model"], [{"role": "user", "content": "Reply with: OK"}], max_tokens=5)
        except llm.LLMError as e:
            return {"ok": False, "message": str(e)}
        return {"ok": True, "message": f"Groq is working ({time.time() - t:.1f}s). Reply: {(msg.get('content') or '').strip()[:20]}",
                "models": [m for m in models if not re.search(r"whisper|guard|tts|embed", m)]}

    # ---------------------------------------------------------------- offline AI
    def offline_status(self) -> dict:
        return {"runtime": str(local.find_runtime() or ""), "model": local.model_path(self.db) or "",
                "model_name": local.MODEL["name"], "model_gb": local.MODEL["gb"], "running": local.SERVER.ready(),
                "downloads": local.DOWNLOADS.list()}

    def offline_install(self, what: str = "all") -> dict:
        jobs = []
        if what in ("all", "runtime") and not local.find_runtime():
            jobs.append(local.install_runtime())
        if what in ("all", "model") and not local.model_path(self.db):
            jobs.append(local.download_model())
        return {"jobs": jobs, **self.offline_status()}

    def offline_link(self, path: str) -> dict:
        p = Path(path)
        if p.suffix.lower() != ".gguf" or not p.exists():
            raise ValueError("Choose a .gguf model file.")
        self.db.set_setting("offline_model", str(p))
        return self.offline_status()

    def downloads(self) -> dict:
        return {"jobs": local.DOWNLOADS.list()}

    # ---------------------------------------------------------------- confirmations
    def new_action(self, kind: str, title: str, items: list[dict]) -> dict:
        aid = uuid.uuid4().hex[:10]
        act = {"id": aid, "kind": kind, "title": title, "items": items, "created": now()}
        self.pending[aid] = act
        return {k: v for k, v in act.items() if k != "token"}

    def confirm(self, action_id: str, approve: bool = True) -> dict:
        act = self.pending.pop(action_id, None)
        if not act:
            return {"ok": False, "message": "This change has already been handled or has expired."}
        if not approve:
            return {"ok": True, "message": "Cancelled. Nothing was changed."}
        done = 0
        if act["kind"] == "leave":
            for it in act["items"]:
                self.api.api_leave_add(it["emp"], it["from"], it["to"], it.get("type") or "Leave", "Added with Ask PNO", "agent")
                done += 1
            msg = f"Saved {done} leave record{'s' if done != 1 else ''}. Attendance and scores are updated."
        elif act["kind"] == "holiday":
            for it in act["items"]:
                self.api.api_holiday_add(it["day"], it["name"])
                done += 1
            msg = "Holiday saved. Nobody is counted absent on that day."
        elif act["kind"] == "note":
            for it in act["items"]:
                self.api.api_note_add(it["emp"], it["text"])
                done += 1
            msg = "Note saved on the profile."
        elif act["kind"] == "import":
            res = self.api.api_import_commit(act["token"], act.get("options") or {})
            ok = sum(1 for f in res["done"] for r in f.get("results", []) if r.get("status") == "ok")
            msg = f"Imported {ok} report table{'s' if ok != 1 else ''}."
        else:
            msg = "Done."
        self.db.log("agent", f"confirmed {act['kind']}: {act['title']}")
        return {"ok": True, "message": msg}

    # ---------------------------------------------------------------- the read-only SQL sandbox
    def sql_connection(self, month: str | None, anonymise: bool) -> sqlite3.Connection:
        mm = engine.model(self.db, month)
        con = sqlite3.connect(f"file:{self.db.path}?mode=ro", uri=True)
        con.execute("""CREATE TEMP TABLE people(emp, name, store, city, format, dept_code, dept, section, designation, grade, gender,
                       role, role_label, score, band, coverage, attendance_score, presence_pct, compliance_pct, worked_days,
                       absent_days, leave_days, off_days, punches_to_fix, longest_absence, avg_hours, sales_vs_budget_pct,
                       productivity_vs_target_pct, oos_pct, waste_pct, manager_emp, manager_name, joining)""")
        rows = []
        for p in mm.people.values():
            a = p.att or {}
            b = p.brief()
            rows.append((p.emp, f"Employee {p.emp}" if anonymise else p.name, p.store, p.city, p.store_format, p.dept_code, p.dept,
                         p.section, p.designation, p.grade, p.gender, p.role, b["role_label"], b["score"], b["band"], b["coverage"],
                         a.get("score"), a.get("presence"), a.get("compliance"), a.get("worked"), a.get("absent"), a.get("leave"),
                         a.get("off"), a.get("fixes"), a.get("longest_absence"),
                         round(a["avg_minutes"] / 60, 2) if a.get("avg_minutes") else None, p.kpis.get("sales"), p.kpis.get("prod"),
                         p.kpis.get("oos"), p.kpis.get("waste"), p.manager_emp,
                         p.manager_name if not anonymise else None, p.joining))
        con.executemany(f"INSERT INTO people VALUES({','.join('?' * 33)})", rows)
        con.execute("""CREATE TEMP VIEW sales AS SELECT st.name AS store, s.month, s.as_of, s.level, s.code, s.name, s.dept, s.actual,
                       s.budget, s.growth, s.ly, s.waste, s.oos, s.margin_net, s.customers
                       FROM main.sales s JOIN main.stores st ON st.id=s.store_id JOIN main.imports i ON i.id=s.import_id AND i.active=1
                       WHERE s.period='MTD' AND s.as_of=(SELECT MAX(s2.as_of) FROM main.sales s2 JOIN main.imports i2 ON i2.id=s2.import_id
                       AND i2.active=1 WHERE s2.store_id=s.store_id AND s2.month=s.month AND s2.period='MTD')
                       AND s.level IN ('section','dept','store')""")
        con.execute("""CREATE TEMP VIEW productivity AS SELECT st.name AS store, p.month, p.row_code, p.row_name, p.actual, p.target, p.ly
                       FROM main.productivity p JOIN main.stores st ON st.id=p.store_id JOIN main.imports i ON i.id=p.import_id AND i.active=1""")
        con.execute("""CREATE TEMP VIEW leaves AS SELECT l.emp_no, l.d_from, l.d_to, l.type FROM main.leaves l
                       LEFT JOIN main.imports i ON i.id=l.import_id WHERE l.import_id IS NULL OR i.active=1""")
        con.execute("CREATE TEMP VIEW stores AS SELECT id, name, format, city FROM main.stores")
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, getattr(sqlite3, "SQLITE_RECURSIVE", 33)}

        def guard(action, a1, a2, db, src):
            return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
        con.set_authorizer(guard)
        return con

    # ---------------------------------------------------------------- asking
    def ask(self, question: str, history: list, month: str | None, scope: dict, attachments: list) -> dict:
        t0 = time.time()
        c = self._cfg()
        key = self._key()
        tb = Toolbox(self, month, scope, bool(c["anonymise"]))
        intro = self._attachments(tb, attachments, key, c) if attachments else ""
        if not question.strip() and intro:
            return self._reply(tb, intro, "basic", t0)
        engine_name = self._choose(c, key)
        note = ""
        if engine_name in ("groq", "offline"):
            try:
                text = self._llm(engine_name, c, key, tb, question, history)
                return self._reply(tb, (intro + "\n\n" if intro else "") + text, engine_name, t0)
            except (llm.LLMError, RuntimeError, OSError) as e:
                note = f"_{e} Answered with the built-in assistant instead._\n\n"
                tb.blocks.clear()
                if c["mode"] == "auto" and engine_name == "groq" and self.offline_ready():
                    try:
                        text = self._llm("offline", c, key, tb, question, history)
                        return self._reply(tb, (intro + "\n\n" if intro else "") + text, "offline", t0)
                    except Exception:
                        pass
        text = basic.answer(tb, question) if question.strip() else ""
        return self._reply(tb, note + (intro + "\n\n" if intro else "") + text, "basic", t0)

    def _reply(self, tb: Toolbox, text: str, engine_name: str, t0: float) -> dict:
        if tb.anon:
            mm = tb._mm()
            text = re.sub(r"Employee (\d{5,})", lambda m: f"{mm.people[m.group(1)].name} ({m.group(1)})" if m.group(1) in mm.people else m.group(0), text)
        return {"answer": text.strip(), "blocks": tb.blocks, "actions": tb.actions, "engine": engine_name,
                "engine_label": {"groq": "Groq", "offline": "Offline AI", "basic": "Built-in assistant"}[engine_name],
                "tools": tb.used, "seconds": round(time.time() - t0, 1)}

    def _llm(self, engine_name: str, c: dict, key: str, tb: Toolbox, question: str, history: list) -> str:
        if engine_name == "groq":
            base, model, k = llm.GROQ_URL, c["model"], key
        else:
            path = local.model_path(self.db)
            if not local.SERVER.ensure(path):
                raise RuntimeError("The offline AI is still loading. Try again in a moment.")
            base, model, k = f"http://127.0.0.1:{local.PORT}/v1", "local", ""
        mm = tb._mm()
        ctx = (f"Month on screen: {mm.month} (data up to {mm.as_of}). Filters on screen: "
               f"{json.dumps(tb.scope) if tb.scope else 'whole country'}. Months available: {', '.join(engine.months_available(self.db))}. "
               f"Today: {time.strftime('%Y-%m-%d')}.")
        msgs = [{"role": "system", "content": SYSTEM + "\n\n" + ctx}]
        for h in history[-8:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                msgs.append({"role": h["role"], "content": str(h["content"])[:3000]})
        msgs.append({"role": "user", "content": question})
        tools = openai_tools()
        for _ in range(8):
            msg = llm.chat(base, k, model, msgs, tools, timeout=120 if engine_name == "offline" else 60)
            calls = msg.get("tool_calls") or []
            if not calls:
                return msg.get("content") or "I could not find an answer in the data."
            msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for call in calls:
                fn = call.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                out = tb.run(fn.get("name", ""), args)
                msgs.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(out, default=str)[:7000]})
        return "I looked at the data but needed too many steps. Please ask a narrower question."

    # ---------------------------------------------------------------- files dropped into the chat
    def _attachments(self, tb: Toolbox, paths: list, key: str, c: dict) -> str:
        lines = []
        known = []
        for p in paths:
            try:
                a = importers.analyze_path(p)
            except Exception as e:
                lines.append(f"**{Path(p).name}**: could not be read ({e}).")
                continue
            if a["results"]:
                known.append(p)
                for r in a["results"]:
                    lines.append(f"**{Path(p).name}** looks like a **{importers.KIND_LABEL[r.kind]}**: {r.summary}.")
            else:
                leave = self._leave_from_unknown(p, key, c)
                if leave:
                    tb.t_propose_leave(leave)
                    lines.append(f"**{Path(p).name}** looks like a leave list. I prepared {len(leave)} leave records for you to confirm.")
                else:
                    lines.append(f"**{Path(p).name}**: I could not recognise this file. Try the Import screen to map it.")
        if known:
            res = self.api.api_import_analyze(paths=known)
            act = self.new_action("import", f"Import {len(known)} file{'s' if len(known) != 1 else ''}",
                                  [{"file": f["file"], "tables": [r["label"] + f" ({r['rows']} rows)" for r in f["results"]]} for f in res["files"]])
            self.pending[act["id"]]["token"] = res["token"]
            needs = {r["sheet"]: {"month": res["suggested_month"]} for f in res["files"] for r in f["results"] if "month" in r["needs"]}
            if needs:
                self.pending[act["id"]]["options"] = {f["file"]: needs for f in res["files"]}
                lines.append(f"A productivity report has no date; I'll file it under **{res['suggested_month']}** (change on the Import screen if needed).")
            tb.actions.append(act)
            lines.append("Click **Confirm** to import.")
        return "\n".join(lines)

    def _leave_from_unknown(self, path: str, key: str, c: dict) -> list[dict]:
        """A leave list in an unknown layout: the AI sees only the headers and 5 sample rows to work out the columns;
        the whole file is then read here on this PC."""
        from ..reader import open_file
        from ..util import clean_text, emp_code
        wb = open_file(path)
        if not wb.sheets:
            return []
        rows = wb.sheets[0].rows
        hdr_i = next((i for i, r in enumerate(rows[:15]) if sum(1 for x in r if isinstance(x, str) and x.strip()) >= 3), 0)
        header = [clean_text(x) for x in rows[hdr_i]]
        sample = [[clean_text(x) for x in r] for r in rows[hdr_i + 1:hdr_i + 6]]
        mapping = None
        if key or self.offline_ready():
            prompt = ("Columns of a spreadsheet: " + json.dumps(header) + "\nSample rows: " + json.dumps(sample) +
                      '\nIf this is a list of employee leave, reply with JSON only: {"emp": i, "from": i, "to": i, "type": i, '
                      '"status": i} using 0-based column indexes (null if missing). If it is not a leave list reply {"leave": false}.')
            try:
                if key:
                    msg = llm.chat(llm.GROQ_URL, key, c["model"], [{"role": "user", "content": prompt}], max_tokens=120)
                else:
                    local.SERVER.ensure(local.model_path(self.db))
                    msg = llm.chat(f"http://127.0.0.1:{local.PORT}/v1", "", "local", [{"role": "user", "content": prompt}], max_tokens=120)
                m = re.search(r"\{.*\}", msg.get("content") or "", re.S)
                mapping = json.loads(m.group(0)) if m else None
            except Exception:
                mapping = None
        if not mapping or mapping.get("leave") is False or mapping.get("emp") is None or mapping.get("from") is None:
            return []
        out = []
        for r in rows[hdr_i + 1:]:
            g = lambda k: r[mapping[k]] if mapping.get(k) is not None and mapping[k] < len(r) else None  # noqa: E731
            emp = emp_code(g("emp"))
            if not emp or (g("status") and re.search(r"reject|cancel|pending|declin", str(g("status")), re.I)):
                continue
            out.append({"who": emp, "from": str(g("from")), "to": str(g("to") or g("from")), "type": clean_text(g("type")) or "Leave"})
        return out
