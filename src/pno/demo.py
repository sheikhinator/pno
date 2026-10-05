"""Fictional demo data in the exact layouts of the real reports (made-up people and figures).

Used by the tests, the build self-test and Settings → "Try demo data". Never contains real staff or company figures.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

FIRST_M = ["Ali", "Ahmed", "Usman", "Bilal", "Hamza", "Hassan", "Zeeshan", "Imran", "Kamran", "Faisal", "Asad", "Saad",
           "Fahad", "Junaid", "Adeel", "Shahbaz", "Arslan", "Tariq", "Naveed", "Owais", "Danish", "Rizwan", "Salman",
           "Umair", "Haris", "Talha", "Waleed", "Nabeel", "Sohail", "Yasir"]
FIRST_F = ["Ayesha", "Fatima", "Sana", "Hina", "Maryam", "Amna", "Sadia", "Nimra", "Iqra", "Rabia", "Zainab", "Mehwish",
           "Hira", "Anum", "Sidra", "Kiran", "Saba", "Areeba", "Laiba", "Komal"]
LAST = ["Khan", "Ahmed", "Ali", "Hussain", "Iqbal", "Raza", "Shah", "Butt", "Malik", "Qureshi", "Siddiqui", "Chaudhry",
        "Javed", "Aslam", "Rafiq", "Anwar", "Nawaz", "Akram", "Farooq", "Saleem", "Tahir", "Yousaf"]

# (format, city, name, productivity code)
STORES = [
    ("HM", "LAH", "Fortress", "651"), ("SM", "LAH", "High Street Paragon City", "652"), ("HM", "KCH", "Lucky One", "654"),
    ("HM", "LAH", "Packages Mall", "656"), ("HM", "GUJ", "Steel Casting", "657"), ("SM", "LAH", "DHA 7", "658"),
    ("SM", "LAH", "DHA Rahbar", "659"), ("SM", "LAH", "Askari 10", "660"), ("HM", "LAH", "Emporium Mall", "660"),
    ("SM", "ISL", "D12 (P06)", "661"), ("HM", "ISL", "WTC", "661"), ("HM", "FAI", "Lyallpur Galleria", "663"),
    ("HB", "KCH", "Lucky One", ""), ("HB", "LAH", "Packages Mall", ""), ("HB", "LAH", "Emporium", ""),
]
# how each report writes the H&B store names (they differ on purpose)
HB_ROSTER = {"Lucky One": "H&B PK KCH Lucky One", "Packages Mall": "H&B PK LAH PACKAGES MALL", "Emporium": "H&B PK LAH Emporium"}
HB_SALES = {"Lucky One": "HB PK KCH H&B PAK KCH LUK (MYLI)", "Packages Mall": "H&B PK LAH Packages Mall",
            "Emporium": "HB PK LAH H&B PAK LAH EMP (MYLI)"}
PROD_TRUNC = {"High Street Paragon City": "High Street Paragon Ci", "Packages Mall": "Packages"}

# BO sections: code, name, department
SECTIONS = [
    ("S011", "Beverages", "01", "FMG"), ("S012", "DPH [Detergent. Perfume]", "01", "FMG"), ("S013", "Cigarette", "01", "FMG"),
    ("S014", "Grocery [Dry Food]", "01", "FMG"), ("S021", "Ultra Fresh", "01", "OPSS"), ("S022", "Dairy Products SS", "01", "OPSS"),
    ("S023", "Delicatessen SS", "01", "OPSS"), ("S025", "Poultry", "01", "OPSS"), ("S026", "Frozen Food", "01", "OPSS"),
    ("S050", "Delicatessen Counter", "02", ""), ("S051", "Dairy Counter", "02", ""), ("S052", "Butchery", "02", ""),
    ("S053", "Fishery", "02", ""), ("S054", "Bakery/Pastry", "02", ""), ("S056", "Fruits & Vegetables", "02", ""),
    ("S057", "Coffee Shop", "02", ""),
    ("S080", "Household Goods", "04", ""), ("S081", "Photo", "04", ""), ("S082", "Office Automation", "04", ""),
    ("S083", "Mobility", "04", ""), ("S084", "Gift & Shop", "04", ""), ("S085", "TV / VCR", "04", ""),
    ("S086", "Hi-fi Sound", "04", ""), ("S087", "Household appliances", "04", ""),
    ("S030", "Tools - Do it yourself", "03", ""), ("S031", "House-ware", "03", ""), ("S032", "Stationary", "03", ""),
    ("S033", "Camping / Gardening", "03", ""), ("S034", "House Equipment", "03", ""), ("S035", "Car", "03", ""),
    ("S036", "Toys", "03", ""), ("S037", "Library", "03", ""), ("S039", "Sports", "03", ""), ("S071", "Luggage", "03", ""),
    ("S040", "Home Linen", "05", ""), ("S041", "Baby", "05", ""), ("S042", "Children", "05", ""), ("S043", "Ladies", "05", ""),
    ("S044", "Men", "05", ""), ("S060", "Shoes", "05", ""), ("S061", "Accessories", "05", ""), ("S062", "Gift Stand", "05", ""),
]
X_ROWS = ["X091 - Spice Stand", "X092 - Perfume", "X093 - Textile Gift", "X095 - Gold Counter", "X096 - Photo Processing",
          "X097 - Music", "X100 - Jewelry", "X101 - Sunglasses", "X102 - Flowers", "X104 - Arabic Perfumes",
          "X105 - Market Consignment", "X106 - HHH Consignment", "X107 - Services", "X108 - Consumable",
          "X109 - LHH Consignment", "X110 - Scrap Sales", "X111 - Myli", "X113 - Trading"]

# roster section -> (department label, staff designation)
HM_TEAMS = [
    ("01:CGD-FMCG", "CGD - DPH", "Stocker"), ("01:CGD-FMCG", "CGD - Grocery", "Stocker"), ("01:CGD-FMCG", "CGD - Beverages", "Stocker"),
    ("02:Market", "FFD - Bakery", "Baker"), ("02:Market", "FFD - Delicatessen Counter", "Cook"), ("02:Market", "FFD - Butchery", "Butcher"),
    ("02:Market", "FFD - Fishery", "Fish Monger"), ("02:Market", "FFD - Fruits & Vegetables", "Stocker"),
    ("03:Light Household", "LHH - House-ware", "Stocker"), ("03:Light Household", "LHH - Toys", "Stocker"),
    ("04:Heavy Household", "HHH - Household Appl", "Sales Person"), ("04:Heavy Household", "HHH - Office Automation", "Sales Person"),
    ("05:Textile", "TXT - Men", "Stocker"), ("05:Textile", "TXT - Shoes", "Stocker"),
]
SERVICES = [("CCS - Customer Care & Services", "Officer - C.C.S"), ("MNT - Maintenance", "Technician"),
            ("RSK - Risk and Compliance", "Officer - Risk & Compliance"), ("REC - Receiving", "Checker")]


@dataclass
class Person:
    emp: str
    name: str
    bu: str
    dept: str
    section: str
    designation: str
    grade: str
    gender: str
    manager: str
    joining: date
    pattern: str = "normal"      # normal | absentee | leaver | night | sloppy | perfect


@dataclass
class Demo:
    people: list[Person] = field(default_factory=list)
    files: dict[str, bytes] = field(default_factory=dict)


def _xlsx(sheets: dict[str, list[list]]) -> bytes:
    import xlsxwriter
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "strings_to_numbers": False})
    datef = wb.add_format({"num_format": "dd-mmm-yy"})
    for title, rows in sheets.items():
        ws = wb.add_worksheet(title[:31])
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                if v is None or v == "":
                    continue
                if isinstance(v, date):
                    ws.write_datetime(r, c, _dt(v), datef)
                else:
                    ws.write(r, c, v)
    wb.close()
    return buf.getvalue()


def _dt(d: date):
    from datetime import datetime
    return datetime(d.year, d.month, d.day)


class _Names:
    def __init__(self, rnd: random.Random):
        self.rnd = rnd

    def __call__(self, gender: str) -> str:
        first = self.rnd.choice(FIRST_F if gender == "Female" else FIRST_M)
        if gender == "Male" and self.rnd.random() < 0.45:
            first = "Muhammad " + first
        return f"{first} {self.rnd.choice(LAST)}"


def build_people(seed: int = 7) -> list[Person]:
    rnd = random.Random(seed)
    name = _Names(rnd)
    people: list[Person] = []
    serial = [20050000]

    def new_emp(prefix=None):
        serial[0] += rnd.randint(3, 97)
        return str(prefix + serial[0] % 100000 if prefix else serial[0])

    def add(bu, dept, section, desig, grade, gender, manager, pattern="normal", emp=None, nm=None):
        joined = date(2026, 8, 1) - timedelta(days=rnd.randint(200, 3000))
        p = Person(emp or new_emp(), nm or name(gender), bu, dept, section, desig, grade, gender, manager, joined, pattern)
        people.append(p)
        return p

    for fmt, city, sname, _ in STORES:
        if fmt == "HB":
            bu = HB_ROSTER[sname]
            dep = add(bu, "99:Services", "MGM - Management", "Deputy Manager", "12", "Female", "Hina Saleem (Area)",
                      emp=new_emp(60000000))
            for i in range(5):
                patt = rnd.choice(["normal", "normal", "night", "sloppy", "perfect"])
                add(bu, "06:Express Common", "OTH - Common", "Senior Beauty Advisor" if i == 0 else "Beauty Advisor",
                    rnd.choice(["07", "08", "09"]), "Female" if rnd.random() < 0.85 else "Male", "Hina Saleem (Area)", patt)
            continue
        bu = f"{fmt} PK {city} {sname}"
        gm = add(bu, "99:Services", "MGM - Management", "Store Manager", "14", "Male", "Regional Director North", "perfect",
                 emp=new_emp(60000000))
        if fmt == "SM":
            sm_bak = add(bu, "02:Market", "FFD - Bakery", "Section Manager", "08", "Male", gm.name)
            sm_but = add(bu, "02:Market", "FFD - Butchery", "Section Manager", "08", "Male", gm.name)
            for _ in range(3):
                add(bu, "02:Market", "FFD - Bakery", "Baker", "04", "Male", sm_bak.name)
                add(bu, "02:Market", "FFD - Butchery", "Butcher", "04", "Male", sm_but.name)
            for _ in range(6):
                add(bu, "01:CGD-FMCG", "CGD - Grocery", "Stocker", "04", "Male", gm.name,
                    rnd.choice(["normal", "normal", "normal", "absentee", "sloppy"]))
            for _ in range(3):
                add(bu, "11:Central Cashier Office(CCO)", "CCO - Cashiers", "Cashier", "04",
                    rnd.choice(["Male", "Female"]), gm.name)
            continue
        # hypermarket
        dh_cgd = add(bu, "01:CGD-FMCG", "CGD - FMCG (Common)", "Department Head", "13", "Male", gm.name, emp=new_emp(60000000))
        dh_fresh = add(bu, "02:Market", "FFD - Market (Common)", "Department Head", "13", "Male", gm.name,
                       emp=new_emp(60000000)) if sname != "Lyallpur Galleria" else None
        top_fresh = dh_fresh or gm
        sup_cgd = add(bu, "01:CGD-FMCG", "CGD - DPH", "Supervisor", "06", "Male", dh_cgd.name)
        sm_bakery = add(bu, "02:Market", "FFD - Bakery", "Section Manager", "08", "Male", top_fresh.name)
        sup_butch = add(bu, "02:Market", "FFD - Butchery", "Supervisor", "06", "Male", top_fresh.name)
        sm_fv = add(bu, "02:Market", "FFD - Fruits & Vegetables", "Section Manager", "08", "Male", top_fresh.name)
        tl_lhh = add(bu, "03:Light Household", "LHH - Light Household (Common)", "Team Leader", "11", "Male", gm.name)
        tl_hhh = add(bu, "04:Heavy Household", "HHH - Heavy Household (Common)", "Team Leader", "11", "Male", gm.name)
        tl_txt = add(bu, "05:Textile", "TXT - Textile (Common)", "Team Leader", "10", "Female", gm.name)
        boss = {"CGD - DPH": sup_cgd, "CGD - Grocery": sup_cgd, "CGD - Beverages": sup_cgd,
                "FFD - Bakery": sm_bakery, "FFD - Delicatessen Counter": sm_bakery, "FFD - Butchery": sup_butch,
                "FFD - Fishery": sup_butch, "FFD - Fruits & Vegetables": sm_fv, "LHH - House-ware": tl_lhh,
                "LHH - Toys": tl_lhh, "HHH - Household Appl": tl_hhh, "HHH - Office Automation": tl_hhh,
                "TXT - Men": tl_txt, "TXT - Shoes": tl_txt}
        for dept, section, desig in HM_TEAMS:
            for _ in range(rnd.randint(2, 4)):
                patt = rnd.choices(["normal", "absentee", "night", "sloppy", "perfect", "leaver"], [60, 7, 8, 10, 13, 2])[0]
                add(bu, dept, section, desig, rnd.choice(["04", "04", "05", "06"]), "Male" if rnd.random() < 0.85 else "Female",
                    boss[section].name, patt)
        cco = add(bu, "11:Central Cashier Office(CCO)", "CCO - Central Cashier Office", "Supervisor", "05", "Male", gm.name)
        for _ in range(rnd.randint(5, 7)):
            add(bu, "11:Central Cashier Office(CCO)", "CCO - Cashiers", "Cashier", "04", rnd.choice(["Male", "Female"]), cco.name)
        add(bu, "11:Central Cashier Office(CCO)", "CCO - Safe", "Safe Clerk", "04", "Male", cco.name)
        for section, desig in SERVICES:
            add(bu, "99:Services", section, desig, "04", "Male", "Functional Head " + section[:3])
    # a few awkward cases the real roster has: repeated names and a manager name that is a prefix of another
    for p in people[40:44]:
        p.name = "Muhammad Bilal"
    return people


# ------------------------------------------------------------------------------------------------ roster
def roster_xlsx(people: list[Person]) -> bytes:
    rows = [["Business Unit", "Department", "Section", "Employee Number", "Employee Name", "Designation ", "Grade",
             "Gender", "Reporting Manager "]]
    for p in people:
        rows.append([p.bu, p.dept, p.section, int(p.emp), p.name, p.designation, p.grade, p.gender, p.manager])
    return _xlsx({"Sheet1": rows})


# ------------------------------------------------------------------------------------------------ attendance
def _day_cells(rnd: random.Random, p: Person, d: date, off_day: int, leave_days: set[date]) -> tuple[str, str, str]:
    """IN, OUT, Total WH exactly as the biometric export writes them."""
    nm = "Not Marked"
    if p.pattern == "leaver" and d.day >= 12:
        return nm, nm, "Absent"
    if d in leave_days or d.weekday() == off_day:
        return nm, nm, "Absent"
    r = rnd.random()
    if p.pattern == "absentee" and r < 0.22:
        return nm, nm, "Absent"
    if p.pattern != "perfect" and r < 0.03:
        return nm, nm, "Absent"
    start_h = {"night": rnd.choice([15, 16]), "normal": rnd.choice([8, 9, 11, 12, 14])}.get(p.pattern, rnd.choice([8, 9, 12]))
    start = start_h * 60 + rnd.randint(-15, 40)
    dur = rnd.randint(540, 600) if p.pattern == "perfect" else rnd.randint(470, 640)
    if p.pattern == "sloppy" and rnd.random() < 0.18:
        kind = rnd.choice(["no_out", "no_in", "manual", "punch_abs"])
        t_in = _hhmmss(start, rnd)
        t_out = _hhmmss(start + dur, rnd)
        if kind == "no_out":
            return t_in, nm, "Absent"
        if kind == "no_in":
            return "0", t_out, "Absent"
        if kind == "manual":
            return nm, nm, f"{dur // 60}:{dur % 60:02d}"
        return t_in, t_out, "Absent"
    return _hhmmss(start, rnd), _hhmmss(start + dur, rnd), f"{dur // 60}:{dur % 60:02d}"


def _hhmmss(mins: int, rnd: random.Random) -> str:
    mins %= 1440
    return f"{mins // 60:02d}:{mins % 60:02d}:{rnd.randint(0, 59):02d}"


def attendance_xlsx(people: list[Person], month: date, upto: int | None = None, seed: int = 11,
                    leaves: dict[str, set[date]] | None = None) -> bytes:
    """Biometric MTD grid: title row with dates over IN/OUT/Total WH, then Absent / Present totals."""
    rnd = random.Random(seed + month.month)
    days = []
    d = month.replace(day=1)
    while d.month == month.month and (upto is None or d.day <= upto):
        days.append(d)
        d += timedelta(days=1)
    row1 = ["Biometric Attendance", None, None, None, None, None]
    row2 = ["Business Unit Name", "Section", "Employee No", "Employeee Name", "Designation", "Joining date"]
    for day in days:
        row1 += [f"{day.day}-{day.strftime('%b')}-{day.strftime('%y')}", None, None]
        row2 += ["IN", "OUT", "Total WH"]
    row1 += [None, None]
    row2 += ["Absent", "Present"]
    rows = [row1, row2]
    for p in people:
        off = int(p.emp) % 7
        leave_days = (leaves or {}).get(p.emp, set())
        cells = [p.bu.ljust(30), p.section.ljust(30), p.emp, p.name.ljust(30), p.designation, p.joining.strftime("%d/%m/%Y")]
        present = 0
        for day in days:
            a, b, c = _day_cells(rnd, p, day, off, leave_days)
            present += c != "Absent"
            cells += [a, b, c]
        cells += [len(days) - present, present]
        rows.append(cells)
    return _xlsx({"Sheet1": rows})


# ------------------------------------------------------------------------------------------------ productivity
def productivity_xlsx(month: date, seed: int = 21) -> bytes:
    rnd = random.Random(seed + month.month)
    head = ["Store Name", "Dept/Section", "Store Productivity", "Store Productivity LY", "Target Productivity",
            "Forecasted Productivity ", "v/s Target", "v/s LY", "Forecasted v/s Target Productivity"]
    rows = []
    for fmt, city, sname, code in STORES:
        if fmt == "HB":
            continue
        label = f"{code} {city} {PROD_TRUNC.get(sname, sname)}"
        if fmt == "HM":
            lines = [("00 - Overall Store", 100), ("CCO", 180), ("S054 - Bakery/Pastry", 12), ("S050-S051 Deli & Dairy", 25),
                     ("01-CGD", 500), ("S052 - Butchery", 7.5), ("03-LHH", 55), ("04-HHH", 2.2),
                     ("S056 - Fruits & Vegetables", 55), ("05-TXT", 28), ("S053 - Fishery", 1.5)]
        else:
            lines = [("00 - Overall Store", 45), ("Other Store Sections", 55), ("S052 - Butchery", 8.5), ("S054 - Bakery/Pastry", 6)]
        rows.append(head)
        for row, base in lines:
            target = round(base * rnd.uniform(0.85, 1.15), 1)
            actual = round(target * rnd.uniform(0.7, 1.35), 1)
            ly = actual * rnd.uniform(0.8, 1.2)
            fc = round(actual * rnd.uniform(0.9, 1.1), 1) if rnd.random() > 0.25 else None
            rows.append([label, row, actual, ly, target, fc, _arrow(actual / target - 1), _arrow(actual / ly - 1),
                         _arrow((fc or 0) / target - 1)])
        rows += [[], []]
    return _xlsx({"Productivity": rows})


def _arrow(x: float) -> str:
    p = round(x * 100)
    return f"▲ {p}%" if p > 0 else (f"▼ {p}%" if p < 0 else "▬ 0%")


# ------------------------------------------------------------------------------------------------ BO 200-10-05
def _money(v: float) -> str:
    return f"{v:,.0f}"


def _pct(v: float | None) -> str:
    if v is None:
        return ""
    return f"({abs(v):,.1f}%)" if v < 0 else f"{v:,.1f}%"


def bo_sales_xlsx(as_of: date, seed: int = 31, period: str = "MTD", numeric: bool = False) -> bytes:
    """200-10-05 Country Periodic Store Performance Report, 'Store Net Sales' tab: one block per store."""
    rnd = random.Random(seed + as_of.toordinal())
    days = as_of.day if period == "MTD" else 1
    start = as_of.replace(day=1) if period == "MTD" else as_of
    rows: list[list] = []
    head1 = ["Section Code Name", "Net Sales", "", "", "", "", "", "Section Weight", "", "Customer", "", "Pent. Rate", "Item",
             "", "Avg Basket", "", "Avg Selling Price", "", "Margin %", "", "", "Avg Stock", "Out of Stock %"]
    head2 = ["", "Actual", "Forecast", "Budget", "Gth %", "Var FCT %", "Var %", " in Store", "in Cntry", "Cust", "Gth %", "",
             "Actual", "Gth %", "Actual", "Gth %", "Actual", "Gth %", "NetMrg", "Waste ", "NetMrg-Wst", "", ""]
    for fmt, city, sname, _ in STORES:
        store_name = HB_SALES[sname] if fmt == "HB" else f"{fmt} PK {city} {sname}"
        scale = {"HM": 1.0, "SM": 0.12, "HB": 0.05}[fmt] * days
        rows.append(["Report Name: 200-10-05-Country Periodic Store Performance Report", "", "", "", "",
                     f"Currency:  LOCAL CURR - {period}", "", "", "", f"Net Sales of: ({as_of.strftime('%a')}) {as_of.strftime('%d-%b-%y')}",
                     "", "", "Run By: demo"])
        rows.append([f"Store Name: {store_name}", "", "", "", "", f"Report Period : {start:%d/%m/%Y} - {as_of:%d/%m/%Y}", "", "",
                     "", f"Compare With: ({as_of.strftime('%a')}) {as_of.replace(year=as_of.year - 1):%d-%b-%y}", "", "",
                     f"Run Time: {as_of + timedelta(days=1):%d/%m/%Y} 8:58:47 AM"])
        rows.append([])
        rows.append(list(head1))
        rows.append(list(head2))
        data = {}
        for code, sec, dept, sub in SECTIONS:
            active = fmt != "HB" or code == "S012"
            if fmt == "SM" and dept in ("04",) or code in ("S013", "S023", "S025", "S057", "S081", "S084", "S086", "S037"):
                active = False
            base = rnd.uniform(0.05, 1.5) * 1_000_000 * scale / 30 if active else 0
            budget = base * rnd.uniform(0.75, 1.2) if active else 0
            growth = rnd.uniform(-35, 45) if active else 0.0
            data[code] = dict(actual=base, budget=budget, growth=growth, cust=rnd.randint(50, 2500) * days / 30 if active else 0,
                              margin=rnd.uniform(-5, 40) if active else 0, waste=(rnd.uniform(0, 6) if dept == "02" and active else 0.0),
                              oos=(0.0 if dept == "02" or not active else rnd.uniform(4, 35)), stock=base * rnd.uniform(3, 9))
        cust_total = rnd.randint(1500, 6500) * max(1, days) // 30 + 200

        def line(label, items, cust=None):
            a = sum(data[c]["actual"] for c in items)
            b = sum(data[c]["budget"] for c in items)
            ly = sum(data[c]["actual"] / (1 + data[c]["growth"] / 100) for c in items if data[c]["actual"])
            g = (a / ly - 1) * 100 if ly else 0.0
            w = sum(data[c]["waste"] * data[c]["actual"] for c in items) / a if a else 0.0
            m = sum(data[c]["margin"] * data[c]["actual"] for c in items) / a if a else 0.0
            o = sum(data[c]["oos"] * data[c]["actual"] for c in items) / a if a else 0.0
            cu = cust if cust is not None else max([data[c]["cust"] for c in items] or [0])
            return _row(label, a, b, g, cu, m, w, o, sum(data[c]["stock"] for c in items), numeric)

        def sec_line(code):
            name = next(s[1] for s in SECTIONS if s[0] == code)
            return line(f"{code} - {name}", [code])

        groups = [("01", "FMG", "CGD-FMG"), ("01", "OPSS", "CGD-OPSS")]
        cg = []
        for dept, sub, label in groups:
            codes = [s[0] for s in SECTIONS if s[2] == dept and s[3] == sub]
            cg += codes
            rows += [sec_line(c) for c in codes]
            rows.append(line(label, codes))
        rows.append(line("Consumer Goods", cg))
        fresh = [s[0] for s in SECTIONS if s[2] == "02"]
        rows += [sec_line(c) for c in fresh]
        rows.append(line("Fresh Food", fresh))
        rows.append(line("z", fresh))
        food = line("Food", cg + fresh)
        food[9:12] = ["", "", ""]
        rows.append(food)
        nonfood = []
        for dept, label in [("04", "Heavy House Hold"), ("03", "Light House Hold"), ("05", "Textile")]:
            codes = [s[0] for s in SECTIONS if s[2] == dept]
            nonfood += codes
            rows += [sec_line(c) for c in codes]
            rows.append(line(label, codes))
        rows.append(line("z", nonfood))
        nf = line("Non Food", nonfood)
        nf[9:12] = ["", "", ""]
        rows.append(nf)
        rows.append(line("Total Store", cg + fresh + nonfood, cust_total))
        for x in X_ROWS:
            v = cust_total * 12 if x.startswith("X107") else 0
            rows.append([x, _money(v) if not numeric else v, 0, "", _pct(5.0 if v else 0.0), "0.0%", "", "0.0%", "0.0%", cust_total if v else 0])
        rows.append(["Consignment", _money(cust_total * 12), 0, 0])
        rows.append([])
        tot = line("Total Hypermarket", cg + fresh + nonfood, cust_total)
        rows.append(tot)
        rows.append([])
    return _xlsx({"Store Net Sales": rows})


def _row(label, a, b, g, cust, margin, waste, oos, stock, numeric):
    var = (a / b - 1) * 100 if b else 0.0
    if numeric:     # a workbook saved with real numbers and % formats: percentages arrive as fractions
        f = lambda x: x / 100
        return [label, round(a), 0, round(b), f(g), 0, f(var), 0.05, 0.01, round(cust), f(3.0), f(30.0), round(a / 300),
                f(1.0), 1500.0, f(2.0), 300.0, f(1.0), f(margin), f(waste), f(margin - waste), round(stock), f(oos)]
    return [label, _money(a), "0", _money(b), _pct(g), "0.0%", _pct(var), "5.0%", "1.0%", f"{cust:,.0f}", _pct(3.0), "30.0%",
            _money(a / 300), _pct(1.0), "1,500.0", _pct(2.0), "300.0", _pct(1.0), _pct(margin), _pct(waste),
            _pct(margin - waste), _money(stock), _pct(oos)]


# ------------------------------------------------------------------------------------------------ leave
def leave_xlsx(people: list[Person], month: date, seed: int = 41) -> tuple[bytes, dict[str, set[date]]]:
    rnd = random.Random(seed + month.month)
    rows = [["Employee No", "Employee Name", "Leave Type", "From Date", "To Date", "Days", "Status"]]
    taken: dict[str, set[date]] = {}
    for p in rnd.sample(people, max(3, len(people) // 12)):
        start = month.replace(day=rnd.randint(2, 24))
        n = rnd.randint(1, 3)
        end = start + timedelta(days=n - 1)
        status = "Approved" if rnd.random() > 0.1 else "Rejected"
        rows.append([p.emp, p.name, rnd.choice(["Annual Leave", "Sick Leave", "Casual Leave"]), start, end, n, status])
        if status == "Approved":
            taken.setdefault(p.emp, set()).update(start + timedelta(days=i) for i in range(n))
    return _xlsx({"Leave": rows}), taken


def build(seed: int = 7) -> Demo:
    """Two months of demo files: August and September 2026."""
    people = build_people(seed)
    demo = Demo(people=people)
    demo.files["Employee Basic Details.xlsx"] = roster_xlsx(people)
    for m in (date(2026, 8, 1), date(2026, 9, 1)):
        lv, taken = leave_xlsx(people, m)
        tag = m.strftime("%b %Y")
        demo.files[f"Leave Register {tag}.xlsx"] = lv
        demo.files[f"Biometric Attendance MTD {tag}.xlsx"] = attendance_xlsx(people, m, leaves=taken)
        demo.files[f"MTD Productivity {tag}.xlsx"] = productivity_xlsx(m)
        last = (m.replace(month=m.month + 1) - timedelta(days=1))
        demo.files[f"200-10-05 Country Performance {last:%d-%b-%Y}.xlsx"] = bo_sales_xlsx(last)
    return demo
