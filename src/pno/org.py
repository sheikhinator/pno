"""Who is who: roles, reporting lines and each manager's area of responsibility.

Rules agreed with HR:
- Store Manager / General Manager → whole store (Total Store). In H&B stores the Deputy / Store Manager.
- Department Head → their department in their store.
- Section Manager / Supervisor / Team Leader → the sections their team works in (Khalid runs Bakery + Deli).
- CCO supervisor / manager → the CCO.
- Everyone else → staff: own attendance plus their section's result as team context.
Reporting managers are written as names in the roster, and names repeat, so they are matched in the same store first.
"""

from __future__ import annotations

import re

from .util import norm

# roster section keywords → BO section codes (longest keyword wins)
SECTION_KEYWORDS = [
    ("DAIRY COUNTER", ["S051"]), ("DELICATESSEN COUNTER", ["S050"]), ("DELI COUNTER", ["S050"]),
    ("DELICATESSEN SS", ["S023"]), ("DAIRY PRODUCTS", ["S022"]), ("ULTRA FRESH", ["S021"]), ("FROZEN", ["S026"]),
    ("POULTRY", ["S025"]), ("BEVERAGE", ["S011"]), ("DPH", ["S012"]), ("DETERGENT", ["S012"]), ("CIGARETTE", ["S013"]),
    ("GROCERY", ["S014"]), ("DRY FOOD", ["S014"]), ("BAKERY", ["S054"]), ("PASTRY", ["S054"]), ("BUTCHERY", ["S052"]),
    ("FISHERY", ["S053"]), ("FRUITS", ["S056"]), ("VEGETABLES", ["S056"]), ("COFFEE", ["S057"]), ("DELICATESSEN", ["S050"]),
    ("DELI", ["S050"]), ("HOUSEHOLD GOODS", ["S080"]), ("PHOTO", ["S081"]), ("OFFICE AUTOMATION", ["S082"]),
    ("MOBILITY", ["S083"]), ("MOBILE", ["S083"]), ("GIFT AND SHOP", ["S084"]), ("TV", ["S085"]), ("HI FI", ["S086"]),
    ("HOUSEHOLD APPL", ["S087"]), ("TOOLS", ["S030"]), ("DIY", ["S030"]), ("HOUSE WARE", ["S031"]), ("HOUSEWARE", ["S031"]),
    ("STATIONARY", ["S032"]), ("STATIONERY", ["S032"]), ("CAMPING", ["S033"]), ("GARDEN", ["S033"]),
    ("HOUSE EQUIPMENT", ["S034"]), ("CAR", ["S035"]), ("TOYS", ["S036"]), ("LIBRARY", ["S037"]), ("BOOK", ["S037"]),
    ("SPORTS", ["S039"]), ("LUGGAGE", ["S071"]), ("HOME LINEN", ["S040"]), ("BABY", ["S041"]), ("CHILDREN", ["S042"]),
    ("KIDS", ["S042"]), ("LADIES", ["S043"]), ("WOMEN", ["S043"]), ("MEN", ["S044"]), ("SHOES", ["S060"]),
    ("FOOTWEAR", ["S060"]), ("ACCESSORIES", ["S061"]), ("GIFT STAND", ["S062"]),
]
SECTION_KEYWORDS.sort(key=lambda kv: -len(kv[0]))
PREFIX_DEPT = {"CGD": "01", "FFD": "02", "MKT": "02", "LHH": "03", "HHH": "04", "TXT": "05", "CCO": "11"}
DEPT_NAMES = {"01": "Consumer Goods", "02": "Fresh Food", "03": "Light Household", "04": "Heavy Household",
              "05": "Textile", "06": "Health & Beauty", "11": "Central Cashier Office", "15": "E-commerce", "99": "Services"}
SERVICE_PREFIXES = {"CCS", "DIG", "MNT", "M AND S", "P AND O", "Q AND H", "REC", "RSK", "SEC", "ADM", "HR", "FIN", "LOG"}
MANAGERISH = re.compile(r"SECTION MANAGER|SUPERVISOR|TEAM LEADER|ASSISTANT MANAGER|\bMANAGER\b|\bHEAD\b|INCHARGE|IN CHARGE")

ROLE_LABEL = {"GM": "Store Manager", "HBM": "H&B Store Lead", "DH": "Department Head", "SM": "Section Manager",
              "CCO": "CCO Manager", "AREA": "Area Manager", "STAFF": "Staff"}


def section_prefix(section_raw: str) -> str:
    n = norm(section_raw)
    m = re.match(r"^([A-Z]{2,4}(?: AND [A-Z])?)\s", n)
    return m.group(1) if m else ""


def map_section(section_raw: str, dept_code: str = "", overrides: dict | None = None) -> dict:
    """Roster section → what it is measured on: {'codes': [...]} or {'dept': '01'} or {'store': True} or {}."""
    n = norm(section_raw)
    if overrides and n in overrides:
        return overrides[n]
    if not n:
        return {}
    prefix = section_prefix(section_raw)
    if prefix in SERVICE_PREFIXES:
        return {"service": True}
    if prefix == "MGM" or "MANAGEMENT" in n:
        return {"store": True}
    body = n[len(prefix):].strip() if prefix else n
    if "COMMON" in body or "(COMMON)" in section_raw.upper():
        d = dept_code or PREFIX_DEPT.get(prefix, "")
        if prefix == "OTH" or d == "06":
            return {"store": True}
        return {"dept": d} if d else {}
    if prefix == "CCO":
        return {"cco": True}
    for kw, codes in SECTION_KEYWORDS:
        if re.search(rf"\b{kw}\b", body):
            return {"codes": list(codes)}
    if prefix in PREFIX_DEPT:
        return {"dept": PREFIX_DEPT[prefix]}
    return {}


def role_of(designation: str, store_format: str, dept_code: str, section_raw: str, has_reports: bool) -> str:
    d = norm(designation)
    if "STORE MANAGER" in d or "GENERAL MANAGER" in d or d in ("GM", "SM STORE MANAGER"):
        return "HBM" if store_format == "HB" else "GM"
    if store_format == "HB" and ("DEPUTY MANAGER" in d or "STORE HEAD" in d or "MANAGER" in d):
        return "HBM"
    if re.search(r"DEPARTMENT (HEAD|MANAGER)|DEPT (HEAD|MANAGER)|HEAD OF DEPARTMENT", d):
        return "DH"
    sec = norm(section_raw)
    if (dept_code == "11" or sec.startswith("CCO")) and MANAGERISH.search(d):
        return "CCO"
    if "SECTION MANAGER" in d or (MANAGERISH.search(d) and has_reports):
        return "SM"
    return "STAFF"


def clean_manager(name: str) -> tuple[str, str]:
    """'Muhammad Waqas #60004169' → ('Muhammad Waqas', '60004169')."""
    if not name:
        return "", ""
    if " #" in name:
        a, b = name.rsplit(" #", 1)
        return a.strip(), b.strip()
    return name.strip(), ""
