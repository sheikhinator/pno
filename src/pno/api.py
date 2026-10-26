"""The data service behind every screen. JavaScript calls dispatch(method, params) and gets JSON back."""

from __future__ import annotations

import json
import re
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
    def hiring(self):
        if getattr(self, "_hiring", None) is None:
            from .hiring import Hiring
            self._hiring = Hiring(self)
        return self._hiring

    @property
    def learning(self):
        if getattr(self, "_learning", None) is None:
            from .learning import Learning
            self._learning = Learning(self)
        return self._learning

    # ---------------------------------------------------------------- learning studio
    def api_learn_list(self) -> dict:
        return {**self.learning.courses(), "stats": self.learning.stats()}

    def api_learn_build(self, **kw) -> dict:
        return self.learning.build(**kw)

    def api_learn_course(self, course_id: int) -> dict:
        return self.learning.course(int(course_id))

    def api_learn_delete(self, course_id: int) -> dict:
        return self.learning.delete(int(course_id))

    def api_learn_duplicate(self, course_id: int) -> dict:
        return self.learning.duplicate(int(course_id))

    def api_learn_edit(self, course_id: int, content: dict) -> dict:
        return self.learning.edit(int(course_id), content)

    def api_learn_rewrite(self, course_id: int, module: int, lesson: int, how: str) -> dict:
        return self.learning.rewrite(int(course_id), int(module), int(lesson), how)

    def api_learn_for_person(self, key: str, hours: float = 3, lecture_min: int = 20) -> dict:
        return self.learning.for_person(key, hours, lecture_min)

    def api_learn_people(self) -> dict:
        return {"people": self.learning.people()}

    def api_learn_assign(self, course_id: int, people: list, due: str | None = None) -> dict:
        return self.learning.assign(int(course_id), people, due)

    def api_learn_result(self, assignment_id: int, status: str | None = None, score=None, notes: str | None = None) -> dict:
        return self.learning.result(int(assignment_id), status, score, notes)

    def api_learn_unassign(self, assignment_id: int) -> dict:
        return self.learning.remove_assignment(int(assignment_id))

    def api_learn_path_save(self, name: str, level: int, course_ids: list, path_id: int | None = None) -> dict:
        return self.learning.save_path(name, level, [int(c) for c in course_ids], path_id)

    def api_learn_path_delete(self, path_id: int) -> dict:
        return self.learning.delete_path(int(path_id))

    def api_learn_export(self, course_id: int, fmt: str = "pdf", save_as: str | None = None, open_after: bool = True) -> dict:
        from .learning import export as LX
        if fmt not in LX.EXPORTERS:
            raise ValueError("Choose PDF, answer key, PowerPoint, Word, Excel or the full pack.")
        c = self.learning.course(int(course_id))
        name = f"{LX.safe_name(c['content']['title'])} - {LX.SUFFIX[fmt]}.{LX.EXT[fmt]}"
        path = save_as or self.host.save_path(name, LX.EXT[fmt])
        if not path:
            return {"cancelled": True}
        if fmt in ("xlsx", "zip"):
            LX.EXPORTERS[fmt](c["content"], path, c["assignments"])
        else:
            LX.EXPORTERS[fmt](c["content"], path)
        self.db.log("export", f"course #{course_id} {fmt} {path}")
        if open_after:
            self.host.open_path(path)
        return {"ok": True, "path": path, "name": Path(path).name}

    def api_learn_certificate(self, assignment_id: int, save_as: str | None = None, open_after: bool = True) -> dict:
        from .learning import export as LX
        a = self.db.q1("SELECT a.*, c.title, c.hours FROM assignments a JOIN courses c ON c.id=a.course_id WHERE a.id=?", (int(assignment_id),))
        if not a:
            raise ValueError("Assignment not found.")
        name = a["person_name"] or a["person"]
        path = save_as or self.host.save_path(f"Certificate - {LX.safe_name(name)} - {LX.safe_name(a['title'])}.pdf", "pdf")
        if not path:
            return {"cancelled": True}
        LX.certificate(name, a["title"], path, f"{a['score']:.0f}%" if a["score"] is not None else "", a["hours"],
                       (a["completed_at"] or "")[:10])
        if open_after:
            self.host.open_path(path)
        return {"ok": True, "path": path, "name": Path(path).name}

    # ---------------------------------------------------------------- hiring (vacancies, CVs, pipeline)
    def api_hire_list(self) -> dict:
        self.hiring.retention()
        return self.hiring.vacancies()

    def api_hire_draft(self, title: str = "", role: str = "", store: str = "", section: str = "", category: str = "") -> dict:
        return self.hiring.draft(title, role, store, section, category)

    def api_hire_ai_jd(self, title: str, store: str = "", section: str = "", notes: str = "") -> dict:
        d = self.hiring.draft(title, "", store, section)
        out = self.agent.complete(
            "Write a clear, professional job description for Majid Al Futtaim Carrefour Pakistan in markdown with sections: Purpose of the role, "
            "Key responsibilities (6-8 bullets), What you bring (experience, education, skills), Competencies, Working conditions. "
            f"Role: {title}. Store: {store or 'any'}. Section: {section or 'any'}. Extra notes from the hiring manager: {notes or 'none'}. "
            "Never ask for age, gender, marital status or religion.", max_tokens=900)
        if out:
            d["jd"], d["engine"] = out[0], out[1]
        else:
            d["note"] = "No AI is set up: the built-in JD for this role is shown."
        return d

    def api_hire_save(self, **v) -> dict:
        return self.hiring.save_vacancy(**v)

    def api_hire_delete(self, vacancy_id: int) -> dict:
        return self.hiring.delete_vacancy(int(vacancy_id))

    def api_hire_vacancy(self, vacancy_id: int, blind: bool = False) -> dict:
        return self.hiring.vacancy(int(vacancy_id), bool(blind))

    def api_hire_upload(self, files: list, vacancy_id: int | None = None, source: str = "Upload") -> dict:
        return self.hiring.add_uploads(files, vacancy_id, source)

    def api_hire_add_paths(self, paths: list, vacancy_id: int | None = None, source: str = "Upload") -> dict:
        return self.hiring.add_cvs(paths, vacancy_id, source)

    def api_hire_pick(self, vacancy_id: int | None = None, source: str = "Upload") -> dict:
        paths = self.host.pick_files("cvs")
        if not paths:
            return {"cancelled": True}
        return self.hiring.add_cvs(paths, vacancy_id, source)

    def api_hire_candidate(self, candidate_id: int, vacancy_id: int | None = None, blind: bool = False) -> dict:
        return self.hiring.candidate(int(candidate_id), vacancy_id, bool(blind))

    def api_hire_candidate_update(self, candidate_id: int, **kw) -> dict:
        return self.hiring.update_candidate(int(candidate_id), **kw)

    def api_hire_candidate_delete(self, candidate_id: int) -> dict:
        return self.hiring.delete_candidate(int(candidate_id))

    def api_hire_apply(self, vacancy_id: int, candidate_ids: list) -> dict:
        for c in candidate_ids:
            self.hiring.apply(int(vacancy_id), int(c))
        return self.hiring.vacancy(int(vacancy_id))

    def api_hire_stage(self, app_id: int, stage: str, note: str = "") -> dict:
        return self.hiring.set_stage(int(app_id), stage, note)

    def api_hire_kit(self, app_id: int, ai: bool = True) -> dict:
        return self.hiring.kit(int(app_id), bool(ai))

    def api_hire_panel(self, app_id: int, interviewer: str, scores: dict, note: str = "", decision: str = "") -> dict:
        return self.hiring.panel_score(int(app_id), interviewer, scores, note, decision)

    def api_hire_onboarding(self, app_id: int, item: str, done: bool) -> dict:
        return self.hiring.onboarding(int(app_id), item, bool(done))

    def api_hire_message(self, app_id: int, kind: str = "invite", lang: str = "en", when: str = "", place: str = "") -> dict:
        return self.hiring.message(int(app_id), kind, lang, when, place)

    def api_hire_ai(self, app_id: int) -> dict:
        return self.hiring.ai_assess(int(app_id))

    def api_hire_bank(self, q: str = "", skill: str = "", city: str = "", min_years: float = 0) -> dict:
        return self.hiring.bank(q, skill, city, min_years or 0)

    def api_hire_match_bank(self, vacancy_id: int) -> dict:
        return self.hiring.match_bank(int(vacancy_id))

    def api_hire_analytics(self) -> dict:
        return self.hiring.analytics()

    def api_hire_settings(self, keep_months: int | None = None) -> dict:
        if keep_months:
            self.db.set_setting("hire_keep_months", max(1, int(keep_months)))
        return {"keep_months": self.db.get_setting("hire_keep_months", 12), **self.hiring.retention()}

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
        if not getattr(self, "_repaired", False):
            self._repaired = True
            try:
                self._repair_store_names()
            except Exception:
                traceback.print_exc()
        months = analytics.month_list(self.db)
        default = months[0]["value"] if months else None
        mm = engine.model(self.db, default) if default else None
        counts = {k: self.db.val(f"SELECT COUNT(*) FROM imports WHERE kind=? AND active=1", (k,), 0)
                  for k in ("roster", "attendance", "productivity", "sales", "leave")}
        return {"version": __version__, "months": months, "month": default, "demo": self.demo,
                "options": analytics.options(mm, {}) if mm else {"cities": [], "formats": [], "stores": [], "depts": [], "sections": []},
                "counts": counts, "has_data": any(counts.values()), "hide_names": self._hide(),
                "theme": self.db.get_setting("theme", "auto"), "ai": self.agent.public_status(),
                "unsure_stores": self.db.val("SELECT COUNT(*) FROM store_aliases WHERE confirmed=0", (), 0),
                "notice": self._take_notice()}

    def _take_notice(self) -> str:
        n, self.real_db.notice = getattr(self.real_db, "notice", ""), ""
        return n

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

    def api_org(self, month=None, store_id=None, auto=False) -> dict:
        return analytics.org_chart(self.db, month, store_id, self._hide(), bool(auto))

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
        return {"token": token, "files": self._lined_up([importers.describe(a) for a in analyses], analyses), "errors": errors,
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
        return {"token": token, "files": self._lined_up([importers.describe(a) for a in analyses], analyses), "errors": errors,
                "suggested_month": self._suggest_month()}

    def _suggest_month(self) -> str:
        m = engine.months_available(self.db)
        return m[-1] if m else date.today().strftime("%Y-%m")

    def _lined_up(self, files: list[dict], analyses: list[dict]) -> list[dict]:
        """Give sheets without a month of their own the month of the other sheets, and remember it for saving."""
        from .period import line_up
        known = self.db.q1("""SELECT MAX(period_to) FROM imports WHERE active=1 AND period_type IN ('ytd','mtd')
                              AND kind NOT IN ('po_turnover','po_shift','attendance')""")
        line_up([r for f in files for r in f["results"]], known[0] if known else None)
        for f, a in zip(files, analyses):
            a["period_hint"] = {(r["sheet"], r["kind"]): r["period"] for r in f["results"]}
        return files

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
        new_sets = [r["import_id"] for f in out for r in f.get("results", []) if r.get("kind") == "dataset" and r.get("status") == "ok"]
        if new_sets:
            threading.Thread(target=self._ai_label_datasets, args=(new_sets,), daemon=True).start()
        return {"done": out, "months": analytics.month_list(self.db)}

    def api_imports(self) -> dict:
        from .period import label as period_label
        rows = [dict(r) for r in self.db.q("SELECT * FROM imports ORDER BY id DESC LIMIT 500")]
        for r in rows:
            r["warnings"] = json.loads(r["warnings"] or "[]")
            r["summary"] = (r["summary"] or "").rsplit(" [", 1)[0]
            r["period_label"] = period_label(r.get("period_type"), r.get("period_from"), r.get("period_to")) if r.get("period_type") else ""
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

    def _repair_store_names(self) -> None:
        """Earlier versions misread names like 'PK HM GUJ Steel Casting' as a store with no format: relink them once."""
        from .stores import StoreResolver, parse_name
        bad = self.db.q("""SELECT a.alias, a.raw, a.store_id FROM store_aliases a JOIN stores s ON s.id=a.store_id
                           WHERE COALESCE(s.format,'')='' AND COALESCE(s.is_ho,0)=0""")
        for row in bad:
            p = parse_name(row["raw"])
            if not p.format:
                continue
            target, _sure = StoreResolver(self.db)._match(p)
            fmt = self.db.val("SELECT format FROM stores WHERE id=?", (target,), "") if target else ""
            if target == row["store_id"] or not fmt:
                target = None
            if target is None:
                key = f"{p.format}|{p.city}|{' '.join(p.tokens)}"
                ex = self.db.q1("SELECT id FROM stores WHERE key=?", (key,))
                target = ex[0] if ex else self.db.x(
                    "INSERT INTO stores(key, name, format, city, code, is_ho) VALUES(?,?,?,?,?,0)",
                    (key, p.name, p.format, p.city, p.code)).lastrowid
            if target != row["store_id"]:
                try:
                    self._relink_store_rows(row["alias"], target)
                except ValueError:
                    pass

    def api_store_new(self, alias: str) -> dict:
        """Split an alias that was linked to the wrong store into a store of its own."""
        from .stores import parse_name
        raw = self.db.val("SELECT raw FROM store_aliases WHERE alias=?", (alias,))
        if not raw:
            raise ValueError("Unknown store name.")
        cur = self.db.val("SELECT store_id FROM store_aliases WHERE alias=?", (alias,))
        if self.db.val("SELECT COUNT(*) FROM store_aliases WHERE store_id=?", (cur,), 0) <= 1:
            self.db.x("UPDATE store_aliases SET confirmed=1 WHERE alias=?", (alias,))
            return {"ok": True, "store_id": cur, "message": "This name is already a store of its own."}
        p = parse_name(raw)
        base = f"{p.format}|{p.city}|{' '.join(p.tokens)}|{alias}"
        key, n = base, 1
        while self.db.q1("SELECT 1 FROM stores WHERE key=?", (key,)):
            n += 1
            key = f"{base}#{n}"
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
        if pack == "hiring":
            report = self.hiring.report(int(emp or store_id), hide_names)
        else:
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

    # ---------------------------------------------------------------- P&O review (the ten-tab P&O workbook)
    def _po(self):
        from .po import privacy
        from .po.insights import Insights
        from .po.store import PoStore

        hide = self._hide()
        privacy.set_demo_mode(hide)
        weights = self.db.get_setting("po_weights", None)
        view = self.db.get_setting("po_view", None)
        key = (str(self.db.path), self.db.version, json.dumps(weights, sort_keys=True), json.dumps(view, sort_keys=True), hide)
        cached = getattr(self, "_po_cache", None)
        if cached and cached[0] == key:
            return cached[1]
        ins = Insights(PoStore(self.db), weights=weights, view=view)
        self._po_cache = (key, ins)
        return ins

    def _po_period(self, ins) -> dict:
        """The period every P&O screen is showing, what each tab contributes to it, and the choices available."""
        from .po.insights import PACK_LABELS, _ml
        cov = sorted(ins.coverage, key=lambda c: (c.get("type") != "general", PACK_LABELS.get(c["kind"], c["kind"])))
        from .datahealth import _age
        created = {r["id"]: r["created_at"] for r in self.db.q("SELECT id, created_at FROM imports WHERE active=1")}
        return {"view": ins.view, "label": ins.view_label, "notes": ins.notes, "leaver_window": ins.leaver_window,
                "sales_label": ins.periods.get("po_sales") or "",
                "months": [{"value": m, "label": _ml(m)} for m in ins.available["months"]], "types": ins.available["types"],
                "ytd_from": ins.available.get("ytd_from", {}), "default_to": ins.available.get("default_to"),
                "coverage": [{"name": PACK_LABELS.get(c["kind"], c["kind"]), "type": c.get("type") or "", "label": c.get("label") or "—",
                              "rows": c["rows"], "note": c.get("note", ""), "how": c.get("how", ""),
                              "age": _age(created.get(c.get("iid")))} for c in cov]}

    def api_data_health(self, month: str | None = None) -> dict:
        from . import datahealth
        from .po.insights import Insights
        from .po.store import PoStore
        ins = Insights(PoStore(self.db), view={"type": "latest"})
        return datahealth.report(self.db, ins, month)

    def api_lock_month(self, month: str, locked: bool = True) -> dict:
        from . import datahealth
        datahealth.set_lock(self.db, month, bool(locked))
        return self.api_data_health(month)

    def api_po_period(self) -> dict:
        ins = self._po()
        return {"has_data": not ins.empty, **self._po_period(ins)}

    def api_po_view(self, type: str = "latest", **kw) -> dict:  # noqa: A002 - matches the screen's field name
        """Choose the period for the P&O screens: latest data, one month (MTD) or a year-to-date range (from–to)."""
        view = {"type": type if type in ("latest", "mtd", "ytd") else "latest", "from": kw.get("from"), "to": kw.get("to")}
        self.db.set_setting("po_view", view)
        return self.api_po_period()

    def api_po_review(self, metric: str = "sales_vs_budget") -> dict:
        from .po.insights import PACK_LABELS
        ins = self._po()
        if ins.empty:
            return {"has_data": False, "period": self._po_period(ins)}
        h = ins.headline()
        stores, sections, values = ins.section_matrix(metric)
        return {"has_data": True, "period": self._po_period(ins), "headline": h, "stores": ins.store_scorecard(), "alerts": ins.alerts(40),
                "heat": {"metric": metric, "stores": stores, "sections": sections,
                         "values": [[values.get((st, sec)) for sec in sections] for st in stores]},
                "sources": [{"kind": PACK_LABELS.get(k, k), "source": v} for k, v in sorted(ins.sources.items())]}

    def _leader_row(self, ins, leader, ranks) -> dict:
        from .po.format import leader_name
        from .po.insights import tenure_text
        box = ins.talent_box(leader)
        return {"key": leader.key, "rank": ranks.get(leader.key), "name": leader_name(leader), "store": leader.store or "—",
                "leads": leader.section_text, "role": leader.designation, "system_role": leader.system_designation, "score": leader.score, "business": leader.business,
                "rating": leader.latest_rating, "rating_label": leader.rating_label, "in_role": tenure_text(leader.months_in_role),
                "months_in_role": leader.months_in_role, "talent": ins.TALENT_NAMES.get(box) if box else None}

    def api_po_leaders(self, q: str = "", store: str = "") -> dict:
        from .po.format import leader_name
        ins = self._po()
        if ins.empty:
            return {"has_data": False, "period": self._po_period(ins)}
        all_leaders = ins.leaders()
        ranks = {l.key: i + 1 for i, l in enumerate(x for x in all_leaders if x.score is not None)}
        rows = ins.find_leader(q) if q.strip() else all_leaders
        if store:
            rows = [l for l in rows if l.store == store]
        boxes = {}
        for l in all_leaders:
            b = ins.talent_box(l)
            if b:
                boxes.setdefault(b, []).append({"key": l.key, "name": leader_name(l), "store": l.store, "score": l.score})
        talent = [{"col": c, "row": r, "name": ins.TALENT_NAMES[(c, r)], "leaders": sorted(boxes.get((c, r), []), key=lambda x: -(x["score"] or 0))}
                  for r in (2, 1, 0) for c in (0, 1, 2)]
        bench = [{"severity": f["severity"], "reason": f["reason"], **self._leader_row(ins, f["leader"], ranks)} for f in ins.bench()]
        return {"has_data": True, "period": self._po_period(ins), "leaders": [self._leader_row(ins, l, ranks) for l in rows], "talent": talent, "bench": bench,
                "stores": sorted({l.store for l in all_leaders if l.store}), "weights": ins.weights,
                "scored": len(ranks), "total": len(all_leaders)}

    def api_po_leader(self, key: str) -> dict:
        from .po.format import leader_profile_html
        ins = self._po()
        leader = next((l for l in ins.leaders() if l.key == key), None)
        if not leader:
            raise ValueError("Leader not found.")
        return {"key": key, "html": leader_profile_html(ins, leader)}

    def api_po_turnover(self) -> dict:
        from .po import privacy
        ins = self._po()
        if ins.empty or not ins.has("po_turnover"):
            return {"has_data": False, "period": self._po_period(ins)}
        t = ins.turnover_summary()
        recent = sorted((r for r in ins.rows("po_turnover") if r.get("date")), key=lambda r: r["date"], reverse=True)[:40]
        return {"has_data": True, "period": self._po_period(ins), **t, "as_of": ins.as_of,
                "recent": [{"date": r["date"], "name": privacy.name(r["employee_name"], r.get("employee_id") or r["employee_name"]),
                            "store": r["store"], "section": r["section"], "type": r["exit_type"], "reason": r["reason"]} for r in recent]}

    def api_po_shifts(self, store: str = "") -> dict:
        from .po import canon, privacy
        ins = self._po()
        if ins.empty or not ins.has("po_shift"):
            return {"has_data": False, "period": self._po_period(ins)}
        r = ins.roster_summary()
        known = [s[0] for s in canon._STORES]
        stores = sorted(r["stores"], key=lambda n: (known.index(n) if n in known else 99, n))
        store = store if store in stores else (stores[0] if stores else "")
        rows = [x for x in ins.rows("po_shift") if x["store"] == store]
        people: dict = {}
        for x in rows:
            p = people.setdefault(x["employee_id"], {"emp": x["employee_id"], "name": privacy.name(x["employee_name"], x["employee_id"]),
                                                       "section": x["section"], "designation": x["designation"], "days": {}})
            p["days"][x["date"]] = x["shift"]
        grid = sorted(people.values(), key=lambda p: (canon.department(p["section"]), p["section"], p["name"]))
        return {"has_data": True, "period": self._po_period(ins), "stores": stores, "store": store, "days": r["days"], "people": r["people"], "mix": dict(r["mix"]),
                "grid": [{**p, "days": [p["days"].get(d, "Not rostered") for d in r["days"]]} for p in grid],
                "gaps": r["gaps"], "leave": [{"name": privacy.name(n, n), "store": s, "days": d} for n, s, d in r["leave"]]}

    # ---------------------------------------------------------------- Data explorer (any other table)
    def api_datasets(self) -> dict:
        from .po import explorer
        return {"datasets": explorer.datasets(self.db)}

    def api_dataset(self, import_id: int, group: str | None = None, measure: str | None = None, agg: str | None = None) -> dict:
        from .po import explorer
        return explorer.view(self.db, int(import_id), group, measure, agg)

    def _dataset_meta_save(self, import_id: int, **fields) -> None:
        row = self.db.q1("SELECT id, payload FROM po_records WHERE import_id=? AND kind='dataset_meta'", (import_id,))
        if row:
            meta = json.loads(row["payload"])
            meta.update(fields)
            self.db.x("UPDATE po_records SET payload=? WHERE id=?", (json.dumps(meta, ensure_ascii=False, default=str), row["id"]))

    def api_dataset_ai(self, import_id: int, question: str = "") -> dict:
        """AI-written insights for a dataset (from computed summaries, not raw files); built-in insights otherwise."""
        from .po import explorer
        v = explorer.view(self.db, int(import_id))
        prompt = ("You are an HR and retail analyst at Carrefour Pakistan. Below is a table imported into P&O, already summarised. "
                  "Write 4-7 short, specific insights a P&O director would act on, as markdown bullets, using only these numbers. "
                  "Then one line starting 'Title:' with a short title for the table and one line starting 'About:' describing "
                  "what the table contains in one sentence." + (f" Focus on: {question}" if question else "") +
                  "\n\n" + explorer.summary_for_ai(v))
        try:
            out = self.agent.complete(prompt, max_tokens=900)
        except Exception as e:  # noqa: BLE001 - shown to the user, built-in insights still apply
            return {"engine": "basic", "text": "", "note": str(e), "insights": v["insights"]}
        if not out:
            return {"engine": "basic", "text": "", "note": "No AI is set up (Settings → AI). Built-in insights are shown.",
                    "insights": v["insights"]}
        text, engine_name = out
        title = next((l.split(":", 1)[1].strip() for l in text.splitlines() if l.lower().startswith("title:")), "")
        about = next((l.split(":", 1)[1].strip() for l in text.splitlines() if l.lower().startswith("about:")), "")
        body = "\n".join(l for l in text.splitlines() if not l.lower().startswith(("title:", "about:"))).strip()
        self._dataset_meta_save(int(import_id), ai_insights=body, **({"ai_title": title[:80]} if title else {}),
                                **({"ai_description": about[:300]} if about else {}))
        return {"engine": engine_name, "text": body, "title": title, "about": about, "insights": v["insights"]}

    def _ai_label_datasets(self, import_ids: list[int]) -> None:
        """Right after import, if a cloud AI is set up, let it name each new dataset and its unclear columns."""
        from .po import explorer
        for iid in import_ids:
            try:
                meta, rows = explorer.load(self.db, iid)
                cols = [{"name": c["name"], "type": c["type"], "guess": c.get("role", ""), "sample": c.get("sample", [])}
                        for c in meta.get("columns", [])]
                note = meta.get("user_description", "")
                prompt = ("Columns of a table imported into a retail HR analytics app, with sample values." +
                          (f" The user describes it as: {note}." if note else "") + " Reply with JSON only: "
                          '{"title": short title, "about": one sentence, "roles": {column name: one of store, section, department, '
                          "employee_id, employee_name, designation, manager, city, date, month, actual, budget, target, last_year, "
                          'forecast, count, score, reason, type or ""}}.\n' + json.dumps(cols, default=str)[:6000])
                out = self.agent.complete(prompt, max_tokens=700, allow_offline=False)
                if not out:
                    return
                text = out[0]
                data = json.loads(text[text.find("{"): text.rfind("}") + 1])
                roles = data.get("roles") or {}
                for c in meta.get("columns", []):
                    r = roles.get(c["name"])
                    if r and not c.get("role"):
                        c["role"] = r
                self._dataset_meta_save(iid, columns=meta["columns"], ai_title=(meta.get("title") if meta.get("user_description") and meta.get("title") else str(data.get("title") or ""))[:80],
                                        ai_description=str(data.get("about") or "")[:300])
            except Exception:  # noqa: BLE001 - labelling is optional
                continue

    def api_po_nps(self, city: str = "") -> dict:
        from statistics import mean
        ins = self._po()
        rows = [r for r in ins.rows("po_nps") if r.get("nps") is not None and r.get("year")]
        if not rows:
            return {"has_data": False, "period": self._po_period(ins)}
        years = sorted({r["year"] for r in rows})
        latest, prev = years[-1], (years[-2] if len(years) > 1 else None)
        cities = sorted({r["city"] for r in rows})
        sections = [s for s in ("Beverages", "DPH", "Grocery", "OPSS", "Bakery", "Butchery", "Fishery", "Deli", "Fruits & Vegetables",
                                "Light Household", "Heavy Household", "Textile", "Myli") if any(r["section"] == s for r in rows)]
        sections += sorted({r["section"] for r in rows} - set(sections))

        def avg(items):
            vals = [r["nps"] for r in items]
            return round(mean(vals), 1) if vals else None

        def pick(c=None, sec=None, y=None):
            return [r for r in rows if (c is None or r["city"] == c) and (sec is None or r["section"] == sec) and (y is None or r["year"] == y)]

        matrix = [[avg(pick(c, sec, latest)) for sec in sections] for c in cities]
        change = [[(lambda a, b: None if a is None or b is None else round(a - b, 1))(avg(pick(c, sec, latest)), avg(pick(c, sec, prev)) if prev else None)
                   for sec in sections] for c in cities]
        scope = city if city in cities else ""
        cats = []
        for cat in sorted({r["category"] for r in pick(scope or None)}):
            now_ = avg([r for r in pick(scope or None, None, latest) if r["category"] == cat])
            before = avg([r for r in pick(scope or None, None, prev) if r["category"] == cat]) if prev else None
            sec = next((r["section"] for r in rows if r["category"] == cat), "")
            if now_ is not None or before is not None:
                cats.append({"category": cat, "section": sec, "nps": now_, "prev": before,
                             "change": None if now_ is None or before is None else round(now_ - before, 1)})
        ranked = sorted([c for c in cats if c["nps"] is not None], key=lambda c: -c["nps"])
        movers = sorted([c for c in cats if c["change"] is not None], key=lambda c: c["change"])
        overall = avg(pick(scope or None, None, latest))
        overall_prev = avg(pick(scope or None, None, prev)) if prev else None
        insights = []
        if overall is not None:
            insights.append(f"{'Overall' if not scope else scope} NPS {latest}: **{overall:+.0f}**" +
                            (f", {overall - overall_prev:+.0f} vs {prev}." if overall_prev is not None else "."))
        if ranked:
            insights.append(f"Best: **{ranked[0]['category']}** ({ranked[0]['nps']:+.0f}); weakest: **{ranked[-1]['category']}** ({ranked[-1]['nps']:+.0f}).")
        if movers:
            insights.append(f"Biggest drop: **{movers[0]['category']}** ({movers[0]['change']:+.0f}); biggest gain: **{movers[-1]['category']}** ({movers[-1]['change']:+.0f}).")
        neg = [c["category"] for c in ranked if c["nps"] < 0]
        if neg:
            insights.append(f"{len(neg)} categor{'y has' if len(neg) == 1 else 'ies have'} more detractors than promoters: {', '.join(neg[:5])}.")
        missing = [c for c in cities if not any(r["city"] == c for r in pick(None, None, latest))]
        if missing:
            insights.append(f"No {latest} survey yet for: {', '.join(missing)}.")
        by_city = [{"city": c, "nps": avg(pick(c, None, latest)), "prev": avg(pick(c, None, prev)) if prev else None,
                    "stores": [st for st in ins.stores() if __import__("pno.po.canon", fromlist=["x"]).store_city(st) == c]} for c in cities]
        return {"has_data": True, "period": self._po_period(ins), "years": years, "latest": latest, "prev": prev, "cities": cities, "city": scope, "sections": sections,
                "matrix": matrix, "change": change, "categories": cats, "best": ranked[:5], "worst": ranked[-5:][::-1],
                "drops": movers[:5], "gains": movers[-5:][::-1], "overall": overall, "overall_prev": overall_prev,
                "by_city": by_city, "insights": insights}

    def api_po_weights(self, weights: dict | None = None, reset: bool = False) -> dict:
        from .po.insights import DEFAULT_WEIGHTS, WEIGHT_LABELS
        if reset:
            self.db.x("DELETE FROM settings WHERE key='po_weights'")
        elif weights is not None:
            clean = {k: max(0.0, float(v)) for k, v in weights.items() if k in DEFAULT_WEIGHTS and v not in (None, "")}
            self.db.set_setting("po_weights", clean)
        current = {**DEFAULT_WEIGHTS, **(self.db.get_setting("po_weights", None) or {})}
        return {"weights": current, "labels": WEIGHT_LABELS, "defaults": DEFAULT_WEIGHTS}

    def api_open_path(self, path: str) -> dict:
        self.host.open_path(path)
        return {"ok": True}

    # ---------------------------------------------------------------- backup / demo
    def api_backup(self) -> dict:
        path = self.host.save_path(f"P&O backup {date.today():%Y-%m-%d}.sqlite3", "backup")
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

    def api_agent_test(self, provider: str | None = None, key: str | None = None, model: str | None = None) -> dict:
        return self.agent.test(provider, key, model)

    def api_agent_ask(self, question: str, history: list | None = None, month=None, scope=None, attachments=None, engine=None) -> dict:
        return self.agent.ask(question, history or [], month, scope or {}, attachments or [], engine)

    def api_agent_confirm(self, action_id: str, approve: bool = True) -> dict:
        return self.agent.confirm(action_id, approve)

    def api_agent_upload(self, files: list) -> dict:
        """Files dropped or pasted into the chat (browser side): kept in the data folder for the assistant to read."""
        import base64
        folder = data_dir() / "chat-files"
        folder.mkdir(parents=True, exist_ok=True)
        paths = []
        for f in files[:10]:
            name = re.sub(r"[^\w.\- ]+", "_", str(f.get("name") or "file"))[:80] or "file"
            path = folder / f"{uuid.uuid4().hex[:6]}-{name}"
            path.write_bytes(base64.b64decode(f["b64"]))
            paths.append(str(path))
        return {"paths": paths}

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
