"""
Dry Run Mode - Safe Schedule Validation

Run full schedule generation WITHOUT pushing to QGenda.
Output to outputs/ directory. NEVER push unless --live flag explicitly set.

Outputs:
- Proposed schedule (Excel, CSV)
- Fairness report (counts, CV%, top/bottom 3)
- Constraint violation report
- Optional: comparison vs historical actuals from qgenda_cleaned.csv

Usage:
  python -m src.dry_run --start 2026-03-01 --end 2026-06-30
  python -m src.dry_run --start 2026-03-01 --end 2026-06-30 --live  # Still dry-run; --live reserved for future
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict

# Ensure we can import from src
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    load_roster,
    load_vacation_map,
    load_cursor_state,
    filter_pool,
    INPATIENT_WEEKDAY_CONFIG,
    INPATIENT_WEEKEND_CONFIG,
)
from src.engine import (
    schedule_weekday_mercy,
    schedule_weekend_mercy,
    calculate_fairness_metrics,
)
from src.exporter import export_to_csv, export_to_excel, export_fairness_report
from src.constraints import ConstraintChecker, ConstraintSeverity

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def get_weekday_dates(start: date, end: date):
    """Monday-Friday in range"""
    dates = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)
    return dates


def get_weekend_saturday_dates(start: date, end: date):
    """Saturdays in range (each represents full weekend)"""
    dates = []
    d = start
    while d <= end:
        if d.weekday() == 5:  # Saturday
            dates.append(d)
        d += timedelta(days=1)
    return dates


def run_dry_run(
    start_date: date,
    end_date: date,
    output_dir: Path = OUTPUTS_DIR,
) -> Dict:
    """
    Generate schedule in dry-run mode. No QGenda push.

    Returns dict with schedule, metrics, violations, output paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"dry_run_{start_date.isoformat()}_{end_date.isoformat()}_{ts}"

    # Load config
    roster = load_roster()
    vacation_map = load_vacation_map()
    cursors = load_cursor_state()

    mercy_pool = filter_pool(roster, INPATIENT_WEEKDAY_CONFIG["pool_filter"])
    weekend_pool = filter_pool(roster, INPATIENT_WEEKEND_CONFIG.get("pool_filter", "participates_weekend"))
    if not weekend_pool:
        weekend_pool = mercy_pool  # Fallback

    # Schedule weekday Mercy
    weekday_dates = get_weekday_dates(start_date, end_date)
    wd_schedule, wd_cursor = schedule_weekday_mercy(
        people=mercy_pool,
        dates=weekday_dates,
        cursor=cursors.get("weekday_cursor", 0),
        vacation_map=vacation_map,
    )

    # Schedule weekend Mercy
    sat_dates = get_weekend_saturday_dates(start_date, end_date)
    we_schedule, we_cursor = schedule_weekend_mercy(
        people=weekend_pool,
        saturday_dates=sat_dates,
        cursor=cursors.get("weekend_cursor", 0),
        vacation_map=vacation_map,
    )

    # Merge schedules for reporting
    all_schedule = dict(wd_schedule)
    all_schedule.update(we_schedule)

    # Fairness metrics (combine both)
    combined_assignments = {}
    for dt, assignments in all_schedule.items():
        combined_assignments[dt] = assignments
    metrics = calculate_fairness_metrics(combined_assignments, roster)

    # Constraint check
    checker = ConstraintChecker(roster, vacation_map)
    weekend_date_strs = [d.strftime("%Y-%m-%d") for d in sat_dates]
    hard_violations, soft_violations = checker.check_all(all_schedule, weekend_date_strs)

    # Export
    csv_path = output_dir / f"{prefix}_schedule.csv"
    xlsx_path = output_dir / f"{prefix}_schedule.xlsx"
    report_path = output_dir / f"{prefix}_fairness_report.txt"
    violations_path = output_dir / f"{prefix}_violations.txt"

    export_to_csv(all_schedule, csv_path, include_shift=True)
    export_to_excel(all_schedule, xlsx_path, pivot=True)
    export_fairness_report(metrics, report_path, top_n=3, bottom_n=3)

    with open(violations_path, "w") as f:
        f.write("=== Constraint Violations ===\n\n")
        f.write(f"Hard: {len(hard_violations)}\n")
        for v in hard_violations:
            f.write(f"  - {v.description}\n")
        f.write(f"\nSoft: {len(soft_violations)}\n")
        for v in soft_violations:
            f.write(f"  - {v.description}\n")

    # Print summary
    total_assignments = sum(len(a) for a in all_schedule.values())
    sorted_counts = sorted(
        metrics.get("weighted_counts", metrics.get("counts", {})).items(),
        key=lambda x: x[1],
        reverse=True,
    )
    top3 = sorted_counts[:3]
    bottom3 = sorted_counts[-3:][::-1]

    print("\n" + "=" * 60)
    print("DRY RUN SUMMARY (no data pushed to QGenda)")
    print("=" * 60)
    print(f"Date range: {start_date} to {end_date}")
    print(f"Total assignments: {total_assignments}")
    print(f"CV%: {metrics.get('cv', 0):.2f}% (target <10%)")
    print(f"\nTop 3 assigned:")
    for name, count in top3:
        print(f"  {name}: {count:.2f}" if isinstance(count, float) else f"  {name}: {count}")
    print(f"\nBottom 3 assigned:")
    for name, count in bottom3:
        print(f"  {name}: {count:.2f}" if isinstance(count, float) else f"  {name}: {count}")
    print(f"\nConstraint violations: {len(hard_violations)} hard, {len(soft_violations)} soft")
    print(f"\nOutputs written to: {output_dir}")
    print(f"  - {csv_path.name}")
    print(f"  - {xlsx_path.name}")
    print(f"  - {report_path.name}")
    print(f"  - {violations_path.name}")
    print("=" * 60 + "\n")

    return {
        "schedule": all_schedule,
        "metrics": metrics,
        "hard_violations": hard_violations,
        "soft_violations": soft_violations,
        "outputs": {
            "csv": csv_path,
            "excel": xlsx_path,
            "report": report_path,
            "violations": violations_path,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Dry run schedule generation (no QGenda push)")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: outputs/)")
    parser.add_argument("--live", action="store_true", help="Reserved for future: push to QGenda (currently no-op)")
    args = parser.parse_args()

    try:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end = datetime.strptime(args.end, "%Y-%m-%d").date()
    except ValueError as e:
        print(f"Invalid date format: {e}")
        sys.exit(1)

    if start > end:
        print("Start date must be before end date")
        sys.exit(1)

    out_dir = Path(args.output_dir) if args.output_dir else OUTPUTS_DIR
    run_dry_run(start, end, output_dir=out_dir)
    if args.live:
        print("Note: --live is reserved for future QGenda push. No push performed in dry-run mode.")


if __name__ == "__main__":
    main()
