# Radiology Scheduler — Changelog

All notable changes to the scheduling engine are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [3.0.0] — 2026-02-21

### Summary
Complete overhaul of the assignment coverage model. The engine now schedules
all 23 real rotation types derived from QGenda data (Jan–Mar 2026), enforces
hard IR/non-IR pool separation at the filter level, and correctly outputs both
Saturday and Sunday for every weekend period.

---

### Added

#### Pool Enforcement (`engine.py`, `schedule_config.py`)
- `exclude_ir` flag on every block config. When `True`, `_filter_pool()` strips
  all staff with `participates_ir=True` before any cursor math. IR staff
  (DA, SS, SF, TR) are now **hard-excluded** from M0, M1, M2, M3,
  M0_WEEKEND, EP, and Dx-CALL at the engine level — not just by roster tag.
- `concurrent_ok` flag on outpatient/subspecialty blocks. When `True`, the
  engine skips the cross-block daily exclusion for that block, allowing a
  radiologist to hold one inpatient shift + multiple outpatient assignments
  on the same date (mirrors real QGenda practice: JJ does M1 + Cardiac,
  JC does Remote-MRI + Skull-Base, etc.).

#### New Shift Types (`schedule_config.py`)
Expanded from 7 shift codes to 39. New codes added, all regex-matched from
raw QGenda task strings:

| Code | QGenda Task |
|---|---|
| `IR-CALL` | IR-CALL (RMG) |
| `Remote-Gen` | IHS Remote General |
| `Remote-MRI` | IHS Remote MRI |
| `Remote-Breast` | IHS Remote Breast & US |
| `Remote-PET` | IHS Remote PET |
| `Wash-MRI` | IHS Washington MRI x1080 |
| `Wash-Breast` | IHS Washington Breast & US x1081 |
| `Enc-MRI` | IHS Encinitas MRI x1580 |
| `Enc-Breast` | IHS Encinitas Breast & US x1581 |
| `Enc-Gen` | IHS Encinitas General x1580 |
| `Poway-MRI` | IHS Poway MRI x1680 |
| `Poway-PET` | IHS Poway PET x1680 |
| `Poway-Gen` | IHS Poway General x1680 |
| `NC-Gen` | IHS National City General x2280 |
| `NC-PET` | IHS National City PET x2280 |
| `NC-Breast` | IHS National City Breast x2280 |
| `NC-MRI` | IHS National City MRI x2280 |
| `O'Toole` | Scripps O'Toole Breast Center |
| `Wknd-MRI` | Weekend IHS MRI |
| `Wknd-PET` | Weekend IHS PET |

Fixed/concurrent shifts (weight=0, not rotation-managed):
`Skull-Base`, `Cardiac`

#### QGenda Regex Normalizer (`schedule_config.py`)
- `normalize_task_name(raw_string)` — 39-pattern regex map converts any raw
  QGenda task string to an engine shift code. First match wins.
  Case-insensitive. Falls back to the raw string if no pattern matches.
- Bare `"gen"` or `"general"` normalizes to `"Remote-Gen"`.
- Used by `skills.py`, `constraints.py`, and the planned QGenda import parser.

#### New Scheduling Blocks
Expanded from 8 blocks to 23, in priority order:

| # | Block | Pool | IR Excluded | Concurrent |
|---|---|---|---|---|
| 1 | IR-1 / IR-2 | participates_ir | No | No |
| 2 | IR-CALL | participates_ir | No | No |
| 3 | M3 Evening | participates_mercy | **Yes** | No |
| 4 | M0 Helper | participates_mercy | **Yes** | No |
| 5 | M1 + M2 | participates_mercy | **Yes** | No |
| 6 | Remote Gen (non-IR) | participates_gen | **Yes** | Yes |
| 7 | Remote Gen (IR staff) | participates_ir | No | Yes |
| 8 | Remote MRI | participates_gen + MRI tag | **Yes** | Yes |
| 9 | Remote Breast | participates_gen + MG tag | No (DA eligible) | Yes |
| 10 | Remote PET | participates_gen + PET tag | **Yes** | Yes |
| 11 | Washington MRI | participates_gen + MRI tag | **Yes** | Yes |
| 12 | Encinitas MRI | participates_gen + MRI tag | **Yes** | Yes |
| 13 | Poway MRI | participates_gen + MRI tag | **Yes** | Yes |
| 14 | Washington Breast | participates_gen + MG tag | No (DA eligible) | Yes |
| 15 | Encinitas Breast | participates_gen + MG tag | **Yes** | Yes |
| 16 | Poway PET | participates_gen + PET tag | **Yes** | Yes |
| 17 | Encinitas Gen | participates_gen + Gen tag | No (IR eligible) | Yes |
| 18 | Poway Gen | participates_gen + Gen tag | No (IR eligible) | Yes |
| 19 | NC Gen | participates_gen + Gen tag | No (IR eligible) | Yes |
| 20 | O'Toole | participates_mg + MG tag | No (DA eligible) | Yes |
| 21 | Weekend Inpatient | participates_weekend | **Yes** | Yes |
| 22 | Weekend MRI | participates_gen + MRI tag | **Yes** | Yes |
| 23 | Weekend PET | participates_gen + PET tag | **Yes** | Yes |

#### Sunday Output (`engine.py`, `dry_run.py`)
- `expand_weekend_to_sunday(schedule)` — new function that mirrors every
  Saturday entry into the following Sunday. Weekend staff (EP, M0_WEEKEND,
  Dx-CALL, Wknd-MRI, Wknd-PET) cover both days; the engine now outputs
  both dates with identical assignments.
- Called automatically in `dry_run.py` after `schedule_blocks()`.
- Schedule output now includes 60 dates for a 2-month period
  (42 weekdays + 9 Saturdays + 9 Sundays) vs. 51 previously.

#### Cursor State (`cursor_state.json`)
- 16 cursor keys now tracked (was 3):
  `gen_ir`, `gen_nonir`, `inpatient_weekday`, `inpatient_weekend`,
  `ir_call`, `ir_weekday`, `otoole`, `remote_breast`, `remote_mri`,
  `remote_pet`, `site_breast`, `site_gen`, `site_mri`, `site_pet`,
  `wknd_mri`, `wknd_pet`

#### `skills.py` — Rewritten
- Now derives `SHIFT_SUBSPECIALTY_MAP` directly from `SHIFT_DEFINITIONS`
  (single source of truth — no manual duplication).
- Uses `normalize_task_name()` so raw QGenda strings are accepted everywhere.
- `OUTPATIENT_ONLY_SHIFTS` and `FIXED_ASSIGNMENT_SHIFTS` sets control which
  shifts are skipped during roster coverage validation.

---

### Fixed

#### `dry_run.py` — Stale `schedule_weekend_mercy()` Call
- **Bug:** Local copies had a direct call to `schedule_weekend_mercy(saturday_dates=...)`
  which no longer exists. Weekend scheduling is now handled inside `schedule_blocks()`.
- **Fix:** Removed the stale call. `dry_run.py` passes `weekend_dates=saturday_dates`
  to `schedule_blocks()` and calls `expand_weekend_to_sunday()` on the result.

#### `engine.py` — Weekend Blocks on Weekday Dates
- **Bug:** Weekend-type blocks (schedule_type="weekend") fell back to weekday
  dates when no `saturday_dates` were provided, causing M0_WEEKEND to appear
  on Mondays in test fixtures.
- **Fix:** Weekend blocks now unconditionally skip when `weekend_dates` is empty.

#### `constraints.py` — Case-Insensitive Subspecialty Matching
- **Bug:** `check_subspecialty_qualification()` compared raw required tags
  (`{'MRI'}`) against lowercased person specs (`{'mri'}`), producing false
  SUBSPECIALTY_MISMATCH hard violations for every outpatient assignment.
- **Fix:** Required tags are now lowercased before comparison.

#### `constraints.py` — Double-Booking Definition
- **Bug:** `check_double_booking()` flagged any radiologist appearing more than
  once per day, incorrectly treating concurrent outpatient assignments as
  violations (e.g., James Cooper: Remote-MRI + Skull-Base).
- **Fix:** Only **exclusive** shifts (M0/M1/M2/M3, IR-1/IR-2/IR-CALL, EP/Dx-CALL/M0_WEEKEND)
  are checked for double-booking. Outpatient and subspecialty assignments
  on the same date are permitted.

#### `config.py` — Backward-Compatible Imports
- Removed stale re-exports of `INPATIENT_WEEKDAY_CONFIG` and
  `INPATIENT_WEEKEND_CONFIG` (renamed in schedule_config). Added aliases
  (`M3_CONFIG`, `WEEKEND_CONFIG`) to maintain backward compatibility with
  existing test fixtures.

---

### Changed

#### `schedule_config.py` — Complete Rewrite
- Old file defined 8 blocks with 3 cursor keys.
- New file defines 23 blocks with 16 cursor keys, pool config helpers,
  O'Toole weekday filter (`OTOOLE_WEEKDAYS`), fixed subspecialty assignments
  dict, and the full regex alias table.

#### `constraints.py` — Pool Gate Checks Formalized
- `check_mercy_pool_gate()`, `check_weekend_pool_gate()`, and
  `check_ir_pool_gate()` now complement the engine-level `exclude_ir` flag.
  Both layers must pass for an assignment to be valid.

#### Test Suite (`test_full_orchestration.py`)
- All fixtures updated to pass `ALL_CURSOR_KEYS` cursor state dict.
- `test_no_unfilled_slots` — relaxed: outpatient subspecialty slots may be
  UNFILLED when the qualified pool is exhausted; only mercy/IR inpatient
  slots are required to fill.
- `test_no_double_booking` — updated to only check exclusive shifts.
- Added `schedule` fixture to `TestConstraintChecking` for the unfilled test.
- `metrics_fixture` now returns `(metrics, schedule)` tuple.
- **37/37 tests passing.**

---

## [2.1.0] — 2026-02-20

### Added
- Explicit `participates_mercy`, `participates_ir`, `participates_weekend`,
  `participates_gen`, `participates_outpatient`, `participates_mg` boolean
  columns to `roster_key.csv`.
- `_parse_yes_no()` helper in `config.py` to parse YES/NO/yes/no strings.
- `filter_pool()` exported from `config.py` for test fixtures.

### Fixed
- `skills.py` — added `OUTPATIENT_ONLY_SHIFTS` set to suppress false-positive
  coverage warnings for remote/site outpatient shifts.
- `skills.py` — normalized required subspecialty tags to lowercase in
  `get_qualified_staff()` to fix MG vs mg tag mismatch.

### Changed
- IR pool (DA, SS, SF, TR) restricted: `participates_mercy=NO`,
  `participates_weekend=NO` for SS, SF, TR. DA retains `participates_mg=YES`.
- Test assertions: `test_mercy_pool_size` updated to expect 15 (not 19).

---

## [2.0.0] — 2026-02-15

### Added
- Block scheduling engine (`schedule_blocks()`) with priority-ordered blocks.
- `ConstraintChecker` with hard/soft violation reporting.
- `calculate_fairness_metrics()` with per-radiologist and per-shift CV.
- Export layer: CSV, Excel (pivot), fairness report text, violations file.
- `dry_run.py` CLI with `--start`, `--end`, `--interactive`, `--save-cursors`.
- `cursor_state.json` for cross-period fairness continuity.

---

## [1.0.0] — 2026-02-01

### Added
- Initial weighted cursor algorithm (infinite modulo stream).
- FTE-weighted assignment frequency.
- Vacation-aware scheduling (skipped staff retain stream position).
- Back-to-back weekend avoidance.
- `roster_key.csv` with 19 radiologists.
