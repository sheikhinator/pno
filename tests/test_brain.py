"""2.7: People Brain, corrections that win over imports, profile sheets, AI routing."""

from __future__ import annotations

import pytest

from pno import importers
from pno.api import Api
from pno.db import Database

from po_fixture import make_po_workbook


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "pno.sqlite3")
    a = importers.analyze_path(make_po_workbook(tmp_path / "po.xlsx"))
    importers.commit(db, a, {"*": {"month": "2026-09", "as_of": "2026-09-30"}})
    return Api(db)


def test_brain_pages(api):
    s = api.dispatch("brain_search", {"q": ""})
    assert s["rows"] and s["people"] >= 15
    emp = s["rows"][0]["emp"]
    p = api.dispatch("brain_person", {"emp": emp})
    assert "error" not in p, p
    assert p["facts"] and all(f["source"] for f in p["facts"]) and p["timeline"] is not None
    assert set(p["insights"]) >= {"strengths", "risks", "next_steps"}
    st = api.dispatch("brain_store", {"store": p["store"]})
    assert any(r["emp"] == emp for r in st["people"])
    g = api.dispatch("brain_graph", {})
    ids = {n["id"] for n in g["nodes"]}
    assert g["nodes"] and all(e["a"] in ids and e["b"] in ids for e in g["edges"])


def test_corrections_win_and_survive_reimport(api, tmp_path):
    s = api.dispatch("brain_search", {"q": "DEMO0001"})
    emp = s["rows"][0]["emp"]
    r = api.dispatch("correction_add", {"emp": emp, "field": "designation", "value": "Section Manager", "note": "promoted in Sep"})
    assert "error" not in r, r
    assert r["person"]["designation"] == "Section Manager"
    f = next(x for x in r["person"]["facts"] if x["field"] == "designation")
    assert f.get("corrected") and f["source"] == "Corrected by P&O"
    ins = api._po()
    assert next(l for l in ins.leaders() if l.employee_id == emp).designation == "Section Manager"
    # re-import the same workbook: the correction still wins
    a = importers.analyze_path(make_po_workbook(tmp_path / "po2.xlsx"))
    importers.commit(api.db, a, {"*": {"month": "2026-10", "as_of": "2026-10-31", "replace": True}})
    assert api.dispatch("brain_person", {"emp": emp})["designation"] == "Section Manager"
    # undo
    cid = api.dispatch("corrections", {})["rows"][0]["id"]
    api.dispatch("correction_undo", {"correction_id": cid})
    assert api.dispatch("brain_person", {"emp": emp})["designation"] != "Section Manager"
    assert "error" in api.dispatch("correction_add", {"emp": emp, "field": "rating", "value": "9"})


def test_left_correction_removes_from_headcount(api):
    before = api._po().headcount()
    s = api.dispatch("brain_search", {"q": "DEMO0002"})
    emp = s["rows"][0]["emp"]
    api.dispatch("correction_add", {"emp": emp, "field": "status", "value": "left"})
    api.dispatch("correction_add", {"emp": emp, "field": "left_on", "value": "2026-09-15"})
    ins = api._po()
    assert ins.headcount() == before - 1
    assert any(str(r.get("employee_id")) == emp for r in ins.rows("po_turnover"))
    assert api.dispatch("brain_person", {"emp": emp})["left"]


def test_chat_correction_needs_confirm(api):
    from pno.agent import basic
    from pno.agent.tools import Toolbox
    tb = Toolbox(api.agent, "2026-09", {}, False)
    name = api.dispatch("brain_person", {"emp": api.dispatch("brain_search", {"q": "DEMO0003"})["rows"][0]["emp"]})["name"]
    a = basic.answer(tb, f"No, {name} is a Department Head, not a team leader")
    assert "Confirm" in a and tb.actions
    act = tb.actions[0]
    assert api.dispatch("brain_person", {"emp": act["items"][0]["emp"]})["designation"] != "Department Head"
    api.agent.confirm(act["id"], True)
    assert api.dispatch("brain_person", {"emp": act["items"][0]["emp"]})["designation"] == "Department Head"


def test_profile_export(api, tmp_path):
    emp = api.dispatch("brain_search", {"q": "DEMO0001"})["rows"][0]["emp"]
    for fmt in ("pdf", "docx"):
        out = tmp_path / f"p.{fmt}"
        r = api.dispatch("profile_export", {"emp": emp, "fmt": fmt, "save_as": str(out), "open_after": False})
        assert "error" not in r, r
        assert out.stat().st_size > 3000


def test_ai_routes(api):
    r = api.dispatch("agent_settings", {"routes": {"learning": "gemini", "chat": "offline", "bogus": "groq"}})
    st = api.dispatch("agent_status", {})
    t = {x["id"]: x["engine"] for x in st["tasks"]}
    assert t["learning"] == "gemini" and t["chat"] == "offline" and "bogus" not in t
    c = api.agent._cfg()
    assert api.agent._for_task(c, "learning")["mode"] == "gemini" and api.agent._for_task(c, "policy")["mode"] == c["mode"]
    api.dispatch("agent_settings", {"routes": {"learning": "auto"}})
    assert {x["id"]: x["engine"] for x in api.dispatch("agent_status", {})["tasks"]}["learning"] == "auto"
