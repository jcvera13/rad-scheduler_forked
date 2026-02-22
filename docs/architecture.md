# Radiology Scheduler — Architecture Reference

**Version:** 3.2.0  
**Last Updated:** 2026-02-22

---

## Overview

The scheduler is a Python command-line tool that produces fair, constraint-valid
radiology rotation schedules and exports them for import into QGenda. It does
not push to QGenda directly; all runs are dry runs by default.

```
config/                     Runtime configuration
  roster_key.csv            Radiologists + pool flags (participates_mercy, participates_ir, participates_gen,
                            participates_MRI, participates_PET, etc.) + subspecialties
  vacation_map.csv          date → unavailable_staff (semicolon-sep); from extract_vacation_map or manual
  cursor_state.json         Fairness cursors per block, persisted across runs

dry_run_state.json          (project root) Exemption dates from --group runs; merged into unavailability for
                            subsequent group or full runs; cleared on full run or --reset

inputs/                     QGenda .xlsx exports (optional)
  *.xlsx                    Source for scripts/extract_vacation_map.py → vacation_map.csv

src/
  schedule_config.py        Block definitions, shift codes, regex aliases, TASK_FIXED_WEEKDAYS,
                            2-week cycle (Remote-Gen, NC-Gen), DRY_RUN_GROUPS, Neuro Friday
  engine.py                 Core algorithm + block orchestrator; IR-CALL weekend-mirrored;
                            Remote-Gen multi-slot; fixed weekdays + cycle date filtering
  config.py                 CSV loaders (roster with participates_MRI/PET fallback), cursor I/O
  constraints.py            Hard/soft checker; task allowed weekdays; duplicate task allows Remote-Gen multi-slot
  skills.py                 Subspecialty qualification (incl. Breast-Proc, MRI+Proc for Wash-MRI)
  exporter.py               CSV, Excel, fairness report, violations output
  dry_run.py                CLI (--start, --end, --group, --reset, --visual); loads/saves dry_run_state

scripts/
  extract_vacation_map.py   Build vacation_map.csv from QGenda .xlsx (exempt: vacation, off, admin, no call, no ep)

tests/
  test_full_orchestration.py  Integration tests across all sections

outputs/                    Generated per run (git-ignored)
  *.csv, *.xlsx, *_fairness_report.txt, *_fairness_data.json, *_violations.txt [, *_*.png with --visual]
```

---

## Core Algorithm — Weighted Cursor

The scheduler uses an **infinite modulo stream** to produce fair assignments
across arbitrarily long time horizons without rebalancing.

```
People = [P0, P1, P2, ... PN-1]   ordered by roster index
Cursor = float                      persisted across scheduling runs

For each shift slot on each date:
  pos = floor(cursor) % N
  Walk forward from pos skipping:
    - staff on vacation that date
    - staff already assigned an exclusive shift that date
    - staff not in the filtered pool for this block
  Assign to first eligible person found
  cursor += shift_weight
```

**Shift weights** control long-run assignment frequency:
- `M0` = 0.25 (2-hour helper, counts as quarter shift)
- `EP` = 0.81 (6.5-hour early person)
- `M1/M2/IR-1/IR-2` = 1.00 (full day)
- Concurrent/fixed assignments (Skull-Base, Cardiac) = 0.00 (not tracked)

FTE weighting is applied at the roster level; 1.0 FTE staff step through the
cursor at the standard rate.

---

## Pool Architecture

Every block filters the roster through pool filter, optional exclude_ir, subspecialty gate, and optional
**participates_MRI** / **participates_PET** before the cursor runs. For Gen site blocks, a **preferred_subspecialty**
(SOFT) sorts the pool so preferred-tag staff are picked earlier.

```
Full Roster
      │
      ▼
Pool Filter           e.g. participates_mercy=True or participates_gen=True
      │
      ▼
exclude_ir gate       if True: remove participates_ir=True staff
      │
      ▼
Subspecialty Gate     e.g. Breast-Proc (HARD), neuro, MRI, PET
      │
      ▼
require_participates_mri / require_participates_pet   (when set on block config)
      │
      ▼
Preferred subspecialty sort (optional)   e.g. North_Gen+Cont for Enc-Gen/Poway-Gen, South_Gen+Cont for NC-Gen
      │
      ▼
Eligible Pool         cursor picks from this set
```

### Roster Columns (roster_key.csv)

- **Pool flags:** `participates_mercy`, `participates_ir`, `participates_weekend`, `participates_gen`, `participates_outpatient`, `participates_mg`
- **participates_MRI** / **participates_PET:** Boolean; wired to all MRI/PET tasks. If column missing, inferred from subspecialties (e.g. MRI/MRI+Proc → MRI, PET → PET) for backward compatibility.

### Subspecialty Tags (from roster_key.csv)

| Tag | Constraint | Enables |
|---|---|---|
| `ir` | — | IR-1, IR-2, IR-CALL |
| `Breast-Proc` | **HARD** (required) | Wash-Breast, Enc-Breast, O'Toole (Mon/Tue/Wed only) |
| `North_Gen+Cont` | **SOFT** (prefer) | Enc-Gen, Poway-Gen — preferred; fallback to participates_gen |
| `South_Gen+Cont` | **SOFT** (prefer) | NC-Gen — preferred; fallback to participates_gen |
| `MRI` / `MRI+Proc` | + participates_MRI | Remote-MRI, Enc-MRI, Poway-MRI, Wknd-MRI; MRI+Proc for Wash-MRI |
| `MG` | (Breast tasks use Breast-Proc) | Remote-Breast; Wash/Enc Breast and O'Toole require Breast-Proc |
| `PET` | + participates_PET | Remote-PET, Poway-PET, Wknd-PET |
| `Gen` | — | Remote-Gen, Enc-Gen, Poway-Gen, NC-Gen |
| `neuro` | — | Skull-Base (e.g. Neuro Friday block), fixed assignments |
| `cardiac` | — | Cardiac (concurrent, fixed) |

---

## Block Scheduling Order

Blocks execute in priority order. Each block has an independent cursor and
builds on the accumulated schedule from all prior blocks.

**Exclusive blocks** (inpatient/IR): cross-block daily exclusion is enforced —
a person assigned to M1 cannot be assigned to M2 or any other exclusive shift
that day.

**Concurrent blocks** (outpatient): cross-block daily exclusion is **not**
enforced — a person assigned to M3 can also appear in Remote-MRI on the same
date. This matches real QGenda practice.

**Fixed day-of-week** and **2-week cycle** rules (see below) restrict which dates each block runs on; the engine filters block_dates accordingly before scheduling.

| Priority | Block | Exclusive | IR Excluded | Notes |
|---|---|---|---|---|
| 1 | IR-1 / IR-2 | Yes | — | Weekdays only |
| 2 | IR-CALL | Yes | — | **Weekend only (Sat+Sun); mirrored** — one person per weekend for both days |
| 3 | M3 Evening | Yes | **Yes** | |
| 4 | M0 Helper | Yes | **Yes** | |
| 5 | M1 + M2 | Yes | **Yes** | |
| 6 | O'Toole | No | No (DA if Breast-Proc) | **Mon/Tue/Wed only**; Breast-Proc required |
| 7–8 | Wash / Enc Breast | No | 7=No, 8=Yes | Breast-Proc required |
| 9–11 | Site MRI (Wash/Enc/Poway) | No | Yes | participates_MRI + subspecialty |
| 12 | Poway PET | No | Yes | participates_PET |
| 13–15 | Site Gen (Enc/Poway/NC) | No | No | North_Gen+Cont / South_Gen+Cont prefer |
| 16–17 | Remote Gen (non-IR / IR) | No | 16=Yes, 17=No | **2-week cycle**; Week 2 some days 2 staff (Remote-Gen) |
| 18–20 | Remote MRI / Breast / PET | No | 18=Yes, 19=No, 20=Yes | |
| 21 | Weekend Inpatient | No | **Yes** | |
| 22–23 | Weekend MRI / PET | No | Yes | participates_MRI / participates_PET |
| 24 | Neuro Friday (Skull-Base) | No | Yes | Fridays only; round-robin neuro tag (dry_run group3) |

### 2-Week Cycle and Fixed Weekdays

- **Cycle week** is derived from the schedule start: `(date - cycle_start).days // 7 % 2` (0 = week 1, 1 = week 2).
- **Remote-Gen (gen_nonir):** Week 1: Mon, Tue, Fri (1 slot each). Week 2: Mon, Tue (2 each), Wed (1), Thu (2). Merge allows up to 2 staff per (date, Remote-Gen).
- **NC-Gen:** Week 1 Mon–Fri; Week 2 **Mon–Tue only**.
- **TASK_FIXED_WEEKDAYS** (in `schedule_config`) restricts each task to allowed weekdays (e.g. Enc-Breast Tue/Wed, Enc-MRI Mon, Poway-MRI Wed, Wash-Breast Mon/Fri, IR-CALL Sat/Sun). Validation rejects assignments outside those days.

---

## QGenda Task Name Normalization

Raw QGenda task strings are mapped to engine shift codes via 39 regex patterns
in `schedule_config.QGENDA_TASK_REGEX_ALIASES`. Patterns are applied
case-insensitively; first match wins.

```python
from src.schedule_config import normalize_task_name

normalize_task_name("Mercy 0 (M0 (remote) 0700-0800, 1130-1230)")
# → "M0"

normalize_task_name("IHS Poway PET x1680 (Poway PET 0800-1700)")
# → "Poway-PET"

normalize_task_name("IHS Remote General (Remote General)")
# → "Remote-Gen"

normalize_task_name("Scripps O'Toole Breast Center (O'Toole 0730-1630)")
# → "O'Toole"
```

---

## Constraint Checking

`ConstraintChecker.check_all(schedule)` returns `(hard_violations, soft_violations)`.

### Hard Constraints (block schedule if violated)
| Check | Rule |
|---|---|
| `check_vacation` | No one assigned on a vacation (or exemption) date |
| `check_double_booking` | No one in two exclusive shifts same day |
| `check_duplicate_task_assignment` | At most one staff per (date, shift); **Remote-Gen** allows up to 2 per (date, shift) |
| `check_task_allowed_weekdays` | Assignment date must be in TASK_FIXED_WEEKDAYS for that shift |
| `check_ir_and_gen_same_day` | No IR weekday (IR-1/IR-2) + Gen shift same day |
| `check_single_weekday_task_per_person` | No radiologist with two distinct weekday tasks same day |
| `check_mercy_pool_gate` | No IR staff in M0/M1/M2/M3 |
| `check_weekend_pool_gate` | No IR staff in EP/Dx-CALL/M0_WEEKEND |
| `check_ir_pool_gate` | No non-IR staff in IR-1/IR-2/IR-CALL |
| `check_subspecialty_qualification` | Shift requires tag person doesn't have (incl. Breast-Proc, MRI+Proc for Wash-MRI) |

### Soft Constraints (logged, not blocked)
| Check | Rule |
|---|---|
| Back-to-back weekend | Same person two consecutive weekends |
| Workload CV exceeded | Weighted or hours-assigned CV > 10% target |

---

## Fairness Metrics

`calculate_fairness_metrics(schedule, roster)` returns:

```python
{
  "mean":           float,         # mean weighted load across all staff
  "std":            float,
  "cv":             float,         # coefficient of variation (std/mean)
  "min":            float,
  "max":            float,
  "counts":         {name: int},   # raw assignment count per person
  "weighted_counts":{name: float}, # shift-weight-adjusted load per person
  "hours_counts":   {name: float}, # total hours assigned per person (from SHIFT_DEFINITIONS)
  "hours_mean":     float,
  "hours_std":      float,
  "hours_cv":       float,         # CV of hours assigned (fairness/balance)
  "per_shift":      {shift: {name: int}},
  "per_shift_cv":   {shift: float},
  "unfilled":       int,
}
```

**CV target:** < 10%. The 25% overall CV in the Jan–Mar 2026 run reflects
structural load differentiation: IR staff (4 people) hold IR-1 + IR-2 + IR-CALL
every weekday while sharing Gen assignments, resulting in 50–80 weighted
assignments vs. 37–46 for non-IR staff. Per-pool CV (IR pool vs. mercy pool
separately) converges faster.

---

## Task Grouping (schedule_config.py)

Rotation configs are grouped into three explicit types:

- **mercy_weekday_cfg** — Mercy inpatient weekday (M0, M1, M2, M3); non-IR only. Built via `_mercy_weekday_cfg()`.
- **mercy_weekend_cfg** — Mercy inpatient weekend (M0_WEEKEND, EP, Dx-CALL); non-IR only. Built via `_mercy_weekend_cfg()`.
- **weekend_outpt_cfg** — Weekend outpatient (Wknd-MRI, Wknd-PET). Built via `_weekend_outpt_cfg()`.

Block configs reference these helpers; backwards-compat aliases were removed in 3.1.

---

## Weekend Scheduling

Weekends use **Saturday and Sunday** from `get_weekend_dates()`.

- **IR-CALL** is **weekend-only and mirrored:** one IR staff is assigned to **both** Saturday and Sunday of each weekend (same person both days). Implemented via `_schedule_ir_call_mirrored()` and weekend pairs; it does not use the generic `schedule_period` path.
- **Inpatient weekend** (M0_WEEKEND, EP, Dx-CALL) and **weekend outpatient** (Wknd-MRI, Wknd-PET) use `weekend_dates` as a flat list; each day gets its own cursor advance. EP is one person per weekend day (location on-site Sat / remote Sun is a QGenda property, not a scheduling split).

---

## Cursor Persistence

After a run with `--save-cursors`, `cursor_state.json` is updated with the
final cursor value for each block. The next run resumes from those positions,
ensuring fairness accumulates correctly across scheduling periods rather than
restarting from the same person each period.

```bash
# Period 1 — save state
python -m src.dry_run --start 2026-01-01 --end 2026-03-31 --save-cursors

# Period 2 — resumes from saved cursor positions
python -m src.dry_run --start 2026-04-01 --end 2026-06-30 --save-cursors
```

---

## Grouped Dry Run (--group) and Exemption State

Dry-run can schedule **only a named group** of blocks, then record **exemption days** for the assigned staff so they are not double-assigned in later group runs or in a full run.

- **`--group group1|group2|group3|group4`** — Run only the blocks in that group (see `schedule_config.DRY_RUN_GROUPS`).
- **`--reset`** — Clear `dry_run_state.json` before the run (use before a full schedule or to discard prior exemptions).
- **dry_run_state.json** (project root) stores `exemption_dates`: `{ date_str: [name1, name2, ...] }`. When present, these dates are merged into the vacation/unavailability map for the run so those staff are excluded from other blocks on those days.
- **Exemption extrapolation:** After a run with `--group`, the engine extrapolates exemption days from the schedule (each assigned person is marked unavailable on that date) and merges them into the state file. Full run (no `--group`) clears the state after scheduling.

**Groups:**

| Group | Block IDs |
|---|---|
| group1 | ir_weekday, ir_call, m3_weekday |
| group2 | m0_weekday, m1m2_weekday, otoole, wash_breast, enc_breast |
| group3 | neuro_friday (Skull-Base, Fridays only, round-robin neuro) |
| group4 | wknd_mri, wknd_pet |

```bash
# Schedule only IR + M3, then update exemption state
python -m src.dry_run --start 2026-03-01 --end 2026-05-31 --group group1

# Later: full run clears dry_run_state; or --reset to clear before run
python -m src.dry_run --start 2026-03-01 --end 2026-05-31 --reset
```

---

## Vacation Map and Inputs

`config/vacation_map.csv` has columns `date`, `unavailable_staff`. Each row is one date (YYYY-MM-DD) with semicolon-separated staff names who are unavailable that day. Populate manually or via:

```bash
python scripts/extract_vacation_map.py   # reads first .xlsx in inputs/, writes config/vacation_map.csv
```

`extract_vacation_map.py` parses QGenda List by Assignment Tag or List by Staff Export, extracts rows whose task matches exempt patterns (vacation, off all day, admin, no call, no ep), and aggregates by date. Staff names are normalized to "First Last" to match `roster_key.csv`.

---

## File Dependencies

```
dry_run.py
  ├── config.py             load_roster() (participates_MRI/PET), load_vacation_map(), load_cursor_state()
  ├── engine.py             schedule_blocks() (blocks=, weekend_dates=), get_weekend_dates(),
  │                         _schedule_ir_call_mirrored(), cycle/date filtering
  │     └── schedule_config.py   SCHEDULING_BLOCKS, TASK_FIXED_WEEKDAYS, REMOTE_GEN_CYCLE_WEEKDAYS,
  │                             DRY_RUN_GROUPS, ALLOW_MULTIPLE_PER_SLOT_SHIFTS
  ├── constraints.py        ConstraintChecker (task allowed weekdays, duplicate task allows Remote-Gen multi-slot)
  │     └── skills.py       SHIFT_SUBSPECIALTY_MAP, normalize_task_name()
  ├── dry_run_state.json    load_dry_run_state(), save_dry_run_state(), merge_exemptions_into_vacation()
  └── exporter.py           export_to_csv(), export_to_excel(), export_fairness_report()
        └── engine.py       calculate_fairness_metrics()
```
