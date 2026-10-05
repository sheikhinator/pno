"""Where PNO keeps its database, settings and exports (always on this PC)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("PNO_HOME")
    if override:
        p = Path(override)
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        p = Path(base) / "PNO"
    else:
        p = Path.home() / ".pno"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "pno.sqlite3"


def exports_dir() -> Path:
    p = Path.home() / "Documents" / "PNO Reports"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        p = data_dir() / "exports"
        p.mkdir(parents=True, exist_ok=True)
    return p


def resource(*parts: str) -> Path:
    """Path to a bundled resource, both from source and from a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base.joinpath(*parts)
