"""Offline assistant chat and local data/model settings."""

from __future__ import annotations

import html
from pathlib import Path
import sys
from typing import Any, Callable

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .ui_helpers import FilterBar, empty_panel

MODEL_MAX_BYTES = 1_000_000_000
BUNDLED_MODEL_RELATIVE = Path("models") / "qwen2.5-0.5b-instruct-q4_k_m.gguf"


def packaged_model_path(executable: str | Path | None = None) -> Path | None:
    """Return the exact bundled model when it exists beside the executable."""
    path = Path(executable or sys.executable).expanduser().resolve().parent / BUNDLED_MODEL_RELATIVE
    try:
        if path.is_file() and 0 < path.stat().st_size <= MODEL_MAX_BYTES:
            return path
    except OSError:
        return None
    return None


def selected_model_path(settings: QSettings) -> str | None:
    """A saved Settings choice wins; otherwise use the model packaged by the builder."""
    override = str(settings.value("assistant/model_path", "") or "").strip()
    if override:
        return override
    bundled = packaged_model_path()
    return str(bundled) if bundled else None


class AssistantPage(QWidget):
    def __init__(self, store: Any, run_job: Callable):
        super().__init__()
        self.store = store
        self.run_job = run_job
        self.settings = QSettings("PNO", "WorkforceAnalytics")
        self._request_active = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(empty_panel(
            "Ask about your reports",
            "Answers use locally imported data and this laptop's optional GGUF model. "
            "This assistant sends no report data or questions to an online service.",
        ))
        self.filters = FilterBar(self.store)
        layout.addWidget(self.filters)
        self.model_label = QLabel()
        self.model_label.setObjectName("hint")
        layout.addWidget(self.model_label)
        model_path = selected_model_path(self.settings)
        self.model_label.setText(f"Selected local model: {model_path or 'None · rule-based answers remain available'}")
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(False)
        self.transcript.setPlaceholderText("Ask a question about the visible report scope.")
        self.transcript.append(
            "<p style='color:#756E68'>Assistant · Answers are limited to local report evidence and will identify "
            "when information is missing.</p>"
        )
        layout.addWidget(self.transcript, 1)
        row = QHBoxLayout()
        self.question = QLineEdit()
        self.question.setPlaceholderText("e.g., How did sales compare with budget this month?")
        self.question.returnPressed.connect(self.ask)
        self.send = QPushButton("Ask locally")
        self.send.setObjectName("primaryButton")
        self.send.clicked.connect(self.ask)
        row.addWidget(self.question, 1)
        row.addWidget(self.send)
        layout.addLayout(row)
        self.notice = QLabel("Assistant is offline.")
        self.notice.setObjectName("hint")
        layout.addWidget(self.notice)

    def ask(self) -> None:
        if self._request_active:
            return
        question = self.question.text().strip()
        if not question:
            return
        self.question.clear()
        self.transcript.append(f"<p><b>You</b><br>{html.escape(question, quote=True)}</p>")
        self._request_active = True
        self.question.setEnabled(False)
        self.send.setEnabled(False)
        filters = self.filters.filters()
        model_path = selected_model_path(self.settings)

        def work() -> str:
            from .assistant import Assistant

            return Assistant(self.store, model_path=model_path).ask(question, filters=filters)

        def done(answer: str) -> None:
            self._request_active = False
            self.question.setEnabled(True)
            self.send.setEnabled(True)
            rendered = html.escape(str(answer), quote=True).replace("\n", "<br>")
            self.transcript.append(f"<p><b>PNO · Local</b><br>{rendered}</p>")
            self.notice.setText("Answer generated locally from the selected report scope.")

        def failed(error: Exception) -> None:
            self._request_active = False
            self.question.setEnabled(True)
            self.send.setEnabled(True)
            message = html.escape(str(error), quote=True).replace("\n", "<br>")
            self.transcript.append(f"<p><b>Assistant unavailable</b><br>{message}</p>")
            self.notice.setText("Could not generate this answer.")

        self.run_job(work, done, title="Preparing a local answer…", on_error=failed)

    def refresh(self) -> None:
        self.filters.refresh_dimensions()


class SettingsPage(QWidget):
    def __init__(
        self,
        store: Any,
        run_job: Callable,
        changed: Callable | None = None,
        set_restore_active: Callable[[bool], None] | None = None,
    ):
        super().__init__()
        self.store = store
        self.run_job = run_job
        self.changed = changed or (lambda: None)
        self.restore_state_changed = set_restore_active or (lambda _active: None)
        self._restore_active = False
        self.settings = QSettings("PNO", "WorkforceAnalytics")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(empty_panel(
            "Privacy & local data",
            "Reports, backups, assistant questions, and model files stay on this computer. "
            "No background cloud connection, model download, or automatic data upload is used.",
        ))

        model = empty_panel(
            "Optional local assistant model",
            "Choose an existing GGUF file up to 1 GB. Models are never downloaded by the application. "
            "Rule-based report answers remain available without one.",
        )
        self.model_path = QLabel()
        self.model_path.setWordWrap(True)
        self.model_path.setObjectName("hint")
        self._sync_model_label()
        self.select_model = QPushButton("Choose local GGUF…")
        self.select_model.clicked.connect(self._choose_model)
        self.clear_model = QPushButton("Clear model")
        self.clear_model.clicked.connect(self._clear_model)
        model.layout().addWidget(self.model_path)
        row = QHBoxLayout()
        row.addWidget(self.select_model)
        row.addWidget(self.clear_model)
        row.addStretch(1)
        model.layout().addLayout(row)
        layout.addWidget(model)

        data = empty_panel(
            "Local database backup & recovery",
            "Back up the SQLite database to an approved local location. Restoring first preserves the current database; "
            "the selected backup must pass SQLite validation.",
        )
        self.db_path = QLabel(f"Database: {self.store.path}")
        self.db_path.setWordWrap(True)
        self.db_path.setObjectName("hint")
        data.layout().addWidget(self.db_path)
        buttons = QHBoxLayout()
        self.backup = QPushButton("Back up database…")
        self.backup.clicked.connect(self._backup)
        self.restore = QPushButton("Restore from backup…")
        self.restore.setObjectName("dangerButton")
        self.restore.clicked.connect(self._restore)
        buttons.addWidget(self.backup)
        buttons.addWidget(self.restore)
        buttons.addStretch(1)
        data.layout().addLayout(buttons)
        layout.addWidget(data)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setObjectName("hint")
        layout.addWidget(self.notice)
        layout.addStretch(1)

    def _sync_model_label(self) -> None:
        override = str(self.settings.value("assistant/model_path", "") or "").strip()
        bundled = packaged_model_path()
        if override:
            self.model_path.setText(f"Selected local model (Settings override): {override}")
        elif bundled:
            self.model_path.setText(f"Selected packaged model (automatic): {bundled}")
        else:
            self.model_path.setText("No model selected · offline rule-based answers are available.")

    def _choose_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a local GGUF model", "", "GGUF models (*.gguf)")
        if not path:
            return
        try:
            file = Path(path)
            size = file.stat().st_size
            if file.suffix.casefold() != ".gguf":
                raise ValueError("Choose a .gguf file.")
            if size <= 0 or size > MODEL_MAX_BYTES:
                raise ValueError("Choose a non-empty model of at most 1 GB.")
            with file.open("rb") as model:
                if model.read(4) != b"GGUF":
                    raise ValueError("The selected file does not have a GGUF model header.")
        except OSError as exc:
            QMessageBox.critical(self, "Model file unavailable", str(exc))
            return
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid model file", str(exc))
            return
        self.settings.setValue("assistant/model_path", str(file.resolve()))
        self.settings.sync()
        self._sync_model_label()
        self.notice.setText("Local model selected. The app will not copy, download, or upload it.")

    def _clear_model(self) -> None:
        self.settings.remove("assistant/model_path")
        self.settings.sync()
        self._sync_model_label()
        fallback = packaged_model_path()
        self.notice.setText(
            f"Settings override cleared. {'Using packaged model: ' + str(fallback) if fallback else 'Rule-based offline answers remain available.'}"
        )

    def _backup(self) -> None:
        from datetime import datetime

        default = Path.home() / f"PNO-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3"
        path, _ = QFileDialog.getSaveFileName(self, "Back up local database", str(default), "SQLite database (*.sqlite3 *.db)")
        if not path:
            return
        if not QMessageBox.question(
            self, "Confirm local backup", f"Create a backup at this path?\n\n{path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        ) == QMessageBox.StandardButton.Yes:
            return
        self.backup.setEnabled(False)

        def work() -> str:
            self.store.backup(path)
            return path

        def done(saved: str) -> None:
            self.backup.setEnabled(not self._restore_active)
            self.notice.setText(f"Backup created locally:\n{saved}")
            QMessageBox.information(self, "Backup complete", f"Database backup created:\n{saved}")

        def failed(error: Exception) -> None:
            self.backup.setEnabled(not self._restore_active)
            self.notice.setText(f"Backup failed: {error}")
            QMessageBox.critical(self, "Backup failed", str(error))

        self.run_job(
            work,
            done,
            title="Backing up local database…",
            on_error=failed,
            mutating=True,
        )

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a validated database backup", "", "SQLite database (*.sqlite3 *.db);;All files (*)")
        if not path:
            return
        if Path(path).resolve() == Path(self.store.path).resolve():
            QMessageBox.warning(self, "Choose a backup copy", "The selected path is the current database, not a separate backup.")
            return
        reply = QMessageBox.warning(
            self,
            "Confirm database restore",
            "This will replace the current local database. The application will preserve a backup of the current database "
            "before restoring the selected file. Continue only if the selected backup is approved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._set_restore_active(True)

        def work() -> None:
            self.store.restore(path)

        def done(_: Any) -> None:
            self._set_restore_active(False)
            self.notice.setText("Database restored. Your previous database was preserved before this operation.")
            QMessageBox.information(self, "Restore complete", self.notice.text())
            self.changed()

        def failed(error: Exception) -> None:
            self._set_restore_active(False)
            self.notice.setText(f"Restore failed: {error}")
            QMessageBox.critical(self, "Restore failed", str(error))

        self.run_job(
            work,
            done,
            title="Validating and restoring database…",
            on_error=failed,
            mutating=True,
            restore=True,
        )

    def _set_restore_active(self, active: bool) -> None:
        self._restore_active = bool(active)
        self.backup.setEnabled(not self._restore_active)
        self.restore.setEnabled(not self._restore_active)
        self.restore_state_changed(self._restore_active)
