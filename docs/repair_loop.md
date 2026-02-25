# Cursor Agent Prompt — Dry Run Repair Loop

## Usage
Paste the prompt below directly into Cursor's agent/composer input.

---

## Prompt

You are a senior Python engineer on a radiology scheduling system. Your task is to implement an automated iterative repair process that activates when a dry_run completes with unfilled assignments. Read ALL existing files before writing any code — especially dry_run.py, engine.py, constraints.py, schedule_config.py, and roster_key.csv. Follow all existing conventions.

---

## CONTEXT

The dry_run CLI generates a preview schedule and reports any unfilled assignments (slots where no qualified staff could be matched). Currently the process stops there. We need an automated repair loop that attempts to resolve those gaps before surfacing results to the user.

---

## TASK — IMPLEMENT THE REPAIR LOOP

### Trigger Condition

After any dry_run completes, inspect the output for unfilled assignments. If any exist, automatically enter the repair loop. If none exist, exit normally as before — no behavior change for clean runs.

### Repair Loop Architecture

Implement as a dedicated module: `src/repair.py`

The loop must be called from within dry_run.py immediately after the initial schedule generation, before any output is printed to the user. Signature should follow whatever pattern dry_run.py uses for its own internal calls.

```
dry_run result
     ↓
any unfilled assignments?
     ├── NO  → print results, exit normally
     └── YES → enter RepairEngine
                    ↓
               row-by-row iteration over unfilled dates/tasks
                    ↓
               for each unfilled slot:
                 (1) reconfigure — find new candidate from qualified pool
                 (2) validate — run existing constraint/matching rules
                 (3) accept if passes, skip if fails
                    ↓
               repeat up to MAX_REPAIR_ITERATIONS (configurable, default 3)
                    ↓
               print repair report (what was fixed, what remains unfilled)
```

---

## STEP 1 — DETECT UNFILLED ASSIGNMENTS

Read how dry_run currently represents unfilled slots (None, empty string, "UNFILLED", etc. — check the actual codebase). Build a detection function that:

- Collects all unfilled slots into a structured list: `[{date, task, group, week_cycle, reason_unfilled}]`
- Sorts them by date ascending so repair is attempted chronologically
- Logs count before repair begins: `"Repair loop initiated — {n} unfilled assignments found"`

---

## STEP 2 — RECONFIGURATION LOGIC (repair attempt per slot)

For each unfilled slot, attempt reassignment by:

1. **Pull the qualified staff pool** for that task using the existing roster matching logic (same rules as engine.py — do not duplicate, call the existing function)

2. **Filter out staff already assigned that day** (check existing daily assignment tracking in the schedule state)

3. **Apply soft-constraint preference ordering:**
   - Tier 1: staff with matching subspecialty tag (Breast-Proc, North_Gen+Cont, South_Gen+Cont per task)
   - Tier 2: staff with participates_gen / participates_MRI / participates_PET = yes
   - Tier 3: any remaining qualified staff
   - Try each tier in order, stop at first successful assignment

4. **Within each tier, prefer staff with the lowest current assignment count** for that dry_run group (fairness-aware selection — check how engine.py currently balances load and mirror that approach)

5. **Do not reassign staff who have an exemption day on that date** (check dry_run_state.json exemptions)

---

## STEP 3 — VALIDATION (constraint check before accepting)

After each candidate reassignment is generated, run it through the existing constraint validation pipeline before accepting. Do not re-implement constraint logic — call the existing validation function(s) from constraints.py.

A repair assignment is only accepted if it passes ALL hard constraints. Soft constraint failures are logged as warnings but do not block acceptance.

If validation fails, try the next candidate in the tier. If all candidates in all tiers are exhausted, mark the slot as `REPAIR_FAILED` and move to the next unfilled slot.

---

## STEP 4 — REPAIR REPORT OUTPUT

After the repair loop completes, print a structured summary before the normal dry_run output:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  REPAIR LOOP SUMMARY  (iteration {n} of max {MAX})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Unfilled before repair : {x}
  Successfully repaired  : {y}
  Still unfilled         : {z}

  REPAIRED:
  {date}  {task}  →  {staff_assigned}  [tier {1|2|3}]  [soft constraint warning if any]

  STILL UNFILLED:
  {date}  {task}  →  REPAIR_FAILED  Reason: {exhausted_all_candidates | exemption_block | hard_constraint_fail}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Also write this report to `dry_run_repair_log.json` in the same output directory as other dry_run artifacts. Append (do not overwrite) so multiple repair runs are preserved with timestamps.

---

## STEP 5 — ITERATION CONTROL

The repair loop runs up to `MAX_REPAIR_ITERATIONS` times (default 3, make it a config constant at the top of repair.py). Each iteration re-checks if unfilled slots remain from the previous pass and attempts repair again — some slots may become fillable after earlier slots in the same pass are resolved (staff freed up by reordering).

Exit the loop early if either:
- All slots are filled (success)
- An iteration produces zero new repairs (no progress — stop to avoid infinite loop)

---

## IMPLEMENTATION REQUIREMENTS

1. Read all existing files before writing a single line of code.
2. Do not duplicate any existing logic — call existing functions from engine.py, constraints.py, and dry_run.py.
3. repair.py must be importable standalone and also callable as a module from dry_run.py.
4. All new constants (MAX_REPAIR_ITERATIONS, log file name, etc.) go at the top of repair.py, clearly labeled.
5. Update dry_run.py to call the repair loop — this should be the only file outside repair.py that changes, unless you find a necessary dependency update.
6. After writing each file, state what changed and why.
7. If any existing function signatures, data structures, or state representations conflict with this design, pause and ask before proceeding.
8. Write a changelog at the end listing every file touched and the nature of each change.

---

## Design Notes

### Why `repair.py` as a separate module
Keeps repair logic isolated from dry_run's existing flow — easier to test independently and easier to remove or replace without touching the core scheduling pipeline.

### Why "call existing functions, don't duplicate"
Without this guard, agents commonly re-implement constraint logic with subtle differences that pass their own internal tests but diverge from the real rules in constraints.py. This is the most common failure mode.

### Why tier-based candidate selection
Gives the agent a deterministic priority order rather than letting it invent its own preference logic, which tends to be inconsistent with how the rest of the engine handles soft constraints.

### Why the zero-progress exit condition
Prevents the agent from writing an infinite loop that looks like it's working but never converges — if an iteration produces no new repairs, all remaining slots are structurally unfillable given current roster and constraints.
