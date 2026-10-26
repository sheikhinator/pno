"""2.4: training needs analysis and the workforce forecast."""

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


def test_training_needs_and_targeted_course(api):
    tn = api.dispatch("training_needs", {"threshold": 80})
    assert "error" not in tn, tn
    assert tn["rows"] and tn["topics"]
    for r in tn["rows"]:
        assert all(n["score"] < 8 and n["topic"] for n in r["needs"])
    t = tn["topics"][0]
    r = api.dispatch("training_build", {"topic": t["topic"], "hours": 2, "threshold": 80})
    assert "error" not in r, r
    assert r["assigned"] == t["n"]
    after = {x["topic"]: x for x in r["topics"]}
    assert t["topic"] not in after                     # everyone who needed it now has it assigned
    assert any(n["status"] == "assigned" for row in r["rows"] for n in row["needs"] if n["topic"] == t["topic"])
    assert "error" in api.dispatch("training_build", {"topic": t["topic"], "threshold": 80})


def test_forecast_scenarios(api):
    f = api.dispatch("forecast", {"months": 6})
    assert "error" not in f, f
    b = f["baseline"]
    assert b["headcount"] > 0 and len(f["labels"]) == 6 and f["labels"][0] > "2026-09"
    assert f["series"]["today"] == [b["headcount"]] * 6               # replacing leavers keeps headcount flat
    g = api.dispatch("forecast", {"months": 6, "turnover_change": -25, "hires_per_month": 0, "replacement_cost": 50000})
    assert g["leavers"]["scenario"] <= g["leavers"]["today"]
    assert g["cost"]["saving"] == round(b["leavers_per_month"] * 0.25 * 6 * 50000)
    if b["leavers_per_month"]:
        assert g["series"]["scenario"][-1] < b["headcount"]
    h = api.dispatch("forecast", {"months": 3, "growth_heads": 30})
    assert h["series"]["target"][-1] == b["headcount"] + 30


def test_empty_database(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    api = Api(Database(tmp_path / "e.sqlite3"))
    assert api.dispatch("training_needs", {})["rows"] == []
    f = api.dispatch("forecast", {})
    assert "error" not in f, f
