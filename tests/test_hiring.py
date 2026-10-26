"""Hiring: CV reading and fair scoring, duplicates, pipeline, interview kit, messages, talent bank, analytics, exports."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from pno.api import Api
from pno.db import Database
from pno.hiring import cvparse, scoring, templates

STRONG = """Bilal Ahmed
bilal@example.com | 0321-7654321 | Lahore
Date of Birth: 12-05-1990
Marital Status: Married
Religion: Islam
CNIC: 35202-1234567-1
EXPERIENCE
Section Manager - Fresh Food, Carrefour Lahore    Jan 2020 - Present
Managed a team of 18 staff in butchery, bakery and deli. Shrinkage control, rostering, KPI and budget reporting, HACCP food safety.
Supervisor, Al-Fatah    Mar 2016 - Dec 2019
Inventory, stock count, merchandising, customer complaints.
EDUCATION
BBA, University of the Punjab
"""
WEAK = """Usman Tariq
usman.t@example.com 0333-1112223 Karachi
Call centre agent, ABC Telecom    Jan 2023 - Dec 2024
Customer service and complaints on the phone. Typing and data entry for the support team every day.
Intermediate
""" + "Other details about hobbies and interests. " * 5


def test_parse_reads_history_and_hides_personal_details():
    p = cvparse.parse(STRONG, "bilal.pdf")
    assert p["name"] == "Bilal Ahmed" and p["email"] == "bilal@example.com" and p["phone"] == "03217654321" and p["city"] == "Lahore"
    assert [j["title"] for j in p["jobs"]] == ["Section manager", "Team leader / supervisor"]
    assert p["years_total"] and p["years_total"] > 9 and p["years_retail"] == p["years_total"]
    assert p["team_size"] == 18 and p["education"] == "Bachelor's" and {"Butchery", "Food safety", "Shrink & loss prevention"} <= set(p["skills"])
    red = cvparse.redact(STRONG)
    for secret in ("1990", "Married", "Islam", "35202-1234567-1"):
        assert secret not in red
    assert "Carrefour" in red


def test_scoring_is_explained_and_ignores_personal_details():
    rub = templates.default_rubric("section_manager", "Fresh food")
    strong = scoring.score(cvparse.parse(STRONG), cvparse.redact(STRONG), rub)
    weak = scoring.score(cvparse.parse(WEAK), cvparse.redact(WEAK), rub)
    assert strong["band"] == "strong" and strong["score"] >= 75 and weak["band"] in ("weak", "no")
    assert all({"label", "points", "max", "why", "evidence"} <= set(p) for p in strong["parts"])
    assert any("team of 18" in p["evidence"] for p in strong["parts"])
    # the same CV with different personal details scores exactly the same
    other = STRONG.replace("Married", "Single").replace("1990", "1975").replace("Islam", "Christianity")
    assert scoring.score(cvparse.parse(other), cvparse.redact(other), rub)["score"] == strong["score"]
    ko = dict(rub, knockouts={"min_years": 0, "cities": ["Lahore"], "must_skills": []})
    assert scoring.score(cvparse.parse(WEAK), WEAK, ko)["knockouts"]


def test_flags_gaps_and_job_hopping():
    cv = "A Person\nAssociate, X  Jan 2015 - Mar 2015\nAssociate, Y Jan 2016 - Apr 2016\nAssociate, Z  Jan 2019 - Jun 2019\n"
    f = cvparse.flags(cvparse.jobs(cv))
    assert any("Gap of" in x for x in f) and any("shorter than a year" in x for x in f)


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    return Api(Database(tmp_path / "pno.sqlite3"))


def _cvs(tmp_path):
    import docx
    a = tmp_path / "Bilal Ahmed CV.docx"
    d = docx.Document()
    for line in STRONG.splitlines():
        d.add_paragraph(line)
    d.save(a)
    b = tmp_path / "usman.txt"
    b.write_text(WEAK)
    return [str(a), str(b)]


def test_vacancy_to_hire(api, tmp_path):
    d = api.dispatch("hire_draft", {"title": "Section Manager Fresh", "category": "Fresh food"})
    assert d["role"] == "section_manager" and "Key responsibilities" in d["jd"]
    v = api.dispatch("hire_save", {**{k: d[k] for k in ("title", "role", "jd", "rubric")}, "store": "LAH Fortress", "section": "Fresh Food"})
    r = api.dispatch("hire_add_paths", {"paths": _cvs(tmp_path), "vacancy_id": v["id"]})
    assert len(r["added"]) == 2 and not r["failed"], r
    again = api.dispatch("hire_add_paths", {"paths": _cvs(tmp_path)[:1], "vacancy_id": v["id"]})
    assert again["updated"] and not again["added"]                         # same person merged, not duplicated
    v = api.dispatch("hire_vacancy", {"vacancy_id": v["id"]})
    assert [a["name"] for a in v["apps"]][0] == "Bilal Ahmed" and v["bands"]["strong"] == 1
    blind = api.dispatch("hire_vacancy", {"vacancy_id": v["id"], "blind": True})
    assert all(a["name"].startswith("Candidate ") for a in blind["apps"])
    top = v["apps"][0]
    c = api.dispatch("hire_candidate", {"candidate_id": top["candidate_id"], "vacancy_id": v["id"]})
    assert "Married" not in c["text"] and c["applications"][0]["result"]["parts"]
    kit = api.dispatch("hire_kit", {"app_id": top["id"], "ai": False})
    assert len(kit["questions"]) >= 5 and {"competency"} <= {q["type"] for q in kit["questions"]}
    p = api.dispatch("hire_panel", {"app_id": top["id"], "interviewer": "Sana", "scores": {"Commercial acumen": 4, "People leadership": 5}})
    assert p["avg"] == 4.5
    ur = api.dispatch("hire_message", {"app_id": top["id"], "kind": "invite", "lang": "ur", "when": "3 Nov 11:00"})
    assert "3 Nov 11:00" in ur["text"] and "محترم" in ur["text"]
    for st in ("screened", "interview1", "offer", "joined"):
        api.dispatch("hire_stage", {"app_id": top["id"], "stage": st})
    assert api.dispatch("hire_list", {})["rows"][0]["status"] == "filled"     # headcount 1 reached
    ob = api.dispatch("hire_onboarding", {"app_id": top["id"], "item": templates.ONBOARDING[0], "done": True})
    assert templates.ONBOARDING[0] in ob["onboarding"]
    a = api.dispatch("hire_analytics", {})
    assert a["hires"] == 1 and a["offer_acceptance"] == 100.0 and [f["count"] for f in a["funnel"]] == [2, 1, 1, 1, 1]
    # the talent bank finds people for the next vacancy
    v2 = api.dispatch("hire_save", {"title": "Section Manager Bakery", "role": "section_manager", "category": "Fresh food"})
    m = api.dispatch("hire_match_bank", {"vacancy_id": v2["id"]})
    assert m["rows"] and m["rows"][0]["name"] == "Bilal Ahmed"
    assert api.dispatch("hire_bank", {"skill": "Butchery"})["total"] == 1
    # shortlist pack in every format
    from pno import exports
    rep = api.hiring.report(v["id"])
    for fmt in ("pdf", "pptx", "xlsx"):
        out = tmp_path / f"s.{fmt}"
        exports.render(rep, fmt, str(out))
        assert out.stat().st_size > 3000


def test_rubric_change_rescores(api, tmp_path):
    v = api.dispatch("hire_save", {"title": "Team Leader", "role": "team_leader"})
    api.dispatch("hire_add_paths", {"paths": _cvs(tmp_path), "vacancy_id": v["id"]})
    v = api.dispatch("hire_vacancy", {"vacancy_id": v["id"]})
    rub = v["rubric"]
    rub["knockouts"]["cities"] = ["Karachi"]
    api.dispatch("hire_save", {**{k: v[k] for k in ("id", "title", "role", "jd", "store", "section", "status")}, "rubric": rub})
    v = api.dispatch("hire_vacancy", {"vacancy_id": v["id"]})
    bilal = next(a for a in v["apps"] if a["name"] == "Bilal Ahmed")
    assert bilal["band"] == "no" and bilal["knockouts"]


def test_unreadable_cv_and_retention(api, tmp_path):
    empty = tmp_path / "scan.txt"
    empty.write_text("scan")
    r = api.dispatch("hire_add_paths", {"paths": [str(empty)]})
    assert r["failed"] and "text" in r["failed"][0]["error"]
    api.dispatch("hire_add_paths", {"paths": _cvs(tmp_path)})
    cid = api.db.q1("SELECT id FROM candidates WHERE name='Usman Tariq'")[0]
    api.dispatch("hire_candidate_update", {"candidate_id": cid, "bank": False})
    old = (datetime.now() - timedelta(days=500)).isoformat()
    api.db.x("UPDATE candidates SET updated_at=? WHERE id=?", (old, cid))
    out = api.dispatch("hire_settings", {"keep_months": 12})
    assert out["anonymised"] == 1
    c = api.db.q1("SELECT name, email, text, anonymised FROM candidates WHERE id=?", (cid,))
    assert c["anonymised"] == 1 and c["email"] is None and not c["text"] and "Usman" not in c["name"]


def test_assistant_answers_hiring(api, tmp_path):
    v = api.dispatch("hire_save", {"title": "Section Manager Fresh", "role": "section_manager", "category": "Fresh food"})
    api.dispatch("hire_add_paths", {"paths": _cvs(tmp_path), "vacancy_id": v["id"]})
    r = api.dispatch("agent_ask", {"question": "Who are the best candidates for section manager fresh?"})
    assert "Bilal Ahmed" in r["answer"] and "strong" in r["answer"].lower()
    r = api.dispatch("agent_ask", {"question": "How is hiring going?"})
    assert "open vacanc" in r["answer"]
