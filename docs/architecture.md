# Radiology Scheduler — Architecture Reference

**Version:** 3.1.0  
**Last Updated:** 2026-02-21

---

## Overview

The scheduler is a Python command-line tool that produces fair, constraint-valid
radiology rotation schedules and exports them for import into QGenda. It does
not push to QGenda directly; all runs are dry runs by default.

```
config/                     Runtime configuration
  roster_key.csv            19 radiologists + pool flags + subspecialties
  vacation_map.csv          date → unavailable_staff (semicolon-sep); from extract_vacation_map or manual
  cursor_state.json         16 fairness cursors, persisted across runs

inputs/                     QGenda .xlsx exports (optional)
  *.xlsx                    Source for scripts/extract_vacation_map.py → vacation_map.csv

src/
  schedule_config.py        Block definitions, shift codes, regex aliases, task grouping (mercy_weekday/weekend, weekend_outpt)
  engine.py                 Core scheduling algorithm + block orchestrator; one assignment per (date, shift); O'Toole Tue/Wed/Fri
  config.py                 CSV loaders, cursor I/O
  constraints.py            Hard/soft constraint checker
  skills.py                 Subspecialty qualification helpers (incl. MRI+Proc for Wash-MRI)
  exporter.py               CSV, Excel, fairness report, violations output
  dry_run.py                CLI entry point (--visual for matplotlib charts)

scripts/
  extract_vacation_map.py   Build vacation_map.csv from QGenda .xlsx (exempt: vacation, off, admin, no call, no ep)

tests/
  test_full_orchestration.py  37 integration tests across all sections

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

Every block filters the roster through two gates before the cursor runs:

```
Full Roster (19)
      │
      ▼
Pool Filter           e.g. participates_mercy=True → 15 staff
      │
      ▼
exclude_ir gate       if True: remove participates_ir=True staff
      │
      ▼
Subspecialty Gate     e.g. requires MRI tag → 6-8 staff
      │
      ▼
Eligible Pool         cursor picks from this set
```

### Pool Membership

| Staff | Pool Keys |
|---|---|
| Derrick Allen (DA) | IR + Gen + MG (mercy=No, weekend=No) |
| Sharjeel Sabir (SS) | IR + Gen only |
| Sina Fartash (SF) | IR + Gen only |
| Ted Rothenberg (TR) | IR + Gen only |
| All 15 non-IR | Mercy + Weekend + Gen + subspecialty tags |

### Subspecialty Tags (from roster_key.csv)

| Tag | Staff | Enables |
|---|---|---|
| `ir` | DA, SS, SF, TR | IR-1, IR-2, IR-CALL |
| `MRI` | BT, EC, EL, GA, JC, JV, KY, MB | Remote-MRI, Enc-MRI, Poway-MRI, Wknd-MRI |
| `MRI+Proc` | EL, GA, JC, JV, KY, MB | **Wash-MRI** (Washington MRI only) |
| `MG` | DA, EK, JC, JJ, KR, KY, MS, RT | Remote-Breast, Wash-Breast, Enc-Breast, O'Toole |
| `PET` | EK, MB, MG, YR | Remote-PET, Poway-PET, Wknd-PET |
| `Gen` | All 19 | Remote-Gen, Enc-Gen, Poway-Gen, NC-Gen, all Gen sites |
| `neuro` | BT, JC, JV | Skull-Base (concurrent, fixed) |
| `cardiac` | BT, JJ | Cardiac (concurrent, fixed) |

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

| Priority | Block | Exclusive | IR Excluded |
|---|---|---|---|
| 1 | IR-1 / IR-2 | Yes | — |
| 2 | IR-CALL | Yes | — |
| 3 | M3 Evening | Yes | **Yes** |
| 4 | M0 Helper | Yes | **Yes** |
| 5 | M1 + M2 | Yes | **Yes** |
| 6–7 | Remote Gen (non-IR / IR) | No | 6=Yes, 7=No |
| 8–10 | Remote MRI / Breast / PET | No | 8=Yes, 9=No, 10=Yes |
| 11–13 | Site MRI (Wash/Enc/Poway) | No | Yes |
| 14–15 | Site Breast (Wash/Enc) | No | 14=No, 15=Yes |
| 16 | Poway PET | No | Yes |
| 17–19 | Site Gen (Enc/Poway/NC) | No | No (IR eligible) |
| 20 | O'Toole (Tue/Wed/Fri only) | No | No (DA eligible) |
| 21 | Weekend Inpatient | No | **Yes** |
| 22–23 | Weekend MRI / PET | No | Yes |

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
| `check_vacation` | No one assigned on a vacation date |
| `check_double_booking` | No one in two exclusive shifts same day |
| `check_duplicate_task_assignment` | At most one staff per (date, shift) — no two radiologists on same task |
| `check_ir_and_gen_same_day` | No IR weekday (IR-1/IR-2) + Gen shift same day |
| `check_single_weekday_task_per_person` | No radiologist with two distinct weekday tasks same day |
| `check_mercy_pool_gate` | No IR staff in M0/M1/M2/M3 |
| `check_weekend_pool_gate` | No IR staff in EP/Dx-CALL/M0_WEEKEND |
| `check_ir_pool_gate` | No non-IR staff in IR-1/IR-2/IR-CALL |
| `check_subspecialty_qualification` | Shift requires tag person doesn't have (incl. MRI+Proc for Wash-MRI) |

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

Weekends are scheduled using **Saturday and Sunday as distinct dates** in `weekend_dates` (from `get_weekend_dates()`). Each weekend day gets its own cursor advance and assignments. Assignments:

- `M0_WEEKEND` — weekend helper
- `EP` — Early Person (on-site Saturday, remote Sunday)
- `Dx-CALL` — Late Person Call (remote)
- `Wknd-MRI` — Weekend MRI (when scheduled)
- `Wknd-PET` — Weekend PET (when scheduled)

The EP shift description notes "on-site Sat / remote Sun" but scheduling
assigns the same person to both days. Location difference is a QGenda shift
property, not a scheduling decision.

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
  ├── config.py           load_roster(), load_vacation_map(), load_cursor_state()
  ├── engine.py           schedule_blocks(), get_weekend_dates()
  │     └── schedule_config.py   SCHEDULING_BLOCKS, SHIFT_DEFINITIONS, task grouping
  ├── constraints.py      ConstraintChecker (incl. duplicate task, IR+Gen same day, two weekday tasks)
  │     └── skills.py     SHIFT_SUBSPECIALTY_MAP, normalize_task_name() (incl. MRI+Proc for Wash-MRI)
  └── exporter.py         export_to_csv(), export_to_excel(), export_fairness_report()
        └── engine.py     calculate_fairness_metrics() (incl. hours_counts, hours_cv)
```
