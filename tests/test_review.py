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
    assert review.status("leavers", 5, t) == "neutral"
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
            assert [x.inner_text().strip() for x in pg.locator("#nav button").all()] == ["Review", "Ask P&O AI"]
            pg.locator("[data-act=rv-dept][data-v='Consumer Goods']").click(); pg.wait_for_selector("text=Country · CG", timeout=10000)
            pg.locator("[data-act=rv-role][data-v=dept]").click(); time.sleep(0.6)
            pg.locator("tr[data-act=rv-person]").first.click(); pg.wait_for_selector(".pfacts", timeout=10000)
            pg.keyboard.press("Escape"); time.sleep(0.3)
            pg.locator("[data-act=rv-role][data-v='']").click(); time.sleep(0.5)
            pg.locator("tr[data-act=rv-drill]").first.click(); time.sleep(0.8)
            assert "sections" in pg.locator(".rpanel").first.inner_text().lower() or pg.locator("[data-act=rv-crumb]").count() >= 1
            pg.locator("[data-act=rv-sort][data-k=score]").click(); time.sleep(0.4)
            pg.evaluate("go('hiring')"); time.sleep(0.5)
            assert pg.evaluate("window.PNO_state.page") == "rv"                      # hidden modules can't be reached
            pg.locator("#top [data-act=present]").click(); time.sleep(0.4); pg.keyboard.press("Escape")
            pg.locator("[data-go=ask]").click(); pg.wait_for_selector("#askq", timeout=10000)
            assert not errs, errs
            b.close()
    finally:
        srv.shutdown()
