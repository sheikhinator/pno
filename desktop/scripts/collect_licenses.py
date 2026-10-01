"""Include upstream license files in the distributable offline ZIP."""

from importlib import metadata
from pathlib import Path
import shutil
import sys
import hashlib
from urllib.request import urlopen

PACKAGES = [
    "PySide6", "PySide6-Essentials", "PySide6-Addons", "shiboken6",
    "openpyxl", "et-xmlfile", "xlrd", "reportlab", "pillow", "numpy",
    "llama-cpp-python", "diskcache", "jinja2", "MarkupSafe",
    "typing-extensions", "pyinstaller",
]

PINNED_LICENSES = [
    (
        "LGPL-3.0-only.txt",
        "https://raw.githubusercontent.com/pyside/pyside-setup/"
        "24627cd36e1593adf22eb1f2950e4248e7bcc1ec/LICENSES/LGPL-3.0-only.txt",
        "da7eabb7bafdf7d3ae5e9f223aa5bdc1eece45ac569dc21b3b037520b4464768",
    ),
    (
        "Python-PSF-License-3.11.txt",
        "https://raw.githubusercontent.com/python/cpython/v3.11.14/LICENSE",
        "3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf",
    ),
    (
        "openpyxl-MIT.txt",
        "https://foss.heptapod.net/openpyxl/openpyxl/-/raw/3.1.5/LICENCE.rst",
        "0c84bb42f5d367e5ebf9fc2dde35b16141df5ee0fdc189250858bc6c5560f69e",
    ),
    (
        "et-xmlfile-MIT.txt",
        "https://foss.heptapod.net/openpyxl/et_xmlfile/-/raw/2.0.0/LICENCE.rst",
        "0c84bb42f5d367e5ebf9fc2dde35b16141df5ee0fdc189250858bc6c5560f69e",
    ),
]


def _download_pinned_license(name: str, url: str, expected_sha256: str, destination: Path) -> None:
    with urlopen(url, timeout=60) as response:
        content = response.read(1_000_001)
    if len(content) > 1_000_000:
        raise RuntimeError(f"Upstream license {name} exceeds the 1 MB safety limit.")
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected_sha256:
        raise RuntimeError(f"Upstream license {name} failed SHA-256 verification.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def main():
    root = Path("dist/licenses")
    root.mkdir(parents=True, exist_ok=True)
    inventory = []
    for package in PACKAGES:
        distribution = metadata.distribution(package)
        count = 0
        for entry in distribution.files or []:
            if not any("license" in part.casefold() or part.casefold().startswith("copying")
                       for part in entry.parts):
                continue
            source = Path(distribution.locate_file(entry))
            if not source.is_file() or source.suffix.casefold() in {".py", ".pyc", ".dll", ".so"}:
                continue
            # Distribution records are not allowed to escape the package directory.
            clean_parts = [part for part in entry.parts if part not in {".", "..", "/", "\\"}]
            target = root / package / Path(*clean_parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            count += 1
        inventory.append(f"{package} {distribution.version}: {count} upstream notice files")
    for filename in ("LICENSE.txt", "LICENSE"):
        source = Path(sys.base_prefix) / filename
        if source.is_file():
            shutil.copyfile(source, root / "PYTHON-LICENSE.txt")
            break
    pinned_inventory = []
    for name, url, checksum in PINNED_LICENSES:
        destination = root / "upstream" / name
        _download_pinned_license(name, url, checksum, destination)
        pinned_inventory.append(f"{name}: SHA-256 {checksum}")
    for package in ("PySide6", "PySide6-Essentials", "PySide6-Addons", "shiboken6"):
        (root / package).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            root / "upstream" / "LGPL-3.0-only.txt",
            root / package / "LGPL-3.0-only.txt",
        )
    (root / "upstream" / "PYTHON-SHA256SUMS.txt").write_text(
        "\n".join(pinned_inventory) + "\n", encoding="utf-8"
    )
    (root / "INVENTORY.txt").write_text("\n".join(inventory) + "\n", encoding="utf-8")
    print("Dependency license notices collected.")


if __name__ == "__main__":
    main()
