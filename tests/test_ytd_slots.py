"""4.2.2: one year-to-date load, then months one by one."""
import pathlib
from pno.api import Api
from pno.db import Database


def _api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    return Api(Database(tmp_path / "p.sqlite3"))


def _file(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_ytd_then_months(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    ytd = _file(tmp_path, "Store sales.csv", "Store,Net Sales,Budget,LY\nLAH Fortress,900,950,800\nKCH Lucky One,1800,1700,1600\n")
    a = api.dispatch("import_analyze", {"paths": [ytd], "month": "ytd:2026-09"})
    r = a["files"][0]["results"][0]
    assert r["period"]["type"] == "ytd" and r["period"]["from"] == "2026-01" and r["period"]["to"] == "2026-09"
    api.dispatch("import_commit", {"token": a["token"], "options": {}})
    cal = api.dispatch("import_calendar", {"year": 2026})
    assert cal["baseline"] == "2026-09" and cal["months"][0]["ytd"] and [m["short"] for m in cal["months"][1:]] == ["Oct", "Nov", "Dec"]
    oct_ = _file(tmp_path, "Store sales Oct.csv", "Store,Net Sales,Budget,LY\nLAH Fortress,100,110,90\nKCH Lucky One,200,190,180\n")
    a = api.dispatch("import_analyze", {"paths": [oct_], "month": "2026-10"})
    r = a["files"][0]["results"][0]
    assert r["period"]["type"] == "mtd" and r["period"]["to"] == "2026-10"          # the YTD load isn't remembered for later months
    api.dispatch("import_commit", {"token": a["token"], "options": {}})
    labels = [s["label"] for s in api.api_review()["period"]["slots"]]
    assert labels == ["Jan 2026–Sep 2026 (YTD)", "Oct 2026"]
    api.dispatch("ytd_baseline", {"month": "2026-08"})
    assert api.dispatch("import_calendar", {"year": 2026})["months"][0]["end"] == "2026-08"


def test_first_quick_load_is_ytd(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    f = _file(tmp_path, "YTD Sales SEP.csv", "Store,Net Sales,Budget,LY\nLAH Fortress,900,950,800\nKCH Lucky One,1800,1700,1600\n")
    a = api.dispatch("import_analyze", {"paths": [f]})
    assert a["slot"] == "ytd" and a["files"][0]["results"][0]["period"]["type"] == "ytd"


def test_ytd_slot_survives_older_data_and_reimports(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    f = _file(tmp_path, "Store sales.csv", "Store,Net Sales,Budget,LY\nLAH Fortress,900,950,800\nKCH Lucky One,1800,1700,1600\n")
    api.db.set_setting("ytd_baseline", None)
    a = api.dispatch("import_analyze", {"paths": [f], "month": "2026-09"})        # loaded month-style, as before 4.2.2
    api.dispatch("import_commit", {"token": a["token"], "options": {}})
    api.db.set_setting("ytd_baseline", None)
    cal = api.dispatch("import_calendar", {"year": 2026})
    assert cal["months"][0].get("ytd") and cal["months"][0]["end"] == "2026-09"
    a = api.dispatch("import_analyze", {"paths": [f]})                             # re-import through Update data
    api.dispatch("import_commit", {"token": a["token"], "options": {}})
    assert api.dispatch("import_calendar", {"year": 2026})["months"][0].get("ytd")
    assert [s["label"] for s in api.api_review()["period"]["slots"]] == ["Jan 2026–Sep 2026 (YTD)"]
