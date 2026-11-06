"""P&O AI: the chat agent. Groq, Gemini or OpenRouter (cloud), the offline model (on this PC) or the built-in assistant.

Mode 'auto' uses the first cloud AI with a key (Groq, Gemini, OpenRouter), else the offline model when it is installed, else
the built-in assistant, and moves down that list on the fly when a service fails. Choosing one AI puts it first. Changes the agent prepares are saved only after the user confirms.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from ..db import now
from . import basic, llm, local
from .secrets import mask, protect, unprotect
from .tools import Toolbox, openai_tools

SYSTEM = """You are "P&O AI", the analyst inside P&O (People & Organisation), the HR and business performance app of
Majid Al Futtaim Carrefour Pakistan, used by the P&O Director. Answer from the app's data only, using the tools. Never invent
names or numbers; if something is not in the data, say so plainly.

The data: ONE master sheet per period (year to date or one month), one row per leader (store managers, deputy managers,
department heads, section managers, team leaders) with: employee number, name, joining date, grade, store (BU), section,
designation, time in current role, and their results: Sales vs budget %, Productivity vs target %, Shrink vs budget %,
Stock days (% of budget), Leavers, Disciplinary (DA) cases, Customer NPS and performance Rating (one per year).
A blank, "—", #N/A, "Unrated" or a rating of 0 means "not filled yet": it is left out, never counted as zero.

How P&O scores a leader: each filled result earns 0-10 points against its benchmark (amber line = 5, green line = 7, one step
past green = 10); the score out of 10 is the weighted average of those points (at least 3 results are needed for a score).
Category: High 7+, Good 5-6.9, Low below 5. Some people have their own criteria (marked custom); the tools already apply them.
The current criteria and weights are given below; quote them as they are.

Always call a tool before answering: person for anyone named (even a first name), people for lists and rankings, store / stores
for stores, overview for the country, review for a department or section view, data_health for what is missing, sql for anything
else. If a name matches several people, ask which one. If someone has no score, say which results are missing (not_filled_yet).

How to answer (like a senior analyst writing for a director):
1. First line: the direct answer in one or two sentences, with the key number in **bold**.
2. Call the kpis tool with 3-5 headline figures (value + short context, tone good/warn/bad) when numbers matter.
3. Then short sections with ### headings: what the data shows, why (drivers, comparisons with peers and benchmarks), what it means.
   Use markdown tables for several items, bullets for lists, and one "> **Risk:** …" or "> **Strength:** …" callout.
4. Use the chart tool for any ranking or comparison with 3+ values. One or two charts, not more.
5. End with "### Recommended actions": 2-4 numbered, specific actions (who, what).
Keep it tight: no filler, no repeating the question. Say which period the figures cover. Write + and − signs on changes.
If the user writes in Urdu or Roman Urdu, answer in the same language."""


ENGINES = ["auto", "groq", "gemini", "openrouter", "offline", "basic"]
ENGINE_NAME = {"auto": "Auto", "groq": "Groq", "gemini": "Gemini", "openrouter": "OpenRouter", "offline": "Offline AI",
               "basic": "Built-in assistant"}
STATUS_LABEL = {"offline": "Offline AI · on this PC", "basic": "Built-in assistant"}


FOLLOW = [
    (r"turnover|leaver|attrition|resign", ["Which stores have the most leavers?", "Which department heads have zero leavers?", "Make a retention course for team leaders"]),
    (r"nps|customer", ["Which stores have NPS below 50?", "Who has the best NPS?", "Make a 2 hour customer service course for associates"]),
    (r"vacanc|candidate|hiring|cv", ["How is hiring going?", "Who should we interview first?", "Anyone in the talent bank with fresh food experience?"]),
    (r"course|training", ["What training do we have?", "Make a 3 hour shrink course for section managers", "Which store managers need training most?"]),
    (r"missing|not filled|complete|health", ["Who is missing a rating?", "Which stores have gaps in the data?", "Brief me for the country review"]),
    (r"store manager|department head|deputy|leader|score|rating", ["Who are the bottom 5 department heads?", "Who could replace a store manager?", "Compare Fortress and Emporium"]),
    (r"sales|budget|store|productiv|shrink|stock", ["Which stores need attention and why?", "Who is below sales budget?", "Where is stock days worst?"]),
]


def followups(text: str, used: list) -> list[str]:
    """Three natural next questions, from what the answer was about."""
    t = (text or "").lower() + " " + " ".join(used or [])
    for rx, qs in FOLLOW:
        if re.search(rx, t):
            return qs
    return ["Brief me for the country review", "Which stores need attention and why?", "Is my data ready?"]


TASKS = {
    "chat": "Chat with your data (names, ratings, results)",
    "learning": "Courses and learning",
    "hiring": "CV screening and job descriptions",
    "import": "Reading unknown files during import",
    "policy": "Policy answers",
    "insights": "Survey comments, written insights and dataset labels",
}


def _drop_empty(x):
    if isinstance(x, dict):
        return {k: _drop_empty(v) for k, v in x.items() if v not in (None, "", [], {})}
    if isinstance(x, list):
        return [_drop_empty(v) for v in x]
    if isinstance(x, float):
        return round(x, 2)
    return x


def _compact(out, limit: int = 6000) -> str:
    """Tool results without empty fields, rounded numbers and no spaces: the same facts in far fewer tokens."""
    s = json.dumps(_drop_empty(out), default=str, separators=(",", ":"), ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + '…(cut: ask a narrower question for the rest)'


class AgentService:
    def __init__(self, api):
        self.api = api
        self.pending: dict[str, dict] = {}
        self._answers: dict[tuple, tuple[float, dict]] = {}

    @property
    def db(self):
        return self.api.db

    # ---------------------------------------------------------------- settings
    # Settings "ai": mode (auto | groq | gemini | openrouter | offline | basic), keys {provider: encrypted key},
    # models {provider: model id}, lists {provider: models the provider reported on the last Test}, anonymise.
    def _cfg(self) -> dict:
        stored = self.db.get_setting("ai", {}) or {}
        c = {"mode": "auto", "anonymise": False, "keys": {}, "models": {}, "lists": {}, "routes": {}}
        c.update({k: v for k, v in stored.items() if k not in ("key", "model")})
        c["keys"], c["models"], c["lists"] = dict(c["keys"] or {}), dict(c["models"] or {}), dict(c["lists"] or {})
        c["routes"] = {k: v for k, v in dict(c.get("routes") or {}).items() if k in TASKS and v in ENGINES}
        if stored.get("key") and "groq" not in c["keys"]:          # settings saved by P&O 1.3 and earlier
            c["keys"]["groq"] = stored["key"]
        if stored.get("model") and "groq" not in c["models"]:
            c["models"]["groq"] = stored["model"]
        if c["mode"] not in ENGINES:
            c["mode"] = "auto"
        return c

    def save_settings(self, mode=None, model=None, anonymise=None, key=None, clear_key=False, provider=None, routes=None) -> dict:
        c = self._cfg()
        if isinstance(routes, dict):
            for t, e in routes.items():
                if t in TASKS:
                    if e in (None, "", "auto"):
                        c["routes"].pop(t, None)
                    elif e in ENGINES:
                        c["routes"][t] = e
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
                "tasks": [{"id": t, "label": l, "engine": c["routes"].get(t, "auto")} for t, l in TASKS.items()],
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

    def _for_task(self, c: dict, task: str | None) -> dict:
        """The settings with the AI chosen for this kind of work put first."""
        e = (c.get("routes") or {}).get(task or "")
        return {**c, "mode": e} if e and e != "auto" else c

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
        elif act["kind"] == "correction":
            for it in act["items"]:
                self.api.api_correction_add(it["emp"], it["field"], it["value"], it.get("note") or "Corrected in Ask P&O AI", it.get("cycle"), "chat")
                done += 1
            msg = f"Corrected. Every screen now uses the new value{'s' if done > 1 else ''}, and later imports won't overwrite it. Undo it on the person's page."
        elif act["kind"] == "import":
            res = self.api.api_import_commit(act["token"], act.get("options") or {})
            ok = sum(1 for f in res["done"] for r in f.get("results", []) if r.get("status") == "ok")
            msg = f"Imported {ok} report table{'s' if ok != 1 else ''}."
        else:
            msg = "Done."
        self.db.log("agent", f"confirmed {act['kind']}: {act['title']}")
        return {"ok": True, "message": msg}

    # ---------------------------------------------------------------- asking
    def _endpoint(self, engine_name: str, c: dict, keys: dict, wait: float | None = None) -> tuple[str, str, str]:
        if engine_name in llm.PROVIDERS:
            return llm.provider_url(engine_name), self._model(c, engine_name), keys[engine_name]
        path = local.model_path(self.db)
        if not (local.SERVER.ensure(path, wait=wait) if wait else local.SERVER.ensure(path)):
            raise RuntimeError("The offline AI is still loading. Try again in a moment.")
        return f"http://127.0.0.1:{local.PORT}/v1", "local", ""

    def complete(self, prompt: str, system: str = "", max_tokens: int = 900, allow_offline: bool = True, task: str = "insights") -> tuple[str, str] | None:
        """One plain AI completion (no tools) with the first AI that answers; None when only the built-in assistant is set up.
        `task` picks the AI chosen for that kind of work in Settings → AI."""
        c = self._for_task(self._cfg(), task)
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
        c = self._for_task(self._cfg(), "chat")
        if engine in ENGINES:                  # switched from the chat box for this question
            c["mode"] = engine
        ck = (question.strip().casefold(), month, json.dumps(scope or {}, sort_keys=True), self.db.version, c["mode"],
              json.dumps([h.get("content", "")[:200] for h in (history or [])[-2:]]))
        hit = self._answers.get(ck) if not attachments else None
        if hit and time.time() - hit[0] < 900:                      # the same question on the same data: answer from memory
            return {**hit[1], "cached": True, "seconds": round(time.time() - t0, 1)}
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
                out = self._reply(tb, note + (intro + "\n\n" if intro else "") + text, engine_name, t0)
                if not tb.actions:
                    self._answers[ck] = (time.time(), out)
                    if len(self._answers) > 60:
                        self._answers.pop(next(iter(self._answers)))
                return out
            except (llm.LLMError, RuntimeError, OSError) as e:
                notes.append(str(e).rstrip(".") + ".")
                tb.blocks.clear()
        note = ("_" + " ".join(notes) + " Answered with the built-in assistant instead._\n\n") if notes else ""
        text = basic.answer(tb, question) if question.strip() else ""
        return self._reply(tb, note + (intro + "\n\n" if intro else "") + text, "basic", t0)

    def _reply(self, tb: Toolbox, text: str, engine_name: str, t0: float) -> dict:
        if tb.anon and tb._facts is not None:
            by = tb.facts.by_emp
            text = re.sub(r"Employee (\d{5,})", lambda m: f"{by[m.group(1)]['name']} ({m.group(1)})" if m.group(1) in by else m.group(0), text)
        label = ENGINE_NAME[engine_name]
        if engine_name in llm.PROVIDERS:
            label += " · " + self._model(self._cfg(), engine_name).split("/")[-1]
        return {"answer": text.strip(), "blocks": tb.blocks, "actions": tb.actions, "engine": engine_name,
                "engine_label": label, "tools": tb.used, "seconds": round(time.time() - t0, 1), "followups": followups(text, tb.used)}

    def _llm(self, engine_name: str, c: dict, keys: dict, tb: Toolbox, question: str, history: list) -> str:
        base, model, k = self._endpoint(engine_name, c, keys)
        f = tb.facts
        ctx = ("No master sheet uploaded yet." if f.empty else
               f"Period on screen: {f.period_label}. Periods loaded: {', '.join(f.periods)}. Leaders: {len(f.leaders)} in {len(f.stores())} stores "
               f"({', '.join(f.stores())}). Criteria and weights now: {f.criteria_text()}.") + f" Today: {time.strftime('%Y-%m-%d')}."
        msgs = [{"role": "system", "content": SYSTEM + "\n\n" + ctx}]
        hist = [h for h in history if h.get("role") in ("user", "assistant") and h.get("content")]
        if len(hist) > 6:                       # older turns as one short line each, the last three exchanges in full
            msgs.append({"role": "system", "content": "Earlier in this chat: " + " | ".join(str(h["content"])[:140].replace("\n", " ") for h in hist[:-6] if h["role"] == "user")})
        for h in hist[-6:]:
            msgs.append({"role": h["role"], "content": str(h["content"])[:1800 if h["role"] == "assistant" else 1200]})
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
                msgs.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": _compact(out)})
        return "I looked at the data but needed too many steps. Please ask a narrower question."

    # ---------------------------------------------------------------- files dropped into the chat
    def _attachments(self, tb: Toolbox, paths: list) -> str:
        """A file dropped into the chat: if it is a master sheet, say what is in it and how complete it is."""
        from .. import master
        from ..reader import open_file
        lines = []
        for p in paths:
            name = Path(p).name
            try:
                wb = open_file(p)
            except Exception as e:  # noqa: BLE001
                lines.append(f"**{name}**: could not be read ({e}).")
                continue
            sheet = next((sh for sh in wb.sheets if master.score(sh)[0] > 0), None)
            if not sheet:
                lines.append(f"**{name}** is not a master sheet (no Employee No, Designation and result columns found).")
                continue
            r = master.parse(sheet)
            cov = master.coverage(r["rows"])
            gaps = [f"{m['label']} {m['filled']}/{m['of']}" for m in cov["measures"] if m["filled"] < m["of"]]
            lines.append(f"**{name}** is a master sheet: **{cov['people']} leaders** in {len(cov['stores'])} stores, "
                         f"{cov['filled_pct']}% of results filled" + (f" (still missing: {', '.join(gaps)})" if gaps else "") + ".")
            lines += [f"> {w}" for w in r["warnings"][:3]]
        if lines:
            lines.append("To use it, open **Data → Master sheet**, pick the period (year to date or one month) and add the file.")
        return "\n".join(lines)
