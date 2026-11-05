"""5.0: click through every screen of the app (Review, Hiring, Learning, Ask P&O AI, Data, Settings) on the demo data in
Chromium, failing on any JavaScript error, error toast or error box.

Runs when Playwright and a Chromium are available (CI and development); skipped otherwise.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

CHROME = next((p for p in [os.environ.get("PNO_CHROMIUM"), "/opt/pw-browsers/chromium", shutil.which("chromium"),
                           shutil.which("chrome"), shutil.which("google-chrome")] if p and Path(p).exists()), None)

SALES = ("Department\tSection\tCode\tStore Type\tStore Short Name\tBudget\tNet Sales\n"
         "Consumer Goods\tCGD - Beverages\tS011\tHypermarket\t651 LAH Fortress\t462,300,119\t917,679,535\n"
         "Consumer Goods\tCGD - Beverages\tS011\tHypermarket\t654 KCH Lucky One\t909,098,806\t1,255,593,961\n"
         "Consumer Goods\tCGD - Beverages\t\t\t\t1,371,398,925\t2,173,273,496\n"
         "Fresh Food\tFFD - Bakery\tS054\tHypermarket\t651 LAH Fortress\t250,125,343\t256,186,030\n"
         "Fresh Food\tFFD - Bakery\tS054\tHypermarket\t654 KCH Lucky One\t238,567,878\t222,499,111\n")


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    os.environ["PNO_HOME"] = str(home / "data")
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    from pno.api import Api, load_demo
    from pno.db import Database
    from pno.devserver import make_server
    db = Database(home / "pno.sqlite3")
    load_demo(db)
    api = Api(db)
    api.dispatch("hire_save", {"title": "Department Head · Consumer Goods", "role": "department_head", "store": "LAH Packages Mall",
                               "department": "Consumer Goods"})
    srv = make_server(db, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/web/index.html", srv, home
    srv.shutdown()


def test_click_everything(app):
    url, srv, home = app
    errors: list[str] = []
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=CHROME) if CHROME else p.chromium.launch()
        except Exception as e:  # no browser on this machine
            pytest.skip(f"Chromium not available: {e}")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" and "favicon" not in m.text
                and "404" not in m.text else None)

        def settle(t=0.5):
            time.sleep(t)
            page.wait_for_function("!document.querySelector('.page .loading')", timeout=20000)
            bad = page.locator(".toast.err").all_inner_texts()
            if bad:
                errors.append("toast: " + " | ".join(bad))
                page.evaluate("document.querySelectorAll('.toast.err').forEach(t=>t.remove())")
            assert not page.locator(".errbox").count(), page.locator(".errbox").first.inner_text()

        def nav(k):
            page.locator(f".side nav [data-go={k}]").click()
            settle(0.8)
            assert page.evaluate("window.PNO_state.page") == k

        def saved():
            page.wait_for_selector(".toast >> text=saved", timeout=30000)
            page.evaluate("document.querySelectorAll('.toast').forEach(t=>t.remove())")

        page.goto(url)
        page.wait_for_function("window.PNO_ready === true", timeout=30000)
        page.wait_for_selector(".rtiles", timeout=30000)
        settle(1)

        # ---------------------------------------------------------------- sidebar
        assert [x.inner_text().strip() for x in page.locator("#nav button").all()] == ["Review", "Hiring", "Learning", "Ask P&O AI"]
        assert [x.inner_text().strip() for x in page.locator(".nav-bottom button").all()] == ["Data", "Settings"]
        page.locator("[data-act=side-mini]").click(); time.sleep(0.3)
        assert page.evaluate("document.body.classList.contains('side-mini')")
        page.locator("[data-act=side-mini]").click(); time.sleep(0.3)

        # ---------------------------------------------------------------- review
        page.locator(".rtile.click[data-k=sales]").first.click(); settle()       # a tile ranks the people on it
        page.wait_for_selector("th.sorted", timeout=20000)
        for sel in ("#rv-store", "#rv-dept", "#rv-role"):
            page.locator(sel).select_option(index=1); settle(0.7)
        page.locator("[data-act=rv-clear]").click(); settle(0.7)
        page.locator("tr[data-act=rv-drill]").first.click(); settle(0.8)
        page.locator("[data-act=rv-clear]").click(); settle(0.7)
        for b in page.locator("[data-act=pv-slot]").all()[:3]:
            b.click(); settle(0.8)
        page.locator("[data-act=rv-sort][data-k=score]").click(); settle()
        page.locator("[data-pf=score]").select_option("good"); settle()
        page.locator("[data-act=rv-pfclear]").click(); settle()
        head = page.locator(".rtable thead").last.bounding_box()["y"]
        page.locator(".rpanel .tbl-wrap").last.evaluate("e => e.scrollTop = 600"); time.sleep(0.3)
        assert abs(page.locator(".rtable thead").last.bounding_box()["y"] - head) < 2                      # headers stay frozen
        page.locator("[data-act=rv-scores]").click(); saved()
        page.locator("tr[data-act=rv-person]").first.click(); page.wait_for_selector(".pfacts", timeout=10000)
        for b in page.locator(".modal [data-act=rv-ptab]").all():
            b.click(); time.sleep(0.3)
        # what if: change this person's criteria, export it, save it for them, then put them back
        time.sleep(0.8)
        if not page.locator("#wif .wif-r").count():                                 # too few results for a score: try someone else
            page.keyboard.press("Escape"); time.sleep(0.3)
            page.locator("tr[data-act=rv-person]").nth(2).click(); page.wait_for_selector("#wif .wif-r", timeout=15000)
        page.locator("#wif .wif-r").nth(0).locator("[data-w='+']").click()
        page.locator("#wif .wif-r").nth(1).locator(".switch span").click()
        assert page.locator("#wif-new").inner_text().strip() not in ("", "—")
        page.locator("#wif-exp").click(); page.locator(".wif-pop [data-f=xlsx]").click(); saved()
        page.locator("#wif-save").click(); page.wait_for_selector(".modal .ctag", timeout=30000)
        page.wait_for_selector("#wif-std", timeout=10000); page.locator("#wif-std").click()
        page.wait_for_function("document.querySelector('.modal') && !document.querySelector('.modal .ctag')", timeout=30000)
        page.locator(".modal [data-act=rv-pscores][data-f=xlsx]").click(); saved()
        page.locator(".modal [data-act=rv-pscores][data-f=pdf]").click(); saved()
        page.locator(".modal [data-act=rv-course]").click()
        page.wait_for_function("window.PNO_state.page === 'learning'", timeout=30000); settle(1)
        nav("rv")
        page.locator("#top [data-act=rv-export]").click(); page.wait_for_selector(".xfmt", timeout=5000)
        page.locator(".xf:has(input[value=xlsx])").click()
        page.locator("#xf-go").click(); page.wait_for_selector(".toast", timeout=90000)
        page.keyboard.press("Escape"); time.sleep(0.3)
        page.locator("#top [data-act=present]").click(); time.sleep(0.4); page.keyboard.press("Escape"); time.sleep(0.3)
        page.evaluate("go('talent')"); time.sleep(0.4)
        assert page.evaluate("window.PNO_state.page") == "rv"                        # removed modules can't be reached

        # ---------------------------------------------------------------- hiring
        nav("hiring")
        page.locator("[data-act=h-open]").first.click(); settle(0.8)
        page.locator("[data-act=h-vtab][data-t=internal]").first.click(); settle(0.5)
        page.wait_for_selector(".itarget", timeout=60000)
        names = page.locator(".icand .sub").all_inner_texts()
        assert names and not any("Bakery" in n and "Section Manager" in n for n in names)                  # experience must match
        page.locator(".itarget .switch span").click(); page.wait_for_function("document.querySelector('#h-cross') && document.querySelector('#h-cross').checked", timeout=30000)
        settle(1.5)
        page.locator("[data-act=int-more]").first.click(); page.wait_for_selector(".modal", timeout=5000)
        page.keyboard.press("Escape"); time.sleep(0.3)
        page.locator("[data-act=int-add]").first.click(); settle(1)
        for t in ("pipe", "bank", "stats", "vac"):
            page.locator(f"[data-act=h-tab][data-tab={t}]").first.click(); settle(0.6)

        # ---------------------------------------------------------------- learning
        nav("learning")
        if page.locator("[data-act=l-open]").count():
            page.locator("[data-act=l-open]").first.click(); settle(0.8)

        # ---------------------------------------------------------------- ask
        nav("ask")
        page.fill("#askq", "Which stores are below budget?")
        page.locator("[data-act=ask-send]").click()
        page.wait_for_function("document.querySelector('.umsg') && document.querySelector('.amsg') && !document.querySelector('.amsg .thinking')", timeout=90000)

        # ---------------------------------------------------------------- data
        nav("import")
        for t in ("health", "import"):
            page.locator(f".datatabs [data-go={t}]").click(); settle(0.8)
        # the master sheet: pick the period, paste it, check, save; it shows on the Review
        page.locator("[data-act=m-type][data-t=mtd]").click(); settle(0.4)
        page.select_option("#m-month", index=0); settle(0.4)
        page.locator("[data-act=m-paste]").click()
        from pno import demo
        page.fill("#m-text", demo.master_tsv("2026-10", False).decode("utf-8"))
        page.locator("[data-act=m-readtext]").click()
        page.wait_for_selector("[data-act=m-save]", timeout=60000)
        assert page.locator(".mcov > div").count() == 8
        page.locator("[data-act=m-save]").click(); saved(); settle(1)
        assert page.locator("text=on the Review").count()
        page.locator("[data-act=m-show]").first.click(); settle(0.8)
        page.locator("[data-act=m-health]").first.click(); settle(1)
        assert page.evaluate("window.PNO_state.page") == "health"
        page.locator(".mcov > div.click").last.click(); settle(0.6)
        page.locator("#h-sheet").select_option(index=0); settle(0.6)
        page.locator(".datatabs [data-go=import]").click(); settle(0.8)
        n = page.evaluate("document.querySelectorAll('[data-act=imp-del]').length")
        page.locator("[data-act=imp-del]").first.click(); page.locator("#del-go").click()
        page.wait_for_selector(".toast >> text=Deleted", timeout=60000); settle(1)
        assert page.evaluate("document.querySelectorAll('[data-act=imp-del]').length") == n - 1

        # ---------------------------------------------------------------- settings
        nav("settings")
        for t in ("ai", "stores", "backups", "data", "look", "bench"):
            page.locator(f"[data-act=set-tab][data-tab={t}]").click(); settle(0.6)
        w = page.locator("tr[data-ck=sales] [data-cf=weight]")
        w.fill("40"); w.dispatch_event("input")
        page.wait_for_function("document.querySelector('#crit-state').textContent.includes('Saved')", timeout=30000)
        assert page.locator("#crit-prev table").count()
        page.locator("[data-act=tg-reset]").click(); settle()

        browser.close()
    assert not errors, errors
