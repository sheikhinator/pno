"""The data service behind every screen. JavaScript calls dispatch(method, params) and gets JSON back."""

from __future__ import annotations

import json
import math
import threading
import traceback
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import __version__, analytics, engine, importers
from .db import Database, now
from .paths import data_dir, exports_dir
from .stores import CITIES, FORMAT_LABEL
from .util import month_label, parse_date

FIXED_HOLIDAYS = [("02-05", "Kashmir Solidarity Day"), ("03-23", "Pakistan Day"), ("05-01", "Labour Day"),
                  ("05-28", "Youm-e-Takbeer"), ("08-14", "Independence Day"), ("11-09", "Iqbal Day"),
                  ("12-25", "Quaid-e-Azam Day")]


def _clean(o):
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else round(o, 4)
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_clean(v) for v in o]
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    return o


def dumps(o) -> str:
    return json.dumps(_clean(o), ensure_ascii=False, default=str)


class Host:
    """Desktop features the browser cannot do itself. The Qt window overrides these."""

    def pick_files(self, kind: str = "reports") -> list[str]:
        return []

    def save_path(self, name: str, filt: str = "") -> str | None:
        return str(exports_dir() / name)

    def open_path(self, path: str) -> None:
        pass

    def open_url(self, url: str) -> None:
        pass


class Api:
    def __init__(self, db: Database, host: Host | None = None):
        self.real_db = db
        self.db = db
        self.host = host or Host()
        self.demo = False
        self.sessions: dict[str, dict] = {}
        self._agent = None
        self._lock = threading.RLock()

    # ---------------------------------------------------------------- plumbing
    def dispatch(self, method: str, params: dict) -> Any:
        fn = getattr(self, f"api_{method}", None)
        if fn is None:
            return {"error": f"Unknown request: {method}"}
        try:
            return fn(**(params or {}))
        except Exception as e:                       # every error reaches the screen as a readable message
            if not isinstance(e, (ValueError, KeyError)):
                traceback.print_exc()
            return {"error": str(e) or e.__class__.__name__}

    @property
    def agent(self):
        if self._agent is None:
            from .agent.service import AgentService
            self._agent = AgentService(self)
        return self._agent

    def _hide(self) -> bool:
        return bool(self.db.get_setting("hide_names", False))

    # ---------------------------------------------------------------- start-up
    def api_init(self) -> dict:
        months = analytics.month_list(self.db)
        default = months[0]["value"] if months else None
        mm = engine.model(self.db, default) if default else None
        counts = {k: self.db.val(f"SELECT COUNT(*) FROM imports WHERE kind=? AND active=1", (k,), 0)
                  for k in ("roster", "attendance", "productivity", "sales", "leave")}
        return {"version": __version__, "months": months, "month": default, "demo": self.demo,
                "options": analytics.options(mm, {}) if mm else {"cities": [], "formats": [], "stores": [], "depts": [], "sections": []},
                "counts": counts, "has_data": any(counts.values()), "hide_names": self._hide(),
                "theme": self.db.get_setting("theme", "auto"), "ai": self.agent.public_status(),
                "unsure_stores": self.db.val("SELECT COUNT(*) FROM store_aliases WHERE confirmed=0", (), 0)}

    def api_options(self, month: str | None = None, scope: dict | None = None) -> dict:
        return analytics.options(engine.model(self.db, month), scope or {})

    # ---------------------------------------------------------------- screens
    def api_dashboard(self, month=None, scope=None, compare=None) -> dict:
        return analytics.dashboard(self.db, month, scope or {}, compare, self._hide())

    def api_people(self, month=None, scope=None, q="", role="", band="", sort="score", desc=True, limit=500, offset=0, flag=""):
        return analytics.people_list(self.db, month, scope or {}, q, role, band, sort, desc, limit, offset, self._hide(), flag)

    def api_person(self, emp: str, month=None) -> dict:
        return analytics.person(self.db, month, str(emp), self._hide())

    def api_stores(self, month=None, scope=None) -> dict:
        mm = engine.model(self.db, month)
        return {"month": mm.month, "rows": analytics.store_league(mm, scope or {})}

    def api_store(self, store_id: int, month=None) -> dict:
        return analytics.store_detail(self.db, month, int(store_id), self._hide())

    def api_attendance(self, month=None, scope=None) -> dict:
        return analytics.attendance_view(self.db, month, scope or {}, self._hide())

    def api_org(self, month=None, store_id=None) -> dict:
        return analytics.org_chart(self.db, month, store_id, self._hide())

    def api_compare(self, emps: list, month=None) -> dict:
        return {"people": [analytics.person(self.db, month, str(e), self._hide()) for e in emps[:4]]}

    def api_search(self, q: str, month=None) -> dict:
        mm = engine.model(self.db, month)
        nq = (q or "").strip().lower()
        if len(nq) < 2:
            return {"people": [], "stores": []}
        ppl = [p for p in mm.people.values() if nq in p.name.lower() or nq in p.emp][:12]
        sts = [s for s in mm.stores.values() if nq in s["name"].lower()][:6]
        return {"people": [{"emp": p.emp, "name": p.name if not self._hide() else f"Employee {p.emp}",
                            "sub": f"{p.designation} · {p.store}"} for p in ppl],
                "stores": [{"store_id": s["id"], "name": s["name"], "sub": FORMAT_LABEL.get(s["format"], "")} for s in sts]}

    # ---------------------------------------------------------------- imports
    def api_pick_files(self) -> dict:
        paths = self.host.pick_files("reports")
        return self.api_import_analyze(paths=paths) if paths else {"cancelled": True}

    def api_import_analyze(self, paths: list | None = None, text: str | None = None, name: str = "Pasted data") -> dict:
        analyses = []
        errors = []
        for p in paths or []:
            try:
                analyses.append(importers.analyze_path(p))
            except Exception as e:
                errors.append({"file": Path(p).name, "error": str(e)})
        if text:
            analyses.append(importers.analyze_text(text, name))
        token = uuid.uuid4().hex[:12]
        self.sessions[token] = {"analyses": analyses, "created": now()}
        suggested = self._suggest_month()
        return {"token": token, "files": [importers.describe(a) for a in analyses], "errors": errors,
                "suggested_month": suggested}

    def api_import_upload(self, files: list) -> dict:
        """Files sent from a browser (development / tests): [{name, b64}]."""
        import base64
        analyses, errors = [], []
        for f in files:
            try:
                analyses.append(importers.analyze_bytes(base64.b64decode(f["b64"]), f["name"]))
            except Exception as e:
                errors.append({"file": f.get("name", "?"), "error": str(e)})
        token = uuid.uuid4().hex[:12]
        self.sessions[token] = {"analyses": analyses, "created": now()}
        return {"token": token, "files": [importers.describe(a) for a in analyses], "errors": errors,
                "suggested_month": self._suggest_month()}

    def _suggest_month(self) -> str:
        m = engine.months_available(self.db)
        return m[-1] if m else date.today().strftime("%Y-%m")

    def api_import_commit(self, token: str, options: dict | None = None) -> dict:
        sess = self.sessions.get(token)
        if not sess:
            raise ValueError("This preview has expired. Please add the files again.")
        options = options or {}
        out = []
        for a in sess["analyses"]:
            try:
                out.append({"file": a["file"], "results": importers.commit(self.db, a, options.get(a["file"], {}))})
            except Exception as e:
                out.append({"file": a["file"], "error": str(e)})
        self.sessions.pop(token, None)
        return {"done": out, "months": analytics.month_list(self.db)}

    def api_imports(self) -> dict:
        rows = [dict(r) for r in self.db.q("SELECT * FROM imports ORDER BY id DESC LIMIT 500")]
        for r in rows:
            r["warnings"] = json.loads(r["warnings"] or "[]")
            r["summary"] = (r["summary"] or "").rsplit(" [", 1)[0]
        return {"rows": rows}

    def api_import_undo(self, import_id: int) -> dict:
        return importers.undo(self.db, int(import_id))

    def api_import_redo(self, import_id: int) -> dict:
        return importers.redo(self.db, int(import_id))

    # ---------------------------------------------------------------- settings
    def api_settings(self) -> dict:
        w, r = engine.settings(self.db)
        return {"weights": w, "rules": r, "default_weights": engine.DEFAULT_WEIGHTS, "default_rules": engine.DEFAULT_RULES,
                "labels": engine.COMPONENT_LABEL, "role_labels": {k: v for k, v in __import__("pno.org", fromlist=["x"]).ROLE_LABEL.items()},
                "hide_names": self._hide(), "theme": self.db.get_setting("theme", "auto"),
                "weights_history": self.db.get_setting("weights_history", []), "data_dir": str(data_dir()),
                "db_path": str(self.db.path), "version": __version__}

    def api_settings_save(self, weights: dict | None = None, rules: dict | None = None, hide_names=None, theme=None) -> dict:
        if weights is not None:
            clean = {}
            for role, ws in weights.items():
                clean[role] = {k: float(v) for k, v in ws.items() if v not in (None, "") and float(v) > 0}
                if not clean[role]:
                    raise ValueError(f"Every role needs at least one weighted part ({role}).")
            hist = self.db.get_setting("weights_history", []) or []
            hist.append({"at": now(), "weights": clean, "rules": rules or self.db.get_setting("rules", {})})
            self.db.set_setting("weights_history", hist[-30:])
            self.db.set_setting("weights", clean)
        if rules is not None:
            cur = self.db.get_setting("rules", {}) or {}
            for k, v in rules.items():
                if k in engine.DEFAULT_RULES:
                    cur[k] = v
            self.db.set_setting("rules", cur)
        if hide_names is not None:
            self.db.set_setting("hide_names", bool(hide_names))
        if theme is not None:
            self.db.set_setting("theme", theme)
        self.db.log("settings", "saved")
        return {"ok": True}

    def api_settings_reset(self) -> dict:
        self.db.x("DELETE FROM settings WHERE key IN ('weights','rules')")
        return {"ok": True}

    # stores
    def api_store_list(self) -> dict:
        stores = [dict(r) for r in self.db.q("SELECT * FROM stores ORDER BY format, city, name")]
        aliases = [dict(r) for r in self.db.q("SELECT a.*, s.name AS store_name FROM store_aliases a JOIN stores s ON s.id=a.store_id ORDER BY a.confirmed, a.raw")]
        for s in stores:
            s["format_label"] = FORMAT_LABEL.get(s["format"], "")
            s["city_label"] = CITIES.get(s["city"], s["city"])
        return {"stores": stores, "aliases": aliases}

    def api_store_alias_set(self, alias: str, store_id: int, confirm: bool = True) -> dict:
        self._relink_store_rows(alias, int(store_id), confirm)
        return {"ok": True}

    def _relink_store_rows(self, alias: str, store_id: int, confirm: bool = True) -> None:
        """Point a store name at another store; rows imported under that name follow it. All or nothing."""
        raw = self.db.val("SELECT raw FROM store_aliases WHERE alias=?", (alias,))
        if not raw:
            raise ValueError("Unknown store name.")
        clash = self.db.q1("""SELECT 1 FROM sales a JOIN sales b ON b.import_id=a.import_id AND b.period=a.period
                              AND b.as_of=a.as_of AND b.code=a.code AND b.store_id=? AND b.store_raw<>a.store_raw
                              WHERE a.store_raw=? LIMIT 1""", (store_id, raw)) or \
            self.db.q1("""SELECT 1 FROM productivity a JOIN productivity b ON b.import_id=a.import_id AND b.row_code=a.row_code
                          AND b.store_id=? AND b.store_raw<>a.store_raw WHERE a.store_raw=? LIMIT 1""", (store_id, raw))
        if clash:
            raise ValueError("That store already has its own figures in the same report, so these are two different "
                             "stores. Choose another store or keep it separate.")
        with self.db.tx() as db:
            c = db.conn
            c.execute("UPDATE store_aliases SET store_id=?, confirmed=? WHERE alias=?", (store_id, int(bool(confirm)), alias))
            c.execute("UPDATE roster SET store_id=? WHERE bu_raw=?", (store_id, raw))
            c.execute("UPDATE att_people SET store_id=? WHERE bu_raw=?", (store_id, raw))
            c.execute("UPDATE sales SET store_id=? WHERE store_raw=?", (store_id, raw))
            c.execute("UPDATE productivity SET store_id=? WHERE store_raw=?", (store_id, raw))
            c.execute("""UPDATE attendance_all SET store_id=? WHERE EXISTS (SELECT 1 FROM att_people ap
                         WHERE ap.import_id=attendance_all.import_id AND ap.emp_no=attendance_all.emp_no AND ap.bu_raw=?)""",
                      (store_id, raw))
            c.execute("DELETE FROM stores WHERE id NOT IN (SELECT store_id FROM store_aliases)")
        self.db.rebuild_attendance()

    def api_store_new(self, alias: str) -> dict:
        """Split an alias that was linked to the wrong store into a store of its own."""
        from .stores import parse_name
        raw = self.db.val("SELECT raw FROM store_aliases WHERE alias=?", (alias,))
        if not raw:
            raise ValueError("Unknown store name.")
        p = parse_name(raw)
        key = f"{p.format}|{p.city}|{' '.join(p.tokens)}|{alias}"
        sid = self.db.x("INSERT INTO stores(key, name, format, city, code, is_ho) VALUES(?,?,?,?,?,?)",
                        (key, p.name, p.format, p.city, p.code, int(p.is_ho))).lastrowid
        self._relink_store_rows(alias, sid)
        return {"ok": True, "store_id": sid}

    def api_store_update(self, store_id: int, name: str | None = None, is_ho: bool | None = None) -> dict:
        if name:
            self.db.x("UPDATE stores SET name=? WHERE id=?", (name.strip(), int(store_id)))
        if is_ho is not None:
            self.db.x("UPDATE stores SET is_ho=? WHERE id=?", (int(bool(is_ho)), int(store_id)))
        return {"ok": True}

    def api_section_map(self) -> dict:
        mm = engine.model(self.db)
        from .org import map_section
        over = self.db.get_setting("section_map", {}) or {}
        secs = sorted({(p.section, p.dept_code) for p in mm.people.values() if p.section})
        rows = []
        for s, d in secs:
            from .util import norm
            m = map_section(s, d, over)
            rows.append({"section": s, "dept": d, "key": norm(s), "map": m, "overridden": norm(s) in over})
        return {"rows": rows}

    def api_section_map_set(self, key: str, codes: list | None = None, dept: str | None = None, store: bool = False,
                            service: bool = False, reset: bool = False) -> dict:
        over = self.db.get_setting("section_map", {}) or {}
        if reset:
            over.pop(key, None)
        else:
            over[key] = ({"codes": [c.strip().upper() for c in codes if c.strip()]} if codes else {"dept": dept} if dept
                         else {"store": True} if store else {"service": True} if service else {})
        self.db.set_setting("section_map", over)
        return {"ok": True}

    def api_manager_set(self, emp: str, manager_emp: str | None) -> dict:
        over = self.db.get_setting("manager_overrides", {}) or {}
        over[str(emp)] = str(manager_emp) if manager_emp else ""
        self.db.set_setting("manager_overrides", over)
        return {"ok": True}

    # holidays & leave
    def api_holidays(self, year: int | None = None) -> dict:
        rows = [dict(r) for r in self.db.q("SELECT h.day, h.name FROM holidays h LEFT JOIN imports i ON i.id=h.import_id "
                                           "WHERE h.import_id IS NULL OR i.active=1 ORDER BY h.day")]
        if year:
            rows = [r for r in rows if r["day"].startswith(str(year))]
        return {"rows": rows}

    def api_holiday_add(self, day: str, name: str) -> dict:
        d = parse_date(day)
        if not d or not name.strip():
            raise ValueError("Give a date and a name for the holiday.")
        self.db.x("INSERT OR REPLACE INTO holidays(day, name) VALUES(?,?)", (d.isoformat(), name.strip()))
        self.db.log("holiday", f"{d} {name}")
        return {"ok": True}

    def api_holiday_delete(self, day: str) -> dict:
        self.db.x("DELETE FROM holidays WHERE day=?", (day,))
        return {"ok": True}

    def api_holidays_defaults(self, year: int) -> dict:
        n = 0
        for md, name in FIXED_HOLIDAYS:
            if not self.db.q1("SELECT 1 FROM holidays WHERE day=?", (f"{int(year)}-{md}",)):
                self.db.x("INSERT INTO holidays(day, name) VALUES(?,?)", (f"{int(year)}-{md}", name))
                n += 1
        return {"ok": True, "added": n}

    def api_leaves(self, month: str | None = None, emp: str | None = None) -> dict:
        sql = ("SELECT l.*, i.source FROM leaves l LEFT JOIN imports i ON i.id=l.import_id "
               "WHERE (l.import_id IS NULL OR i.active=1)")
        params: list = []
        if month:
            sql += " AND l.d_to>=? AND l.d_from<=?"
            params += [f"{month}-01", f"{month}-31"]
        if emp:
            sql += " AND l.emp_no=?"
            params.append(emp)
        rows = [dict(r) for r in self.db.q(sql + " ORDER BY l.d_from DESC LIMIT 2000", params)]
        mm = engine.model(self.db, month) if month else engine.model(self.db)
        for r in rows:
            p = mm.people.get(r["emp_no"])
            r["name"] = (p.name if not self._hide() else f"Employee {p.emp}") if p else "(not in this month)"
            r["store"] = p.store if p else ""
        return {"rows": rows}

    def api_leave_add(self, emp: str, d_from: str, d_to: str | None = None, type: str = "Annual Leave", note: str = "",
                      source: str = "manual") -> dict:
        a, b = parse_date(d_from), parse_date(d_to or d_from)
        if not a or not b:
            raise ValueError("Give valid dates for the leave.")
        if b < a:
            a, b = b, a
        mm = engine.model(self.db)
        if str(emp) not in mm.people and not self.db.q1("SELECT 1 FROM roster WHERE emp_no=?", (str(emp),)):
            raise ValueError(f"Employee {emp} is not in the imported data.")
        iid = self.db.x("INSERT INTO imports(kind, file_name, file_hash, month, as_of, rows, summary, source, created_at) "
                        "VALUES('leave', ?, ?, ?, ?, 1, ?, ?, ?)",
                        (f"{'Agent' if source == 'agent' else 'Manual'} entry", uuid.uuid4().hex, b.isoformat()[:7], b.isoformat(),
                         f"Leave for {emp}: {a} to {b} ({type})", source, now())).lastrowid
        self.db.x("INSERT INTO leaves(emp_no, d_from, d_to, type, note, import_id, created_at) VALUES(?,?,?,?,?,?,?)",
                  (str(emp), a.isoformat(), b.isoformat(), type or "Leave", note, iid, now()))
        return {"ok": True, "import_id": iid}

    def api_leave_delete(self, leave_id: int) -> dict:
        r = self.db.q1("SELECT import_id FROM leaves WHERE id=?", (int(leave_id),))
        self.db.x("DELETE FROM leaves WHERE id=?", (int(leave_id),))
        if r and r[0] and not self.db.q1("SELECT 1 FROM leaves WHERE import_id=?", (r[0],)):
            self.db.x("UPDATE imports SET active=0 WHERE id=? AND source IN ('manual','agent')", (r[0],))
        return {"ok": True}

    def api_note_add(self, emp: str, text: str, day: str | None = None) -> dict:
        if not text.strip():
            raise ValueError("Write a note first.")
        self.db.x("INSERT INTO notes(emp_no, day, text, created_at) VALUES(?,?,?,?)", (str(emp), day, text.strip(), now()))
        return {"ok": True}

    def api_note_delete(self, note_id: int) -> dict:
        self.db.x("DELETE FROM notes WHERE id=?", (int(note_id),))
        return {"ok": True}

    # ---------------------------------------------------------------- exports
    def api_export(self, pack: str, fmt: str, month=None, scope=None, emp=None, store_id=None, hide=None, save_as=None,
                   open_after: bool = True) -> dict:
        from . import exports
        hide_names = self._hide() if hide is None else bool(hide)
        report = exports.build_pack(self.db, pack, month, scope or {}, emp=emp, store_id=store_id, hide=hide_names)
        name = exports.file_name(report, fmt)
        path = save_as or self.host.save_path(name, fmt)
        if not path:
            return {"cancelled": True}
        exports.render(report, fmt, path)
        self.db.log("export", f"{pack} {fmt} {path}")
        if open_after:
            self.host.open_path(path)
        return {"ok": True, "path": path, "name": Path(path).name}

    def api_open_path(self, path: str) -> dict:
        self.host.open_path(path)
        return {"ok": True}

    # ---------------------------------------------------------------- backup / demo
    def api_backup(self) -> dict:
        path = self.host.save_path(f"PNO backup {date.today():%Y-%m-%d}.sqlite3", "backup")
        if not path:
            return {"cancelled": True}
        self.db.backup(path)
        return {"ok": True, "path": path}

    def api_restore(self, path: str | None = None) -> dict:
        if not path:
            paths = self.host.pick_files("backup")
            if not paths:
                return {"cancelled": True}
            path = paths[0]
        self.db.restore(path)
        return {"ok": True}

    def api_demo(self, on: bool = True) -> dict:
        if on and not self.demo:
            demo_db = Database(data_dir() / "pno-demo.sqlite3")
            if not demo_db.val("SELECT COUNT(*) FROM imports", (), 0):
                load_demo(demo_db)
            self.db, self.demo = demo_db, True
        elif not on and self.demo:
            self.db.close()
            self.db, self.demo = self.real_db, False
        return self.api_init()

    def api_audit(self) -> dict:
        return {"rows": [dict(r) for r in self.db.q("SELECT * FROM audit ORDER BY id DESC LIMIT 300")]}

    # ---------------------------------------------------------------- agent
    def api_agent_status(self) -> dict:
        return self.agent.status()

    def api_agent_settings(self, **kw) -> dict:
        return self.agent.save_settings(**kw)

    def api_agent_test(self) -> dict:
        return self.agent.test()

    def api_agent_ask(self, question: str, history: list | None = None, month=None, scope=None, attachments=None) -> dict:
        return self.agent.ask(question, history or [], month, scope or {}, attachments or [])

    def api_agent_confirm(self, action_id: str, approve: bool = True) -> dict:
        return self.agent.confirm(action_id, approve)

    def api_agent_attach(self) -> dict:
        paths = self.host.pick_files("reports")
        return {"paths": paths}

    def api_offline_status(self) -> dict:
        return self.agent.offline_status()

    def api_offline_install(self, what: str = "all") -> dict:
        return self.agent.offline_install(what)

    def api_offline_pick_model(self) -> dict:
        paths = self.host.pick_files("gguf")
        return self.agent.offline_link(paths[0]) if paths else {"cancelled": True}

    def api_downloads(self) -> dict:
        return self.agent.downloads()

    def api_month_label(self, month: str) -> dict:
        return {"label": month_label(month)}


def load_demo(db: Database) -> None:
    """Fill a database with the fictional demo files (two months) plus holidays."""
    from . import demo
    d = demo.build()
    for name, data in d.files.items():
        a = importers.analyze_bytes(data, name)
        importers.commit(db, a, {"*": {"as_of": "2026-09-30"}} if "Employee" in name else None, source="demo")
    for md, name in FIXED_HOLIDAYS:
        db.x("INSERT OR IGNORE INTO holidays(day, name) VALUES(?,?)", (f"2026-{md}", name))
