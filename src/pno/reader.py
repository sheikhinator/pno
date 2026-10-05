"""Open any report file and expose every table inside it as a grid of cells.

- .xlsx / .xlsm / .xlsb / .xls / .ods through calamine (fast; hidden sheets included), openpyxl as fallback
- .xls files that are really HTML tables (common for web exports) and .htm/.html
- .csv / .txt / .tsv with any delimiter and encoding (UTF-8, UTF-16, Windows-1252)
- text pasted from the clipboard
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

Row = list[Any]


@dataclass
class Sheet:
    name: str
    rows: list[Row]
    hidden: bool = False
    kind: str = "sheet"


@dataclass
class Workbook:
    name: str
    sheets: list[Sheet]
    file_hash: str
    warnings: list[str] = field(default_factory=list)


def file_hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def open_file(path: str | Path) -> Workbook:
    path = Path(path)
    data = path.read_bytes()
    return open_bytes(data, path.name)


def open_bytes(data: bytes, name: str) -> Workbook:
    warnings: list[str] = []
    head = data[:4096]
    kind = sniff(head)
    if kind == "zip":
        sheets = _calamine_bytes(data, warnings) or _openpyxl_bytes(data, warnings)
    elif kind == "ole":
        sheets = _calamine_bytes(data, warnings)
    elif kind == "html":
        sheets = _html_sheets(data)
    else:
        sheets = _text_sheets(data, Path(name).stem or "Data")
    sheets = [s for s in sheets if any(any(c not in (None, "") for c in r) for r in s.rows)]
    if not sheets:
        warnings.append("No tables were found in this file.")
    return Workbook(name=name, sheets=sheets, file_hash=file_hash(data), warnings=warnings)


def from_text(text: str, name: str = "Pasted data") -> Workbook:
    data = text.encode("utf-8")
    return Workbook(name=name, sheets=_text_sheets(data, name, kind="paste"), file_hash=file_hash(data))


def sniff(head: bytes) -> str:
    if head.startswith(b"PK"):
        return "zip"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "ole"
    low = head.lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    if low.startswith(b"<") and (b"<table" in head.lower() or b"<html" in low or b"<!doctype" in low or b"<?xml" in low):
        return "html"
    return "text"


def _calamine_bytes(data: bytes, warnings: list[str]) -> list[Sheet]:
    try:
        import python_calamine as pc
    except ImportError:  # pragma: no cover
        return []
    try:
        wb = pc.CalamineWorkbook.from_filelike(io.BytesIO(data))
    except Exception as e:
        warnings.append(f"Fast reader could not open the workbook ({e}).")
        return []
    out = []
    for meta in wb.sheets_metadata:
        if str(meta.typ).split(".")[-1].lower() != "worksheet":
            continue
        try:
            sh = wb.get_sheet_by_name(meta.name)
            rows = [list(r) for r in sh.iter_rows()]
        except Exception as e:
            warnings.append(f"Sheet '{meta.name}' could not be read: {e}")
            continue
        rows = [[None if c == "" else c for c in r] for r in rows]
        hidden = str(meta.visible).split(".")[-1].lower() != "visible"
        out.append(Sheet(name=meta.name, rows=rows, hidden=hidden))
    return out


def _openpyxl_bytes(data: bytes, warnings: list[str]) -> list[Sheet]:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        warnings.append(f"This file could not be opened as a workbook: {e}")
        return []
    out = [Sheet(name=ws.title, rows=[list(r) for r in ws.iter_rows(values_only=True)],
                 hidden=ws.sheet_state != "visible") for ws in wb.worksheets]
    wb.close()
    return out


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[Row]] = []
        self._stack: list[list[Row]] = []
        self._row: Row | None = None
        self._cell: list[str] | None = None
        self._span = 1

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            try:
                self._span = max(1, int(a.get("colspan", "1")))
            except ValueError:
                self._span = 1
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip() or None)
            self._row.extend([None] * (self._span - 1))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._stack:
            self._stack[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._stack:
            t = self._stack.pop()
            if t:
                self.tables.append(t)

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def decode(data: bytes) -> str:
    """Text in any of the encodings Excel and Windows produce. UTF-16 only when it is really UTF-16."""
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if len(data) > 4 and data[1:2] == b"\x00" and data[3:4] == b"\x00":
        return data.decode("utf-16-le", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _html_sheets(data: bytes) -> list[Sheet]:
    p = _TableParser()
    p.feed(decode(data))
    return [Sheet(name=f"Table {i}", rows=t, kind="html") for i, t in enumerate(p.tables, 1) if len(t) >= 2]


def _text_sheets(data: bytes, name: str, kind: str = "csv") -> list[Sheet]:
    text = decode(data)
    delim = guess_delimiter("\n".join(text.splitlines()[:200]))
    grid = [[c if c != "" else None for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)]
    return [Sheet(name=name, rows=grid, kind=kind)] if grid else []


def guess_delimiter(sample: str) -> str:
    lines = [ln for ln in sample.splitlines() if ln.strip()][:100]
    best, best_score = ",", 0.0
    for d in ["\t", ",", ";", "|"]:
        per = sorted(len(next(csv.reader([ln], delimiter=d))) for ln in lines) if lines else [1]
        med = per[len(per) // 2]
        score = (med > 1) * med * sum(1 for x in per if x == med) / len(per)
        if score > best_score:
            best, best_score = d, score
    return best
