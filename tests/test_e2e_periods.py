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
            # import screen: period controls follow the type chosen
            page.evaluate("go('import')")
            settle()
            browser.close()
    finally:
        srv.shutdown()
    assert not errors, errors
