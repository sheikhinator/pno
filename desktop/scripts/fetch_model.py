"""Build-time only: retrieve pinned public weights, verifying their SHA-256."""

import hashlib
from pathlib import Path
import urllib.request

REVISION = "9217f5db79a29953eb74d5343926648285ec7e67"
FILENAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
EXPECTED_SHA256 = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
EXPECTED_SIZE = 491_400_032
BASE_URL = f"https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/{REVISION}"


def main():
    destination = Path("dist/models")
    destination.mkdir(parents=True, exist_ok=True)
    temporary = destination / (FILENAME + ".part")
    digest = hashlib.sha256()
    count = 0
    try:
        with urllib.request.urlopen(f"{BASE_URL}/{FILENAME}", timeout=120) as response:
            with temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    count += len(chunk)
                    output.write(chunk)
        if count != EXPECTED_SIZE or digest.hexdigest() != EXPECTED_SHA256:
            raise RuntimeError("Model size/checksum mismatch; refusing to package weights.")
        temporary.replace(destination / FILENAME)
        with urllib.request.urlopen(f"{BASE_URL}/LICENSE", timeout=60) as response:
            (destination / "QWEN-LICENSE.txt").write_bytes(response.read())
        print(f"Verified {FILENAME}: {count:,} bytes, SHA256 {digest.hexdigest()}")
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
