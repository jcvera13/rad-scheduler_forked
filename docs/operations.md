# Radiology Scheduler — Operations Guide

**Version:** 3.1.0  
**Last Updated:** 2026-02-21

---

## Quick Start

```bash
cd qgenda_scheduler/app_forked

# Activate virtual environment
source venv/bin/activate

# Generate schedule (dry run — no QGenda push)
python -m src.dry_run --start 2026-03-01 --end 2026-05-31

# Output files appear in ./outputs/
```

---

## CLI Reference

```
python -m src.dry_run [OPTIONS]

Required:
  --start YYYY-MM-DD    Schedule start date (inclusive)
  --end   YYYY-MM-DD    Schedule end date (inclusive)

Optional:
  --output-dir DIR      Output directory (default: ./outputs)
  --interactive         Pause before each scheduling block for review
  --save-cursors        Persist final cursor positions to cursor_state.json
  --visual              Generate matplotlib charts (shift/hours distribution, deviation, task breakdown)
```

### Example Runs

```bash
# Standard quarter run
python -m src.dry_run --start 2026-04-01 --end 2026-06-30

# Save cursors so next quarter picks up where this one left off
python -m src.dry_run --start 2026-04-01 --end 2026-06-30 --save-cursors

# Review each block interactively before committing
python -m src.dry_run --start 2026-04-01 --end 2026-06-30 --interactive

# With visual analysis (matplotlib charts)
python -m src.dry_run --start 2026-04-01 --end 2026-06-30 --visual

# Custom output directory
python -m src.dry_run --start 2026-04-01 --end 2026-06-30 --output-dir /tmp/q2_draft
```

---

## Output Files

Each run produces four files in `./outputs/` named by date range:

| File | Contents |
|---|---|
| `*_schedule.csv` | Long-form: one row per (date, shift, person) assignment |
| `*_schedule.xlsx` | Pivot table: dates as rows, shifts as columns, names as values |
| `*_fairness_report.txt` | Per-radiologist weighted workload, hours assigned, CV, top/bottom |
| `*_fairness_data.json` | Programmatic fairness: weighted_cv, hours_cv, hours_counts, unfilled |
| `*_violations.txt` | All hard and soft constraint violations with details |

When run with `--visual`, additional PNGs: `*_shift_distribution.png`, `*_hours_distribution.png`, `*_shift_deviation.png`, `*_task_breakdown.png`.

### Reading the Excel Pivot

- Rows = dates (Mon–Fri weekdays + Sat + Sun)
- Columns = shift codes (IR-1, IR-2, M0, M1, M2, M3, EP, Dx-CALL, Remote-MRI, ...)
- Each cell = at most one staff name per (date, shift); empty = shift not scheduled or unfilled

---

## Run Steps Explained

The engine runs in 6 steps, printed to console:

```
Step 1/6: Loading configuration
  Loads roster_key.csv, vacation_map.csv, cursor_state.json

Step 2/6: Validating inputs
  Roster structure, required columns, pool membership checks
  Subspecialty coverage — every rotation-managed shift has ≥1 qualified person

Step 3/6: Building date lists
  Weekdays (Mon–Fri) and Saturdays within the date range
  Sundays are added automatically after scheduling

Step 4/6: Running block scheduling
  23 blocks in priority order (IR → Mercy → Gen → Outpatient → Weekend)
  Each block picks from its eligible pool via weighted cursor

Step 5/6: Checking constraints
  Hard: vacation, double-booking, duplicate task (one person per date+shift),
        IR+Gen same day, two weekday tasks per person, pool gates, subspecialty mismatch
  Soft: back-to-back weekend, weighted CV and hours-assigned CV target

Step 6/6: Exporting outputs
  CSV, Excel, fairness report, violations file
```

---

## Interpreting the Fairness Report

```
Overall Weighted CV:   25.89%  (target <10%)  ✗ FAIL
Mean weighted load:    50.27
Std Dev:               13.02
Min / Max:             37.00 / 78.00
```

**What CV means here:** The coefficient of variation (std ÷ mean) across all 19
radiologists' weighted assignment counts. A lower number = more equal workload.

**Why CV is elevated (structural, not a bug):**

IR staff (DA, SS, SF, TR) hold IR-1, IR-2, and IR-CALL every weekday they are
not on vacation, plus Gen assignments, resulting in 50–80 weighted assignments
over two months. Non-IR staff share mercy and weekend pools across 15 people,
landing at 37–46. This reflects real compensation structure — IR specialists
carry higher load as part of their role. Track per-pool CV separately if needed:

```python
# IR pool CV only
ir_names = {"Derrick Allen","Sharjeel Sabir","Sina Fartash","Ted Rothenberg"}
ir_loads = {n: v for n,v in metrics["weighted_counts"].items() if n in ir_names}
```

**Per-shift CV** is high for specialty pools because the eligible pool is small
(e.g., only 4 staff for IR-1/IR-2 → CV 291%). This is expected and not
actionable. Target CV < 10% is most meaningful within the mercy and weekend pools.

---

## Managing Vacations

**Preferred:** Build `vacation_map.csv` from a QGenda .xlsx export so dry_run uses current exempt days (vacation, off all day, admin, No call, no ep):

```bash
# Place your QGenda export in inputs/, then:
python scripts/extract_vacation_map.py

# Or specify input and output:
python scripts/extract_vacation_map.py --input inputs/YourExport.xlsx --output config/vacation_map.csv
```

**Manual edit:** `config/vacation_map.csv` format (one row per date, staff semicolon-separated):

```csv
date,unavailable_staff
2026-04-07,Eric Chou;Karen Yuan
2026-04-08,Eric Chou
2026-05-25,Karen Yuan
```

- `date` = `YYYY-MM-DD`
- `unavailable_staff` = semicolon-separated full names matching `roster_key.csv` exactly
- Staff listed on a date are skipped by the cursor for that date (stream position preserved)

---

## Managing the Roster

Edit `config/roster_key.csv`. Key columns:

| Column | Values | Meaning |
|---|---|---|
| `name` | Full name string | Must be unique. Used as key everywhere. |
| `fte` | 0.1–1.0 | Relative scheduling frequency |
| `participates_mercy` | yes/no | Eligible for M0, M1, M2, M3 |
| `participates_ir` | yes/no | Eligible for IR-1, IR-2, IR-CALL |
| `participates_weekend` | yes/no | Eligible for EP, Dx-CALL, M0_WEEKEND |
| `participates_gen` | yes/no | Eligible for Gen and outpatient blocks |
| `participates_mg` | yes/no | Eligible for O'Toole and Breast blocks |
| `subspecialties` | comma-separated tags | Controls outpatient pool gates |

**Subspecialty tags** (case-sensitive in CSV, matched case-insensitively by engine):

| Tag | Enables |
|---|---|
| `ir` | IR-1, IR-2, IR-CALL |
| `MRI` | Remote/site/weekend MRI (except Wash-MRI) |
| `MRI+Proc` | **Wash-MRI** (Washington MRI) — staffed only by MRI+Proc-tagged staff |
| `MG` | All Breast shifts + O'Toole |
| `PET` | All PET shifts (Remote, Poway, weekend) |
| `Gen` | All Gen shifts (required for any outpatient Gen assignment) |
| `neuro` | Skull-Base (concurrent fixed, not rotation-managed) |
| `cardiac` | Cardiac (concurrent fixed, not rotation-managed) |

### Adding a New Radiologist

1. Add a row to `roster_key.csv` with a new `index` value (next integer in sequence).
2. Set `participates_*` flags appropriately.
3. Add subspecialty tags matching their clinical qualifications.
4. Run `python -m pytest tests/test_full_orchestration.py -v` — the roster
   validation tests will catch any misconfiguration.

### Adding an IR Radiologist

Set `participates_ir=yes`, `participates_mercy=no`, `participates_weekend=no`.
Add `ir` to subspecialties. The engine's `exclude_ir` gate will automatically
keep them out of mercy and weekend pools.

---

## Cursor State Management

`config/cursor_state.json` holds the current stream position for each of the
16 scheduling cursors. These persist across runs to ensure fairness accumulates
rather than resetting each period.

```json
{
  "gen_ir": 14.0,
  "gen_nonir": 27.5,
  "inpatient_weekday": 62.25,
  "inpatient_weekend": 18.0,
  "ir_call": 42.0,
  "ir_weekday": 42.0,
  ...
}
```

**Reset cursors** (start fresh for a new fiscal year or new group of radiologists):

```bash
python3 -c "
import json
from src.schedule_config import ALL_CURSOR_KEYS
state = {k: 0.0 for k in ALL_CURSOR_KEYS}
json.dump(state, open('config/cursor_state.json','w'), indent=2)
print('Cursors reset')
"
```

**Do not manually edit cursor values** unless correcting a known error — the
fractional values encode partial-shift weights and must remain consistent with
the stream position.

---

## Running Tests

```bash
python -m pytest tests/test_full_orchestration.py -v
```

**37 tests across 7 sections:**

| Section | Tests | What It Checks |
|---|---|---|
| 1. Roster Validation | 11 | Pool sizes, IR exclusions, FTE presence |
| 2. Subspecialty Parsing | 5 | Tag parsing, shift coverage |
| 3. Block Scheduling | 3 | Runs without error, correct shifts, no exclusive double-booking |
| 4. Constraint Checking | 6 | 0 hard violations: no vacation, no pool gate breaches |
| 5. Fairness Metrics | 6 | All keys present, all radiologists tracked |
| 6. Export Layer | 4 | CSV/Excel/report files exist and contain expected data |
| 7. Weekend Scheduling | 2 | Weekend block assigned, no back-to-back |

Run a single section:
```bash
python -m pytest tests/test_full_orchestration.py::TestConstraintChecking -v
```

---

## Troubleshooting

### "IR staff appearing in M0/M1/M2/M3"
- Check `roster_key.csv`: the IR radiologist must have `participates_mercy=no`
- Check `schedule_config.py`: the mercy blocks must have `"exclude_ir": True`
- Run `python -m pytest tests/test_full_orchestration.py::TestConstraintChecking::test_no_mercy_pool_gate_violations`

### "Could not fill [shift] on [date]" in log output
- For outpatient/subspecialty shifts this is expected on heavy-vacation days —
  the entire qualified pool may already be assigned elsewhere or on vacation.
- For M0/M1/M2/M3/IR-1/IR-2 this should never happen with 19 radiologists.
  If it does: check vacation_map.csv for overlapping entries that exhaust the pool.

### "SUBSPECIALTY_MISMATCH hard violation"
- The person assigned to a shift lacks the required tag in their `subspecialties` column.
- Either correct the roster (add the tag) or adjust the block's `subspecialty_gate`.
- Case matters in the CSV: use `MRI` not `mri`. The engine normalizes to lowercase internally.

### "TypeError: ... unexpected keyword argument 'saturday_dates'"
- Your local `dry_run.py` is an older version. Weekend scheduling moved inside
  `schedule_blocks()`. Replace `src/dry_run.py` with the current version.

### High CV (> 10%)
- CV above 10% for a 2-month period is expected due to IR/non-IR structural
  load difference. Run longer periods (6+ months) or evaluate per-pool CV.
- If non-IR staff CV is high, check that vacation entries are not concentrating
  assignments on a subset of people.

---

## Planned Features (Not Yet Implemented)

- **QGenda API push** — `dry_run.py` currently only generates files.
- **Outpatient rotation blocks** — Remote MRI/PET/Breast site rotation has
  per-site history weighting (Washington vs. Poway vs. Encinitas) not yet tracked.
- **FTE < 1.0 support** — All radiologists are currently 1.0 FTE. The cursor
  math supports partial FTE; needs roster data to activate.
- **Per-pool fairness reporting** — Report IR pool CV and mercy pool CV
  independently for cleaner fairness auditing.
