"""2.2: policy library and answers, 1:1 notes, goals, manager effectiveness."""

from __future__ import annotations

import base64
from datetime import date, timedelta

import pytest

from pno import importers, workplace
from pno.api import Api
from pno.db import Database

from po_fixture import make_po_workbook

POLICY = """LEAVE POLICY

1. Annual leave
Permanent employees are entitled to 20 working days of annual leave per calendar year. Annual leave must be approved by the line manager at least 7 days in advance.

2. Sick leave
Employees may take up to 8 days of paid sick leave per year. A medical certificate is required for more than 2 consecutive days.

3. Maternity leave
Female employees are entitled to 90 days of paid maternity leave.

ATTENDANCE AND PUNCTUALITY

4. Late arrival
Arriving more than 15 minutes after the shift start counts as late. Three late arrivals in a month lead to a written warning.
"""


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "pno.sqlite3")
    a = importers.analyze_path(make_po_workbook(tmp_path / "po.xlsx"))
    importers.commit(db, a, {"*": {"month": "2026-09", "as_of": "2026-09-30"}})
    return Api(db)


def test_policy_chunks_keep_headings():
    cs = workplace.chunks(POLICY)
    assert len(cs) >= 3
    assert any("Sick leave" in c["heading"] or "Sick leave" in c["text"] for c in cs)


def test_policy_search_and_answer(api):
    r = api.dispatch("policy_upload", {"files": [{"name": "Leave_Policy.txt", "b64": base64.b64encode(POLICY.encode()).decode()}]})
    assert r["added"] == ["Leave Policy"] and r["policies"][0]["passages"] >= 3
    hits = workplace.search(api.db, "how many sick days")
    assert hits and "8 days" in hits[0]["text"]
    hits = workplace.search(api.db, "what happens if someone is late three times")
    assert hits and "written warning" in hits[0]["text"]
    ans = api.dispatch("policy_ask", {"question": "How much annual leave do we get?", "ai": False})
    assert ans["engine"] == "search" and ans["sources"] and "20 working days" in ans["sources"][0]["text"]
    assert "Leave Policy" in ans["answer"]
    # re-adding the same title replaces, not duplicates
    api.dispatch("policy_paste", {"title": "Leave Policy", "text": POLICY + "\n\n5. Hajj leave\nOnce in service, 15 days of paid Hajj leave."})
    assert len(api.dispatch("policies", {})["policies"]) == 1
    assert "Hajj" in workplace.search(api.db, "hajj leave")[0]["text"]
    v = api.dispatch("policy_view", {"policy_id": r["policies"][0]["id"]})
    assert v["passages"]
    assert not api.dispatch("policy_delete", {"policy_id": v["id"]})["policies"]


def test_policy_without_library(api):
    assert "No policies" in api.dispatch("policy_ask", {"question": "leave?", "ai": False})["answer"]
    assert "no readable text" in api.dispatch("policy_paste", {"title": "x", "text": "too short"})["error"]


def test_notes_create_follow_up_actions(api):
    r = api.dispatch("meeting_add", {"subject": "Example Leader 01", "subject_key": "k1", "store": "LAH Fortress", "body": "Talked about rota",
                                  "follow_up": "Share new rota", "follow_due": "2026-11-15", "mood": 4})
    assert r["rows"][0]["action_id"] and r["open_follow_ups"] == 1
    acts = api.dispatch("actions", {})["rows"]
    assert acts[0]["title"] == "Share new rota" and acts[0]["owner"] == "Example Leader 01"
    assert len(r["overdue_1to1"]) >= 1
    assert api.dispatch("meetings", {"subject_key": "k1"})["rows"]
    r = api.dispatch("meeting_delete", {"note_id": r["rows"][0]["id"]})
    assert not r["rows"]


def test_goals_progress_and_state(api):
    start = (date.today() - timedelta(days=50)).isoformat()
    g = api.dispatch("goal_add", {"title": "Cut leavers", "baseline": 10, "target": 4, "due": (date.today() + timedelta(days=50)).isoformat(), "store": "LAH Fortress"})
    row = g["rows"][0]
    assert row["progress"] == 0
    api.db.x("UPDATE goals SET created_at=? WHERE id=?", (start, row["id"]))
    g = api.dispatch("goal_update", {"goal_id": row["id"], "value": 7, "note": "Better rota"})
    row = g["rows"][0]
    assert row["progress"] == 50.0 and row["state"] == "on track" and row["history"][-1]["note"] == "Better rota"
    g = api.dispatch("goal_update", {"goal_id": row["id"], "value": 4})
    assert g["rows"][0]["state"] == "achieved"
    g = api.dispatch("goal_update", {"goal_id": row["id"], "value": 9})
    assert g["rows"][0]["state"] in ("at risk", "off track")
    assert not api.dispatch("goal_delete", {"goal_id": row["id"]})["rows"]
    assert g["templates"]


def test_manager_effectiveness(api):
    m = api.dispatch("managers", {})
    assert m["rows"]
    for r in m["rows"]:
        assert 0 <= r["score"] <= 100 and r["team"] >= 2 and r["band"] in ("Strong", "Steady", "Needs support")
    assert [r["score"] for r in m["rows"]] == sorted([r["score"] for r in m["rows"]], reverse=True)


def test_assistant_routes(api):
    from pno.agent import basic
    from pno.agent.tools import Toolbox
    tb = Toolbox(api.agent, "2026-09", {}, False)
    assert "No policies" in basic.answer(tb, "What does the leave policy say?")
    api.dispatch("policy_paste", {"title": "Leave Policy", "text": POLICY})
    assert "8 days" in basic.answer(tb, "How many days of sick leave do we get?")
    assert "No goals" in basic.answer(tb, "Are our goals on track?")
    api.dispatch("goal_add", {"title": "Cut leavers", "baseline": 10, "target": 4})
    assert "Cut leavers" in basic.answer(tb, "Which goals are off track?")
    assert "Manager effectiveness" in basic.answer(tb, "Which managers need support?")
    assert tb.t_hr_policy("maternity")["found"]
