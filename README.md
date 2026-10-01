# PNO — offline Windows workforce analytics

Python desktop application for local-only HR and operations review. This repository contains only application source and fictional test reports. Corporate workbooks must never be uploaded here.

See [desktop/README.md](desktop/README.md) for operation and Windows build instructions.

## Windows test builds

Once enabled, the GitHub Actions workflow tests the Python application on Windows, creates `PNO.exe`, smoke-tests that executable, verifies the pinned small local model, and publishes a prerelease containing:

- `PNO.exe` — desktop executable (no model bundled inside this file).
- `PNO-Windows-Offline.zip` — complete offline package, including the 491 MB model.
- `SHA256SUMS.txt` — checksums.

Use the complete ZIP for local-model chat. Shared databases, network access, online AI, and production certification are not included.

Initial preview; calculations and imports require validation against authorized corporate sources before operational rollout. Actual workbooks have not been supplied due to company policy.

### Enable the Windows build

The source-pushing connector does not have workflow-writing permission. The workflow is supplied as [desktop/windows-build.yml](desktop/windows-build.yml). To activate it using your GitHub account:

1. Copy the complete contents of that file.
2. Create `.github/workflows/windows-build.yml` in this repository and paste those contents.
3. Commit to `main`. This starts the Windows build. Its test release appears under **Releases** only if all checks and packaging succeed.

No executable exists until that Windows build succeeds. Source checks on Linux are not a substitute for Windows validation.
