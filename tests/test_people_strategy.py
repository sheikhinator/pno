"""2.0: flight risk, succession, manpower plan, action tracker and the 'What needs you today' inbox."""

from __future__ import annotations

import pytest

from pno import actions, importers
from pno.api import Api
from pno.db import Database

from po_fixture import make_po_workbook


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "pno.sqlite3")
    a = importers.analyze_path(make_po_workbook(tmp_path / "po.xlsx"))
    out = importers.commit(db, a, {"*": {"month": "2026-09", "as_of": "2026-09-30"}})
    assert all(r["status"] == "ok" for r in out), out
    return Api(db)


def test_flight_risk_is_explained(api):
    r = api.dispatch("po_risk", {})
    assert r["has_data"] and r["risk"]
    for x in r["risk"]:
        assert 0 <= x["score"] <= 100 and x["band"] in ("High", "Medium", "Low") and x["reasons"]
    scores = [x["score"] for x in r["risk"]]
    assert scores == sorted(scores, reverse=True)


def test_succession_board(api):
    sc = api.dispatch("po_risk", {})["succession"]
    assert sc["stores"] and sc["roles"] == ["Store manager", "Department head", "Section manager"]
    assert all(c["status"] in ("Ready now", "Ready in a year", "No successor", "No one in role") for c in sc["cells"])
    assert sum(sc["summary"].values()) == len(sc["cells"])


def test_manpower_plan_matches_names(api):
    m = api.dispatch("manpower_save", {"paste": "Store\tDepartment\tApproved\nHM PK LAH Fortress\tFFD - Fresh Food\t40\nFortress\tCGD-FMCG\t25\nbad line"})
    assert m["saved"] == 2 and m["has_plan"]
    planned = {(r["store"], r["department"]): r for r in m["rows"] if r["approved"] is not None}
    assert ("LAH Fortress", "Fresh Food") in planned and ("LAH Fortress", "Consumer Goods") in planned
    r = planned[("LAH Fortress", "Fresh Food")]
    assert r["gap"] == r["actual"] - 40
    m = api.dispatch("manpower_save", {"rows": [{"store": "LAH Fortress", "department": "Fresh Food", "approved": None}]})
    assert ("LAH Fortress", "Fresh Food") not in {(r["store"], r["department"]) for r in m["rows"] if r["approved"] is not None}


def test_action_tracker(api):
    r = api.dispatch("action_add", {"title": "Fix rota", "owner": "SM", "due": "2020-01-01", "priority": "High"})
    a = r["rows"][0]
    assert a["overdue"] and r["overdue"] == 1
    r = api.dispatch("action_update", {"action_id": a["id"], "status": "done", "note": "Rota changed"})
    a = r["rows"][0]
    assert a["status"] == "done" and a["done_at"] and a["history"][-1]["note"] == "Rota changed" and r["done_30d"] == 1
    text = "Answer.\n\n### Recommended actions\n1. **Review** Lucky One rota\n2. Train bakery on markdowns\n\n### Notes\n- not an action"
    assert actions.from_text(text) == ["Review Lucky One rota", "Train bakery on markdowns"]
    assert api.dispatch("actions_from_answer", {"text": text})["added"] == 2
    api.dispatch("action_delete", {"action_id": a["id"]})
    assert len(api.dispatch("actions", {})["rows"]) == 2


def test_today_inbox(api):
    api.dispatch("action_add", {"title": "Late thing", "due": "2020-01-01"})
    t = api.dispatch("today", {})
    assert t["items"] and t["items"][0]["level"] == "bad"
    assert any(i["area"] == "Action overdue" for i in t["items"])


def test_assistant_answers_people_strategy(api):
    assert "risk of leaving" in api.dispatch("agent_ask", {"question": "Who might leave?"})["answer"]
    assert "successor" in api.dispatch("agent_ask", {"question": "Where do we have succession gaps?"})["answer"]
    assert "Basic Sheet" in api.dispatch("agent_ask", {"question": "Are we understaffed? manpower"})["answer"]
    api.dispatch("action_add", {"title": "Late", "due": "2020-01-01"})
    assert "overdue" in api.dispatch("agent_ask", {"question": "Which actions are overdue?"})["answer"]
