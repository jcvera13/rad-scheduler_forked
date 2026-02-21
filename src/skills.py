"""
skills.py — Subspecialty / Skill Matching for Radiology Scheduling

Functions:
  - Tag each radiologist with subspecialty qualifications
  - Enforce that qualified staff fill subspecialty-designated shifts
  - Distinguish fixed assignments (Skull Base, Cardiac, O'Toole) from
    rotational subspecialty slots (IR-1, IR-2)

Subspecialty tags (from roster_key.csv and QGenda data):
  ir, neuro, nm, MRI, PET, MG, Gen, cardiac, skull_base, Proc

See: config/roster_key.csv, src/schedule_config.FIXED_SUBSPECIALTY_ASSIGNMENTS
"""

from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Shift → required subspecialty tags
# Uses real QGenda task names AND engine short codes
# ---------------------------------------------------------------------------
SHIFT_SUBSPECIALTY_MAP: Dict[str, Set[str]] = {
    # IR shifts — must have 'ir' tag
    "IR-1":           {"ir"},
    "IR-2":           {"ir"},
    "IR-CALL":        {"ir"},
    "IR-CALL (RMG)":  {"ir"},
    "PVH-IR":         {"ir"},
    "PVH IR":         {"ir"},

    # Subspecialty fixed shifts
    "Skull Base":     {"neuro"},        # neuro/skull_base required
    "Cardiac":        {"cardiac"},
    "O'Toole":        {"mg"},           # Mammography
    "NM Brain":       {"nm"},

    # Rotational but subspecialty-preferred (soft gate — qualified preferred)
    "Remote MRI":     {"mri"},
    "Remote PET":     {"pet"},
    "Remote Breast":  {"mg"},
    "Washington MRI": {"mri"},
    "Poway PET":      {"pet"},
}

# Shifts that are FIXED to specific named radiologists (not rotation engine)
FIXED_ASSIGNMENT_SHIFTS: Set[str] = {
    "Skull Base",
    "Cardiac",
    "O'Toole",
}

# Shifts that are ROTATIONAL among qualified pool
ROTATIONAL_SUBSPECIALTY_SHIFTS: Set[str] = {
    "IR-1",
    "IR-2",
    "IR-CALL",
    "PVH-IR",
}


# ---------------------------------------------------------------------------
# Query Functions
# ---------------------------------------------------------------------------

def get_qualified_staff(
    roster: List[Dict[str, Any]],
    required_subspecialties: Set[str],
) -> List[Dict[str, Any]]:
    """
    Filter roster to radiologists with ALL required subspecialty tags.

    Args:
        roster: Full roster list (each dict has 'subspecialties': List[str])
        required_subspecialties: Set of required tags, e.g. {'ir'}

    Returns:
        Filtered list (preserves original order for cursor fairness)
    """
    if not required_subspecialties:
        return roster
    qualified = []
    for p in roster:
        specs = {s.lower().strip() for s in p.get("subspecialties", [])}
        if required_subspecialties.issubset(specs):
            qualified.append(p)
    return qualified


def check_shift_qualification(
    person: Dict[str, Any],
    shift_name: str,
) -> bool:
    """
    Check if a radiologist is qualified for a given shift.

    Returns True if shift has no subspecialty requirement,
    or if person has all required tags.
    """
    required = SHIFT_SUBSPECIALTY_MAP.get(shift_name, set())
    if not required:
        return True
    person_specs = {s.lower().strip() for s in person.get("subspecialties", [])}
    return required.issubset(person_specs)


def get_pool_for_shift(
    roster: List[Dict[str, Any]],
    shift_name: str,
    pool_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get the eligible pool for a shift:
      1. Apply pool membership filter (e.g. participates_ir)
      2. Apply subspecialty gate

    Args:
        roster:      Full roster
        shift_name:  QGenda task name or engine shift code
        pool_filter: Optional roster dict key, e.g. 'participates_mercy'

    Returns:
        Filtered list, original order preserved
    """
    pool = roster
    if pool_filter:
        pool = [p for p in pool if p.get(pool_filter, False)]
    required = SHIFT_SUBSPECIALTY_MAP.get(shift_name, set())
    if required:
        pool = get_qualified_staff(pool, required)
    return pool


def is_fixed_assignment(shift_name: str) -> bool:
    """True if shift uses fixed (non-rotation) assignment."""
    return shift_name in FIXED_ASSIGNMENT_SHIFTS


def is_rotational_subspecialty(shift_name: str) -> bool:
    """True if shift rotates among qualified subspecialty pool."""
    return shift_name in ROTATIONAL_SUBSPECIALTY_SHIFTS


def get_subspecialty_summary(roster: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Return a dict of subspecialty tag → list of radiologist names for audit.

    Useful for validating roster coverage and printing skill matrix.
    """
    summary: Dict[str, List[str]] = {}
    for p in roster:
        for spec in p.get("subspecialties", []):
            tag = spec.strip()
            if tag not in summary:
                summary[tag] = []
            summary[tag].append(p["name"])
    return summary


def validate_shift_coverage(
    roster: List[Dict[str, Any]],
    shifts_to_check: Optional[List[str]] = None,
) -> List[str]:
    """
    Validate that every shift with a subspecialty requirement has ≥1
    qualified radiologist in the roster.

    Args:
        roster:          Full roster
        shifts_to_check: Shift names to check (defaults to all in map)

    Returns:
        List of warning strings (empty = all OK)
    """
    if shifts_to_check is None:
        shifts_to_check = list(SHIFT_SUBSPECIALTY_MAP.keys())

    warnings = []
    for shift in shifts_to_check:
        required = SHIFT_SUBSPECIALTY_MAP.get(shift, set())
        if not required:
            continue
        qualified = get_qualified_staff(roster, required)
        if not qualified:
            warnings.append(
                f"Shift '{shift}' requires {required} but NO qualified radiologist in roster"
            )
        elif len(qualified) < 2 and shift in ROTATIONAL_SUBSPECIALTY_SHIFTS:
            warnings.append(
                f"Rotational shift '{shift}' has only {len(qualified)} qualified radiologist "
                f"({qualified[0]['name']}) — need ≥2 for fair rotation"
            )
    return warnings
