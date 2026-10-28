"""4.0: the Review screen (the only screen besides Ask) and its numbers."""
import os
import threading
import time

import pytest

from pno.api import Api, load_demo
from pno.db import Database
from pno import review


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    home = tmp_path_factory.mktemp("rv")
    os.environ["PNO_HOME"] = str(home / "data")
    db = Database(home / "pno.sqlite3"); load_demo(db)
    a = Api(db); a.dispatch("init", {})
    return a


def test_slices(api):
    c = api.dispatch("review", {})
    assert not c.get("error") and c["grid_kind"] == "stores" and c["tiles"] and c["people"]
    cg = api.dispatch("review", {"dept": "Consumer Goods"})
    assert cg["grid_kind"] == "stores" and all(p["level"] < 5 for p in cg["people"])          # store managers aren't CG people
    st = c["options"]["stores"][0]
    s = api.dispatch("review", {"store": st})
    assert s["grid_kind"] == "departments" and all(p["store"] == st for p in s["people"])
    ff = api.dispatch("review", {"store": st, "dept": "Fresh Food"})
    assert ff["grid_kind"] == "sections" and {g["name"] for g in ff["grid"]} <= set(review.sections_of("Fresh Food"))
    dh = api.dispatch("review", {"dept": "Consumer Goods", "role": "dept"})
    assert dh["people"] and all(p["level"] == 4 for p in dh["people"])
    for v in (c, cg, s, ff, dh):
        for n in ("strong", "weak", "focus"):
            assert v["notes"][n]


def test_people_not_ranked_and_match_grid(api):
    st = api.dispatch("review", {})["options"]["stores"][0]
    v = api.dispatch("review", {"store": st, "dept": "Fresh Food"})
    stores = [p["store"] for p in v["people"]]
    assert stores == sorted(stores, key=lambda s: v["options"]["stores"].index(s))                 # store order, not score order
    for p in v["people"]:
        assert "rank" not in p
    head = next((p for p in v["people"] if p["level"] == 4), None)
    if head:                                                                                        # a department head shows the department's own numbers
        tile = {t["key"]: t["value"] for t in v["tiles"]}
        cell = {c["key"]: c["value"] for c in head["cells"]}
        for k in ("sales", "shrink", "oos"):
            if tile.get(k) is not None and cell.get(k) is not None:
                assert abs(tile[k] - cell[k]) < 0.05, k


def test_status_and_targets(api):
    t = review.targets(api.db)
    assert review.status("attendance", 96, t) == "good" and review.status("attendance", 91, t) == "warn" and review.status("attendance", 80, t) == "bad"
    assert review.status("oos", 2, t) == "good" and review.status("oos", 9, t) == "bad"
    assert review.status("leavers", 5, t) == "bad"                     # per person; unit totals are shown uncoloured
    api.dispatch("review_targets", {"targets": {"attendance": {"green": 98, "amber": 96}}})
    assert review.status("attendance", 96.5, review.targets(api.db)) == "warn"
    api.dispatch("review_targets", {"reset": True})


def test_person_sheet(api):
    p = api.dispatch("review", {})["people"][0]
    s = api.dispatch("review_person", {"emp": p["emp"], "key": p["key"]})
    assert s["row"]["name"] == p["name"] and s["facts"]["Store"] == p["store"] and "peer_median" in s


def test_assistant_uses_review(api):
    a = api.dispatch("agent_ask", {"question": "How is CG doing at country level?"})["answer"]
    assert "Country · CG" in a and "What's strong" in a
    a = api.dispatch("agent_ask", {"question": "Compare Fortress and Emporium"})["answer"]
    assert " vs " in a and "|" in a


def test_two_tab_app(api):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from pno.devserver import make_server
    srv = make_server(api.db, 0); threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1366, "height": 860})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/web/index.html"); pg.wait_for_function("window.PNO_ready === true", timeout=60000)
            pg.wait_for_selector(".rtiles", timeout=20000)
            assert [x.inner_text().strip() for x in pg.locator("#nav button").all()] == ["Review", "Ask P&O AI", "Data"]
            pg.select_option("#rv-dept", "Consumer Goods"); pg.wait_for_selector("text=Country · CG", timeout=10000)
            pg.select_option("#rv-role", "dept"); time.sleep(0.6)
            pg.locator("tr[data-act=rv-person]").first.click(); pg.wait_for_selector(".pfacts", timeout=10000)
            pg.keyboard.press("Escape"); time.sleep(0.3)
            pg.select_option("#rv-role", ""); time.sleep(0.5)
            pg.select_option("#rv-sec", "Grocery"); time.sleep(0.6)
            assert "Grocery" in pg.locator(".rhead h1").inner_text()
            pg.locator("[data-act=rv-clear]").click(); time.sleep(0.6)
            pg.select_option("#rv-sec", "Bakery"); time.sleep(0.6)
            assert "Fresh Food" in pg.locator(".rhead h1").inner_text()             # a section sets its department
            pg.locator("[data-act=rv-clear]").click(); time.sleep(0.6)
            pg.locator("tr[data-act=rv-drill]").first.click(); time.sleep(0.8)
            assert "sections" in pg.locator(".rpanel").first.inner_text().lower() or pg.locator("[data-act=rv-crumb]").count() >= 1
            pg.locator("[data-act=rv-sort][data-k=score]").click(); time.sleep(0.4)
            pg.evaluate("go('hiring')"); time.sleep(0.5)
            assert pg.evaluate("window.PNO_state.page") == "rv"                      # hidden modules can't be reached
            pg.locator("#top [data-act=present]").click(); time.sleep(0.4); pg.keyboard.press("Escape")
            pg.locator("#nav [data-go=import]").click(); pg.wait_for_selector(".datatabs", timeout=10000)
            for t in ("health", "brain", "import"):
                pg.locator(f".datatabs [data-go={t}]").click(); time.sleep(0.8)
                assert pg.evaluate("window.PNO_state.page") == t and not pg.locator(".errbox").count()
            pg.locator("[data-act=rv-settings]").click(); pg.wait_for_selector("tr[data-ck]", timeout=10000)
            pg.locator("tr[data-ck=nps] .switch span").click(); pg.locator("[data-act=crit-save]").click(); time.sleep(0.8)
            pg.locator("#nav [data-go=rv]").click(); pg.wait_for_selector(".rtiles", timeout=10000)
            assert "Customer NPS" not in pg.locator(".rtiles").inner_text()
            pg.locator("#nav [data-go=import]").click(); pg.wait_for_selector(".datatabs", timeout=10000)
            for t in ("health", "brain", "import"):
                pg.locator(f".datatabs [data-go={t}]").click(); time.sleep(0.8)
                assert pg.evaluate("window.PNO_state.page") == t and not pg.locator(".errbox").count()
            pg.locator("[data-go=ask]").click(); pg.wait_for_selector("#askq", timeout=10000)
            assert not errs, errs
            b.close()
    finally:
        srv.shutdown()


def test_criteria_and_score(api):
    from pno.review import points, config, targets
    t = targets(api.db)
    assert points("attendance", 90, t) == 5 and points("attendance", 95, t) == 7 and points("attendance", 100, t) == 10
    assert points("oos", 3, t) == 7 and points("oos", 6, t) == 5
    rows = api.dispatch("review_criteria", {})["rows"]
    assert {r["key"] for r in rows} >= {"sales", "oos", "attendance", "rating"} and abs(sum(r["share"] for r in rows) - 100) <= 3
    before = api.dispatch("review", {})["people"][0]
    w = [{"key": r["key"], "show": r["key"] != "nps", "weight": (100 if r["key"] == "sales" else 0), "green": r["green"], "amber": r["amber"]} for r in rows]
    api.dispatch("review_criteria", {"rows": w})
    v = api.dispatch("review", {})
    assert all(t["key"] != "nps" for t in v["tiles"])
    p = next(x for x in v["people"] if x["key"] == before["key"])
    sales = next(c for c in p["cells"] if c["key"] == "sales")["value"]
    score = next(c for c in p["cells"] if c["key"] == "score")["value"]
    assert score is None or abs(score - points("sales", sales, targets(api.db))) < 0.11       # only sales counts now
    with pytest.raises(Exception):
        api.api_review_criteria(rows=[{"key": "attendance", "show": True, "weight": 10, "green": 90, "amber": 95}])
    api.dispatch("review_criteria", {"reset": True})
    assert config(api.db)["nps"]["show"] is True


def test_person_record(api):
    p = api.dispatch("review", {})["people"][0]
    s = api.dispatch("review_person", {"emp": p["emp"], "key": p["key"]})
    assert s["record"] and s["record"]["facts"] and "timeline" in s["record"]
    assert s["components"] and all("share" in c for c in s["components"])
