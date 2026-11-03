import sys, random
from openpyxl import Workbook
from openpyxl.styles import PatternFill
random.seed(5)
STORES = [("Hypermarket","651 LAH Fortress"),("Hypermarket","654 KCH Lucky One"),("Hypermarket","656 LAH Packages"),("Hypermarket","657 GUJ Steel Casting"),
          ("Hypermarket","660 LAH Emporium Mall"),("Hypermarket","661 ISL WTC"),("Hypermarket","663 FAI Lyallpur Galleria"),("Supermarket","652 LAH High Street Paragon Ci"),
          ("Supermarket","658 LAH DHA 7"),("Supermarket","659 LAH DHA Rahbar"),("Supermarket","660 LAH Askari 10"),("Supermarket","661 ISL D12 (P06)"),
          ("H&B","960 H&B LAH Packages Mall"),("H&B","962 H&B LAH Fortress"),("H&B","965 LAH H&B PAK LAH EMP (MYLI)"),("H&B","967 LAH H&B PAK LAH DHA Phase"),
          ("H&B","968 LAH H&B PAK LAH DHA Rahbar"),("H&B","976 KCH H&B PAK KCH LUK (MYLI)")]
SECS = [("Consumer Goods","CGD - Beverages","S011"),("Consumer Goods","CGD - Dairy Products SS","S022"),("Consumer Goods","CGD - DPH","S012"),("Consumer Goods","CGD - Grocery","S014"),
        ("Fresh Food","FFD - Bakery/Pastry","S054"),("Fresh Food","FFD - Butchery","S052"),("Fresh Food","FFD - Fruits & Vegetables","S056"),
        ("Light Household","LHH - House-ware","S031"),("Heavy Household","HHH - TV / VCR","S085"),("Textile","TXT - Men","S044"),("Health & Beauty","H&B - Cosmetics","X111")]
wb = Workbook(); ws = wb.active; ws.title = "Sales YTD"
ws.append(["", "", "", "", "", "YTD", ""]); ws.merge_cells("F1:G1")
ws.append(["Department", "Section", "Code", "Store Type", "Store Short Name", "Budget", "Net Sales"])
yellow = PatternFill("solid", fgColor="FFFF66")
for d, s, c in SECS:
    tb = ta = 0
    for t, n in STORES:
        hb = t == "H&B"
        b = 0 if (hb and d != "Health & Beauty") else random.randint(20_000_000, 900_000_000) // (10 if t == "Supermarket" else 1)
        a = random.randint(0, 400) if (hb and d != "Health & Beauty") else int(b * random.uniform(0.8, 1.3))
        ws.append([d, s, c, t, n, b, a]); tb += b; ta += a
    ws.append([d, s, None, None, None, tb, ta])
    for cell in ws[ws.max_row]: cell.fill = yellow
if "--merged" in sys.argv:          # the real export: titles merged down over rows 1-2, 'YTD' over Budget | Net Sales
    for col in "ABCDE":
        ws[f"{col}1"] = ws[f"{col}2"].value; ws[f"{col}2"] = None; ws.merge_cells(f"{col}1:{col}2")
wb.save(sys.argv[1])
