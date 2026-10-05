"""Shared pieces for the report parsers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..util import clean_text, is_blank, norm


@dataclass
class ParseResult:
    kind: str                      # roster | attendance | productivity | sales | leave
    sheet: str
    rows: list[dict] = field(default_factory=list)
    month: str | None = None       # YYYY-MM
    as_of: str | None = None       # YYYY-MM-DD
    warnings: list[str] = field(default_factory=list)
    summary: str = ""
    confidence: float = 1.0
    needs: list[str] = field(default_factory=list)     # e.g. ['month'] when the file has no date
    extra: dict[str, Any] = field(default_factory=dict)
    preview: list[dict] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)


KIND_LABEL = {"roster": "Employee roster", "attendance": "Biometric attendance", "productivity": "MTD productivity",
              "sales": "BO 200-10-05 store sales", "leave": "Leave register"}


def cells(row: list) -> list[str]:
    return [norm(c) for c in row]


def find_col(header: list[str], *patterns: str, exclude: tuple[str, ...] = (), start: int = 0) -> int | None:
    """First column whose normalised header matches any pattern (regex, whole-cell)."""
    for p in patterns:
        rx = re.compile(rf"^(?:{p})$")
        for i in range(start, len(header)):
            h = header[i]
            if h and rx.match(h) and not any(re.search(e, h) for e in exclude):
                return i
    return None


def get(row: list, i: int | None) -> Any:
    return row[i] if i is not None and i < len(row) else None


def blank_row(row: list) -> bool:
    return all(is_blank(c) for c in row)


def text(row: list, i: int | None) -> str:
    return clean_text(get(row, i))
