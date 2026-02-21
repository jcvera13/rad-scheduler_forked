"""
Export Layer for Fair Radiology Scheduling

- Excel export with formatted schedule grid (dates × radiologists)
- CSV export for programmatic review
- Fairness audit report (per-radiologist counts, weighted workload, CV)

See docs/implementation_guide.md
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Type alias for schedule format: date_str -> [(shift_name, person_name)]
ScheduleType = Dict[str, List[Tuple[str, str]]]


def export_to_csv(
    schedule: ScheduleType,
    output_path: Path,
    include_shift: bool = True,
) -> None:
    """
    Export schedule to CSV (date, shift, staff).

    Args:
        schedule: Dict[date_str, List[(shift_name, person_name)]]
        output_path: Output file path
        include_shift: If True, include shift column
    """
    import csv
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        if include_shift:
            writer = csv.DictWriter(f, fieldnames=["date", "shift", "staff"])
            writer.writeheader()
            for date_str, assignments in sorted(schedule.items()):
                for shift_name, person_name in assignments:
                    writer.writerow({"date": date_str, "shift": shift_name, "staff": person_name})
        else:
            writer = csv.DictWriter(f, fieldnames=["date", "staff"])
            writer.writeheader()
            for date_str, assignments in sorted(schedule.items()):
                for _shift, person_name in assignments:
                    writer.writerow({"date": date_str, "staff": person_name})


def export_to_excel(
    schedule: ScheduleType,
    output_path: Path,
    pivot: bool = True,
) -> None:
    """
    Export schedule to Excel with formatted grid.

    Args:
        schedule: Dict[date_str, List[(shift_name, person_name)]]
        output_path: Output .xlsx path
        pivot: If True, create date × shift grid with staff names
    """
    import pandas as pd
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for date_str, assignments in sorted(schedule.items()):
        for shift_name, person_name in assignments:
            rows.append({"date": date_str, "shift": shift_name, "staff": person_name})
    df = pd.DataFrame(rows)
    if pivot:
        grid = df.pivot_table(index="date", columns="shift", values="staff", aggfunc="first")
        grid.to_excel(output_path)
    else:
        df.to_excel(output_path, index=False)


def export_fairness_report(
    metrics: Dict[str, Any],
    output_path: Path,
    top_n: int = 3,
    bottom_n: int = 3,
) -> None:
    """
    Export fairness audit report (text format).

    Args:
        metrics: From engine.calculate_fairness_metrics
        output_path: Output .txt path
        top_n: Number of most-assigned to highlight
        bottom_n: Number of least-assigned to highlight
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wc = metrics.get("weighted_counts", metrics.get("counts", {}))
    sorted_names = sorted(wc.keys(), key=lambda n: wc.get(n, 0), reverse=True)
    mean_val = metrics.get("mean", 0)
    cv = metrics.get("cv", 0)
    with open(output_path, "w") as f:
        f.write("=== Fairness Audit Report ===\n\n")
        f.write(f"Mean (weighted): {mean_val:.2f}\n")
        f.write(f"Std Dev: {metrics.get('std', 0):.2f}\n")
        f.write(f"CV: {cv:.2f}% (target <10%)\n\n")
        f.write("Top assigned:\n")
        for name in sorted_names[:top_n]:
            val = wc.get(name, 0)
            pct = (val / mean_val * 100) if mean_val else 0
            f.write(f"  {name}: {val:.2f} ({pct:.1f}% of mean)\n")
        f.write("\nBottom assigned:\n")
        for name in sorted_names[-bottom_n:][::-1]:
            val = wc.get(name, 0)
            pct = (val / mean_val * 100) if mean_val else 0
            f.write(f"  {name}: {val:.2f} ({pct:.1f}% of mean)\n")
