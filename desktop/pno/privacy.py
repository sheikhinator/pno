"""Presentation (demo) mode: mask people's names and IDs on screen and in exports."""

from __future__ import annotations

import hashlib

_STATE = {"demo": False}


def set_demo_mode(enabled: bool) -> None:
    _STATE["demo"] = bool(enabled)


def demo_mode() -> bool:
    return _STATE["demo"]


def _code(key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return f"{int(digest[:6], 16) % 900 + 100}"


def name(value: str, key: str | None = None) -> str:
    if not demo_mode() or not value:
        return value
    return f"Leader {_code(key or value)}"


def employee_id(value: str) -> str:
    if not demo_mode() or not value:
        return value
    return "ID hidden"
