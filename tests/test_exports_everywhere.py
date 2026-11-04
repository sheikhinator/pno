"""Export everywhere: any table, any AI answer, every pack in Word; pins and follow-up questions."""

from __future__ import annotations

import pytest

from pno import exports
from pno.api import Api, load_demo
from pno.db import Database


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "pno.sqlite3")
    load_demo(db)
    return Api(db)


ANSWER = """**Fortress leads with 107% of budget.**

### What the data shows
- Sales are ahead in 9 of 12 stores
- Lucky One is 13% behind

| Store | Sales | vs budget |
|---|---|---|
| Fortress | 774.1 M | 107% |
| Lucky One | 516.5 M | 87% |

> **Risk:** Lucky One productivity is 9% below target.
"""


def test_answer_becomes_a_report():
    rep = exports.markdown_report("Sales", ANSWER, [{"type": "kpis", "items": [{"label": "Sales", "value": "3.59 bn"}]},
                                                    {"type": "chart", "kind": "hbar", "title": "x", "labels": ["a", "b"], "series": [{"name": "s", "values": [1, 2]}]}])
    types = [s["type"] for s in rep["sections"]]
    assert types[0] == "kpis" and "heading" in types and "table" in types and "text" in types and types[-1] == "chart"
    table = next(s for s in rep["sections"] if s["type"] == "table")
    assert table["rows"][0]["c0"] == "Fortress"


@pytest.mark.parametrize("fmt", ["pdf", "docx", "pptx", "xlsx"])
def test_answer_and_table_export(api, tmp_path, fmt):
    out = tmp_path / f"a.{fmt}"
    r = api.dispatch("export_answer", {"title": "Which stores need attention?", "text": ANSWER, "fmt": fmt, "save_as": str(out), "open_after": False})
    assert r["ok"] and out.stat().st_size > 1500
    if fmt != "pptx":
        out = tmp_path / f"t.{fmt}"
        r = api.dispatch("export_table", {"title": "Store league", "columns": ["Store", "Sales", "vs budget"],
                                          "rows": [["Fortress", "774.1", "107%"], ["Lucky One", "516.5", "87%"]], "fmt": fmt,
                                          "save_as": str(out), "open_after": False})
        assert r["ok"] and out.stat().st_size > 1500


def test_numbers_in_tables_stay_numbers_in_excel(tmp_path):
    rep = exports.table_report("T", ["Store", "Sales", "Share"], [["A", "1,200", "12%"], ["B", "800", "8%"]])
    row = rep["sections"][0]["rows"][0]
    assert row["c1"] == 1200.0 and row["c2"] == 12.0 and row["c0"] == "A"

