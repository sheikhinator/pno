"""Package binaries, local model, fictional examples and user guide."""

import hashlib
from pathlib import Path
import zipfile


def main():
    root = Path("dist")
    archive = root / "PNO-Windows-Offline.zip"
    entries = [root / "PNO.exe", root / "README.md", root / "THIRD-PARTY-NOTICES.md"]
    entries.extend(p for folder in ("models", "samples", "licenses") for p in (root / folder).rglob("*") if p.is_file())
    if not (root / "PNO.exe").is_file():
        raise RuntimeError("No Windows executable was built.")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as output:
        for entry in entries:
            output.write(entry, "PNO/" + entry.relative_to(root).as_posix())
    checksums = []
    for path in [root / "PNO.exe", archive]:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        checksums.append(f"{digest.hexdigest()}  {path.name}")
    (root / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
