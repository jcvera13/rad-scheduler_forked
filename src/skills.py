"""
Subspecialty / Skill Matching for Radiology Scheduling

Tags each radiologist with subspecialty qualifications (IR, Neuro, MSK, Cardiac, Body, etc.)
Enforces that qualified staff fill subspecialty-designated shifts.
Supports fixed vs rotational subspecialty assignments.

See docs/analysis/subspecialty_analysis.txt, SHIPMG_Radiology_Qgenda_Guide
"""

from typing import Any, Dict, List, Optional, Set


# Subspecialty requirements for shift types (from SHIPMG guide)
SHIFT_SUBSPECIALTY_MAP = {
    "IR1": {"ir"},
    "IR2": {"ir"},
    "O'Toole": {"MG", "mammography"},
    "Skull Base": {"neuro", "skull_base"},
    "Cardiac": {"cardiac"},
    "NM Brain": {"nm", "neuro"},
}

# Core specialty names from QGenda
CORE_SPECIALTIES = {"Mercy", "IR", "MG", "MRI", "PET", "Gen"}


def get_qualified_staff(
    roster: List[Dict[str, Any]],
    required_subspecialties: Set[str],
) -> List[Dict[str, Any]]:
    """
    Filter roster to those qualified for the given subspecialty set.

    Args:
        roster: List of radiologist dicts with 'subspecialties' list
        required_subspecialties: Set of required tags (e.g. {'ir'})

    Returns:
        Filtered list of qualified radiologists
    """
    qualified = []
    for p in roster:
        specs = set(s.lower().strip() for s in p.get("subspecialties", []))
        if required_subspecialties.issubset(specs) or not required_subspecialties:
            qualified.append(p)
    return qualified


def check_shift_qualification(
    person: Dict[str, Any],
    shift_name: str,
) -> bool:
    """Check if person is qualified for shift (subspecialty match)"""
    req = SHIFT_SUBSPECIALTY_MAP.get(shift_name, set())
    if not req:
        return True
    specs = set(s.lower().strip() for s in person.get("subspecialties", []))
    return bool(req & specs)


def get_pool_for_shift(
    roster: List[Dict[str, Any]],
    shift_name: str,
    pool_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get roster filtered by pool membership and subspecialty qualification.

    Args:
        roster: Full roster
        shift_name: e.g. 'IR1', 'M0', 'Skull Base'
        pool_filter: Optional key like 'participates_mercy'

    Returns:
        Filtered list
    """
    result = roster
    if pool_filter:
        result = [p for p in result if p.get(pool_filter, False)]
    req = SHIFT_SUBSPECIALTY_MAP.get(shift_name, set())
    if req:
        result = get_qualified_staff(result, req)
    return result
