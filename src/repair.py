"""
repair.py — Automated repair loop for unfilled dry_run assignments.

When a dry_run completes with unfilled slots, this module attempts to fill them
by reusing the same pool and constraint logic as the engine, then validating
each candidate with ConstraintChecker.check_all. No duplicate logic — calls
engine.filter_pool_for_block and constraints.check_all.
"""

import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (configurable at top of module)
# ---------------------------------------------------------------------------
MAX_REPAIR_ITERATIONS = 3
REPAIR_LOG_FILENAME = "dry_run_repair_log.json"
REASON_POOL_EXHAUSTED = "pool_exhausted"
REASON_EXHAUSTED_ALL_CANDIDATES = "exhausted_all_candidates"
REASON_EXEMPTION_BLOCK = "exemption_block"
REASON_HARD_CONSTRAINT_FAIL = "hard_constraint_fail"

# Preferred subspecialty tag per shift for tier ordering (Tier 1 = has this tag)
PREFERRED_TAG_BY_SHIFT: Dict[str, str] = {
    "Enc-Gen": "North_Gen+Cont",
    "Poway-Gen": "North_Gen+Cont",
    "NC-Gen": "South_Gen+Cont",
    "Wash-Breast": "Breast-Proc",
    "Enc-Breast": "Breast-Proc",
    "O'Toole": "Breast-Proc",
}


def _shift_to_block() -> Dict[str, Dict[str, Any]]:
    """Build shift_name -> block dict (first block that contains the shift wins)."""
    from src.schedule_config import SCHEDULING_BLOCKS

    out: Dict[str, Dict[str, Any]] = {}
    for block in SCHEDULING_BLOCKS:
        config = block.get("config", {})
        for shift in config.get("shift_names", []):
            if shift not in out:
                out[shift] = block
    return out


def collect_unfilled(schedule: Dict[str, List[Tuple[str, str]]]) -> List[Dict[str, Any]]:
    """
    Collect all unfilled slots into a structured list, sorted by date ascending.

    Returns list of dicts: { "date", "task", "group", "reason_unfilled" }.
    """
    shift_to_block = _shift_to_block()
    unfilled: List[Dict[str, Any]] = []

    for date_str, assignments in schedule.items():
        for shift_name, person_name in assignments:
            if person_name != "UNFILLED":
                continue
            block = shift_to_block.get(shift_name)
            unfilled.append({
                "date": date_str,
                "task": shift_name,
                "group": block["block_id"] if block else None,
                "reason_unfilled": REASON_POOL_EXHAUSTED,
            })

    unfilled.sort(key=lambda x: x["date"])
    if unfilled:
        logger.info(f"Repair loop initiated — {len(unfilled)} unfilled assignments found")
    return unfilled


def get_pool_for_shift(
    roster: List[Dict[str, Any]],
    shift_name: str,
    schedule: Dict[str, List[Tuple[str, str]]],
    date_str: str,
    vacation_map: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    """
    Return eligible staff for this (shift, date): block pool minus already-assigned
    and vacation/exemption on that date.
    """
    from src.engine import filter_pool_for_block

    shift_to_block = _shift_to_block()
    block = shift_to_block.get(shift_name)
    if not block:
        return []

    pool = filter_pool_for_block(roster, block)

    assigned_that_day = {
        name for _shift, name in schedule.get(date_str, [])
        if name != "UNFILLED"
    }
    unavailable = set(vacation_map.get(date_str, []))
    exclude = assigned_that_day | unavailable
    return [p for p in pool if p["name"] not in exclude]


def _assignment_counts(schedule: Dict[str, List[Tuple[str, str]]]) -> Dict[str, int]:
    """Count how many assignments each person has in the schedule."""
    counts: Dict[str, int] = {}
    for _date_str, assignments in schedule.items():
        for _shift, person_name in assignments:
            if person_name == "UNFILLED":
                continue
            counts[person_name] = counts.get(person_name, 0) + 1
    return counts


def tier_order_candidates(
    pool: List[Dict[str, Any]],
    shift_name: str,
    schedule: Dict[str, List[Tuple[str, str]]],
) -> List[Dict[str, Any]]:
    """
    Order candidates: Tier 1 = preferred tag for this shift, Tier 2 = participates_*,
    Tier 3 = rest. Within each tier, sort by lowest assignment count (fairness).
    """
    counts = _assignment_counts(schedule)
    preferred_tag = PREFERRED_TAG_BY_SHIFT.get(shift_name)
    shift_lower = shift_name.lower()

    def tier_key(p: Dict[str, Any]) -> Tuple[int, int]:
        tier = 3
        specs = [s.lower() for s in p.get("subspecialties", [])]
        if preferred_tag and preferred_tag.lower() in specs:
            tier = 1
        elif shift_lower and (
            "gen" in shift_lower and p.get("participates_gen", False)
            or "mri" in shift_lower and p.get("participates_MRI", False)
            or "pet" in shift_lower and p.get("participates_PET", False)
        ):
            tier = 2
        return (tier, counts.get(p["name"], 0))

    return sorted(pool, key=tier_key)


def try_repair_slot(
    schedule: Dict[str, List[Tuple[str, str]]],
    slot: Dict[str, Any],
    candidate_name: str,
    checker: Any,
    weekend_dates: Optional[List[str]] = None,
) -> bool:
    """
    Try assigning candidate to this slot. Clone schedule, replace first UNFILLED
    for (slot["date"], slot["task"]) with candidate, run check_all. Return True
    if no hard violations (accept); else False.
    """
    schedule_copy = copy.deepcopy(schedule)
    date_str = slot["date"]
    task = slot["task"]
    assignments = schedule_copy.get(date_str, [])
    for i, (s, name) in enumerate(assignments):
        if s == task and name == "UNFILLED":
            assignments[i] = (task, candidate_name)
            break
    else:
        return False

    hard, _soft = checker.check_all(schedule_copy, weekend_dates=weekend_dates)
    return len(hard) == 0


def _apply_repair(
    schedule: Dict[str, List[Tuple[str, str]]],
    slot: Dict[str, Any],
    candidate_name: str,
) -> None:
    """Mutate schedule: replace first UNFILLED for (slot["date"], slot["task"]) with candidate."""
    date_str = slot["date"]
    task = slot["task"]
    assignments = schedule.get(date_str, [])
    for i, (s, name) in enumerate(assignments):
        if s == task and name == "UNFILLED":
            assignments[i] = (task, candidate_name)
            return


def run_repair_loop(
    schedule: Dict[str, List[Tuple[str, str]]],
    roster: List[Dict[str, Any]],
    vacation_map: Dict[str, List[str]],
    checker: Any,
    weekend_dates: Optional[List[str]] = None,
    output_dir: Optional[Path] = None,
    prefix: str = "",
) -> Dict[str, Any]:
    """
    Run up to MAX_REPAIR_ITERATIONS passes over unfilled slots; for each slot try
    tier-ordered candidates and accept first that passes check_all. Mutates
    schedule in place. Prints summary and appends to dry_run_repair_log.json.

    Returns: { "unfilled_before", "repaired_count", "repaired", "still_unfilled" }.
    """
    from datetime import datetime, timezone

    output_dir = Path(output_dir) if output_dir else Path(".")
    unfilled_before = len(collect_unfilled(schedule))
    repaired: List[Dict[str, Any]] = []
    still_unfilled: List[Dict[str, Any]] = []
    iteration_used = 0

    for iteration in range(MAX_REPAIR_ITERATIONS):
        unfilled_list = collect_unfilled(schedule)
        if not unfilled_list:
            break
        iteration_used = iteration + 1
        repaired_this_pass = 0

        for slot in unfilled_list:
            pool = get_pool_for_shift(roster, slot["task"], schedule, slot["date"], vacation_map)
            candidates = tier_order_candidates(pool, slot["task"], schedule)
            assigned = False
            preferred_tag = PREFERRED_TAG_BY_SHIFT.get(slot["task"])
            for person in candidates:
                specs_lower = [s.lower() for s in person.get("subspecialties", [])]
                if preferred_tag and preferred_tag.lower() in specs_lower:
                    tier = 1
                elif person.get("participates_gen") or person.get("participates_MRI") or person.get("participates_PET"):
                    tier = 2
                else:
                    tier = 3
                if try_repair_slot(schedule, slot, person["name"], checker, weekend_dates):
                    _apply_repair(schedule, slot, person["name"])
                    repaired.append({
                        "date": slot["date"],
                        "task": slot["task"],
                        "staff": person["name"],
                        "tier": tier,
                    })
                    repaired_this_pass += 1
                    assigned = True
                    break

        if repaired_this_pass == 0:
            break

    still_list = collect_unfilled(schedule)
    still_unfilled = [{"date": s["date"], "task": s["task"], "reason": REASON_EXHAUSTED_ALL_CANDIDATES} for s in still_list]
    repaired_count = len(repaired)
    still_count = len(still_list)

    # Report
    sep = "━" * 38
    print(f"\n{sep}")
    print(f"  REPAIR LOOP SUMMARY  (iteration {iteration_used} of max {MAX_REPAIR_ITERATIONS})")
    print(sep)
    print(f"  Unfilled before repair : {unfilled_before}")
    print(f"  Successfully repaired  : {repaired_count}")
    print(f"  Still unfilled         : {still_count}")
    print()
    if repaired:
        print("  REPAIRED:")
        for r in repaired:
            print(f"  {r['date']}  {r['task']}  →  {r['staff']}  [tier {r['tier']}]")
    if still_unfilled:
        print("  STILL UNFILLED:")
        for s in still_unfilled:
            print(f"  {s['date']}  {s['task']}  →  REPAIR_FAILED  Reason: {s.get('reason', REASON_EXHAUSTED_ALL_CANDIDATES)}")
    print(sep + "\n")

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "prefix": prefix,
        "unfilled_before": unfilled_before,
        "repaired_count": repaired_count,
        "still_unfilled_count": still_count,
        "repaired": repaired,
        "still_unfilled": still_unfilled,
    }
    log_path = output_dir / REPAIR_LOG_FILENAME
    try:
        existing: List[Dict[str, Any]] = []
        if log_path.exists():
            with open(log_path) as f:
                data = json.load(f)
                existing = data if isinstance(data, list) else [data]
        existing.append(log_entry)
        with open(log_path, "w") as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not write repair log: {e}")

    return {
        "unfilled_before": unfilled_before,
        "repaired_count": repaired_count,
        "still_unfilled_count": still_count,
        "repaired": repaired,
        "still_unfilled": still_unfilled,
    }
