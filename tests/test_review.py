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
            assert [x.inner_text().strip() for x in pg.locator("#nav button").all()] == ["Review", "Hiring", "Learning", "Ask P&O AI"]
            assert [x.inner_text().strip() for x in pg.locator(".nav-bottom button").all()] == ["Data", "Settings"]
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
            heads = [x.inner_text().strip() for x in pg.locator(".rtable").last.locator("thead tr").first.locator("th").all()]
            assert heads[0].lower() == "person" and heads[1].lower().startswith("score")                 # score sits next to the name
            n0 = pg.locator("tr[data-act=rv-person]").count()
            pg.locator("[data-pf=score]").select_option("good"); time.sleep(0.6)
            assert pg.locator("tr[data-act=rv-person]").count() <= n0
            pg.locator("[data-act=rv-pfclear]").click(); time.sleep(0.5)
            assert pg.locator("tr[data-act=rv-person]").count() == n0
            pg.locator("[data-act=rv-course]").first.click()
            pg.wait_for_function("window.PNO_state.page === 'learning'", timeout=20000); time.sleep(1)
            assert pg.locator(".page").inner_text().count("Development course") >= 1
            pg.locator("#nav [data-go=rv]").click(); pg.wait_for_selector(".rtiles", timeout=10000)
            pg.locator("#top [data-act=rv-export]").click(); pg.wait_for_selector(".xfmt", timeout=5000); pg.keyboard.press("Escape"); time.sleep(0.3)
            pg.evaluate("go('talent')"); time.sleep(0.5)
            assert pg.evaluate("window.PNO_state.page") == "rv"                      # removed modules can't be reached
            pg.locator("#top [data-act=present]").click(); time.sleep(0.4); pg.keyboard.press("Escape")
            pg.locator(".nav-bottom [data-go=import]").click(); pg.wait_for_selector(".datatabs", timeout=10000)
            for t in ("health", "import"):
                pg.locator(f".datatabs [data-go={t}]").click(); time.sleep(0.8)
                assert pg.evaluate("window.PNO_state.page") == t and not pg.locator(".errbox").count()
            pg.locator("[data-act=rv-settings]").click(); pg.wait_for_selector("tr[data-ck]", timeout=10000)
            pg.locator("tr[data-ck=nps] .switch span").click(); pg.wait_for_function("document.querySelector('#crit-state').textContent.includes('Saved')", timeout=15000)
            pg.locator("#nav [data-go=rv]").click(); pg.wait_for_selector(".rtiles", timeout=10000)
            assert "Customer NPS" not in pg.locator(".rtiles").inner_text()
            pg.locator(".nav-bottom [data-go=import]").click(); pg.wait_for_selector(".datatabs", timeout=10000)
            for t in ("health", "import"):
                pg.locator(f".datatabs [data-go={t}]").click(); time.sleep(0.8)
                assert pg.evaluate("window.PNO_state.page") == t and not pg.locator(".errbox").count()
            pg.locator("[data-go=ask]").click(); pg.wait_for_selector("#askq", timeout=10000)
            assert not errs, errs
            b.close()
    finally:
        srv.shutdown()


@pytest.mark.parametrize("fmt", ["pdf", "pptx", "docx", "xlsx"])
def test_review_export(api, tmp_path, fmt):
    out = tmp_path / f"review.{fmt}"
    r = api.dispatch("review_export", {"fmt": fmt, "dept": "Consumer Goods", "save_as": str(out), "open_after": False})
    assert r.get("ok") and out.stat().st_size > 5000, r
    if fmt == "pptx":
        from pptx import Presentation
        prs = Presentation(str(out))
        assert len(prs.slides) >= 6 and any(sh.has_chart for sl in prs.slides for sh in sl.shapes)


def test_course_for_person(api):
    p = api.dispatch("review", {})["people"][0]
    c = api.dispatch("learn_for_person", {"key": p["key"], "use_ai": False})
    assert c["content"]["for"]["name"] and c["content"]["modules"] and c["title"].startswith("Development course")


def test_score_colours_editable(api):
    from pno.review import targets
    api.dispatch("review_criteria", {"score": {"green": 8, "amber": 6}})
    assert targets(api.db)["score"] == {"green": 8.0, "amber": 6.0}
    with pytest.raises(Exception):
        api.api_review_criteria(score={"green": 5, "amber": 7})
    api.dispatch("review_criteria", {"reset": True})
    assert targets(api.db)["score"]["green"] == 7



def test_criteria_for_one_person(api):
    """5.1: criteria saved for one person score them everywhere (marked custom); others are untouched; Back to standard undoes it."""
    sc = lambda p: next(c["value"] for c in p["cells"] if c["key"] == "score")  # noqa: E731
    ppl = [p for p in api.dispatch("review", {})["people"] if sc(p) is not None]
    me, other = ppl[2], ppl[3]
    rows = [{"key": "sales", "weight": 60, "show": True}, {"key": "productivity", "weight": 0}, {"key": "shrink", "weight": 10},
            {"key": "nps", "weight": 10}, {"key": "leavers", "weight": 10}, {"key": "da", "weight": 5}]
    assert "error" in api.dispatch("review_person_criteria", {"key": me["key"], "rows": [{"key": "sales", "weight": 10, "green": -5, "amber": 0}]})
    api.dispatch("review_person_criteria", {"key": me["key"], "rows": rows})
    after = {p["key"]: p for p in api.dispatch("review", {})["people"]}
    assert after[me["key"]]["custom"] and after[me["key"]]["std_score"] == sc(me)
    assert not after[other["key"]]["custom"] and sc(after[other["key"]]) == sc(other)
    assert "productivity" not in {x["key"] for x in after[me["key"]]["parts"]}
    api.dispatch("review_person_criteria", {"key": me["key"], "reset": True})
    back = next(p for p in api.dispatch("review", {})["people"] if p["key"] == me["key"])
    assert not back["custom"] and sc(back) == sc(me)
