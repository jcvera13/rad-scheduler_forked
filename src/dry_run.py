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
from typing import Any, Dict, List, Optional

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
# Visual analysis (matplotlib) — reference: scripts/analyze_schedule.py
# ---------------------------------------------------------------------------

def _generate_visual_analysis(
    schedule: Dict,
    metrics: Dict,
    roster: List,
    output_dir: Path,
    prefix: str,
) -> None:
    """Generate matplotlib charts for dry_run schedule (shift/hours distribution, deviation, task breakdown)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not installed — skip visual analysis. Install with: pip install matplotlib")
        return

    out = Path(output_dir)
    names = [p["name"] for p in roster]
    rc = metrics.get("counts", {})
    hc = metrics.get("hours_counts", {})
    mean_val = metrics.get("mean", 0)
    std_val = metrics.get("std", 0)
    hours_mean = metrics.get("hours_mean", 0)
    hours_std = metrics.get("hours_std", 0)
    cv_pct = metrics.get("cv", 0)
    hours_cv = metrics.get("hours_cv", 0)

    staff_sorted = sorted(names, key=lambda n: rc.get(n, 0), reverse=True)
    shifts = [rc.get(n, 0) for n in staff_sorted]
    hours = [hc.get(n, 0) for n in staff_sorted]
    x = range(len(staff_sorted))

    # Chart 1: Shift distribution
    fig, ax = plt.subplots(figsize=(13, 5))
    colors = ["#b22222" if s > mean_val + std_val else "#1a3d7c" if s < mean_val - std_val else "#4a90d9" for s in shifts]
    ax.bar(x, shifts, color=colors, alpha=0.85, width=0.65)
    ax.axhline(mean_val, color="crimson", linewidth=1.8, linestyle="--", label=f"Mean: {mean_val:.1f}")
    ax.axhline(mean_val + std_val, color="orange", linewidth=1, linestyle=":")
    ax.axhline(mean_val - std_val, color="orange", linewidth=1, linestyle=":")
    for bar, val in zip(ax.patches, shifts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.4, str(val), ha="center", va="bottom", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(staff_sorted, rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("Shift Count")
    ax.set_title(f"Shift Distribution by Staff (dry_run)\nCV = {cv_pct:.1f}%", fontsize=13, fontweight="bold")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / f"{prefix}_shift_distribution.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ Visual  → {prefix}_shift_distribution.png")

    # Chart 2: Hours distribution
    fig, ax = plt.subplots(figsize=(13, 5))
    hcolors = ["#b22222" if h > hours_mean + hours_std else "#1a3d7c" if h < hours_mean - hours_std else "#2e8b57" for h in hours]
    ax.bar(x, hours, color=hcolors, alpha=0.85, width=0.65)
    ax.axhline(hours_mean, color="crimson", linewidth=1.8, linestyle="--", label=f"Mean: {hours_mean:.1f} hrs")
    ax.axhline(hours_mean + hours_std, color="orange", linewidth=1, linestyle=":")
    ax.axhline(hours_mean - hours_std, color="orange", linewidth=1, linestyle=":")
    for bar, val in zip(ax.patches, hours):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, f"{val:.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(staff_sorted, rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("Total Hours Assigned")
    ax.set_title(f"Hours-Assigned Distribution by Staff (dry_run)\nCV = {hours_cv:.1f}%", fontsize=13, fontweight="bold")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / f"{prefix}_hours_distribution.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ Visual  → {prefix}_hours_distribution.png")

    # Chart 3: Shift deviation from mean
    deviations = [s - mean_val for s in shifts]
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.bar(x, deviations, color=["#b22222" if d >= 0 else "#1a3d7c" for d in deviations], alpha=0.8, width=0.65)
    ax.axhline(0, color="black", linewidth=1)
    ax.axhline(std_val, color="orange", linewidth=1, linestyle="--", label="±1 SD")
    ax.axhline(-std_val, color="orange", linewidth=1, linestyle="--")
    ax.set_xticks(list(x))
    ax.set_xticklabels(staff_sorted, rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("Deviation from Mean Shifts")
    ax.set_title("Shift Deviation from Mean (dry_run)", fontsize=13, fontweight="bold")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / f"{prefix}_shift_deviation.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ Visual  → {prefix}_shift_deviation.png")

    # Chart 4: Task breakdown (top 15 shifts by assignment count)
    shift_counts: Dict[str, int] = {}
    for _date, assignments in schedule.items():
        for shift_name, person_name in assignments:
            if person_name == "UNFILLED":
                continue
            shift_counts[shift_name] = shift_counts.get(shift_name, 0) + 1
    sorted_shifts = sorted(shift_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    if sorted_shifts:
        fig, ax = plt.subplots(figsize=(10, 6))
        labels = [s[0] for s in reversed(sorted_shifts)]
        vals = [s[1] for s in reversed(sorted_shifts)]
        ax.barh(labels, vals, color="#4a90d9", alpha=0.85)
        for bar, val in zip(ax.patches, vals):
            ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2, str(val), va="center", fontsize=9)
        ax.set_xlabel("Assignment Count")
        ax.set_title("Top 15 Task Types (dry_run)", fontsize=13, fontweight="bold")
        ax.grid(axis="x", alpha=0.3)
        fig.tight_layout()
        fig.savefig(out / f"{prefix}_task_breakdown.png", dpi=150)
        plt.close(fig)
        print(f"  ✓ Visual  → {prefix}_task_breakdown.png")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_dry_run(
    start_date: date,
    end_date: date,
    output_dir: Path = OUTPUTS_DIR,
    interactive: bool = False,
    save_cursors: bool = False,
    visual: bool = False,
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
    output_dir = Path(output_dir)
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

    # ── 4b. Repair loop (if any unfilled) ───────────────────────────────────
    metrics = calculate_fairness_metrics(full_schedule, roster)
    if metrics.get("unfilled", 0) > 0:
        from src.repair import run_repair_loop
        run_repair_loop(
            full_schedule,
            roster,
            vacation_map,
            checker,
            weekend_dates=sat_strs or None,
            output_dir=output_dir,
            prefix=prefix,
        )
        metrics = calculate_fairness_metrics(full_schedule, roster)

    # ── 5. Constraint checking ─────────────────────────────────────────────
    print("\nStep 5/6: Checking constraints...")

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
    hours_cv = metrics.get("hours_cv", 0)
    hcv_icon = "✓" if hours_cv < 10.0 else "✗"
    print(f"  {hcv_icon} Hours-assigned CV: {hours_cv:.2f}% (target <10%)")

    # ── 6. Export ──────────────────────────────────────────────────────────
    print("\nStep 6/6: Exporting outputs...")

    csv_path        = output_dir / f"{prefix}_schedule.csv"
    xlsx_path       = output_dir / f"{prefix}_schedule.xlsx"
    report_path     = output_dir / f"{prefix}_fairness_report.txt"
    violations_path = output_dir / f"{prefix}_violations.txt"

    export_to_csv(full_schedule, csv_path, include_shift=True)
    name_to_initials = {p["name"]: p["initials"] for p in roster}
    export_to_excel(
        full_schedule, xlsx_path, pivot=True,
        shift_order=["IR-1", "IR-2", "M0", "M1", "M2", "M3",
                     "M0_WEEKEND", "EP", "LP", "Dx-CALL"],
        name_to_initials=name_to_initials,
    )
    export_fairness_report(
        metrics, report_path,
        pool_label="Full Rotation Schedule",
        target_cv=10.0,
        top_n=5, bottom_n=5,
    )

    # Fairness JSON (hours-assigned CV for programmatic fairness/balance checks)
    import json
    fairness_data_path = output_dir / f"{prefix}_fairness_data.json"
    with open(fairness_data_path, "w") as f:
        json.dump({
            "weighted_cv": metrics.get("cv", 0),
            "hours_mean": metrics.get("hours_mean", 0),
            "hours_std": metrics.get("hours_std", 0),
            "hours_cv": metrics.get("hours_cv", 0),
            "hours_counts": {k: round(v, 1) for k, v in (metrics.get("hours_counts") or {}).items()},
            "unfilled": metrics.get("unfilled", 0),
        }, f, indent=2)
    print(f"  ✓ Fairness JSON: {fairness_data_path.name} (includes hours-assigned CV)")

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
    print(f"  Hours-assigned CV: {hours_cv:.2f}%  {hcv_icon}")
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

    if visual:
        _generate_visual_analysis(full_schedule, metrics, roster, output_dir, prefix)

    print(f"\n{sep}\n")

    result = {
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
    return result


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
    parser.add_argument(
        "--visual",
        action="store_true",
        help="Generate matplotlib charts (shift/hours distribution, deviation, task breakdown). Reference: scripts/analyze_schedule.py",
    )
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
        visual=args.visual,
    )


if __name__ == "__main__":
    main()
