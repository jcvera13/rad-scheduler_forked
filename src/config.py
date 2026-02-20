"""
Configuration Module for Fair Radiology Scheduling Engine

Loads roster, shift definitions, constraint weights, and fairness targets.
See docs/architecture.md, docs/rotation_configuration.md, docs/analysis/comprehensive_analysis.md
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Default paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_ROSTER_PATH = DEFAULT_CONFIG_DIR / "roster_key.csv"
DEFAULT_VACATION_PATH = DEFAULT_CONFIG_DIR / "vacation_map.csv"
DEFAULT_CURSOR_PATH = DEFAULT_CONFIG_DIR / "cursor_state.json"


# ---------------------------------------------------------------------------
# Shift Definitions (from M0_Weighted_Revised_Analysis, rotation_configuration)
# ---------------------------------------------------------------------------
DEFAULT_SHIFT_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # Inpatient Weekday Mercy shifts
    "M0": {"hours": 2, "weight": 0.25, "location": "remote", "description": "Helper shift 0700-0800, 1130-1230"},
    "M1": {"hours": 8, "weight": 1.0, "location": "onsite", "description": "Day shift 0800-1600"},
    "M2": {"hours": 8, "weight": 1.0, "location": "remote", "description": "Remote 0930-1730"},
    "M3": {"hours": 6, "weight": 0.75, "location": "remote", "description": "Evening 1600-2200"},
    # IR shifts (qualification-gated)
    "IR1": {"hours": 8, "weight": 1.0, "location": "onsite", "requires": "ir"},
    "IR2": {"hours": 8, "weight": 1.0, "location": "onsite", "requires": "ir"},
    # Weekend inpatient
    "M0_WEEKEND": {"hours": 2, "weight": 0.25, "location": "remote"},
    "EP": {"hours": 6.5, "weight": 0.81, "location": "mixed"},  # Early Person
    "LP": {"hours": 8, "weight": 1.0, "location": "remote"},    # Dx-CALL/Late Person
}


# ---------------------------------------------------------------------------
# Inpatient Weekday Config (4 shifts: M0, M1, M2, M3)
# ---------------------------------------------------------------------------
INPATIENT_WEEKDAY_CONFIG = {
    "shift_names": ["M0", "M1", "M2", "M3"],
    "shifts_per_period": 4,
    "pool_filter": "participates_mercy",
    "avoid_previous": False,  # Weekdays: back-to-back is acceptable
    "allow_fallback": True,
    "cursor_key": "weekday_cursor",
}

# ---------------------------------------------------------------------------
# Inpatient Weekend Config (3 shifts per weekend)
# ---------------------------------------------------------------------------
INPATIENT_WEEKEND_CONFIG = {
    "shift_names": ["M0 Weekend", "EP", "Dx-CALL"],  # LP = Dx-CALL
    "shifts_per_period": 3,
    "pool_filter": "participates_weekend",
    "avoid_previous": True,   # CRITICAL: Avoid back-to-back weekends
    "allow_fallback": True,
    "cursor_key": "weekend_cursor",
}

# ---------------------------------------------------------------------------
# IR Config (qualification-gated pool)
# ---------------------------------------------------------------------------
IR_WEEKDAY_CONFIG = {
    "shift_names": ["IR1", "IR2"],
    "shifts_per_period": 2,
    "pool_filter": "participates_ir",
    "avoid_previous": False,
    "allow_fallback": True,
    "cursor_key": "ir_cursor",
}

# ---------------------------------------------------------------------------
# Constraint Weights (for optimization - soft vs hard)
# ---------------------------------------------------------------------------
CONSTRAINT_WEIGHTS = {
    "back_to_back_weekend": 100,   # Soft: minimize violations
    "workload_cv_target": 0.10,    # Target CV < 10%
    "m0_helper_weight": 0.25,      # M0 = 0.25 × M1
    "fte_weight": True,            # FTE-weighted assignment frequency
}

# ---------------------------------------------------------------------------
# Fairness Targets (from analysis docs)
# ---------------------------------------------------------------------------
FAIRNESS_TARGETS = {
    "cv_target": 0.10,           # < 10% coefficient of variation
    "max_deviation_from_mean": 0.20,  # ±20% from mean
    "weighted_hours": True,      # Track by weighted hours, not shift count
}


def load_roster(
    roster_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Load radiologist roster from roster_key.csv

    Expected columns: id, index, initials, name, email, role, exempt_dates,
    fte, participates_mercy, participates_ir, participates_weekend,
    subspecialties (optional)

    Returns:
        List of radiologist dicts with keys: id, index, initials, name,
        email, role, exempt_dates, fte, participates_mercy, participates_ir,
        participates_weekend, subspecialties
    """
    import pandas as pd

    path = roster_path or DEFAULT_ROSTER_PATH
    if not path.exists():
        raise FileNotFoundError(f"Roster file not found: {path}")

    df = pd.read_csv(path)

    people: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        person: Dict[str, Any] = {
            "id": int(row["id"]),
            "index": int(row["index"]),
            "initials": str(row["initials"]).strip(),
            "name": str(row["name"]).strip(),
            "email": str(row.get("email", "")),
            "role": str(row.get("role", "Radiologist")),
            "fte": float(row.get("fte", 1.0)),
            "participates_mercy": _parse_yes_no(row.get("participates_mercy", "yes")),
            "participates_ir": _parse_yes_no(row.get("participates_ir", "no")),
            "participates_weekend": _parse_yes_no(row.get("participates_weekend", "yes")),
        }

        # Exempt dates
        if "exempt_dates" in row and pd.notna(row["exempt_dates"]) and row["exempt_dates"]:
            person["exempt_dates"] = [d.strip() for d in str(row["exempt_dates"]).split(";") if d.strip()]
        else:
            person["exempt_dates"] = []

        # Subspecialties (comma or semicolon separated)
        if "subspecialties" in row and pd.notna(row["subspecialties"]) and row["subspecialties"]:
            raw = str(row["subspecialties"])
            person["subspecialties"] = [
                s.strip() for s in raw.replace(";", ",").split(",") if s.strip()
            ]
        else:
            person["subspecialties"] = []

        people.append(person)

    # Validate indices are contiguous
    indices = sorted([p["index"] for p in people])
    if indices != list(range(len(people))):
        raise ValueError(
            f"Roster indices must be contiguous 0..{len(people)-1}. Found: {indices}"
        )

    return people


def _parse_yes_no(val: Any) -> bool:
    """Parse yes/no, 1/0, true/false to bool"""
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("yes", "1", "true", "y"):
        return True
    if s in ("no", "0", "false", "n", ""):
        return False
    return True  # Default to yes for unknown values


def load_vacation_map(
    vacation_path: Optional[Path] = None,
) -> Dict[str, List[str]]:
    """
    Load vacation map from vacation_map.csv

    Expected columns: date, unavailable_staff (semicolon-separated names)

    Returns:
        Dict mapping date strings (YYYY-MM-DD) to list of unavailable staff names
    """
    import pandas as pd

    path = vacation_path or DEFAULT_VACATION_PATH
    if not path.exists():
        return {}

    df = pd.read_csv(path)
    vacation_map: Dict[str, List[str]] = {}
    for _, row in df.iterrows():
        date_str = str(row["date"]).strip()
        if pd.notna(row.get("unavailable_staff")) and row["unavailable_staff"]:
            staff_list = [s.strip() for s in str(row["unavailable_staff"]).split(";") if s.strip()]
            vacation_map[date_str] = staff_list
        else:
            vacation_map[date_str] = []
    return vacation_map


def load_cursor_state(cursor_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load cursor positions from cursor_state.json

    Returns:
        Dict with weekday_cursor, weekend_cursor, ir_cursor, last_updated
    """
    path = cursor_path or DEFAULT_CURSOR_PATH
    if not path.exists():
        return {
            "weekday_cursor": 0,
            "weekend_cursor": 0,
            "ir_cursor": 0,
            "last_updated": None,
        }

    with open(path) as f:
        data = json.load(f)
    return {
        "weekday_cursor": data.get("weekday_cursor", 0),
        "weekend_cursor": data.get("weekend_cursor", 0),
        "ir_cursor": data.get("ir_cursor", 0),
        "last_updated": data.get("last_updated"),
    }


def save_cursor_state(
    state: Dict[str, Any],
    cursor_path: Optional[Path] = None,
) -> None:
    """Persist cursor positions to cursor_state.json"""
    path = cursor_path or DEFAULT_CURSOR_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


# Aliases for shift names used in scheduling
SHIFT_WEIGHT_ALIASES: Dict[str, str] = {
    "M0 WEEKEND": "M0_WEEKEND",
    "DX-CALL": "LP",
    "LP": "LP",
}


def get_shift_weight(shift_name: str) -> float:
    """Get weight for a shift by name (M0=0.25, M1=1.0, etc.)"""
    key = shift_name.upper().replace(" ", "_").strip()
    if key in SHIFT_WEIGHT_ALIASES:
        key = SHIFT_WEIGHT_ALIASES[key]
    if key in DEFAULT_SHIFT_DEFINITIONS:
        return DEFAULT_SHIFT_DEFINITIONS[key]["weight"]
    # Fallback: partial match
    for k, v in DEFAULT_SHIFT_DEFINITIONS.items():
        if k in key or key in k:
            return v["weight"]
    return 1.0  # Default


def filter_pool(
    people: List[Dict[str, Any]],
    pool_filter: str,
) -> List[Dict[str, Any]]:
    """
    Filter roster by pool membership (mercy, ir, weekend)

    Args:
        people: Full roster
        pool_filter: Key in person dict, e.g. 'participates_mercy'

    Returns:
        Filtered list, preserving index order for cursor math
    """
    return [p for p in people if p.get(pool_filter, False)]


def get_config() -> Dict[str, Any]:
    """Return full configuration dict for external use"""
    return {
        "shift_definitions": DEFAULT_SHIFT_DEFINITIONS.copy(),
        "inpatient_weekday": INPATIENT_WEEKDAY_CONFIG.copy(),
        "inpatient_weekend": INPATIENT_WEEKEND_CONFIG.copy(),
        "ir_weekday": IR_WEEKDAY_CONFIG.copy(),
        "constraint_weights": CONSTRAINT_WEIGHTS.copy(),
        "fairness_targets": FAIRNESS_TARGETS.copy(),
    }


if __name__ == "__main__":
    # Quick validation
    roster = load_roster()
    print(f"Loaded {len(roster)} radiologists")
    vacation = load_vacation_map()
    print(f"Vacation map: {len(vacation)} dates")
    cursors = load_cursor_state()
    print(f"Cursors: {cursors}")
    mercy = filter_pool(roster, "participates_mercy")
    print(f"Mercy pool: {len(mercy)}")
