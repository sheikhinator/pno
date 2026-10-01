"""Deterministic offline query interpretation with optional local GGUF prose."""

from __future__ import annotations

import calendar
import re
from datetime import date
from pathlib import Path
from typing import Any

from .analysis import analyze, _text


_ISO_DATE = re.compile(r"(?<!\d)(\d{4}-\d{2}(?:-\d{2})?)(?!\d)")
_NUMBER_TOKEN = re.compile(
    r"(?<!\w)(?:[$€£]?\d[\d,]*(?:\.\d+)?%?|zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|"
    r"fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion|first|second|third|"
    r"double|triple|half|couple|several|many|few)(?!\w)",
    re.IGNORECASE,
)
_MODEL_WORDS = {
    "a", "above", "ahead", "and", "are", "at", "attendance", "available", "below", "beat",
    "behind", "budget", "but", "came", "compared", "data", "declined", "decreased", "down",
    "dropped", "enough", "evidence", "exceeded", "falling", "fell", "flat", "grew", "grown",
    "has", "have", "in", "increased", "insufficient", "is", "last", "matched", "met", "missed",
    "month", "monthly", "not", "of", "on", "over", "performance", "plan", "positive", "prior",
    "recorded", "reported", "remained", "results", "rose", "sales", "short", "target", "the",
    "there", "this", "to", "under", "unavailable", "unchanged", "versus", "vs", "was", "were",
    "up", "while", "with", "year", "year-over-year",
}
_BUDGET_DIRECTIONS = {
    "above": (
        r"\b(?:above|over)\s+(?:the\s+)?(?:budget|plan|target)\b",
        r"\b(?:beat|exceeded)\s+(?:the\s+)?(?:budget|plan|target)\b",
        r"\bahead\s+of\s+(?:the\s+)?(?:budget|plan|target)\b",
    ),
    "below": (
        r"\b(?:below|under|behind)\s+(?:the\s+)?(?:budget|plan|target)\b",
        r"\bmissed\s+(?:the\s+)?(?:budget|plan|target)\b",
        r"\bshort\s+of\s+(?:the\s+)?(?:budget|plan|target)\b",
    ),
    "at": (
        r"\b(?:at|on|met|matched)\s+(?:the\s+)?(?:budget|plan|target)\b",
    ),
}
_GROWTH_DIRECTIONS = {
    "grew": {"grew", "grown", "increased", "positive", "rose", "up"},
    "declined": {"declined", "decreased", "down", "dropped", "falling", "fell"},
    "unchanged": {"flat", "remained", "unchanged"},
}


def _latest_date(filters: dict[str, Any], question_dates: list[str]) -> str | None:
    value = _text(filters.get("period_to")) or (_text(question_dates[-1]) if question_dates else None)
    if value and re.fullmatch(r"\d{4}-\d{2}", value):
        try:
            year, month = (int(part) for part in value.split("-"))
            return date(year, month, calendar.monthrange(year, month)[1]).isoformat()
        except ValueError:
            pass
    return value


def _employee_roster(store: Any, period: str | None) -> list[dict[str, Any]]:
    try:
        rows = store.employees(period=period)
    except TypeError:
        try:
            rows = store.employees(period)
        except Exception:
            return []
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    latest_by_identity: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = _text(row.get("employee_id") or row.get("employee_code"))
        identity = code.casefold() if code else _text(row.get("employee_name")).casefold()
        if not identity:
            continue
        snapshot = _text(row.get("_period"))
        previous = latest_by_identity.get(identity)
        if previous is not None and snapshot < previous:
            continue
        if previous is None or snapshot > previous:
            unique = {key: value for key, value in unique.items() if key[0] != identity}
            latest_by_identity[identity] = snapshot
        unique[(identity, _text(row.get("store")).casefold())] = row
    return list(unique.values())


def _country_value(row: dict[str, Any]) -> str:
    value = _text(row.get("country") or row.get("country_name"))
    if value:
        return value
    raw = row.get("raw")
    if isinstance(raw, dict):
        for key, raw_value in raw.items():
            if re.sub(r"[\W_]+", "", str(key).casefold()) in {"country", "countryname"} and _text(raw_value):
                return _text(raw_value)
    return ""


def _match_employees(roster: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    lower = question.casefold()
    matches: dict[tuple[str, str], dict[str, Any]] = {}
    for employee in roster:
        code = _text(employee.get("employee_id") or employee.get("employee_code"))
        name = _text(employee.get("employee_name"))
        found = False
        if code:
            pattern = rf"(?<![\w]){re.escape(code.casefold())}(?![\w])"
            found = re.search(pattern, lower) is not None
        if name and name.casefold() in lower:
            found = True
        if found:
            matches[(code.casefold(), _text(employee.get("store")).casefold())] = employee
    return list(matches.values())


def _employee_intent(question: str) -> tuple[bool, str | None]:
    """Recognize explicit employee lookups even when the code is not in roster."""
    numeric_match = re.search(
        r"\b(?:employee|staff|associate)\s*#?\s*(\d+)\b",
        question,
        re.IGNORECASE,
    )
    if numeric_match:
        return True, numeric_match.group(1)
    code_match = re.search(
        r"\b(?:employee|staff|associate)\s+(?:id|code|number)\s*(?:is|=|:|#)?\s*([A-Za-z0-9][A-Za-z0-9._/-]*)",
        question,
        re.IGNORECASE,
    )
    if code_match:
        return True, code_match.group(1)
    if re.search(r"\b(?:employee|staff|associate)\s+(?:id|code|number)\b", question, re.IGNORECASE):
        return True, None
    person_match = re.search(
        r"\b(?:employee|staff|associate)\s+(?:named|called|is|:|#)?\s*([A-Za-z][A-Za-z0-9_-]*)",
        question,
        re.IGNORECASE,
    )
    if person_match:
        token = person_match.group(1)
        if token.casefold() not in {
            "count", "counts", "number", "data", "details", "sales", "attendance",
            "productivity", "records", "status", "history", "report", "headcount",
            "total", "performance", "information", "lookup",
        }:
            return True, token
    standalone_code = re.search(r"\b[A-Z]{1,6}[-_]?\d{2,}\b", question)
    if standalone_code:
        return True, standalone_code.group(0)
    return False, None


def _dimension_override(store: Any, question: str, filters: dict[str, Any]) -> None:
    try:
        dimensions = store.dimensions()
    except Exception:
        dimensions = {}
    countries = dimensions.get("countries", [])
    if not countries:
        try:
            countries = sorted({
                _country_value(row)
                for row in store.records()
                if isinstance(row, dict) and _country_value(row)
            }, key=str.casefold)
        except Exception:
            countries = []
    dimensions = dict(dimensions)
    dimensions["countries"] = countries
    lower = question.casefold()
    for dimension in ("countries", "stores", "departments", "sections"):
        key = {
            "countries": "country",
            "stores": "store",
            "departments": "department",
            "sections": "section",
        }[dimension]
        found = []
        for value in dimensions.get(dimension, []):
            label = _text(value)
            if not label:
                continue
            if re.search(rf"(?<!\w){re.escape(label.casefold())}(?!\w)", lower):
                found.append(label)
        # Only a unique mention is an override; resolving repeated names from
        # different dimensions/stores silently would be misleading.
        unique = list(dict.fromkeys(found))
        if len(unique) == 1:
            filters[key] = unique[0]


def _date_overrides(question: str, filters: dict[str, Any]) -> list[str]:
    matches = _ISO_DATE.findall(question)
    normalized: list[str] = []
    for match in matches:
        if len(match) == 7:
            try:
                year, month = (int(part) for part in match.split("-"))
                normalized.extend([date(year, month, 1).isoformat(), date(year, month, calendar.monthrange(year, month)[1]).isoformat()])
            except ValueError:
                continue
        else:
            try:
                normalized.append(date.fromisoformat(match).isoformat())
            except ValueError:
                continue
    if normalized:
        if len(matches) > 1:
            filters["period_from"] = normalized[0]
            filters["period_to"] = normalized[-1]
        else:
            filters["period_from"] = normalized[0]
            filters["period_to"] = normalized[-1]
    return normalized


def _format_value(value: Any, suffix: str = "") -> str:
    if value is None:
        return "unavailable"
    return f"{value:,.2f}{suffix}" if isinstance(value, (int, float)) else f"{value}{suffix}"


class Assistant:
    """Local query helper. Python analysis is the sole source of facts."""

    def __init__(self, store: Any, model_path: str | Path | None = None):
        self.store = store
        self.model_path = Path(model_path).expanduser() if model_path else None
        self._model = None
        self._model_error: str | None = None
        self._model_attempted = False

    def _load_model(self) -> Any:
        if self._model_attempted:
            return self._model
        self._model_attempted = True
        if self.model_path is None:
            return None
        try:
            if not self.model_path.is_file():
                raise FileNotFoundError(f"Selected local model file does not exist: {self.model_path}")
            size = self.model_path.stat().st_size
            if size > 1_000_000_000:
                raise ValueError("Selected GGUF model exceeds the 1 GB local model limit.")
            if self.model_path.suffix.casefold() != ".gguf":
                raise ValueError("Selected model must be a local .gguf file.")
            try:
                from llama_cpp import Llama
            except ImportError as error:
                raise RuntimeError("Local model selected, but llama_cpp is not installed. Install the optional local-ai extra.") from error
            self._model = Llama(
                model_path=str(self.model_path),
                n_ctx=2048,
                n_threads=4,
                n_gpu_layers=0,
                verbose=False,
            )
        except Exception as error:
            self._model_error = str(error)
            self._model = None
        return self._model

    def _model_commentary(self, result: dict[str, Any]) -> str | None:
        model = self._load_model()
        if model is None:
            return None
        metrics = result.get("metrics", {})
        actual = metrics.get("actual")
        budget = metrics.get("budget")
        last_year = metrics.get("last_year")
        budget_status = "unavailable"
        if isinstance(actual, (int, float)) and isinstance(budget, (int, float)) and budget != 0:
            budget_status = "above" if actual > budget else "below" if actual < budget else "at"
        growth_status = "unavailable"
        if isinstance(actual, (int, float)) and isinstance(last_year, (int, float)) and last_year != 0:
            growth_status = "grew" if actual > last_year else "declined" if actual < last_year else "unchanged"
        attendance_status = "available" if metrics.get("attendance_rate_pct") is not None else "unavailable"
        qualitative_facts = (
            f"Sales versus budget: {budget_status}.\n"
            f"Sales versus last year: {growth_status}.\n"
            f"Attendance evidence: {attendance_status}."
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Write one brief qualitative summary using only the supplied conditions. "
                    "Do not add numbers, names, causes, advice, recommendations, predictions, "
                    "or employee judgments. Do not infer other facts. If the conditions do not "
                    "support a useful summary, explicitly say there is not enough evidence."
                ),
            },
            {
                "role": "user",
                "content": f"Python-derived qualitative conditions:\n{qualitative_facts}",
            },
        ]
        try:
            response = model.create_chat_completion(
                messages=messages,
                max_tokens=64,
                temperature=0.0,
            )
            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            text = _text(message.get("content")).strip() if isinstance(message, dict) else ""
            text = re.sub(r"^\s*[-*#]+\s*", "", text)
            if not self._safe_model_summary(text, budget_status, growth_status, attendance_status):
                return None
            return text
        except Exception as error:
            self._model_error = f"Local model inference failed: {error}"
            return None

    @staticmethod
    def _safe_model_summary(
        text: str,
        budget_status: str,
        growth_status: str,
        attendance_status: str,
    ) -> bool:
        """Accept only short wording composed of supported qualitative claims."""
        if not text or len(text) > 240 or "\n" in text or _NUMBER_TOKEN.search(text):
            return False
        if re.search(r"[!?]", text):
            return False
        words = re.findall(r"[a-z]+(?:-[a-z]+)*", text.casefold())
        if not words or any(word not in _MODEL_WORDS for word in words):
            return False
        normalized = text.casefold().strip()
        if re.fullmatch(r"(?:there is )?(?:not enough|insufficient) evidence[.]?", normalized):
            return True

        clauses = [
            clause.strip()
            for clause in re.split(r"\s+(?:and|but|while)\s+|[,;.]",
                                   normalized)
            if clause.strip()
        ]
        has_supported_claim = False
        budget_terms = re.compile(r"\b(?:budget|plan|target)\b")
        for clause in clauses:
            clause_words = set(re.findall(r"[a-z]+(?:-[a-z]+)*", clause))
            budget_patterns = {
                status: any(re.search(pattern, clause) for pattern in patterns)
                for status, patterns in _BUDGET_DIRECTIONS.items()
            }
            mentions_budget = budget_terms.search(clause) is not None
            if mentions_budget:
                if "not" in clause_words:
                    return False
                if budget_status == "unavailable":
                    if "unavailable" not in clause_words or any(budget_patterns.values()):
                        return False
                elif not budget_patterns.get(budget_status) or any(
                    matched for status, matched in budget_patterns.items() if status != budget_status
                ):
                    return False
                else:
                    has_supported_claim = True

            growth_directions = set().union(*_GROWTH_DIRECTIONS.values())
            growth_words = clause_words & growth_directions
            compares_years = (
                {"last", "year"}.issubset(clause_words)
                or {"prior", "year"}.issubset(clause_words)
                or "year-over-year" in clause_words
                or {"year", "over"}.issubset(clause_words)
            )
            if growth_words or compares_years:
                if "not" in clause_words:
                    return False
                if growth_status == "unavailable":
                    if not ("unavailable" in clause_words and not growth_words):
                        return False
                elif (
                    not growth_words & _GROWTH_DIRECTIONS[growth_status]
                    or growth_words - _GROWTH_DIRECTIONS[growth_status]
                ):
                    return False
                else:
                    has_supported_claim = True

            if "attendance" in clause_words:
                if attendance_status not in clause_words:
                    return False
                has_supported_claim = True

        return has_supported_claim

    def ask(self, question: str, filters: dict[str, Any] | None = None) -> str:
        question = _text(question)
        active_filters = dict(filters or {})
        dates = _date_overrides(question, active_filters)
        if re.search(r"\b(daily|per day|day by day)\b", question, re.IGNORECASE):
            active_filters["kind"] = "sales_daily"
        elif re.search(r"\b(mtd|month.to.date|monthly snapshot)\b", question, re.IGNORECASE):
            active_filters["kind"] = "sales_mtd"

        as_of = _latest_date(active_filters, dates)
        roster = _employee_roster(self.store, as_of)
        found_employees = _match_employees(roster, question)
        explicit_employee, requested_employee = _employee_intent(question)
        if len(found_employees) > 1:
            options = [
                f"{_text(person.get('employee_name')) or 'Unnamed'} "
                f"[{_text(person.get('employee_id') or person.get('employee_code')) or 'no code'}]"
                for person in found_employees
            ]
            return "Offline assistant — deterministic lookup\nAmbiguous employee match. Please specify a unique employee code: " + "; ".join(options)
        previous_employee_filter = _text(active_filters.get("employee"))
        employee_filter_overridden = False
        if len(found_employees) == 1:
            resolved_code = (
                _text(found_employees[0].get("employee_id") or found_employees[0].get("employee_code"))
                or _text(found_employees[0].get("employee_name"))
            )
            employee_filter_overridden = bool(previous_employee_filter and previous_employee_filter.casefold() != resolved_code.casefold())
            active_filters["employee"] = resolved_code
        elif explicit_employee:
            requested_display = requested_employee or "unspecified employee"
            return (
                "Offline assistant — deterministic lookup\n"
                f"No matching employee '{requested_display}' was found in the as-of roster "
                f"({as_of or 'latest available'}). No all-location analysis was run."
            )

        _dimension_override(self.store, question, active_filters)
        result = analyze(self.store, active_filters)
        metrics = result.get("metrics", {})

        lines = ["Offline assistant — deterministic analysis"]
        if employee_filter_overridden:
            lines.append(
                f"Question employee selection '{active_filters.get('employee')}' overrides UI employee filter '{previous_employee_filter}'."
            )
        if active_filters.get("employee"):
            employee_code = _text(active_filters.get("employee"))
            lines.append(f"Employee lookup: {employee_code} (as-of roster period {as_of or 'latest available'}).")
            if found_employees and len(found_employees) == 1:
                employee = found_employees[0]
                assignment = ", ".join(
                    f"{key} {_text(employee.get(key))}"
                    for key in ("store", "department", "section")
                    if _text(employee.get(key))
                )
                if assignment:
                    lines.append(f"Roster assignment: {assignment}.")
        period_label = (
            f"{active_filters.get('period_from', '')} to {active_filters.get('period_to', '')}".strip()
            if active_filters.get("period_from") or active_filters.get("period_to")
            else "latest available period"
        )
        scope_labels = [
            f"{label}={active_filters[key]}"
            for key, label in (
                ("country", "country"),
                ("store", "store"),
                ("department", "department"),
                ("section", "section"),
            )
            if active_filters.get(key)
        ]
        scope_text = ", ".join(scope_labels) if scope_labels else "all available locations"
        lines.append(f"Scope: {period_label}; kind={active_filters.get('kind', 'sales_mtd')}; {scope_text}.")
        for key, label, suffix in (
            ("actual", "Actual", ""),
            ("budget", "Budget", ""),
            ("last_year", "Last year", ""),
            ("budget_achievement_pct", "Budget achievement", "%"),
            ("sales_growth_pct", "Sales growth", "%"),
            ("attendance_rate_pct", "Attendance rate", "%"),
            ("hours", "Recorded hours", ""),
            ("employee_count", "Employees in scope", ""),
            ("direct_reports", "Direct reports", ""),
            ("productivity", "Source-reported productivity", ""),
            ("oos_value", "Source-reported OOS value", ""),
            ("oos_pct", "Source-reported OOS percentage", "%"),
        ):
            lines.append(f"{label}: {_format_value(metrics.get(key), suffix)}.")
        if metrics.get("actual") is None and not result.get("rows"):
            lines.append("No matching sales data is available; missing values are not treated as zero.")
        if result.get("trends") and re.search(r"\b(trend|history|historical|compare|comparison|over time)\b", question, re.IGNORECASE):
            lines.append("Historical comparison (computed from non-overlapping selected records):")
            for trend in result["trends"]:
                lines.append(
                    f"- {trend['period']}: actual {_format_value(trend.get('actual'))}; "
                    f"budget achievement {_format_value(trend.get('budget_achievement_pct'), '%')}; "
                    f"sales growth vs source last year {_format_value(trend.get('sales_growth_pct'), '%')}."
                )
        lines.extend(result.get("warnings", []))
        if result.get("sources"):
            citations = []
            for source in result["sources"]:
                description = " / ".join(str(source.get(field)) for field in ("kind", "period", "source", "sheet") if source.get(field))
                if source.get("import_id") is not None:
                    description += f" [import {source['import_id']}]"
                citations.append(description or "local active import")
            lines.append("Sources: " + "; ".join(dict.fromkeys(citations)) + ".")
        else:
            lines.append("Sources: no matching active local imports.")

        model_text = self._model_commentary(result)
        if model_text:
            lines.append(
                "Local model wording (unverified; review before sharing; not a source of facts): "
                f"{model_text}"
            )
        elif self.model_path is not None:
            if self._model is None:
                lines.append(f"Local model unavailable: {self._model_error or 'model could not be loaded'}.")
            elif self._model_error:
                lines.append(f"Local model summary unavailable: {self._model_error}.")
            else:
                lines.append("Local model summary unavailable: generated wording was rejected by safety validation.")

        return "\n".join(lines)