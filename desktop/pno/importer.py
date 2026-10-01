"""Offline workbook discovery and normalization for PNO imports."""

from __future__ import annotations

import csv
import hashlib
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Iterable


KINDS = {"roster", "attendance", "sales_daily", "sales_mtd", "productivity"}


@dataclass
class Candidate:
    kind: str
    sheet: str
    header_row: int
    records: list[dict]
    warnings: list[str]
    confidence: float
    column_map: dict[str, str]


@dataclass
class ImportPlan:
    path: str
    checksum: str
    candidates: list[Candidate]
    warnings: list[str]


@dataclass(frozen=True)
class _DayHeader:
    day: int
    month: int | None = None
    year: int | None = None
    label: str = ""
    month_from_header: bool = False


# Header matching is intentionally conservative. It identifies common spelling
# variations without guessing from data values.
ALIASES: dict[str, tuple[str, ...]] = {
    "store": ("store", "store name", "store code", "branch", "location", "outlet", "business unit"),
    "department": ("department", "dept", "division"),
    "section": ("section", "sub department", "sub-department", "category"),
    "employee_id": (
        "employee id", "employee number", "employee no", "emp id", "emp no",
        "staff id", "staff number", "personnel number",
    ),
    "employee_name": ("employee name", "staff name", "associate name", "name"),
    "designation": ("designation", "job title", "position", "role"),
    "grade": ("grade", "job grade", "employee grade"),
    "gender": ("gender", "sex"),
    "manager_id": (
        "reporting manager employee number", "manager employee number",
        "manager id", "manager number", "reports to id",
    ),
    "manager_name": (
        "reporting manager", "reporting manager name", "manager name",
        "reports to", "supervisor",
    ),
    "date": ("date", "business date", "attendance date", "sales date", "day"),
    "status": ("status", "attendance status", "day status", "leave status"),
    "in_time": ("in", "in time", "time in", "clock in", "check in", "check-in"),
    "out_time": ("out", "out time", "time out", "clock out", "check out", "check-out"),
    "hours": (
        "hours", "total hours", "total wh", "total working hours", "working hours",
        "work hours", "wh",
    ),
    "actual": ("actual", "actual sales", "net sales", "sales actual", "sales"),
    "budget": ("budget", "sales budget", "target", "sales target"),
    "last_year": (
        "last year", "last year sales", "ly", "sales ly", "same period last year",
    ),
    "oos_value": ("oos value", "out of stock value", "oos sales"),
    "oos_pct": ("oos %", "oos pct", "oos percentage", "out of stock %"),
    "productivity": ("productivity", "sales per hour", "sph"),
    "productivity_ly": ("productivity ly", "productivity last year", "sph ly"),
    "productivity_growth": (
        "productivity growth", "productivity growth %", "sph growth",
    ),
}

ROSTER_FIELDS = {
    "employee_id", "employee_name", "designation", "grade", "gender",
    "manager_name", "manager_id",
}
STATUS_TOKENS = {
    "P", "A", "AB", "ABS", "WO", "W/O", "PH", "H", "HD", "SL", "CL", "EL",
    "PL", "L", "LV", "OFF", "OD", "WFH", "PRESENT", "ABSENT", "LEAVE",
    "SICK LEAVE", "CASUAL LEAVE", "EARNED LEAVE", "WEEKLY OFF",
    "PUBLIC HOLIDAY", "HOLIDAY", "HALF DAY", "WORK FROM HOME",
}
WEAK_EXACT_ALIASES = {
    "actual": {"sales"},
    "employee_name": {"name"},
    "designation": {"role"},
    "date": {"day"},
    "in_time": {"in"},
    "out_time": {"out"},
    "hours": {"wh"},
    "last_year": {"ly"},
    "productivity": {"sph"},
}


def _normal(value: Any) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ").strip().lower()
    return re.sub(r"[\s_.-]+", " ", text)


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M:%S").rstrip("0").rstrip(":")
    return str(value).strip()


def _canonical_header(header: str) -> str | None:
    normalized = _normal(header)
    for canonical, aliases in ALIASES.items():
        if normalized in {_normal(alias) for alias in aliases}:
            return canonical
    # Multi-row labels often surround a meaningful leaf, e.g. "2025-01-01
    # Total WH". Select the most specific matching alias globally; returning
    # the first token match makes "Last Year Sales 880" become actual sales.
    pieces = normalized.split()
    matches: list[tuple[int, int, str]] = []
    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            alias_parts = _normal(alias).split()
            for index in range(max(1, len(pieces) - len(alias_parts) + 1)):
                if pieces[index:index + len(alias_parts)] == alias_parts:
                    matches.append((len(alias_parts), len(" ".join(alias_parts)), canonical))
    if matches:
        return max(matches, key=lambda match: (match[0], match[1]))[2]
    return None


def _matrix_headers(
    rows: list[list[Any]], start: int, height: int, merged: dict[tuple[int, int], Any]
) -> tuple[list[str], list[list[Any]]]:
    width = max((len(row) for row in rows), default=0)
    components: list[list[Any]] = []
    headers: list[str] = []
    for col in range(width):
        values: list[Any] = []
        for row_idx in range(start, min(start + height, len(rows))):
            value = rows[row_idx][col] if col < len(rows[row_idx]) else None
            if value is None:
                value = merged.get((row_idx, col))
            if value is not None and _string(value):
                # A merged label may be expanded across columns; retain it for
                # each leaf so date/day group headings survive flattening.
                values.append(value)
        components.append(values)
        distinct: list[str] = []
        for value in values:
            text = _string(value)
            if text and (not distinct or _normal(text) != _normal(distinct[-1])):
                distinct.append(text)
        headers.append(" ".join(distinct))
    return headers, components


def _recognized_count(headers: Iterable[str], mappings: dict[str, str]) -> int:
    return sum(1 for header in headers if mappings.get(header) or _canonical_header(header))


def _header_strength(
    header: str, components: list[Any], mappings: dict[str, str]
) -> tuple[str | None, bool]:
    """Return a canonical field and whether the text is convincing as a header."""
    if header in mappings:
        return mappings[header], True
    for component in reversed(components):
        text = _string(component)
        if text in mappings:
            return mappings[text], True
    normalized = _normal(header)
    for canonical, aliases in ALIASES.items():
        alias_map = {_normal(alias): alias for alias in aliases}
        if normalized in alias_map:
            alias = normalized
            return canonical, alias not in WEAK_EXACT_ALIASES.get(canonical, set())
    for component in reversed(components):
        normalized_component = _normal(component)
        for canonical, aliases in ALIASES.items():
            for alias in aliases:
                if normalized_component == _normal(alias):
                    return canonical, normalized_component not in WEAK_EXACT_ALIASES.get(
                        canonical, set()
                    )
    # Wrapped/grouped headings remain useful for mapping but are weak evidence:
    # ordinary row values such as "Store Manager" can contain alias words.
    return _canonical_header(header), False


def _added_row_is_header_structure(row: list[Any]) -> bool:
    matched: set[str] = set()
    strong: set[str] = set()
    populated = 0
    structural_cells = 0
    date_columns = 0
    numeric_days: set[int] = set()
    for value in row:
        if value is None or not _string(value):
            continue
        populated += 1
        text = _string(value)
        canonical, is_strong = _header_strength(text, [value], {})
        if canonical:
            matched.add(canonical)
            if is_strong:
                strong.add(canonical)
            if any(_normal(text) == _normal(alias) for alias in ALIASES[canonical]):
                structural_cells += 1
        if isinstance(value, (date, datetime)):
            date_columns += 1
            structural_cells += 1
        elif re.fullmatch(r"(?:0?[1-9]|[12]\d|3[01])(?:\.0)?", text):
            numeric_days.add(int(float(text)))
            structural_cells += 1
        elif re.fullmatch(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}", text):
            date_columns += 1
            structural_cells += 1
    if not populated or structural_cells / populated < 0.7:
        return False
    consecutive_run = any(
        all(day in numeric_days for day in range(start, start + 3))
        for start in numeric_days
    )
    if date_columns >= 2 or (1 in numeric_days and len(numeric_days) >= 2) or consecutive_run:
        return True
    if len(strong) >= 2:
        return True
    # Wide attendance subheaders commonly use terse IN/OUT tokens (weak in
    # isolation) alongside Total WH/Status. Require several distinct fields.
    return len(matched & {"in_time", "out_time", "hours", "status"}) >= 2 and (
        "hours" in matched or "status" in matched
    )


def _header_windows(
    rows: list[list[Any]], merged: dict[tuple[int, int], Any], mappings: dict[str, str],
) -> list[tuple[int, int, list[str], list[list[Any]], int]]:
    options: list[tuple[int, int, list[str], list[list[Any]], int]] = []
    max_start = min(len(rows), 80)
    for start in range(max_start):
        for height in range(1, min(4, len(rows) - start) + 1):
            if height > 1:
                added_rows = rows[start + 1:start + height]
                # A longer window is a header only when its final row contains
                # genuine subheading/day-heading structure. Never absorb the
                # first data row just because its values resemble aliases.
                if not added_rows or not _added_row_is_header_structure(added_rows[-1]):
                    continue
            headers, components = _matrix_headers(rows, start, height, merged)
            matches = [
                _header_strength(header, components[col], mappings)
                for col, header in enumerate(headers)
                if header.strip()
            ]
            count = sum(canonical is not None for canonical, _ in matches)
            strong = sum(canonical is not None and is_strong for canonical, is_strong in matches)
            weak = count - strong
            # Require positive header evidence, not just a pair of row values
            # that happen to contain alias words (e.g. "Sales"/"Store Manager").
            convincing = strong >= 2 or (strong >= 1 and weak >= 1)
            if not convincing:
                continue
            canonical_columns = {
                col for col, header in enumerate(headers)
                if header.strip() and _header_strength(header, components[col], mappings)[0]
            }
            data_coverage = False
            for data_row in rows[start + height:min(start + height + 4, len(rows))]:
                populated = sum(
                    col < len(data_row) and data_row[col] is not None and bool(_string(data_row[col]))
                    for col in canonical_columns
                )
                if populated >= 2:
                    data_coverage = True
                    break
            if data_coverage:
                options.append((start, height, headers, components, count))

    options.sort(
        key=lambda option: (
            sum(
                _header_strength(option[2][col], option[3][col], mappings)[1]
                for col in range(len(option[2])) if option[2][col].strip()
            ),
            sum(
                _daily_header(option[2][col], option[3][col])[0] is not None
                for col in range(len(option[2]))
            ),
            option[4],
            sum(bool(header.strip()) for header in option[2]),
            -option[1],
        ),
        reverse=True,
    )
    selected: list[tuple[int, int, list[str], list[list[Any]], int]] = []
    occupied: set[int] = set()
    for option in options:
        start, height = option[0], option[1]
        if any(index in occupied for index in range(start, start + height)):
            continue
        # Avoid interpreting a title or body row as a table header unless it
        # has data below it.
        if start + height >= len(rows):
            continue
        occupied.update(range(start, start + height))
        selected.append(option)
    return sorted(selected, key=lambda option: option[0])


def _generic_header_window(
    rows: list[list[Any]], merged: dict[tuple[int, int], Any]
) -> list[tuple[int, int, list[str], list[list[Any]], int]]:
    """Find a single plausible unrecognized header for manual classification."""
    for start in range(min(len(rows) - 1, 80)):
        headers, components = _matrix_headers(rows, start, 1, merged)
        values = [header for header in headers if header.strip()]
        if len(values) < 2 or len({_normal(value) for value in values}) < 2:
            continue
        # Typical header rows are mostly text. Require a populated following
        # row to distinguish a real table from a stray title.
        next_row = rows[start + 1]
        if sum(value is not None and bool(_string(value)) for value in next_row) < 2:
            continue
        return [(start, 1, headers, components, 0)]
    return []


def _detect_kind(headers: list[str], count: int) -> tuple[str, float]:
    mapped = {_canonical_header(header) for header in headers}
    mapped.discard(None)
    if ROSTER_FIELDS.issubset(mapped) or (
        {"employee_id", "employee_name", "designation", "manager_id"} <= mapped
    ):
        return "roster", min(0.99, 0.72 + 0.04 * len(mapped))
    has_in = "in_time" in mapped
    has_out = "out_time" in mapped
    has_day_columns = any(_daily_header(header)[0] is not None for header in headers)
    if (
        "employee_id" in mapped
        and (has_in or has_out or "hours" in mapped or has_day_columns or {"date", "status"} <= mapped)
    ):
        return "attendance", min(0.98, 0.68 + 0.05 * len(mapped))
    if "actual" in mapped and "date" in mapped:
        return "sales_daily", min(0.97, 0.7 + 0.05 * len(mapped))
    if "actual" in mapped and "budget" in mapped:
        return "sales_mtd", min(0.97, 0.66 + 0.05 * len(mapped))
    if "actual" in mapped:
        return "sales_daily", min(0.9, 0.58 + 0.05 * len(mapped))
    if "productivity" in mapped or "productivity_ly" in mapped:
        return "productivity", min(0.94, 0.64 + 0.05 * len(mapped))
    if count:
        return "unknown", min(0.55, 0.3 + 0.05 * count)
    return "unknown", 0.2


def _daily_header(
    header: str,
    components: list[Any] | None = None,
    period: str | None = None,
) -> tuple[Any, str | None]:
    """Return (day, subfield) for wide attendance headings."""
    raw_parts = [value for value in components or [] if _string(value)]
    if not raw_parts:
        raw_parts = [header]
    parts = [_string(value) for value in raw_parts]
    category: str | None = None
    for value in parts:
        canonical = _canonical_header(value)
        if canonical in {"in_time", "out_time", "hours", "status"}:
            category = canonical
    combined = " ".join(parts)
    # Date values are more reliable than parsing flattened text. Excel dates
    # are kept as date objects in components.
    for value in raw_parts:
        if isinstance(value, datetime):
            return value.date(), category
        if isinstance(value, date):
            return value, category
    for value in parts:
        text = _string(value)
        iso_match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)
        if iso_match:
            year, month, day = (int(part) for part in iso_match.groups())
            return _DayHeader(day, month, year, text, True), category
        numeric_match = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2}|\d{2})\b", text)
        if numeric_match:
            first, second, year = (int(part) for part in numeric_match.groups())
            year = year if year >= 100 else 2000 + year
            # Workbook date headings are commonly day/month/year; try that
            # first, then month/day/year when only the latter is valid.
            day, month = first, second
            if second > 12 and first <= 12:
                day, month = second, first
            return _DayHeader(day, month, year, text, True), category

    month_numbers = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7,
        "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
        "december": 12,
    }
    month_match = re.search(
        r"\b(" + "|".join(sorted(month_numbers, key=len, reverse=True)) + r")\b",
        combined.lower(),
    )
    if month_match:
        month = month_numbers[month_match.group(1)]
        day = None
        # Day may be before or after its named month, or in a separate row.
        before = combined[:month_match.start()]
        after = combined[month_match.end():]
        day_match = re.search(r"\b(0?[1-9]|[12]\d|3[01])\b", before)
        if not day_match:
            day_match = re.search(r"\b(0?[1-9]|[12]\d|3[01])\b", after)
        if not day_match:
            for part in parts:
                if re.fullmatch(r"(?:0?[1-9]|[12]\d|3[01])(?:\.0)?", part):
                    day_match = re.match(r"(\d+)", part)
                    break
        if day_match:
            day = int(day_match.group(1))
            year_match = re.search(r"\b(19\d{2}|20\d{2})\b", combined)
            if not year_match:
                year_match = re.search(r"\b(0?\d|[12]\d|3[01])[- /](\d{2})\b", combined)
            year = None
            if year_match:
                year_text = year_match.group(year_match.lastindex or 1)
                year = int(year_text)
                if year < 100:
                    year += 2000
            elif period:
                period_match = re.match(r"^\s*(\d{4})[-/]\d{1,2}", str(period))
                if period_match:
                    year = int(period_match.group(1))
            return _DayHeader(day, month, year, combined, True), category

    # Numeric day headings are completed from the selected period only; a
    # named month above is never silently replaced by that period's month.
    for value in parts:
        text = _string(value)
        if re.fullmatch(r"(?:0?[1-9]|[12]\d|3[01])(?:\.0)?", text):
            day = int(float(text))
            return _DayHeader(day, label=combined), category
    match = re.match(r"^\s*(0?[1-9]|[12]\d|3[01])(?:\.0)?\b", combined)
    if match:
        return _DayHeader(int(float(match.group(1))), label=combined), category
    return None, category


def _resolve_day_header(
    heading: Any, period: str | None
) -> tuple[str | None, str | None, bool]:
    if isinstance(heading, datetime):
        parsed = heading.date()
    elif isinstance(heading, date):
        parsed = heading
    elif isinstance(heading, _DayHeader):
        period_match = re.match(r"^\s*(\d{4})[-/](\d{1,2})", str(period or ""))
        period_year = int(period_match.group(1)) if period_match else None
        period_month = int(period_match.group(2)) if period_match else None
        month = heading.month if heading.month_from_header else (heading.month or period_month)
        year = heading.year or period_year
        if month is None or year is None:
            return None, f"Unresolved attendance date heading {heading.label!r}; provide a year/month period.", False
        try:
            parsed = date(year, month, heading.day)
        except ValueError:
            return None, f"Impossible attendance date heading {heading.label!r}; that day does not exist.", True
        if heading.month_from_header and period_month and (
            heading.month != period_month
            or (heading.year is not None and period_year is not None and heading.year != period_year)
        ):
            return (
                parsed.isoformat(),
                f"Attendance heading date in {heading.label!r} differs from selected period {period}; heading date retained.",
                False,
            )
        return parsed.isoformat(), None, False
    else:
        return None, f"Unresolved attendance date heading {heading!r}.", False
    return parsed.isoformat(), None, False


def _open_source(
    path: Path,
) -> tuple[list[tuple[str, list[list[Any]], dict, set, dict[tuple[int, int], str]]], list[str]]:
    """Return (sheet, values, merged-header-values, empty-formula-cells)."""
    suffix = path.suffix.lower()
    warnings: list[str] = []
    if suffix in {".csv", ".tsv"}:
        raw = path.read_bytes()
        text: str | None = None
        for encoding in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError(f"Could not decode delimited file: {path}")
        delimiter = "\t" if suffix == ".tsv" else ","
        sample = text[:8192]
        if suffix == ".csv" and sample:
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                pass
        rows = [list(row) for row in csv.reader(text.splitlines(), delimiter=delimiter)]
        return [("CSV" if suffix == ".csv" else "TSV", rows, {}, set(), {})], warnings
    if suffix == ".xlsx":
        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError("Reading .xlsx files requires openpyxl.") from exc
        formulas_book = openpyxl.load_workbook(path, read_only=False, data_only=False, keep_vba=False)
        values_book = openpyxl.load_workbook(path, read_only=False, data_only=True, keep_vba=False)
        sheets = []
        for sheet_name in values_book.sheetnames:
            values_ws = values_book[sheet_name]
            formula_ws = formulas_book[sheet_name]
            rows = [list(row) for row in values_ws.iter_rows(values_only=True)]
            merged: dict[tuple[int, int], Any] = {}
            for merged_range in formula_ws.merged_cells.ranges:
                min_col, min_row, max_col, max_row = merged_range.bounds
                anchor = values_ws.cell(min_row, min_col).value
                for row_idx in range(min_row - 1, max_row):
                    for col_idx in range(min_col - 1, max_col):
                        if row_idx != min_row - 1 or col_idx != min_col - 1:
                            merged[(row_idx, col_idx)] = anchor
            empty_formula_cells: set[tuple[int, int]] = set()
            formats: dict[tuple[int, int], str] = {}
            for row in formula_ws.iter_rows():
                for cell in row:
                    if cell.number_format:
                        formats[(cell.row - 1, cell.column - 1)] = cell.number_format
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        if values_ws.cell(cell.row, cell.column).value is None:
                            empty_formula_cells.add((cell.row - 1, cell.column - 1))
            sheets.append((sheet_name, rows, merged, empty_formula_cells, formats))
        formulas_book.close()
        values_book.close()
        return sheets, warnings
    if suffix == ".xls":
        try:
            import xlrd
        except ImportError as exc:
            raise RuntimeError("Reading .xls files requires xlrd.") from exc
        workbook = xlrd.open_workbook(path, on_demand=True, formatting_info=True)
        sheets = []
        for sheet in workbook.sheets():
            rows: list[list[Any]] = []
            formats: dict[tuple[int, int], str] = {}
            for row_idx in range(sheet.nrows):
                values = []
                for col_idx in range(sheet.ncols):
                    cell = sheet.cell(row_idx, col_idx)
                    value = cell.value
                    if cell.xf_index < len(workbook.xf_list):
                        xf = workbook.xf_list[cell.xf_index]
                        format_entry = workbook.format_map.get(xf.format_key)
                        format_text = getattr(format_entry, "format_str", "")
                        if format_text:
                            formats[(row_idx, col_idx)] = format_text
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            value = xlrd.xldate_as_datetime(value, workbook.datemode)
                        except (ValueError, OverflowError):
                            pass
                    elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                        value = None
                    values.append(value)
                rows.append(values)
            merged = {}
            for rlo, rhi, clo, chi in sheet.merged_cells:
                anchor = rows[rlo][clo]
                for row_idx in range(rlo, rhi):
                    for col_idx in range(clo, chi):
                        if row_idx != rlo or col_idx != clo:
                            merged[(row_idx, col_idx)] = anchor
            sheets.append((sheet.name, rows, merged, set(), formats))
        workbook.release_resources()
        return sheets, warnings
    raise ValueError(f"Unsupported file type {suffix or '(no extension)'}; use .xlsx, .xls, .csv or .tsv.")


def _parse_number(value: Any, header: str, number_format: str | None = None) -> Any:
    if not isinstance(value, str):
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                return None
            is_percentage = "%" in (number_format or "")
            if is_percentage and isinstance(value, (int, float)):
                return float(value) * 100
            return value
        return value
    text = value.strip()
    if not text:
        return value
    if text.endswith("%"):
        try:
            return float(text[:-1].replace(",", "").strip())
        except ValueError:
            return value
    cleaned = text.replace(",", "")
    if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", cleaned):
        try:
            number = float(cleaned)
            return int(number) if number.is_integer() else number
        except ValueError:
            pass
    return value


def _value_for_record(
    value: Any, canonical: str | None, header: str, number_format: str | None
) -> Any:
    if isinstance(value, (datetime, date, time)):
        return _string(value)
    if canonical in {
        "actual", "budget", "last_year", "oos_value", "oos_pct", "hours",
        "productivity", "productivity_ly", "productivity_growth",
    }:
        return _parse_number(value, header, number_format)
    return value


def _is_status(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = re.sub(r"\s+", " ", value.strip().upper())
    return normalized in STATUS_TOKENS


def _summary_kind(row: dict[str, Any]) -> str | None:
    text = " ".join(str(value) for value in row.values() if value is not None).upper()
    if re.search(r"\b(GRAND TOTAL|OVERALL TOTAL|REPORT TOTAL|SUBTOTAL OF ALL)\b", text):
        return "grand"
    # A plain Total row is safely removable only when it has no department or
    # section dimension. Departmental aggregates remain available to callers.
    label_values = {str(value).strip().upper() for value in row.values() if value is not None}
    if "TOTAL" in label_values and not row.get("department") and not row.get("section"):
        return "total"
    return None


def _make_candidate(
    path: Path,
    checksum: str,
    sheet: str,
    rows: list[list[Any]],
    merged: dict[tuple[int, int], Any],
    empty_formula_cells: set[tuple[int, int]],
    start: int,
    height: int,
    headers: list[str],
    components: list[list[Any]],
    next_start: int,
    detected_kind: str,
    confidence: float,
    mappings: dict[str, str],
    period: str | None,
    formats: dict[tuple[int, int], str],
    manual_kind: str | None,
) -> Candidate:
    candidate_kind = manual_kind or detected_kind
    warnings: list[str] = []
    if manual_kind and detected_kind != manual_kind:
        if detected_kind == "unknown":
            warnings.append(f"Kind manually set to {manual_kind}; report type was not identified automatically.")
        else:
            warnings.append(f"Kind manually set to {manual_kind}; detected {detected_kind}.")
    elif detected_kind == "unknown":
        warnings.append("Report type was not identified; select a manual kind before importing.")

    column_map: dict[str, str] = {}
    mapped_columns: dict[int, str] = {}
    for col, header in enumerate(headers):
        canonical = mappings.get(header)
        if canonical is None:
            # Overrides also work with exact leaf labels in multirow headings.
            for component in reversed(components[col]):
                if _string(component) in mappings:
                    canonical = mappings[_string(component)]
                    break
        if canonical is None:
            canonical = _canonical_header(header)
        if canonical:
            mapped_columns[col] = canonical
            if header:
                column_map[header] = canonical

    wide_columns: dict[Any, dict[int, int]] = {}
    wide_column_indexes: set[int] = set()
    if candidate_kind == "attendance":
        for col, header in enumerate(headers):
            day, subfield = _daily_header(header, components[col], period)
            if day is not None and subfield is None:
                # A date-only daily column in a monthly attendance grid stores
                # its attendance token directly in the cell.
                subfield = "status"
            explicit = mappings.get(header)
            if explicit is None:
                explicit = next(
                    (
                        mappings[_string(component)]
                        for component in reversed(components[col])
                        if _string(component) in mappings
                    ),
                    None,
                )
            if explicit is not None:
                subfield = explicit if explicit in {"in_time", "out_time", "hours", "status"} else None
            if day is not None and subfield in {"in_time", "out_time", "hours", "status"}:
                if isinstance(day, _DayHeader):
                    day_key = (day.year, day.month, day.day)
                elif isinstance(day, datetime):
                    day_key = day.date().isoformat()
                elif isinstance(day, date):
                    day_key = day.isoformat()
                else:
                    day_key = str(day)
                wide_columns.setdefault(day_key, {"_day": day})[subfield] = col
                wide_column_indexes.add(col)
                column_map[header] = subfield

    records: list[dict] = []
    start_data = start + height
    for row_idx in range(start_data, min(next_start, len(rows))):
        row_values = rows[row_idx]
        if not any(value is not None and _string(value) for value in row_values):
            continue
        formula_missing = any(
            missing_row == row_idx and 0 <= missing_col < len(row_values)
            for missing_row, missing_col in empty_formula_cells
        )
        if formula_missing:
            warnings.append(
                f"Formula cache missing on {sheet} row {row_idx + 1}; affected values were not imported."
            )
        if candidate_kind == "attendance" and wide_columns:
            base: dict[str, Any] = {}
            raw: dict[str, Any] = {}
            for col, header in enumerate(headers):
                if col >= len(row_values) or not header:
                    continue
                value = row_values[col]
                if value is None:
                    continue
                if col in wide_column_indexes:
                    continue
                canonical = mapped_columns.get(col)
                if canonical in {"in_time", "out_time", "hours", "status"}:
                    raw[header] = _string(value) if isinstance(value, (date, datetime, time)) else value
                    continue
                if canonical:
                    base[canonical] = _value_for_record(
                        value, canonical, header, formats.get((row_idx, col))
                    )
                else:
                    raw[header] = _string(value) if isinstance(value, (date, datetime, time)) else value
            if raw:
                base["raw"] = raw
            for daily in wide_columns.values():
                record = dict(base)
                resolved_date, date_warning, invalid_date = _resolve_day_header(
                    daily["_day"], period
                )
                record["date"] = resolved_date
                if date_warning:
                    warnings.append(date_warning)
                if invalid_date:
                    continue
                found_values = False
                status = None
                for field_name in ("in_time", "out_time", "hours", "status"):
                    col = daily.get(field_name)
                    if col is None or col >= len(row_values):
                        continue
                    value = row_values[col]
                    if value is None or (isinstance(value, str) and not value.strip()):
                        continue
                    found_values = True
                    if field_name == "status":
                        status = _string(value)
                    elif _is_status(value):
                        status = _string(value)
                    else:
                        record[field_name] = _value_for_record(
                            value, field_name, headers[col], formats.get((row_idx, col))
                        )
                if status:
                    record["status"] = status
                if not found_values:
                    continue
                if record.get("out_time") and record.get("in_time"):
                    in_value, out_value = str(record["in_time"]), str(record["out_time"])
                    if re.match(r"^\d{1,2}:\d{2}", in_value) and re.match(r"^\d{1,2}:\d{2}", out_value):
                        if out_value[:5] < in_value[:5]:
                            warnings.append(
                                f"Overnight shift preserved on source row {row_idx + 1}; times were not adjusted."
                            )
                record["_provenance"] = {
                    "source": str(path), "checksum": checksum, "sheet": sheet,
                    "row": row_idx + 1,
                }
                summary = _summary_kind(record)
                if summary in {"grand", "total"}:
                    warnings.append(f"Excluded report-level summary row at source row {row_idx + 1}.")
                    continue
                records.append(record)
            continue

        record: dict[str, Any] = {}
        raw: dict[str, Any] = {}
        for col, header in enumerate(headers):
            if col >= len(row_values) or not header:
                continue
            value = row_values[col]
            if value is None:
                continue
            canonical = mapped_columns.get(col)
            normalized_value = _value_for_record(
                value, canonical, header, formats.get((row_idx, col))
            )
            if canonical:
                record[canonical] = normalized_value
            else:
                raw[header] = _string(value) if isinstance(value, (date, datetime, time)) else value
        if raw:
            record["raw"] = raw
        if not record:
            continue
        record["_provenance"] = {
            "source": str(path), "checksum": checksum, "sheet": sheet, "row": row_idx + 1,
        }
        summary = _summary_kind(record)
        if summary in {"grand", "total"}:
            warnings.append(f"Excluded report-level summary row at source row {row_idx + 1}.")
            continue
        if candidate_kind == "attendance" and record.get("out_time") and record.get("in_time"):
            in_value, out_value = str(record["in_time"]), str(record["out_time"])
            if (
                re.match(r"^\d{1,2}:\d{2}", in_value)
                and re.match(r"^\d{1,2}:\d{2}", out_value)
                and out_value[:5] < in_value[:5]
            ):
                warnings.append(
                    f"Overnight shift preserved on source row {row_idx + 1}; times were not adjusted."
                )
        records.append(record)

    # De-duplicate warnings while preserving their discovery order.
    warnings = list(dict.fromkeys(warnings))
    return Candidate(
        kind=candidate_kind,
        sheet=sheet,
        header_row=start + 1,
        records=records,
        warnings=warnings,
        confidence=confidence,
        column_map=column_map,
    )


def scan_workbook(
    path: str | Path,
    kind: str | None = None,
    period: str | None = None,
    mappings: dict[str, str] | None = None,
) -> ImportPlan:
    """Scan a local workbook and return table candidates without importing them."""
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"Import file not found: {file_path}")
    if kind is not None and kind not in KINDS:
        raise ValueError(f"Unsupported manual kind {kind!r}; choose one of {', '.join(sorted(KINDS))}.")
    overrides = dict(mappings or {})
    for source_header, canonical in overrides.items():
        if canonical not in {
            "store", "department", "section", "employee_id", "employee_name",
            "designation", "grade", "gender", "manager_id", "manager_name",
            "date", "status", "in_time", "out_time", "hours", "actual", "budget",
            "last_year", "oos_value", "oos_pct", "productivity", "productivity_ly",
            "productivity_growth",
        }:
            raise ValueError(f"Invalid canonical mapping for {source_header!r}: {canonical!r}")
    checksum = hashlib.sha256(file_path.read_bytes()).hexdigest()
    sheets, plan_warnings = _open_source(file_path)
    candidates: list[Candidate] = []
    for sheet, rows, merged, empty_formula_cells, formats in sheets:
        header_options = _header_windows(rows, merged, overrides)
        if not header_options:
            header_options = _generic_header_window(rows, merged)
        if not header_options:
            continue
        # If the workbook has no recognized schema, provide a low-confidence
        # candidate so the UI can request a manual kind.
        candidates_for_sheet: list[tuple[Any, ...]] = []
        options = header_options
        for option in options:
            start, height, headers, components, count = option
            detected_kind, confidence = _detect_kind(headers, count)
            label_hint = _normal(f"{file_path.stem} {sheet}")
            if detected_kind in {"sales_daily", "sales_mtd"}:
                if "mtd" in label_hint or "month to date" in label_hint:
                    detected_kind = "sales_mtd"
                    confidence = max(confidence, 0.76)
                elif "daily" in label_hint:
                    detected_kind = "sales_daily"
                    confidence = max(confidence, 0.76)
            candidates_for_sheet.append((start, height, headers, components, count, detected_kind, confidence))
        for index, item in enumerate(candidates_for_sheet):
            start, height, headers, components, count, detected_kind, confidence = item
            next_start = (
                candidates_for_sheet[index + 1][0]
                if index + 1 < len(candidates_for_sheet)
                else len(rows)
            )
            if kind:
                confidence = max(confidence, 0.35)
            candidate = _make_candidate(
                file_path, checksum, sheet, rows, merged, empty_formula_cells,
                start, height, headers, components, next_start, detected_kind,
                confidence, overrides, period, formats, kind,
            )
            candidates.append(candidate)
    if not candidates:
        plan_warnings.append("No recognizable table headers were found.")
    return ImportPlan(
        path=str(file_path.resolve()),
        checksum=checksum,
        candidates=candidates,
        warnings=plan_warnings,
    )