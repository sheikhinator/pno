"""The same store is written differently in every report; all variants must land on one store."""

from pno.stores import StoreResolver, parse_name, similarity

GROUPS = [
    ["HM PK LAH Fortress", "HM PK LAH FORTRESS STADIUM", "651 LAH Fortress"],
    ["SM PK LAH High Street Paragon City", "652 LAH High Street Paragon Ci"],
    ["HM PK KCH Lucky One", "654 KCH Lucky One"],
    ["H&B PK KCH Lucky One", "HB PK KCH H&B PAK KCH LUK (MYLI)", "H&B PK KCH LUCKY ONE"],
    ["H&B PK LAH Emporium", "HB PK LAH H&B PAK LAH EMP (MYLI)"],
    ["HM PK LAH Emporium Mall", "660 LAH Emporium Mall"],
    ["HM PK FAI Lyallpur Galleria", "663 FAI Lyallpur Galleria"],
    ["SM PK LAH DHA 7", "658 LAH DHA 7"],
]


def test_parse_name():
    p = parse_name("HB PK KCH H&B PAK KCH LUK (MYLI)")
    assert (p.format, p.city) == ("HB", "KCH") and "LUK" in p.tokens
    p = parse_name("652 LAH High Street Paragon Ci")
    assert (p.code, p.format, p.city) == ("652", "", "LAH")
    assert parse_name("SM PK LAH DHA 7").name == "DHA 7"
    assert parse_name("PK Head Office Lahore").is_ho


def test_similarity_subsequence():
    assert similarity(["LUK"], ["LUCKY", "ONE"]) > 0.6
    assert similarity(["FORTRESS"], ["PACKAGES"]) == 0


def test_every_variant_resolves_to_one_store(empty_db):
    r = StoreResolver(empty_db, "test")
    ids = [{r.resolve(n) for n in g} for g in GROUPS]
    for g, s in zip(GROUPS, ids):
        assert len(s) == 1, g
    flat = [next(iter(s)) for s in ids]
    assert len(set(flat)) == len(GROUPS)           # HM Lucky One and H&B Lucky One stay different stores
    assert empty_db.val("SELECT COUNT(*) FROM stores") == len(GROUPS)


def test_hm_and_hb_same_mall_are_different(empty_db):
    r = StoreResolver(empty_db)
    assert r.resolve("HM PK LAH Packages Mall") != r.resolve("H&B PK LAH PACKAGES MALL")


def test_cached_alias_is_used(empty_db):
    r = StoreResolver(empty_db)
    a = r.resolve("HM PK LAH Fortress")
    assert StoreResolver(empty_db).resolve("  HM PK LAH Fortress ") == a
    assert empty_db.val("SELECT COUNT(*) FROM store_aliases") == 1


def test_display_name_upgrades_from_truncated(empty_db):
    r = StoreResolver(empty_db)
    sid = r.resolve("652 LAH High Street Paragon Ci")
    r.resolve("SM PK LAH High Street Paragon City")
    assert empty_db.val("SELECT name FROM stores WHERE id=?", (sid,)) == "High Street Paragon City"
