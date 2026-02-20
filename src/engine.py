"""
Fair Radiology Scheduling Engine

Implements the infinite modulo stream / cursor-based fairness algorithm
from docs/architecture.md with:
- Vacation-aware scheduling (skipped staff retain rotation position)
- Back-to-back weekend avoidance (strict + fallback modes)
- FTE-weighted assignment frequency
- Weighted cursor advancement (M0=0.25×, M1=1.0×, M2=1.0×, M3=0.75×)

See docs/architecture.md, docs/analysis/comprehensive_analysis.md
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple, Union

from .config import (
    DEFAULT_SHIFT_DEFINITIONS,
    get_shift_weight,
    load_roster,
    load_vacation_map,
)

logger = logging.getLogger(__name__)


def schedule_period(
    people: List[Dict[str, Any]],
    dates: List[date],
    shifts_per_period: int,
    shift_names: Optional[List[str]] = None,
    shift_weights: Optional[Dict[str, float]] = None,
    cursor: Union[int, float] = 0,
    vacation_map: Optional[Dict[str, List[str]]] = None,
    avoid_previous: bool = False,
    allow_fallback: bool = True,
    use_weighted_cursor: bool = True,
) -> Tuple[Dict[str, List[Tuple[str, str]]], float]:
    """
    Schedule shifts using infinite modulo stream with optional weighted cursor.

    Args:
        people: List of radiologist dicts (must have 'name', 'index'; order defines rotation)
        dates: List of dates to schedule (for weekend, use Saturday date per period)
        shifts_per_period: Number of shifts per date/period
        shift_names: Optional list like ['M0','M1','M2','M3'] for weighted fairness
        shift_weights: Optional {shift_name: weight}; defaults from config
        cursor: Starting stream position (int for simple, float for weighted)
        vacation_map: Dict[date_str, List[unavailable_names]]
        avoid_previous: If True, avoid same people as previous period (back-to-back weekend)
        allow_fallback: If True, relax avoid_previous when insufficient staff
        use_weighted_cursor: If True, advance cursor by shift weight (M0=0.25, etc.)

    Returns:
        Tuple of:
          - schedule: Dict[date_str, List[(shift_name, person_name)]]
          - final_cursor: float (or int if not weighted)
    """
    if vacation_map is None:
        vacation_map = {}

    N = len(people)
    name_list = [p["name"] for p in people]
    if N == 0:
        raise ValueError("People list cannot be empty")

    # Build shift weights
    if shift_names is None:
        shift_names = [f"Shift_{i}" for i in range(shifts_per_period)]
    weights = shift_weights or {}
    for name in shift_names:
        if name not in weights:
            weights[name] = get_shift_weight(name) if use_weighted_cursor else 1.0

    schedule: Dict[str, List[Tuple[str, str]]] = {}
    stream_pos = float(cursor)
    last_assigned: set = set()

    for d in dates:
        key = d.strftime("%Y-%m-%d")
        unavailable = set(vacation_map.get(key, []))
        if avoid_previous and last_assigned:
            unavailable |= last_assigned

        assigned: List[Tuple[str, str]] = []
        shift_idx = 0

        while len(assigned) < shifts_per_period:
            shift_name = shift_names[shift_idx % len(shift_names)]
            weight = weights.get(shift_name, 1.0)

            probe = int(stream_pos)
            tries = 0
            chosen = None
            max_tries = N * 2

            while tries < max_tries:
                candidate = name_list[probe % N]
                if candidate not in unavailable and candidate not in [a[1] for a in assigned]:
                    chosen = candidate
                    break
                probe += 1
                tries += 1

            if chosen is None and allow_fallback and avoid_previous and last_assigned:
                # Retry without back-to-back restriction
                logger.warning(f"Insufficient staff for {key} shift {shift_name}, relaxing back-to-back")
                unavailable -= last_assigned
                probe = int(stream_pos)
                tries = 0
                while tries < max_tries:
                    candidate = name_list[probe % N]
                    if candidate not in unavailable and candidate not in [a[1] for a in assigned]:
                        chosen = candidate
                        break
                    probe += 1
                    tries += 1

            if chosen is None:
                raise RuntimeError(
                    f"Insufficient staff for {key} shift {shift_name}. "
                    f"Unavailable: {unavailable}, Assigned: {assigned}"
                )

            assigned.append((shift_name, chosen))
            stream_pos += weight
            shift_idx += 1

        last_assigned = {a[1] for a in assigned}
        schedule[key] = assigned
        logger.info(f"Scheduled {key}: {assigned}")

    return schedule, stream_pos


def schedule_weekday_mercy(
    people: List[Dict[str, Any]],
    dates: List[date],
    cursor: float = 0,
    vacation_map: Optional[Dict[str, List[str]]] = None,
) -> Tuple[Dict[str, List[Tuple[str, str]]], float]:
    """Convenience: Schedule inpatient weekday (M0, M1, M2, M3)."""
    return schedule_period(
        people=people,
        dates=dates,
        shifts_per_period=4,
        shift_names=["M0", "M1", "M2", "M3"],
        cursor=cursor,
        vacation_map=vacation_map,
        avoid_previous=False,
        allow_fallback=True,
        use_weighted_cursor=True,
    )


def schedule_weekend_mercy(
    people: List[Dict[str, Any]],
    saturday_dates: List[date],
    cursor: float = 0,
    vacation_map: Optional[Dict[str, List[str]]] = None,
) -> Tuple[Dict[str, List[Tuple[str, str]]], float]:
    """
    Schedule inpatient weekend (M0 Weekend, EP, Dx-CALL).
    Uses Saturday date as period key; avoid_previous=True for back-to-back prevention.
    """
    # Include both Sat and Sun in vacation check for each weekend
    expanded_vacation: Dict[str, List[str]] = {}
    if vacation_map:
        for sat in saturday_dates:
            sat_str = sat.strftime("%Y-%m-%d")
            from datetime import timedelta
            sun = sat + timedelta(days=1)
            sun_str = sun.strftime("%Y-%m-%d")
            unavailable = set(vacation_map.get(sat_str, []) + vacation_map.get(sun_str, []))
            expanded_vacation[sat_str] = list(unavailable)

    return schedule_period(
        people=people,
        dates=saturday_dates,
        shifts_per_period=3,
        shift_names=["M0 Weekend", "EP", "Dx-CALL"],
        cursor=cursor,
        vacation_map=expanded_vacation or vacation_map,
        avoid_previous=True,
        allow_fallback=True,
        use_weighted_cursor=True,
    )


def schedule_ir_weekday(
    people: List[Dict[str, Any]],
    dates: List[date],
    cursor: float = 0,
    vacation_map: Optional[Dict[str, List[str]]] = None,
) -> Tuple[Dict[str, List[Tuple[str, str]]], float]:
    """Schedule IR weekday shifts (IR1, IR2). Pool must be IR-qualified."""
    return schedule_period(
        people=people,
        dates=dates,
        shifts_per_period=2,
        shift_names=["IR1", "IR2"],
        cursor=cursor,
        vacation_map=vacation_map,
        avoid_previous=False,
        allow_fallback=True,
        use_weighted_cursor=True,
    )


def calculate_fairness_metrics(
    schedule: Dict[str, List[Tuple[str, str]]],
    people: List[Dict[str, Any]],
    shift_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Calculate fairness metrics: counts, weighted counts, mean, std, CV.

    Returns dict with: mean, std, cv, min, max, counts (raw), weighted_counts
    """
    import math

    if shift_weights is None:
        shift_weights = {}
    for k, v in DEFAULT_SHIFT_DEFINITIONS.items():
        if k not in shift_weights:
            shift_weights[k] = v["weight"]

    raw_counts: Dict[str, int] = {p["name"]: 0 for p in people}
    weighted_counts: Dict[str, float] = {p["name"]: 0.0 for p in people}

    for _date, assignments in schedule.items():
        for shift_name, person_name in assignments:
            if person_name in raw_counts:
                raw_counts[person_name] += 1
                w = shift_weights.get(shift_name, get_shift_weight(shift_name))
                weighted_counts[person_name] += w

    values = list(weighted_counts.values())
    mean_val = sum(values) / len(values) if values else 0
    variance = sum((v - mean_val) ** 2 for v in values) / len(values) if values else 0
    std_val = math.sqrt(variance)
    cv = (std_val / mean_val * 100) if mean_val > 0 else 0

    return {
        "mean": mean_val,
        "std": std_val,
        "cv": cv,
        "min": min(values) if values else 0,
        "max": max(values) if values else 0,
        "counts": raw_counts,
        "weighted_counts": weighted_counts,
    }


# Re-export for backwards compatibility with scheduling_engine
def load_roster_from_file(path: str) -> List[Dict[str, Any]]:
    """Load roster from CSV path."""
    from pathlib import Path
    return load_roster(Path(path))


def load_vacation_from_file(path: str) -> Dict[str, List[str]]:
    """Load vacation map from CSV path."""
    from pathlib import Path
    return load_vacation_map(Path(path))
