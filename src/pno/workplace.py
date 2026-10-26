"""2.2: HR policy library with search and answers, 1:1 and visit notes, goals, and manager effectiveness.

Policies are stored as plain text, split into passages and searched locally (BM25), so a question gets the exact
clauses even with no AI. When an AI is set up it writes a short answer from those passages only, citing them.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from .db import now

# ---------------------------------------------------------------------------------------------- policies
_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("a an the of to in on for and or is are be by with as at it this that from any all can may shall will should "
            "must not no do does what when who how which per if than then they their them its our we you your".split())
_SYN = {"leave": ["leaves", "holiday", "vacation", "absence"], "salary": ["pay", "wage", "wages", "compensation"],
        "fire": ["termination", "terminate", "dismissal"], "late": ["lateness", "tardiness", "punctuality"],
        "maternity": ["maternal", "pregnancy"], "overtime": ["ot", "extra hours"], "resign": ["resignation", "notice"],
        "fine": ["penalty", "deduction"], "warning": ["disciplinary", "da", "show cause"], "sick": ["illness", "medical"]}


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]


def _stem(w: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "ies", "es", "ed", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def chunks(text: str, size: int = 900) -> list[dict]:
    """Split a policy into passages that keep their section heading."""
    text = text.replace("\r", "")
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=\s*(?:\d+(?:\.\d+)*[.)]?\s+[A-Z]|[A-Z][A-Z /&-]{4,}$))", text) if p and p.strip()]
    out, cur, head, top = [], "", "", ""
    for p in paras:
        first = p.split("\n", 1)[0].strip()
        is_head = len(first) < 80 and (first.isupper() or bool(re.match(r"^\d+(\.\d+)*[.)]?\s+[A-Z]", first)))
        if is_head and "\n" not in p:
            if cur:
                out.append({"heading": head, "text": cur.strip()})
                cur = ""
            if first.isupper():
                top = head = first.title()
            else:
                head = f"{top} · {first}" if top else first
            continue
        if is_head and "\n" in p:                      # '2. Sick leave' followed by its text: its own passage
            if cur:
                out.append({"heading": head, "text": cur.strip()})
                cur = ""
            head = f"{top} · {first}" if top else first
        if len(cur) + len(p) > size and cur:
            out.append({"heading": head, "text": cur.strip()})
            cur = ""
        cur += p + "\n\n"
    if cur.strip():
        out.append({"heading": head, "text": cur.strip()})
    return [dict(c, n=i + 1) for i, c in enumerate(out)]


def add_policy(db, title: str, text: str, file_name: str = "", category: str = "") -> int:
    text = (text or "").strip()
    if len(text) < 40:
        raise ValueError("The policy has no readable text. Use a PDF with text (not a scan), a Word file or paste the text.")
    cs = chunks(text)
    title = (title or file_name or "Policy").strip()[:160]
    old = db.q1("SELECT id FROM policies WHERE title=?", (title,))
    if old:
        db.x("UPDATE policies SET text=?, chunks=?, file_name=?, category=?, added_at=? WHERE id=?",
             (text, json.dumps(cs), file_name, category, now(), old["id"]))
        return old["id"]
    return db.x("INSERT INTO policies(title, category, file_name, text, chunks, added_at) VALUES(?,?,?,?,?,?)",
                (title, category, file_name, text, json.dumps(cs), now())).lastrowid


def policies(db) -> list[dict]:
    return [{"id": r["id"], "title": r["title"], "category": r["category"] or "", "file_name": r["file_name"] or "",
             "added_at": r["added_at"], "passages": len(json.loads(r["chunks"] or "[]")), "words": len((r["text"] or "").split())}
            for r in db.q("SELECT * FROM policies ORDER BY category, title")]


def search(db, query: str, limit: int = 6) -> list[dict]:
    q = [_stem(w) for w in _tokens(query)]
    for w in list(q):
        for k, syn in _SYN.items():
            if w == _stem(k) or w in [_stem(s) for s in syn]:
                q += [_stem(k)] + [_stem(s) for s in syn if " " not in s]
    q = list(dict.fromkeys(q))
    if not q:
        return []
    docs = []
    for r in db.q("SELECT id, title, chunks FROM policies"):
        for c in json.loads(r["chunks"] or "[]"):
            toks = [_stem(w) for w in _tokens(c["heading"] + " " + c["text"])]
            docs.append((r["id"], r["title"], c, Counter(toks), len(toks)))
    if not docs:
        return []
    n = len(docs)
    avg = sum(d[4] for d in docs) / n
    df = Counter(w for d in docs for w in set(d[3]) if w in q)
    scored = []
    for pid, title, c, tf, ln in docs:
        s = 0.0
        for w in q:
            if tf.get(w):
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * ln / avg))
        if c["heading"] and any(w in [_stem(x) for x in _tokens(c["heading"])] for w in q):
            s *= 1.3
        if s > 0:
            scored.append({"policy_id": pid, "policy": title, "heading": c["heading"], "n": c["n"], "text": c["text"], "score": round(s, 2),
                           "highlight": _best_sentence(c["text"], q)})
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


def _best_sentence(text: str, q: list[str]) -> str:
    sents = [x for x in re.split(r"(?<=[.;:])\s+|\n", text) if len(x.strip()) >= 25] or [text]
    best = max(sents, key=lambda s: sum(1 for w in _tokens(s) if _stem(w) in q), default="")
    return best.strip()[:400]


def answer(db, agent, question: str) -> dict:
    hits = search(db, question, 6)
    if not hits:
        has = db.q1("SELECT COUNT(*) FROM policies")[0]
        return {"answer": "No policy covers this." if has else "No policies have been added yet. Add the HR policy manual (PDF or Word) first.",
                "sources": [], "engine": "search"}
    text, engine = None, "search"
    if agent is not None:
        ctx = "\n\n".join(f"[{i + 1}] {h['policy']}{(' · ' + h['heading']) if h['heading'] else ''}\n{h['text'][:1400]}" for i, h in enumerate(hits))
        try:
            out = agent.complete(f"Question: {question}\n\nPolicy passages:\n{ctx}\n\nAnswer the question in plain English using ONLY these passages. "
                                 "Cite passages like [1]. If the passages don't answer it, say the policy does not cover it. Keep it under 150 words.",
                                 system="You answer HR policy questions for a retail HR team in Pakistan, strictly from the passages given.",
                                 max_tokens=500, task="policy")
            if out and out[0]:
                text, engine = out
        except Exception:  # noqa: BLE001 - fall back to the passages themselves
            text = None
    if not text:
        top = hits[0]
        text = (f"From **{top['policy']}**{(' · ' + top['heading']) if top['heading'] else ''} [1]:\n\n> {top['highlight']}\n\n"
                "The full passages are below.")
    return {"answer": text, "sources": hits, "engine": engine}


# ---------------------------------------------------------------------------------------------- 1:1 and visit notes
NOTE_KINDS = ["1:1", "Store visit", "Feedback", "Coaching", "Concern", "Recognition"]


def add_note(db, subject: str, body: str, kind: str = "1:1", store: str = "", subject_key: str = "", follow_up: str = "",
             follow_due: str | None = None, mood: int | None = None, when: str | None = None) -> int:
    if not body.strip() and not follow_up.strip():
        raise ValueError("Write what was discussed.")
    nid = db.x("INSERT INTO meetings(subject, subject_key, store, kind, body, follow_up, follow_due, mood, met_on, created_at) "
               "VALUES(?,?,?,?,?,?,?,?,?,?)",
               (subject.strip()[:120], subject_key[:120], store[:80], kind if kind in NOTE_KINDS else "1:1", body[:6000], follow_up[:500],
                follow_due, mood if mood in (1, 2, 3, 4, 5) else None, (when or date.today().isoformat())[:10], now())).lastrowid
    if follow_up.strip():
        from . import actions
        aid = actions.add(db, follow_up.strip(), owner=subject.strip(), store=store, area=kind, due=follow_due, source=f"{kind} note")
        db.x("UPDATE meetings SET action_id=? WHERE id=?", (aid, nid))
    return nid


def notes(db, subject_key: str = "", subject: str = "", store: str = "") -> dict:
    sql, args = "SELECT n.*, a.status AS action_status FROM meetings n LEFT JOIN actions a ON a.id=n.action_id WHERE 1=1", []
    if subject_key:
        sql += " AND (n.subject_key=? OR lower(n.subject)=lower(?))"
        args += [subject_key, subject or subject_key]
    elif subject:
        sql += " AND lower(n.subject)=lower(?)"
        args.append(subject)
    if store:
        sql += " AND n.store=?"
        args.append(store)
    rows = [dict(r) for r in db.q(sql + " ORDER BY n.met_on DESC, n.id DESC LIMIT 500", tuple(args))]
    last: dict[str, str] = {}
    for r in rows:
        last.setdefault(r["subject"], r["met_on"])
    return {"rows": rows, "kinds": NOTE_KINDS, "people": len(last), "last_met": last,
            "open_follow_ups": sum(1 for r in rows if r["action_id"] and r["action_status"] in ("open", "in progress"))}


def delete_note(db, note_id: int) -> None:
    db.x("DELETE FROM meetings WHERE id=?", (note_id,))


def overdue_one_to_ones(db, ins, days: int = 45) -> list[dict]:
    """Leaders with no 1:1 note in the last N days (or never)."""
    last = {}
    for r in db.q("SELECT subject, subject_key, MAX(met_on) AS m FROM meetings WHERE kind='1:1' GROUP BY subject_key, subject"):
        for k in (r["subject_key"], (r["subject"] or "").lower()):
            if k:
                last[k] = max(last.get(k, ""), r["m"] or "")
    cut = (date.today() - timedelta(days=days)).isoformat()
    out = []
    from .po.format import leader_name
    for l in ins.leaders():
        m = last.get(l.key) or last.get(leader_name(l).lower()) or last.get((l.name or "").lower())
        if not m or m < cut:
            out.append({"key": l.key, "name": leader_name(l), "store": l.store, "role": l.designation, "last": m})
    return out


# ---------------------------------------------------------------------------------------------- goals
def _goal_progress(g: dict) -> float | None:
    try:
        b, t, c = float(g["baseline"]), float(g["target"]), float(g["current"])
    except (TypeError, ValueError):
        return None
    if t == b:
        return 100.0 if c == t else 0.0
    return round(max(0.0, min(150.0, 100 * (c - b) / (t - b))), 1)


def _goal_status(g: dict, prog: float | None) -> str:
    if g["status"] in ("done", "dropped"):
        return g["status"]
    if prog is not None and prog >= 100:
        return "achieved"
    try:
        start = date.fromisoformat((g["created_at"] or "")[:10])
        due = date.fromisoformat(g["due"])
    except (TypeError, ValueError):
        return "on track" if prog is None or prog >= 50 else "at risk"
    span = max(1, (due - start).days)
    elapsed = 100 * min(1.0, max(0, (date.today() - start).days) / span)
    if date.today() > due:
        return "missed"
    if prog is None:
        return "no update"
    return "on track" if prog >= elapsed - 10 else "at risk" if prog >= elapsed - 30 else "off track"


def add_goal(db, title: str, owner: str = "", store: str = "", metric: str = "", unit: str = "", baseline=None, target=None,
             due: str | None = None, level: str = "Store") -> int:
    if not title.strip():
        raise ValueError("Write the goal.")
    hist = [{"at": now()[:10], "value": baseline, "note": "Set"}] if baseline not in (None, "") else []
    return db.x("INSERT INTO goals(title, owner, store, level, metric, unit, baseline, target, current, due, status, created_at, updated_at, history) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,'open',?,?,?)",
                (title.strip()[:200], owner[:80], store[:80], level[:20], metric[:80], unit[:12], _num(baseline), _num(target), _num(baseline),
                 due or (date.today() + timedelta(days=90)).isoformat(), now(), now(), json.dumps(hist))).lastrowid


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "")) if v not in (None, "") else None
    except ValueError:
        return None


def update_goal(db, goal_id: int, value=None, note: str = "", status: str | None = None, **kw) -> None:
    g = db.q1("SELECT * FROM goals WHERE id=?", (goal_id,))
    if not g:
        raise ValueError("Goal not found.")
    hist = json.loads(g["history"] or "[]")
    sets, vals = [], []
    if value not in (None, ""):
        sets.append("current=?")
        vals.append(_num(value))
        hist.append({"at": now()[:10], "value": _num(value), "note": note[:300]})
    elif note:
        hist.append({"at": now()[:10], "value": None, "note": note[:300]})
    if status in ("open", "done", "dropped"):
        sets.append("status=?")
        vals.append(status)
    for k in ("title", "owner", "store", "metric", "unit", "due", "level"):
        if kw.get(k) is not None:
            sets.append(f"{k}=?")
            vals.append(str(kw[k])[:200])
    for k in ("baseline", "target"):
        if kw.get(k) not in (None, ""):
            sets.append(f"{k}=?")
            vals.append(_num(kw[k]))
    sets += ["history=?", "updated_at=?"]
    vals += [json.dumps(hist), now()]
    db.x(f"UPDATE goals SET {', '.join(sets)} WHERE id=?", (*vals, goal_id))


def delete_goal(db, goal_id: int) -> None:
    db.x("DELETE FROM goals WHERE id=?", (goal_id,))


def goals(db) -> dict:
    rows = []
    for g in db.q("SELECT * FROM goals ORDER BY status IN ('done','dropped'), due, id"):
        r = dict(g)
        r["history"] = json.loads(g["history"] or "[]")
        r["progress"] = _goal_progress(r)
        r["state"] = _goal_status(r, r["progress"])
        rows.append(r)
    st = Counter(r["state"] for r in rows)
    live = [r for r in rows if r["status"] == "open"]
    return {"rows": rows, "counts": dict(st), "open": len(live),
            "avg_progress": round(statistics.mean([r["progress"] for r in live if r["progress"] is not None]), 1) if any(r["progress"] is not None for r in live) else None,
            "templates": GOAL_TEMPLATES}


GOAL_TEMPLATES = [
    {"title": "Cut staff turnover", "metric": "Leavers per month", "unit": "", "level": "Store"},
    {"title": "Raise sales productivity", "metric": "Sales per labour hour", "unit": "PKR", "level": "Store"},
    {"title": "Lift customer NPS", "metric": "NPS", "unit": "pts", "level": "Store"},
    {"title": "Reduce shrinkage", "metric": "Shrink % of sales", "unit": "%", "level": "Department"},
    {"title": "Reduce real absence", "metric": "Absence %", "unit": "%", "level": "Store"},
    {"title": "Complete mandatory training", "metric": "Completion %", "unit": "%", "level": "Store"},
    {"title": "Fill open vacancies", "metric": "Open vacancies", "unit": "", "level": "Store"},
]


# ---------------------------------------------------------------------------------------------- manager effectiveness
def manager_effectiveness(ins) -> dict:
    """For each manager on the Basic Sheet: how their team is doing (leader index, ratings, people leaving, discipline)."""
    from .po.format import leader_name
    from .po import canon
    leaders = {l.employee_id: l for l in ins.leaders() if l.employee_id}
    by_name = {canon.name_key(l.name): l for l in leaders.values()}
    teams: dict[str, list] = defaultdict(list)
    for r in ins.rows("po_master"):
        m = (r.get("manager_name") or "").strip()
        if m:
            teams[canon.name_key(m)].append(r)
    out = []
    for mk, team in teams.items():
        if len(team) < 2:
            continue
        mgr = by_name.get(mk)
        name = leader_name(mgr) if mgr else canon.repair_name(team[0].get("manager_name"))
        tl = [leaders.get(str(t.get("employee_id"))) for t in team]
        tl = [x for x in tl if x]
        idx = [x.score for x in tl if x.score is not None]
        rat = [x.latest_rating for x in tl if x.latest_rating is not None]
        leavers = sum(x.kpis.get("leavers") or 0 for x in tl)
        da = sum(x.kpis.get("da") or 0 for x in tl)
        parts, why = [], []
        if idx:
            parts.append((statistics.mean(idx), 0.45))
        if rat:
            parts.append(((statistics.mean(rat) - 1) / 4 * 100, 0.25))
        churn = 100 - min(100, 100 * leavers / max(1, len(team) * 6))
        parts.append((churn, 0.2))
        parts.append((100 - min(100, da * 15), 0.1))
        w = sum(p[1] for p in parts)
        score = round(sum(v * k for v, k in parts) / w, 1)
        if idx and statistics.mean(idx) < 55:
            why.append(f"Team leader index {statistics.mean(idx):.0f}")
        if rat and statistics.mean(rat) < 2.7:
            why.append(f"Team rating {statistics.mean(rat):.1f}")
        if leavers >= len(team) * 2:
            why.append(f"{leavers} people left their teams")
        if da >= 3:
            why.append(f"{da} disciplinary cases")
        out.append({"manager": name, "store": (mgr.store if mgr else team[0].get("store")) or "", "role": mgr.designation if mgr else "",
                    "team": len(team), "leaders_scored": len(idx), "team_index": round(statistics.mean(idx), 1) if idx else None,
                    "team_rating": round(statistics.mean(rat), 2) if rat else None, "leavers": leavers, "da": da, "score": score,
                    "band": "Strong" if score >= 70 else "Steady" if score >= 55 else "Needs support", "why": why})
    out.sort(key=lambda r: -r["score"])
    return {"rows": out, "managers": len(out), "needs_support": sum(1 for r in out if r["band"] == "Needs support")}
