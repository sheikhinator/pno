"""Click through every screen and button of the real interface in Chromium (demo data), failing on any JS error.

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


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    os.environ["PNO_HOME"] = str(home / "data")
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    from pno.api import load_demo
    from pno.db import Database
    from pno.devserver import make_server
    db = Database(home / "pno.sqlite3")
    load_demo(db)
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

        def go(name):
            page.evaluate(f"go('{name}')")
            settle()

        def close_sheet():
            page.keyboard.press("Escape")
            time.sleep(0.6)

        page.goto(url)
        page.wait_for_function("window.PNO_ready === true", timeout=30000)
        settle(1)

        # ---------------------------------------------------------------- home
        assert page.locator(".kpi").count() == 5
        page.locator(".kpi").first.click()
        settle()
        assert page.locator("[data-page=people]").count()
        go("home")
        page.locator("#ch-league .hit").first.click()
        settle()
        assert page.locator(".crumbs").inner_text().count("›") >= 1
        page.locator("[data-act=scope-clear]").click()
        settle()
        page.locator("#ch-dist .hit").nth(3).click()
        settle()
        assert page.locator("[data-page=people]").count()
        go("home")
        page.locator(".plist .prow").first.click()
        page.wait_for_selector(".sheet.on .sheet-head")
        for tab in ["attendance", "history", "team", "leave", "overview"]:
            page.locator(f"[data-act=sheet-tab][data-tab={tab}]").click()
            time.sleep(0.3)
        page.locator("[data-act=sheet-tab][data-tab=leave]").click()
        page.fill("#pl-from", "2026-09-10")
        page.fill("#pl-to", "2026-09-11")
        page.locator("[data-act=pl-add]").click()
        page.wait_for_selector("[data-act=pl-del]")
        page.locator("[data-act=pl-del]").first.click()
        page.wait_for_function("!document.querySelector('[data-act=pl-del]')", timeout=15000)
        page.fill("#pn-text", "Discussed attendance")
        page.locator("[data-act=pn-add]").click()
        page.wait_for_selector("[data-act=pn-del]")
        page.locator("[data-act=pn-del]").first.click()
        time.sleep(0.3)
        page.locator(".sheet [data-act=export]").click()
        page.wait_for_selector(".modal.on")
        page.locator("#fmtseg [data-fmt=xlsx]").click()
        page.locator("#exp-go").click()
        page.wait_for_selector(".toast >> text=Saved", timeout=30000)
        close_sheet()
        settle()
        page.locator(".alert").first.click()
        settle()
        go("home")

        # ---------------------------------------------------------------- filters, month, compare
        page.select_option("select[data-scope=city]", "LAH")
        settle()
        page.select_option("select[data-scope=format]", "HM")
        settle()
        page.locator("select[data-scope=store_id]").select_option(index=1)
        settle()
        page.locator("select[data-scope=dept]").select_option(index=1)
        settle()
        assert "›" in page.locator(".crumbs").inner_text()
        page.locator("[data-act=scope-up]").first.click()
        settle()
        page.locator("[data-act=scope-clear]").click()
        settle()
        page.select_option("#month", "2026-08")
        settle()
        page.select_option("#month", "2026-09")
        settle()
        page.locator("#compare").select_option(index=1)
        settle()

        # ---------------------------------------------------------------- search
        name = page.evaluate("document.querySelector('.plist .prow b').textContent")
        page.fill("#q", name[:6])
        page.wait_for_selector(".sugg button", timeout=5000)
        page.keyboard.press("Enter")
        page.wait_for_selector(".sheet.on")
        close_sheet()

        # ---------------------------------------------------------------- people
        go("people")
        page.fill("#pq", "muhammad")
        time.sleep(0.9)
        settle()
        page.fill("#pq", "")
        time.sleep(0.9)
        settle()
        for role in ["MANAGERS", "GM", "DH", "SM", "CCO", "HBM", "STAFF", ""]:
            page.locator(f"[data-act=role][data-role='{role}']").click()
            settle(0.2)
        for b in ["excellent", "warn", ""]:
            page.locator(f"[data-act=band][data-band='{b}']").click()
            settle(0.2)
        for key in ["name", "store", "attendance", "absent", "fixes", "role", "score"]:
            page.locator(f"th[data-key={key}]").click()
            settle(0.2)
        page.locator("[data-sel]").nth(0).click()
        settle(0.2)
        page.locator("[data-sel]").nth(1).click()
        settle(0.2)
        page.locator("[data-act=compare]").click()
        page.wait_for_selector(".modal.on")
        page.locator("[data-act=clear-sel]").click()
        settle()
        page.locator("tr.click").first.click()
        page.wait_for_selector(".sheet.on")
        close_sheet()
        page.locator("[data-act=export][data-pack=people]").click()
        page.wait_for_selector(".modal.on")
        page.locator("[data-act=modal-close]").click()
        time.sleep(0.4)

        # ---------------------------------------------------------------- performance
        go("performance")
        for role in ["GM", "DH", "CCO", "HBM", "STAFF", "SM"]:
            page.locator(f"[data-act=perf-role][data-role={role}]").click()
            settle(0.3)
        page.locator("#ch-perf .hit").first.click()
        page.wait_for_selector(".sheet.on")
        close_sheet()

        # ---------------------------------------------------------------- stores
        go("stores")
        page.locator(".scard").nth(2).click()
        settle()
        assert page.locator("[data-page=store]").count()
        page.locator("[data-act=export][data-pack=store]").click()
        page.wait_for_selector(".modal.on")
        page.locator("#exp-go").click()
        page.wait_for_selector(".toast >> text=Saved", timeout=30000)
        page.locator("[data-act=focus-store]").click()
        settle(0.8)
        page.locator("[data-act=scope-clear]").click()
        settle()

        # ---------------------------------------------------------------- attendance
        go("attendance")
        for tab in ["long", "low", "store", "register", "fixes"]:
            page.locator(f"[data-act=att-tab][data-tab={tab}]").click()
            settle(0.3)
        page.locator("[data-act=export][data-pack=attendance]").click()
        page.wait_for_selector(".modal.on")
        page.locator("#fmtseg [data-fmt=pptx]").click()
        page.locator("#exp-go").click()
        page.wait_for_selector(".toast >> text=Saved", timeout=30000)

        # ---------------------------------------------------------------- org
        go("org")
        page.locator("[data-act=tree-all]").click()
        time.sleep(0.3)
        page.locator(".node[data-person]").first.click()
        page.wait_for_selector(".sheet.on")
        close_sheet()
        page.locator(".page select[data-scope=store_id]").select_option(index=2)
        settle()

        # ---------------------------------------------------------------- ask
        go("ask")
        page.locator("[data-act=ask-sugg]").first.click()
        page.wait_for_selector(".msg.a .meta", timeout=30000)
        settle()
        person = page.evaluate("Object.values(document.querySelectorAll('.msg.a table td')).map(t=>t.textContent)[1]") or ""
        page.fill("#askq", "Top 5 section managers")
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelectorAll('.msg.a .meta').length >= 2", timeout=30000)
        page.fill("#askq", "Who was absent the most this month?")
        page.locator("[data-act=ask-send]").click()
        page.wait_for_function("document.querySelectorAll('.msg.a .meta').length >= 3", timeout=30000)
        page.fill("#askq", "Add 23 September 2026 as Eid holiday")
        page.locator("[data-act=ask-send]").click()
        page.wait_for_selector("[data-act=confirm]", timeout=30000)
        page.locator("[data-act=confirm]").first.click()
        page.wait_for_selector(".chip >> text=Saved", timeout=15000)
        page.fill("#askq", "Add 24 September 2026 as Test holiday")
        page.locator("[data-act=ask-send]").click()
        page.wait_for_selector("[data-act=cancel]", timeout=30000)
        page.locator("[data-act=cancel]").first.click()
        page.wait_for_selector(".chip >> text=Cancelled", timeout=15000)
        page.locator("[data-act=ask-clear]").click()
        settle()
        assert person is not None

        # ---------------------------------------------------------------- import (upload, preview, commit, undo, redo)
        go("import")
        from pno import demo
        f = home / "MTD Productivity Oct 2026.xlsx"
        f.write_bytes(demo.productivity_xlsx(__import__("datetime").date(2026, 10, 1)))
        page.set_input_files("#filein", str(f))
        page.wait_for_selector("[data-act=import-commit]", timeout=20000)
        page.locator("[data-act=import-commit]").click()
        page.wait_for_selector("[data-act=undo]", timeout=20000)
        settle()
        page.locator("[data-act=undo]").first.click()
        settle(0.8)
        page.locator("[data-act=redo]").first.click()
        settle(0.8)
        page.locator("[data-act=paste]").click()
        page.wait_for_selector("#paste-t")
        page.fill("#paste-t", "Employee No\tEmployee Name\tLeave Type\tFrom Date\tTo Date\tStatus\n"
                  f"{srv.api.db.val('SELECT emp_no FROM roster LIMIT 1')}\tX\tSick Leave\t2026-09-03\t2026-09-04\tApproved\n")
        page.locator("#paste-go").click()
        page.wait_for_selector("[data-act=import-commit]")
        page.locator("[data-act=import-cancel]").click()
        settle()

        # ---------------------------------------------------------------- settings
        go("settings")
        page.fill("[data-w=SM][data-p=sales]", "30")
        page.locator("[data-act=weights-save]").click()
        settle(0.8)
        page.locator("[data-act=weights-reset]").click()
        settle(0.8)
        page.locator("[data-act=set-tab][data-tab=ai]").click()
        settle()
        for mode in ["basic", "offline", "groq", "auto"]:
            page.locator(f"[data-act=ai-mode][data-mode={mode}]").click()
            settle(0.4)
        page.locator("[data-act=groq-test]").click()
        time.sleep(0.8)
        page.evaluate("document.querySelectorAll('.toast.err').forEach(t=>t.remove())")   # no key in tests: expected message
        page.locator("[data-act=set-tab][data-tab=stores]").click()
        settle()
        if page.locator("[data-act=alias-ok]").count():
            page.locator("[data-act=alias-ok]").first.click()
            settle(0.8)
        page.locator("[data-act=set-tab][data-tab=sections]").click()
        settle()
        inp = page.locator("[data-secmap]").first
        inp.fill("S054, S050")
        inp.dispatch_event("change")
        settle(0.8)
        if page.locator("[data-act=sec-reset]").count():
            page.locator("[data-act=sec-reset]").first.click()
            settle(0.6)
        page.locator("[data-act=set-tab][data-tab=holidays]").click()
        settle()
        page.locator("[data-act=hol-defaults]").click()
        settle(0.6)
        page.fill("#hol-day", "2026-09-17")
        page.fill("#hol-name", "Test Day")
        page.locator("[data-act=hol-add]").click()
        settle(0.6)
        page.locator("[data-act=hol-del]").first.click()
        settle(0.6)
        page.locator("[data-act=set-tab][data-tab=leave]").click()
        settle()
        page.fill("#lv-emp", srv.api.db.val("SELECT emp_no FROM roster LIMIT 1 OFFSET 5"))
        page.fill("#lv-from", "2026-09-15")
        page.fill("#lv-to", "2026-09-16")
        page.locator("[data-act=lv-add]").click()
        settle(0.6)
        page.locator("[data-act=lv-del]").first.click()
        settle(0.6)
        page.locator("[data-act=set-tab][data-tab=data]").click()
        settle()
        page.locator("[data-act=set-tab][data-tab=look]").click()
        settle()
        page.locator("[data-act=theme][data-theme=dark]").click()
        settle(0.5)
        page.locator("#hide-names").dispatch_event("click")
        time.sleep(0.4)
        page.locator("#hide-names").dispatch_event("click")
        time.sleep(0.4)
        page.locator("[data-act=theme][data-theme=auto]").click()
        settle(0.5)

        # ---------------------------------------------------------------- demo mode and present mode
        page.locator("[data-act=set-tab][data-tab=data]").click()
        settle()
        page.locator("[data-act=demo-on]").first.click()
        page.wait_for_selector(".demo-pill", timeout=60000)
        settle(1)
        page.locator(".demo-pill").click()
        page.wait_for_function("!document.querySelector('.demo-pill')", timeout=30000)
        settle(1)
        go("home")
        page.locator("[data-act=present]").first.click()
        time.sleep(0.6)
        page.keyboard.press("ArrowDown")
        time.sleep(0.4)
        page.keyboard.press("ArrowUp")
        page.keyboard.press("Escape")
        time.sleep(0.4)
        assert not page.evaluate("document.body.classList.contains('present')")
        for name in ["home", "people", "performance", "stores", "attendance", "org", "ask", "import", "settings"]:
            go(name)
        errors += [f"js: {e}" for e in page.evaluate("window.PNO_errors")]
        browser.close()
    assert not errors, "\n".join(errors)


SAMPLE = """ms => new Promise(res => { const out = []; const t0 = performance.now();
  (function f(){ const s = document.querySelectorAll('.sheet');
    out.push([s.length, s.length ? getComputedStyle(s[s.length - 1]).transform : 'gone']);
    if (performance.now() - t0 < ms) requestAnimationFrame(f); else res(out); })(); })"""


def test_profile_panel_stays_open_while_moving_between_people(app):
    """Clicking a manager or team member inside an open profile swaps the content; the panel never slides away."""
    url, srv, home = app
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=CHROME) if CHROME else p.chromium.launch()
        except Exception as e:
            pytest.skip(f"Chromium not available: {e}")
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.goto(url)
        page.wait_for_function("window.PNO_ready === true", timeout=30000)
        page.evaluate("go('people')")
        page.wait_for_selector("[data-act=role][data-role=SM]")
        page.locator("[data-act=role][data-role=SM]").click()
        page.wait_for_selector("[data-page=people] [data-person]")
        page.locator("[data-page=people] [data-person]").first.click()
        page.wait_for_selector(".sheet.on .sheet-head")
        time.sleep(0.7)
        first = page.locator(".sheet-head h2").inner_text()
        for target in [".sheet-head [data-person]", ".sheet .prow[data-person]"]:
            if target.endswith(".prow[data-person]"):
                page.locator("[data-act=sheet-tab][data-tab=team]").click()
                page.wait_for_selector(target)
            before = page.locator(".sheet-head h2").inner_text()
            page.locator(target).first.click()
            frames = page.evaluate(SAMPLE, 700)
            assert all(n == 1 and t in ("none", "matrix(1, 0, 0, 1, 0, 0)") for n, t in frames), frames
            page.wait_for_function(f"document.querySelector('.sheet-head h2').innerText !== {before!r}")
        assert page.locator("[data-act=sheet-back]").count()
        page.locator("[data-act=sheet-back]").click()
        page.wait_for_function("!document.querySelector('.sheet.swapping')")
        page.locator("[data-act=sheet-back]").click()
        page.wait_for_function(f"document.querySelector('.sheet-head h2').innerText === {first!r}")
        assert not page.locator("[data-act=sheet-back]").count()
        # close, then reopen while it is still sliding out: one panel, fully open
        page.keyboard.press("Escape")
        time.sleep(0.1)
        page.locator("[data-page=people] [data-person]").nth(1).click()
        page.wait_for_selector(".sheet.on .sheet-head")
        time.sleep(0.8)
        assert page.locator(".sheet").count() == 1 and page.locator(".scrim").count() == 1
        assert not page.evaluate("window.PNO_errors").__len__()
        browser.close()
