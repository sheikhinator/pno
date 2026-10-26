"""The P&O screens in Chromium with the fictional workbook: switch between latest, MTD and YTD on every screen."""

from __future__ import annotations

import os
import threading
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_e2e_ui import CHROME  # noqa: E402


def test_period_bar_on_every_po_screen(tmp_path):
    os.environ["PNO_HOME"] = str(tmp_path / "data")
    from po_fixture import make_po_workbook

    from pno import importers
    from pno.db import Database
    from pno.devserver import make_server
    db = Database(tmp_path / "pno.sqlite3")
    a = importers.analyze_path(make_po_workbook(tmp_path / "po.xlsx"))
    out = importers.commit(db, a, {"*": {"as_of": "2026-09-30", "period_to": "2026-09"}})
    assert all(r["status"] == "ok" for r in out), out
    srv = make_server(db, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errors: list[str] = []
    try:
        with pw.sync_playwright() as p:
            try:
                browser = p.chromium.launch(executable_path=CHROME) if CHROME else p.chromium.launch()
            except Exception as e:  # no browser on this machine
                pytest.skip(f"Chromium not available: {e}")
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "favicon" not in m.text else None)
            page.goto(f"http://127.0.0.1:{srv.server_address[1]}/web/index.html")
            page.wait_for_function("window.PNO_ready === true", timeout=30000)

            def settle():
                time.sleep(0.5)
                page.wait_for_function("!document.querySelector('.page .loading')", timeout=20000)
                assert not page.locator(".errbox").count(), page.locator(".errbox").first.inner_text()

            for screen in ["review", "talent", "retention", "shifts", "nps"]:
                page.evaluate(f"go('{screen}')")
                settle()
                assert page.locator(".pbar").count() == 1, screen
                page.locator("[data-act=pv-type][data-t=ytd]").click()
                settle()
                assert "YTD" in page.locator(".pcov>summary").inner_text()
                page.locator(".pcov>summary").click()
                assert page.locator(".pcov-box tr").count() > 3
                page.locator(".pcov>summary").click()
                page.locator("[data-act=pv-type][data-t=mtd]").click()
                settle()
                months = page.locator("select[data-pv=to] option").all_inner_texts()
                assert months, screen
                page.select_option("select[data-pv=to]", index=0)
                settle()
                page.locator("[data-act=pv-type][data-t=latest]").click()
                settle()
            # data health: checklist, checks, dictionary, lock and unlock
            page.evaluate("go('health')")
            settle()
            assert page.locator(".hrow").count() >= 10
            page.locator(".hdict>summary").click()
            page.locator("[data-act=h-lock]").click()
            settle()
            assert "Locked" in page.locator("[data-act=h-lock]").inner_text()
            page.locator("[data-act=h-lock]").click()
            settle()
            # hiring: create a vacancy, then every tab
            page.evaluate("go('hiring')")
            settle()
            page.locator("[data-act=h-new]").first.click()
            time.sleep(0.6)
            page.fill("#hv-title", "Team Leader Bakery")
            page.select_option("#hv-role", "team_leader")
            page.locator("[data-act=h-draft]").click()
            time.sleep(0.6)
            assert "Team Leader" in page.locator("#hv-jd").input_value()
            page.locator("[data-act=h-save]").click()
            settle()
            assert page.locator("#hdrop").count() == 1
            page.locator("[data-act=h-edit]").click()
            time.sleep(0.5)
            page.keyboard.press("Escape")
            for tab in ("pipe", "bank", "stats", "vac"):
                page.locator(f"[data-act=h-tab][data-tab={tab}]").click()
                settle()
            # learning studio: make a course, read, quiz, assign, tabs
            page.evaluate("go('learning')")
            settle()
            page.locator("[data-act=l-new]").first.click()
            time.sleep(0.5)
            page.fill("#lf-hours", "2")
            page.locator("[data-act=l-build]").click()
            settle()
            assert page.locator(".ltoc-l").count() > 3 and page.locator(".lbody").count() == 1
            page.locator("[data-act=l-step][data-d='1']").click()
            settle()
            page.locator("[data-act=l-quiz]").first.click()
            settle()
            if page.locator(".lopt").count():
                page.locator(".lopt").first.click()
                settle()
            page.locator("[data-act=l-people]").click()
            settle()
            page.locator("[data-act=l-back]").click()
            settle()
            for tab in ("track", "paths", "courses"):
                page.locator(f"[data-act=l-tab][data-tab={tab}]").click()
                settle()
            # 2.0: flight risk, succession, manpower, actions, today inbox
            page.evaluate("go('talent')")
            settle()
            for tab in ("risk", "succ"):
                page.locator(f"[data-act=po-tab][data-tab={tab}]").click()
                settle()
            page.evaluate("go('manpower')")
            settle()
            page.evaluate("go('actions')")
            settle()
            page.locator("[data-act=act-new]").click()
            time.sleep(0.4)
            page.fill("#af-title", "Check the bakery rota")
            page.locator("#af-save").click()
            settle()
            assert "Check the bakery rota" in page.locator(".page").inner_text()
            page.evaluate("go('home')")
            settle()
            time.sleep(1)
            # command palette and table export
            page.locator("#q").click()
            page.keyboard.type(">data health")
            time.sleep(0.6)
            page.keyboard.press("Enter")
            settle()
            assert page.locator(".hrow").count() >= 10
            page.evaluate("go('review')")
            settle()
            assert page.locator(".tx").count() >= 1
            page.locator(".tx").first.click()
            time.sleep(0.4)
            assert page.locator(".txf").count() == 3
            page.keyboard.press("Escape")
            page.evaluate("go('import')")
            settle()
            browser.close()
    finally:
        srv.shutdown()
    assert not errors, errors
