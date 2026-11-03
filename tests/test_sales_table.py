"""4.2.5: the flat YTD sales table (Department · Section · Code · Store Type · Store Short Name · Budget · Net Sales)."""
import subprocess
import sys
from pathlib import Path

from pno import importers
from pno.api import Api, specific_key
from pno.db import Database


def _file(tmp_path):
    p = tmp_path / "Sales YTD Sep.xlsx"
    subprocess.run([sys.executable, str(Path(__file__).with_name("make_sales_table.py")), str(p)], check=True)
    return p


def test_read_as_sales(tmp_path):
    (r,) = importers.analyze_path(_file(tmp_path))["results"]
    assert r.kind == "sales" and r.confidence >= 0.9
    sec = [x for x in r.rows if x["level"] == "section"]
    assert {x["store_raw"] for x in sec} >= {"LAH Fortress", "KCH Lucky One", "LAH Askari 10"}       # '651 LAH Fortress' → 'LAH Fortress'
    assert all(x["code"].startswith(("S", "X")) and x["period"] == "YTD" for x in sec)
    assert any(x["level"] == "store" and x["store_raw"] == "LAH Fortress" for x in r.rows)           # totals added up
    assert not any(x["store_raw"] in ("", None) for x in r.rows)                                      # subtotal lines skipped


def test_generic_sheet_names_never_remembered(tmp_path, monkeypatch):
    assert specific_key("Sheet1") == "" and specific_key("YTD") == "" and specific_key("Data") == ""
    assert specific_key("Out of Stock and Stock Days YTDSEP") != ""
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    api = Api(Database(tmp_path / "p.sqlite3"))
    api.db.set_setting("import_templates", {"sheet": {"kind": "productivity"}, "": {"kind": "productivity"},
                                            specific_key("Sales YTD Sep"): {"kind": "productivity"}})
    a = api.dispatch("import_analyze", {"paths": [str(_file(tmp_path))], "month": "ytd:2026-09"})
    r = a["files"][0]["results"][0]
    assert r["kind"] == "sales" and not r.get("kind_hint")                                           # a sure reader wins
    c = api.dispatch("import_commit", {"token": a["token"], "options": {}})
    assert c["done"][0]["results"][0]["kind"] == "sales"
    assert next(t for t in api.api_review()["tiles"] if t["key"] == "sales")["value"] is not None
