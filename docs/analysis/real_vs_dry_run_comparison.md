# Real Schedule vs Dry Run — Comparison & Improvement Plan

**Period:** 3/1/2026 – 5/31/2026  
**Sources:** `docs/Real+Schedule_3_1_2026 through 5_31_2026.xlsx` (QGenda export) vs `outputs/dry_run_2026-03-01_2026-05-31_schedule.xlsx`

---

## Executive Summary

The dry run produces **344 UNFILLED** slots over the period, concentrated in **Remote-Gen, Remote-MRI, Remote-Breast, Remote-PET**, and to a lesser extent **NC-Gen, Enc-Breast, IR-CALL, Poway-*, Enc-MRI, Wash-Breast, Wash-MRI**. The real schedule fills these roles with fewer total assignments per shift type and sometimes **multiple staff on the same (date, shift)** for remote work. Root cause: the engine tries to fill **one slot per weekday for every outpatient block** (65 weekdays × many blocks), while the real schedule uses **demand-based coverage** (e.g. ~26 Remote-Gen over 65 days, ~34 Remote-MRI) and allows **2–3 people for the same shift on the same day** for remote roles.

---

## 1. Real Schedule — Assignment Counts (Work Tasks Only)

| Shift         | Real count | Approx per weekday |
|---------------|------------|---------------------|
| Remote-MRI    | 34         | ~0.5                |
| Remote-Breast | 32         | ~0.5                |
| M3            | 31         | ~0.5                |
| M0            | 31         | ~0.5                |
| M2            | 29         | ~0.45               |
| M1            | 28         | ~0.43               |
| Remote-Gen    | 26         | ~0.4                |
| IR-1 / IR-2   | 25 each    | ~0.38               |
| IR-CALL       | 16         | ~0.25               |
| Wash-MRI, Remote-PET, NC-Gen, O'Toole | 15 each | ~0.23 |
| EP, Dx-CALL   | 13, 12     | ~0.2                |
| M0_WEEKEND, Wknd-MRI, Wknd-PET | 11 each | weekend only |
| Poway-PET, Poway-Gen, Enc-Gen, Wash-Breast, Enc-Breast | 10 each | ~0.15 |
| Poway-MRI, Enc-MRI | 5 each   | ~0.08               |

**Observation:** Real schedule does **not** fill every outpatient shift every weekday. Remote and site outpatient are used at **sub-daily** rates (e.g. Remote-Gen ~0.4/day, Enc-MRI ~0.08/day).

---

## 2. Real Schedule — Multiple Staff per (Date, Shift)

The real schedule has **20 (date, shift) combinations with 2+ people** assigned:

- **Remote-MRI:** 2 or 3 people on the same day (e.g. 2026-03-13, 2026-03-27)
- **Remote-Breast:** 2 people on the same day on several dates
- **Remote-Gen:** 2 people on the same day on several dates

So real operations allow **concurrent coverage** for remote roles (multiple radiologists on Remote-MRI, Remote-Breast, Remote-Gen the same day). The current engine enforces **exactly one assignment per (date, shift)** and **one outpatient assignment per person per day**, which prevents matching this pattern.

---

## 3. Dry Run — Where UNFILLED Concentrates

| Shift          | Filled | UNFILLED | Total slots |
|----------------|--------|----------|-------------|
| Remote-PET     | 0      | 65       | 65          |
| Remote-Breast  | 1      | 64       | 65          |
| Remote-MRI     | 1      | 64       | 65          |
| Remote-Gen     | 5      | 60       | 65          |
| NC-Gen         | 30     | 35       | 65          |
| Enc-Breast     | 51     | 14       | 65          |
| IR-CALL        | 55     | 10       | 65          |
| Poway-PET      | 55     | 10       | 65          |
| Poway-MRI      | 56     | 9        | 65          |
| Poway-Gen      | 57     | 8        | 65          |
| Enc-MRI        | 63     | 2        | 65          |
| Wash-Breast    | 63     | 2        | 65          |
| Wash-MRI       | 64     | 1        | 65          |

**Total UNFILLED:** 344.

**Root cause (simplified):**

- **Exclusive weekday:** 7 people/day (IR-1, IR-2, M3, M0, M1, M2) + O'Toole on Tue/Wed/Fri.
- **Outpatient slots attempted:** ~12+ site/remote blocks × 1 slot/day = 12+ slots/day.
- **Non-IR pool:** 15 people. After 7 exclusive + 1 O'Toole (some days) ≈ 8 people left for outpatient. So we need 12+ outpatient assignments but only ~8 people available → 4+ UNFILLED per day for later blocks (Remote-*, NC-Gen, etc.).
- **One assignment per (date, shift):** We never add a second person for the same shift on the same day, so we cannot mimic real “2× Remote-MRI” days.
- **One outpatient per person per day:** Each person can only cover one outpatient slot per day, which is correct for fairness but forces a hard cap on total outpatient coverage.

---

## 4. Recommended Improvements (for Current Project)

### A. **Demand-based frequency for outpatient blocks (high impact)**

- **Idea:** Do not schedule every outpatient block on every weekday. Cap how many weekdays per period a block runs (e.g. “Remote-Gen 2×/week”, “Remote-MRI 3×/week”).
- **Implementation:** Add an optional block-level config, e.g. `max_slots_per_week` or `weekday_fraction`, and when building `block_dates` for that block, restrict to a subset of weekdays (e.g. randomly or by cursor so fairness is preserved). Example: `max_slots_per_week=2` for Remote-Gen → only 2 weekdays per week get a Remote-Gen slot.
- **Effect:** Fewer slots to fill, so pool is not exhausted; filled rate for remote/site outpatient increases and UNFILLED drops.

### B. **Allow multiple staff per (date, shift) for designated shifts (medium impact)**

- **Idea:** For shifts that in the real schedule often have 2+ people (e.g. Remote-MRI, Remote-Breast, Remote-Gen), allow the engine to assign a second (and optionally third) person the same (date, shift) instead of enforcing strict uniqueness.
- **Implementation:** Add an optional block-level flag, e.g. `allow_multiple_per_slot=True`, and for those blocks either:
  - run the block with `shifts_per_period=2` (or 3) on the same dates, or
  - in the merge step, allow appending another (same shift, same date) when the shift is in an “allow_multiple” set (and optionally cap at 2–3).
- **Effect:** Matches real “2× Remote-MRI” days and increases filled coverage for those roles without creating double-booking for exclusive shifts.

### C. **Block order / pool priority (lower impact)**

- **Idea:** Schedule “high demand” or “often UNFILLED” blocks (e.g. Remote-Gen, Remote-MRI) earlier so they get first pick of the outpatient pool, or schedule them after fewer competing blocks.
- **Trade-off:** Putting remote before site could unbalance site coverage. Prefer A and B first.

### D. **Vacation / exempt days (already in place)**

- **Real schedule:** Exempt tasks (VACATION, OFF ALL DAY, Admin, No Call, No EP) are excluded from work counts. The project’s `extract_vacation_map.py` and `vacation_map.csv` already feed this into dry_run so unavailability is respected. No change needed for this.

### E. **Roster and subspecialty alignment**

- Ensure roster tags (MRI, MRI+Proc, MG, PET, Gen) and pool flags match real staffing so pool sizes and eligibility are not artificially small (e.g. Remote-PET 0 filled suggests PET pool may be too small or over-committed earlier in the block order). Review `roster_key.csv` and block order for Remote-PET, Remote-Breast, Remote-MRI.

---

## 5. Implementation Done (slots_per_week)

- **A. Demand-based frequency** was implemented in `engine.py` and `schedule_config.py`:
  - `config.get("slots_per_week")` — when set, weekday block dates are limited to that many days per ISO week (first N weekdays of each week).
  - Applied to: **GEN_NONIR_CONFIG** (2/week), **REMOTE_MRI_CONFIG** (3), **REMOTE_BREAST_CONFIG** (3), **REMOTE_PET_CONFIG** (2), **NC_GEN_CONFIG** (2), based on real schedule counts.
- **Result:** UNFILLED dropped from **344 → 223** for the same period (3/1–5/31/2026). Total assignments 1344; remaining UNFILLED are mostly IR-CALL, NC-Gen, Enc-Breast, Poway-*, and remote when pool is exhausted.

## 6. Hard Violations (TWO_WEEKDAY_TASKS) After slots_per_week

The current run reports **55 hard violations**: all are **IR staff (DA, SS, SF, TR) with IR-CALL and another outpatient** (Enc-Gen, NC-Gen, Poway-Gen, Remote-Gen, Wash-Breast, O'Toole) on the same day. The engine treats “no two distinct weekday tasks” as strict, so IR-CALL + any other assignment flags. In the real schedule, **IR-CALL may be an “on call” overlay** so that having another assignment the same day is allowed. If so, consider relaxing the constraint for **IR-CALL** only (e.g. do not count IR-CALL toward “one task per weekday” so IR can have IR-CALL + one Gen/outpatient). Not changed in code yet; document and product owner can decide.

## 7. Next Steps (Optional)

1. **Implement B (allow multiple per slot)** for Remote-MRI, Remote-Breast, Remote-Gen so 2 people can be assigned the same (date, shift) where the real schedule does.
2. **IR-CALL + same-day outpatient:** If real operations allow IR-CALL plus one other task for IR staff, add an exception in constraints and in engine augmented_vacation so IR-CALL assignees are not excluded from outpatient blocks that day (and/or do not flag TWO_WEEKDAY_TASKS when the second task is IR-CALL).
3. Re-run dry_run and compare UNFILLED and violation counts.
4. Optionally add a script under `scripts/` that loads real and dry-run xlsx, normalizes shift names, and reports filled vs UNFILLED by shift.

---

## 8. Data Summary (for reproducibility)

- **Real:** 455 work assignment rows (exempt excluded), 55 unique dates, 20 (date, shift) with 2+ people.
- **Dry run:** 92 rows (dates) × 26 shift columns; 344 UNFILLED total; Remote-PET/Remote-Breast/Remote-MRI/Remote-Gen account for the majority of UNFILLED.
