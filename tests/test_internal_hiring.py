"""2.6: internal talent first, with backfill and the chain of moves a promotion sets off."""

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


def vac(api, role, store="LAH Fortress", section=""):
    v = api.dispatch("hire_save", {"title": role.replace("_", " ").title(), "role": role, "store": store, "section": section})
    return v.get("id") or v["vacancy"]["id"] if isinstance(v, dict) and ("id" in v or "vacancy" in v) else v


def _vid(api, role, store="LAH Fortress", section=""):
    api.dispatch("hire_save", {"title": role.replace("_", " ").title(), "role": role, "store": store, "section": section})
    return api.db.q1("SELECT MAX(id) FROM vacancies")[0]


def test_internal_candidates_with_backfill(api):
    vid = _vid(api, "section_manager", "LAH Fortress", "Bakery")
    r = api.dispatch("hire_internal", {"vacancy_id": vid})
    assert "error" not in r, r
    assert r["candidates"] and r["verdict"]["decision"] in ("internal", "internal_backfill", "develop", "external")
    recs = [c["recommend"] for c in r["candidates"]]
    assert recs == sorted(recs, reverse=True)
    for c in r["candidates"]:
        assert 0 <= c["fit"] <= 100 and len(c["parts"]) == 6 and abs(sum(p["weight"] for p in c["parts"]) - 100) < 1e-9
        bf = c["backfill"]
        assert bf["status"] in ("covered", "interim", "weak", "gap") and bf["risk"] in ("Low", "Medium", "High")
        if c["source"] == "leader":
            assert bf["steps"] and bf["steps"][-1]["how"] == "external"          # every chain ends where someone must be hired
            names = [s["by"] for s in bf["steps"] if s["by"]]
            assert c["name"] not in names and len(names) == len(set(names))     # nobody fills two seats, nobody replaces themselves
        assert not (c["move"] != "Promotion" and c["store"] == "LAH Fortress")  # a same-level person in the same store is not a 'move'


def test_gap_lowers_the_recommendation(api):
    vid = _vid(api, "department_head", "LAH Fortress", "Fresh Food")
    r = api.dispatch("hire_internal", {"vacancy_id": vid})
    for c in r["candidates"]:
        if c["backfill"]["status"] == "gap" and c["level"] >= 4:
            assert c["recommend"] < c["fit"] + 5


def test_entry_level_is_external(api):
    vid = _vid(api, "associate", "LAH Fortress", "Bakery")
    r = api.dispatch("hire_internal", {"vacancy_id": vid})
    assert r["verdict"]["decision"] == "external" and not r["candidates"]


def test_shortlist_internal_into_pipeline(api):
    vid = _vid(api, "section_manager", "LAH Fortress", "Bakery")
    r = api.dispatch("hire_internal", {"vacancy_id": vid})
    c = r["candidates"][0]
    r2 = api.dispatch("hire_internal_add", {"vacancy_id": vid, "key": c["key"]})
    assert next(x for x in r2["candidates"] if x["key"] == c["key"])["in_pipeline"]
    v = api.dispatch("hire_vacancy", {"vacancy_id": vid})
    app = next(a for a in v["apps"] if a["source"] == "Internal")
    assert app["score"] == c["fit"]
    api.hiring.rescore(vid)                                   # CV rescoring must not overwrite an internal candidate's score
    v = api.dispatch("hire_vacancy", {"vacancy_id": vid})
    assert next(a for a in v["apps"] if a["source"] == "Internal")["score"] == c["fit"]
    api.dispatch("hire_internal_add", {"vacancy_id": vid, "key": c["key"]})
    assert api.db.q1("SELECT COUNT(*) FROM candidates WHERE source='Internal'")[0] == 1


def test_assistant_internal_question(api):
    from pno.agent import basic
    from pno.agent.tools import Toolbox
    tb = Toolbox(api.agent, "2026-09", {}, False)
    a = basic.answer(tb, "Who could be the next section manager for Bakery at Fortress?")
    assert "Internal talent first" in a and ("|" in a or "Hire from outside" in a)


def test_candidates_match_experience_and_format(tmp_path, monkeypatch):
    """5.0: a CG department head comes from CG (or a supermarket deputy), never a bakery section manager; a hypermarket
    store manager can be a supermarket store manager or a strong department head; a supermarket seat never takes a hyper SM."""
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    from pno.api import Api, load_demo
    from pno.db import Database
    db = Database(tmp_path / "d.sqlite3")
    load_demo(db)
    api = Api(db)

    def cands(**v):
        r = api.dispatch("hire_save", {"title": "x", **v})
        vid = r.get("id") or r.get("vacancy", {}).get("id")
        return api.dispatch("hire_internal", {"vacancy_id": vid})["candidates"]

    dh = cands(role="department_head", store="LAH Packages Mall", department="Consumer Goods")
    assert dh and all("Consumer Goods" in (c["experience"] or "") or c["designation"] == "Deputy Manager" for c in dh)
    assert any(c["designation"] == "Deputy Manager" and c["format"] == "Supermarket" for c in dh)
    sm = cands(role="store_manager", store="LAH Emporium Mall")
    assert any(c["designation"] == "Store Manager" and c["format"] == "Supermarket" for c in sm)
    assert any(c["designation"] == "Department Head" for c in sm)
    ssm = cands(role="store_manager", fmt="Supermarket")
    assert not any(c["designation"] == "Store Manager" and c["format"] == "Hypermarket" for c in ssm)
