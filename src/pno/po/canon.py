"""Name normalisation shared by the P&O workbook importers and insights.

Every workbook tab spells stores, sections and people differently
("L.H.H.", "03-LHH", "LHH - Light Household (Common)"). These helpers map each
variant to one canonical label so the tabs can be joined. Matching is rule
based and transparent; anything unrecognised is returned unchanged rather
than guessed.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------- stores --

# (canonical name, city, format, keyword patterns). Order matters: the first
# match wins, so more specific patterns come first.
_STORES: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("LAH Fortress", "Lahore", "Hypermarket", (r"fortress",)),
    ("LAH Packages Mall", "Lahore", "Hypermarket", (r"packages",)),
    ("LAH Emporium Mall", "Lahore", "Hypermarket", (r"emporium", r"\bemp\b")),
    ("KCH Lucky One", "Karachi", "Hypermarket", (r"lucky", r"\bluk\b")),
    ("KCH Dolmen City Mall", "Karachi", "Hypermarket", (r"dolmen",)),
    ("GUJ Steel Casting", "Gujranwala", "Hypermarket", (r"steel\s*casting", r"\bstc\b", r"gujranwala", r"\bguj\b")),
    ("FAI Lyallpur Galleria", "Faisalabad", "Hypermarket", (r"lyallpur", r"\bfai\b", r"faisalabad")),
    ("ISL WTC", "Islamabad", "Hypermarket", (r"\bwtc\b",)),
    ("ISL D12 (DIZ Markaz)", "Islamabad", "Supermarket", (r"\bd12\b", r"diz\s*markaz", r"\bp06\b", r"\bp61\b")),
    ("LAH Askari 10", "Lahore", "Supermarket", (r"askari",)),
    ("LAH DHA Rahbar", "Lahore", "Supermarket", (r"rahbar",)),
    ("LAH DHA Phase 7", "Lahore", "Supermarket", (r"dha\s*(phase)?\s*7\b",)),
    ("LAH Paragon City", "Lahore", "Supermarket", (r"paragon", r"high\s*street")),
    ("LAH Avenue Mall", "Lahore", "Supermarket", (r"avenue",)),
]

_STORE_PATTERNS = [
    (name, city, fmt, [re.compile(p, re.IGNORECASE) for p in patterns])
    for name, city, fmt, patterns in _STORES
]

CITY_ALIASES = {
    "lahore": "Lahore", "lah": "Lahore",
    "karachi": "Karachi", "kch": "Karachi", "khi": "Karachi",
    "islamabad": "Islamabad", "isl": "Islamabad",
    "faisalabad": "Faisalabad", "fai": "Faisalabad",
    "gujranwala": "Gujranwala", "guj": "Gujranwala",
}


def text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def is_health_beauty(value: Any) -> bool:
    raw = text(value).casefold()
    return raw.startswith(("h&b", "hb ")) or "myli" in raw or " h&b " in f" {raw} "


def store(value: Any) -> str:
    """Canonical store name; Health & Beauty (Myli) outlets get their own label."""
    raw = text(value)
    if not raw or raw.startswith("#"):
        return ""
    for name, _city, _fmt, patterns in _STORE_PATTERNS:
        if any(p.search(raw) for p in patterns):
            return f"{name} · Myli" if is_health_beauty(raw) else name
    return raw


def store_city(name: str) -> str:
    base = name.replace(" · Myli", "")
    for canonical, city, _fmt, _patterns in _STORES:
        if canonical == base:
            return city
    return ""


def store_format(name: str) -> str:
    if name.endswith(" · Myli"):
        return "Health & Beauty"
    for canonical, _city, fmt, _patterns in _STORES:
        if canonical == name:
            return fmt
    return ""


def city(value: Any) -> str:
    raw = text(value).casefold()
    for key, label in CITY_ALIASES.items():
        if re.search(rf"\b{re.escape(key)}\b", raw):
            return label
    return ""


# -------------------------------------------------------------- sections --

# Canonical sections and the department family each belongs to.
DEPARTMENT_OF = {
    "Beverages": "Consumer Goods",
    "DPH": "Consumer Goods",
    "Grocery": "Consumer Goods",
    "OPSS": "Consumer Goods",
    "Consumer Goods": "Consumer Goods",
    "Bakery": "Fresh Food",
    "Butchery": "Fresh Food",
    "Fishery": "Fresh Food",
    "Deli": "Fresh Food",
    "Fruits & Vegetables": "Fresh Food",
    "Fresh Food": "Fresh Food",
    "Light Household": "Light Household",
    "Heavy Household": "Heavy Household",
    "Non Food": "Non Food",
    "Textile": "Textile",
    "Myli": "Health & Beauty",
    "CCO": "Services",
    "Services": "Services",
    "Management": "Management",
    "Overall": "Overall",
    "Other Sections": "Overall",
}

DEPARTMENT_ORDER = [
    "Consumer Goods", "Fresh Food", "Light Household", "Heavy Household",
    "Non Food", "Textile", "Health & Beauty", "Services", "Management", "Overall",
]

SECTION_ORDER = [
    "Beverages", "DPH", "Grocery", "OPSS", "Bakery", "Butchery", "Fishery", "Deli",
    "Fruits & Vegetables", "Light Household", "Heavy Household", "Textile", "Myli", "CCO",
]

# Section codes used by the periodic store performance (sales) report.
SALES_CODE = {
    "S011": "Beverages", "S012": "DPH", "S013": "Grocery", "S014": "Grocery",
    "S021": "OPSS", "S022": "OPSS", "S023": "OPSS", "S025": "OPSS", "S026": "OPSS",
    "S050": "Deli", "S051": "Deli", "S052": "Butchery", "S053": "Fishery",
    "S054": "Bakery", "S056": "Fruits & Vegetables", "S057": "Fresh Food",
    "X111": "Myli",
}
for _code in ("S030", "S031", "S032", "S033", "S034", "S035", "S036", "S037", "S039", "S071"):
    SALES_CODE[_code] = "Light Household"
for _code in ("S040", "S041", "S042", "S043", "S044", "S060", "S061", "S062"):
    SALES_CODE[_code] = "Textile"
for _code in ("S080", "S081", "S082", "S083", "S084", "S085", "S086", "S087"):
    SALES_CODE[_code] = "Heavy Household"

# Keyword rules, checked in order. Patterns use word boundaries where a short
# token could appear inside an unrelated word ("men" in "management").
_SECTION_RULES: list[tuple[str, str]] = [
    (r"overall\s*store", "Overall"),
    (r"other\s*store\s*sections", "Other Sections"),
    (r"\bcco\b|cashier|central\s*cash", "CCO"),
    (r"myli|health\s*(and|&)\s*beauty|\bh&b\b", "Myli"),
    (r"baby\s*hygiene|\bdph\b|d\.p\.h|detergent", "DPH"),
    (r"beverag|baverag|\bbev\b", "Beverages"),
    (r"deli(?!very)|del\.?\s*count|dairy\s*counter|\bs05[01]\b", "Deli"),
    (r"grocery|dry\s*groc|dry\s*food|dry\s*packaged", "Grocery"),
    (r"opss|o\.p\.s\.s|frozen|refrigerated|dairy\s*prod|ultra\s*fresh|poultry", "OPSS"),
    (r"bakery|pastry", "Bakery"),
    (r"butcher", "Butchery"),
    (r"fish", "Fishery"),
    (r"fruit|\bf\s*&\s*v\b|veg", "Fruits & Vegetables"),
    (r"fresh\s*food|\bffd\b|\bfd\.|common\s*ffd|\bmarket\b", "Fresh Food"),
    (r"non[\s-]*food|\bnfd\b|nonfd", "Non Food"),
    (r"\bhhh\b|h\.h\.h|heavy\s*house|appliance|off(ice)?\s*autom|mobil|laptop|\btv\b|hh\s*goods|sound\s*system|photograph", "Heavy Household"),
    (r"\blhh\b|l\.h\.h|light\s*house|house-?ware|stationar|\btoys?\b|\bcars?\b|car\s*access|luggage|d\.i\.y|\bdiy\b|garden|sport|outdoor|camping|home\s*improvement|kitchen|^accessories$", "Light Household"),
    (r"\btxt\b|textile|\bmen\b|menswear|women|ladies|children|\bbaby\b|babywear|shoes|linen|accessory", "Textile"),
    (r"\bcgd\b|fmcg|f\.m\.c\.g|consumer\s*goods|comm\.?\s*fmcg|\bcg\b", "Consumer Goods"),
    (r"management|\bmgm\b|\bmgt\b", "Management"),
    (r"\both\b", "Services"),
    (r"receiving|\brec\b|customer\s*care|\bccs\b|maintenance|\bmnt\b|risk|\brsk\b|fulfil|decoration|security|quality|hygiene|\bq&h\b|\bit\b|services|admin", "Services"),
]
_SECTION_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in _SECTION_RULES]


def section(value: Any) -> str:
    """Canonical section for any spelling; '' if blank, original text if unknown."""
    raw = text(value)
    if not raw or raw.startswith("#"):
        return ""
    code = re.match(r"^([SX]\d{3})\b", raw)
    if code and code.group(1) in SALES_CODE:
        return SALES_CODE[code.group(1)]
    for pattern, label in _SECTION_COMPILED:
        if pattern.search(raw):
            return label
    return raw


def department(section_name: str) -> str:
    return DEPARTMENT_OF.get(section_name, "")


def sections_in(text_value: Any) -> list[str]:
    """All canonical sections mentioned in free text such as role remarks."""
    raw = text(value=text_value)
    found: list[str] = []
    # Split on connectors so "Bakery & Delicatessen Sections" yields both.
    for part in re.split(r"\s*(?:&|,|/|\band\b)\s*", raw, flags=re.IGNORECASE):
        label = section(part)
        if label in DEPARTMENT_OF and label not in found and label not in {"Overall", "Other Sections", "Management", "Services"}:
            found.append(label)
    whole = section(raw)
    if not found and whole in DEPARTMENT_OF:
        found.append(whole)
    return found


# ---------------------------------------------------------------- people --

def employee_id(value: Any) -> str:
    raw = text(value)
    if isinstance(value, float) and value.is_integer():
        raw = str(int(value))
    if re.fullmatch(r"\d+\.0", raw):
        raw = raw[:-2]
    return raw if re.fullmatch(r"[A-Za-z]*\d+[A-Za-z0-9-]*", raw) else ""


def repair_name(value: Any) -> str:
    """Undo the workbook's accidental 'am' -> 'MOR' replacement and tidy spaces."""
    name = text(value)
    if "MOR" in name or "KAmR" in name:
        name = re.sub(r"(?<=[a-z])MOR(?=[a-z])", "am", name)
        name = re.sub(r"\bMOR(?=[a-z])", "Am", name)
        name = re.sub(r"(?<=[a-z])MOR\b", "am", name)
        name = re.sub(r"(?<=\b[A-Z])MOR(?=[a-z])", "am", name)
        name = name.replace("KAmRran", "Kamran")
    name = re.sub(r"\s+\.$", "", name)
    return name


def name_key(value: Any) -> str:
    """Loose key for matching a manager name to an employee name."""
    raw = repair_name(value).casefold()
    raw = re.sub(r"[^a-z0-9 ]", " ", raw)
    raw = raw.replace("mohammad", "muhammad").replace("muhamad", "muhammad").replace("mohammed", "muhammad")
    return " ".join(raw.split())


ROLE_RANK = {
    "store manager": 6, "deputy manager": 5, "department head": 4, "c.c.o manager": 4,
    "section manager": 3, "team leader": 2, "supervisor": 1,
}


def role_rank(designation: Any) -> int:
    return ROLE_RANK.get(text(designation).casefold(), 0)


def is_leader(designation: Any) -> bool:
    return role_rank(designation) >= 1


# ---------------------------------------------------------------- shifts --

SHIFT_ORDER = ["Morning", "Mid", "Evening", "Off", "Leave", "Inventory", "Not rostered", "Other"]


def shift(value: Any) -> str:
    raw = text(value).casefold()
    if not raw:
        return "Not rostered"
    if raw.startswith("mor") or raw == "morning":
        return "Morning"
    if raw.startswith("mid"):
        return "Mid"
    if raw.startswith(("eve", "clos")):
        return "Evening"
    if "off" in raw and "tol" not in raw:
        return "Off"
    if raw in {"al", "c/l", "cl", "sl", "tol", "leave", "ml"} or "leave" in raw:
        return "Leave"
    if "inventory" in raw:
        return "Inventory"
    return "Other"
