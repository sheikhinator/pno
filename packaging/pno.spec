# PyInstaller recipe for PNO.exe (one folder: fast start, no unpacking to %TEMP% on every launch).
#   pyinstaller packaging/pno.spec --noconfirm
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src" / "pno"

datas = [
    (str(SRC / "web"), "web"),
    (str(SRC / "assets"), "assets"),
]
runtime = ROOT / "packaging" / "runtime" / "llama"
if runtime.exists():                       # the offline AI runtime (llama.cpp), downloaded by the build workflow
    datas.append((str(runtime), "runtime/llama"))

hiddenimports = [
    "pno.window", "pno.agent.service", "pno.agent.basic", "pno.agent.tools", "pno.agent.local", "pno.agent.llm",
    "pno.importers.roster", "pno.importers.attendance", "pno.importers.productivity", "pno.importers.sales",
    "pno.importers.leave", "python_calamine", "reportlab.graphics.charts.linecharts", "reportlab.graphics.barcode",
    "PySide6.QtWebChannel", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
]
excludes = ["tkinter", "PySide6.Qt3DCore", "PySide6.QtQuick3D", "PySide6.QtCharts", "PySide6.QtDataVisualization",
            "PySide6.QtMultimedia", "PySide6.QtBluetooth", "PySide6.QtSensors", "PySide6.QtSerialPort",
            "PySide6.QtDesigner", "PySide6.QtTest", "PySide6.QtSql", "PySide6.QtLocation", "PySide6.QtGraphs",
            "matplotlib", "numpy", "pandas", "IPython", "pytest"]

a = Analysis(
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PNO",
    icon=str(SRC / "assets" / "pno.ico"),
    console=False,
    disable_windowed_traceback=False,
    version=str(ROOT / "packaging" / "version.txt"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PNO", upx=False)
