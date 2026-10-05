"""Draw the PNO app icon (gold tile, dark 'PNO') and write src/pno/assets/pno.ico + pno.png. Run once; output is committed."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image  # noqa: E402
from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QLinearGradient, QPainter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "pno" / "assets"


def draw(size: int, family: str) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    r = QRectF(size * 0.03, size * 0.03, size * 0.94, size * 0.94)
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor("#E6B652"))
    g.setColorAt(1, QColor("#94600F"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(r, size * 0.22, size * 0.22)
    f = QFont(family)
    f.setBold(True)
    f.setPixelSize(int(size * (0.36 if size >= 32 else 0.42)))
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 96)
    p.setFont(f)
    p.setPen(QColor("#22150D"))
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, "PNO" if size >= 24 else "P")
    p.end()
    return img


def main():
    QGuiApplication(sys.argv[:1])
    fid = QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / "bricolage-grotesque-latin-700-normal.woff2"))
    fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    family = fams[0] if fams else "DejaVu Sans"
    tmp = ROOT / "build" / "icon"
    tmp.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = []
    for s in sizes:
        path = tmp / f"{s}.png"
        draw(s, family).save(str(path))
        imgs.append(Image.open(path).convert("RGBA"))
    imgs[-1].save(ASSETS / "pno.ico", sizes=[(s, s) for s in sizes], append_images=imgs[:-1])
    draw(512, family).save(str(ASSETS / "pno.png"))
    print("font:", family, "->", ASSETS / "pno.ico")


if __name__ == "__main__":
    main()
