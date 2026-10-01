# PNO — Windows offline analytics test build

## What this preview includes

- Local SQLite history for roster, attendance, productivity, daily sales and MTD sales.
- Multi-sheet Excel (.xlsx/.xls) and CSV/TSV import detection, manual mappings, previews and validation warnings.
- Pasted tabular data import.
- Period/calendar browsing, organizational filters, employee name/code search and manager-ID hierarchy.
- Sales and attendance analysis, historical charts, source-reported productivity/OOS, evidence-based commentary.
- PDF, Excel and CSV review exports with reporting periods, warnings and source references.
- Offline controlled-query chat, with optional small local model for language summaries.
- Backup and validated restore. Nothing is sent to the internet by the runtime application.

This is a testing preview, not certified corporate software. Unknown layouts require review. Scoring remains provisional until the organization approves targets, weights, attendance policies and the interpretation of each measure. The tool does not make employment decisions.

## Run the Windows package

1. Obtain corporate IT permission. The executable is unsigned; do not bypass company security policies.
2. Download `PNO-Windows-Offline.zip` from this repository's Releases page.
3. Extract the entire ZIP to a folder you can write to. Run `PNO/PNO.exe`.
4. The `models` folder contains the verified 491 MB local model. Keep it beside the executable, or select another compatible local GGUF in Settings (maximum 1 GB).
5. Try the fictional examples in `samples` before importing real files locally.

No Python installation, GPU, API key or network connection is needed to run the packaged application. Chat uses the local model when available; otherwise it is clearly labeled as rule-based. Import and calculations do not depend on the model.

### Data and privacy

The database is in the Windows user's local application-data directory, not inside the executable. Settings displays its exact location. `PNO_DATA_DIR` may override the directory for testing.

Never put corporate data into the public GitHub repository or upload it to this workspace. This application does not encrypt the database in this initial preview: use company-approved device encryption and Windows access controls. Backups and exported reports contain potentially sensitive data and must be secured under corporate policy.

Roster assignments reflect saved snapshot dates, not an inferred history. Older periods without appropriate snapshots must show warnings. Names are not used as unique manager identifiers. Gender is not a scoring factor.

### Import review

Select the report period and inspect each detected sheet/table. Correct mappings where necessary, then save selected candidates. Unmapped columns remain as source values; they do not silently become KPIs.

Identical imports are rejected. Corrections require confirmation and leave earlier versions in history. Daily/MTD are different datasets; cumulative MTD snapshots must not be added together as transactions.

Attendance statuses and numerical zero remain distinct. Unknown statuses, cached-formula gaps and incomplete dates must be reviewed. The importer does not execute Excel macros or calculate Excel formulas; save calculated workbooks in Excel first if their cached results are missing.

## Build from source on Windows

Python 3.11 x64 is required for building, not for using the executable:

```
cd desktop
python -m pip install -e ".[test,build]"
powershell -File scripts/build_windows.ps1
```

Follow company execution policies; obtain approval instead of changing them arbitrarily. The build script also installs the CPU local-model runtime and downloads pinned public model weights. Internet is required at build time only. Outputs go to `desktop/dist`.

The small model is Qwen2.5-0.5B-Instruct Q4_K_M (491,400,032 bytes). SHA-256 is checked before packaging. Preserve its Apache 2.0 license.

## Development checks

```
cd desktop
python -m pytest -q
python -m pno --smoke-test
python -m pno
```

On headless Linux set `QT_QPA_PLATFORM=offscreen` for UI tests. All test fixtures are fictional. `--capture PATH.png` captures the native window for visual checks without opening corporate files.

Review third-party notices before redistribution. Network sharing, cloud AI, logins and database encryption are outside this first preview.
