"""
config.py — Configuration Module for Fair Radiology Scheduling Engine

Loads roster, vacation map, and cursor state.
Re-exports schedule_config constants for backwards compatibility.

Key fix: subspecialties column in roster_key.csv uses comma-separated
unquoted values (e.g.  neuro,cardiac,nm,MRI,Gen).
Old format was space-separated quoted strings — now normalized.
"""

import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_ROSTER_PATH    = DEFAULT_CONFIG_DIR / "roster_key.csv"
DEFAULT_VACATION_PATH  = DEFAULT_CONFIG_DIR / "vacation_map.csv"
DEFAULT_CURSOR_PATH    = DEFAULT_CONFIG_DIR / "cursor_state.json"


# ---------------------------------------------------------------------------
# Re-export from schedule_config for backwards compatibility
# ---------------------------------------------------------------------------
from src.schedule_config import (    # noqa: E402
    SHIFT_DEFINITIONS as DEFAULT_SHIFT_DEFINITIONS,
    CONSTRAINT_WEIGHTS,
    FAIRNESS_TARGETS,
    SCHEDULING_BLOCKS,
    M3_CONFIG   as INPATIENT_WEEKDAY_CONFIG,   # backwards compat aliases
    WEEKEND_CONFIG as INPATIENT_WEEKEND_CONFIG,
    IR_WEEKDAY_CONFIG,
    normalize_task_name,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_yes_no(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("yes", "true", "1", "y")


def _parse_subspecialties(raw: Any) -> List[str]:
    """
    Robust parser for subspecialty strings.
    Handles:
      - comma-separated:  "ir,MRI,Gen"
      - semicolon-sep:    "ir;MRI;Gen"
      - space-sep quoted: '"ir" "MRI" "Gen"'  (old malformed CSV format)
      - single value:     "ir"
    Returns lowercase-stripped list.
    """
    if not raw or (isinstance(raw, float)):
        return []
    s = str(raw).strip()
    if not s:
        return []

    # Strip outer quotes if any
    s = s.strip('"').strip("'")

    # Replace space-separated quoted tokens: "ir" "MRI" → ir,MRI
    s = re.sub(r'"\s+"', ",", s)
    s = re.sub(r'"\s*', "", s)

    # Normalise delimiters to comma
    s = s.replace(";", ",").replace("|", ",")

    parts = [p.strip().strip('"').strip("'") for p in s.split(",")]
    return [p for p in parts if p]


# ---------------------------------------------------------------------------
# Roster loader
# ---------------------------------------------------------------------------

def load_roster(
    roster_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Load radiologist roster from roster_key.csv.

    Expected columns:
      id, index, initials, name, email, role, exempt_dates, fte,
      participates_mercy, participates_ir, participates_weekend,
      subspecialties, notes (optional)

    Returns sorted list of dicts (sorted by index).
    """
    import pandas as pd

    path = roster_path or DEFAULT_ROSTER_PATH
    if not path.exists():
        raise FileNotFoundError(f"Roster file not found: {path}")

    df = pd.read_csv(path)

    people: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        subspecs = _parse_subspecialties(row.get("subspecialties", ""))
        # participates_MRI / participates_PET: from column if present, else infer from subspecialties
        _participates_mri = row.get("participates_MRI")
        if _participates_mri is None or (isinstance(_participates_mri, float) and math.isnan(_participates_mri)):
            _participates_mri = any(
                s and (s.lower() in ("mri", "mri+proc")) for s in subspecs
            )
        else:
            _participates_mri = _parse_yes_no(_participates_mri)
        _participates_pet = row.get("participates_PET")
        if _participates_pet is None or (isinstance(_participates_pet, float) and math.isnan(_participates_pet)):
            _participates_pet = any(s and s.lower() == "pet" for s in subspecs)
        else:
            _participates_pet = _parse_yes_no(_participates_pet)

        person: Dict[str, Any] = {
            "id":                  int(row["id"]),
            "index":               int(row["index"]),
            "initials":            str(row["initials"]).strip(),
            "name":                str(row["name"]).strip(),
            "email":               str(row.get("email", "") or ""),
            "role":                str(row.get("role", "Radiologist")),
            "fte":                 float(row.get("fte", 1.0)),
            "participates_mercy":     _parse_yes_no(row.get("participates_mercy",     "yes")),
            "participates_ir":        _parse_yes_no(row.get("participates_ir",        "no")),
            "participates_weekend":   _parse_yes_no(row.get("participates_weekend",   "yes")),
            "participates_gen":       _parse_yes_no(row.get("participates_gen",       "yes")),
            "participates_outpatient":_parse_yes_no(row.get("participates_outpatient","yes")),
            "participates_mg":        _parse_yes_no(row.get("participates_mg",        "no")),
            "participates_MRI":       _participates_mri,
            "participates_PET":       _participates_pet,
            "subspecialties":         subspecs,
            "notes":                  str(row.get("notes", "") or ""),
        }

        # Parse exempt_dates (semicolon-separated YYYY-MM-DD)
        raw_exempt = row.get("exempt_dates", "")
        if raw_exempt and str(raw_exempt).strip() and str(raw_exempt) != "nan":
            person["exempt_dates"] = [
                d.strip() for d in str(raw_exempt).split(";") if d.strip()
            ]
        else:
            person["exempt_dates"] = []

        people.append(person)

    # Sort by index (ensures cursor math works correctly)
    people.sort(key=lambda p: p["index"])

    # Validate
    indices = [p["index"] for p in people]
    if indices != list(range(len(people))):
        raise ValueError(
            f"Roster indices must be 0..{len(people)-1}. Got: {indices}. "
            "Check roster_key.csv for gaps or duplicate index values."
        )

    logger.info(f"Loaded {len(people)} radiologists from {path}")
    return people


# ---------------------------------------------------------------------------
# Vacation map loader
# ---------------------------------------------------------------------------

def load_vacation_map(
    vacation_path: Optional[Path] = None,
) -> Dict[str, List[str]]:
    """
    Load vacation map from vacation_map.csv.

    Returns: {date_str: [unavailable_names]}
    """
    import pandas as pd

    path = vacation_path or DEFAULT_VACATION_PATH
    if not path.exists():
        logger.warning(f"Vacation map not found: {path}. Returning empty map.")
        return {}

    df = pd.read_csv(path)
    vacation_map: Dict[str, List[str]] = {}

    for _, row in df.iterrows():
        date_str = str(row["date"]).strip()
        raw_staff = row.get("unavailable_staff", "")
        if raw_staff and str(raw_staff).strip() and str(raw_staff) != "nan":
            names = [n.strip() for n in str(raw_staff).split(";") if n.strip()]
            vacation_map[date_str] = names
        else:
            vacation_map[date_str] = []

    logger.info(f"Loaded vacation map: {len(vacation_map)} dates from {path}")
    return vacation_map


# ---------------------------------------------------------------------------
# Cursor state
# ---------------------------------------------------------------------------

def load_cursor_state(
    cursor_path: Optional[Path] = None,
) -> Dict[str, float]:
    """Load cursor state from JSON. Returns empty dict if file missing."""
    path = cursor_path or DEFAULT_CURSOR_PATH
    if not path.exists():
        logger.warning(f"Cursor state not found: {path}. Starting from 0.")
        return {}
    with open(path) as f:
        data = json.load(f)
    # Remove metadata keys
    return {k: float(v) for k, v in data.items()
            if k not in ("last_updated", "notes") and isinstance(v, (int, float))}


def save_cursor_state(
    cursor_state: Dict[str, float],
    cursor_path: Optional[Path] = None,
) -> None:
    """Persist cursor state to JSON with metadata."""
    from datetime import date as _date
    path = cursor_path or DEFAULT_CURSOR_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {k: round(v, 4) for k, v in cursor_state.items()}
    data["last_updated"] = _date.today().isoformat()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Cursor state saved to {path}: {data}")


# ---------------------------------------------------------------------------
# Pool filter
# ---------------------------------------------------------------------------

def filter_pool(
    people: List[Dict[str, Any]],
    pool_filter: str,
) -> List[Dict[str, Any]]:
    """Filter roster by pool membership key (e.g. 'participates_mercy')."""
    return [p for p in people if p.get(pool_filter, False)]


# ---------------------------------------------------------------------------
# Shift weight lookup
# ---------------------------------------------------------------------------

SHIFT_WEIGHT_ALIASES: Dict[str, str] = {
    "MERCY_0": "M0", "MERCY_1": "M1", "MERCY_2": "M2", "MERCY_3": "M3",
    "IR1": "IR-1", "IR2": "IR-2",
}


def get_shift_weight(shift_name: str) -> float:
    """Return weight for a shift name (1.0 if unknown)."""
    key = shift_name.upper().replace(" ", "_").strip()
    if key in SHIFT_WEIGHT_ALIASES:
        key = SHIFT_WEIGHT_ALIASES[key]
    for k, v in DEFAULT_SHIFT_DEFINITIONS.items():
        if k.upper() == key:
            return v["weight"]
    return 1.0


# ---------------------------------------------------------------------------
# Full config dict
# ---------------------------------------------------------------------------

def get_config() -> Dict[str, Any]:
    return {
        "shift_definitions":   DEFAULT_SHIFT_DEFINITIONS.copy(),
        "inpatient_weekday":   INPATIENT_WEEKDAY_CONFIG.copy(),
        "inpatient_weekend":   INPATIENT_WEEKEND_CONFIG.copy(),
        "ir_weekday":          IR_WEEKDAY_CONFIG.copy(),
        "constraint_weights":  CONSTRAINT_WEIGHTS.copy(),
        "fairness_targets":    FAIRNESS_TARGETS.copy(),
        "scheduling_blocks":   SCHEDULING_BLOCKS,
    }


# ---------------------------------------------------------------------------
# Quick validation on import
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    roster = load_roster()
    print(f"Loaded {len(roster)} radiologists")
    for p in roster:
        specs = ", ".join(p["subspecialties"]) or "(none)"
        ir_flag = "✓ IR" if p["participates_ir"] else ""
        print(f"  [{p['index']:2d}] {p['initials']} {p['name']:<22} FTE={p['fte']} {ir_flag} | {specs}")

    vacation = load_vacation_map()
    print(f"\nVacation map: {len(vacation)} dates")

    cursors = load_cursor_state()
    print(f"Cursors: {cursors}")

    mercy_pool = filter_pool(roster, "participates_mercy")
    ir_pool    = filter_pool(roster, "participates_ir")
    print(f"\nMercy pool: {len(mercy_pool)} | IR pool: {len(ir_pool)}")
