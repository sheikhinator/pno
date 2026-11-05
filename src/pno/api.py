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


def template_key(name: str) -> str:
    """'Out of Stock & Stock Days YTDSEP 2026.xlsx' and next month's 'Out of Stock & Stock Days YTDOCT' → the same key."""
    n = str(name or "").lower()
    n = re.sub(r"\.(xlsx|xlsm|xls|csv|txt|tsv)$", "", n)
    n = re.sub(r"(ytd|mtd)(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", " ", n)
    n = re.sub(r"\b(ytd|mtd|jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sep(t(ember)?)?|oct(ober)?|nov(ember)?|dec(ember)?|week|wk)\b", " ", n)
    n = re.sub(r"[^a-z]+", " ", n)
    return " ".join(w for w in n.split() if len(w) > 1 and w not in ("and", "the", "of", "for", "to", "copy", "final", "new"))[:80]


GENERIC_KEYS = {"", "sheet", "data", "report", "export", "book", "table", "pivot", "summary", "raw", "output", "query", "result", "results",
                "detail", "details", "total", "sales", "file", "list", "page", "tab", "workbook", "main", "master"}


def specific_key(name: str) -> str:
    """A remembered-layout key only when the name says something about the report ('Sheet1', 'YTD', 'Data' don't)."""
    k = template_key(name)
    return "" if k in GENERIC_KEYS or len(k) < 4 else k


IMPORT_GUIDE = {
    "roster": "Employee master / Basic Sheet from the HR system: one row per person with employee number, name, store, section, designation.",
    "po_role": "Leaders with the date they started their current role (any layout with a 'since' date).",
    "po_rating": "Appraisal results: employee number or name and the rating (1-5), with the year if possible.",
    "attendance": "Biometric attendance for the month: daily in/out times per employee.",
    "sales": "BO 200-10-05 store performance, or any table of store sales with budget.",
    "productivity": "Section productivity: store productivity vs target.",
    "po_shrink": "Shrinkage and stock days by section.",
    "po_nps": "Customer NPS.",
    "po_da": "Disciplinary actions: a pivot by section and store, or a list of cases.",
    "po_turnover": "Leavers: employee, leaving date, exit type and reason.",
    "po_shift": "The shift roster: one row per person, one column per day (M / Mid / E / OFF).",
    "leave": "Leave register: employee number, from and to dates, leave type and status.",
}


def _quiet(fn, *a):
    try:
        fn(*a)
    except Exception:  # noqa: BLE001 - background housekeeping never stops the app
        traceback.print_exc()


class Api:
    def __init__(self, db: Database, host: Host | None = None):
        self.real_db = db
        self.db = db
        self.host = host or Host()
        self.demo = False
        self.sessions: dict[str, dict] = {}
        self._agent = None
        self._lock = threading.RLock()
        self._repair_stores(db)
        from . import office
        try:
            office.load_synonyms(db)
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    @staticmethod
    def _repair_stores(db: Database) -> None:
        """2.4: split H&B stores that older versions merged into the hypermarket of the same name."""
        if db.get_setting("repair_stores_v2"):
            return
        try:
            from .stores import repair_formats
            fixed = repair_formats(db)
            db.set_setting("repair_stores_v2", True)
            if fixed:
                db.notice = ("Store list fixed: H&B (Myli) stores were mixed into the hypermarket of the same name and some stores "
                             "were listed twice. Import the latest Sales report again so every department shows in every store.")
        except Exception:  # noqa: BLE001 - never block start-up
            traceback.print_exc()

    # ---------------------------------------------------------------- plumbing
    def dispatch(self, method: str, params: dict) -> Any:
        fn = getattr(self, f"api_{method}", None)
        if fn is None:
            return {"error": f"Unknown request: {method}"}
        params = dict(params or {})
        idem = params.pop("_idem", None)
        # idempotency key: a double click or a retried request does the change once and gets the same answer back
        if idem:
            seen = self.__dict__.setdefault("_idem_seen", {})
            if idem in seen:
                return seen[idem]
        try:
            out = fn(**params)
            if idem and not (isinstance(out, dict) and out.get("error")):
                seen[idem] = {"ok": True, "repeat": True} if len(str(out)) > 20000 else out   # never hold big answers in memory
                if len(seen) > 200:
                    for k in list(seen)[:100]:
                        seen.pop(k, None)
            return out
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

    def api_learn_for_person(self, key: str, hours: float = 3, lecture_min: int = 20, use_ai: bool = True) -> dict:
        return self.learning.for_person(key, hours, lecture_min, use_ai)

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
            "Never ask for age, gender, marital status or religion.", max_tokens=900, task="hiring")
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

    def api_hire_internal(self, vacancy_id: int, cross: bool = False) -> dict:
        return self.hiring.internal_search(int(vacancy_id), bool(cross))

    def api_hire_internal_add(self, vacancy_id: int, key: str) -> dict:
        return self.hiring.add_internal(int(vacancy_id), str(key))

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
        return {"version": __version__, "months": months, "month": default, "demo": self.demo, "tour_done": bool(self.db.get_setting("tour_done", False)), "full_mode": False,
                "options": analytics.options(mm, {}) if mm else {"cities": [], "formats": [], "stores": [], "depts": [], "sections": []},
                "counts": counts, "has_data": any(counts.values()), "hide_names": self._hide(),
                "theme": self.db.get_setting("theme", "auto"), "ai": self.agent.public_status(), "lock": self.api_lock_status(),
                "unsure_stores": self.db.val("SELECT COUNT(*) FROM store_aliases WHERE confirmed=0", (), 0),
                "notice": self._take_notice()}

    def _take_notice(self) -> str:
        n, self.real_db.notice = getattr(self.real_db, "notice", ""), ""
        return n

    def api_options(self, month: str | None = None, scope: dict | None = None) -> dict:
        return analytics.options(engine.model(self.db, month), scope or {})

    # ---------------------------------------------------------------- screens
    def api_person(self, emp: str, month=None) -> dict:
        return analytics.person(self.db, month, str(emp), self._hide())

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
    def api_pick_files(self, month: str | None = None) -> dict:
        paths = self.host.pick_files("reports")
        return self.api_import_analyze(paths=paths, month=month) if paths else {"cancelled": True}

    SUMMARY_KINDS = ("sales", "productivity", "po_shrink", "po_nps", "po_da")

    def ytd_baseline(self) -> str | None:
        """The month the year-to-date load runs to (Jan–that month), after which data comes month by month. Once known it is
        saved, so re-importing or replacing a file can never make the year-to-date slot disappear."""
        b = self.db.get_setting("ytd_baseline", None)
        if b:
            return b
        k = ",".join("?" * len(self.SUMMARY_KINDS))
        r = self.db.q1(f"""SELECT MAX(period_to) FROM imports WHERE active=1 AND period_type='ytd' AND substr(period_from,6,2)='01'
                           AND kind IN ({k})""", self.SUMMARY_KINDS)
        if not (r and r[0]):
            # data loaded before 4.2.2 (or month by month): the year to date runs to the latest month any summary report covers
            r = self.db.q1(f"SELECT MAX(period_to) FROM imports WHERE active=1 AND period_type IN ('ytd','mtd') AND kind IN ({k})", self.SUMMARY_KINDS)
        if r and r[0]:
            self.db.set_setting("ytd_baseline", r[0])
            return r[0]
        return None

    def api_ytd_baseline(self, month: str | None = None) -> dict:
        if month and not re.fullmatch(r"\d{4}-\d\d", month):
            raise ValueError("Pick a month.")
        self.db.set_setting("ytd_baseline", month or None)
        return {"baseline": self.ytd_baseline()}

    def api_import_calendar(self, year: int | None = None) -> dict:
        """The slots to load data into: one year-to-date slot (Jan → the baseline month) and then every month after it
        separately. Years without a year-to-date load show their months one by one."""
        from . import datahealth
        from .period import month_label as ml
        y = int(year or date.today().year)
        cur = date.today().strftime("%Y-%m")
        locked = datahealth.locked_months(self.db)
        base = self.ytd_baseline()
        suggested = None
        has_any = self.db.q1(f"SELECT 1 FROM imports WHERE active=1 AND kind IN ({','.join('?' * len(self.SUMMARY_KINDS))})", self.SUMMARY_KINDS)
        if not base and not has_any and y == date.today().year:
            t = date.today()
            suggested = f"{t.year}-{t.month - 1:02d}" if t.month > 1 else None        # nothing loaded yet: YTD to last month
        b = base if base and int(base[:4]) == y else suggested

        def slot(key, kind):
            cl = datahealth.checklist(self.db, key)
            per = [c for c in cl if not c.get("every") and not c.get("optional")]   # master, roles, ratings serve every period; shifts and leave are optional
            ok = sum(1 for c in per if c["status"] in ("ok", "derived"))
            from . import intake
            items = [{"kind": c["kind"], "name": c["name"], "status": c["status"], "label": c["label"], "detail": c["detail"], "every": c.get("every", False),
                      "optional": c.get("optional", False), "needs": intake.columns_needed(c["kind"])} for c in cl]
            running = key == cur                               # the month isn't over yet: nothing to load for it
            if kind == "ytd":
                return {"month": f"ytd:{key}", "end": key, "ytd": True, "label": f"Jan–{date(y, int(key[5:]), 1):%b} {y} · year to date",
                        "short": f"Jan–{date(y, int(key[5:]), 1):%b}", "ok": ok, "total": len(per), "future": key > cur, "running": False,
                        "locked": key in locked, "items": items, "set": bool(base)}
            m = int(key[5:])
            return {"month": key, "label": ml(key), "short": date(y, m, 1).strftime("%b"), "ok": ok, "total": len(per), "future": key >= cur,
                    "running": running, "locked": key in locked, "items": items}
        if b:
            months = [slot(b, "ytd")] + [slot(f"{y}-{m:02d}", "mtd") for m in range(int(b[5:]) + 1, 13)]
        else:
            months = [slot(f"{y}-{m:02d}", "mtd") for m in range(1, 13)]
        return {"year": y, "months": months, "today": cur, "guide": IMPORT_GUIDE, "baseline": base, "ytd_end_choices": [f"{y}-{m:02d}" for m in range(1, 13) if f"{y}-{m:02d}" < cur or f"{y}-{m:02d}" == b]}

    def api_import_analyze(self, paths: list | None = None, text: str | None = None, name: str = "Pasted data", month: str | None = None) -> dict:
        analyses = []
        errors = []
        for p in paths or []:
            try:
                analyses.append(importers.analyze_path(p))
            except Exception as e:
                errors.append({"file": Path(p).name, "error": str(e)})
        if text:
            analyses.append(importers.analyze_text(text, name))
        return self._new_session(analyses, errors, month)

    def _new_session(self, analyses: list, errors: list, month: str | None) -> dict:
        ytd = bool(month and str(month).startswith("ytd:"))
        if ytd:
            month = month[4:]
        elif not month and not self.db.q1(
                f"SELECT 1 FROM imports WHERE active=1 AND kind IN ({','.join('?' * len(self.SUMMARY_KINDS))})", self.SUMMARY_KINDS):
            # the very first load (quick Update data): it is the year-to-date load, up to the month the reports show
            ytd = True
            from .importers import describe
            shown = [r["period"].get("to") for a in analyses for r in describe(a, self.db)["results"]
                     if r["period"].get("sure") and r["period"]["type"] in ("ytd", "mtd") and r["kind"] in self.SUMMARY_KINDS]
            t = date.today()
            month = self.ytd_baseline() or max([m for m in shown if m] or [f"{t.year}-{t.month - 1:02d}" if t.month > 1 else f"{t.year - 1}-12"])
        token = uuid.uuid4().hex[:12]
        self.sessions[token] = {"analyses": analyses, "created": now(), "month": month}
        files = self._lined_up([importers.describe(a, self.db) for a in analyses], analyses, month, ytd)
        from .smart import checks
        cross = checks.cross(self.db, [r for a in analyses for r in a["results"]])       # people checked across every file
        for f in files:
            for r in f["results"]:
                have = {i["text"] for i in r.get("issues", [])}
                r.setdefault("issues", []).extend(c for c in cross if c.get("sheet") == r["sheet"] and c["text"] not in have)
        self.sessions[token]["ytd"] = ytd
        return {"token": token, "files": files, "errors": errors, "suggested_month": month or self._suggest_month(), "month": month,
                "slot": "ytd" if ytd else "mtd"}

    def api_import_upload(self, files: list, month: str | None = None) -> dict:
        """Files sent from a browser (development / tests): [{name, b64}]."""
        import base64
        analyses, errors = [], []
        for f in files:
            try:
                analyses.append(importers.analyze_bytes(base64.b64decode(f["b64"]), f["name"]))
            except Exception as e:
                errors.append({"file": f.get("name", "?"), "error": str(e)})
        return self._new_session(analyses, errors, month)

    def _suggest_month(self) -> str:
        m = engine.months_available(self.db)
        return m[-1] if m else date.today().strftime("%Y-%m")

    def _lined_up(self, files: list[dict], analyses: list[dict], month: str | None = None, ytd: bool = False) -> list[dict]:
        """Give sheets without a month of their own the month of the other sheets (or the month picked on the
        calendar), and remember it for saving."""
        from .period import line_up
        known = self.db.q1("""SELECT MAX(period_to) FROM imports WHERE active=1 AND period_type IN ('ytd','mtd')
                              AND kind NOT IN ('po_turnover','po_shift','attendance')""")
        line_up([r for f in files for r in f["results"]], month or (known[0] if known else None))
        if month:
            for f in files:
                for r in f["results"]:
                    p = r["period"]
                    if p["type"] in ("mtd", "ytd") and not p.get("sure") and not r.get("dated"):
                        p.update(to=month, **({"from": f"{month[:4]}-01"} if p["type"] == "ytd" else {"from": month}),
                                 why=f"The month you picked on the calendar ({month}).")
        tpls = self.db.get_setting("import_templates", {}) or {}
        for f in files:
            for r in f["results"]:
                ks, kf = specific_key(r["sheet"]), specific_key(f["file"])
                t = (tpls.get(ks) if ks else None) or (tpls.get(kf) if kf else None)
                if not t:
                    continue
                r["remembered"] = t
                if t.get("kind") and t["kind"] != r["kind"]:
                    # a remembered type never overrides a reader that is sure what the sheet is
                    if (r.get("confidence") or 0) >= 0.9 and not r.get("smart"):
                        r["remembered"] = {k: v for k, v in t.items() if k != "kind"}
                    else:
                        r["kind_hint"] = t["kind"]
                if t.get("columns") and r.get("smart"):
                    by_title = {c["header"]: c["index"] for c in r.get("columns", []) if c.get("header")}
                    fixed = {f: by_title[h] for f, h in t["columns"].items() if h in by_title}
                    a = next((x for x in analyses if x["file"] == f["file"]), None)
                    if a is not None and fixed and r["sheet"] not in (a.get("mapping_used") or {}):
                        try:
                            k = next(i for i, x in enumerate(a["results"]) if x.sheet == r["sheet"])
                            a["results"][k] = importers.reparse(a, a["results"][k], t.get("kind") or r["kind"], fixed)
                            fresh = importers.describe(a, self.db)["results"][k]
                            r.update({x: fresh[x] for x in ("kind", "label", "rows", "summary", "mapping", "issues", "preview", "confidence")})
                            r.pop("kind_hint", None)
                        except (ValueError, StopIteration):
                            pass
                pt = t.get("period_type")
                if pt and pt != r["period"]["type"]:
                    p = r["period"]
                    to = p.get("to") or (r.get("month") or self._suggest_month())
                    p.update(type=pt, why=f"Remembered from last time ({pt.upper() if pt != 'general' else 'general'}).",
                             **({"from": None, "to": None} if pt == "general" else {"to": to, "from": to if pt == "mtd" else (p.get("from") if p.get("from") and p["type"] == "ytd" else f"{to[:4]}-01")}))
        base = self.ytd_baseline()
        if month and not ytd and base and month > base:
            # a month after the year-to-date load: its summary reports are that month on its own
            for f in files:
                for r in f["results"]:
                    p = r["period"]
                    if p["type"] == "general" or r.get("dated") or r["kind"] in ("po_turnover", "po_shift", "attendance", "leave"):
                        continue
                    if p["type"] == "ytd" and p.get("sure") and p.get("to") == month and "remembered" not in (p.get("why") or "").lower():
                        continue                        # the file itself says year to date
                    p.update(type="mtd", to=month, **{"from": month}, why=f"{date(int(month[:4]), int(month[5:]), 1):%B %Y} on its own (after the year-to-date load).")
        if ytd and month:
            # the year-to-date slot: every summary report in this load counts from January (dated files keep their own dates)
            for f in files:
                for r in f["results"]:
                    p = r["period"]
                    if p["type"] == "general" or r.get("dated") or r["kind"] in ("po_turnover", "po_shift", "attendance", "leave"):
                        continue
                    own = p.get("to") if p.get("sure") else None
                    note = (f" The file itself shows up to {date(int(own[:4]), int(own[5:]), 1):%B}; it is filed with this load."
                            if own and own != month else "")
                    p.update(type="ytd", to=month, **{"from": f"{month[:4]}-01"}, sure=True,
                             why=f"Loaded as year to date (Jan–{date(int(month[:4]), int(month[5:]), 1):%b} {month[:4]}).{note}")
        for f, a in zip(files, analyses):
            a["period_hint"] = {(r["sheet"], r["kind"]): r["period"] for r in f["results"]}
            a["kind_hint"] = {r["sheet"]: r["kind_hint"] for r in f["results"] if r.get("kind_hint")}
        return files

    def _session_sheet(self, token: str, file: str, sheet: str):
        sess = self.sessions.get(token)
        if not sess:
            raise ValueError("This preview has expired. Please add the files again.")
        a = next((x for x in sess["analyses"] if x["file"] == file), None)
        if a is None:
            raise ValueError("File not found in this import.")
        i = next((k for k, r in enumerate(a["results"]) if r.sheet == sheet), None)
        if i is None:
            raise ValueError("Sheet not found in this import.")
        return a, i

    # ---------------------------------------------------------------- 4.3 guided intake (one report at a time)
    @staticmethod
    def _slot_fields(kind: str) -> list[dict]:
        """The fields that matter for this report, for the 'which column is which' matcher."""
        from . import smart
        k = smart.KINDS.get("sales_simple" if kind == "sales" else kind) or {}
        names = []
        for f in list(k.get("need", [])) + list(k.get("want", [])):
            for x in (f if isinstance(f, (tuple, list)) else (f,)):
                if x in smart.FIELDS and x not in names:
                    names.append(x)
        return [{"value": x, "label": smart.FIELDS[x]["label"]} for x in names] or smart.field_choices()

    def _sheet_columns(self, a: dict, sheet: str) -> list[dict]:
        from .smart import profile
        sh = (a.get("sheets") or {}).get(sheet)
        tabs = profile.find_tables(sh.rows) if sh is not None else []
        return [{"index": c.index, "header": c.header, "examples": c.examples[:3]} for c in tabs[0].columns if c.header or c.n] if tabs else []

    def _slot_result(self, token: str, kind: str, month: str | None) -> dict:
        from . import intake
        sess = self.sessions[token]
        hit = intake.pick(sess["analyses"], kind)
        label = {"sales": "store sales"}.get(kind, importers.KIND_LABEL.get(kind, kind))
        if not hit:
            seen = [f"'{r.sheet}' looks like {importers.KIND_LABEL.get(r.kind, r.kind)}" for a in sess["analyses"] for r in a["results"]]
            cols = []
            first = next(((a, r) for a in sess["analyses"] for r in a["results"]), None)
            if first:
                sess["pick"] = (first[0]["file"], first[1].sheet)
                cols = self._sheet_columns(first[0], first[1].sheet)
                sig = intake.layout_sig(kind, cols)
                mem = (self.db.get_setting("layout_maps", {}) or {}).get(sig) if sig else None
                if mem and not sess.get("fixed"):
                    by = {str(c.get("header")): c["index"] for c in cols if c.get("header")}
                    fixed = {fld: by[h] for fld, h in mem.items() if h in by}
                    if fixed:
                        sess["fixed"] = True
                        a0 = first[0]
                        k = a0["results"].index(first[1])
                        try:
                            a0["results"][k] = importers.reparse(a0, first[1], kind, fixed)
                            a0["results"][k].warn("Columns matched the way you matched them last time for this layout.")
                            return self._slot_result(token, kind, month)
                        except ValueError:
                            pass
            return {"token": token, "kind": kind, "status": "bad", "headline": f"This isn't {label} as it stands.",
                    "checks": ([{"level": "bad", "text": x} for x in seen] or [{"level": "bad", "text": "No table could be read."}]) +
                              ([{"level": "info", "text": "If it is, match the columns below (or ask the AI) and press Read again."}] if cols else []),
                    "columns": cols, "mapping": [], "fields": self._slot_fields(kind)}
        a, i, reread = hit
        sess["pick"] = (a["file"], a["results"][i].sheet)
        # only this sheet is saved
        for other in sess["analyses"]:
            other["results"] = [r for k, r in enumerate(other["results"]) if other is a and k == i]
        f = self._lined_up([importers.describe(a, self.db)], [a], month, bool(sess.get("ytd")))[0]
        r = f["results"][0]
        sig = intake.layout_sig(kind, r.get("columns") or [])
        mem = (self.db.get_setting("layout_maps", {}) or {}).get(sig) if sig else None
        if mem and not sess.get("fixed") and (reread or r.get("smart")):
            by = {str(c.get("header")): c["index"] for c in r.get("columns") or [] if c.get("header")}
            fixed = {fld: by[h] for fld, h in mem.items() if h in by}
            if fixed:
                a["results"][0] = importers.reparse(a, a["results"][0], kind, fixed)
                sess["fixed"] = True
                f = self._lined_up([importers.describe(a, self.db)], [a], month, bool(sess.get("ytd")))[0]
                r = f["results"][0]
                a["results"][0].warn("Columns matched the way you matched them last time for this layout.")
        res = a["results"][0]
        for note in sess.get("merged", []):
            res.warn(note)
        fills = intake.fill(self, kind, res.rows, r["period"])
        cols_now = [c for c in (r.get("columns") or []) if "index" in c] or self._sheet_columns(a, res.sheet)
        sec_col = any(re.search(r"section|category|sub ?dep", str(c.get("header") or ""), re.I) for c in cols_now)
        v = intake.verify(kind, res, r["period"], fills, reread, label, sec_col)
        return {"token": token, "kind": kind, "file": a["file"], "sheet": res.sheet, "period": r["period"], **v,
                "columns": [c for c in (r.get("columns") or []) if "index" in c] or self._sheet_columns(a, res.sheet), "mapping": r.get("mapping") or [], "fields": self._slot_fields(kind),
                "preview": r.get("preview") or [], "confidence": r.get("confidence"), "summary": r.get("summary")}

    def api_slot_read(self, kind: str, month: str | None = None, paths: list | None = None, files: list | None = None,
                      text: str | None = None) -> dict:
        """Read the file(s) or pasted cells given for one report on the checklist and verify them as that report."""
        import base64
        analyses, errors = [], []
        if paths is None and files is None and not text:
            paths = self.host.pick_files("reports")
            if not paths:
                return {"cancelled": True}
        for p in paths or []:
            try:
                analyses.append(importers.analyze_path(p))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{Path(p).name}: {e}")
        for f in files or []:
            try:
                analyses.append(importers.analyze_bytes(base64.b64decode(f["b64"]), f["name"]))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{f.get('name')}: {e}")
        if text:
            analyses.append(importers.analyze_text(text, "Pasted cells"))
        if not analyses:
            raise ValueError("; ".join(errors) or "Nothing to read.")
        s = self._new_session(analyses, [], month)
        return self._slot_result(s["token"], kind, month if not (month or "").startswith("ytd:") else month[4:])

    def api_slot_fix(self, token: str, kind: str, mapping: dict, month: str | None = None) -> dict:
        """The director matched the columns: read the sheet again that way and verify again."""
        sess = self.sessions.get(token)
        if not sess or not sess.get("pick"):
            raise ValueError("This preview has expired. Please add the file again.")
        file, sheet = sess["pick"]
        a, i = self._session_sheet(token, file, sheet)
        fixed = {f: int(j) for f, j in mapping.items() if str(j).lstrip("-").isdigit() and int(j) >= 0}
        cols = {c["index"]: c.get("header") for c in self._sheet_columns(a, sheet)}
        a["results"][i] = importers.reparse(a, a["results"][i], kind, fixed or None)
        a.setdefault("mapping_used", {})[sheet] = mapping
        sess["fixed"] = True
        from . import intake
        sig = intake.layout_sig(kind, [{"header": h} for h in cols.values()])
        if sig and fixed:                               # remembered for this layout: next time it is matched the same way
            maps = self.db.get_setting("layout_maps", {}) or {}
            maps[sig] = {f: cols[j] for f, j in fixed.items() if cols.get(j)}
            if len(maps) > 200:
                maps = dict(list(maps.items())[-200:])
            self.db.set_setting("layout_maps", maps)
        return self._slot_result(token, kind, month if not (month or "").startswith("ytd:") else month[4:])

    def api_slot_ai(self, token: str, kind: str, month: str | None = None) -> dict:
        """A second opinion on the column matches from the AI chosen for imports (offline AI works too)."""
        sess = self.sessions.get(token)
        if not sess or not sess.get("pick"):
            raise ValueError("This preview has expired. Please add the file again.")
        file, sheet = sess["pick"]
        try:
            out = self.api_import_ai(token, file, sheet)
            note = f"{out.get('engine') or 'AI'}: {out.get('why') or 'columns matched'}"
        except ValueError as e:
            # no AI set up (or its answer was unreadable): P&O's own engine reads the columns again from scratch
            from . import smart
            a, i = self._session_sheet(token, file, sheet)
            sh = (a.get("sheets") or {}).get(sheet)
            ms = smart.mapper.analyse(sh, file, kind="sales_simple" if kind == "sales" else kind) if sh is not None else []
            note = f"{e} P&O's own engine couldn't be sure either: match the columns below."
            if ms and ms[0].mapping:
                try:
                    a["results"][i] = importers.reparse(a, a["results"][i], kind, dict(ms[0].mapping))
                    note = f"{str(e).split('.')[0]}. P&O's own engine matched the columns instead."
                except ValueError:
                    pass
        r = self._slot_result(token, kind, month if not (month or "").startswith("ytd:") else month[4:])
        r["ai_note"] = note
        return r

    # ------------------------------------------------ 4.3.1 the AI fixes a copy of the data, the director reviews it
    def api_slot_repair(self, token: str, kind: str, month: str | None = None, use_ai: bool = True) -> dict:
        """Plan the clean-up (AI, else P&O's own engine), make it on a copy, read the copy as the report and show it for review.
        Nothing replaces the original until the director presses 'Use the fixed copy'."""
        from . import intake, smart
        from .smart import repair
        sess = self.sessions.get(token)
        if not sess or not sess.get("pick"):
            raise ValueError("This preview has expired. Please add the file again.")
        file, sheet = sess["pick"]
        a, i = self._session_sheet(token, file, sheet)
        sheets = a.get("sheets") or {}
        src = sheets.get(sess.get("orig_sheet") or sheet) or sheets.get(sheet)
        if src is None:
            raise ValueError("The sheet can't be found any more. Please add the file again.")
        sess.setdefault("orig_sheet", src.name)
        label = {"sales": "store sales"}.get(kind, importers.KIND_LABEL.get(kind, kind))
        skind = "sales_simple" if kind == "sales" else kind
        fields = [f["value"] for f in self._slot_fields(kind)]
        engine, why, ops, mapping = "P&O engine", "", [], {}
        if use_ai:
            try:
                out = self.agent.complete(repair.ai_prompt(src, kind, label, fields), max_tokens=900, task="import",
                                          system="You plan spreadsheet clean-ups for an HR analytics app. Reply with JSON only.")
                if out and out[0]:
                    ops, mapping, why = repair.parse_plan(out[0], len(src.rows[0]) if src.rows else 0)
                    engine = out[1] or "AI"
            except Exception as e:  # noqa: BLE001 - the engine plans instead
                why = f"The AI couldn't plan it ({str(e)[:80]}); P&O's own engine did."
        own = repair.engine_plan(src, kind)
        if not ops:
            ops, engine = own, ("P&O engine" if engine == "P&O engine" or not use_ai else f"{engine} + P&O engine")
            if use_ai and not why:
                why = "No AI is set up (Settings → AI); P&O's own engine planned the clean-up." if engine == "P&O engine" else why
        elif not any(o["op"] == "header" for o in ops) and any(o["op"] == "header" for o in own):
            ops = [o for o in own if o["op"] == "header"] + ops       # the engine is sure the titles span two rows
        fixed, log = repair.apply(src, ops)
        a.setdefault("sheets", {})[fixed.name] = fixed
        from .importers import _read_as_is
        from .importers.base import ParseResult
        res = _read_as_is(fixed, file)                       # an exact reader first (the cleaned copy often fits one)
        if res is not None and (res.kind != kind or (res.extra.get("smart") and mapping)):
            res = None
        if res is None:
            try:
                res = importers.reparse(a, ParseResult(kind="dataset", sheet=fixed.name), kind,
                                        {f: j for f, j in mapping.items() if f in smart.FIELDS} or None)
            except ValueError:
                res = None
        sess["repair"] = {"sheet": fixed.name, "res": res, "log": log}
        if res is None or not res.rows:
            v = {"status": "bad", "headline": f"Even after the clean-up this can't be read as {label}.", "checks": []}
        else:
            per = importers.guess_period(a, res)
            if sess.get("ytd") and month:
                mo = month[4:] if month.startswith("ytd:") else month
                per.update(type="ytd", to=mo, **{"from": f"{mo[:4]}-01"})
            sec_col = any(re.search(r"section|category|sub ?dep", str(h or ""), re.I) for h in (fixed.rows[0] if fixed.rows else []))
            v = intake.verify(kind, res, per, [], False, label, sec_col)
        return {"token": token, "engine": engine, "why": why, "steps": log, "rows_before": len(src.rows), "rows_after": len(fixed.rows),
                "before": repair.preview(src, 8), "after": repair.preview(fixed, 10), "check": v,
                "privacy": "The AI saw only the column titles and the shape of the cells, never the figures or names." if use_ai and engine != "P&O engine" else ""}

    def api_slot_repair_use(self, token: str, kind: str, month: str | None = None) -> dict:
        sess = self.sessions.get(token)
        if not sess or not sess.get("repair") or sess["repair"].get("res") is None:
            raise ValueError("There is no fixed copy to use. Run the fix again.")
        file, sheet = sess["pick"]
        a, i = self._session_sheet(token, file, sheet)
        rp = sess.pop("repair")
        a["results"][i] = rp["res"]
        for st in rp["log"]:
            rp["res"].warn(f"Fixed: {st['what']}")
        sess["pick"] = (file, rp["sheet"])
        sess["fixed"] = True
        return self._slot_result(token, kind, month if not (month or "").startswith("ytd:") else month[4:])

    def api_slot_repair_download(self, token: str) -> dict:
        """A copy of the fixed sheet as Excel, to keep or check."""
        import base64
        from .smart import repair
        sess = self.sessions.get(token)
        rp = (sess or {}).get("repair")
        name = rp["sheet"] if rp else ((sess or {}).get("pick") or ("", ""))[1]
        file = ((sess or {}).get("pick") or ("", ""))[0]
        sh = None
        for a in (sess or {}).get("analyses", []):
            sh = (a.get("sheets") or {}).get(name) or sh
        if sh is None:
            raise ValueError("Nothing to download yet.")
        data = repair.to_xlsx(sh)
        fname = f"{Path(file).stem or 'Data'} (fixed by P&O).xlsx"
        path = self.host.save_path(fname, "Excel (*.xlsx)")
        if path:
            Path(path).write_bytes(data)
            self.host.open_path(str(Path(path).parent))
            return {"path": str(path), "name": fname}
        return {"b64": base64.b64encode(data).decode(), "name": fname}

    def api_slot_extra(self, token: str, kind: str, month: str | None = None, paths: list | None = None, files: list | None = None,
                       text: str | None = None) -> dict:
        """Ask once: a second file (or pasted cells) for just the part that is missing, e.g. the budget."""
        import base64
        from . import intake
        sess = self.sessions.get(token)
        if not sess or not sess.get("pick"):
            raise ValueError("This preview has expired. Please add the file again.")
        if paths is None and files is None and not text:
            paths = self.host.pick_files("reports")
            if not paths:
                return {"cancelled": True}
        extra = [importers.analyze_path(p) for p in paths or []] + [importers.analyze_bytes(base64.b64decode(f["b64"]), f["name"]) for f in files or []]
        if text:
            extra.append(importers.analyze_text(text, "Pasted cells"))
        hit = intake.pick(extra, kind)
        if not hit:
            raise ValueError("The second file couldn't be read as the same report.")
        file, sheet = sess["pick"]
        a, i = self._session_sheet(token, file, sheet)
        note = intake.merge(kind, a["results"][i].rows, hit[0]["results"][hit[1]].rows)
        sess.setdefault("merged", []).append(note)
        return self._slot_result(token, kind, month if not (month or "").startswith("ytd:") else month[4:])

    def api_slot_save(self, token: str, kind: str, month: str | None = None, replace: list | None = None) -> dict:
        """Save the checked report. `replace`: the imports it takes the place of (they can be restored from history)."""
        sess = self.sessions.get(token)
        if not sess:
            raise ValueError("This preview has expired. Please add the file again.")
        mo = month[4:] if (month or "").startswith("ytd:") else month
        opts = {}
        for a in sess["analyses"]:
            for r in a["results"]:
                opts.setdefault(a["file"], {})[r.sheet] = {"kind": kind, "replace": bool(replace), **({"month": mo} if mo else {})}
        out = self.api_import_commit(token, opts)
        saved = [r for f in out.get("done", []) for r in f.get("results", []) if r.get("status") == "ok"]
        if saved and replace:
            for iid in replace:
                try:
                    importers.undo(self.db, int(iid))
                except Exception:  # noqa: BLE001 - already removed
                    pass
        return out

    def api_slot_info(self, kind: str, month: str) -> dict:
        """What is loaded for one report of one period (the checklist row the director clicked)."""
        from . import datahealth
        from .period import label as period_label
        mo = month[4:] if month.startswith("ytd:") else month
        item = next((c for c in datahealth.checklist(self.db, mo) if c["kind"] == kind), None)
        rows = []
        for r in self.db.q("SELECT * FROM imports WHERE active=1 AND kind=? ORDER BY id DESC", (kind,)):
            r = dict(r)
            f, t = r.get("period_from") or r.get("month"), r.get("period_to") or r.get("month")
            if r.get("period_type") not in (None, "", "general") and not (f and t and (f <= mo <= t if kind in ("po_turnover", "po_shift") else t == mo)):
                continue
            rows.append({"id": r["id"], "file": r["file_name"], "sheet": r.get("sheet_name"), "at": (r["created_at"] or "")[:16].replace("T", " "),
                         "rows": r.get("rows"), "summary": (r.get("summary") or "").rsplit(" [", 1)[0],
                         "period": period_label(r.get("period_type"), r.get("period_from"), r.get("period_to")) if r.get("period_type") else "",
                         "warnings": json.loads(r.get("warnings") or "[]")})
        return {"kind": kind, "label": importers.KIND_LABEL.get(kind, kind), "status": (item or {}).get("status"), "imports": rows,
                "guide": IMPORT_GUIDE.get(kind, "")}

    def api_import_remap(self, token: str, file: str, sheet: str, kind: str, mapping: dict | None = None) -> dict:
        """Read a sheet again as the type the user chose, with the column matches the user set."""
        a, i = self._session_sheet(token, file, sheet)
        new = importers.reparse(a, a["results"][i], kind, mapping or None)
        a["results"][i] = new
        a.setdefault("mapping_used", {})[sheet] = mapping or {}
        sess = self.sessions.get(token) or {}
        return {"file": self._lined_up([importers.describe(a, self.db)], [a], sess.get("month"))[0]}

    def api_import_ai(self, token: str, file: str, sheet: str) -> dict:
        """Ask the AI what a sheet is and which column is which. Only column titles and the kind of values are sent,
        never names, numbers or other cell contents."""
        from . import smart
        from .smart import profile
        a, i = self._session_sheet(token, file, sheet)
        sh = (a.get("sheets") or {}).get(sheet)
        tables = profile.find_tables(sh.rows) if sh else []
        if not tables:
            raise ValueError("No table found in this sheet.")
        t = tables[0]
        cols = []
        for c in t.columns:
            if not c.n:
                continue
            kinds = ", ".join(f"{k} {round(100 * v)}%" for k, v in sorted(c.share.items(), key=lambda kv: -kv[1]) if v >= 0.3) or "text"
            cols.append(f"{c.index}: '{c.header or '(no title)'}' — values look like: {kinds}; {c.distinct} distinct")
        kinds = ", ".join(f"{k} ({v['label']})" for k, v in smart.KINDS.items())
        fields = ", ".join(f"{k} ({v['label']})" for k, v in smart.FIELDS.items())
        prompt = (f"A sheet named '{sheet}' in file '{file}' (title: '{t.title[:120]}') has these columns:\n" + "\n".join(cols) +
                  f"\n\nReport types: {kinds}, dataset (anything else).\nFields: {fields}.\n\nReply with JSON only: "
                  '{"kind": "<type>", "mapping": {"<field>": <column number>, ...}, "why": "<one sentence>"}')
        out = self.agent.complete(prompt, system="You map HR spreadsheet columns to a fixed schema. Reply with JSON only.", max_tokens=500, task="import")
        if not out or not out[0]:
            raise ValueError("No AI is set up. Add a key in Settings → AI, or match the columns yourself.")
        m = re.search(r"\{.*\}", out[0], re.S)
        if not m:
            raise ValueError("The AI's answer could not be read. Match the columns yourself.")
        ans = json.loads(m.group(0))
        kind = ans.get("kind") or "dataset"
        kind = "sales" if kind == "sales_simple" else kind
        mapping = {f: int(j) for f, j in (ans.get("mapping") or {}).items() if f in smart.FIELDS and str(j).lstrip("-").isdigit()}
        r = self.api_import_remap(token, file, sheet, kind, mapping if kind != "dataset" else None)
        return {**r, "why": ans.get("why", ""), "engine": out[1]}

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
        self._remember_templates(sess["analyses"], out)
        if sess.get("ytd"):
            # the one-off year-to-date load: next month's files of the same name are monthly, so don't remember 'YTD' for them
            tpls = self.db.get_setting("import_templates", {}) or {}
            for a in sess["analyses"]:
                for r in a["results"]:
                    for k in (template_key(r.sheet), template_key(a["file"])):
                        if k in tpls:
                            tpls[k].pop("period_type", None)
            self.db.set_setting("import_templates", tpls)
            if not self.db.get_setting("ytd_baseline", None) and sess.get("month"):
                self.db.set_setting("ytd_baseline", sess["month"])
        new_sets = [r["import_id"] for f in out for r in f.get("results", []) if r.get("kind") == "dataset" and r.get("status") == "ok"]
        if new_sets:
            threading.Thread(target=self._ai_label_datasets, args=(new_sets,), daemon=True).start()
        return {"done": out, "months": analytics.month_list(self.db)}

    def _remember_templates(self, analyses: list[dict], out: list[dict]) -> None:
        """Remember what each sheet was (report type and period type) so next month's file is set up the same way."""
        tpls = self.db.get_setting("import_templates", {}) or {}
        for f in out:
            for r in f.get("results", []):
                if r.get("status") != "ok":
                    continue
                row = self.db.q1("SELECT kind, period_type FROM imports WHERE id=?", (r["import_id"],))
                if row and specific_key(r["sheet"]):
                    t = {"kind": row["kind"], "period_type": row["period_type"], "sheet": r["sheet"], "at": now()[:10]}
                    a = next((x for x in analyses if x["file"] == f.get("file")), None)
                    res = next((x for x in (a or {}).get("results", []) if x.sheet == r["sheet"]), None)
                    if res is not None and res.extra.get("smart") and res.extra.get("mapping"):
                        t["columns"] = {m["field"]: m["header"] for m in res.extra["mapping"] if m.get("header")}
                    tpls[specific_key(r["sheet"])] = t
        if len(tpls) > 300:
            tpls = dict(sorted(tpls.items(), key=lambda kv: kv[1].get("at", ""))[-300:])
        self.db.set_setting("import_templates", tpls)

    def api_import_templates(self, forget: str | None = None) -> dict:
        tpls = self.db.get_setting("import_templates", {}) or {}
        if forget and forget in tpls:
            tpls.pop(forget)
            self.db.set_setting("import_templates", tpls)
        from .importers import KIND_LABEL
        return {"templates": [{"key": k, **v, "example": v.get("sheet"), "used": v.get("at"), "kind_label": KIND_LABEL.get(v.get("kind"), v.get("kind"))}
                              for k, v in sorted(tpls.items())]}

    def api_imports(self) -> dict:
        from .period import label as period_label
        rows = [dict(r) for r in self.db.q("SELECT * FROM imports ORDER BY id DESC LIMIT 500")]
        for r in rows:
            r["warnings"] = json.loads(r["warnings"] or "[]")
            r["summary"] = (r["summary"] or "").rsplit(" [", 1)[0]
            r["period_label"] = period_label(r.get("period_type"), r.get("period_from"), r.get("period_to")) if r.get("period_type") else ""
            r["kind_label"] = importers.KIND_LABEL.get(r["kind"], r["kind"])
        return {"rows": rows}

    def api_import_undo(self, import_id: int) -> dict:
        return importers.undo(self.db, int(import_id))

    # ------------------------------------------------ 6.0 the master sheet: the one upload
    def api_master_read(self, period_type: str = "ytd", month: str = "", paths: list | None = None, files: list | None = None,
                        text: str | None = None) -> dict:
        """Read the master sheet (file or pasted cells), check it, and show what will be saved for the period."""
        import base64
        from . import master
        from .reader import from_text, open_bytes, open_file
        if paths is None and files is None and not text:
            paths = self.host.pick_files("reports")
            if not paths:
                return {"cancelled": True}
        wbs = []
        for p in paths or []:
            wbs.append(open_file(p))
        for f in files or []:
            wbs.append(open_bytes(base64.b64decode(f["b64"]), f["name"]))
        if text:
            wbs.append(from_text(text, "Pasted cells"))
        best = None
        for wb in wbs:
            for sh in wb.sheets:
                if master.score(sh)[0] > 0:
                    r = master.parse(sh)
                    if best is None or len(r["rows"]) > len(best[2]["rows"]):
                        best = (wb, sh, r)
        if best is None:
            seen = [f"{wb.name} · {sh.name}" for wb in wbs for sh in wb.sheets]
            return {"status": "bad", "headline": "This isn't the master sheet.",
                    "checks": [{"level": "bad", "text": "No sheet has the master sheet's columns (Employee No, Designation and the measures)."}]
                    + [{"level": "info", "text": f"Looked at: {x}"} for x in seen[:6]], "token": None}
        wb, sh, r = best
        ptype = "mtd" if period_type == "mtd" else "ytd"
        if not re.match(r"^20\d\d-\d\d$", month or ""):
            t = date.today()
            month = f"{t.year}-{t.month - 1:02d}" if t.month > 1 else f"{t.year - 1}-12"
        pfrom = f"{month[:4]}-01" if ptype == "ytd" else month
        token = uuid.uuid4().hex[:12]
        self.sessions[token] = {"master": r, "file": wb.name, "hash": wb.file_hash, "ptype": ptype, "pfrom": pfrom, "pto": month, "created": now()}
        cov = master.coverage(r["rows"])
        checks = [{"level": "good", "text": f"{len(r['rows'])} leaders read from '{sh.name}'."}]
        stores = sorted({x["store"] for x in r["rows"] if x["store"]})
        checks.append({"level": "good", "text": f"{len(stores)} stores: {', '.join(stores[:12])}{'…' if len(stores) > 12 else ''}."})
        lv = {}
        for x in r["rows"]:
            lv[x["designation"] or "?"] = lv.get(x["designation"] or "?", 0) + 1
        checks.append({"level": "good", "text": "Roles: " + ", ".join(f"{n} {k}" for k, n in sorted(lv.items(), key=lambda kv: -kv[1])) + "."})
        for m in r["missing_columns"]:
            checks.append({"level": "bad" if m in ("Employee No", "Designation", "BU") else "warn", "text": f"Column '{m}' is not in the sheet."})
        for m in cov["measures"]:
            if m["pct"] < 100:
                checks.append({"level": "warn" if m["pct"] else "info",
                               "text": f"{m['label']}: filled for {m['filled']} of {m['of']} leaders" + (" (not filled yet: shows '—' and doesn't count in scores)" if m["pct"] < 100 else "") + "."})
        for x in r["scaled"]:
            checks.append({"level": "info", "text": f"{x}: Excel stored these as fractions (0.152); read as percentages (15.2%)."})
        for w in r["warnings"]:
            checks.append({"level": "warn", "text": w})
        same = self.db.q1("SELECT file_name, created_at FROM imports WHERE active=1 AND kind='master' AND period_type=? AND period_to=?", (ptype, month))
        if same:
            checks.append({"level": "info", "text": f"Saving replaces the sheet already loaded for this period ({same['file_name']}, {same['created_at'][:10]}); it can be restored from the list."})
        bad = any(c["level"] == "bad" for c in checks)
        warn = any(c["level"] == "warn" for c in checks)
        from . import master as M
        lab = M.label(ptype, pfrom, month)
        head = (f"Can't save: the sheet is missing columns P&O needs." if bad else
                f"Ready to save as {lab}. Some figures aren't filled yet; they show as '—' until next time." if warn else f"Ready to save as {lab}: everything is filled.")
        prev = [{k: x.get(k) for k in ("emp", "name", "store", "section", "designation", *master.MEASURES)} for x in r["rows"][:8]]
        return {"token": token, "status": "bad" if bad else "warn" if warn else "good", "headline": head, "checks": checks, "label": lab,
                "coverage": cov, "preview": prev, "file": wb.name, "sheet": "" if sh.name == wb.name else sh.name}

    def api_master_save(self, token: str) -> dict:
        from . import master
        sess = self.sessions.get(token)
        if not sess or "master" not in sess:
            raise ValueError("This preview has expired. Please add the sheet again.")
        r = sess["master"]
        if not r["rows"]:
            raise ValueError("Nothing to save.")
        iid = master.save(self.db, r["rows"], sess["file"], sess["hash"], sess["ptype"], sess["pfrom"], sess["pto"])
        self.db.set_setting("master_view", None)                  # show the newest
        self.db.log("import", f"master sheet {sess['file']} {sess['ptype']} {sess['pto']}")
        self.sessions.pop(token, None)
        self._po_cache = None
        self.__dict__.pop("_rv_cache", None)
        return {"ok": True, "import_id": iid, "label": master.label(sess["ptype"], sess["pfrom"], sess["pto"])}

    def api_master_list(self) -> dict:
        """Every master sheet loaded, newest first, with how complete it is."""
        from . import master
        cur = master.chosen(self.db)
        out = []
        for r in self.db.q("SELECT * FROM imports WHERE kind='master' ORDER BY period_to DESC, period_type, id DESC"):
            r = dict(r)
            cov = master.coverage(master.rows_for(self.db, r)) if r["active"] else None
            out.append({"id": r["id"], "label": master.label(r["period_type"], r["period_from"], r["period_to"]), "type": r["period_type"], "to": r["period_to"],
                        "file": r["file_name"], "at": (r["created_at"] or "")[:16].replace("T", " "), "rows": r["rows"], "active": bool(r["active"]),
                        "filled": cov["filled_pct"] if cov else None, "on_screen": bool(cur and cur["id"] == r["id"])})
        return {"rows": out}

    def api_master_health(self, import_id: int | None = None) -> dict:
        """What is filled and what is still missing in the master sheet on screen (or the one given)."""
        from . import master
        p = None
        if import_id:
            p = next((x for x in master.periods(self.db) if x["id"] == int(import_id)), None)
        p = p or master.chosen(self.db)
        if not p:
            return {"empty": True}
        rows = master.rows_for(self.db, p)
        return {"empty": False, "id": p["id"], "label": master.label(p["period_type"], p["period_from"], p["period_to"]), "file": p["file_name"],
                "periods": [{"id": x["id"], "label": master.label(x["period_type"], x["period_from"], x["period_to"])} for x in master.periods(self.db)],
                **master.coverage(rows)}

    def api_import_delete(self, import_id: int) -> dict:
        """Delete an uploaded file's data for good (Undo only switches it off)."""
        out = importers.delete(self.db, int(import_id))
        self._po_cache = None
        self.__dict__.pop("_rv_cache", None)
        return out

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
    # ---------------------------------------------------------------- actions, manpower, today
    # ---------------------------------------------------------------- 2.2 policies, notes, goals, managers
    # ---------------------------------------------------------------- 2.4 training needs and workforce forecast
    # ---------------------------------------------------------------- 2.7 People Brain and corrections
    def _brain(self):
        from .brain import Brain
        key = (str(self.db.path), self.db.version, self._hide())
        c = getattr(self, "_brain_cache", None)
        if c and c[0] == key:
            return c[1]
        b = Brain(self)
        self._brain_cache = (key, b)
        return b

    def api_brain_search(self, q: str = "", store: str = "", level: int | None = None, include_left: bool = False) -> dict:
        b = self._brain()
        rows = b.find(q, 400)
        if store:
            rows = [r for r in rows if r["store"] == store]
        if level is not None and str(level) != "":
            rows = [r for r in rows if (r["level"] or 0) >= int(level)]
        if not include_left:
            rows = [r for r in rows if not r["left"]]
        stores = sorted({(p["facts"].get("store") or {}).get("value") for p in b.people.values() if (p["facts"].get("store") or {}).get("value")})
        return {"rows": rows[:300], "total": len(rows), "stores": stores, "people": len(b.people)}

    def api_brain_person(self, emp: str) -> dict:
        page = self._brain().person_page(emp)
        if self._hide():
            page["name"] = f"Employee {page['emp']}"
        return page

    def api_brain_store(self, store: str) -> dict:
        return self._brain().store_page(store)

    def api_brain_graph(self, store: str = "", leaders_only: bool = True) -> dict:
        return self._brain().graph(store, bool(leaders_only))

    def api_correction_add(self, emp: str, field: str, value: Any, note: str = "", cycle: int | None = None, source: str = "manual") -> dict:
        from . import brain
        b = self._brain()
        p = b.people.get(str(emp))
        old = ((p or {}).get("facts", {}).get(field) or {}).get("value") if p else None
        brain.add_correction(self.db, emp, field, value, (p or {}).get("name", ""), note, source, int(cycle) if cycle else None, old)
        return {"ok": True, "person": self.api_brain_person(emp) if p else None}

    def api_correction_undo(self, correction_id: int) -> dict:
        from . import brain
        brain.undo_correction(self.db, int(correction_id))
        return {"ok": True}

    def api_corrections(self) -> dict:
        from . import brain
        return {"rows": brain.corrections(self.db), "fields": brain.FIELDS}

    def api_profile_export(self, emp: str, fmt: str = "pdf", include_notes: bool = False, save_as: str | None = None, open_after: bool = True) -> dict:
        from . import exports
        from .brain import profile_report
        page = self.api_brain_person(emp)
        rep = profile_report(page, bool(include_notes))
        path = save_as or self.host.save_path(exports.file_name(rep, fmt), fmt)
        if not path:
            return {"cancelled": True}
        exports.render(rep, fmt, path)
        self.db.log("export", f"profile {emp} {fmt}")
        if open_after:
            self.host.open_path(path)
        return {"path": path}

    # ---------------------------------------------------------------- 2.8 employee relations
    # ---------------------------------------------------------------- 4.0 review
    def api_review(self, store: str | None = None, dept: str | None = None, section: str | None = None, role: str | None = None) -> dict:
        from . import review
        key = ("rv", self.db.version, json.dumps(self.db.get_setting("master_view", None), sort_keys=True), store, dept, section, role)
        c = self.__dict__.setdefault("_rv_cache", {})
        if key not in c:
            if len(c) > 40:
                c.clear()
            c[key] = review.Review(self).build(store or None, dept or None, section or None, role or None)
        out = dict(c[key])
        ins = self._po()
        out["has_data"] = not ins.empty
        out["period"] = self._po_period(ins)          # the period bar: latest, one month or year to date
        return out

    def api_review_export(self, fmt: str = "pdf", store: str | None = None, dept: str | None = None, section: str | None = None,
                          role: str | None = None, ai: bool = True, save_as: str | None = None, open_after: bool = True) -> dict:
        """The Review as a PowerPoint deck, PDF report, Word document or Excel workbook."""
        from . import review_export
        fmt = fmt if fmt in review_export.RENDER else "pdf"
        d = review_export.build(self, store or None, dept or None, section or None, role or None, ai=bool(ai))
        nice = re.sub(r"[^\w\- ]+", "", f"P&O Review {d['view'].replace(' · ', ' ')} {date.today():%Y-%m-%d}").strip()
        path = save_as or self.host.save_path(f"{nice}.{fmt}", fmt)
        if not path:
            return {"cancelled": True}
        review_export.RENDER[fmt](d, path)
        if open_after:
            self.host.open_path(path)
        return {"ok": True, "path": path, "ai": bool(d["ai"]), "ai_engine": d["ai_engine"]}

    def api_review_person(self, emp: str = "", key: str = "") -> dict:
        from . import review
        return review.person(self, emp, key)

    def api_review_person_criteria(self, key: str = "", emp: str = "", rows: list | None = None, reset: bool = False) -> dict:
        """Save criteria for one person only (their own weights and green / amber lines), or put them back on the standard ones."""
        from . import review
        if not key and emp:
            p = review.person(self, emp, "")
            key = p["row"]["key"]
        allc = self.db.get_setting("person_criteria", {}) or {}
        if reset or not rows:
            allc.pop(str(key), None)
        else:
            own = {}
            for r in rows:
                k = r.get("key")
                if k not in review.CRITERIA or k == "score":
                    continue
                w = max(0.0, min(100.0, float(r.get("weight") or 0)))
                g, a = r.get("green"), r.get("amber")
                e = {"show": bool(r.get("show", True)) and w > 0, "weight": w}
                if g not in (None, "") and a not in (None, ""):
                    g, a = float(g), float(a)
                    up = review.CRITERIA[k]["better"] == "up"
                    if (up and a > g) or (not up and a < g):
                        raise ValueError(f"{review.CRITERIA[k]['label']}: amber must be {'below' if up else 'above'} green.")
                    e.update(green=g, amber=a)
                own[k] = e
            if sum(1 for e in own.values() if e["show"]) < 3:
                raise ValueError("Keep at least three criteria switched on.")
            allc[str(key)] = own
        self.db.set_setting("person_criteria", allc)
        self.db.version += 1
        self.__dict__.pop("_rv_cache", None)
        return {"ok": True, "custom": str(key) in allc, "people": len(allc)}

    def api_review_person_export(self, key: str = "", emp: str = "", fmt: str = "xlsx", rows: list | None = None, save_as=None,
                                 open_after: bool = True) -> dict:
        """One person's scores as a table: every criterion's result, its lines, the points out of 10, the weight and what it adds to the score.
        With `rows` (the person sheet's what-if), the scores with those criteria, next to the current ones."""
        from . import exports, review
        if rows:
            return self._what_if_export(key, emp, rows, fmt, save_as, open_after)
        p = review.person(self, emp, key)
        r, C = p["row"], p["criteria"]
        cells = {c["key"]: c for c in r["cells"]}
        parts = {x["key"]: x for x in r.get("parts", [])}
        rows = []
        for k, c in cells.items():
            if k == "score":
                continue
            cr = C.get(k, {})
            pt = parts.get(k)
            rows.append([cr.get("label") or review.CRITERIA[k]["label"], "" if c.get("value") is None else f"{c['value']:g}",
                         "" if cr.get("green") is None else f"{cr['green']:g}", "" if cr.get("amber") is None else f"{cr['amber']:g}",
                         {"good": "On or above benchmark", "warn": "Close", "bad": "Below benchmark"}.get(c.get("status"), "Not scored"),
                         "" if not pt else f"{pt['points']:.1f}", "" if not pt else f"{pt['weight']:g}", "" if not pt else f"{pt['share']}%",
                         "" if not pt else f"{pt['points'] * pt['share'] / 100:.2f}",
                         "" if p.get("peer_median", {}).get(k) is None else f"{p['peer_median'][k]:g}"])
        sc = cells.get("score", {}).get("value")
        rows.append(["Score (out of 10)", "" if sc is None else f"{sc:g}", "", "", "", "", "", "100%", "" if sc is None else f"{sc:g}", ""])
        title = f"Scores · {r['name']}"
        scope = " · ".join(x for x in (r.get("role"), r.get("store"), r.get("area")) if x)
        rep = exports.table_report(title, ["Criterion", "Result", "Green from", "Amber from", "Status", "Points /10", "Weight", "Share of score",
                                           "Adds to score", "Peer median"], rows, scope)
        return self._save_report(rep, fmt, save_as, open_after, f"scores {r['name']}")

    def _what_if_export(self, key: str, emp: str, rows: list, fmt: str, save_as, open_after: bool) -> dict:
        from . import exports, review
        p = review.person(self, emp, key)
        r = p["row"]
        rv = review.Review(self)
        cfg = {k: dict(v) for k, v in (rv.person_setup(r["key"]) or (rv.cfg, rv.t))[0].items()}
        t = {k: dict(v) for k, v in (rv.person_setup(r["key"]) or (rv.cfg, rv.t))[1].items()}
        for x in rows:
            k = x.get("key")
            if k in cfg:
                cfg[k].update(show=bool(x.get("show", True)), weight=float(x.get("weight") or 0))
                if x.get("green") not in (None, "") and x.get("amber") not in (None, ""):
                    t[k] = {"green": float(x["green"]), "amber": float(x["amber"])}
        now = next((c["value"] for c in r["cells"] if c["key"] == "score"), None)
        new, parts = review.Review._compute(r["cells"], cfg, t)
        pp = {x["key"]: x for x in parts}
        peers = [s for s in p.get("peer_scores", []) if s is not None]
        rank = lambda v: None if v is None else 1 + sum(1 for s in peers if s > v)  # noqa: E731
        out = []
        for c in r["cells"]:
            k = c["key"]
            if k == "score" or c["value"] is None:
                continue
            q = review.points(k, c["value"], t)
            x = pp.get(k)
            out.append([review.CRITERIA[k]["label"], f"{c['value']:g}", "Yes" if x else "No", f"{cfg[k]['weight']:g}",
                        "" if t[k]["green"] is None else f"{t[k]['green']:g}", "" if t[k]["amber"] is None else f"{t[k]['amber']:g}",
                        "" if q is None else f"{q:.1f}", f"{x['share']}%" if x else "", f"{x['points'] * x['share'] / 100:.2f}" if x else ""])
        out.append(["Score (out of 10)", "", "", "", "", "", "", "", "" if new is None else f"{new:g}"])
        note = (f"Score now {now if now is not None else '—'} → what if {new if new is not None else '—'}; place among {len(peers) + 1} "
                f"{r.get('role') or 'peers'}: #{rank(now) or '—'} → #{rank(new) or '—'}")
        rep = exports.table_report(f"What if · {r['name']}", ["Criterion", "Result", "Counts", "Weight", "Green from", "Amber from", "Points /10",
                                                               "Share of score", "Adds to score"], out, note)
        return self._save_report(rep, fmt, save_as, open_after, f"what-if {r['name']}")

    def api_review_scores_export(self, store: str | None = None, dept: str | None = None, section: str | None = None, role: str | None = None,
                                 fmt: str = "xlsx", save_as=None, open_after: bool = True) -> dict:
        """Everyone in the current selection: the points out of 10 on every criterion and the score, as a table."""
        from . import exports, review
        d = self.api_review(store, dept, section, role)
        keys = [k for k in d["people_keys"] if k != "score"] if d.get("people_keys") else [k for k in review.CRITERIA if k != "score"]
        rows = []
        for p in d["people"]:
            parts = {x["key"]: x for x in p.get("parts", [])}
            sc = next((c["value"] for c in p["cells"] if c["key"] == "score"), None)
            rows.append([p["name"] + (" (custom criteria)" if p.get("custom") else ""), p.get("role") or "", p.get("store") or "", "" if sc is None else f"{sc:g}"] +
                        ["" if k not in parts else f"{parts[k]['points']:.1f}" for k in keys])
        rows.sort(key=lambda r: -(float(r[3]) if r[3] else -1))
        rep = exports.table_report(f"Scores · {d.get('label', 'Review')}", ["Person", "Role", "Store", "Score /10"] + [review.CRITERIA[k]["label"] + " (pts /10)" for k in keys],
                                   rows, d.get("label", ""))
        return self._save_report(rep, fmt, save_as, open_after, "scores")

    def api_review_preview(self, rows: list, score: dict | None = None) -> dict:
        """Settings → Criteria, before saving: the scores and the ranking with these weights, next to the current ones."""
        from . import review
        cfg, t = review.config(self.db), review.targets(self.db)
        new_cfg, new_t = {k: dict(v) for k, v in cfg.items()}, {k: dict(v) for k, v in t.items()}
        for r in rows or []:
            k = r.get("key")
            if k in new_cfg:
                new_cfg[k].update(show=bool(r.get("show", True)), weight=max(0.0, min(100.0, float(r.get("weight") or 0))))
                try:
                    g, a = float(r.get("green")), float(r.get("amber"))
                    new_t[k].update(green=g, amber=a)
                    new_cfg[k].update(green=g, amber=a)
                except (TypeError, ValueError):
                    pass
        if score:
            try:
                new_t["score"] = {"green": float(score["green"]), "amber": float(score["amber"])}
            except (KeyError, TypeError, ValueError):
                pass
        old = self.api_review()["people"]
        new = review.Review(self, new_cfg, new_t).build(None, None, None, None)["people"]
        sc = lambda p: next((c["value"] for c in p["cells"] if c["key"] == "score"), None)  # noqa: E731
        st = lambda p: next((c["status"] for c in p["cells"] if c["key"] == "score"), None)  # noqa: E731
        rank = lambda ps: {p["key"]: i + 1 for i, p in enumerate(sorted([p for p in ps if sc(p) is not None], key=lambda p: -sc(p)))}  # noqa: E731
        ro, rn = rank(old), rank(new)
        before = {p["key"]: sc(p) for p in old}
        out = sorted([p for p in new if sc(p) is not None], key=lambda p: -sc(p))
        total = sum(v["weight"] for v in new_cfg.values() if v["show"])
        return {"people": [{"name": p["name"], "role": p.get("role"), "store": p.get("store"), "old": before.get(p["key"]), "new": sc(p), "status": st(p),
                            "old_rank": ro.get(p["key"]), "new_rank": rn.get(p["key"])} for p in out],
                "shares": {k: (round(100 * v["weight"] / total) if total and v["show"] else 0) for k, v in new_cfg.items()}, "total": total}

    def api_review_criteria(self, rows: list | None = None, reset: bool = False, score: dict | None = None) -> dict:
        """Settings → Criteria: for each criterion whether it shows on the Review, its weight in the score, and its green / amber lines."""
        from . import review
        if reset:
            self.db.set_setting("review_criteria", {})
            self.db.set_setting("review_targets", {})
        elif rows:
            crit = self.db.get_setting("review_criteria", {}) or {}
            tg = self.db.get_setting("review_targets", {}) or {}
            for r in rows:
                k = r.get("key")
                if k not in review.CRITERIA or k == "score":
                    continue
                w = float(r.get("weight") or 0)
                if not 0 <= w <= 100:
                    raise ValueError("Weights go from 0 to 100.")
                crit[k] = {"show": bool(r.get("show", True)), "weight": w}
                g, a = r.get("green"), r.get("amber")
                if g not in (None, "") and a not in (None, ""):
                    g, a = float(g), float(a)
                    up = review.CRITERIA[k]["better"] == "up"
                    if (up and a > g) or (not up and a < g):
                        raise ValueError(f"{review.CRITERIA[k]['label']}: amber must be {'below' if up else 'above'} green.")
                    tg[k] = {"green": g, "amber": a}
            self.db.set_setting("review_criteria", crit)
            self.db.set_setting("review_targets", tg)
        if score and not reset:
            g, a = float(score.get("green")), float(score.get("amber"))
            if not 0 <= a <= g <= 10:
                raise ValueError("Score colours: amber must be below green, both between 0 and 10.")
            tg = self.db.get_setting("review_targets", {}) or {}
            tg["score"] = {"green": g, "amber": a}
            self.db.set_setting("review_targets", tg)
        self.db.version += 1                           # every screen recalculates with the new criteria
        cfg = review.config(self.db)
        total = sum(v["weight"] for v in cfg.values() if v["show"])
        return {"rows": [{"key": k, "label": review.CRITERIA[k]["label"], "better": review.CRITERIA[k]["better"], "fmt": review.CRITERIA[k]["fmt"],
                          "count": bool(review.CRITERIA[k].get("count")), **v, "share": round(100 * v["weight"] / total) if total and v["show"] else 0}
                         for k, v in cfg.items()], "total": total, "score": {"green": review.targets(self.db)["score"]["green"], "amber": review.targets(self.db)["score"]["amber"]},
                "custom": self._custom_people()}

    def _custom_people(self) -> list[dict]:
        """People scored on criteria of their own (person sheet → What if → Save)."""
        own = self.db.get_setting("person_criteria", {}) or {}
        if not own:
            return []
        try:
            names = {l.key: (l.name, l.designation, l.store) for l in self._po().leaders()}
        except Exception:  # noqa: BLE001
            names = {}
        return [{"key": k, "name": names.get(k, (k, "", ""))[0], "role": names.get(k, ("", "", ""))[1], "store": names.get(k, ("", "", ""))[2]} for k in own]

    def api_review_targets(self, targets: dict | None = None, reset: bool = False) -> dict:
        from . import review
        if reset:
            self.db.set_setting("review_targets", {})
        elif targets:
            cur = self.db.get_setting("review_targets", {}) or {}
            for k, v in targets.items():
                if k in review.CRITERIA and isinstance(v, dict):
                    cur[k] = {kk: (float(vv) if vv not in (None, "") else None) for kk, vv in v.items() if kk in ("green", "amber")}
            self.db.set_setting("review_targets", cur)
        t = review.targets(self.db)
        return {"rows": [{"key": k, "label": v["label"], "better": v["better"], **t[k]} for k, v in review.CRITERIA.items() if v["green"] is not None]}

    # ---------------------------------------------------------------- 3.0 office
    def api_backups(self) -> dict:
        from . import office
        return {"rows": office.backups(), "auto": self.db.get_setting("auto_backup", True) is not False, "folder": str(office.backup_dir()),
                "last": self.db.get_setting("auto_backup_last", None)}

    def api_backup_now(self) -> dict:
        from . import office
        office.auto_backup(self.db, force=True)
        return self.api_backups()

    def api_backup_auto(self, on: bool = True) -> dict:
        self.db.set_setting("auto_backup", bool(on))
        return self.api_backups()

    def api_restore_backup(self, name: str) -> dict:
        from . import office
        p = office.backup_dir() / Path(name).name
        if not p.exists():
            raise ValueError("That backup is no longer there.")
        self.db.restore(p)
        return {"ok": True}

    def api_synonyms(self) -> dict:
        from . import office
        return office.synonyms(self.db)

    def api_synonyms_save(self, field: str, words: list) -> dict:
        from . import office
        return office.save_synonyms(self.db, field, words)

    def api_tour_done(self, done: bool = True) -> dict:
        self.db.set_setting("tour_done", bool(done))
        return {"ok": True}

    def api_people_pick(self, q: str = "") -> dict:
        return {"rows": self._brain().find(q, 15)}

    # ---------------------------------------------------------------- app lock
    def _pin_hash(self, pin: str, salt: str) -> str:
        import hashlib
        return hashlib.pbkdf2_hmac("sha256", str(pin).encode(), salt.encode(), 120_000).hex()

    def api_lock_status(self) -> dict:
        c = self.db.get_setting("app_lock", {}) or {}
        return {"enabled": bool(c.get("hash")), "minutes": c.get("minutes", 10)}

    def api_lock_set(self, pin: str, minutes: int = 10, old_pin: str = "") -> dict:
        import secrets
        c = self.db.get_setting("app_lock", {}) or {}
        if c.get("hash") and self._pin_hash(old_pin, c["salt"]) != c["hash"]:
            raise ValueError("The current PIN is wrong.")
        if not re.fullmatch(r"\d{4,8}", str(pin or "")):
            raise ValueError("Use a PIN of 4 to 8 digits.")
        salt = secrets.token_hex(8)
        self.db.set_setting("app_lock", {"hash": self._pin_hash(pin, salt), "salt": salt, "minutes": max(1, min(240, int(minutes or 10)))})
        self.db.log("settings", "app lock PIN set")
        return self.api_lock_status()

    def api_lock_off(self, pin: str) -> dict:
        c = self.db.get_setting("app_lock", {}) or {}
        if c.get("hash") and self._pin_hash(pin, c["salt"]) != c["hash"]:
            raise ValueError("Wrong PIN.")
        self.db.set_setting("app_lock", {})
        self.db.log("settings", "app lock turned off")
        return self.api_lock_status()

    def api_unlock(self, pin: str) -> dict:
        import time as _t
        c = self.db.get_setting("app_lock", {}) or {}
        if not c.get("hash"):
            return {"ok": True}
        fails = getattr(self, "_pin_fails", [])
        fails = [t for t in fails if _t.time() - t < 300]
        if len(fails) >= 5:
            raise ValueError("Too many wrong PINs. Wait 5 minutes.")
        if self._pin_hash(pin, c["salt"]) == c["hash"]:
            self._pin_fails = []
            return {"ok": True}
        self._pin_fails = fails + [_t.time()]
        return {"ok": False, "left": 5 - len(self._pin_fails)}

    # ---------------------------------------------------------------- 2.3 engagement, recognition, month close
    def api_export_table(self, title: str, columns: list, rows: list, fmt: str = "xlsx", scope: str = "", save_as=None, open_after: bool = True) -> dict:
        """Any table on any screen, as Excel, PDF or Word, in the corporate style."""
        from . import exports
        rep = exports.table_report(title, [str(c) for c in columns], [[str(v) for v in r] for r in rows[:20000]], scope)
        return self._save_report(rep, fmt, save_as, open_after, f"table {title}")

    def api_export_answer(self, title: str, text: str, blocks: list | None = None, fmt: str = "pdf", save_as=None, open_after: bool = True) -> dict:
        """An AI chat answer as a PDF, Word or PowerPoint report."""
        from . import exports
        rep = exports.markdown_report(title, text, blocks or [])
        return self._save_report(rep, fmt, save_as, open_after, "answer")

    def _save_report(self, rep: dict, fmt: str, save_as, open_after: bool, what: str) -> dict:
        from . import exports
        name = exports.file_name(rep, fmt)
        path = save_as or self.host.save_path(name, fmt)
        if not path:
            return {"cancelled": True}
        exports.render(rep, fmt, path)
        self.db.log("export", f"{what} {fmt} {path}")
        if open_after:
            self.host.open_path(path)
        return {"ok": True, "path": path, "name": Path(path).name}

    # ---------------------------------------------------------------- P&O review (the ten-tab P&O workbook)
    def _po(self):
        """6.0: everything comes from the master sheet."""
        from . import master
        key = (str(self.db.path), self.db.version, json.dumps(self.db.get_setting("master_view", None), sort_keys=True))
        cached = getattr(self, "_po_cache", None)
        if cached and cached[0] == key:
            return cached[1]
        ins = master.Insights(self)
        self._po_cache = (key, ins)
        return ins

    def _po_period(self, ins=None) -> dict:
        """The Review's period bar: every master sheet loaded (year to date or one month), and the one on screen."""
        from . import master
        ps = master.periods(self.db)
        cur = master.chosen(self.db)
        slots = [{"type": p["period_type"], "from": p["period_from"] or p["period_to"], "to": p["period_to"],
                  "label": master.label(p["period_type"], p["period_from"], p["period_to"])} for p in ps]
        view = {"type": cur["period_type"], "from": cur["period_from"] or cur["period_to"], "to": cur["period_to"]} if cur else {"type": "latest"}
        return {"slots": slots, "view": view, "label": master.label(cur["period_type"], cur["period_from"], cur["period_to"]) if cur else "No data yet",
                "notes": [], "months": [{"value": p["period_to"], "label": p["period_to"]} for p in ps] or [{"value": "", "label": ""}], "coverage": []}

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
        """Pick the period the Review shows: one of the master sheets loaded (latest = the newest)."""
        self.db.set_setting("master_view", {"type": type, "to": kw.get("to")} if type in ("ytd", "mtd") else None)
        self.db.version += 1
        return self.api_po_period()

    def _leader_row(self, ins, leader, ranks) -> dict:
        from .po.format import leader_name
        from .po.insights import tenure_text
        box = ins.talent_box(leader)
        return {"key": leader.key, "rank": ranks.get(leader.key), "name": leader_name(leader), "store": leader.store or "—",
                "leads": leader.section_text, "role": leader.designation, "system_role": leader.system_designation, "score": leader.score, "business": leader.business,
                "rating": leader.latest_rating, "rating_label": leader.rating_label, "in_role": tenure_text(leader.months_in_role),
                "months_in_role": leader.months_in_role, "talent": ins.TALENT_NAMES.get(box) if box else None}

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
                out = self.agent.complete(prompt, max_tokens=700, allow_offline=False, task="insights")
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
    # 6.0: the master sheet, year to date to September and October on its own
    from . import master
    from .reader import from_text
    for month, ytd in (("2026-09", True), ("2026-10", False)):
        data = demo.master_tsv(month, ytd)
        r = master.parse(from_text(data.decode("utf-8"), "Master sheet").sheets[0])
        import hashlib
        master.save(db, r["rows"], f"Master sheet {'YTD' if ytd else 'MTD'} {month} (demo).xlsx", hashlib.sha1(data).hexdigest(),
                    "ytd" if ytd else "mtd", f"{month[:4]}-01" if ytd else month, month, source="demo")
