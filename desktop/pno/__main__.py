"""Launch the PNO desktop application or perform a native UI smoke check."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
import time
from datetime import date
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="PNO offline workforce analytics")
    parser.add_argument("--smoke-test", action="store_true", help="create the native window against a temporary database and exit")
    parser.add_argument("--capture", metavar="PATH", help="save a screenshot of the current native window and exit")
    args = parser.parse_args()
    if args.smoke_test or args.capture:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow
    from .storage import Store

    temporary = tempfile.TemporaryDirectory(prefix="pno-ui-smoke-") if args.smoke_test or args.capture else None
    store = Store(Path(temporary.name) / "pno-smoke.sqlite3") if temporary else Store(Store.default_path())
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("PNO Workforce Analytics")
    app.setOrganizationName("PNO")
    app.setStyle("Fusion")
    window = MainWindow(store)
    window.show()
    app.processEvents()

    if args.capture:
        output = Path(args.capture).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(output), "PNG"):
            print(f"Could not save screenshot: {output}", file=sys.stderr)
            window.close()
            if temporary:
                temporary.cleanup()
            return 1
        print(f"Native desktop screenshot saved: {output}")
        window.close()
        if temporary:
            temporary.cleanup()
        return 0
    if args.smoke_test:
        try:
            _seed_fictional_smoke_records(store)
            window.refresh_data()
            window.navigate("dashboard")
            app.processEvents()
            overview = window._pages["dashboard"]
            _wait_for_refresh(app, overview, overview._refresh_token)
            initial = overview.last_result
            if not initial or initial["metrics"].get("actual") != 200:
                raise RuntimeError("Dashboard did not load the isolated fictional smoke records.")
            from .ui_helpers import ChartCanvas

            if not isinstance(overview.chart._view, ChartCanvas):
                raise RuntimeError("Dashboard failed to render its populated native chart.")
            store_filter = overview.filters_bar.store
            index = store_filter.findData("Fictional Smoke South")
            if index < 0:
                raise RuntimeError("Dashboard store filter did not expose the smoke fixture dimension.")
            prior_token = overview._refresh_token
            store_filter.setCurrentIndex(index)
            changed_token = overview._refresh_token
            if changed_token <= prior_token:
                raise RuntimeError("Changing the dashboard store filter did not trigger a refresh.")
            _wait_for_refresh(app, overview, changed_token)
            filtered = overview.last_result
            if not filtered or filtered["metrics"].get("actual") != 75:
                raise RuntimeError("Dashboard filter change did not scope the chart and metrics to the selected store.")
            if overview.filters_bar.filters().get("store") != "Fictional Smoke South":
                raise RuntimeError("Dashboard filter selection did not retain its canonical store value.")
            if not isinstance(overview.chart._view, ChartCanvas) or not any(
                row.get("actual") == 75 for row in overview.chart._view.rows
            ):
                raise RuntimeError("The native chart did not update to the selected store's filtered value.")
        except Exception as exc:
            print(f"UI smoke test failed: {exc}", file=sys.stderr)
            window.close()
            temporary.cleanup()
            return 1
        required_pages = {
            "dashboard", "sales_daily", "sales_mtd", "attendance", "staff",
            "analysis", "assistant", "imports", "settings",
        }
        if set(window._pages) != required_pages:
            print("UI smoke test failed: one or more primary pages are missing.", file=sys.stderr)
            window.close()
            temporary.cleanup()
            return 1
        window.navigate("imports")
        app.processEvents()
        window.close()
        temporary.cleanup()
        print("UI smoke test passed: pages instantiate, a fictional chart renders, and store filtering updates metrics.")
        return 0
    return app.exec()


def _seed_fictional_smoke_records(store) -> None:
    """Seed a disposable DB only for --smoke-test; normal launch never creates example data."""
    period = date.today().replace(day=1).isoformat()
    records = [
        {
            "store": "Fictional Smoke North",
            "department": "Fictional Test Department",
            "date": period,
            "actual": 125,
            "budget": 100,
            "last_year": 120,
        },
        {
            "store": "Fictional Smoke South",
            "department": "Fictional Test Department",
            "date": period,
            "actual": 75,
            "budget": 80,
            "last_year": 70,
        },
    ]
    checksum = hashlib.sha256(b"PNO fictional UI smoke fixture v1").hexdigest()
    store.import_records(
        kind="sales_mtd",
        period=period,
        records=records,
        source="Fictional synthetic UI smoke fixture",
        checksum=checksum,
        sheet="Synthetic test data",
    )


def _wait_for_refresh(app, page, token: int, timeout: float = 12.0) -> None:
    deadline = time.monotonic() + timeout
    while page._last_completed_token < token:
        app.processEvents()
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for the filtered dashboard refresh.")
        time.sleep(0.005)


if __name__ == "__main__":
    raise SystemExit(main())
