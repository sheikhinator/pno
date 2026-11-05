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


def test_first_quick_load_is_ytd(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    f = _file(tmp_path, "YTD Sales SEP.csv", "Store,Net Sales,Budget,LY\nLAH Fortress,900,950,800\nKCH Lucky One,1800,1700,1600\n")
    a = api.dispatch("import_analyze", {"paths": [f]})
    assert a["slot"] == "ytd" and a["files"][0]["results"][0]["period"]["type"] == "ytd"

