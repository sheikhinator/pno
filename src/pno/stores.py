"""One store list for every report.

The same store is written differently in each report:
    roster / attendance   H&B PK LAH FORTRESS STADIUM      HM PK FAI Lyallpur Galleria
    BO 200-10-05          H&B PK LAH Fortress              HB PK LAH H&B PAK LAH EMP (MYLI)
    productivity          663 FAI Lyallpur Galleria        652 LAH High Street Paragon Ci   (no format, may be cut short)
Names are matched within the same city and format; links PNO is unsure about are listed for HR to confirm once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .db import Database
from .util import clean_text, norm

FORMATS = {"HM": "HM", "SM": "SM", "HB": "HB", "H AND B": "HB", "H&B": "HB"}
FORMAT_LABEL = {"HM": "Hypermarket", "SM": "Supermarket", "HB": "Health & Beauty", "HO": "Office", "": "Store"}
CITIES = {"LAH": "Lahore", "KCH": "Karachi", "KHI": "Karachi", "ISL": "Islamabad", "FAI": "Faisalabad",
          "GUJ": "Gujranwala", "RWP": "Rawalpindi", "MUL": "Multan", "PSH": "Peshawar", "SKT": "Sialkot",
          "HYD": "Hyderabad", "QTA": "Quetta"}
NOISE = {"PK", "PAK", "MYLI", "MALL", "STADIUM", "PHASE", "CITY", "THE", "STORE", "H", "AND", "B", "HB", "HM", "SM"}
OFFICE = re.compile(r"\b(HEAD OFFICE|HO|CORPORATE|SUPPORT OFFICE|REGIONAL OFFICE|COUNTRY OFFICE)\b")


@dataclass
class Parsed:
    raw: str
    format: str
    city: str
    name: str
    code: str
    tokens: list[str]
    is_ho: bool


def parse_name(raw: str) -> Parsed:
    text = clean_text(raw)
    n = norm(text)
    code = ""
    m = re.match(r"^(\d{3,4})\s+(.*)$", n)
    if m:
        code, n = m.group(1), m.group(2)
    fmt = ""
    m = re.match(r"^(H AND B|HM|SM|HB)\s+(.*)$", n)
    if m:
        fmt, n = FORMATS[m.group(1)], m.group(2)
    n = re.sub(r"^PK\s+", "", n)
    city = ""
    m = re.match(r"^([A-Z]{3})\s+(.*)$", n)
    if m and m.group(1) in CITIES:
        city, n = m.group(1), m.group(2)
    # 'H AND B PAK LAH EMP MYLI' style repeats of the format and city inside the name
    n = re.sub(r"\bH AND B\b", " ", n)
    if city:
        n = re.sub(rf"\b{city}\b", " ", n)
    tokens = [t for t in n.split() if t not in NOISE]
    is_ho = bool(OFFICE.search(norm(text)))
    disp = _display(text, code, fmt, city)
    return Parsed(raw=text, format="HO" if is_ho and not fmt else fmt, city=city, name=disp, code=code,
                  tokens=tokens or n.split(), is_ho=is_ho)


def _display(text: str, code: str, fmt: str, city: str) -> str:
    s = clean_text(text)
    s = re.sub(r"^\d{3,4}\s+", "", s)
    s = re.sub(r"^(H&B|HM|SM|HB)\s+", "", s, flags=re.I)
    s = re.sub(r"^PK\s+", "", s, flags=re.I)
    if city:
        s = re.sub(rf"^{city}\s+", "", s, flags=re.I)
    s = re.sub(r"^H&B\s+PAK\s+[A-Z]{3}\s+", "", s, flags=re.I)
    s = re.sub(r"\s*\(?MYLI\)?\s*$", "", s, flags=re.I).strip()
    if s.isupper() and len(s) > 3:
        s = " ".join(w if len(w) <= 3 or any(ch.isdigit() for ch in w) else w.capitalize() for w in s.split())
    return s or text


def _tok_match(a: str, b: str) -> bool:
    if a == b:
        return True
    if a.isdigit() or b.isdigit():
        return False
    if len(a) >= 2 and len(b) >= 2 and (b.startswith(a) or a.startswith(b)):
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 3 and short[0] == long_[0]:
        it = iter(long_)
        return all(ch in it for ch in short)          # LUK ~ LUCKY, EMP ~ EMPORIUM
    return False


def similarity(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    used, m = set(), 0
    for t in a:
        for j, u in enumerate(b):
            if j not in used and _tok_match(t, u):
                used.add(j)
                m += 1
                break
    return 0.5 * m / len(a) + 0.5 * m / len(b)


class StoreResolver:
    """Finds or creates the store for a name written in a report. Cached per import for speed."""

    def __init__(self, db: Database, source: str = ""):
        self.db = db
        self.source = source
        self.cache: dict[str, int | None] = {}
        self.unsure: list[str] = []

    def resolve(self, raw) -> int | None:
        text = clean_text(raw)
        if not text:
            return None
        alias = norm(text)
        if alias in self.cache:
            return self.cache[alias]
        r = self.db.q1("SELECT store_id FROM store_aliases WHERE alias=?", (alias,))
        if r:
            self.cache[alias] = r[0]
            return r[0]
        p = parse_name(text)
        sid, sure = self._match(p)
        if sid is None:
            key = f"{p.format}|{p.city}|{' '.join(p.tokens)}"
            ex = self.db.q1("SELECT id FROM stores WHERE key=?", (key,))
            if ex:
                sid = ex[0]
            else:
                sid = self.db.x("INSERT INTO stores(key, name, format, city, code, is_ho) VALUES(?,?,?,?,?,?)",
                                (key, p.name, p.format, p.city, p.code, int(p.is_ho))).lastrowid
            sure = True
        else:
            st = self.db.q1("SELECT name, code, format FROM stores WHERE id=?", (sid,))
            # keep the most complete display name (productivity names can be cut short)
            if p.code and not st["code"]:
                self.db.x("UPDATE stores SET code=? WHERE id=?", (p.code, sid))
            if p.format and not st["format"]:
                self.db.x("UPDATE stores SET format=? WHERE id=?", (p.format, sid))
            if len(p.name) > len(st["name"]) and not p.code and "MYLI" not in norm(text) and p.format:
                self.db.x("UPDATE stores SET name=? WHERE id=?", (p.name, sid))
        self.db.x("INSERT OR IGNORE INTO store_aliases(alias, raw, store_id, confirmed, source) VALUES(?,?,?,?,?)",
                  (alias, text, sid, 1 if sure else 0, self.source))
        if not sure:
            self.unsure.append(text)
        self.cache[alias] = sid
        return sid

    def _match(self, p: Parsed) -> tuple[int | None, bool]:
        rows = self.db.q("SELECT id, key, format, city FROM stores")
        best, best_s, second = None, 0.0, 0.0
        for r in rows:
            fmt, city, toks = r["key"].split("|", 2)
            if p.city and city and p.city != city:
                continue
            if p.format and fmt and p.format != fmt:
                continue
            if not p.format and fmt == "HB":          # productivity rows have no format: they are HM / SM stores
                continue
            s = similarity(p.tokens, toks.split())
            if s > best_s:
                best, best_s, second = r["id"], s, best_s
            elif s > second:
                second = s
        if best is None or best_s < 0.6 or abs(best_s - second) < 1e-9:
            return None, True
        sure = best_s >= 0.99 and (second < 0.6)
        return best, sure


def store_label(row) -> str:
    fmt = row["format"] if row["format"] else ""
    return f"{row['name']}" + (f" · {fmt}" if fmt and fmt != "HO" else "")
