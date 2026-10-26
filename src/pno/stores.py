"""One store list for every report.

The same store is written differently in each report:
    roster / attendance   H&B PK LAH FORTRESS STADIUM      HM PK FAI Lyallpur Galleria
    BO 200-10-05          H&B PK LAH Fortress              HB PK LAH H&B PAK LAH EMP (MYLI)
    productivity          663 FAI Lyallpur Galleria        652 LAH High Street Paragon Ci   (no format, may be cut short)
Names are matched within the same city and format; links PNO is unsure about are listed for HR to confirm once.
"""

from __future__ import annotations

import re
from functools import lru_cache
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
    canon: str = ""          # the known store this is (catalogue name without format), e.g. 'LAH Packages Mall'


_CITY_CODE = {"Lahore": "LAH", "Karachi": "KCH", "Islamabad": "ISL", "Faisalabad": "FAI", "Gujranwala": "GUJ"}


@lru_cache(maxsize=50000)
def canon_store(text: str) -> str:
    """The catalogue store a name points to, whatever the format ('H&B … EMP (MYLI)' and 'HM … Emporium' → 'LAH Emporium Mall')."""
    from .po import canon
    c = canon.store(text)
    base = c.replace(" · Myli", "")
    return base if any(base == n for n, *_ in canon._STORES) else ""


def parse_name(raw: str) -> Parsed:
    text = clean_text(raw)
    n = norm(text)
    code = ""
    m = re.match(r"^(\d{3,4})\s+(.*)$", n)
    if m:
        code, n = m.group(1), m.group(2)
    fmt = ""
    n = re.sub(r"^PK\s+(?=(H AND B|HM|SM|HB)\s)", "", n)          # 'PK HM GUJ Steel Casting' = 'HM PK GUJ …'
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
    cn = "" if is_ho else canon_store(text)
    if cn:
        from .po import canon
        city = city or _CITY_CODE.get(canon.store_city(cn), "")
        disp = cn.split(" ", 1)[1] if cn[:3] in _CITY_CODE.values() else cn
        tokens = [t for t in norm(disp).split() if t not in NOISE] or tokens
    return Parsed(raw=text, format="HO" if is_ho and not fmt else fmt, city=city, name=disp, code=code,
                  tokens=tokens or n.split(), is_ho=is_ho, canon=cn)


def _display(text: str, code: str, fmt: str, city: str) -> str:
    s = clean_text(text)
    s = re.sub(r"^\d{3,4}\s+", "", s)
    s = re.sub(r"^PK\s+(?=(H&B|HM|SM|HB)\s)", "", s, flags=re.I)
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
                self._rekey(sid, p.format)
            if len(p.name) > len(st["name"]) and not p.code and "MYLI" not in norm(text) and p.format:
                self.db.x("UPDATE stores SET name=? WHERE id=?", (p.name, sid))
        self.db.x("INSERT OR IGNORE INTO store_aliases(alias, raw, store_id, confirmed, source) VALUES(?,?,?,?,?)",
                  (alias, text, sid, 1 if sure else 0, self.source))
        if not sure:
            self.unsure.append(text)
        self.cache[alias] = sid
        return sid

    def _match(self, p: Parsed) -> tuple[int | None, bool]:
        rows = self.db.q("SELECT id, key, name, format, city FROM stores")
        best, best_s, second = None, 0.0, 0.0
        for r in rows:
            kfmt, city, toks = r["key"].split("|", 2)
            fmt = r["format"] if r["format"] and r["format"] != "HO" else kfmt   # the key keeps the first format seen (may be blank)
            if p.city and city and p.city != city:
                continue
            if p.format and fmt and p.format != fmt:
                continue
            if not p.format and fmt == "HB":          # productivity rows have no format: they are HM / SM stores
                continue
            rc = canon_store(f"{city} {r['name']}") or canon_store(f"{city} {toks}")
            if p.canon and rc:
                s = 1.0 if rc == p.canon else 0.0           # both are known stores: same store or not, no guessing
            else:
                s = similarity(p.tokens, toks.split())
            if s > best_s:
                best, best_s, second = r["id"], s, best_s
            elif s > second:
                second = s
        if best is None or best_s < 0.6 or abs(best_s - second) < 1e-9:
            return None, True
        sure = best_s >= 0.99 and (second < 0.6)
        return best, sure


    def _rekey(self, sid: int, fmt: str) -> None:
        """A store first seen without a format (productivity) gets its format into the key, so an H&B store with the same
        name is never matched to the hypermarket again."""
        k = self.db.q1("SELECT key FROM stores WHERE id=?", (sid,))[0]
        f, rest = k.split("|", 1)
        if not f:
            new = f"{fmt}|{rest}"
            if not self.db.q1("SELECT 1 FROM stores WHERE key=? AND id!=?", (new, sid)):
                self.db.x("UPDATE stores SET key=? WHERE id=?", (new, sid))


def repair_formats(db: Database) -> list[str]:
    """Undo merges of different formats into one store (e.g. 'H&B PK LAH Packages Mall' into the Packages hypermarket).

    Older versions matched an H&B store to the hypermarket of the same name when the hypermarket was first seen in a
    file without formats (productivity). This splits them again: the H&B names get their own store and every row
    written with an H&B name moves to it. Returns the stores fixed (their sales should be imported again)."""
    fixed = []
    for st in db.q("SELECT id, key, name, format, city FROM stores"):
        aliases = db.q("SELECT alias, raw FROM store_aliases WHERE store_id=?", (st["id"],))
        by_fmt: dict[str, list] = {}
        for a in aliases:
            f = parse_name(a["raw"] or a["alias"]).format
            if f and f != "HO":
                by_fmt.setdefault(f, []).append(a)
        if len(by_fmt) < 2:
            if len(by_fmt) == 1 and not st["key"].split("|", 1)[0]:
                f = next(iter(by_fmt))
                new = f"{f}|{st['key'].split('|', 1)[1]}"
                if not db.q1("SELECT 1 FROM stores WHERE key=?", (new,)):
                    db.x("UPDATE stores SET key=?, format=COALESCE(NULLIF(format,''), ?) WHERE id=?", (new, f, st["id"]))
            continue
        keep = st["format"] if st["format"] in by_fmt else ("HM" if "HM" in by_fmt else "SM" if "SM" in by_fmt else next(iter(by_fmt)))
        rest = st["key"].split("|", 1)[1]
        db.x("UPDATE stores SET key=?, format=? WHERE id=?", (f"{keep}|{rest}", keep, st["id"]))
        for f, al in by_fmt.items():
            if f == keep:
                continue
            p = parse_name(al[0]["raw"] or al[0]["alias"])
            key = f"{f}|{p.city or st['city']}|{' '.join(p.tokens)}"
            ex = db.q1("SELECT id FROM stores WHERE key=?", (key,))
            nid = ex[0] if ex else db.x("INSERT INTO stores(key, name, format, city, code, is_ho) VALUES(?,?,?,?,?,0)",
                                        (key, p.name, f, p.city or st["city"], "")).lastrowid
            raws = [a["raw"] for a in al if a["raw"]]
            for a in al:
                db.x("UPDATE store_aliases SET store_id=? WHERE alias=?", (nid, a["alias"]))
            for tbl, col in (("roster", "bu_raw"), ("attendance_all", "bu_raw"), ("attendance", "bu_raw"), ("att_people", "bu_raw"),
                             ("sales", "store_raw"), ("productivity", "store_raw")):
                try:
                    cols = {r[1] for r in db.q(f"PRAGMA table_info({tbl})")}
                    if col in cols and raws:
                        db.x(f"UPDATE OR IGNORE {tbl} SET store_id=? WHERE store_id=? AND {col} IN ({','.join('?' * len(raws))})", (nid, st["id"], *raws))
                except Exception:  # noqa: BLE001 - a table missing in an old database
                    pass
            fixed.append(f"{st['name']} ({FORMAT_LABEL.get(f, f)})")
    # the same known store written two ways ('D12 (P06)' and 'DIZ MARKAZ', 'Steel Casting' and 'STC-Gujranwala'): one store
    groups: dict[tuple[str, str], list] = {}
    for st in db.q("SELECT id, key, name, format, city FROM stores ORDER BY id"):
        kf, city, toks = st["key"].split("|", 2)
        c = canon_store(f"{city} {st['name']}") or canon_store(f"{city} {toks}")
        if not c:
            continue
        fmt = "HB" if (st["format"] or kf) == "HB" else "main"
        groups.setdefault((c, fmt), []).append(st)
    for (c, _f), sts in groups.items():
        if len(sts) < 2:
            continue
        keep = next((x for x in sts if x["format"]), sts[0])
        for st in sts:
            if st["id"] == keep["id"]:
                continue
            for tbl in ("store_aliases", "roster", "attendance_all", "attendance", "att_people", "sales", "productivity"):
                try:
                    db.x(f"UPDATE OR IGNORE {tbl} SET store_id=? WHERE store_id=?", (keep["id"], st["id"]))
                except Exception:  # noqa: BLE001
                    pass
            left = sum(db.q1(f"SELECT COUNT(*) FROM {t} WHERE store_id=?", (st["id"],))[0] for t in ("store_aliases", "roster", "sales", "productivity"))
            if not left:
                db.x("DELETE FROM stores WHERE id=?", (st["id"],))
            fixed.append(f"{st['name']} = {keep['name']}")
    if fixed:
        db.log("repair", "stores: " + ", ".join(fixed))
    return fixed


def store_label(row) -> str:
    fmt = row["format"] if row["format"] else ""
    return f"{row['name']}" + (f" · {fmt}" if fmt and fmt != "HO" else "")
