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
    "gguf": "AI model (*.gguf)",
    "backup": "PNO backup (*.sqlite3 *.db);;All files (*)",
    "pdf": "PDF (*.pdf)",
    "pptx": "PowerPoint (*.pptx)",
    "xlsx": "Excel (*.xlsx)",
}


class _Signals(QObject):
    done = Signal(str, str)


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
        if method in self.UI_METHODS:
            try:
                out = self.api.dispatch(method, json.loads(params or "{}"))
            except Exception as e:
                out = {"error": str(e)}
            self.reply.emit(rid, dumps(out))
            return
        self.pool.start(_Job(self.api, rid, method, params, self.signals))


class QtHost(Host):
    def __init__(self, window: "MainWindow"):
        self.window = window

    def pick_files(self, kind: str = "reports") -> list[str]:
        title = {"reports": "Choose report files", "gguf": "Choose an AI model file", "backup": "Choose a PNO backup"}.get(kind, "Choose files")
        start = str(Path.home() / ("Downloads" if kind != "backup" else "Documents"))
        if kind == "reports":
            paths, _ = QFileDialog.getOpenFileNames(self.window, title, start, FILTERS["reports"])
            return list(paths)
        path, _ = QFileDialog.getOpenFileName(self.window, title, start, FILTERS.get(kind, ""))
        return [path] if path else []

    def save_path(self, name: str, filt: str = "") -> str | None:
        path, _ = QFileDialog.getSaveFileName(self.window, "Save as", str(exports_dir() / name), FILTERS.get(filt, ""))
        return path or None

    def open_path(self, path: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))


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
        self.setWindowTitle("PNO · People & Performance")
        icon = resource("assets", "pno.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1440, 900)
        self.setMinimumSize(1024, 680)

        self.api = Api(db, QtHost(self))
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
