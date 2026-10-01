"""Readable worksheet provenance and row-qualified candidate identity helpers."""

from __future__ import annotations

import re
from typing import Any

_IDENTITY_SUFFIX = re.compile(r" \[PNO header row (\d+)\]$")


def candidate_key(candidate: Any) -> str:
    return f"{candidate.sheet}\x1f{candidate.header_row}"


def stored_sheet_identity(sheet: str, header_row: int, qualify: bool) -> str:
    if not qualify:
        return sheet
    return f"{sheet} [PNO header row {header_row}]"


def split_sheet_identity(value: Any) -> tuple[str, str | None]:
    """Separate stored disambiguation metadata without losing the actual sheet name."""
    text = str(value or "")
    match = _IDENTITY_SUFFIX.search(text)
    if not match:
        return text, None
    return text[: match.start()], match.group(1)