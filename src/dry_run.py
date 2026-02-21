"""
dry_run.py — Safe Schedule Validation (No QGenda Push)

Full orchestration:
  1. Load roster, vacation map, cursor state
  2. Validate inputs (roster structure, IR pool size, shift coverage)
  3. Run block scheduling (IR → M3 → M0 → M1/M2 → weekend)
  4. Check constraints (hard + soft)
  5. Calculate fairness metrics
  6. Export CSV, Excel, fairness report, violations report
  7. Print summary to console

Usage:
  python -m src.dry_run --start 2026-03-01 --end 2026-05-31
  python -m src.dry_run --start 2026-03-01 --end 2026-05-31 --interactive
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    load_roster,
    load_vacation_map,
    load_cursor_state,
    save_cursor_state,
    filter_pool,
)
from src.engine import (
    schedule_blocks,
    calculate_fairness_metrics,
    get_weekday_dates,
    get_saturday_dates,
    get_weekend_dates,
)
from src.constraints import ConstraintChecker
from src.exporter import export_to_csv, export_to_excel, export_fairness_report
from src.skills import get_subspecialty_summary, validate_shift_coverage

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

OUTPUTS_DIR = PROJECT_ROOT / "outputs"


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_dry_run(
    start_date: date,
    end_date: date,
    output_dir: Path = OUTPUTS_DIR,
    interactive: bool = False,
    save_cursors: bool = False,
) -> Dict:
    """
    Generate full schedule in dry-run mode (never pushes to QGenda).

    Args:
        start_date:   First date to schedule
        end_date:     Last date to schedule
        output_dir:   Directory for output files
        interactive:  If True, prompt user before each block
        save_cursors: If True, persist updated cursor state to disk

    Returns:
        Dict with schedule, metrics, violations, output paths
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"dry_run_{start_date}_{end_date}"
    sep = "=" * 70

    print(f"\n{sep}")
    print(f"  DRY RUN MODE — No data pushed to QGenda")
    print(f"  Period: {start_date} → {end_date}")
    print(f"{sep}\n")

    # ── 1. Load configuration ──────────────────────────────────────────────
    print("Step 1/6: Loading configuration...")
    roster         = load_roster()
    vacation_map   = load_vacation_map()
    cursor_state   = load_cursor_state()
    print(f"  ✓ {len(roster)} radiologists | {len(vacation_map)} vacation dates | cursors: {cursor_state}")

    # ── 2. Validate inputs ─────────────────────────────────────────────────
    print("\nStep 2/6: Validating inputs...")
    from src.schedule_config import SHIFT_DEFINITIONS, FAIRNESS_TARGETS, ALL_CURSOR_KEYS

    checker = ConstraintChecker(
        roster=roster,
        vacation_map=vacation_map,
        shift_definitions=SHIFT_DEFINITIONS,
        fairness_targets=FAIRNESS_TARGETS,
    )
    roster_errors, roster_warnings = checker.validate_roster()
    coverage_warnings = validate_shift_coverage(roster)
    spec_summary = get_subspecialty_summary(roster)

    for err in roster_errors:
        print(f"  ✗ ROSTER ERROR: {err}")
    for w in roster_warnings + coverage_warnings:
        print(f"  ⚠ WARNING: {w}")

    if roster_errors:
        print("\n  ✗ Cannot proceed — fix roster errors above.")
        sys.exit(1)

    if not roster_errors and not roster_warnings:
        print("  ✓ Roster valid")

    print(f"  ✓ Subspecialty coverage: {len(spec_summary)} tags across roster")

    # ── 3. Build date lists ────────────────────────────────────────────────
    print("\nStep 3/6: Building date lists...")
    weekday_dates  = get_weekday_dates(start_date, end_date)
    saturday_dates = get_saturday_dates(start_date, end_date)
    weekend_dates  = get_weekend_dates(start_date, end_date)
    sat_strs       = [d.isoformat() for d in saturday_dates]
    print(f"  ✓ {len(weekday_dates)} weekdays | {len(saturday_dates)} weekends ({len(weekend_dates)} Sat+Sun days)")

    # ── 4. Block scheduling ────────────────────────────────────────────────
    print("\nStep 4/6: Running block scheduling...")
    print("  Block order: IR → Mercy → Gen → Remote → Site → O\'Toole → Weekend")

    full_schedule, cursor_state = schedule_blocks(
        roster=roster,
        dates=weekday_dates,
        cursor_state=cursor_state,
        vacation_map=vacation_map,
        interactive=interactive,
        weekend_dates=weekend_dates if weekend_dates else None,
    )

    total_assignments = sum(len(v) for v in full_schedule.values())
    print(f"  ✓ {total_assignments} total assignments across {len(full_schedule)} dates")

    if save_cursors:
        save_cursor_state(cursor_state)
        print(f"  ✓ Cursors saved: {cursor_state}")

    # ── 5. Constraint checking ─────────────────────────────────────────────
    print("\nStep 5/6: Checking constraints...")
    metrics = calculate_fairness_metrics(full_schedule, roster)

    hard_violations, soft_violations = checker.check_all(
        schedule=full_schedule,
        weekend_dates=sat_strs or None,
        metrics=metrics,
        pool_label="Full Schedule",
    )

    h_count = len(hard_violations)
    s_count = len(soft_violations)
    cv_pct  = metrics["cv"]
    status  = "✓" if h_count == 0 else "✗"
    cv_icon = "✓" if cv_pct < 10.0 else "✗"

    print(f"  {status} Hard violations: {h_count}")
    print(f"    Soft violations: {s_count}")
    print(f"  {cv_icon} Weighted CV: {cv_pct:.2f}% (target <10%)")

    # ── 6. Export ──────────────────────────────────────────────────────────
    print("\nStep 6/6: Exporting outputs...")

    csv_path        = output_dir / f"{prefix}_schedule.csv"
    xlsx_path       = output_dir / f"{prefix}_schedule.xlsx"
    report_path     = output_dir / f"{prefix}_fairness_report.txt"
    violations_path = output_dir / f"{prefix}_violations.txt"

    export_to_csv(full_schedule, csv_path, include_shift=True)
    export_to_excel(
        full_schedule, xlsx_path, pivot=True,
        shift_order=["IR-1", "IR-2", "M0", "M1", "M2", "M3",
                     "M0_WEEKEND", "EP", "LP", "Dx-CALL"]
    )
    export_fairness_report(
        metrics, report_path,
        pool_label="Full Rotation Schedule",
        target_cv=10.0,
        top_n=5, bottom_n=5,
    )

    # Violations report
    with open(violations_path, "w") as f:
        f.write("=== Constraint Violations ===\n\n")
        f.write(f"HARD ({h_count}):\n")
        for v in hard_violations:
            f.write(f"  {v}\n")
        f.write(f"\nSOFT ({s_count}):\n")
        for v in soft_violations:
            f.write(f"  {v}\n")

    print(f"  ✓ CSV:       {csv_path.name}")
    print(f"  ✓ Excel:     {xlsx_path.name}")
    print(f"  ✓ Report:    {report_path.name}")
    print(f"  ✓ Violations:{violations_path.name}")

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print("  SUMMARY")
    print(f"{sep}")
    print(f"  Period:            {start_date} → {end_date}")
    print(f"  Total assignments: {total_assignments}")
    print(f"  Unfilled slots:    {metrics['unfilled']}")
    print(f"  Weighted CV:       {cv_pct:.2f}%  {cv_icon}")
    print(f"  Hard violations:   {h_count}  {status}")
    print(f"  Soft violations:   {s_count}")

    wc = metrics["weighted_counts"]
    sorted_wc = sorted(wc.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  Top 3 assigned (weighted):")
    for name, val in sorted_wc[:3]:
        print(f"    {name:<24} {val:.2f}")
    print(f"\n  Bottom 3 assigned (weighted):")
    for name, val in sorted_wc[-3:][::-1]:
        print(f"    {name:<24} {val:.2f}")

    print(f"\n  Per-shift CV:")
    for shift, cv_val in sorted(metrics.get("per_shift_cv", {}).items()):
        icon = "✓" if cv_val < 10.0 else "✗"
        print(f"    {shift:<16} {cv_val:6.2f}%  {icon}")

    print(f"\n{sep}\n")

    return {
        "schedule":        full_schedule,
        "metrics":         metrics,
        "hard_violations": hard_violations,
        "soft_violations": soft_violations,
        "cursor_state":    cursor_state,
        "outputs": {
            "csv":        csv_path,
            "excel":      xlsx_path,
            "report":     report_path,
            "violations": violations_path,
        },
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Dry-run schedule generation (no QGenda push)"
    )
    parser.add_argument("--start",        required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end",          required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--output-dir",   default=None,  help="Output directory (default: outputs/)")
    parser.add_argument("--interactive",  action="store_true", help="Prompt before each block")
    parser.add_argument("--save-cursors", action="store_true", help="Persist cursor state after run")
    args = parser.parse_args()

    try:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end   = datetime.strptime(args.end,   "%Y-%m-%d").date()
    except ValueError as e:
        print(f"Invalid date format: {e}")
        sys.exit(1)

    if start > end:
        print("Error: start date must be before end date")
        sys.exit(1)

    out_dir = Path(args.output_dir) if args.output_dir else OUTPUTS_DIR
    run_dry_run(
        start, end,
        output_dir=out_dir,
        interactive=args.interactive,
        save_cursors=args.save_cursors,
    )


if __name__ == "__main__":
    main()
