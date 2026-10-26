"""Learning Studio: retail courses for any role, sized to the hours you choose, with lessons, visuals and assessments.

Courses are assembled from the built-in library (works offline). When an AI is set up it can write extra lessons on
any topic and rewrite lessons (simpler, longer, in Urdu) in the same block format, which is validated before use.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from ..db import now
from . import library

LEVELS = {1: "Associate", 2: "Team leader / supervisor", 3: "Section manager", 4: "Department head", 6: "Store manager"}
BLOCK_TYPES = {"para", "points", "formula", "example", "chart", "kpis", "steps", "table", "dodont", "callout"}
Q_TYPES = {"mcq", "tf", "calc", "scenario"}
LESSON_SCHEMA = (
    'Return JSON only: {"title": str, "objectives": [str], "blocks": [block]} where each block is one of: '
    '{"type":"para","text":str} | {"type":"points","title":str,"items":[str]} | '
    '{"type":"formula","name":str,"expr":str,"where":[str],"example":str} | {"type":"example","title":str,"lines":[str]} | '
    '{"type":"chart","kind":"bar|hbar|line","title":str,"labels":[str],"series":[{"name":str,"values":[number]}],"unit":str} | '
    '{"type":"kpis","items":[{"label":str,"value":str,"sub":str}]} | {"type":"steps","title":str,"items":[str]} | '
    '{"type":"table","title":str,"columns":[str],"rows":[[str]]} | {"type":"dodont","do":[str],"dont":[str]} | '
    '{"type":"callout","kind":"key|tip|warn","text":str}. '
    'Also "quiz": [{"type":"mcq","q":str,"options":[str],"answer":index,"explain":str} | {"type":"tf","q":str,"options":["True","False"],'
    '"answer":0|1,"explain":str} | {"type":"calc","q":str,"answer":str,"explain":str} | {"type":"scenario","q":str,"answer":str,"explain":str}].'
)


def _j(v, default):
    try:
        return json.loads(v) if v else default
    except (TypeError, ValueError):
        return default


def _json_from(text: str) -> Any:
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON")
    end = max(t.rfind("}"), t.rfind("]"))
    return json.loads(t[start:end + 1])


def clean_lesson(raw: dict) -> dict | None:
    """Keep only well-formed blocks and questions from an AI-written lesson."""
    if not isinstance(raw, dict) or not raw.get("title"):
        return None
    blocks = []
    for b in raw.get("blocks") or []:
        if not isinstance(b, dict) or b.get("type") not in BLOCK_TYPES:
            continue
        if b["type"] == "chart":
            try:
                raw_labels = list(b.get("labels", []))
                if not raw_labels or any(len(s.get("values", [])) != len(raw_labels) for s in b.get("series", [])):
                    continue                                        # values that do not line up with labels: drop
                labels = [str(x) for x in raw_labels][:12]
                series = [{"name": str(s.get("name", "")), "values": [float(v) for v in s.get("values", [])][:12]}
                          for s in b.get("series", [])][:3]
                if not series:
                    continue
                b = {"type": "chart", "kind": b.get("kind") if b.get("kind") in ("bar", "hbar", "line") else "bar", "title": str(b.get("title", "")),
                     "labels": labels, "series": series, "unit": str(b.get("unit", ""))}
            except (TypeError, ValueError):
                continue
        blocks.append(b)
    quiz = []
    for q in raw.get("quiz") or []:
        if isinstance(q, dict) and q.get("type") in Q_TYPES and q.get("q"):
            if q["type"] in ("mcq", "tf"):
                opts = q.get("options") or (["True", "False"] if q["type"] == "tf" else [])
                try:
                    ans = int(q.get("answer"))
                except (TypeError, ValueError):
                    continue
                if not opts or not 0 <= ans < len(opts):
                    continue
                q = {**q, "options": [str(o) for o in opts], "answer": ans}
            quiz.append(q)
    if not blocks:
        return None
    return {"title": str(raw["title"])[:120], "minutes": int(raw.get("minutes") or 20), "objectives": [str(o) for o in raw.get("objectives", [])][:5],
            "blocks": blocks, "quiz": quiz, "source": "AI"}


class Learning:
    def __init__(self, api):
        self.api = api

    @property
    def db(self):
        return self.api.db

    # ------------------------------------------------------------------ catalogue
    def catalogue(self) -> dict:
        return {"topics": [{"key": t["key"], "title": t["title"], "summary": t["summary"], "roles": t["roles"],
                            "lessons": len(t["lessons"]), "minutes": sum(l["minutes"] for l in t["lessons"])} for t in library.TOPICS.values()],
                "levels": [{"value": k, "label": v} for k, v in LEVELS.items()]}

    def courses(self) -> dict:
        rows = []
        for c in self.db.q("SELECT id, title, audience, role_level, hours, lecture_min, source, created_at, content FROM courses ORDER BY id DESC"):
            content = _j(c["content"], {})
            n = self.db.q1("SELECT COUNT(*), SUM(status='completed'), AVG(score) FROM assignments WHERE course_id=?", (c["id"],))
            rows.append({"id": c["id"], "title": c["title"], "audience": c["audience"], "level": c["role_level"], "hours": c["hours"],
                         "lecture_min": c["lecture_min"], "source": c["source"], "created": (c["created_at"] or "")[:10],
                         "modules": len(content.get("modules", [])), "lessons": sum(len(m.get("lessons", [])) for m in content.get("modules", [])),
                         "questions": sum(len(m.get("quiz", [])) for m in content.get("modules", [])) + len(content.get("exam", [])),
                         "assigned": n[0] or 0, "completed": n[1] or 0, "avg_score": round(n[2], 1) if n[2] is not None else None})
        paths = [dict(p) | {"course_ids": _j(p["course_ids"], [])} for p in self.db.q("SELECT * FROM learning_paths ORDER BY role_level")]
        return {"rows": rows, "paths": paths, **self.catalogue()}

    def course(self, cid: int) -> dict:
        c = self.db.q1("SELECT * FROM courses WHERE id=?", (cid,))
        if not c:
            raise ValueError("Course not found.")
        out = dict(c)
        out["content"] = _j(c["content"], {})
        out["assignments"] = [dict(a) for a in self.db.q("SELECT * FROM assignments WHERE course_id=? ORDER BY id DESC", (cid,))]
        return out

    # ------------------------------------------------------------------ building
    def plan(self, level: int = 2, topics: list[str] | None = None, hours: float = 4, lecture_min: int = 25, focus: str = "") -> list[dict]:
        """Which lessons fill the hours: library lessons in topic order, then review sessions; every module ends with a quiz."""
        keys = [k for k in (topics or []) if k in library.TOPICS] or self._match_topics(focus) or library.ROLE_TOPICS.get(int(level), library.ROLE_TOPICS[2])
        budget = max(30, int(float(hours) * 60))
        lec = max(10, int(lecture_min or 25))
        modules, used = [], 0
        for k in keys:
            t = library.TOPICS[k]
            lessons = []
            for l in t["lessons"]:
                if used + lec > budget and modules:
                    break
                lessons.append(l)
                used += lec
            if not lessons:
                break
            used += 10                                              # module quiz
            modules.append({"key": k, "lessons": lessons, "full": len(lessons) == len(t["lessons"])})
            if used >= budget:
                break
        # time left after the library content: case-study / practice sessions per module
        i = 0
        while modules and used + lec <= budget and i < 6 * len(modules):
            modules[i % len(modules)].setdefault("practice", 0)
            modules[i % len(modules)]["practice"] += 1
            used += lec
            i += 1
        return modules

    def _match_topics(self, focus: str) -> list[str]:
        f = (focus or "").lower()
        if not f.strip():
            return []
        words = {"shrink": "shrink", "waste": "shrink", "loss": "shrink", "expir": "shrink", "stock": "stock", "inventory": "stock", "oos": "stock",
                 "availability": "stock", "sales": "sales", "budget": "sales", "kpi": "sales", "growth": "sales", "productiv": "productivity",
                 "rota": "productivity", "roster": "productivity", "schedul": "productivity", "customer": "customer", "service": "customer",
                 "nps": "customer", "complaint": "customer", "lead": "leading", "team": "leading", "coach": "leading", "feedback": "leading",
                 "food safety": "food_safety", "hygiene": "food_safety", "haccp": "food_safety", "fresh": "food_safety", "temperature": "food_safety",
                 "cash": "cash", "till": "cash", "checkout": "cash", "cashier": "cash", "receiv": "receiving", "delivery": "receiving",
                 "merchand": "merch", "display": "merch", "planogram": "merch", "p&l": "pnl", "profit": "pnl", "margin": "pnl",
                 "performance": "performance", "appraisal": "performance", "goal": "performance", "safety": "safety", "accident": "safety"}
        out = []
        for w, k in words.items():
            if w in f and k not in out:
                out.append(k)
        return out

    def build(self, title: str = "", level: int = 2, topics: list[str] | None = None, hours: float = 4, lecture_min: int = 25,
              focus: str = "", audience: str = "", use_ai: bool = False, language: str = "English", jd: str = "") -> dict:
        level = int(level) if int(level or 2) in LEVELS else 2
        focus_text = " ".join(x for x in (focus, jd) if x)
        plan = self.plan(level, topics, hours, lecture_min, focus_text)
        modules = []
        for m in plan:
            t = library.TOPICS[m["key"]]
            lessons = [dict(l, minutes=int(lecture_min), source="Library") for l in m["lessons"]]
            for n in range(m.get("practice", 0)):
                lessons.append(self._practice(t, n, int(lecture_min)))
            modules.append({"key": t["key"], "title": t["title"], "summary": t["summary"], "lessons": lessons, "quiz": t["quiz"],
                            "activity": t["activity"]})
        notes = []
        ai_engine = None
        unknown_focus = focus_text.strip() and not self._match_topics(focus_text) and not topics
        if use_ai or unknown_focus:
            try:
                added, ai_engine = self._ai_module(focus_text or title, level, int(lecture_min), 3 if unknown_focus else 2)
                if added:
                    modules.insert(0 if unknown_focus else len(modules), added)
            except Exception as e:  # noqa: BLE001 - the library course still stands
                notes.append(f"AI lessons were not added: {e}")
            if unknown_focus and not ai_engine:
                notes.append("This topic is not in the built-in library and no AI is set up: the course uses the closest library topics. "
                             "Add an AI key in Settings → AI to generate any topic.")
        exam = []
        for m in modules:
            exam.extend(q for q in m.get("quiz", []) if q["type"] in ("mcq", "tf", "calc"))
        exam = exam[:20]
        objectives = [o for m in modules for l in m["lessons"][:1] for o in l.get("objectives", [])[:1]]
        aud = audience or LEVELS[level]
        total_min = sum(l.get("minutes", 0) for m in modules for l in m["lessons"]) + 10 * len(modules)
        title = title.strip() or (f"{modules[0]['title']} · {aud}" if len(modules) == 1 else f"{aud} development programme")
        content = {"title": title, "audience": aud, "level": level, "summary": f"{len(modules)} modules · {sum(len(m['lessons']) for m in modules)} lessons · "
                   f"about {round(total_min / 60, 1)} hours · {len(exam)}-question final assessment",
                   "objectives": objectives[:8], "modules": modules, "exam": exam, "pass_mark": 70, "language": language,
                   "notes": notes, "made": now(), "topics": list(dict.fromkeys(p["key"] for p in plan if p.get("key") in library.TOPICS))}
        cid = self.db.x("""INSERT INTO courses(title, audience, role_level, language, hours, lecture_min, focus, source, content, created_at, updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (title, aud, level, language, float(hours), int(lecture_min), focus_text[:500],
                                                             "Library + AI" if ai_engine else "Library", json.dumps(content), now(), now())).lastrowid
        self.db.log("course", f"#{cid} {title}")
        return self.course(cid)

    def _practice(self, t: dict, n: int, minutes: int) -> dict:
        sc = [q for q in t["quiz"] if q["type"] in ("scenario", "calc")]
        q = sc[n % len(sc)] if sc else None
        blocks = [{"type": "para", "text": f"Practice session: apply what you learned in '{t['title']}' to a real situation from your store."}]
        if q:
            blocks += [{"type": "callout", "kind": "tip", "text": "Case: " + q["q"]},
                       {"type": "steps", "title": "Work it through in pairs", "items": ["Read the case and list the facts", "Agree what to do first and why",
                                                                                         "Write the actions with an owner and a time", "Compare with the model answer"]},
                       {"type": "example", "title": "Model answer", "lines": [q["answer"], q["explain"]]}]
        blocks.append({"type": "points", "title": "On the floor", "items": [t["activity"]]})
        return {"title": f"Practice {n + 1}: {t['title'].split(' and ')[0]} on the floor", "minutes": minutes, "objectives": ["Apply the module to a real case"],
                "blocks": blocks, "source": "Library"}

    def _ai_module(self, topic: str, level: int, minutes: int, lessons: int) -> tuple[dict | None, str | None]:
        agent = self.api.agent
        sys_ = ("You are a senior retail trainer at Majid Al Futtaim Carrefour Pakistan. You write practical, accurate training for store teams: plain "
                "English, short sentences, real store examples in Pakistani rupees, formulas with worked numbers, and visuals as data (charts, tables, "
                "steps). Never invent company policy; say 'by policy' where policy applies.")
        out = agent.complete(f"Plan a training module on: {topic}. Audience: {LEVELS.get(level, 'store staff')}. Give {lessons} lesson titles. "
                             'Return JSON only: {"title": str, "summary": str, "lessons": [str]}', system=sys_, max_tokens=400, task="learning")
        if not out:
            return None, None
        plan = _json_from(out[0])
        module = {"key": "ai", "title": str(plan.get("title") or topic)[:100], "summary": str(plan.get("summary") or "")[:300], "lessons": [], "quiz": [],
                  "activity": "Apply this module on your shift and note one result to discuss with your manager."}
        for lt in (plan.get("lessons") or [])[:lessons]:
            o = agent.complete(f"Write the lesson '{lt}' of the module '{module['title']}' for {LEVELS.get(level)}s, about {minutes} minutes of teaching. "
                               "Use 6-10 blocks including at least one formula or worked example with numbers, one chart or table, one steps block, and a callout. "
                               "Add 3 quiz questions. " + LESSON_SCHEMA, system=sys_, max_tokens=2200, task="learning")
            if not o:
                continue
            try:
                lesson = clean_lesson(_json_from(o[0]))
            except (ValueError, TypeError):
                lesson = None
            if lesson:
                lesson["minutes"] = minutes
                module["quiz"].extend(lesson.pop("quiz", []))
                module["lessons"].append(lesson)
        return (module if module["lessons"] else None), out[1]

    def rewrite(self, cid: int, module: int, lesson: int, how: str) -> dict:
        """Ask the AI to rewrite one lesson: simpler, more detailed, more examples, or in Urdu."""
        c = self.course(cid)
        content = c["content"]
        les = content["modules"][module]["lessons"][lesson]
        ask = {"simpler": "Rewrite it simpler for staff with basic English: shorter sentences, same facts.",
               "detail": "Make it more detailed: add one more worked example with numbers and one more visual.",
               "examples": "Add more real store examples from Pakistani hypermarkets.",
               "urdu": "Translate all text into Urdu (Urdu script). Keep numbers, formulas and the JSON keys in English."}.get(how, how)
        out = self.api.agent.complete(f"Here is a lesson as JSON:\n{json.dumps(les, ensure_ascii=False)[:7000]}\n\n{ask} " + LESSON_SCHEMA,
                                      max_tokens=2500, task="learning")
        if not out:
            raise ValueError("No AI is set up (Settings → AI). Lessons can still be edited by hand.")
        new = clean_lesson(_json_from(out[0]))
        if not new:
            raise ValueError("The AI's answer could not be used. Try again.")
        new["minutes"] = les.get("minutes", 20)
        new.pop("quiz", None)
        content["modules"][module]["lessons"][lesson] = new
        self._save(cid, content)
        return self.course(cid)

    def edit(self, cid: int, content: dict) -> dict:
        if not isinstance(content, dict) or not content.get("modules"):
            raise ValueError("Course content is not valid.")
        self._save(cid, content)
        return self.course(cid)

    def _save(self, cid: int, content: dict) -> None:
        self.db.x("UPDATE courses SET content=?, title=?, updated_at=? WHERE id=?", (json.dumps(content, ensure_ascii=False), content.get("title", ""), now(), cid))

    def delete(self, cid: int) -> dict:
        self.db.x("DELETE FROM assignments WHERE course_id=?", (cid,))
        self.db.x("DELETE FROM courses WHERE id=?", (cid,))
        return {"ok": True}

    def duplicate(self, cid: int) -> dict:
        c = self.course(cid)
        content = c["content"]
        content["title"] = content["title"] + " (copy)"
        nid = self.db.x("""INSERT INTO courses(title, audience, role_level, language, hours, lecture_min, focus, source, content, created_at, updated_at)
                           SELECT ?, audience, role_level, language, hours, lecture_min, focus, source, ?, ?, ? FROM courses WHERE id=?""",
                        (content["title"], json.dumps(content, ensure_ascii=False), now(), now(), cid)).lastrowid
        return self.course(nid)

    # ------------------------------------------------------------------ people
    def for_person(self, key: str, hours: float = 3, lecture_min: int = 20) -> dict:
        """A development pack for one leader built from their weakest measures in the P&O review."""
        ins = self.api._po()
        leader = next((l for l in ins.leaders() if l.key == key or l.employee_id == key), None)
        if not leader:
            raise ValueError("Leader not found in the P&O review.")
        from ..po import canon
        from ..po.format import leader_name
        weak = sorted(((k, v) for k, v in leader.components.items() if v is not None and v < 70), key=lambda kv: kv[1])
        topics = list(dict.fromkeys(library.KPI_TOPIC[k] for k, _ in weak if k in library.KPI_TOPIC))
        level = min(6, max(1, canon.role_rank(leader.designation) or 2))
        level = 4 if level == 5 else level
        if not topics:
            topics = library.ROLE_TOPICS.get(level, library.ROLE_TOPICS[2])[:2]
        name = leader_name(leader)
        c = self.build(title=f"Development pack · {name}", level=level, topics=topics, hours=hours, lecture_min=lecture_min,
                       audience=leader.designation or LEVELS.get(level, ""))
        c["content"]["for"] = {"name": name, "store": leader.store, "leads": leader.section_text,
                               "why": [f"{k.replace('_', ' ')}: {v / 10:.1f}/10" for k, v in weak[:4]]}
        self._save(c["id"], c["content"])
        self.assign(c["id"], [{"person": leader.employee_id or leader.key, "name": name, "store": leader.store}])
        return self.course(c["id"])

    def assign(self, cid: int, people: list[dict], due: str | None = None) -> dict:
        for p in people:
            self.db.x("""INSERT INTO assignments(course_id, person, person_name, store, assigned_at, due, status) VALUES(?,?,?,?,?,?, 'assigned')""",
                      (cid, str(p.get("person") or p.get("name")), p.get("name") or "", p.get("store") or "", now(), due))
        return self.course(cid)

    def result(self, assignment_id: int, status: str | None = None, score: float | None = None, notes: str | None = None) -> dict:
        a = self.db.q1("SELECT course_id FROM assignments WHERE id=?", (assignment_id,))
        if not a:
            raise ValueError("Assignment not found.")
        if status:
            self.db.x("UPDATE assignments SET status=?, completed_at=? WHERE id=?",
                      (status, now() if status == "completed" else None, assignment_id))
        if score is not None and str(score) != "":
            self.db.x("UPDATE assignments SET score=? WHERE id=?", (max(0.0, min(100.0, float(score))), assignment_id))
        if notes is not None:
            self.db.x("UPDATE assignments SET notes=? WHERE id=?", (notes[:1000], assignment_id))
        return self.course(a[0])

    def remove_assignment(self, assignment_id: int) -> dict:
        a = self.db.q1("SELECT course_id FROM assignments WHERE id=?", (assignment_id,))
        self.db.x("DELETE FROM assignments WHERE id=?", (assignment_id,))
        return self.course(a[0]) if a else {"ok": True}

    def people(self) -> list[dict]:
        """People who can be assigned: P&O leaders, then everyone in the roster."""
        out, seen = [], set()
        try:
            from ..po.format import leader_name
            for l in self.api._po().leaders():
                k = l.employee_id or l.key
                if k in seen:
                    continue
                seen.add(k)
                out.append({"person": k, "name": leader_name(l), "store": l.store, "role": l.designation})
        except Exception:  # noqa: BLE001
            pass
        for r in self.db.q("SELECT DISTINCT emp_no, name, designation, bu_raw FROM roster r JOIN imports i ON i.id=r.import_id AND i.active=1 LIMIT 3000"):
            if r["emp_no"] in seen:
                continue
            seen.add(r["emp_no"])
            out.append({"person": r["emp_no"], "name": r["name"], "store": r["bu_raw"] or "", "role": r["designation"] or ""})
        return out

    def save_path(self, name: str, level: int, course_ids: list[int], pid: int | None = None) -> dict:
        if pid:
            self.db.x("UPDATE learning_paths SET name=?, role_level=?, course_ids=? WHERE id=?", (name, int(level), json.dumps(course_ids), pid))
        else:
            self.db.x("INSERT INTO learning_paths(name, role_level, course_ids, created_at) VALUES(?,?,?,?)", (name, int(level), json.dumps(course_ids), now()))
        return self.courses()

    def delete_path(self, pid: int) -> dict:
        self.db.x("DELETE FROM learning_paths WHERE id=?", (pid,))
        return self.courses()

    def stats(self) -> dict:
        a = self.db.q1("SELECT COUNT(*), SUM(status='completed'), AVG(score), SUM(score >= 70) FROM assignments")
        by_store = [dict(r) for r in self.db.q("""SELECT store, COUNT(*) AS assigned, SUM(status='completed') AS completed, ROUND(AVG(score), 1) AS avg_score
                                                  FROM assignments GROUP BY store ORDER BY assigned DESC""")]
        overdue = self.db.q1("SELECT COUNT(*) FROM assignments WHERE status!='completed' AND due IS NOT NULL AND due < ?", (date.today().isoformat(),))[0]
        return {"assigned": a[0] or 0, "completed": a[1] or 0, "avg_score": round(a[2], 1) if a[2] is not None else None, "passed": a[3] or 0,
                "overdue": overdue, "by_store": by_store, "courses": self.db.q1("SELECT COUNT(*) FROM courses")[0]}


def certificate_text(course: dict, name: str, score: float | None) -> dict:
    return {"name": name, "course": course["title"], "date": datetime.now().strftime("%d %B %Y"),
            "score": f"{score:.0f}%" if score is not None else "", "hours": course.get("hours")}
