"""P&O AI: the chat agent. Groq, Gemini or OpenRouter (cloud), the offline model (on this PC) or the built-in assistant.

Mode 'auto' uses the first cloud AI with a key (Groq, Gemini, OpenRouter), else the offline model when it is installed, else
the built-in assistant, and moves down that list on the fly when a service fails. Choosing one AI puts it first. Changes the agent prepares are saved only after the user confirms.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path

from .. import engine, importers
from ..db import now, ro_uri
from . import basic, llm, local
from .secrets import mask, protect, unprotect
from .tools import Toolbox, openai_tools

SYSTEM = """You are "P&O AI", the analyst inside P&O (People & Organisation), the HR and business performance app of
Majid Al Futtaim Carrefour Pakistan, used by the P&O Director. Answer from the app's data only, using the tools. Never invent
names or numbers; if something is not in the data, say so plainly.

What the data covers (call the tools, several if needed, before answering):
- People scores out of 10 (overview, find_people, person, store, attendance, trend, sql).
- The P&O review (po_review): store league on sales vs budget, growth, productivity vs target, shrinkage and stock days,
  out-of-stock, NPS; every section leader with a leader index out of 10, ratings, time in role, roster, team turnover and
  disciplinary cases; talent grid; bench strength; turnover hotspots and reasons; customer NPS by city and section.
- Other imported tables (datasets): KPI sheets, lists, surveys the user added.

How P&O scores people: each person gets a score out of 10 from what they control (7 = met target, 10 = clearly beat it).
Store Manager: total store; Department Head: their department; Section Manager / Team Leader: their sections; staff: 70% own
attendance + 30% section result. Real absence excludes weekly offs, holidays and booked leave; 9 hours is a full day.
Bands: 9+ Outstanding, 7.5+ Strong, 6+ Meets, 4+ Needs improvement, below 4 Concern.

How to answer (like a senior analyst writing for a director):
1. First line: the direct answer in one or two sentences, with the key number in **bold**.
2. Call the kpis tool with 3-5 headline figures (value + short context, tone good/warn/bad) when numbers matter.
3. Then short sections with ### headings: what the data shows, why (drivers, comparisons, outliers), what it means.
   Use markdown tables for comparisons of several items, bullets for lists, and "> " callouts for the single most important
   risk ("> **Risk:** …") or win ("> **Strength:** …").
4. Use the chart tool for any ranking, comparison or trend with 3+ values (hbar for rankings, line for trends, donut for
   shares of a whole, bar for grouped comparisons). One or two charts, not more.
5. End with "### Recommended actions": 2-4 numbered, specific actions (who, what).
Keep it tight: no filler, no repeating the question. Mention the month or data date. Write + and − signs on changes.
When the user asks to record leave, holidays or notes, use the propose_* tools; nothing is saved until they click Confirm.
If the user writes in Urdu or Roman Urdu, answer in the same language."""


ENGINES = ["auto", "groq", "gemini", "openrouter", "offline", "basic"]
ENGINE_NAME = {"auto": "Auto", "groq": "Groq", "gemini": "Gemini", "openrouter": "OpenRouter", "offline": "Offline AI",
               "basic": "Built-in assistant"}
STATUS_LABEL = {"offline": "Offline AI · on this PC", "basic": "Built-in assistant"}


class AgentService:
    def __init__(self, api):
        self.api = api
        self.pending: dict[str, dict] = {}

    @property
    def db(self):
        return self.api.db

    # ---------------------------------------------------------------- settings
    # Settings "ai": mode (auto | groq | gemini | openrouter | offline | basic), keys {provider: encrypted key},
    # models {provider: model id}, lists {provider: models the provider reported on the last Test}, anonymise.
    def _cfg(self) -> dict:
        stored = self.db.get_setting("ai", {}) or {}
        c = {"mode": "auto", "anonymise": False, "keys": {}, "models": {}, "lists": {}}
        c.update({k: v for k, v in stored.items() if k not in ("key", "model")})
        c["keys"], c["models"], c["lists"] = dict(c["keys"] or {}), dict(c["models"] or {}), dict(c["lists"] or {})
        if stored.get("key") and "groq" not in c["keys"]:          # settings saved by P&O 1.3 and earlier
            c["keys"]["groq"] = stored["key"]
        if stored.get("model") and "groq" not in c["models"]:
            c["models"]["groq"] = stored["model"]
        if c["mode"] not in ENGINES:
            c["mode"] = "auto"
        return c

    def save_settings(self, mode=None, model=None, anonymise=None, key=None, clear_key=False, provider=None) -> dict:
        c = self._cfg()
        if mode in ENGINES:
            c["mode"] = mode
        pid = provider if provider in llm.PROVIDERS else (mode if mode in llm.PROVIDERS else "groq")
        if model and str(model).strip():
            c["models"][pid] = str(model).strip()
        if anonymise is not None:
            c["anonymise"] = bool(anonymise)
        if key and str(key).strip():
            c["keys"][pid] = protect(str(key).strip())
        if clear_key:
            c["keys"].pop(pid, None)
            c["lists"].pop(pid, None)
        self.db.set_setting("ai", c)
        return self.status()

    def _keys(self, c: dict | None = None) -> dict:
        c = c or self._cfg()
        out = {}
        for pid in llm.PROVIDERS:
            k = unprotect(c["keys"].get(pid, "")) if c["keys"].get(pid) else ""
            if k:
                out[pid] = k
        return out

    def _key(self) -> str:
        """The key of the cloud AI that answers now (kept for older callers)."""
        c = self._cfg()
        keys = self._keys(c)
        return next((keys[e] for e in self._chain(c, keys) if e in keys), "")

    def _model(self, c: dict, pid: str) -> str:
        return c["models"].get(pid) or llm.PROVIDERS[pid]["models"][0]

    def offline_ready(self) -> bool:
        return bool(local.find_runtime() and local.model_path(self.db))

    def public_status(self) -> dict:
        c = self._cfg()
        keys = self._keys(c)
        active = self._choose(c, keys)
        ready = [e for e in ENGINES[1:] if self._usable(e, keys)]
        label = STATUS_LABEL.get(active, "")
        if active in llm.PROVIDERS:
            label = f"{llm.PROVIDERS[active]['name']} · {self._model(c, active).split('/')[-1]}"
        return {"mode": c["mode"], "active": active, "label": label, "offline": "offline" in ready,
                "groq": "groq" in keys, "gemini": "gemini" in keys, "openrouter": "openrouter" in keys,
                "ready": ready,
                "choices": [{"id": e, "name": ENGINE_NAME[e], "ready": e == "auto" or e in ready} for e in ENGINES]}

    def status(self) -> dict:
        c = self._cfg()
        keys = self._keys(c)
        providers = []
        for pid, p in llm.PROVIDERS.items():
            listed = c["lists"].get(pid) or []
            model = self._model(c, pid)
            models = list(dict.fromkeys([model] + p["models"] + listed))
            providers.append({"id": pid, "name": p["name"], "tag": p["tag"], "signup": p["signup"], "note": p["note"],
                              "hint": p["hint"], "has_key": pid in keys, "key_masked": mask(keys.get(pid, "")),
                              "model": model, "models": models, "live_models": bool(listed)})
        groq = providers[0]
        return {**self.public_status(), "providers": providers, "anonymise": c["anonymise"],
                "model": groq["model"], "models": groq["models"], "key_masked": groq["key_masked"],     # older screens
                "offline_status": self.offline_status()}

    def _usable(self, engine_name: str, keys: dict) -> bool:
        if engine_name in llm.PROVIDERS:
            return engine_name in keys
        if engine_name == "offline":
            return self.offline_ready()
        return engine_name == "basic"

    def _chain(self, c: dict, keys: dict) -> list[str]:
        """The AIs to try, in order, ending with the built-in assistant (which always works).

        Auto: every cloud AI that has a key (Groq, Gemini, OpenRouter), then the offline AI, then built-in. Choosing one AI
        puts it first; the others that are set up still stand behind it, so a failed key or a used-up free limit switches
        to the next one instead of stopping."""
        order = list(llm.PROVIDERS) + ["offline"]
        m = c["mode"]
        if m == "basic":
            return ["basic"]
        if m in order:
            order.remove(m)
            order.insert(0, m)
        return [e for e in order if self._usable(e, keys)] + ["basic"]

    def _choose(self, c: dict, key=None) -> str:
        keys = key if isinstance(key, dict) else self._keys(c)
        return self._chain(c, keys)[0]

    def test(self, provider: str | None = None, key: str | None = None, model: str | None = None) -> dict:
        """Check one cloud AI: list its models and ask it to say OK. A key typed but not saved yet can be tested too."""
        c = self._cfg()
        keys = self._keys(c)
        pid = provider if provider in llm.PROVIDERS else next((e for e in self._chain(c, keys) if e in llm.PROVIDERS), "groq")
        p = llm.PROVIDERS[pid]
        k = (key or "").strip() or keys.get(pid, "")
        if not k:
            return {"ok": False, "provider": pid, "message": f"Add a {p['name']} API key first (get one at {p['signup']})."}
        model = (model or "").strip() or self._model(c, pid)
        base = llm.provider_url(pid)
        t = time.time()
        models: list[str] = []
        try:
            try:
                models = llm.list_models(base, k)
            except llm.LLMError as e:
                if e.status in (401, 403):
                    raise
            msg = llm.chat(base, k, model, [{"role": "user", "content": "Reply with: OK"}], max_tokens=5 if pid == "groq" else 20)
        except llm.LLMError as e:
            return {"ok": False, "provider": pid, "message": str(e)}
        models = [m for m in models if not re.search(r"whisper|guard|tts|embed|imagen|veo|aqa|image|audio|vision-preview|moderation", m)]
        if models:
            c["lists"][pid] = models[:400]
            self.db.set_setting("ai", c)
        return {"ok": True, "provider": pid, "models": models,
                "message": f"{p['name']} is working with {model} ({time.time() - t:.1f}s). Reply: {(msg.get('content') or '').strip()[:20]}"}

    # ---------------------------------------------------------------- offline AI
    def offline_status(self) -> dict:
        return {"runtime": str(local.find_runtime() or ""), "model": local.model_path(self.db) or "",
                "model_name": local.MODEL["name"], "model_gb": local.MODEL["gb"], "running": local.SERVER.ready(),
                "downloads": local.DOWNLOADS.list()}

    def offline_install(self, what: str = "all") -> dict:
        jobs = []
        if what in ("all", "runtime") and not local.find_runtime():
            try:
                jobs.append(local.install_runtime())
            except Exception as e:                       # e.g. GitHub blocked by the office network
                raise ValueError(f"The offline AI engine could not be downloaded ({e}). The P&O installer already "
                                 "includes it: please reinstall P&O, or check the internet connection.") from None
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
                self.api.api_leave_add(it["emp"], it["from"], it["to"], it.get("type") or "Leave", "Added with Ask P&O AI", "agent")
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
        con = sqlite3.connect(ro_uri(self.db.path), uri=True)
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
    def _endpoint(self, engine_name: str, c: dict, keys: dict, wait: float | None = None) -> tuple[str, str, str]:
        if engine_name in llm.PROVIDERS:
            return llm.provider_url(engine_name), self._model(c, engine_name), keys[engine_name]
        path = local.model_path(self.db)
        if not (local.SERVER.ensure(path, wait=wait) if wait else local.SERVER.ensure(path)):
            raise RuntimeError("The offline AI is still loading. Try again in a moment.")
        return f"http://127.0.0.1:{local.PORT}/v1", "local", ""

    def complete(self, prompt: str, system: str = "", max_tokens: int = 900, allow_offline: bool = True) -> tuple[str, str] | None:
        """One plain AI completion (no tools) with the first AI that answers; None when only the built-in assistant is set up."""
        c = self._cfg()
        keys = self._keys(c)
        chain = [e for e in self._chain(c, keys) if e != "basic" and (allow_offline or e != "offline")]
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        err: Exception | None = None
        for engine_name in chain:
            try:
                base, model, k = self._endpoint(engine_name, c, keys, wait=60)
                msg = llm.chat(base, k, model, msgs, None, timeout=90, max_tokens=max_tokens)
                return (msg.get("content") or "").strip(), engine_name
            except (llm.LLMError, RuntimeError, OSError) as e:
                err = e
        if err:
            raise err
        return None

    def ask(self, question: str, history: list, month: str | None, scope: dict, attachments: list, engine: str | None = None) -> dict:
        t0 = time.time()
        c = self._cfg()
        if engine in ENGINES:                  # switched from the chat box for this question
            c["mode"] = engine
        keys = self._keys(c)
        tb = Toolbox(self, month, scope, bool(c["anonymise"]))
        intro = self._attachments(tb, attachments) if attachments else ""
        if not question.strip() and intro:
            return self._reply(tb, intro, "basic", t0)
        notes = []
        for engine_name in self._chain(c, keys):
            if engine_name == "basic":
                break
            try:
                text = self._llm(engine_name, c, keys, tb, question, history)
                note = ("_" + " ".join(notes) + f" Answered with {ENGINE_NAME[engine_name]} instead._\n\n") if notes else ""
                return self._reply(tb, note + (intro + "\n\n" if intro else "") + text, engine_name, t0)
            except (llm.LLMError, RuntimeError, OSError) as e:
                notes.append(str(e).rstrip(".") + ".")
                tb.blocks.clear()
        note = ("_" + " ".join(notes) + " Answered with the built-in assistant instead._\n\n") if notes else ""
        text = basic.answer(tb, question) if question.strip() else ""
        return self._reply(tb, note + (intro + "\n\n" if intro else "") + text, "basic", t0)

    def _reply(self, tb: Toolbox, text: str, engine_name: str, t0: float) -> dict:
        if tb.anon:
            mm = tb._mm()
            text = re.sub(r"Employee (\d{5,})", lambda m: f"{mm.people[m.group(1)].name} ({m.group(1)})" if m.group(1) in mm.people else m.group(0), text)
        label = ENGINE_NAME[engine_name]
        if engine_name in llm.PROVIDERS:
            label += " · " + self._model(self._cfg(), engine_name).split("/")[-1]
        return {"answer": text.strip(), "blocks": tb.blocks, "actions": tb.actions, "engine": engine_name,
                "engine_label": label, "tools": tb.used, "seconds": round(time.time() - t0, 1)}

    def _llm(self, engine_name: str, c: dict, keys: dict, tb: Toolbox, question: str, history: list) -> str:
        base, model, k = self._endpoint(engine_name, c, keys)
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
    def _attachments(self, tb: Toolbox, paths: list) -> str:
        lines = []
        known = []
        for p in paths:
            try:
                a = importers.analyze_path(p)
            except Exception as e:
                lines.append(f"**{Path(p).name}**: could not be read ({e}).")
                continue
            if a["results"] and all(r.kind == "dataset" for r in a["results"]):
                leave = self._leave_from_unknown(p)
                if leave:
                    tb.t_propose_leave(leave)
                    lines.append(f"**{Path(p).name}** looks like a leave list. I prepared {len(leave)} leave records for you to confirm.")
                    continue
            if a["results"]:
                known.append(p)
                for r in a["results"]:
                    lines.append(f"**{Path(p).name}** looks like a **{importers.KIND_LABEL[r.kind]}**: {r.summary}.")
            else:
                leave = self._leave_from_unknown(p)
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

    def _leave_from_unknown(self, path: str) -> list[dict]:
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
        if self._choose(self._cfg()) != "basic":
            prompt = ("Columns of a spreadsheet: " + json.dumps(header) + "\nSample rows: " + json.dumps(sample) +
                      '\nIf this is a list of employee leave, reply with JSON only: {"emp": i, "from": i, "to": i, "type": i, '
                      '"status": i} using 0-based column indexes (null if missing). If it is not a leave list reply {"leave": false}.')
            try:
                out = self.complete(prompt, max_tokens=120)
                m = re.search(r"\{.*\}", out[0] if out else "", re.S)
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
