"""2.8: people insights on the demo data."""
from pno.api import Api, load_demo
from pno.db import Database
from pno import people_insights as pi


def test_insights_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "p.sqlite3"); load_demo(db); api = Api(db); api.dispatch("init", {})
    r = api.dispatch("people_insights", {})
    assert r["absence"]["available"] and len(r["absence"]["by_weekday"]) == 7
    assert all(x["bradford"] == x["spells"] ** 2 * x["days"] for x in r["absence"]["bradford"])
    for row in r["gender"]["rows"]:
        assert row["women_pct"] is None or row["n"] >= pi.MIN_GROUP
    assert "drivers" in r["drivers"]
    assert pi.band("Store Manager") == "Store leadership" and pi.band("Cashier") == "Staff"


def test_pearson():
    assert round(pi._pearson([1, 2, 3, 4, 5, 6], [2, 4, 6, 8, 10, 12]), 3) == 1.0
    assert pi._pearson([1, 2, 3], [1, 2, 3]) is None
