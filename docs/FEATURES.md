# P&O 4.0 — feature checklist

## 4.0: what the director sees
- ✅ Two tabs only: **Review** and **Ask P&O AI** (Update data, Present and ⚙ in the top bar)
- ✅ Review: Country › Store › Department › Section, plus a role filter (store managers, department heads, section managers, team leaders)
- ✅ Scorecard tiles coloured against benchmarks: sales vs budget, growth, productivity, shrinkage, stock days, out of stock, waste, attendance, leavers, disciplinary cases, NPS
- ✅ What's strong / what's weak / focus this week, written from the numbers
- ✅ Next level down as a coloured grid (stores, departments or sections); click to drill in
- ✅ People benchmark table: every criterion visible, score as the last column, store order (no ranks, no tiers), sortable by any column
- ✅ Person data sheet: results vs benchmark vs peers, what the score is made of, ratings over time, PDF
- ✅ Benchmarks editable in ⚙ Settings; the assistant answers from the same numbers (offline too)
- ✅ The full 3.x toolkit is still inside, off by default (⚙ Settings → Appearance → Full P&O toolkit)


Everything below ships in 3.0 and is covered by the automated tests (287 tests, end-to-end browser runs included).

## Data in
- ✅ Import any Excel / CSV / PDF report, any file name or layout (exact readers first, Smart Import for everything else)
- ✅ Smart Import: finds headers under titles and logos, two-row headers, headerless files, calendar-style rosters
- ✅ Smart Import report types: roster, time in role, ratings, turnover, leave, attendance, shift roster, DA, store sales, customer NPS, productivity, shrinkage & stock days
- ✅ A file that looks like a known report but isn't laid out like one falls back to Smart Import instead of failing
- ✅ Discrepancy checks inside and across sheets; confidence per sheet; fix column matches by hand
- ✅ Import calendar: pick the month, P&O asks for the sheets it expects
- ✅ Remembered layouts per recurring file; your own column names taught in Settings
- ✅ AI import help sends column titles and value types only, never cell values
- ✅ Personal fields (birth date, age, email, mobile, marital status) are never imported
- ✅ Store matching by format (hypermarket / supermarket / Myli H&B) with automatic repair

## People & performance
- ✅ Business review, stores, people, attendance, talent grid, bench, flight risk
- ✅ Leader index: sales, productivity, shrinkage, stock days, rating, retention and customer NPS (weights editable)
- ✅ People Brain: one record per person joined across every source, with where each fact came from
- ✅ Corrections from screens or chat win over later imports, with undo
- ✅ Profile sheet export (PDF / Word) with insights, statistics and optional 1:1 notes
- ✅ People insights: absence by weekday, Bradford factor, wellbeing (long hours, no rest), early and regrettable attrition, gender mix by level (groups under 5 never split), cross-store links

## Organisation & relations
- ✅ Organisation health: changes between Basic Sheets, span of control, probation, rating calibration
- ✅ Employee relations: disciplinary, grievance, investigation and PIP cases with stage deadlines and consistent-outcome guidance
- ✅ 10 HR letters numbered `MAF-PK/P&O/{TYPE}/{YEAR}/{NNN}`, Word or PDF, filed on the person's page
- ✅ Exit interviews with reasons, scores, leaver eNPS and regrettable losses
- ✅ Workforce plan, manpower, goals, 1:1 and visit notes, store-visit checklist that creates actions

## Hiring & learning
- ✅ Vacancies with internal talent first and backfill chains (who covers the role you move someone from)
- ✅ CV screening with blind mode (age, gender, marital status, religion, CNIC, father's name redacted and never scored)
- ✅ Learning Studio: course builder, assignments, training needs from the data

## The director's office
- ✅ Overview inbox: overdue actions and cases, data health, flight risk, goals off track, anniversaries, leaders on leave
- ✅ HR calendar: anniversaries, probation ends, leave, case deadlines, goals, actions, follow-ups, training, holidays
- ✅ Weekly brief on one page: copy, or export to PDF / Word
- ✅ Month close, engagement surveys, recognition and certificates, policy assistant

## AI
- ✅ Choose which AI does which job (confidential work can stay offline)
- ✅ Answer cache, history compaction, short-retry rate-limit handling
- ✅ Charts and tables inside answers; actions from answers

## Experience
- ✅ Skeleton loaders, instant screens (stale-while-revalidate), hover pre-loading, view transitions
- ✅ Undo instead of "are you sure?" (also Ctrl+Z), optimistic updates, safe double-clicks (idempotency keys)
- ✅ Command search (Ctrl K), G-key navigation, `?` shortcut sheet, welcome tour
- ✅ "Explain this number" on KPI cards: what it is, where it comes from, what good looks like
- ✅ Tabular numbers, balanced headings, squircle corners, larger hit areas, reduced-motion support
- ✅ Light / dark theme, hide names for screen-sharing, PIN lock
- ✅ Branded PDF / Word / PowerPoint / Excel exports

## Safety
- ✅ API keys encrypted with Windows DPAPI
- ✅ Automatic daily backup (last 14 kept) plus manual backup and restore with a safety copy
- ✅ Everything stays on the PC; this repository holds only application source and fictional test data
