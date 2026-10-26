"""The desktop window: a Qt web view showing the screens, wired to the data service through QWebChannel."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QUrl, Signal, Slot, Qt
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QMainWindow

from . import __version__
from .api import Api, Host, dumps
from .db import Database
from .paths import exports_dir, resource

FILTERS = {
    "reports": "Reports (*.xlsx *.xlsm *.xls *.csv *.txt *.tsv);;All files (*)",
    "cvs": "CVs (*.pdf *.docx *.doc *.txt *.rtf);;All files (*)",
    "surveys": "Survey results (*.xlsx *.xlsm *.csv *.txt);;All files (*)",
    "policies": "Policies (*.pdf *.docx *.doc *.txt *.rtf *.md);;All files (*)",
    "gguf": "AI model (*.gguf)",
    "docx": "Word (*.docx)",
    "zip": "Zip archive (*.zip)",
    "backup": "P&O backup (*.sqlite3 *.db);;All files (*)",
    "pdf": "PDF (*.pdf)",
    "pptx": "PowerPoint (*.pptx)",
    "xlsx": "Excel (*.xlsx)",
}


class _Signals(QObject):
    done = Signal(str, str)


class _Gui(QObject):
    """Runs a small piece of work (a file dialog, opening a file) on the window's thread and hands back the result,
    so the heavy work around it can stay on a background thread and the window never freezes."""
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run, Qt.ConnectionType.BlockingQueuedConnection)

    @Slot(object)
    def _run(self, box):
        try:
            box["out"] = box["fn"]()
        except Exception as e:  # noqa: BLE001
            box["err"] = e

    def __call__(self, fn):
        from PySide6.QtCore import QThread
        if QThread.currentThread() is self.thread():
            return fn()
        box = {"fn": fn}
        self.call.emit(box)
        if "err" in box:
            raise box["err"]
        return box.get("out")


class _Job(QRunnable):
    def __init__(self, api: Api, rid: str, method: str, params: str, signals: _Signals):
        super().__init__()
        self.api, self.rid, self.method, self.params, self.signals = api, rid, method, params, signals

    def run(self):
        try:
            params = json.loads(self.params or "{}")
            out = self.api.dispatch(self.method, params)
        except Exception as e:                      # never leave the screen waiting
            out = {"error": str(e)}
        try:
            text = dumps(out)
        except Exception as e:
            text = json.dumps({"error": f"Could not send the answer to the screen: {e}"})
        self.signals.done.emit(self.rid, text)


class Bridge(QObject):
    """The object the screens call. Requests run on worker threads so the window never freezes."""

    reply = Signal(str, str)

    # Requests that open a dialog must run on the window's thread.
    UI_METHODS = {"pick_files", "backup", "restore", "offline_pick_model", "agent_attach", "export", "open_path"}

    def __init__(self, api: Api, parent=None):
        super().__init__(parent)
        self.api = api
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(4)
        self.signals = _Signals()
        self.signals.done.connect(self.reply)

    @Slot(str, str, str)
    def request(self, rid: str, method: str, params: str):
        # every request runs off the window's thread; dialogs inside them hop back to it (QtHost.gui), so reading
        # files, exporting or backing up never freezes the window ("Not responding")
        self.pool.start(_Job(self.api, rid, method, params, self.signals))


class QtHost(Host):
    def __init__(self, window: "MainWindow"):
        self.window = window
        self.gui = _Gui()

    def pick_files(self, kind: str = "reports") -> list[str]:
        return self.gui(lambda: self._pick_files(kind))

    def _pick_files(self, kind: str = "reports") -> list[str]:
        title = {"reports": "Choose report files", "gguf": "Choose an AI model file", "backup": "Choose a P&O backup",
                 "cvs": "Choose CVs (PDF, Word or text)", "policies": "Choose HR policies (PDF, Word or text)", "surveys": "Choose survey results"}.get(kind, "Choose files")
        start = str(Path.home() / ("Downloads" if kind != "backup" else "Documents"))
        if kind in ("reports", "cvs", "policies"):
            paths, _ = QFileDialog.getOpenFileNames(self.window, title, start, FILTERS[kind])
            return list(paths)
        path, _ = QFileDialog.getOpenFileName(self.window, title, start, FILTERS.get(kind, ""))
        return [path] if path else []

    def save_path(self, name: str, filt: str = "") -> str | None:
        def ask():
            path, _ = QFileDialog.getSaveFileName(self.window, "Save as", str(exports_dir() / name), FILTERS.get(filt, ""))
            return path or None
        return self.gui(ask)

    def open_path(self, path: str) -> None:
        self.gui(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))

    def open_url(self, url: str) -> None:
        self.gui(lambda: QDesktopServices.openUrl(QUrl(url)))


class Page(QWebEnginePage):
    """Keeps the app on its own screens: links open in the browser and dropped files go to the importer."""

    def __init__(self, profile, window: "MainWindow"):
        super().__init__(profile, window)
        self.window = window

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        if url.scheme() == "file" and url.toLocalFile().replace("\\", "/").endswith("/web/index.html"):
            return True
        if url.scheme() == "file":
            self.window.dropped([url.toLocalFile()])
            return False
        if url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, _type):           # target=_blank → open outside
        helper = QWebEnginePage(self.profile(), self)
        helper.urlChanged.connect(lambda u: (QDesktopServices.openUrl(u), helper.deleteLater()))
        return helper

    def javaScriptConsoleMessage(self, level, message, line, source):
        if os.environ.get("PNO_DEBUG") or level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            print(f"[js] {message} ({Path(source).name}:{line})", file=sys.stderr)


class View(QWebEngineView):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window = window
        self.setAcceptDrops(True)

    def _files(self, event) -> list[str]:
        md = event.mimeData()
        if not md or not md.hasUrls():
            return []
        return [u.toLocalFile() for u in md.urls() if u.isLocalFile()]

    def dragEnterEvent(self, event):
        if self._files(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._files(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        files = self._files(event)
        if files:
            event.acceptProposedAction()
            self.window.dropped(files)
        else:
            super().dropEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, db: Database, profile_dir: Path | None = None):
        super().__init__()
        self.setWindowTitle("P&O · People & Organisation")
        icon = resource("assets", "pno.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1440, 900)
        self.setMinimumSize(1024, 680)

        self.api = Api(db, QtHost(self))
        import threading
        from . import api as _api_mod, office
        # one copy a day, kept 14 days: started 3 minutes after opening so it never slows start-up or an import
        t = threading.Timer(180, lambda: _api_mod._quiet(office.auto_backup, db))
        t.daemon = True
        t.start()
        self.bridge = Bridge(self.api, self)
        self.channel = QWebChannel(self)
        self.channel.registerObject("bridge", self.bridge)

        profile = QWebEngineProfile("pno", self) if profile_dir else QWebEngineProfile.defaultProfile()
        if profile_dir:
            profile.setPersistentStoragePath(str(profile_dir))
            profile.setCachePath(str(profile_dir / "cache"))
        self.view = View(self)
        self.page = Page(profile, self)
        self.page.setWebChannel(self.channel)
        s = self.page.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        self.page.setBackgroundColor(Qt.GlobalColor.white)
        self.view.setPage(self.page)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu if not os.environ.get("PNO_DEBUG")
                                       else Qt.ContextMenuPolicy.DefaultContextMenu)
        self.setCentralWidget(self.view)
        self.view.load(QUrl.fromLocalFile(str(resource("web", "index.html"))))

    def dropped(self, paths: list[str]) -> None:
        paths = [p for p in paths if p and Path(p).is_file()]
        if paths:
            self.page.runJavaScript(f"window.PNO_drop && window.PNO_drop({json.dumps(paths)})")

    def closeEvent(self, event):
        try:
            self.bridge.pool.waitForDone(3000)
            from .agent import local
            local.SERVER.stop()
        except Exception:
            pass
        super().closeEvent(event)


__all__ = ["MainWindow", "Bridge", "QtHost", "__version__"]
