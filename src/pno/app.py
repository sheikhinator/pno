"""Start PNO.

    PNO.exe                      open the app
    PNO.exe --selftest LOG       open every screen on the fictional demo data with no window, write LOG, exit 0/1
    PNO.exe --smoke-test         check that the parsers, engine and exports work (no window), exit 0/1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path


def _qt_env():
    # A stable, quiet web engine on office PCs (no GPU sandbox surprises, no noisy logs).
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    for f in ("--disable-logging", "--log-level=3"):
        if f not in flags:
            flags += " " + f
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags.strip()


def _log_to_file():
    """A windowed .exe has no console: keep error details in a small log next to the data instead of losing them."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        from .paths import data_dir
        path = data_dir() / "pno.log"
        if path.exists() and path.stat().st_size > 2_000_000:
            path.replace(path.with_suffix(".old.log"))
        f = open(path, "a", encoding="utf-8", buffering=1)
        f.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f
    except OSError:
        import io
        sys.stdout = sys.stdout or io.StringIO()
        sys.stderr = sys.stderr or io.StringIO()


def offline_check(model: str, log_path: str) -> int:
    """Build check: start the bundled offline AI with a model file and make sure it answers."""
    os.environ["PNO_HOME"] = tempfile.mkdtemp(prefix="pno-offline-")
    log = open(log_path, "w", encoding="utf-8")

    def out(msg):
        log.write(msg + "\n")
        log.flush()

    ok = False
    try:
        from .agent import llm, local
        from .api import Api, load_demo
        from .db import Database
        exe = local.find_runtime()
        out(f"runtime: {exe}")
        if not exe:
            raise RuntimeError("llama-server not found in the build")
        t = time.time()
        if not local.SERVER.ensure(model, wait=300):
            raise RuntimeError("the offline AI did not become ready")
        out(f"server ready in {time.time() - t:.1f}s")
        msg = llm.chat(f"http://127.0.0.1:{local.PORT}/v1", "", "local",
                       [{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=10, timeout=300)
        out(f"plain reply: {(msg.get('content') or '').strip()!r}")
        ok = bool((msg.get("content") or "").strip())
        db = Database(os.path.join(os.environ["PNO_HOME"], "pno.sqlite3"))
        load_demo(db)
        api = Api(db)
        api.dispatch("agent_settings", {"mode": "offline"})
        api.agent.offline_link(model)
        t = time.time()
        r = api.dispatch("agent_ask", {"question": "Who are the top 3 section managers?"})
        out(f"ask: engine={r.get('engine')} tools={r.get('tools')} in {time.time() - t:.1f}s")
        out("answer: " + (r.get("answer") or r.get("error") or "")[:600])
        db.close()
    except Exception:
        out(traceback.format_exc())
    finally:
        try:
            from .agent import local
            local.SERVER.stop()
        except Exception:
            pass
    out("OFFLINE CHECK " + ("PASSED" if ok else "FAILED"))
    log.close()
    return 0 if ok else 1


def smoke_test(out=print) -> bool:
    """Parsers → engine → every screen's data → every export, on a throwaway database."""
    from . import exports
    from .api import Api, load_demo
    from .db import Database

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "smoke.sqlite3")
        t = time.perf_counter()
        load_demo(db)
        out(f"demo imported in {time.perf_counter() - t:.2f}s")
        api = Api(db)
        init = api.dispatch("init", {})
        if init.get("error") or not init.get("has_data"):
            out(f"init failed: {init}")
            return False
        month = init["month"]
        for m in ("dashboard", "people", "stores", "attendance", "org"):
            r = api.dispatch(m, {"month": month} if m == "org" else {"month": month, "scope": {}})
            if isinstance(r, dict) and r.get("error"):
                out(f"{m} failed: {r['error']}")
                return False
        for pack in exports.PACKS:
            for fmt in ("pdf", "pptx", "xlsx"):
                kw = {}
                if pack == "dept":
                    kw["scope"] = {"dept": api.dispatch("options", {"month": month})["depts"][0]["value"]}
                if pack == "scorecard":
                    kw["emp"] = api.dispatch("people", {"month": month, "scope": {}})["rows"][0]["emp"]
                if pack == "store":
                    kw["store_id"] = api.dispatch("stores", {"month": month, "scope": {}})["rows"][0]["store_id"]
                path = str(Path(tmp) / f"{pack}.{fmt}")
                r = api.dispatch("export", {"pack": pack, "fmt": fmt, "month": month, "save_as": path,
                                            "open_after": False, **kw})
                if r.get("error") or not Path(path).stat().st_size:
                    out(f"export {pack} {fmt} failed: {r}")
                    return False
        a = api.dispatch("agent_ask", {"question": "Who are the top 3 performers?", "month": month})
        if a.get("error"):
            out(f"assistant failed: {a['error']}")
            return False
        db.close()
    out("smoke test passed")
    return True


def selftest(log_path: str) -> int:
    """Load the real window offscreen on demo data, visit every screen and record any screen error."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    tmp = tempfile.mkdtemp(prefix="pno-selftest-")
    os.environ["PNO_HOME"] = tmp
    log = open(log_path, "w", encoding="utf-8")

    def out(msg):
        log.write(msg + "\n")
        log.flush()
        print(msg)

    ok = False
    try:
        if not smoke_test(out):
            return 1
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from .api import load_demo
        from .db import Database
        from .window import MainWindow

        _qt_env()
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] += " --no-sandbox --disable-gpu"
        app = QApplication.instance() or QApplication(sys.argv[:1])
        db = Database(Path(tmp) / "pno.sqlite3")
        load_demo(db)
        win = MainWindow(db)
        win.resize(1440, 900)
        win.show()
        pages = ["home", "people", "performance", "stores", "attendance", "org", "ask", "import", "settings"]
        state = {"i": -1, "errors": [], "t0": time.time(), "visited": []}

        def js(code, cb):
            win.page.runJavaScript(code, 0, cb)

        def step():
            if time.time() - state["t0"] > 120:
                state["errors"].append("timed out")
                return app.exit(1)
            js("JSON.stringify({ready: !!window.PNO_ready, busy: !!document.querySelector('.page .loading'), "
               "errors: window.PNO_errors || [], page: (window.PNO_state||{}).page})", check)

        def check(res):
            try:
                r = json.loads(res or "{}")
            except Exception:
                r = {}
            if not r.get("ready") or r.get("busy"):
                return QTimer.singleShot(250, step)
            if r.get("errors"):
                state["errors"] += r["errors"]
            if state["i"] >= 0:
                state["visited"].append(pages[state["i"]])
            state["i"] += 1
            if state["i"] >= len(pages):
                return app.exit(0 if not state["errors"] else 1)
            js(f"document.querySelector('#nav [data-go=\"{pages[state['i']]}\"]').click(); 1",
               lambda _: QTimer.singleShot(600, step))

        QTimer.singleShot(500, step)
        code = app.exec()
        out(f"screens visited: {', '.join(state['visited'])}")
        if state["errors"]:
            out("screen errors: " + "; ".join(map(str, state["errors"])))
        ok = code == 0 and len(state["visited"]) == len(pages) and not state["errors"]
        win.close()
        db.close()
    except Exception:
        out(traceback.format_exc())
    out("SELFTEST " + ("PASSED" if ok else "FAILED"))
    log.close()
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    _log_to_file()
    ap = argparse.ArgumentParser(prog="PNO")
    ap.add_argument("--selftest", metavar="LOG")
    ap.add_argument("--smoke-test", action="store_true")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--offline-check", nargs=2, metavar=("MODEL", "LOG"))
    a, _ = ap.parse_known_args(argv)

    from . import __version__
    if a.offline_check:
        return offline_check(*a.offline_check)
    if a.version:
        print(__version__)
        return 0
    if a.smoke_test:
        return 0 if smoke_test() else 1
    if a.selftest:
        return selftest(a.selftest)

    _qt_env()
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QMessageBox

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("PNO")
    app.setOrganizationName("PNO")
    app.setApplicationVersion(__version__)
    try:
        from .db import Database
        from .paths import data_dir, db_path
        from .window import MainWindow
        db = Database(db_path())
        win = MainWindow(db, data_dir() / "web")
        win.show()
    except Exception as e:
        traceback.print_exc()
        QMessageBox.critical(None, "PNO could not start", f"{e}\n\nYour data was not changed.")
        return 1
    code = app.exec()
    db.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
