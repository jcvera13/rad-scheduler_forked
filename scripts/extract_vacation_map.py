#!/usr/bin/env python3
"""
Extract exempt days from a QGenda .xlsx export and write config/vacation_map.csv.

Reads an .xlsx file from inputs/ (or a given path), finds all rows where the task
is a qualifying exempt type (e.g. vacation, off all day, admin, No call, no ep),
and writes config/vacation_map.csv in the format expected by dry_run / load_vacation_map:
  date,unavailable_staff
  2026-01-15,First Last;Other Name
  ...

Staff names are normalized to "First Last" to match roster_key.csv.
Dates are written as YYYY-MM-DD.

Usage:
  python scripts/extract_vacation_map.py
  python scripts/extract_vacation_map.py --input inputs/MyExport.xlsx
  python scripts/extract_vacation_map.py --input inputs/MyExport.xlsx --output config/vacation_map.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

# Project root (parent of scripts/)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_INPUTS_DIR = PROJECT_ROOT / "inputs"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "config" / "vacation_map.csv"

# Qualifying exempt tasks (case-insensitive substring match)
EXEMPT_TASK_PATTERNS = [
    "vacation",
    "off all day",
    "pres/vp vacation",
    "admin",
    "administrative",
    "no call",
    "no ep",
]


def detect_format(path: Path) -> str:
    """Return 'qgenda_tag_list', 'qgenda_staff_list', or 'generic_columns'."""
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


def parse_staff_name(raw: str) -> str:
    """Convert 'Last, First (Last, Ini)' to 'First Last'."""
    m = re.match(r"^([^,(]+),\s*([^(]+)", str(raw).strip())
    if m:
        return f"{m.group(2).strip()} {m.group(1).strip()}"
    return str(raw).strip()


def load_qgenda_tag_list(path: Path, exempt_patterns: list[str]) -> pd.DataFrame:
    """Load QGenda 'List by Assignment Tag' and return rows with Date, Staff, Task, IsOff."""
    df_raw = pd.read_excel(path, header=None)
    header_row = None
    for i, row in df_raw.iterrows():
        if str(row[0]).strip().lower() == "date":
            header_row = i
            break
    if header_row is None:
        raise ValueError("Could not find 'Date' header row in file.")
    df = pd.read_excel(path, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    df = df[df["Date"].astype(str).str.strip().str.lower() != "totals"]
    df = df.dropna(subset=["Staff", "Task"])
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df["Staff"] = df["Staff"].apply(parse_staff_name)
    low = df["Task"].astype(str).str.lower()
    df["IsOff"] = low.apply(lambda t: any(p in t for p in exempt_patterns))
    # Drop placeholders
    placeholder = df["Staff"].str.upper().str.strip().str.match(r"^(LOCUMS|OPEN|TBD|VACANT)\b", na=False)
    df = df[~placeholder].copy()
    return df


def load_qgenda_staff_list(path: Path, exempt_patterns: list[str]) -> pd.DataFrame:
    """Load QGenda 'List by Staff Export' and return rows with Date, Staff, Task, IsOff."""
    df = pd.read_excel(path, header=2)
    df.columns = [str(c).strip() for c in df.columns]
    if "Date" not in df.columns or "Task Name" not in df.columns:
        raise ValueError("Expected columns 'Date' and 'Task Name'.")
    if "First Name" in df.columns and "Last Name" in df.columns:
        df["Staff"] = (
            df["First Name"].astype(str).str.strip() + " " + df["Last Name"].astype(str).str.strip()
        )
    else:
        df["Staff"] = df.get("ABBR", pd.Series([""] * len(df))).astype(str)
    df["Task"] = df["Task Name"].astype(str).str.strip()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Staff", "Task"])
    low = df["Task"].str.lower()
    df["IsOff"] = low.apply(lambda t: any(p in t for p in exempt_patterns))
    placeholder = df["Staff"].str.upper().str.strip().str.match(r"^(LOCUMS|OPEN|TBD|VACANT)\b", na=False)
    df = df[~placeholder].copy()
    return df


def load_generic(path: Path, exempt_patterns: list[str]) -> pd.DataFrame:
    """Load generic Excel/CSV with Date and Staff (and optional Task)."""
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]
    date_col = next((c for c in df.columns if "date" in c.lower()), df.columns[0])
    df["Date"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["Date"])
    if "Staff" in df.columns or "Staff Member" in df.columns:
        df["Staff"] = df["Staff"] if "Staff" in df.columns else df["Staff Member"]
    elif "First Name" in df.columns and "Last Name" in df.columns:
        df["Staff"] = (
            df["First Name"].astype(str).str.strip() + " " + df["Last Name"].astype(str).str.strip()
        )
    else:
        raise ValueError("Need Staff (or First/Last Name) column.")
    if "Task" not in df.columns:
        df["Task"] = ""
    low = df["Task"].astype(str).str.lower()
    df["IsOff"] = low.apply(lambda t: any(p in t for p in exempt_patterns))
    return df


def load_exempt_rows(path: Path) -> pd.DataFrame:
    """Load xlsx and return only rows that are exempt (vacation, off, admin, no call, no ep)."""
    fmt = detect_format(path)
    patterns = [p.lower() for p in EXEMPT_TASK_PATTERNS]
    if fmt == "qgenda_tag_list":
        df = load_qgenda_tag_list(path, patterns)
    elif fmt == "qgenda_staff_list":
        df = load_qgenda_staff_list(path, patterns)
    else:
        df = load_generic(path, patterns)
    return df[df["IsOff"]].copy()


def build_vacation_map(df_exempt: pd.DataFrame) -> dict[str, list[str]]:
    """Aggregate exempt rows by date -> list of unique staff names."""
    df_exempt = df_exempt[["Date", "Staff"]].drop_duplicates()
    vacation_map: dict[str, list[str]] = {}
    for _, row in df_exempt.iterrows():
        date_str = row["Date"].strftime("%Y-%m-%d")
        staff = str(row["Staff"]).strip()
        if not staff:
            continue
        if date_str not in vacation_map:
            vacation_map[date_str] = []
        if staff not in vacation_map[date_str]:
            vacation_map[date_str].append(staff)
    return vacation_map


def write_vacation_map_csv(vacation_map: dict[str, list[str]], output_path: Path) -> None:
    """Write vacation_map.csv with columns date, unavailable_staff (semicolon-separated)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for date_str in sorted(vacation_map.keys()):
        staff_list = vacation_map[date_str]
        unavailable_staff = ";".join(sorted(staff_list))
        rows.append({"date": date_str, "unavailable_staff": unavailable_staff})
    df_out = pd.DataFrame(rows)
    df_out.to_csv(output_path, index=False)
    print(f"  Wrote {len(rows)} dates → {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract exempt days from QGenda .xlsx and write config/vacation_map.csv"
    )
    parser.add_argument(
        "--input",
        "-i",
        default=None,
        help="Input .xlsx file or directory containing one (default: first .xlsx in inputs/)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=str(DEFAULT_OUTPUT_PATH),
        help=f"Output CSV path (default: {DEFAULT_OUTPUT_PATH})",
    )
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else None
    if input_path is None:
        if not DEFAULT_INPUTS_DIR.exists():
            print(f"Error: inputs directory not found: {DEFAULT_INPUTS_DIR}")
            return 1
        xlsx_files = list(DEFAULT_INPUTS_DIR.glob("*.xlsx"))
        if not xlsx_files:
            print(f"Error: no .xlsx file found in {DEFAULT_INPUTS_DIR}")
            return 1
        input_path = sorted(xlsx_files)[0]
        print(f"Using input: {input_path.name}")
    else:
        input_path = Path(input_path)
        if input_path.is_dir():
            xlsx_files = list(input_path.glob("*.xlsx"))
            if not xlsx_files:
                print(f"Error: no .xlsx in directory {input_path}")
                return 1
            input_path = sorted(xlsx_files)[0]
            print(f"Using input: {input_path.name}")

    if not input_path.exists():
        print(f"Error: file not found: {input_path}")
        return 1

    output_path = Path(args.output)

    try:
        df_exempt = load_exempt_rows(input_path)
    except Exception as e:
        print(f"Error loading file: {e}")
        return 1

    if df_exempt.empty:
        print("  No exempt rows found. Writing empty vacation map.")
        vacation_map = {}
    else:
        print(f"  Exempt rows: {len(df_exempt)}")
        vacation_map = build_vacation_map(df_exempt)
        print(f"  Unique dates with exempt staff: {len(vacation_map)}")

    write_vacation_map_csv(vacation_map, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
