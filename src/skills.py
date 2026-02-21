"""
skills.py — Subspecialty & Skill Matching

Derives the required-skill set for each shift from SHIFT_DEFINITIONS.
Uses regex-based task name normalization (normalize_task_name) so raw
QGenda strings are mapped before checking qualifications.
"""

from typing import Any, Dict, List, Optional, Set
from src.schedule_config import SHIFT_DEFINITIONS, normalize_task_name


# ---------------------------------------------------------------------------
# Build shift→required-skills from SHIFT_DEFINITIONS (single source of truth)
# ---------------------------------------------------------------------------
SHIFT_SUBSPECIALTY_MAP: Dict[str, Set[str]] = {}
for _code, _def in SHIFT_DEFINITIONS.items():
    req = _def.get("requires")
    if req:
        SHIFT_SUBSPECIALTY_MAP[_code] = {req}

# Fixed / concurrent subspecialty shifts — not rotation-engine managed
FIXED_ASSIGNMENT_SHIFTS: Set[str] = {"Skull-Base", "Cardiac", "O'Toole"}

# IR rotational shifts
ROTATIONAL_SUBSPECIALTY_SHIFTS: Set[str] = {"IR-1", "IR-2", "IR-CALL", "PVH-IR"}

# Non-rotation outpatient shifts (suppress warnings at input-validation time)
OUTPATIENT_ONLY_SHIFTS: Set[str] = {
    "Remote-MRI", "Remote-PET", "Remote-Breast",
    "Wash-MRI", "Wash-Breast", "Wash-Gen",
    "Poway-MRI", "Poway-PET", "Poway-Gen",
    "Enc-MRI", "Enc-Breast", "Enc-Gen",
    "NC-Gen", "NC-PET", "NC-Breast", "NC-MRI",
    "Wknd-MRI", "Wknd-PET",
    "O'Toole",
}


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------

def get_qualified_staff(
    roster: List[Dict[str, Any]],
    required_subspecialties: Set[str],
) -> List[Dict[str, Any]]:
    """Filter roster to radiologists with ALL required subspecialty tags."""
    if not required_subspecialties:
        return roster
    required_lower = {r.lower() for r in required_subspecialties}
    return [
        p for p in roster
        if required_lower.issubset(
            {s.lower().strip() for s in p.get("subspecialties", [])}
        )
    ]


def check_shift_qualification(person: Dict[str, Any], shift_name: str) -> bool:
    """
    Check if a radiologist is qualified for a given shift.
    Accepts both engine codes (e.g. 'Remote-MRI') and raw QGenda strings.
    """
    code = normalize_task_name(shift_name)
    required = SHIFT_SUBSPECIALTY_MAP.get(code, set())
    if not required:
        return True
    specs = {s.lower().strip() for s in person.get("subspecialties", [])}
    return {r.lower() for r in required}.issubset(specs)


def get_pool_for_shift(
    roster: List[Dict[str, Any]],
    shift_name: str,
    pool_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get eligible pool for a shift: pool membership filter + subspecialty gate."""
    pool = roster
    if pool_filter:
        pool = [p for p in pool if p.get(pool_filter, False)]
    code = normalize_task_name(shift_name)
    required = SHIFT_SUBSPECIALTY_MAP.get(code, set())
    if required:
        pool = get_qualified_staff(pool, required)
    return pool


def is_fixed_assignment(shift_name: str) -> bool:
    return normalize_task_name(shift_name) in FIXED_ASSIGNMENT_SHIFTS


def is_rotational_subspecialty(shift_name: str) -> bool:
    return normalize_task_name(shift_name) in ROTATIONAL_SUBSPECIALTY_SHIFTS


def get_subspecialty_summary(roster: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Return {tag: [name, ...]} map for roster audit."""
    summary: Dict[str, List[str]] = {}
    for p in roster:
        for spec in p.get("subspecialties", []):
            tag = spec.strip()
            summary.setdefault(tag, []).append(p["name"])
    return summary


def validate_shift_coverage(
    roster: List[Dict[str, Any]],
    shifts_to_check: Optional[List[str]] = None,
) -> List[str]:
    """
    Check that every rotation-managed shift has ≥1 qualified radiologist.
    Outpatient-only and concurrent-fixed shifts are skipped.
    """
    if shifts_to_check is None:
        shifts_to_check = list(SHIFT_SUBSPECIALTY_MAP.keys())

    warnings = []
    skip = OUTPATIENT_ONLY_SHIFTS | FIXED_ASSIGNMENT_SHIFTS
    for shift in shifts_to_check:
        if shift in skip:
            continue
        required = SHIFT_SUBSPECIALTY_MAP.get(shift, set())
        if not required:
            continue
        qualified = get_qualified_staff(roster, required)
        if not qualified:
            warnings.append(
                f"Shift '{shift}' requires {required} — NO qualified radiologist"
            )
        elif len(qualified) < 2 and shift in ROTATIONAL_SUBSPECIALTY_SHIFTS:
            warnings.append(
                f"Rotational shift '{shift}' has only {len(qualified)} qualified "
                f"({qualified[0]['name']}) — need ≥2 for fair rotation"
            )
    return warnings
