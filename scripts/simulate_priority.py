"""
simulate_priority.py — Find the outpatient block priority ordering that
minimises unfilled slots.

Strategy:
  Blocks 1-5 (IR, Mercy inpatient) and 21-23 (weekend) are FIXED — their
  priority is dictated by hard constraints (IR before Mercy, weekend last).
  Only the *outpatient* blocks (priorities 6-20) are reshuffled.

  Because 15! permutations ≈ 1.3 trillion, we use a greedy local-search
  heuristic: start from the current order, try swapping each pair, keep the
  best, repeat until no improvement.  This converges quickly (< 100 evals
  on a 13-week schedule).

Usage:
  python3 scripts/simulate_priority.py --start 2026-03-01 --end 2026-05-31
"""

import argparse
import copy
import itertools
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_roster, load_vacation_map, load_cursor_state
from src.constraints import ConstraintChecker
from src.engine import (
    schedule_blocks,
    calculate_fairness_metrics,
    get_weekday_dates,
    get_weekend_dates,
)
from src.repair import run_repair_loop, collect_unfilled
from src.schedule_config import (
    SCHEDULING_BLOCKS,
    SHIFT_DEFINITIONS,
    FAIRNESS_TARGETS,
)

logging.basicConfig(level=logging.CRITICAL)
logger = logging.getLogger(__name__)

FIXED_PRIORITY_CUTOFF_LOW = 5    # priorities <= 5 are immutable (IR + Mercy)
FIXED_PRIORITY_CUTOFF_HIGH = 21  # priorities >= 21 are immutable (weekend)


def _run_one(
    blocks: List[Dict[str, Any]],
    roster: List[Dict[str, Any]],
    weekday_dates: List[date],
    weekend_dates: List[date],
    vacation_map: Dict[str, List[str]],
    nc_week_anchor: date,
    checker: ConstraintChecker,
    run_repair: bool = True,
) -> Tuple[int, int, float]:
    """Run scheduling + optional repair; return (unfilled, hard_violations, cv)."""
    cursor_state = load_cursor_state()
    schedule, _ = schedule_blocks(
        roster=roster,
        dates=weekday_dates,
        cursor_state=cursor_state,
        vacation_map=vacation_map,
        blocks=blocks,
        weekend_dates=weekend_dates or None,
        nc_week_anchor=nc_week_anchor,
    )
    metrics = calculate_fairness_metrics(schedule, roster)
    unfilled = metrics.get("unfilled", 0)

    if run_repair and unfilled > 0:
        sat_strs = [d.isoformat() for d in weekend_dates if d.weekday() == 5]
        run_repair_loop(
            schedule, roster, vacation_map, checker,
            weekend_dates=sat_strs or None,
            output_dir=Path("/dev/null").parent,
            prefix="sim",
        )
        metrics = calculate_fairness_metrics(schedule, roster)
        unfilled = metrics.get("unfilled", 0)

    hard, _ = checker.check_all(
        schedule,
        weekend_dates=[d.isoformat() for d in weekend_dates if d.weekday() == 5],
        metrics=metrics,
    )
    return unfilled, len(hard), metrics.get("cv", 0.0)


def _apply_priority_order(
    base_blocks: List[Dict[str, Any]],
    outpatient_order: List[int],
) -> List[Dict[str, Any]]:
    """
    Return a copy of base_blocks with outpatient blocks re-prioritised
    according to outpatient_order (list of original outpatient indices).
    """
    blocks = copy.deepcopy(base_blocks)
    outpatient_idxs = [
        i for i, b in enumerate(blocks)
        if FIXED_PRIORITY_CUTOFF_LOW < b["priority"] < FIXED_PRIORITY_CUTOFF_HIGH
    ]
    for new_rank, orig_idx in enumerate(outpatient_order):
        blocks[outpatient_idxs[orig_idx]]["priority"] = FIXED_PRIORITY_CUTOFF_LOW + 1 + new_rank
    return blocks


def main():
    parser = argparse.ArgumentParser(description="Simulate outpatient priority orderings")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end",   required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--nc-week-anchor", default="2026-03-02",
                        help="NC week anchor (default 2026-03-02)")
    parser.add_argument("--no-repair", action="store_true",
                        help="Skip repair loop (faster but less accurate)")
    parser.add_argument("--max-swaps", type=int, default=200,
                        help="Max swap evaluations per pass (default 200)")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end   = datetime.strptime(args.end,   "%Y-%m-%d").date()
    nc_anchor = datetime.strptime(args.nc_week_anchor, "%Y-%m-%d").date()

    roster       = load_roster()
    vacation_map = load_vacation_map()
    weekday_dates = get_weekday_dates(start, end)
    weekend_dates = get_weekend_dates(start, end)

    checker = ConstraintChecker(
        roster=roster,
        vacation_map=vacation_map,
        shift_definitions=SHIFT_DEFINITIONS,
        fairness_targets=FAIRNESS_TARGETS,
    )

    base_blocks = list(SCHEDULING_BLOCKS)
    outpatient_idxs = [
        i for i, b in enumerate(base_blocks)
        if FIXED_PRIORITY_CUTOFF_LOW < b["priority"] < FIXED_PRIORITY_CUTOFF_HIGH
    ]
    n_outpatient = len(outpatient_idxs)
    outpatient_labels = [base_blocks[i]["label"] for i in outpatient_idxs]

    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  PRIORITY SIMULATION")
    print(f"  Period: {start} → {end}")
    print(f"  Outpatient blocks to reorder: {n_outpatient}")
    print(f"  Repair: {'off' if args.no_repair else 'on'}")
    print(f"{sep}\n")

    print("Outpatient blocks (current order):")
    for i, label in enumerate(outpatient_labels):
        print(f"  [{i:2d}] {label}")

    # Baseline: current ordering
    current_order = list(range(n_outpatient))
    print("\n--- Baseline evaluation ---")
    t0 = time.time()
    best_unfilled, best_hard, best_cv = _run_one(
        base_blocks, roster, weekday_dates, weekend_dates,
        vacation_map, nc_anchor, checker,
        run_repair=not args.no_repair,
    )
    t_baseline = time.time() - t0
    print(f"  Unfilled: {best_unfilled}  |  Hard: {best_hard}  |  CV: {best_cv:.2f}%  ({t_baseline:.1f}s)")
    best_order = list(current_order)

    # Greedy local search: swap pairs
    print(f"\n--- Greedy swap search (max {args.max_swaps} evals) ---")
    improved = True
    total_evals = 0
    pass_num = 0

    while improved:
        improved = False
        pass_num += 1
        print(f"\n  Pass {pass_num}:")
        pairs = list(itertools.combinations(range(n_outpatient), 2))

        for i, j in pairs:
            if total_evals >= args.max_swaps:
                break
            candidate_order = list(best_order)
            candidate_order[i], candidate_order[j] = candidate_order[j], candidate_order[i]

            blocks = _apply_priority_order(base_blocks, candidate_order)
            t0 = time.time()
            unfilled, hard, cv = _run_one(
                blocks, roster, weekday_dates, weekend_dates,
                vacation_map, nc_anchor, checker,
                run_repair=not args.no_repair,
            )
            elapsed = time.time() - t0
            total_evals += 1

            marker = ""
            if unfilled < best_unfilled or (unfilled == best_unfilled and cv < best_cv):
                best_unfilled, best_hard, best_cv = unfilled, hard, cv
                best_order = list(candidate_order)
                improved = True
                marker = " *** NEW BEST ***"

            swap_labels = f"{outpatient_labels[best_order[i]]} <-> {outpatient_labels[best_order[j]]}"
            print(
                f"    [{total_evals:3d}] swap({i},{j}) "
                f"unfilled={unfilled:2d}  hard={hard}  cv={cv:5.2f}%  "
                f"({elapsed:.1f}s){marker}"
            )

        if total_evals >= args.max_swaps:
            print(f"\n  Reached max evaluations ({args.max_swaps})")
            break

    # Results
    print(f"\n{sep}")
    print(f"  SIMULATION RESULTS")
    print(sep)
    print(f"  Total evaluations: {total_evals}")
    print(f"  Best unfilled:     {best_unfilled}")
    print(f"  Best hard:         {best_hard}")
    print(f"  Best CV:           {best_cv:.2f}%")
    print(f"\n  Best outpatient priority order:")
    for rank, idx in enumerate(best_order):
        label = outpatient_labels[idx]
        current_rank = current_order.index(idx) if idx in current_order else -1
        moved = "" if rank == current_rank else f"  (was #{current_rank})"
        print(f"    Priority {FIXED_PRIORITY_CUTOFF_LOW + 1 + rank:2d}: {label}{moved}")
    print(f"\n{sep}\n")


if __name__ == "__main__":
    main()
