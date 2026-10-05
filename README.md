# PNO · People & Performance

A fast Windows desktop app for HR. It turns the daily BO and HR reports into one clear, fair score out of 10 for every
store employee and manager, with attendance, sales, productivity, stock and waste in one place. Everything runs and
stays on the PC.

> This repository holds only the application and **fictional** demo data. Never upload company reports or staff data here.

## Download

Open **Releases** (right-hand side of the repository page) and pick the newest build:

| File | What it is |
|---|---|
| `PNO-Setup-<version>.exe` | Installer for Windows 10/11 (64-bit). No administrator rights needed. |
| `PNO-<version>-portable-win64.zip` | No install: unzip anywhere and run `PNO.exe`. |
| `SHA256SUMS.txt` | Checksums to verify the downloads. |

The app is not code-signed, so Windows SmartScreen may ask once: **More info → Run anyway**.
Data lives in `%LOCALAPPDATA%\PNO` and is kept when PNO is updated or uninstalled.

## What it reads

Drop the files on the Import screen (or anywhere in the window). PNO recognises them by their layout, never by file name:

| Report | Used for |
|---|---|
| Employee Basic Details (roster) | Who works where, their section, designation and reporting manager |
| Biometric Attendance MTD (IN / OUT / Total WH per day) | Real attendance, punches to fix, hours against the 9-hour rule |
| MTD Productivity (store blocks) | Productivity vs target for the store, departments, sections and CCO |
| BO 200-10-05 Country Performance, *Store Net Sales* tab | Sales vs budget, growth vs last year, out-of-stock %, waste % |
| Leave register (any layout with employee number, dates, type) | Booked leave never counts as absence |

Same store, different spellings across reports (for example `H&B PK KCH Lucky One` and `HB PK KCH H&B PAK KCH LUK (MYLI)`)
are matched automatically; anything uncertain is listed under Settings → Stores to confirm once.
Every import can be undone and redone. Re-importing the same file is detected.

## How the score works

Each person is scored only on what they control, using the latest data for the month:

| Role | Measured on (default weights, editable in Settings → Scoring) |
|---|---|
| Store manager (GM) | Total store sales vs budget, productivity, out of stock, waste, team attendance, own attendance |
| Department head | Their department's results + their team's attendance + own attendance |
| Section manager | Their sections' results (Deli & Dairy = one manager; 02 = Fresh) + team + own attendance |
| H&B store lead | H&B store sales, out of stock, team and own attendance |
| CCO manager | Checkout productivity, team and own attendance |
| Staff | Own attendance (70%) + their section's result (30%) |

- **Attendance**: 9 hours is a full day. Store staff get one weekly off in every Monday–Sunday week; head office gets
  Saturday and Sunday. Leave and gazetted holidays never count against anyone. Missing punches count as worked but are
  listed to fix.
- **Sales / productivity**: 80% of budget/target = 0, 100% = 7, 115% = 10 (editable).
- **Out of stock and waste**: ranked against similar sections in the same format.
- Parts with no data are left out and the rest re-weighted; below 60% coverage, or for joiners of under 30 days, no score is given.
- Bands: 9+ Outstanding · 7.5+ Strong · 6+ Meets expectation · 4+ Needs improvement · below 4 Concern.

## Screens

Home (country → city → format → store → department → section filters, month and comparison) · People · Performance by
role · Stores league and store detail · Attendance (real vs system absence, punches to fix, long absences) · Org chart ·
**Ask PNO** · Import · Settings. Present mode shows the dashboard full-screen for meetings.

**Exports** (PDF, PowerPoint with editable charts, Excel with charts): HR Director pack, store report, department
comparison, individual scorecard, attendance exceptions and people ranking. Every export follows the filters on screen
and can hide names.

## Ask PNO (AI assistant)

Ask anything about the data in plain English: *"Top 5 section managers in Lahore"*, *"Why did Fortress drop?"*,
*"Who has the most missing punches?"*. It can also take data: drop a leave list into the chat or type *"Ali Khan was on
sick leave 3–5 Sept"*. PNO prepares the change and **nothing is saved until you click Confirm**.

- **Groq** (fastest): paste a free key from console.groq.com in Settings → AI. Keys are encrypted for your Windows
  account. *Anonymise* sends employee numbers instead of names and puts the names back on your PC.
- **Offline AI**: Settings → AI → *Set up offline AI* downloads a 1.9 GB model once (or link a `.gguf` file you
  already have). The runtime is included in the app; nothing leaves the PC.
- **Built-in assistant**: always available, no setup, answers the common questions.

With *Auto*, PNO uses Groq when a key is set, otherwise the offline AI, otherwise the built-in assistant, and falls back
automatically if one is unavailable.

## For developers

```bash
pip install -r requirements-dev.txt
python -m pytest -q                         # 150+ tests: parsers, scoring, API, exports, AI tools, screens
PYTHONPATH=src python -m pno.app            # run the desktop app
PYTHONPATH=src python -m pno.devserver --db /tmp/pno.sqlite3 --demo    # screens in a browser: http://127.0.0.1:8765/web/index.html
PYTHONPATH=src python -m pno.app --selftest selftest.log               # what the build runs on the finished .exe
```

`src/pno/` holds the reader and parsers (`reader.py`, `importers/`), the store matcher (`stores.py`), the scoring engine
(`engine.py`), the screen data (`analytics.py`, `api.py`), exports (`exports.py`), the assistant (`agent/`) and the
screens (`web/`). The Windows build (`.github/workflows/build.yml`) runs the tests, bundles llama.cpp, builds `PNO.exe`
with PyInstaller, self-tests the built app and the offline AI, then publishes the installer and portable zip.
