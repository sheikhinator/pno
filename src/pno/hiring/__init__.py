"""Hiring: vacancies, CV screening, talent bank, pipeline, interview kits, messages, onboarding and hiring analytics.

CVs are read and scored on this PC. Only the CV text with personal details removed is kept (and only that is ever
shown to an AI). Candidates outside the talent bank are anonymised after the retention period (Settings).
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..db import now
from ..paths import data_dir
from . import cvparse, scoring, templates

COMPANY = "Majid Al Futtaim · Carrefour Pakistan"


def _j(v, default):
    try:
        return json.loads(v) if v else default
    except (TypeError, ValueError):
        return default


def _days(since: str | None) -> int | None:
    try:
        return (date.today() - datetime.fromisoformat(str(since)[:19]).date()).days
    except (TypeError, ValueError):
        return None


class Hiring:
    def __init__(self, api):
        self.api = api

    @property
    def db(self):
        return self.api.db

    # ------------------------------------------------------------------ vacancies
    def templates(self) -> dict:
        return {"roles": [{"key": k, "title": r["title"]} for k, r in templates.ROLES.items()],
                "categories": list(templates.CATEGORIES), "skills": list(cvparse.SKILLS), "stages": templates.STAGES,
                "stores": self._stores()}

    def _stores(self) -> list[str]:
        names = [r[0] for r in self.db.q("SELECT name FROM stores ORDER BY name")]
        try:
            ins = self.api._po()
            names = sorted(set(names) | set(ins.stores()))
        except Exception:  # noqa: BLE001 - P&O data optional
            pass
        return names

    def draft(self, title: str = "", role: str = "", store: str = "", section: str = "", category: str = "") -> dict:
        role = role if role in templates.ROLES else templates.role_key(title)
        title = title or templates.ROLES[role]["title"]
        return {"title": title, "role": role, "jd": templates.jd_text(title, role, store, section, category),
                "rubric": templates.default_rubric(role, category)}

    def save_vacancy(self, **v) -> dict:
        vid = v.get("id")
        role = v.get("role") if v.get("role") in templates.ROLES else templates.role_key(v.get("title", ""))
        rubric = v.get("rubric") or templates.default_rubric(role, v.get("category", ""))
        if isinstance(rubric, str):
            rubric = _j(rubric, templates.default_rubric(role, v.get("category", "")))
        jd = v.get("jd") or templates.jd_text(v.get("title", ""), role, v.get("store", ""), v.get("section", ""), v.get("category", ""))
        fields = {"title": (v.get("title") or templates.ROLES[role]["title"]).strip()[:120], "role": role, "category": v.get("category") or "",
                  "store": v.get("store") or "", "section": v.get("section") or "", "grade": v.get("grade") or "",
                  "headcount": int(v.get("headcount") or 1), "manager": v.get("manager") or "", "jd": jd, "rubric": json.dumps(rubric),
                  "status": v.get("status") or "open", "target_date": v.get("target_date") or None, "notes": v.get("notes") or ""}
        if vid:
            old = self.db.q1("SELECT status, rubric FROM vacancies WHERE id=?", (vid,))
            if not old:
                raise ValueError("Vacancy not found.")
            sets = ", ".join(f"{k}=?" for k in fields)
            closed = now() if fields["status"] in ("filled", "closed") and old["status"] not in ("filled", "closed") else None
            self.db.x(f"UPDATE vacancies SET {sets}{', closed_at=?' if closed else ''} WHERE id=?",
                      (*fields.values(), *([closed] if closed else []), vid))
            if old["rubric"] != fields["rubric"]:
                self.rescore(vid)
        else:
            cur = self.db.x(f"INSERT INTO vacancies({', '.join(fields)}, created_at) VALUES({', '.join('?' * len(fields))}, ?)",
                            (*fields.values(), now()))
            vid = cur.lastrowid
        self.db.log("vacancy", f"#{vid} {fields['title']} ({fields['status']})")
        return self.vacancy(vid)

    def delete_vacancy(self, vid: int) -> dict:
        self.db.x("DELETE FROM applications WHERE vacancy_id=?", (vid,))
        self.db.x("DELETE FROM vacancies WHERE id=?", (vid,))
        return {"ok": True}

    def vacancies(self) -> dict:
        rows = []
        for v in self.db.q("SELECT * FROM vacancies ORDER BY status='open' DESC, id DESC"):
            apps = self.db.q("SELECT band, stage FROM applications WHERE vacancy_id=?", (v["id"],))
            bands = Counter(a["band"] for a in apps)
            stages = Counter(a["stage"] for a in apps)
            rows.append({"id": v["id"], "title": v["title"], "store": v["store"], "section": v["section"], "status": v["status"],
                         "headcount": v["headcount"], "days_open": _days(v["created_at"]) if v["status"] == "open" else None,
                         "target_date": v["target_date"], "cvs": len(apps), "strong": bands.get("strong", 0), "possible": bands.get("possible", 0),
                         "interview": stages.get("interview1", 0) + stages.get("interview2", 0), "offer": stages.get("offer", 0),
                         "joined": stages.get("joined", 0), "created": (v["created_at"] or "")[:10]})
        return {"rows": rows, "bank": self.db.q1("SELECT COUNT(*) FROM candidates WHERE anonymised=0")[0], **self.templates()}

    def vacancy(self, vid: int, blind: bool = False) -> dict:
        v = self.db.q1("SELECT * FROM vacancies WHERE id=?", (vid,))
        if not v:
            raise ValueError("Vacancy not found.")
        v = dict(v)
        v["rubric"] = _j(v["rubric"], templates.default_rubric(v["role"] or "associate"))
        apps = []
        for a in self.db.q("""SELECT a.*, c.name, c.city, c.parsed, c.source, c.file_name, c.created_at AS c_created FROM applications a
                              JOIN candidates c ON c.id=a.candidate_id WHERE a.vacancy_id=? ORDER BY a.score DESC""", (vid,)):
            p = _j(a["parsed"], {})
            r = _j(a["result"], {})
            apps.append({"id": a["id"], "candidate_id": a["candidate_id"],
                         "name": f"Candidate {a['candidate_id']:04d}" if blind else (a["name"] or "Unnamed"),
                         "city": a["city"] or "", "score": a["score"], "band": a["band"], "band_label": r.get("band_label", ""),
                         "stage": a["stage"], "years": p.get("years_total"), "retail_years": p.get("years_retail"),
                         "level": p.get("top_level_label") or "", "last_role": (p.get("jobs") or [{}])[0].get("title", "") if p.get("jobs") else "",
                         "retailers": p.get("retailers", [])[:3], "flags": r.get("flags", []), "knockouts": r.get("knockouts", []),
                         "tags": r.get("tags", []), "source": a["source"] or "", "panel": self._panel_avg(_j(a["panel"], []))})
        stages = Counter(a["stage"] for a in apps)
        bands = Counter(a["band"] for a in apps)
        v.update(apps=apps, blind=blind, funnel=[{"stage": k, "label": l, "count": stages.get(k, 0)} for k, l in templates.STAGES],
                 bands={k: bands.get(k, 0) for k in ("strong", "possible", "weak", "no")}, days_open=_days(v["created_at"]),
                 internal=self.internal_matches(v), skills_all=list(cvparse.SKILLS), stages=templates.STAGES)
        return v

    # ------------------------------------------------------------------ CVs
    def add_cvs(self, paths: list[str], vacancy_id: int | None = None, source: str = "Upload") -> dict:
        folder = data_dir() / "cvs"
        folder.mkdir(parents=True, exist_ok=True)
        added, updated, failed = [], [], []
        for p in paths:
            path = Path(p)
            try:
                text = cvparse.read_text(path)
            except Exception as e:  # noqa: BLE001 - reported per file
                failed.append({"file": path.name, "error": str(e)})
                continue
            if len(text.split()) < 25:
                failed.append({"file": path.name, "error": "Almost no text could be read (a scanned photo?). Save it as a PDF with text "
                                                           "or Word file and add it again."})
                continue
            parsed = cvparse.parse(text, path.name)
            safe = cvparse.redact(text)
            h = cvparse.file_hash(path)
            dup = self._find_duplicate(h, parsed)
            keep = folder / f"{uuid.uuid4().hex[:8]}{path.suffix.lower()}"
            shutil.copyfile(path, keep)
            if dup:
                self.db.x("""UPDATE candidates SET name=?, email=COALESCE(?, email), phone=COALESCE(?, phone), city=COALESCE(NULLIF(?, ''), city),
                             file_name=?, file_path=?, file_hash=?, text=?, parsed=?, updated_at=?, anonymised=0 WHERE id=?""",
                          (parsed["name"], parsed["email"], parsed["phone"], parsed["city"], path.name, str(keep), h, safe,
                           json.dumps(parsed, default=str), now(), dup))
                cid = dup
                updated.append(path.name)
            else:
                cid = self.db.x("""INSERT INTO candidates(name, email, phone, city, file_name, file_path, file_hash, text, parsed, source,
                                   created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (parsed["name"], parsed["email"], parsed["phone"], parsed["city"], path.name, str(keep), h, safe,
                                 json.dumps(parsed, default=str), source, now(), now())).lastrowid
                added.append(path.name)
            if vacancy_id:
                self.apply(int(vacancy_id), cid)
        self.db.log("cv", f"{len(added)} new, {len(updated)} updated CVs" + (f" for vacancy #{vacancy_id}" if vacancy_id else ""))
        return {"added": added, "updated": updated, "failed": failed}

    def add_uploads(self, files: list[dict], vacancy_id: int | None = None, source: str = "Upload") -> dict:
        import base64
        tmp = data_dir() / "cvs" / "incoming"
        tmp.mkdir(parents=True, exist_ok=True)
        paths = []
        for f in files[:300]:
            name = re.sub(r"[^\w.\- ]+", "_", str(f.get("name") or "cv"))[:90] or "cv"
            p = tmp / f"{uuid.uuid4().hex[:6]}-{name}"
            p.write_bytes(base64.b64decode(f["b64"]))
            paths.append(str(p))
        try:
            return self.add_cvs(paths, vacancy_id, source)
        finally:
            for p in paths:
                Path(p).unlink(missing_ok=True)

    def _find_duplicate(self, h: str, parsed: dict) -> int | None:
        r = self.db.q1("SELECT id FROM candidates WHERE file_hash=?", (h,))
        if r:
            return r[0]
        if parsed.get("email"):
            r = self.db.q1("SELECT id FROM candidates WHERE lower(email)=lower(?)", (parsed["email"],))
            if r:
                return r[0]
        if parsed.get("phone") and len(parsed["phone"]) >= 10:
            r = self.db.q1("SELECT id FROM candidates WHERE phone=?", (parsed["phone"],))
            if r:
                return r[0]
        return None

    def apply(self, vid: int, cid: int) -> int:
        v = self.db.q1("SELECT rubric, role FROM vacancies WHERE id=?", (vid,))
        c = self.db.q1("SELECT parsed, text, name, phone FROM candidates WHERE id=?", (cid,))
        if not v or not c:
            raise ValueError("Vacancy or candidate not found.")
        parsed = _j(c["parsed"], {})
        if parsed.get("internal"):                   # an internal candidate is judged on P&O's data, not a CV
            res = parsed["internal_result"]
        else:
            res = scoring.score(parsed, c["text"] or "", _j(v["rubric"], templates.default_rubric(v["role"] or "associate")))
            res["tags"] = self._history_tags(c["name"])
        existing = self.db.q1("SELECT id FROM applications WHERE vacancy_id=? AND candidate_id=?", (vid, cid))
        if existing:
            self.db.x("UPDATE applications SET score=?, band=?, result=? WHERE id=?", (res["score"], res["band"], json.dumps(res), existing[0]))
            return existing[0]
        hist = [{"stage": "applied", "at": now()}]
        return self.db.x("""INSERT INTO applications(vacancy_id, candidate_id, score, band, result, stage, stage_at, history, created_at)
                            VALUES(?,?,?,?,?,'applied',?,?,?)""", (vid, cid, res["score"], res["band"], json.dumps(res), now(), json.dumps(hist), now())).lastrowid

    def rescore(self, vid: int) -> None:
        for a in self.db.q("SELECT candidate_id FROM applications WHERE vacancy_id=?", (vid,)):
            self.apply(vid, a[0])

    def _history_tags(self, name: str | None) -> list[str]:
        """Has this person worked here before (turnover tab) or is on the payroll now (Basic Sheet)?"""
        if not name:
            return []
        try:
            from ..po import canon
            ins = self.api._po()
        except Exception:  # noqa: BLE001
            return []
        key = canon.name_key(name)
        if not key or len(key) < 6:
            return []
        tags = []
        for r in ins._full.get("po_turnover") or ins.rows("po_turnover"):
            if canon.name_key(r.get("employee_name", "")) == key:
                tags.append(f"Ex-employee: left {r.get('date') or ''} · {r.get('exit_type') or ''} · {r.get('reason') or ''}".strip(" ·"))
                break
        for r in ins.rows("po_master"):
            if canon.name_key(r.get("employee_name", "")) == key:
                tags.append(f"Same name as a current employee ({r.get('designation') or 'staff'}, {r.get('store') or ''})")
                break
        return tags

    def candidate(self, cid: int, vid: int | None = None, blind: bool = False) -> dict:
        c = self.db.q1("SELECT * FROM candidates WHERE id=?", (cid,))
        if not c:
            raise ValueError("Candidate not found.")
        c = dict(c)
        p = _j(c.pop("parsed"), {})
        out = {"id": cid, "name": f"Candidate {cid:04d}" if blind else c["name"], "email": None if blind else c["email"],
               "phone": None if blind else c["phone"], "city": c["city"], "file_name": None if blind else c["file_name"],
               "source": c["source"], "notes": c["notes"] or "", "bank": bool(c["bank"]), "parsed": p, "text": c["text"] or "",
               "added": (c["created_at"] or "")[:10], "anonymised": bool(c["anonymised"]), "applications": []}
        for a in self.db.q("""SELECT a.*, v.title, v.store FROM applications a JOIN vacancies v ON v.id=a.vacancy_id
                              WHERE a.candidate_id=? ORDER BY a.id DESC""", (cid,)):
            r = _j(a["result"], {})
            out["applications"].append({"id": a["id"], "vacancy_id": a["vacancy_id"], "title": a["title"], "store": a["store"], "score": a["score"],
                                        "band": a["band"], "band_label": r.get("band_label"), "stage": a["stage"], "result": r,
                                        "history": _j(a["history"], []), "ai": _j(a["ai"], {}), "kit": _j(a["kit"], None),
                                        "panel": _j(a["panel"], []), "panel_avg": self._panel_avg(_j(a["panel"], [])),
                                        "onboarding": _j(a["onboarding"], {}), "checklist": templates.ONBOARDING})
        if vid:
            out["applications"].sort(key=lambda a: a["vacancy_id"] != int(vid))
        return out

    def update_candidate(self, cid: int, notes: str | None = None, bank: bool | None = None, name: str | None = None,
                         city: str | None = None) -> dict:
        if notes is not None:
            self.db.x("UPDATE candidates SET notes=?, updated_at=? WHERE id=?", (notes[:4000], now(), cid))
        if bank is not None:
            self.db.x("UPDATE candidates SET bank=? WHERE id=?", (1 if bank else 0, cid))
        if name:
            self.db.x("UPDATE candidates SET name=? WHERE id=?", (name.strip()[:120], cid))
        if city is not None:
            self.db.x("UPDATE candidates SET city=? WHERE id=?", (city.strip()[:60], cid))
        return self.candidate(cid)

    def delete_candidate(self, cid: int) -> dict:
        r = self.db.q1("SELECT file_path FROM candidates WHERE id=?", (cid,))
        if r and r[0]:
            Path(r[0]).unlink(missing_ok=True)
        self.db.x("DELETE FROM applications WHERE candidate_id=?", (cid,))
        self.db.x("DELETE FROM candidates WHERE id=?", (cid,))
        self.db.log("candidate deleted", f"#{cid}")
        return {"ok": True}

    # ------------------------------------------------------------------ pipeline
    def set_stage(self, app_id: int, stage: str, note: str = "") -> dict:
        if stage not in dict(templates.STAGES):
            raise ValueError("Unknown stage.")
        a = self.db.q1("SELECT history, candidate_id, vacancy_id FROM applications WHERE id=?", (app_id,))
        if not a:
            raise ValueError("Application not found.")
        hist = _j(a["history"], [])
        hist.append({"stage": stage, "at": now(), "note": note[:300]})
        self.db.x("UPDATE applications SET stage=?, stage_at=?, history=? WHERE id=?", (stage, now(), json.dumps(hist), app_id))
        if stage == "joined":
            v = self.db.q1("SELECT headcount, (SELECT COUNT(*) FROM applications WHERE vacancy_id=? AND stage='joined') FROM vacancies WHERE id=?",
                           (a["vacancy_id"], a["vacancy_id"]))
            if v and v[1] >= v[0]:
                self.db.x("UPDATE vacancies SET status='filled', closed_at=? WHERE id=? AND status='open'", (now(), a["vacancy_id"]))
        return {"ok": True, "stage": stage}

    def kit(self, app_id: int, use_ai: bool = True) -> dict:
        a = self.db.q1("""SELECT a.result, v.role, v.title, v.rubric, c.parsed, c.text FROM applications a JOIN vacancies v ON v.id=a.vacancy_id
                          JOIN candidates c ON c.id=a.candidate_id WHERE a.id=?""", (app_id,))
        if not a:
            raise ValueError("Application not found.")
        role = templates.ROLES.get(a["role"] or "associate", templates.ROLES["associate"])
        res, p = _j(a["result"], {}), _j(a["parsed"], {})
        qs = []
        for comp in role["competencies"]:
            for q in templates.QUESTIONS.get(comp, []):
                qs.append({"area": comp, "q": q, "type": "competency"})
        rubric = _j(a["rubric"], {})
        skills = next((c.get("items", []) for c in rubric.get("criteria", []) if c["type"] == "skills"), [])
        for s in skills:
            if s not in (p.get("skills") or {}) and s in templates.SKILL_PROBES:
                qs.append({"area": s, "q": templates.SKILL_PROBES[s], "type": "gap"})
        for f in res.get("flags", []):
            qs.append({"area": "CV check", "q": f"{f}: can you walk us through what happened then?", "type": "flag"})
        if p.get("jobs"):
            j = p["jobs"][0]
            qs.append({"area": "Experience", "q": f"In your latest role ({j.get('title') or 'current job'}, since {j['start']}), what were "
                                                  "your targets and how did you do against them?", "type": "cv"})
        ai_qs = []
        if use_ai:
            try:
                out = self.api.agent.complete(
                    "You interview candidates for Carrefour Pakistan stores. Role: " + a["title"] + ". From this CV (personal details removed), "
                    "write 5 sharp, specific interview questions that test the claims and the gaps against the role. One per line, no numbering.\n\n"
                    + (a["text"] or "")[:5000], max_tokens=500, allow_offline=True)
                if out:
                    ai_qs = [l.strip(" -•\t0123456789.") for l in out[0].splitlines() if len(l.strip()) > 15][:6]
            except Exception:  # noqa: BLE001 - the built-in kit is enough
                ai_qs = []
        qs += [{"area": "AI · from the CV", "q": q, "type": "ai"} for q in ai_qs]
        kit = {"questions": qs, "competencies": role["competencies"], "made": now()}
        self.db.x("UPDATE applications SET kit=? WHERE id=?", (json.dumps(kit), app_id))
        return kit

    def panel_score(self, app_id: int, interviewer: str, scores: dict, note: str = "", decision: str = "") -> dict:
        a = self.db.q1("SELECT panel FROM applications WHERE id=?", (app_id,))
        if not a:
            raise ValueError("Application not found.")
        panel = [p for p in _j(a["panel"], []) if p.get("interviewer") != interviewer]
        clean = {k: max(1, min(5, int(v))) for k, v in (scores or {}).items() if str(v).strip()}
        panel.append({"interviewer": interviewer.strip()[:60] or "Interviewer", "scores": clean, "note": note[:1000],
                      "decision": decision, "at": now()})
        self.db.x("UPDATE applications SET panel=? WHERE id=?", (json.dumps(panel), app_id))
        return {"panel": panel, "avg": self._panel_avg(panel)}

    @staticmethod
    def _panel_avg(panel: list) -> float | None:
        vals = [v for p in panel for v in (p.get("scores") or {}).values()]
        return round(sum(vals) / len(vals), 2) if vals else None

    def onboarding(self, app_id: int, item: str, done: bool) -> dict:
        a = self.db.q1("SELECT onboarding FROM applications WHERE id=?", (app_id,))
        ob = _j(a["onboarding"] if a else None, {})
        ob[item] = now()[:10] if done else None
        ob = {k: v for k, v in ob.items() if v}
        self.db.x("UPDATE applications SET onboarding=? WHERE id=?", (json.dumps(ob), app_id))
        return {"onboarding": ob, "checklist": templates.ONBOARDING}

    def message(self, app_id: int, kind: str = "invite", lang: str = "en", when: str = "", place: str = "") -> dict:
        a = self.db.q1("""SELECT c.name, v.title, v.store FROM applications a JOIN candidates c ON c.id=a.candidate_id
                          JOIN vacancies v ON v.id=a.vacancy_id WHERE a.id=?""", (app_id,))
        if not a:
            raise ValueError("Application not found.")
        t = templates.MESSAGES.get(kind, templates.MESSAGES["invite"]).get(lang) or templates.MESSAGES[kind]["en"]
        return {"text": t.format(name=(a["name"] or "Candidate").split()[0] if lang == "en" else (a["name"] or ""), role=a["title"],
                                 company="Carrefour Pakistan (Majid Al Futtaim)", store=a["store"] or "our store",
                                 date=when or "[date and time]", place=place or a["store"] or "[place]")}

    def ai_assess(self, app_id: int) -> dict:
        a = self.db.q1("""SELECT a.result, v.title, v.jd, c.text FROM applications a JOIN vacancies v ON v.id=a.vacancy_id
                          JOIN candidates c ON c.id=a.candidate_id WHERE a.id=?""", (app_id,))
        if not a:
            raise ValueError("Application not found.")
        res = _j(a["result"], {})
        prompt = ("You screen CVs for Carrefour Pakistan. Judge only experience, skills, results and fit to the role; ignore age, gender, "
                  "marital status, religion and anything personal. Role and JD:\n" + (a["jd"] or a["title"])[:2500] +
                  f"\n\nThe app's score: {res.get('score')}/100 ({res.get('band_label')}). CV (personal details removed):\n" + (a["text"] or "")[:6000] +
                  "\n\nWrite: one line verdict; 'Strengths:' 3 bullets with evidence; 'Concerns:' up to 3 bullets; 'Ask in interview:' 2 bullets. Markdown, short.")
        out = self.api.agent.complete(prompt, max_tokens=600)
        if not out:
            return {"ok": False, "message": "No AI is set up (Settings → AI). The app's own score and evidence still apply."}
        ai = {"text": out[0], "engine": out[1], "at": now()}
        self.db.x("UPDATE applications SET ai=? WHERE id=?", (json.dumps(ai), app_id))
        return {"ok": True, **ai}

    # ------------------------------------------------------------------ talent bank
    def bank(self, q: str = "", skill: str = "", city: str = "", min_years: float = 0, limit: int = 300) -> dict:
        rows = []
        ql = (q or "").lower().strip()
        for c in self.db.q("SELECT * FROM candidates WHERE anonymised=0 ORDER BY updated_at DESC"):
            p = _j(c["parsed"], {})
            if skill and skill not in (p.get("skills") or {}):
                continue
            if city and (c["city"] or "").lower() != city.lower():
                continue
            if min_years and (p.get("years_total") or 0) < float(min_years):
                continue
            if ql and ql not in f"{c['name']} {c['text']} {c['city']} {c['notes']}".lower():
                continue
            apps = self.db.q("SELECT a.stage, v.title FROM applications a JOIN vacancies v ON v.id=a.vacancy_id WHERE a.candidate_id=?", (c["id"],))
            rows.append({"id": c["id"], "name": c["name"], "city": c["city"] or "", "years": p.get("years_total"), "retail_years": p.get("years_retail"),
                         "level": p.get("top_level_label") or "", "skills": list((p.get("skills") or {}).keys())[:6], "retailers": p.get("retailers", [])[:3],
                         "applied": [f"{a['title']} · {dict(templates.STAGES).get(a['stage'], a['stage'])}" for a in apps][:3],
                         "added": (c["created_at"] or "")[:10], "bank": bool(c["bank"])})
            if len(rows) >= limit:
                break
        cities = sorted({r["city"] for r in rows if r["city"]})
        return {"rows": rows, "total": len(rows), "skills": list(cvparse.SKILLS), "cities": cities}

    def match_bank(self, vid: int, limit: int = 30) -> dict:
        """Score everyone in the talent bank against a vacancy (without adding them) to find past applicants who fit."""
        v = self.db.q1("SELECT rubric, role FROM vacancies WHERE id=?", (vid,))
        if not v:
            raise ValueError("Vacancy not found.")
        rubric = _j(v["rubric"], templates.default_rubric(v["role"] or "associate"))
        already = {r[0] for r in self.db.q("SELECT candidate_id FROM applications WHERE vacancy_id=?", (vid,))}
        out = []
        for c in self.db.q("SELECT id, name, city, parsed, text FROM candidates WHERE anonymised=0 AND bank=1"):
            if c["id"] in already:
                continue
            r = scoring.score(_j(c["parsed"], {}), c["text"] or "", rubric)
            if r["band"] in ("strong", "possible"):
                out.append({"id": c["id"], "name": c["name"], "city": c["city"] or "", "score": r["score"], "band": r["band"], "band_label": r["band_label"]})
        out.sort(key=lambda x: -x["score"])
        return {"rows": out[:limit]}

    def internal_search(self, vid: int) -> dict:
        from . import internal
        v = self.db.q1("SELECT * FROM vacancies WHERE id=?", (vid,))
        if not v:
            raise ValueError("Vacancy not found.")
        r = internal.search(self.api, dict(v))
        added = {str(_j(x["parsed"], {}).get("emp")) for x in self.db.q(
            "SELECT c.parsed FROM applications a JOIN candidates c ON c.id=a.candidate_id WHERE a.vacancy_id=? AND c.source='Internal'", (vid,))}
        for c in r["candidates"]:
            c["in_pipeline"] = str(c["emp"]) in added
        r["bank"] = self.match_bank(vid, 8)["rows"]
        r["external_pipeline"] = self.db.q1("SELECT COUNT(*) FROM applications a JOIN candidates c ON c.id=a.candidate_id WHERE a.vacancy_id=? AND c.source!='Internal'", (vid,))[0]
        return r

    def add_internal(self, vid: int, key: str) -> dict:
        """Put an internal candidate into the vacancy's pipeline, with their P&O profile instead of a CV."""
        from . import internal
        v = self.db.q1("SELECT * FROM vacancies WHERE id=?", (vid,))
        r = internal.search(self.api, dict(v), limit=200)
        c = next((x for x in r["candidates"] if str(x["key"]) == str(key)), None)
        if not c:
            raise ValueError("This person is no longer in the internal list.")
        band = "strong" if c["fit"] >= 75 else "possible" if c["fit"] >= 60 else "weak"
        result = {"score": c["fit"], "band": band, "band_label": f"Internal · {c['move']}", "parts": [], "flags": c["watch"], "knockouts": [],
                  "tags": ["Internal", c["move"]], "internal": {k: c[k] for k in ("designation", "store", "leads", "index", "ratings", "why", "watch", "backfill", "parts", "move")}}
        parsed = {"internal": True, "emp": c["emp"], "name": c["name"], "internal_result": result, "years_total": round(c["service_months"] / 12, 1) if c.get("service_months") else None,
                  "top_level_label": c["designation"], "jobs": [{"title": c["designation"], "company": "Carrefour (MAF)"}], "retailers": ["Carrefour"]}
        ex = self.db.q1("SELECT id FROM candidates WHERE source='Internal' AND json_extract(parsed, '$.emp')=?", (str(c["emp"]),))
        text = f"{c['name']} · {c['designation']} · {c['store']} · {c['leads']}\n" + "\n".join(c["why"] + c["watch"])
        if ex:
            cid = ex[0]
            self.db.x("UPDATE candidates SET parsed=?, text=?, updated_at=? WHERE id=?", (json.dumps(parsed, default=str), text, now(), cid))
        else:
            cid = self.db.x("""INSERT INTO candidates(name, email, phone, city, file_name, file_path, file_hash, text, parsed, source, created_at, updated_at, bank)
                               VALUES(?,?,?,?,?,?,?,?,?,'Internal',?,?,0)""", (c["name"], None, None, c.get("city") or "", "", "", f"internal-{c['emp']}",
                                                                             text, json.dumps(parsed, default=str), now(), now())).lastrowid
        self.apply(vid, cid)
        self.db.log("hiring", f"internal candidate {c['emp']} added to vacancy #{vid}")
        return self.internal_search(vid)

    def internal_matches(self, v: dict) -> list[dict]:
        """People already in the business who could step up into this vacancy (one level below, same area)."""
        try:
            ins = self.api._po()
            from ..po import canon
            from ..po.format import leader_name
        except Exception:  # noqa: BLE001
            return []
        level = templates.ROLES.get(v.get("role") or "associate", templates.ROLES["associate"])["level"]
        if level <= 1:
            return []                      # entry roles are filled from outside
        out = []
        for l in ins.leaders():
            lv = canon.role_rank(l.designation)
            if lv != level - 1 and not (level == 2 and lv == 1):
                continue
            same_area = not v.get("section") or any(v["section"].lower() in s.lower() or s.lower() in v["section"].lower() for s in l.sections)
            score = (l.score or 0) + (10 if same_area else 0) + (10 if (l.latest_rating or 0) >= 4 else 0) + (5 if (l.months_in_role or 0) >= 18 else 0)
            out.append({"name": leader_name(l), "role": l.designation, "store": l.store, "leads": l.section_text, "index": l.score,
                        "rating": l.latest_rating, "in_role_months": l.months_in_role, "fit": round(score, 1), "same_area": same_area})
        return sorted(out, key=lambda x: -x["fit"])[:8]

    # ------------------------------------------------------------------ analytics and housekeeping
    def analytics(self) -> dict:
        vac = [dict(v) for v in self.db.q("SELECT * FROM vacancies")]
        apps = [dict(a) | {"src": a["source"]} for a in self.db.q("SELECT a.*, c.source FROM applications a JOIN candidates c ON c.id=a.candidate_id")]
        hires = [a for a in apps if a["stage"] == "joined"]
        tth = []
        for a in hires:
            v = next((x for x in vac if x["id"] == a["vacancy_id"]), None)
            if v and v["created_at"] and a["stage_at"]:
                tth.append((datetime.fromisoformat(a["stage_at"][:19]) - datetime.fromisoformat(v["created_at"][:19])).days)
        order = ["applied", "screened", "interview1", "interview2", "offer", "joined"]

        def furthest(a) -> int:
            seen = [h["stage"] for h in _j(a["history"], [])] + [a["stage"]]
            return max((order.index(x) for x in seen if x in order), default=0)
        offers = [a for a in apps if furthest(a) >= order.index("offer")]
        decided = [a for a in offers if a["stage"] in ("joined", "rejected", "withdrawn")]
        accepted = [a for a in decided if a["stage"] == "joined"]
        by_src: dict[str, Counter] = {}
        for a in apps:
            by_src.setdefault(a["src"] or "Upload", Counter())[a["stage"]] += 1
        open_v = [v for v in vac if v["status"] == "open"]
        bands = Counter(a["band"] for a in apps)
        stage_n = Counter(a["stage"] for a in apps)
        reached = lambda s: sum(1 for a in apps if furthest(a) >= order.index(s))  # noqa: E731
        funnel = [{"label": "CVs", "count": len(apps)}, {"label": "Screened", "count": reached("screened")},
                  {"label": "Interviewed", "count": reached("interview1")}, {"label": "Offered", "count": reached("offer")},
                  {"label": "Joined", "count": reached("joined")}]
        return {"open": len(open_v), "filled": sum(1 for v in vac if v["status"] == "filled"), "cvs": len(apps),
                "bank": self.db.q1("SELECT COUNT(*) FROM candidates WHERE anonymised=0")[0],
                "avg_days_open": round(sum(_days(v["created_at"]) or 0 for v in open_v) / len(open_v), 1) if open_v else None,
                "time_to_hire": round(sum(tth) / len(tth), 1) if tth else None, "hires": len(hires),
                "offer_acceptance": round(100 * len(accepted) / len(decided), 1) if decided else None,
                "offers_pending": len(offers) - len(decided),
                "bands": {k: bands.get(k, 0) for k in ("strong", "possible", "weak", "no")}, "stages": dict(stage_n), "funnel": funnel,
                "sources": [{"source": s, "cvs": sum(c.values()), "interviewed": c.get("interview1", 0) + c.get("interview2", 0) + c.get("offer", 0) + c.get("joined", 0),
                             "joined": c.get("joined", 0)} for s, c in sorted(by_src.items(), key=lambda kv: -sum(kv[1].values()))],
                "oldest": sorted(({"title": v["title"], "store": v["store"], "days": _days(v["created_at"])} for v in open_v), key=lambda x: -(x["days"] or 0))[:8]}

    def retention(self, months: int | None = None) -> dict:
        """Anonymise candidates outside the talent bank whose last activity is older than the retention period."""
        months = int(months or self.db.get_setting("hire_keep_months", 12) or 12)
        cutoff = (datetime.now() - timedelta(days=30 * months)).isoformat()
        old = self.db.q("SELECT id, file_path FROM candidates WHERE bank=0 AND anonymised=0 AND updated_at < ?", (cutoff,))
        for c in old:
            if c["file_path"]:
                Path(c["file_path"]).unlink(missing_ok=True)
            self.db.x("""UPDATE candidates SET name=?, email=NULL, phone=NULL, file_name=NULL, file_path=NULL, text='', notes='',
                         anonymised=1 WHERE id=?""", (f"Former candidate {c['id']:04d}", c["id"]))
        return {"anonymised": len(old), "months": months}

    # ------------------------------------------------------------------ shortlist pack (PDF / PowerPoint / Excel)
    def report(self, vid: int, hide: bool = False) -> dict:
        v = self.vacancy(vid, blind=hide)
        rub = v["rubric"]
        top = [a for a in v["apps"] if a["band"] in ("strong", "possible")][:15]
        rep = {"pack": "hiring", "title": f"Shortlist · {v['title']}", "month": date.today().strftime("%Y-%m"),
               "month_label": date.today().strftime("%d %b %Y"), "scope": " · ".join(x for x in (v["store"], v["section"]) if x) or "All stores",
               "generated": datetime.now().strftime("%d %b %Y %H:%M"), "hide": hide, "as_of": None, "sections": [],
               "sources": [f"{len(v['apps'])} CVs screened on this PC against the vacancy's rubric (personal details hidden from scoring)"]}
        S = rep["sections"]
        S.append({"type": "kpis", "items": [
            {"label": "CVs screened", "value": str(len(v["apps"])), "sub": f"open {v['days_open'] or 0} days"},
            {"label": "Strong", "value": str(v["bands"]["strong"]), "sub": "interview"},
            {"label": "Possible", "value": str(v["bands"]["possible"]), "sub": "phone screen"},
            {"label": "Weak / not suitable", "value": str(v["bands"]["weak"] + v["bands"]["no"]), "sub": "hold or regret"}]})
        S.append({"type": "chart", "kind": "hbar", "title": "Top candidates · match score (0-100)", "labels": [a["name"] for a in top[:12]],
                  "series": [{"name": "Score", "values": [a["score"] for a in top[:12]]}]})
        S.append({"type": "table", "title": "Shortlist", "columns": [
            ("#", "rank", ""), ("Candidate", "name", ""), ("Score", "score", "score"),
            ("Recommendation", "band_label", ""), ("Highest role", "level", ""), ("Years", "years", ""),
            ("Retail yrs", "retail_years", ""), ("City", "city", ""), ("Stage", "stage", "")],
            "rows": [{**a, "rank": i + 1, "stage": dict(templates.STAGES).get(a["stage"], a["stage"])} for i, a in enumerate(v["apps"][:40])]})
        S.append({"type": "table", "title": "How candidates are scored", "columns": [
            ("Criterion", "label", ""), ("Weight", "weight", ""), ("Asks for", "target", "")],
            "rows": [{"label": c["label"], "weight": c["weight"], "target": c.get("target") if c["type"] != "skills" else ", ".join(c.get("items", []))}
                     for c in rub["criteria"] if c.get("weight")]})
        for a in top[:6]:
            c = self.candidate(a["candidate_id"], vid, blind=hide)
            app = next((x for x in c["applications"] if x["vacancy_id"] == vid), None)
            if not app:
                continue
            r = app["result"]
            S.append({"type": "pagebreak"})
            S.append({"type": "heading", "title": f"{a['name']} · {a['score']:.0f}/100 · {a['band_label']}",
                      "sub": f"{a['level'] or 'Level not found'} · {a['years'] or '—'} years · {a['city'] or 'city not stated'}"})
            S.append({"type": "table", "title": "Score breakdown", "columns": [
                ("Criterion", "label", ""), ("Points", "pts", ""), ("Finding", "why", ""), ("Evidence in CV", "evidence", "")],
                "rows": [{"label": p["label"], "pts": f"{p['points']:.0f} / {p['max']:.0f}", "why": p["why"], "evidence": p["evidence"]} for p in r["parts"]]})
            lines = [f"Strength: {x}" for x in r.get("strengths", [])] + [f"Gap: {x}" for x in r.get("gaps", [])] + \
                    [f"Check: {x}" for x in r.get("flags", []) + r.get("tags", [])]
            if lines:
                S.append({"type": "text", "title": "Strengths, gaps and checks", "lines": lines})
        if v["internal"]:
            S.append({"type": "pagebreak"})
            S.append({"type": "table", "title": "Internal people who could step up", "columns": [
                ("Name", "name", ""), ("Role", "role", ""), ("Store", "store", ""), ("Leads", "leads", ""),
                ("Leader index /100", "index", "score"), ("Rating", "rating", "")], "rows": v["internal"]})
        return rep
