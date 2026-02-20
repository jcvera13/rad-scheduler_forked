#!/usr/bin/env python3
"""
Fair Radiology Scheduling Analyzer
Analyzes QGenda schedule exports for workload fairness.

Supports:
  - QGenda "List by Assignment Tag" Excel export  (auto-detected)
  - QGenda "List by Staff Export" Excel (SHIPMG / Imaging Healthcare; auto-detected)
  - Generic CSV/Excel with Date + Staff columns
  - Staff-as-columns CSV/Excel format

Usage:
    python analyze_schedule.py schedule_export.xlsx
    python analyze_schedule.py schedule_export.xlsx --pool combined   # all staff (default)
    python analyze_schedule.py schedule_export.xlsx --pool diagnostic  # DR group only
    python analyze_schedule.py schedule_export.xlsx --pool ir          # IR group only
    python analyze_schedule.py schedule_export.xlsx --start-date 2026-01-01 --end-date 2026-03-31
    python analyze_schedule.py schedule_export.xlsx --output-dir reports/ --exclude-tasks VACATION "OFF ALL DAY"

Requirements:
    pip install pandas openpyxl matplotlib
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.ticker as mticker
    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False
    print("⚠  matplotlib not installed — charts will be skipped.")
    print("   Install with:  pip install matplotlib\n")


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT EXCLUDED TASKS  (case-insensitive substring match)
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_EXCLUDE_PATTERNS = [
    "vacation",
    "off all day",
    "pres/vp vacation",
    "no call",          # administrative placeholder, not a real shift
]

# Tasks with HA = 0 are sometimes administrative placeholders; set True to
# also exclude them from the shift-count analysis.
EXCLUDE_ZERO_HOUR_TASKS = False

# ─────────────────────────────────────────────────────────────────────────────
# SUBSPECIALTY TASKS
# These tasks are separated from the general rotation analysis and get their
# own dedicated charts.  Add or remove entries as needed (case-insensitive
# exact-match against the full task name).
# ─────────────────────────────────────────────────────────────────────────────
SUBSPECIALTY_TASKS = [
    "Skull Base",
    "Cardiac Imaging",
    "NM Brain",
    # IR (Interventional Radiology) – from QGenda List by Staff Export
    "Mercy Hospital IR-1",
    "Mercy Hospital IR-2",
    "PVH IR",
    "IR-CALL (RMG)",
]

# Tasks excluded from rotation for diagnostic-pool shift/hour charts (subspecialty + IHS weekend).
# These are omitted from main fairness distributions; subspecialty and IHS weekend get separate charts.
IHS_WEEKEND_TASKS = [
    "Weekend IHS MRI",
    "Weekend IHS PET",
]

# Only these tasks count toward main shift and hours distributions (rotation charts).
# Subspecialty rotations, IHS Weekend MRI/PET are excluded from these charts.
MAIN_SHIFT_TASKS = [
    "Mercy 1  (on site) 0800-1600 (M1 (on site) 0800-1600)",
    "Mercy 2 (remote) 0930-1730 (M2 (remote) 0930-1730)",
    "Mercy 3 (remote) 1600-2200 (M3 (remote) 1600-2200)",
    "IHS Remote MRI (Remote MRI)",
    "Mercy 0 (M0 (remote) 0700-0800, 1130-1230)",
    "IHS Remote Breast & US (Remote Breast)",
    "IHS Washington MRI x1080 (Wash MRI 0800-1700)",
    "IHS Poway PET x1680 (Poway PET 0800-1700)",
    "IHS Encinitas Breast & US x1581 (Enc Breast 0800-1700)",
    "Scripps O'Toole Breast Center (O'Toole 0730-1630)",
    "Mercy 0 Weekend (M0 Weekend)",
    "Early Person Call (on site Sat/remote Sun) (EP 0800-1430)",
    "Late Person Call (remote) (Dx-CALL1400-2200)",
]


# Path to HA config for filling missing hours (scripts/cleaner/schedule_ha_config.json)
_SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_HA_CONFIG_PATH = _SCRIPT_DIR / "cleaner" / "schedule_ha_config.json"


def fill_missing_ha_from_config(
    df: pd.DataFrame,
    config_path: Path,
    source_path: Path,
    output_dir: Path,
) -> Tuple[pd.DataFrame, int]:
    """
    Fill missing or zero HA using task_ha_map from schedule_ha_config.json.
    Returns (df, n_filled). If n_filled > 0, saves a cleaned file to output_dir.
    """
    if not config_path.exists():
        return df, 0
    try:
        with open(config_path) as f:
            data = json.load(f)
    except Exception:
        return df, 0
    task_ha_map = data.get("task_ha_map") or {}
    if not task_ha_map:
        return df, 0

    # Normalize keys (strip, lower) for case-insensitive matching
    task_ha = {str(k).strip().lower(): (str(k).strip(), float(v)) for k, v in task_ha_map.items()}
    df = df.copy()
    task_stripped = df["Task"].astype(str).str.strip()
    task_lower = task_stripped.str.lower()
    ha_vals = pd.to_numeric(df["HA"], errors="coerce").fillna(0)
    n_filled = 0
    tasks_filled = set()

    for task_norm, (task_orig, ha_val) in task_ha.items():
        if ha_val <= 0:
            continue
        mask = (task_lower == task_norm) & (ha_vals <= 0)
        if mask.any():
            count = mask.sum()
            n_filled += int(count)
            tasks_filled.add(task_orig)
            df.loc[mask, "HA"] = ha_val

    if n_filled > 0 and output_dir is not None and source_path is not None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = source_path.stem
        suffix = source_path.suffix.lower() if source_path.suffix else ".xlsx"
        if suffix not in (".xlsx", ".xls"):
            suffix = ".xlsx"
        cleaned_name = f"{stem}_cleaned_{timestamp}{suffix}"
        cleaned_path = output_dir / cleaned_name
        try:
            df.to_excel(cleaned_path, index=False) if suffix in (".xlsx", ".xls") else df.to_csv(cleaned_path, index=False)
        except Exception:
            df.to_csv(output_dir / f"{stem}_cleaned_{timestamp}.csv", index=False)
            cleaned_path = output_dir / f"{stem}_cleaned_{timestamp}.csv"
        print(f"  HA filled          : {n_filled} rows using {config_path.name}")
        print(f"  Cleaned file saved : {cleaned_path.name}")
        for t in sorted(tasks_filled):
            print(f"    • {t}")

    return df, n_filled


# ─────────────────────────────────────────────────────────────────────────────
# FORMAT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_format(path: Path) -> str:
    """
    Detect which export format the file uses.

    Returns one of:
      'qgenda_tag_list'   – QGenda "List by Assignment Tag" Excel export
      'qgenda_staff_list' – QGenda "List by Staff Export" Excel (Date, Last/First Name, Task Name, HA)
      'generic_columns'  – Date column + Staff column (one row per assignment)
      'staff_as_columns' – Date column with staff names as column headers
    """
    if path.suffix.lower() not in (".xlsx", ".xls"):
        return "generic_columns"

    try:
        probe = pd.read_excel(path, header=None, nrows=6)
        cell_00 = str(probe.iloc[0, 0])
        if "List by Assignment Tag" in cell_00:
            return "qgenda_tag_list"
        if "List by Staff Export" in cell_00:
            return "qgenda_staff_list"
    except Exception:
        pass

    return "generic_columns"


# ─────────────────────────────────────────────────────────────────────────────
# LOADERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_staff_name(raw: str) -> str:
    """
    Convert QGenda's 'Last, First (Last, Ini)' to 'First Last'.
    Falls back to the raw string if the pattern doesn't match.
    """
    m = re.match(r"^([^,(]+),\s*([^(]+)", str(raw).strip())
    if m:
        last  = m.group(1).strip()
        first = m.group(2).strip()
        return f"{first} {last}"
    return str(raw).strip()


def load_qgenda_tag_list(
    path: Path,
    exclude_patterns: List[str],
) -> pd.DataFrame:
    """
    Load a QGenda 'List by Assignment Tag' Excel export.

    Structure:
      Row 0  – report title
      Row 1  – generation timestamp
      Row 2  – blank
      Row 3  – section tag label (e.g. "Untagged")
      Row 4  – column headers: Date | Day | Staff | Task | HA | HT | Status
      Row 5+ – data rows  (ends with a 'Totals' footer row)
    """
    print(f"  Detected format: QGenda 'List by Assignment Tag'")

    df_raw = pd.read_excel(path, header=None)

    # Locate the header row (first row where col-0 == "Date")
    header_row = None
    for i, row in df_raw.iterrows():
        if str(row[0]).strip().lower() == "date":
            header_row = i
            break

    if header_row is None:
        raise ValueError(
            "Could not find a 'Date' header row in the file. "
            "Please verify this is a valid QGenda export."
        )

    # Re-read with proper header
    df = pd.read_excel(path, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    # Drop the trailing 'Totals' row and any fully-blank rows
    df = df[df["Date"].astype(str).str.strip().str.lower() != "totals"]
    df = df.dropna(subset=["Staff", "Task"])

    # Parse dates
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    # Normalise staff names to 'First Last'
    df["Staff"] = df["Staff"].apply(_parse_staff_name)

    # Normalise numeric hours column (HA = Hours Assigned)
    if "HA" in df.columns:
        df["HA"] = pd.to_numeric(df["HA"], errors="coerce").fillna(0)
    else:
        df["HA"] = 0

    # Flag and optionally drop off/vacation rows
    low_task = df["Task"].astype(str).str.lower()
    off_mask = low_task.apply(
        lambda t: any(pat in t for pat in exclude_patterns)
    )
    df["IsOff"] = off_mask

    # Drop QGenda placeholder staff entries (LOCUMS, OPEN, TBD, etc.)
    placeholder_mask = df["Staff"].str.upper().str.strip().str.match(
        r"^(LOCUMS|OPEN|TBD|VACANT)\b", na=False
    )
    if placeholder_mask.any():
        names = ", ".join(df.loc[placeholder_mask, "Staff"].unique())
        print(f"  Placeholder staff removed: {placeholder_mask.sum():,}  ({names})")
        df = df[~placeholder_mask].copy()
        off_mask = df["IsOff"]

    print(f"  Total rows loaded  : {len(df):,}")
    print(f"  Off / vacation rows: {off_mask.sum():,}  (excluded from shift analysis)")
    print(f"  Work assignment rows: {(~off_mask).sum():,}")

    return df


def load_qgenda_staff_list(
    path: Path,
    exclude_patterns: List[str],
) -> pd.DataFrame:
    """
    Load a QGenda 'List by Staff Export' Excel export (SHIPMG / Imaging Healthcare style).

    Structure:
      Row 0 – report title "List by Staff Export (...)"
      Row 1 – generation timestamp
      Row 2 – column headers: Date | Last Name | First Name | ABBR | ... | Task Name | HA | ...
      Row 3+ – data rows

    Normalizes to same schema as other loaders: Date, Staff ('First Last'), Task, HA, IsOff.
    """
    print(f"  Detected format: QGenda 'List by Staff Export'")

    df = pd.read_excel(path, header=2)
    df.columns = [str(c).strip() for c in df.columns]

    # Require columns
    if "Date" not in df.columns or "Task Name" not in df.columns:
        raise ValueError(
            "Expected columns 'Date' and 'Task Name'. "
            "Verify this is a QGenda 'List by Staff Export' file."
        )

    # Build Staff from First Name + Last Name
    if "First Name" in df.columns and "Last Name" in df.columns:
        df["Staff"] = (
            df["First Name"].astype(str).str.strip()
            + " "
            + df["Last Name"].astype(str).str.strip()
        )
    else:
        df["Staff"] = df.get("ABBR", pd.Series([""] * len(df))).astype(str)

    # Normalize to Task (analyzer expects this name)
    df["Task"] = df["Task Name"].astype(str).str.strip()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Staff", "Task"])

    # HA (Hours Assigned)
    if "HA" in df.columns:
        df["HA"] = pd.to_numeric(df["HA"], errors="coerce").fillna(0)
    else:
        df["HA"] = 0

    # Off/vacation flag
    low_task = df["Task"].str.lower()
    off_mask = low_task.apply(
        lambda t: any(pat in t for pat in exclude_patterns)
    )
    df["IsOff"] = off_mask

    # Drop placeholders (LOCUMS, OPEN, TBD, etc.)
    placeholder_mask = df["Staff"].str.upper().str.strip().str.match(
        r"^(LOCUMS|OPEN|TBD|VACANT)\b", na=False
    )
    if placeholder_mask.any():
        n = placeholder_mask.sum()
        print(f"  Placeholder staff removed: {n:,} rows")
        df = df[~placeholder_mask].copy()
        off_mask = df["IsOff"]

    print(f"  Total rows loaded  : {len(df):,}")
    print(f"  Off / vacation rows: {off_mask.sum():,}  (excluded from shift analysis)")
    print(f"  Work assignment rows: {(~off_mask).sum():,}")

    return df


def load_generic(
    path: Path,
    exclude_patterns: List[str],
) -> pd.DataFrame:
    """
    Load a generic CSV or Excel schedule export.
    Handles:
      - 'Date' + 'Staff' (or 'Staff Member' / 'First Name'+'Last Name') columns
      - Staff names as column headers
    """
    print(f"  Detected format: generic CSV/Excel")

    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    df.columns = [str(c).strip() for c in df.columns]

    # Find date column
    date_col = next(
        (c for c in df.columns if "date" in c.lower()), None
    )
    if date_col is None:
        # Assume first column
        date_col = df.columns[0]

    df["Date"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["Date"])

    # Normalise to a 'Staff' + optional 'Task' column
    if "Staff" in df.columns or "Staff Member" in df.columns:
        col = "Staff" if "Staff" in df.columns else "Staff Member"
        df = df.rename(columns={col: "Staff"})
    elif "First Name" in df.columns and "Last Name" in df.columns:
        df["Staff"] = (
            df["First Name"].astype(str).str.strip()
            + " "
            + df["Last Name"].astype(str).str.strip()
        )
    else:
        # Staff as column headers – melt into long form
        skip = {"Date", date_col, "Day", "Week", "Month"}
        staff_cols = [c for c in df.columns if c not in skip and not c.startswith("Unnamed")]
        df = df.melt(id_vars=["Date"], value_vars=staff_cols,
                     var_name="Staff", value_name="Task")
        df = df.dropna(subset=["Task"])
        df = df[df["Task"].astype(str).str.strip().str.lower().isin(["", "nan", "off"]) == False]

    if "Task" not in df.columns:
        df["Task"] = ""
    if "HA" not in df.columns:
        df["HA"] = 0

    low_task = df["Task"].astype(str).str.lower()
    off_mask = low_task.apply(
        lambda t: any(pat in t for pat in exclude_patterns)
    )
    df["IsOff"] = off_mask

    print(f"  Total rows loaded  : {len(df):,}")
    print(f"  Off / vacation rows: {off_mask.sum():,}  (excluded from shift analysis)")
    print(f"  Work assignment rows: {(~off_mask).sum():,}")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSIS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def compute_metrics(counts: Dict[str, float]) -> Dict:
    """Compute fairness statistics from a name→count dict."""
    import numpy as np
    values = list(counts.values())
    if not values:
        return {}

    mean = float(np.mean(values))
    std  = float(np.std(values, ddof=0))
    cv   = (std / mean * 100) if mean > 0 else 0.0

    return {
        "mean": mean,
        "std": std,
        "cv": cv,
        "min": float(min(values)),
        "max": float(max(values)),
        "range": float(max(values) - min(values)),
        "counts": counts,
    }


def assess_fairness(cv: float) -> Tuple[str, str]:
    """Return (emoji, label) for a given CV."""
    if cv < 5:
        return "🌟", "EXCELLENT — near-perfect fairness"
    elif cv < 10:
        return "✅", "GOOD — fair distribution"
    elif cv < 20:
        return "⚠️ ", "MODERATE — some imbalance"
    else:
        return "❌", "POOR — significant imbalance"


# ─────────────────────────────────────────────────────────────────────────────
# REPORT GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def print_and_save_report(
    df_work: pd.DataFrame,
    shift_metrics: Dict,
    hour_metrics: Dict,
    out: Path,
    source_file: Path,
) -> None:
    """Print summary to console and write fairness_report.txt."""

    date_min = df_work["Date"].min().strftime("%Y-%m-%d")
    date_max = df_work["Date"].max().strftime("%Y-%m-%d")
    n_days   = (df_work["Date"].max() - df_work["Date"].min()).days + 1
    n_staff  = len(shift_metrics["counts"])

    emoji_s, label_s = assess_fairness(shift_metrics["cv"])
    emoji_h, label_h = assess_fairness(hour_metrics["cv"])

    # ── Console output ────────────────────────────────────────────────────
    sep = "=" * 80
    print(f"\n{sep}")
    print("📊  FAIRNESS ANALYSIS REPORT")
    print(sep)
    print(f"  Source   : {source_file.name}")
    print(f"  Date range: {date_min}  →  {date_max}  ({n_days} calendar days)")
    print(f"  Staff     : {n_staff}")
    print()

    # Shift-count fairness
    print("── SHIFT COUNT FAIRNESS ─────────────────────────────────────────────")
    print(f"  Mean shifts / person  : {shift_metrics['mean']:.1f}")
    print(f"  Std deviation         : {shift_metrics['std']:.2f}")
    print(f"  Coefficient of variation: {shift_metrics['cv']:.1f}%   {emoji_s} {label_s}")
    print(f"  Min / Max             : {int(shift_metrics['min'])} / {int(shift_metrics['max'])}")
    print()

    # Hour fairness
    print("── HOURS ASSIGNED (HA) FAIRNESS ──────────────────────────────────────")
    print(f"  Mean hours / person   : {hour_metrics['mean']:.1f}")
    print(f"  Std deviation         : {hour_metrics['std']:.1f}")
    print(f"  Coefficient of variation: {hour_metrics['cv']:.1f}%   {emoji_h} {label_h}")
    print(f"  Min / Max             : {hour_metrics['min']:.1f} / {hour_metrics['max']:.1f}")
    print()

    # Per-person table
    print("── PER-PERSON BREAKDOWN ──────────────────────────────────────────────")
    print(f"  {'Name':<26} {'Shifts':>7} {'% Mean':>8} {'Dev':>7}   {'Hours':>8} {'% Mean':>8} {'Dev':>8}")
    print("  " + "-" * 76)

    sorted_staff = sorted(
        shift_metrics["counts"].keys(),
        key=lambda n: shift_metrics["counts"][n],
        reverse=True,
    )
    for name in sorted_staff:
        sc  = shift_metrics["counts"][name]
        hc  = hour_metrics["counts"].get(name, 0)
        sp  = sc / shift_metrics["mean"] * 100 if shift_metrics["mean"] else 0
        hp  = hc / hour_metrics["mean"]  * 100 if hour_metrics["mean"]  else 0
        sd  = sc - shift_metrics["mean"]
        hd  = hc - hour_metrics["mean"]
        print(f"  {name:<26} {sc:>7d} {sp:>7.1f}% {sd:>+7.1f}   {hc:>8.1f} {hp:>7.1f}% {hd:>+8.1f}")

    print()

    # Task breakdown
    task_counts = df_work["Task"].value_counts()
    print("── TASK BREAKDOWN (top 20) ───────────────────────────────────────────")
    for task, cnt in task_counts.head(20).items():
        print(f"  {cnt:>5d}  {task}")
    print()

    # ── Write text file ───────────────────────────────────────────────────
    report_path = out / "fairness_report.txt"
    with open(report_path, "w") as f:
        f.write(f"FAIRNESS ANALYSIS REPORT\n")
        f.write(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Source    : {source_file.name}\n")
        f.write(f"Date range: {date_min} to {date_max}\n\n")

        f.write("SHIFT COUNT FAIRNESS\n")
        f.write(f"  Mean   : {shift_metrics['mean']:.2f}\n")
        f.write(f"  Std Dev: {shift_metrics['std']:.2f}\n")
        f.write(f"  CV     : {shift_metrics['cv']:.2f}%  — {label_s}\n\n")

        f.write("HOURS ASSIGNED FAIRNESS\n")
        f.write(f"  Mean   : {hour_metrics['mean']:.2f}\n")
        f.write(f"  Std Dev: {hour_metrics['std']:.2f}\n")
        f.write(f"  CV     : {hour_metrics['cv']:.2f}%  — {label_h}\n\n")

        f.write("PER-PERSON BREAKDOWN\n")
        f.write(f"{'Name':<26} {'Shifts':>7} {'Hours':>8}\n")
        f.write("-" * 45 + "\n")
        for name in sorted_staff:
            f.write(
                f"{name:<26} {int(shift_metrics['counts'][name]):>7d} "
                f"{hour_metrics['counts'].get(name, 0):>8.1f}\n"
            )

        f.write("\nTASK BREAKDOWN\n")
        for task, cnt in task_counts.items():
            f.write(f"  {cnt:>5d}  {task}\n")

    print(f"  ✓ Report  → {report_path}")

    # ── Write JSON ────────────────────────────────────────────────────────
    json_path = out / "fairness_data.json"
    with open(json_path, "w") as f:
        json.dump(
            {
                "date_range": {"start": date_min, "end": date_max},
                "shift_metrics": {
                    k: (v if not isinstance(v, dict) else {kk: float(vv) for kk, vv in v.items()})
                    for k, v in shift_metrics.items()
                    if k != "counts"
                },
                "hour_metrics": {
                    k: (v if not isinstance(v, dict) else {kk: float(vv) for kk, vv in v.items()})
                    for k, v in hour_metrics.items()
                    if k != "counts"
                },
                "per_person": {
                    name: {
                        "shifts": int(shift_metrics["counts"][name]),
                        "hours": float(hour_metrics["counts"].get(name, 0)),
                    }
                    for name in sorted_staff
                },
                "task_counts": {str(k): int(v) for k, v in task_counts.items()},
            },
            f,
            indent=2,
        )
    print(f"  ✓ JSON    → {json_path}")


# ─────────────────────────────────────────────────────────────────────────────
# VISUALISATIONS
# ─────────────────────────────────────────────────────────────────────────────

def generate_charts(
    df_work: pd.DataFrame,
    shift_metrics: Dict,
    hour_metrics: Dict,
    out: Path,
) -> None:
    if not PLOTTING_AVAILABLE:
        return

    staff_sorted = sorted(
        shift_metrics["counts"].keys(),
        key=lambda n: shift_metrics["counts"][n],
        reverse=True,
    )
    shifts = [shift_metrics["counts"][n] for n in staff_sorted]
    hours  = [hour_metrics["counts"].get(n, 0) for n in staff_sorted]
    x = range(len(staff_sorted))

    # ── Chart 1: Shift counts ─────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(13, 5))
    colors = []
    for s in shifts:
        if s > shift_metrics["mean"] + shift_metrics["std"]:
            colors.append("#b22222")   # significantly above
        elif s < shift_metrics["mean"] - shift_metrics["std"]:
            colors.append("#1a3d7c")   # significantly below
        else:
            colors.append("#4a90d9")   # within normal range

    bars = ax.bar(x, shifts, color=colors, alpha=0.85, width=0.65)
    ax.axhline(shift_metrics["mean"], color="crimson", linewidth=1.8,
               linestyle="--", label=f"Mean: {shift_metrics['mean']:.1f}")
    ax.axhline(shift_metrics["mean"] + shift_metrics["std"], color="orange",
               linewidth=1, linestyle=":", label=f"±1 SD")
    ax.axhline(shift_metrics["mean"] - shift_metrics["std"], color="orange",
               linewidth=1, linestyle=":")

    for bar, val in zip(bars, shifts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.4,
                str(val), ha="center", va="bottom", fontsize=8)

    ax.set_xticks(list(x))
    ax.set_xticklabels(staff_sorted, rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("Shift Count")
    ax.set_title(
        f"Shift Distribution by Staff\nCV = {shift_metrics['cv']:.1f}%",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    p = out / "shift_distribution.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"  ✓ Chart   → {p}")

    # ── Chart 2: Hours assigned ───────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(13, 5))
    hcolors = []
    for h in hours:
        if h > hour_metrics["mean"] + hour_metrics["std"]:
            hcolors.append("#b22222")
        elif h < hour_metrics["mean"] - hour_metrics["std"]:
            hcolors.append("#1a3d7c")
        else:
            hcolors.append("#2e8b57")

    bars = ax.bar(x, hours, color=hcolors, alpha=0.85, width=0.65)
    ax.axhline(hour_metrics["mean"], color="crimson", linewidth=1.8,
               linestyle="--", label=f"Mean: {hour_metrics['mean']:.1f} hrs")
    ax.axhline(hour_metrics["mean"] + hour_metrics["std"], color="orange",
               linewidth=1, linestyle=":")
    ax.axhline(hour_metrics["mean"] - hour_metrics["std"], color="orange",
               linewidth=1, linestyle=":")

    for bar, val in zip(bars, hours):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{val:.0f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(list(x))
    ax.set_xticklabels(staff_sorted, rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("Total Hours Assigned (HA)")
    ax.set_title(
        f"Hours-Assigned Distribution by Staff\nCV = {hour_metrics['cv']:.1f}%",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    p = out / "hours_distribution.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"  ✓ Chart   → {p}")

    # ── Chart 3: Deviation from mean (shifts) ─────────────────────────────
    deviations = [s - shift_metrics["mean"] for s in shifts]
    fig, ax = plt.subplots(figsize=(13, 4))
    bar_colors = ["#b22222" if d >= 0 else "#1a3d7c" for d in deviations]
    ax.bar(x, deviations, color=bar_colors, alpha=0.8, width=0.65)
    ax.axhline(0, color="black", linewidth=1)
    ax.axhline(shift_metrics["std"],  color="orange", linewidth=1, linestyle="--", label="±1 SD")
    ax.axhline(-shift_metrics["std"], color="orange", linewidth=1, linestyle="--")
    ax.set_xticks(list(x))
    ax.set_xticklabels(staff_sorted, rotation=40, ha="right", fontsize=9)
    ax.set_ylabel("Deviation from Mean Shifts")
    ax.set_title("Shift Deviation from Mean", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    p = out / "shift_deviation.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"  ✓ Chart   → {p}")

    # ── Chart 4: Monthly trend ────────────────────────────────────────────
    df_work2 = df_work.copy()
    df_work2["YearMonth"] = df_work2["Date"].dt.to_period("M")
    monthly = (
        df_work2.groupby(["YearMonth", "Staff"])
        .size()
        .reset_index(name="count")
    )
    monthly["YearMonth_dt"] = monthly["YearMonth"].dt.to_timestamp()
    pivot = monthly.pivot(index="YearMonth_dt", columns="Staff", values="count").fillna(0)

    fig, ax = plt.subplots(figsize=(14, 6))
    cmap = plt.colormaps.get_cmap("tab20").resampled(len(pivot.columns))
    for i, col in enumerate(pivot.columns):
        ax.plot(pivot.index, pivot[col], marker="o", markersize=4,
                linewidth=1.4, label=col, color=cmap(i))

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Shifts per Month")
    ax.set_title("Monthly Shift Trend per Staff Member", fontsize=13, fontweight="bold")
    ax.legend(fontsize=7, ncol=2, loc="upper right")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    p = out / "monthly_trend.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"  ✓ Chart   → {p}")

    # ── Chart 5: Task-type breakdown (top 15) ─────────────────────────────
    task_counts = df_work["Task"].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(task_counts.index[::-1], task_counts.values[::-1],
                   color="#4a90d9", alpha=0.85)
    for bar, val in zip(bars, task_counts.values[::-1]):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=9)
    ax.set_xlabel("Assignment Count")
    ax.set_title("Top 15 Task Types", fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    p = out / "task_breakdown.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"  ✓ Chart   → {p}")


# ─────────────────────────────────────────────────────────────────────────────
# SUBSPECIALTY CHARTS
# ─────────────────────────────────────────────────────────────────────────────

def generate_subspecialty_charts(
    df_sub_all: "pd.DataFrame",
    subspecialty_tasks: List[str],
    out: "Path",
) -> None:
    """
    For each subspecialty task produce a two-panel PNG:
      Panel A – Total assignment count per person (horizontal bar, % share labelled)
      Panel B – Monthly assignment cadence (stacked bar by radiologist)

    Also writes a combined overview PNG showing all subspecialties side-by-side.
    """
    if not PLOTTING_AVAILABLE:
        return

    # Consistent colour palette keyed to staff names across all subspecialties
    all_staff = sorted(df_sub_all["Staff"].unique())
    palette   = plt.colormaps.get_cmap("tab20").resampled(max(len(all_staff), 2))
    staff_color = {name: palette(i) for i, name in enumerate(all_staff)}

    summary_rows = []

    for task_name in subspecialty_tasks:
        mask   = df_sub_all["Task"].str.strip().str.lower() == task_name.lower()
        df_t   = df_sub_all[mask].copy()

        if df_t.empty:
            print(f"  \u26a0  No data for subspecialty: \'{task_name}\' — skipping")
            continue

        counts = df_t["Staff"].value_counts()   # sorted descending
        total  = int(counts.sum())

        # Monthly pivot (sorted columns by total desc)
        df_t["YearMonth"] = df_t["Date"].dt.to_period("M")
        monthly = (
            df_t.groupby(["YearMonth", "Staff"])
            .size()
            .reset_index(name="n")
        )
        monthly["YearMonth_dt"] = monthly["YearMonth"].dt.to_timestamp()
        pivot = (
            monthly.pivot(index="YearMonth_dt", columns="Staff", values="n")
            .fillna(0)
            .astype(int)
            .reindex(columns=counts.index.tolist())  # desc by total
        )

        for name, cnt in counts.items():
            summary_rows.append({"Subspecialty": task_name, "Staff": name, "Count": int(cnt)})

        # ── Figure ───────────────────────────────────────────────────────
        fig, (ax_top, ax_bot) = plt.subplots(
            2, 1,
            figsize=(10, 9),
            gridspec_kw={"height_ratios": [1, 1.5]},
        )
        fig.suptitle(task_name, fontsize=15, fontweight="bold", y=0.99)

        # Panel A: horizontal bar – totals
        bar_colors = [staff_color[n] for n in counts.index]
        hbars = ax_top.barh(
            counts.index[::-1], counts.values[::-1],
            color=bar_colors[::-1], alpha=0.88, height=0.5,
        )
        for bar, val in zip(hbars, counts.values[::-1]):
            pct = val / total * 100
            ax_top.text(
                bar.get_width() + 0.15,
                bar.get_y() + bar.get_height() / 2,
                f"{val}  ({pct:.1f}%)",
                va="center", fontsize=10,
            )
        ax_top.set_xlabel("Total Assignments", fontsize=10)
        ax_top.set_title(
            f"Total Assignments by Radiologist  (n = {total})",
            fontsize=11, pad=6,
        )
        ax_top.set_xlim(0, counts.max() * 1.40)
        ax_top.grid(axis="x", alpha=0.3)
        ax_top.spines[["top", "right"]].set_visible(False)

        # Panel B: stacked monthly bar
        x_pos   = range(len(pivot))
        bottom  = None
        month_labels = [dt.strftime("%b %Y") for dt in pivot.index]

        for col in pivot.columns:
            vals  = pivot[col].values.astype(float)
            color = staff_color[col]
            if bottom is None:
                ax_bot.bar(x_pos, vals, label=col, color=color, alpha=0.88, width=0.65)
                bottom = vals.copy()
            else:
                ax_bot.bar(x_pos, vals, bottom=bottom, label=col, color=color, alpha=0.88, width=0.65)
                bottom = bottom + vals

        # Total label at top of each stack
        for xi, tot in enumerate(bottom):
            if tot > 0:
                ax_bot.text(xi, tot + 0.12, str(int(tot)),
                            ha="center", va="bottom", fontsize=9, fontweight="bold")

        ax_bot.set_xticks(list(x_pos))
        ax_bot.set_xticklabels(month_labels, rotation=35, ha="right", fontsize=9)
        ax_bot.set_ylabel("Assignment Count", fontsize=10)
        ax_bot.set_title("Monthly Assignment Cadence", fontsize=11, pad=6)
        ax_bot.legend(
            title="Radiologist", fontsize=9, title_fontsize=9,
            loc="upper right", framealpha=0.85,
        )
        ax_bot.grid(axis="y", alpha=0.3)
        ax_bot.spines[["top", "right"]].set_visible(False)

        fig.tight_layout(rect=[0, 0, 1, 0.97])

        safe = re.sub(r"[^a-z0-9]+", "_", task_name.lower()).strip("_")
        p    = out / f"subspecialty_{safe}.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  \u2713 Subspecialty chart  \u2192 {p}")

    # ── Combined overview ─────────────────────────────────────────────────
    if not summary_rows:
        return

    df_ov     = pd.DataFrame(summary_rows)
    tasks_ov  = df_ov["Subspecialty"].unique().tolist()
    n_tasks   = len(tasks_ov)

    fig, axes = plt.subplots(1, n_tasks, figsize=(6 * n_tasks, 6), sharey=False)
    if n_tasks == 1:
        axes = [axes]
    fig.suptitle("Subspecialty Assignment Overview", fontsize=14, fontweight="bold")

    for ax, task in zip(axes, tasks_ov):
        sub   = df_ov[df_ov["Subspecialty"] == task].sort_values("Count", ascending=False)
        cols  = [staff_color[n] for n in sub["Staff"]]
        bars  = ax.bar(sub["Staff"], sub["Count"], color=cols, alpha=0.88, width=0.55)
        total = sub["Count"].sum()
        for bar, val in zip(bars, sub["Count"]):
            pct = val / total * 100
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.2,
                f"{val}\n({pct:.0f}%)",
                ha="center", va="bottom", fontsize=10, fontweight="bold",
            )
        ax.set_title(task, fontsize=12, fontweight="bold", pad=8)
        ax.set_ylabel("Assignment Count", fontsize=10)
        ax.set_ylim(0, sub["Count"].max() * 1.30)
        ax.tick_params(axis="x", rotation=20, labelsize=9)
        ax.grid(axis="y", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    p = out / "subspecialty_overview.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  \u2713 Subspecialty overview \u2192 {p}")


# ─────────────────────────────────────────────────────────────────────────────
# IHS WEEKEND BREAKOUT CHARTS
# ─────────────────────────────────────────────────────────────────────────────

def generate_ihs_weekend_charts(df_work: "pd.DataFrame", out: "Path") -> None:
    """
    Breakout charts for IHS weekend shifts: counts per radiologist for
    Weekend IHS MRI and Weekend IHS PET. Produces one horizontal bar chart
    per task and an overview with both side by side.
    """
    if not PLOTTING_AVAILABLE:
        return

    task_col = df_work["Task"].astype(str).str.strip().str.lower()
    weekend_set = {t.strip().lower() for t in IHS_WEEKEND_TASKS}
    mask = task_col.isin(weekend_set)
    df_weekend = df_work[mask].copy()
    if df_weekend.empty:
        return

    all_staff = sorted(df_weekend["Staff"].unique())
    palette = plt.colormaps.get_cmap("tab20").resampled(max(len(all_staff), 2))
    staff_color = {name: palette(i) for i, name in enumerate(all_staff)}

    summary_rows = []
    for task_name in IHS_WEEKEND_TASKS:
        task_mask = df_weekend["Task"].str.strip().str.lower() == task_name.lower()
        df_t = df_weekend[task_mask]
        if df_t.empty:
            continue
        counts = df_t["Staff"].value_counts()
        total = int(counts.sum())
        for name, cnt in counts.items():
            summary_rows.append({"Task": task_name, "Staff": name, "Count": int(cnt)})

        # Single-task horizontal bar chart
        fig, ax = plt.subplots(figsize=(10, max(5, len(counts) * 0.4)))
        bar_colors = [staff_color[n] for n in counts.index]
        hbars = ax.barh(counts.index[::-1], counts.values[::-1], color=bar_colors[::-1], alpha=0.88, height=0.5)
        for bar, val in zip(hbars, counts.values[::-1]):
            pct = val / total * 100 if total else 0
            ax.text(bar.get_width() + 0.15, bar.get_y() + bar.get_height() / 2,
                    f"{val}  ({pct:.1f}%)", va="center", fontsize=10)
        ax.set_xlabel("Assignment Count", fontsize=10)
        ax.set_title(f"{task_name} — Count by Radiologist (n = {total})", fontsize=12, fontweight="bold")
        ax.set_xlim(0, counts.max() * 1.35)
        ax.grid(axis="x", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        safe = re.sub(r"[^a-z0-9]+", "_", task_name.lower()).strip("_")
        p = out / f"ihs_weekend_{safe}.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  \u2713 IHS weekend chart \u2192 {p}")

    # Overview: both IHS weekend tasks side by side (only if both present)
    df_ov = pd.DataFrame(summary_rows) if summary_rows else None
    tasks_ov = df_ov["Task"].unique().tolist() if df_ov is not None and len(df_ov) else []
    if len(tasks_ov) >= 2:
        fig, axes = plt.subplots(1, len(tasks_ov), figsize=(6 * len(tasks_ov), 6), sharey=False)
        if len(tasks_ov) == 1:
            axes = [axes]
        fig.suptitle("IHS Weekend Shifts — Count by Radiologist", fontsize=14, fontweight="bold")
        for ax, task in zip(axes, tasks_ov):
            sub = df_ov[df_ov["Task"] == task].sort_values("Count", ascending=False)
            cols = [staff_color[n] for n in sub["Staff"]]
            bars = ax.bar(sub["Staff"], sub["Count"], color=cols, alpha=0.88, width=0.55)
            for bar, val in zip(bars, sub["Count"]):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                        str(int(val)), ha="center", va="bottom", fontsize=10, fontweight="bold")
            ax.set_title(task, fontsize=12, fontweight="bold", pad=8)
            ax.set_ylabel("Assignment Count", fontsize=10)
            ax.tick_params(axis="x", rotation=25, labelsize=9)
            ax.grid(axis="y", alpha=0.3)
            ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        p = out / "ihs_weekend_overview.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  \u2713 IHS weekend overview \u2192 {p}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

# Default roster paths (relative to project root = parent of scripts/)
_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_ROSTER_DIAGNOSTIC = _CONFIG_DIR / "sample_roster_key_diagnostic.csv"
DEFAULT_ROSTER_IR = _CONFIG_DIR / "sample_roster_key_interventional.csv"


def load_roster_names(roster_path: Path) -> List[str]:
    """Load list of staff names from a roster_key-style CSV (column 'name')."""
    rdf = pd.read_csv(roster_path)
    if "name" not in rdf.columns:
        raise ValueError(f"Roster CSV must have a 'name' column: {roster_path}")
    return [str(n).strip() for n in rdf["name"].dropna().unique() if str(n).strip()]


def load_roster_names_for_pool(roster_path: Path, pool: str) -> List[str]:
    """
    Load staff names for a given pool from a roster_key-style CSV.

    pool: 'combined' -> not used (caller should not filter).
           'diagnostic' -> names where participates_ir is no (DR-only).
           'ir' -> all names in the roster (IR roster).
    """
    rdf = pd.read_csv(roster_path)
    if "name" not in rdf.columns:
        raise ValueError(f"Roster CSV must have a 'name' column: {roster_path}")

    if pool == "ir":
        return [str(n).strip() for n in rdf["name"].dropna().unique() if str(n).strip()]

    if pool == "diagnostic":
        if "participates_ir" not in rdf.columns:
            raise ValueError(
                f"Roster CSV must have 'participates_ir' column for --pool diagnostic: {roster_path}"
            )
        no_ir = rdf["participates_ir"].astype(str).str.strip().str.lower().isin(
            ("no", "n", "0", "false")
        )
        return [str(n).strip() for n in rdf.loc[no_ir, "name"].dropna().unique() if str(n).strip()]

    return []


class ScheduleAnalyzer:
    def __init__(
        self,
        schedule_file: str,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
        exclude_tasks: Optional[List[str]] = None,
        roster_path: Optional[str] = None,
        pool: str = "combined",
    ):
        self.path         = Path(schedule_file)
        self.start_date   = start_date
        self.end_date     = end_date
        self.exclude_patterns = [p.lower() for p in (exclude_tasks or DEFAULT_EXCLUDE_PATTERNS)]
        self.roster_path  = Path(roster_path) if roster_path else None
        self.pool         = pool  # "combined" | "diagnostic" | "ir"

    def run(self, output_dir: str = ".") -> bool:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        charts_dir    = out / "charts"
        subspecialty_dir = out / "subspecialty"
        charts_dir.mkdir(exist_ok=True)
        subspecialty_dir.mkdir(exist_ok=True)
        print(f"\n📂 Loading: {self.path}")
        fmt = detect_format(self.path)

        try:
            if fmt == "qgenda_tag_list":
                df = load_qgenda_tag_list(self.path, self.exclude_patterns)
            elif fmt == "qgenda_staff_list":
                df = load_qgenda_staff_list(self.path, self.exclude_patterns)
            else:
                df = load_generic(self.path, self.exclude_patterns)
        except Exception as e:
            print(f"✗ Could not load file: {e}")
            return False

        # Date range filter
        if self.start_date:
            df = df[df["Date"] >= pd.to_datetime(self.start_date)]
        if self.end_date:
            df = df[df["Date"] <= pd.to_datetime(self.end_date)]

        # Fill missing HA from cleaner/schedule_ha_config.json; save cleaned file if any filled
        df, _n_ha_filled = fill_missing_ha_from_config(
            df, DEFAULT_HA_CONFIG_PATH, self.path, out
        )

        df_work = df[~df["IsOff"]].copy()

        # Pool / roster filter: combined (all), diagnostic (DR only), or ir (IR only)
        roster_names: Optional[List[str]] = None
        if self.pool == "diagnostic":
            path = self.roster_path if self.roster_path and self.roster_path.exists() else DEFAULT_ROSTER_DIAGNOSTIC
            if not path.exists():
                print(f"✗ Roster not found for --pool diagnostic: {path}")
                return False
            roster_names = load_roster_names_for_pool(path, "diagnostic")
            print(f"  Pool              : diagnostic (DR only) — {path.name} (participates_ir=no)")
        elif self.pool == "ir":
            path = self.roster_path if self.roster_path and self.roster_path.exists() else DEFAULT_ROSTER_IR
            if not path.exists():
                print(f"✗ Roster not found for --pool ir: {path}")
                return False
            roster_names = load_roster_names_for_pool(path, "ir")
            print(f"  Pool              : IR only — {path.name}")
        elif self.roster_path and self.roster_path.exists():
            roster_names = load_roster_names(self.roster_path)
            print(f"  Roster filter     : {self.roster_path.name}")

        if roster_names is not None:
            before = len(df_work)
            df_work = df_work[df_work["Staff"].isin(roster_names)].copy()
            print(f"  Staff in pool     : {df_work['Staff'].nunique()}  ({len(df_work):,} rows)")
            if before > len(df_work):
                print(f"    (excluded {before - len(df_work):,} rows for staff not in pool)")

        if df_work.empty:
            print("✗ No work assignments found after filtering.")
            return False

        # ── Separate subspecialty and rotation (main shifts only) ─────────
        sub_mask = df_work["Task"].str.strip().str.lower().isin(
            [t.lower() for t in SUBSPECIALTY_TASKS]
        )
        df_subspecialty = df_work[sub_mask].copy()
        # Rotation = only MAIN_SHIFT_TASKS (excludes subspecialty, IHS Weekend MRI/PET, and other tasks)
        main_shift_set = {t.strip().lower() for t in MAIN_SHIFT_TASKS}
        rotation_mask = df_work["Task"].astype(str).str.strip().str.lower().isin(main_shift_set)
        df_rotation = df_work[rotation_mask].copy()

        if sub_mask.any():
            print(f"\n  Subspecialty rows separated: {sub_mask.sum():,}")
            for t in SUBSPECIALTY_TASKS:
                n = (df_work["Task"].str.strip().str.lower() == t.lower()).sum()
                if n:
                    print(f"    • {t}: {n}")

        excluded_from_rotation = (~rotation_mask & ~sub_mask).sum()
        if excluded_from_rotation:
            print(f"  Excluded from rotation (not in main shifts): {excluded_from_rotation:,} rows")
        print(f"\n  Rotation work rows (main shifts only): {len(df_rotation):,}")
        print(f"  Staff in scope     : {df_rotation['Staff'].nunique()}")

        # Shift counts (rotation only)
        shift_counts = df_rotation["Staff"].value_counts().to_dict()
        shift_counts = {k: int(v) for k, v in shift_counts.items()}
        shift_metrics = compute_metrics(shift_counts)

        # Hour counts (rotation only)
        hour_counts = df_rotation.groupby("Staff")["HA"].sum().to_dict()
        hour_counts = {k: float(v) for k, v in hour_counts.items()}
        for name in shift_counts:
            hour_counts.setdefault(name, 0.0)
        hour_metrics = compute_metrics(hour_counts)

        print_and_save_report(
            df_rotation, shift_metrics, hour_metrics, out, self.path
        )
        generate_charts(df_rotation, shift_metrics, hour_metrics, charts_dir)

        # ── Subspecialty charts ───────────────────────────────────────────
        if not df_subspecialty.empty:
            print("\n── Subspecialty charts ──────────────────────────────────────────────────────────────")
            generate_subspecialty_charts(df_subspecialty, SUBSPECIALTY_TASKS, charts_dir)

        # ── IHS Weekend breakout charts (counts per radiologist) ───────────
        print("\n── IHS Weekend breakout charts ──────────────────────────────────────────────────────────")
        generate_ihs_weekend_charts(df_work, charts_dir)

        print(f"\n✅  Analysis complete!  Results saved to: {out.resolve()}")
        return True


# ─────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Analyze QGenda schedule exports for fairness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyze_schedule.py schedule.xlsx
  python analyze_schedule.py schedule.xlsx --start-date 2026-01-01 --end-date 2026-03-31
  python analyze_schedule.py schedule.xlsx --output-dir reports/Q1
  python analyze_schedule.py schedule.xlsx --pool diagnostic   # DR group only
  python analyze_schedule.py schedule.xlsx --pool ir            # IR group only
  python analyze_schedule.py schedule.xlsx --exclude-tasks VACATION "OFF ALL DAY" "No Call"
        """,
    )
    parser.add_argument("schedule_file", help="Path to QGenda CSV/Excel export")
    parser.add_argument("--start-date",  help="Start date filter (YYYY-MM-DD)")
    parser.add_argument("--end-date",   help="End date filter (YYYY-MM-DD)")
    parser.add_argument("--output-dir",  default=".", help="Output directory (default: current directory)")
    parser.add_argument(
        "--pool",
        choices=["combined", "diagnostic", "ir"],
        default="combined",
        help="Analyze by group: combined (all staff), diagnostic (DR only), ir (IR only). "
             "Uses config sample rosters unless --roster is given.",
    )
    parser.add_argument(
        "--exclude-tasks", nargs="+",
        help="Task names to exclude (case-insensitive substring match). "
             "Defaults: vacation, off all day, pres/vp vacation, no call",
    )
    parser.add_argument(
        "--roster",
        help="Optional roster CSV for --pool diagnostic/ir (defaults: config/sample_roster_key_*.csv). "
             "With --pool combined, filters to staff in this roster.",
    )
    args = parser.parse_args()

    if not Path(args.schedule_file).exists():
        print(f"✗ File not found: {args.schedule_file}")
        sys.exit(1)

    analyzer = ScheduleAnalyzer(
        args.schedule_file,
        start_date=args.start_date,
        end_date=args.end_date,
        exclude_tasks=args.exclude_tasks,
        roster_path=args.roster,
        pool=args.pool,
    )
    success = analyzer.run(args.output_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
