"""Native PySide6 application shell and responsive background task runner."""

from __future__ import annotations

import sys
import threading
from contextlib import nullcontext
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .ui_helpers import APP_STYLE, BRAND_GOLD, BRAND_WHITE
from .ui_imports import ImportsPage
from .ui_pages import AnalysisPage, AttendancePage, OverviewPage, SalesPage, StaffPage
from .ui_tools import AssistantPage, SettingsPage


class _Signals(QObject):
    completed = Signal(object)
    failed = Signal(object)
    finished = Signal()


class _Task(QRunnable):
    def __init__(self, operation: Callable[[], Any]):
        super().__init__()
        self.operation = operation
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.operation()
            self.signals.completed.emit(result)
        except BaseException as exc:
            # Never hide worker failures; the GUI displays their message.
            self.signals.failed.emit(exc)
        finally:
            self.signals.finished.emit()


class MainWindow(QMainWindow):
    """All navigation pages share a single persistent local SQLite store."""

    NAVIGATION = [
        ("Overview", "dashboard"),
        ("Sales · daily", "sales_daily"),
        ("Sales · monthly", "sales_mtd"),
        ("Attendance", "attendance"),
        ("Staff & hierarchy", "staff"),
        ("Performance analysis", "analysis"),
        ("Assistant · offline", "assistant"),
        ("Imports & history", "imports"),
        ("Settings & backup", "settings"),
    ]

    def __init__(self, store: Any):
        super().__init__()
        self.store = store
        self._pool = QThreadPool.globalInstance()
        self._tasks: list[_Task] = []
        self._pending = 0
        self._restore_active = False
        self._store_write_lock = threading.Lock()
        self.setWindowTitle("PNO · Workforce Analytics")
        self.setMinimumSize(960, 680)
        self.resize(1360, 880)
        self.setStyleSheet(APP_STYLE)
        self._pages: dict[str, QWidget] = {}
        self._page_containers: dict[str, QScrollArea] = {}
        self._navigation: list[tuple[QPushButton, str]] = []
        self._build()
        self.navigate("dashboard")

    def _build(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(218)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 22, 12, 18)
        side_layout.setSpacing(5)
        brand = QLabel("PNO")
        brand.setStyleSheet(f"font-size:30px;font-weight:800;letter-spacing:4px;color:{BRAND_GOLD};padding-left:10px")
        name = QLabel("WORKFORCE\nANALYTICS")
        name.setStyleSheet(f"font-size:11px;font-weight:700;letter-spacing:1.6px;color:{BRAND_WHITE};padding-left:11px")
        side_layout.addWidget(brand)
        side_layout.addWidget(name)
        side_layout.addSpacing(17)
        for label, key in self.NAVIGATION:
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setProperty("active", False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, page=key: self.navigate(page))
            side_layout.addWidget(button)
            self._navigation.append((button, key))
        side_layout.addStretch(1)
        privacy = QLabel("LOCAL ONLY\nReports and assistant stay on this computer.")
        privacy.setWordWrap(True)
        privacy.setStyleSheet("color:#C7BDAE;font-size:11px;padding:10px;border-top:1px solid #594D41")
        side_layout.addWidget(privacy)
        root_layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        header = QFrame()
        header.setObjectName("panel")
        header.setStyleSheet("QFrame#panel { border-radius:0px; border-left:none; border-right:none; border-top:none; }")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 14, 24, 14)
        header_layout.setSpacing(12)
        header_text = QVBoxLayout()
        self.page_eyebrow = QLabel("CARREFOUR PAKISTAN")
        self.page_eyebrow.setObjectName("eyebrow")
        self.page_title = QLabel("Workforce overview")
        self.page_title.setObjectName("pageTitle")
        header_text.addWidget(self.page_eyebrow)
        header_text.addWidget(self.page_title)
        header_layout.addLayout(header_text)
        header_layout.addStretch(1)
        privacy_tag = QLabel("●  OFFLINE · LOCAL DATA")
        privacy_tag.setStyleSheet(f"font-size:11px;font-weight:700;color:#4B694F;background:#EBF1E9;padding:8px 11px;border-radius:10px")
        header_layout.addWidget(privacy_tag)
        content_layout.addWidget(header)
        self.stack = QStackedWidget()
        self.stack.setMinimumWidth(650)
        content_layout.addWidget(self.stack, 1)
        status = QFrame()
        status.setObjectName("panel")
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(20, 5, 20, 5)
        self.status_message = QLabel("Ready · no data has been modified.")
        self.status_message.setObjectName("hint")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(130)
        self.progress.hide()
        status_layout.addWidget(self.status_message, 1)
        status_layout.addWidget(self.progress)
        content_layout.addWidget(status)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

        page_specs = [
            ("dashboard", OverviewPage, (self.store, self.run_job)),
            ("sales_daily", SalesPage, (self.store, self.run_job, "sales_daily")),
            ("sales_mtd", SalesPage, (self.store, self.run_job, "sales_mtd")),
            ("attendance", AttendancePage, (self.store, self.run_job)),
            ("staff", StaffPage, (self.store, self.run_job)),
            ("analysis", AnalysisPage, (self.store, self.run_job)),
            ("assistant", AssistantPage, (self.store, self.run_job)),
            ("imports", ImportsPage, (self.store, self.run_job, self.refresh_data)),
            ("settings", SettingsPage, (self.store, self.run_job, self.refresh_data, self.set_restore_active)),
        ]
        for key, page_type, args in page_specs:
            page = page_type(*args)
            self._pages[key] = page
            container = QScrollArea()
            container.setWidgetResizable(True)
            container.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            container.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            container.setWidget(page)
            self._page_containers[key] = container
            self.stack.addWidget(container)

    def navigate(self, page_key: str) -> None:
        page = self._pages.get(page_key)
        if page is None:
            return
        self.stack.setCurrentWidget(self._page_containers[page_key])
        for button, key in self._navigation:
            button.setProperty("active", key == page_key)
            button.style().unpolish(button)
            button.style().polish(button)
        title = {
            "dashboard": "Workforce overview",
            "sales_daily": "Daily sales",
            "sales_mtd": "Monthly sales · MTD",
            "attendance": "Attendance & hours",
            "staff": "Staff & hierarchy",
            "analysis": "Performance analysis",
            "assistant": "Assistant · offline",
            "imports": "Imports & history",
            "settings": "Settings & backup",
        }.get(page_key, "Workforce analytics")
        self.page_title.setText(title)
        self.status_message.setText("Ready · local data only.")

    def run_job(
        self,
        operation: Callable[[], Any],
        on_done: Callable[[Any], None],
        title: str = "Working locally…",
        on_error: Callable[[Exception], None] | None = None,
        *,
        mutating: bool = False,
        restore: bool = False,
    ) -> bool:
        if mutating and self._restore_active and not restore:
            error = RuntimeError("A database restore is in progress; retry this write after it completes.")
            self.status_message.setText(str(error))
            self.status_message.setStyleSheet("color:#8D3329")
            if on_error:
                on_error(error)
            return False

        if mutating or restore:
            def guarded_operation() -> Any:
                with self._store_write_lock:
                    if self._restore_active and not restore:
                        raise RuntimeError("A database restore is in progress; this write was not started.")
                    store_lock = getattr(self.store, "_lock", None)
                    with store_lock if store_lock is not None else nullcontext():
                        return operation()

            task = _Task(guarded_operation)
        else:
            task = _Task(operation)
        self._tasks.append(task)
        def completed(result: Any) -> None:
            if self._restore_active and not restore and not mutating:
                return
            on_done(result)

        task.signals.completed.connect(completed)

        def failed(exc: BaseException) -> None:
            if self._restore_active and not restore and not mutating:
                return
            message = str(exc).strip() or repr(exc)
            self.status_message.setText(f"Could not complete operation · {message}")
            self.status_message.setStyleSheet("color:#8D3329")
            if on_error:
                on_error(exc if isinstance(exc, Exception) else RuntimeError(message))

        task.signals.failed.connect(failed)

        def finished() -> None:
            self._pending = max(0, self._pending - 1)
            if self._pending == 0:
                self.progress.hide()
                if not self.status_message.text().startswith("Could not complete operation"):
                    self.status_message.setText("Ready · local data only.")
                    self.status_message.setStyleSheet("")
            try:
                self._tasks.remove(task)
            except ValueError:
                pass

        task.signals.finished.connect(finished)
        self._pending += 1
        self.status_message.setText(title)
        self.status_message.setStyleSheet("")
        self.progress.show()
        self._pool.start(task)
        return True

    def set_restore_active(self, active: bool) -> None:
        self._restore_active = bool(active)
        if self._restore_active:
            for page in self._pages.values():
                token = getattr(page, "_refresh_token", None)
                if token is not None:
                    page._refresh_token = token + 1
        imports = self._pages.get("imports")
        if imports is not None:
            imports._restore_active = self._restore_active
            if self._restore_active:
                imports.plan = None
            if hasattr(imports, "save_button"):
                imports.save_button.setEnabled(
                    not self._restore_active and imports.plan is not None
                )
        settings = self._pages.get("settings")
        if settings is not None:
            settings._restore_active = self._restore_active
            for name in ("backup", "restore"):
                button = getattr(settings, name, None)
                if button is not None:
                    button.setEnabled(not self._restore_active)
        if self._restore_active:
            self.status_message.setText("Database restore in progress · new writes are paused.")
        else:
            self.status_message.setText("Database operations resumed · local data only.")

    def refresh_data(self) -> None:
        for page in self._pages.values():
            refresh = getattr(page, "refresh", None)
            if callable(refresh):
                refresh()
        imports = self._pages.get("imports")
        if imports is not None:
            imports.refresh()
        assistant = self._pages.get("assistant")
        if assistant is not None:
            assistant.refresh()
        self.status_message.setText("Report history updated · local data only.")

    def closeEvent(self, event: QCloseEvent) -> None:
        # Workers write only to the store's transactional API; do not abruptly kill them.
        if self._pool.activeThreadCount():
            self._pool.waitForDone(30000)
        event.accept()


def create_application(argv: list[str] | None = None) -> tuple[QApplication, MainWindow]:
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("PNO Workforce Analytics")
    app.setOrganizationName("PNO")
    app.setStyle("Fusion")
    from .storage import Store

    store = Store(Store.default_path())
    window = MainWindow(store)
    return app, window
