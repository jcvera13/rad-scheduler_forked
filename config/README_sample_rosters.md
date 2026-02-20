# Sample Roster Keys (SHIPMG Radiology)

These rosters were generated from the **QGenda "List by Staff Export"** historical file:

- **Imaging Healthcare - List by Staff Export - 6_21_2025 through 12_21_2025.xlsx**

They correct the earlier run that had **no IR (Interventional Radiology) personnel** loaded.

## Files

| File | Purpose | Staff count |
|------|---------|-------------|
| `sample_roster_key_diagnostic.csv` | Full SHIPMG pool (DR + IR); use for Mercy/weekend/DR fairness. | 19 |
| `sample_roster_key_interventional.csv` | IR-only pool (staff who have IR assignments in the export). | 4 |

## IR personnel (from historical export)

- Derrick Allen  
- Sharjeel Sabir  
- Sina Fartash  
- Ted Rothenberg  

## How they were derived

- **Diagnostic roster**: All non-placeholder staff in the export. `participates_ir` = `yes` only for the four who had at least one IR task (Mercy Hospital IR-1/IR-2, PVH IR, IR-CALL).
- **Interventional roster**: Only those four staff, with `participates_ir=yes`, `subspecialties=IR`.

## Usage

- **Scheduling engine** (`src/config.py`): Use `roster_key.csv` as the main roster. Populate it from `sample_roster_key_diagnostic.csv` and set `participates_ir` (and optionally FTE, email, exempt_dates) as needed.
- **Analyzer** (`scripts/analyze_schedule.py`): Use the new Excel as the schedule source. Optionally restrict to a pool:
  - `--roster config/sample_roster_key_diagnostic.csv` — fairness over full group
  - `--roster config/sample_roster_key_interventional.csv` — fairness over IR pool only

## Source format

The analyzer now auto-detects **QGenda "List by Staff Export"** (header on row 2: Date, Last Name, First Name, Task Name, HA, ...) and loads it correctly for fairness reports and subspecialty (including IR) charts.
