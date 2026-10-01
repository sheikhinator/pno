$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m pip install -e ".[test,build]"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
# Prefer an upstream CPU wheel; compile from source with the runner's
# Visual Studio build tools if no wheel exists for this Python version.
# Avoid native tuning so the executable works on the target i7-8665U.
$env:CMAKE_ARGS = "-DGGML_CUDA=OFF -DGGML_NATIVE=OFF"
python -m pip install "llama-cpp-python==0.3.16" --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
if ($LASTEXITCODE -ne 0) { throw "Local model runtime installation failed" }
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
python scripts/make_samples.py
if ($LASTEXITCODE -ne 0) { throw "Sample generation failed" }
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PNO --paths "." --collect-all llama_cpp --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick scripts/launch.py
if ($LASTEXITCODE -ne 0) { throw "Packaging failed" }
$env:PNO_DATA_DIR = Join-Path $env:TEMP ("pno-smoke-" + [guid]::NewGuid())
$process = Start-Process -FilePath (Join-Path $PWD "dist/PNO.exe") -ArgumentList "--smoke-test" -PassThru
if (-not $process.WaitForExit(90000)) { $process.Kill(); throw "Executable smoke test timed out" }
if ($process.ExitCode -ne 0) { throw "Executable smoke test failed: $($process.ExitCode)" }
python scripts/fetch_model.py
if ($LASTEXITCODE -ne 0) { throw "Model download/checksum failed" }
Copy-Item README.md dist/README.md
Copy-Item THIRD-PARTY-NOTICES.md dist/THIRD-PARTY-NOTICES.md
Copy-Item -Recurse samples dist/samples
python scripts/collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw "Dependency license collection failed" }
python scripts/package_release.py
if ($LASTEXITCODE -ne 0) { throw "Release package failed" }
Write-Host "Windows build ready in desktop/dist"
