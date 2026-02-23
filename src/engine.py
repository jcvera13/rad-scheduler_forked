"""
engine.py — Fair Radiology Scheduling Engine

Core algorithm: infinite modulo stream / cursor-based fairness.
Supports:
  - Weighted cursor (M0=0.25×, M1=1.0×, M3=0.75×, etc.)
  - Block scheduling (schedule IR first, M3 second, Off marks, etc.)
  - Interactive mode: step through blocks with user confirmation
  - FTE-weighted assignment frequency
  - Vacation-aware (skipped staff retain position in stream)
  - Back-to-back weekend avoidance (strict + fallback)
  - 2-week cycle (NC / KM weeks) via nc_week_anchor + week_type on blocks
  - Per-week-type allowed_weekdays (allowed_weekdays_nc / allowed_weekdays_km)
  - IR-CALL Fri+Sat+Sun mirror (mirror_weekend flag on block config)

Algorithm:
  People = [A, B, C, D, ...] ordered by index.
  Cursor = float (weighted).
  For each slot:
    pos = floor(cursor) % N
    Advance to next non-vacation, non-already-assigned person.
    cursor += shift_weight

See docs/architecture.md, src/schedule_config.py
"""

import logging
import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Type alias
Schedule = Dict[str, List[Tuple[str, str]]]   # date_str → [(shift, name)]

# ---------------------------------------------------------------------------
# Week-parity helper
# ---------------------------------------------------------------------------

def _get_week_type(d: date, nc_anchor: Optional[date]) -> Optional[str]:
    """
    Return 'nc' or 'km' for the given date, relative to the NC-week anchor.

    nc_anchor: any Monday (or date) that falls in a known NC week.
               Default anchor used in dry_run: 2026-03-02 (first Mon of real schedule).
    Returns None if nc_anchor is None (parity disabled).
    """
    if nc_anchor is None:
        return None
    anchor_monday = nc_anchor - timedelta(days=nc_anchor.weekday())
    this_monday   = d - timedelta(days=d.weekday())
    weeks_diff    = (this_monday - anchor_monday).days // 7
    return "nc" if weeks_diff % 2 == 0 else "km"


# ---------------------------------------------------------------------------
# Core: single slot assignment
# ---------------------------------------------------------------------------

def _pick_next(
    people: List[Dict[str, Any]],
    cursor: float,
    already_assigned_today: set,
    unavailable: set,
    previous_period: Optional[set] = None,
    allow_fallback: bool = True,
) -> Tuple[Optional[Dict[str, Any]], float]:
    """
    Pick the next eligible person from the stream starting at cursor.

    Returns (person_dict, cursor_advanced_to) or (None, cursor) if no one available.
    Tries strict mode (avoids previous_period) then falls back if allow_fallback.
    """
    N = len(people)
    if N == 0:
        return None, cursor

    def _scan(avoid_prev: bool) -> Optional[Tuple[Dict, float]]:
        start_pos = int(math.floor(cursor)) % N
        for offset in range(N):
            pos = (start_pos + offset) % N
            person = people[pos]
            name = person["name"]
            if name in already_assigned_today:
                continue
            if name in unavailable:
                continue
            if avoid_prev and previous_period and name in previous_period:
                continue
            # Found eligible
            new_cursor = cursor + offset  # cursor advances to this person
            return person, new_cursor
        return None

    result = _scan(avoid_prev=bool(previous_period))
    if result is None and allow_fallback and previous_period:
        logger.debug("Back-to-back fallback triggered")
        result = _scan(avoid_prev=False)

    if result is None:
        logger.warning(f"No eligible person found at cursor={cursor}, unavailable={unavailable}")
        return None, cursor

    return result[0], result[1]


# ---------------------------------------------------------------------------
# Core: schedule_period (single rotation pool, single block)
# ---------------------------------------------------------------------------

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
    fte_weight: bool = False,
) -> Tuple[Schedule, float]:
    """
    Schedule shifts for a list of dates using the infinite modulo stream.

    Args:
        people:              Roster list, each dict has 'name', 'index', optional 'fte'.
                             ORDER defines rotation sequence.
        dates:               Dates to schedule (for weekends, use Saturday date).
        shifts_per_period:   Number of slots per date/period.
        shift_names:         Names for each slot, e.g. ['M0','M1','M2','M3'].
                             Defaults to ['S0','S1',...].
        shift_weights:       Weight per shift name (cursor advance). Default 1.0.
        cursor:              Starting float cursor position in stream.
        vacation_map:        {date_str: [unavailable_names]}.
        avoid_previous:      If True, avoid last period's assigned names (back-to-back).
        allow_fallback:      If True, relax avoid_previous when pool too small.
        use_weighted_cursor: If True, advance cursor by shift weight; else by 1.0.
        fte_weight:          Reserved: FTE-proportional scheduling (future).

    Returns:
        (schedule, final_cursor)
        schedule: {date_str: [(shift_name, person_name), ...]}
    """
    if vacation_map is None:
        vacation_map = {}
    if shift_weights is None:
        shift_weights = {}

    N = len(people)
    if N == 0:
        raise ValueError("people list is empty — check pool filter")

    # Sort by roster index to ensure consistent rotation order regardless of
    # how the pool was filtered. Cursor math uses array position (0..N-1).
    people = sorted(people, key=lambda p: p["index"])

    # Build shift name list
    if shift_names is None:
        shift_names = [f"S{i}" for i in range(shifts_per_period)]
    if len(shift_names) < shifts_per_period:
        shift_names = (shift_names * math.ceil(shifts_per_period / len(shift_names)))[:shifts_per_period]

    schedule: Schedule = {}
    float_cursor = float(cursor)
    previous_names: Optional[set] = None

    for day in dates:
        date_str = day.isoformat()
        unavailable = set(vacation_map.get(date_str, []))
        assigned_today: set = set()
        day_assignments: List[Tuple[str, str]] = []

        for slot_idx in range(shifts_per_period):
            shift = shift_names[slot_idx % len(shift_names)]
            weight = shift_weights.get(shift, 1.0) if use_weighted_cursor else 1.0

            person, new_cursor = _pick_next(
                people=people,
                cursor=float_cursor,
                already_assigned_today=assigned_today,
                unavailable=unavailable,
                previous_period=previous_names if avoid_previous else None,
                allow_fallback=allow_fallback,
            )

            if person is None:
                logger.error(f"Could not fill {shift} on {date_str}")
                day_assignments.append((shift, "UNFILLED"))
                float_cursor += weight
                continue

            # Advance cursor past this person + weight
            advance = (new_cursor - float_cursor) + weight
            float_cursor += advance

            assigned_today.add(person["name"])
            day_assignments.append((shift, person["name"]))
            logger.debug(f"{date_str} {shift} → {person['name']} (cursor={float_cursor:.2f})")

        schedule[date_str] = day_assignments
        previous_names = assigned_today  # for next period back-to-back check

    return schedule, float_cursor


# ---------------------------------------------------------------------------
# Convenience wrappers (weekday / weekend / IR)
# ---------------------------------------------------------------------------

def schedule_weekday_mercy(
    people: List[Dict[str, Any]],
    dates: List[date],
    cursor: float = 0.0,
    vacation_map: Optional[Dict[str, List[str]]] = None,
    shift_names: Optional[List[str]] = None,
    shift_weights: Optional[Dict[str, float]] = None,
) -> Tuple[Schedule, float]:
    """Mercy weekday M0/M1/M2/M3 with weighted cursor."""
    _shift_names = shift_names or ["M0", "M1", "M2", "M3"]
    _weights = shift_weights or {"M0": 0.25, "M1": 1.00, "M2": 1.00, "M3": 0.75}
    return schedule_period(
        people=people,
        dates=dates,
        shifts_per_period=len(_shift_names),
        shift_names=_shift_names,
        shift_weights=_weights,
        cursor=cursor,
        vacation_map=vacation_map,
        avoid_previous=False,
        allow_fallback=True,
        use_weighted_cursor=True,
    )


def schedule_weekend_mercy(
    people: List[Dict[str, Any]],
    dates: List[date],
    cursor: float = 0.0,
    vacation_map: Optional[Dict[str, List[str]]] = None,
) -> Tuple[Schedule, float]:
    """Weekend M0_WEEKEND/EP/Dx-CALL with back-to-back avoidance."""
    return schedule_period(
        people=people,
        dates=dates,
        shifts_per_period=3,
        shift_names=["M0_WEEKEND", "EP", "Dx-CALL"],
        shift_weights={"M0_WEEKEND": 0.25, "EP": 0.81, "Dx-CALL": 1.00},
        cursor=cursor,
        vacation_map=vacation_map,
        avoid_previous=True,
        allow_fallback=True,
        use_weighted_cursor=True,
    )


def schedule_ir_weekday(
    people: List[Dict[str, Any]],
    dates: List[date],
    cursor: float = 0.0,
    vacation_map: Optional[Dict[str, List[str]]] = None,
) -> Tuple[Schedule, float]:
    """IR weekday IR-1/IR-2. Pool must be IR-qualified (4 radiologists)."""
    if len(people) < 2:
        raise ValueError(f"IR pool has only {len(people)} person(s); need ≥2 for IR-1/IR-2.")
    return schedule_period(
        people=people,
        dates=dates,
        shifts_per_period=2,
        shift_names=["IR-1", "IR-2"],
        shift_weights={"IR-1": 1.00, "IR-2": 1.00},
        cursor=cursor,
        vacation_map=vacation_map,
        avoid_previous=False,
        allow_fallback=True,
        use_weighted_cursor=True,
    )


# ---------------------------------------------------------------------------
# BLOCK SCHEDULING ENGINE
# ---------------------------------------------------------------------------

def schedule_blocks(
    roster: List[Dict[str, Any]],
    dates: List[date],
    cursor_state: Dict[str, float],
    vacation_map: Optional[Dict[str, List[str]]] = None,
    blocks: Optional[List[Dict[str, Any]]] = None,
    interactive: bool = False,
    weekend_dates: Optional[List[date]] = None,
    nc_week_anchor: Optional[date] = None,
) -> Tuple[Schedule, Dict[str, float]]:
    """
    Schedule multiple blocks in priority order, merging results per date.

    Args:
        roster:          Full roster (filtered per block's pool_filter).
        dates:           Weekday dates to schedule (weekend_dates separate).
        cursor_state:    Dict of {cursor_key: float} — mutated in place & returned.
        vacation_map:    {date_str: [unavailable_names]}.
        blocks:          Block dicts (schedule_config.SCHEDULING_BLOCKS).
        interactive:     If True, prompt user before each block.
        weekend_dates:   Sat+Sun dates for weekend blocks.
        nc_week_anchor:  A Monday (or any date) known to be an NC week. Used to
                         compute week parity (NC/KM) for blocks with week_type or
                         allowed_weekdays_nc/allowed_weekdays_km. Default: None
                         (parity disabled; use 2026-03-02 for real schedule).

    Returns:
        (merged_schedule, updated_cursor_state)
    """
    from src.schedule_config import SCHEDULING_BLOCKS

    if blocks is None:
        blocks = SCHEDULING_BLOCKS

    if vacation_map is None:
        vacation_map = {}

    merged: Schedule = {}
    blocks_sorted = sorted(blocks, key=lambda b: b["priority"])

    for block in blocks_sorted:
        config = block["config"]
        block_id = block["block_id"]
        label = block["label"]
        can_skip = block.get("can_skip", True)
        schedule_type = config.get("schedule_type", "weekday")
        pool_filter = config.get("pool_filter")
        subspecialty_gate = block.get("subspecialty_gate")
        exclude_ir = block.get("exclude_ir", False)

        # Filter pool — exclude_ir is a hard gate for mercy/weekend blocks
        pool = _filter_pool(roster, pool_filter, subspecialty_gate, exclude_ir=exclude_ir)

        if not pool:
            logger.warning(f"Block '{label}': empty pool after filter — skipping")
            continue

        # Interactive confirmation
        if interactive:
            prompt = block.get("interactive_prompt", f"Schedule {label}?")
            skip = _interactive_confirm(prompt, can_skip=can_skip)
            if skip:
                logger.info(f"Skipped block: {label}")
                continue

        # ── Determine date list for this block ──────────────────────────────
        if schedule_type == "weekend":
            if not weekend_dates:
                logger.debug(f"Block '{label}': no weekend_dates — skipping")
                continue
            block_dates = list(weekend_dates)
        else:
            block_dates = list(dates)

        # 1. week_type filter: only include dates in NC or KM weeks
        week_type = config.get("week_type")
        if week_type and nc_week_anchor and block_dates:
            block_dates = [
                d for d in block_dates
                if _get_week_type(d, nc_week_anchor) == week_type
            ]
            logger.debug(
                f"Block '{label}': week_type='{week_type}' → {len(block_dates)} dates"
            )

        # 2. allowed_weekdays: flat set applies to all weeks.
        #    allowed_weekdays_nc / allowed_weekdays_km: per-week-type override.
        allowed_nc = config.get("allowed_weekdays_nc")
        allowed_km = config.get("allowed_weekdays_km")
        if (allowed_nc is not None or allowed_km is not None) and nc_week_anchor:
            filtered = []
            for d in block_dates:
                wt = _get_week_type(d, nc_week_anchor)
                if wt == "nc" and allowed_nc is not None:
                    if d.weekday() in allowed_nc:
                        filtered.append(d)
                elif wt == "km" and allowed_km is not None:
                    if d.weekday() in allowed_km:
                        filtered.append(d)
                else:
                    filtered.append(d)
            block_dates = filtered
            logger.debug(
                f"Block '{label}': per-week-type allowed_weekdays → {len(block_dates)} dates"
            )
        else:
            # Flat allowed_weekdays (uniform across all weeks)
            allowed_weekdays = config.get("allowed_weekdays")
            if allowed_weekdays is not None and block_dates:
                block_dates = [d for d in block_dates if d.weekday() in allowed_weekdays]
                logger.debug(
                    f"Block '{label}': allowed_weekdays {allowed_weekdays} → {len(block_dates)} dates"
                )

        # 3. slots_per_week cap (demand-based; only for weekday blocks)
        slots_per_week = config.get("slots_per_week")
        if slots_per_week is not None and block_dates and schedule_type == "weekday":
            from itertools import groupby
            def week_key(d):
                return d.isocalendar()[0], d.isocalendar()[1]
            block_dates_sorted = sorted(block_dates)
            limited = []
            for (_y, _w), week_dates in groupby(block_dates_sorted, key=week_key):
                week_list = list(week_dates)
                limited.extend(week_list[: int(slots_per_week)])
            block_dates = limited
            logger.debug(
                f"Block '{label}': slots_per_week={slots_per_week} → {len(block_dates)} dates"
            )

        if not block_dates:
            logger.info(f"Block '{label}': no dates after filters — skipping")
            continue

        cursor_key = config["cursor_key"]
        cursor = cursor_state.get(cursor_key, 0.0)

        concurrent_ok = block.get("concurrent_ok", False)

        # Build augmented vacation map: existing vacation PLUS names already
        # assigned in earlier blocks on each date (prevents double-booking).
        # Hard: No IR weekday + Gen same day; no radiologist with 2 distinct weekday tasks.
        _IR_WEEKDAY_SHIFTS = {"IR-1", "IR-2", "IR-CALL"}
        _EXCLUSIVE_WEEKDAY_SHIFTS = {"M0", "M1", "M2", "M3", "IR-1", "IR-2", "IR-CALL"}
        augmented_vacation = {}
        for d in (vacation_map or {}):
            augmented_vacation[d] = list(vacation_map.get(d, []))
        if not concurrent_ok:
            for date_str, prior_assignments in merged.items():
                prior_names = [name for _, name in prior_assignments if name != "UNFILLED"]
                if prior_names:
                    if date_str not in augmented_vacation:
                        augmented_vacation[date_str] = []
                    augmented_vacation[date_str] = list(set(
                        augmented_vacation.get(date_str, []) + prior_names
                    ))
        # Always exclude IR-1/IR-2 assignees from all other blocks on that date
        for date_str, prior_assignments in merged.items():
            ir_weekday_names = [
                name for shift, name in prior_assignments
                if name != "UNFILLED" and shift in _IR_WEEKDAY_SHIFTS
            ]
            if ir_weekday_names:
                if date_str not in augmented_vacation:
                    augmented_vacation[date_str] = []
                augmented_vacation[date_str] = list(set(
                    augmented_vacation.get(date_str, []) + ir_weekday_names
                ))
        # No radiologist may cover 2 distinct weekday tasks: exclude anyone with
        # any exclusive weekday shift (M0,M1,M2,M3,IR-1,IR-2) from other blocks that day.
        for date_str, prior_assignments in merged.items():
            exclusive_names = [
                name for shift, name in prior_assignments
                if name != "UNFILLED" and shift in _EXCLUSIVE_WEEKDAY_SHIFTS
            ]
            if exclusive_names:
                if date_str not in augmented_vacation:
                    augmented_vacation[date_str] = []
                augmented_vacation[date_str] = list(set(
                    augmented_vacation.get(date_str, []) + exclusive_names
                ))
        # Outpatient blocks: at most one outpatient assignment per person per day
        if concurrent_ok:
            from src.schedule_config import OUTPATIENT_SHIFTS
            for date_str, prior_assignments in merged.items():
                prior_outpatient_names = [
                    name for shift, name in prior_assignments
                    if name != "UNFILLED" and shift in OUTPATIENT_SHIFTS
                ]
                if prior_outpatient_names:
                    if date_str not in augmented_vacation:
                        augmented_vacation[date_str] = []
                    augmented_vacation[date_str] = list(set(
                        augmented_vacation.get(date_str, []) + prior_outpatient_names
                    ))

        block_schedule, new_cursor = schedule_period(
            people=pool,
            dates=block_dates,
            shifts_per_period=config["shifts_per_period"],
            shift_names=config["shift_names"],
            shift_weights=config.get("shift_weights"),
            cursor=cursor,
            vacation_map=augmented_vacation,
            avoid_previous=config.get("avoid_previous", False),
            allow_fallback=config.get("allow_fallback", True),
            use_weighted_cursor=config.get("use_weighted_cursor", True),
        )

        cursor_state[cursor_key] = new_cursor

        # ── mirror_weekend: copy each Friday IR-CALL assignment to Sat + Sun ─
        # Used for IR-CALL where the same IR person covers Fri+Sat+Sun.
        if config.get("mirror_weekend"):
            mirrored: Schedule = {}
            for date_str, assignments in block_schedule.items():
                d = date.fromisoformat(date_str)
                if d.weekday() == 4:   # Friday
                    sat = d + timedelta(days=1)
                    sun = d + timedelta(days=2)
                    for mirror_day in (sat, sun):
                        mirror_str = mirror_day.isoformat()
                        if mirror_str not in mirrored:
                            mirrored[mirror_str] = []
                        for shift_name, person_name in assignments:
                            if person_name == "UNFILLED":
                                continue
                            mirrored[mirror_str].append((shift_name, person_name))
            # Merge mirrored entries — Sat/Sun IR-CALL
            for date_str, assignments in mirrored.items():
                if date_str not in block_schedule:
                    block_schedule[date_str] = []
                block_schedule[date_str].extend(assignments)
            if mirrored:
                logger.info(
                    f"Block '{label}': mirrored IR-CALL to {len(mirrored)} Sat/Sun dates"
                )

        # Merge into master schedule — at most one assignment per (date, shift)
        # to prevent two radiologists on the same task in exports.
        for date_str, assignments in block_schedule.items():
            if date_str not in merged:
                merged[date_str] = []
            existing_shifts = {shift for shift, _ in merged[date_str]}
            for shift_name, person_name in assignments:
                if shift_name in existing_shifts:
                    logger.warning(
                        f"Block '{label}': skipping duplicate (date={date_str}, shift={shift_name}) — already assigned"
                    )
                    continue
                merged[date_str].append((shift_name, person_name))
                existing_shifts.add(shift_name)

        logger.info(f"Block '{label}' scheduled: {sum(len(v) for v in block_schedule.values())} assignments, cursor→{new_cursor:.2f}")

    return merged, cursor_state


# ---------------------------------------------------------------------------
# Fairness Metrics
# ---------------------------------------------------------------------------

def calculate_fairness_metrics(
    schedule: Schedule,
    people: List[Dict[str, Any]],
    shift_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Calculate per-radiologist counts, weighted workload, CV, and per-shift breakdown.

    Returns:
        {
          mean, std, cv, min, max,
          counts: {name: int},
          weighted_counts: {name: float},
          per_shift: {shift_name: {name: int}},
          unfilled: int,
        }
    """
    from src.schedule_config import SHIFT_DEFINITIONS

    if shift_weights is None:
        shift_weights = {k: v["weight"] for k, v in SHIFT_DEFINITIONS.items()}
    shift_hours = {k: v.get("hours", 8) for k, v in SHIFT_DEFINITIONS.items()}

    raw_counts: Dict[str, int] = {p["name"]: 0 for p in people}
    weighted_counts: Dict[str, float] = {p["name"]: 0.0 for p in people}
    hours_counts: Dict[str, float] = {p["name"]: 0.0 for p in people}
    per_shift: Dict[str, Dict[str, int]] = {}
    unfilled = 0

    for _date, assignments in schedule.items():
        for shift_name, person_name in assignments:
            if person_name == "UNFILLED":
                unfilled += 1
                continue
            if person_name not in raw_counts:
                # Radiologist not in current roster (e.g. locum) — skip
                continue

            raw_counts[person_name] += 1
            w = shift_weights.get(shift_name, 1.0)
            weighted_counts[person_name] += w
            hrs = shift_hours.get(shift_name, 8)
            hours_counts[person_name] += hrs

            if shift_name not in per_shift:
                per_shift[shift_name] = {p["name"]: 0 for p in people}
            if person_name in per_shift[shift_name]:
                per_shift[shift_name][person_name] += 1

    values = list(weighted_counts.values())
    mean_val = sum(values) / len(values) if values else 0.0
    variance = sum((v - mean_val) ** 2 for v in values) / len(values) if values else 0.0
    std_val = math.sqrt(variance)
    cv = (std_val / mean_val * 100) if mean_val > 0 else 0.0

    hours_values = list(hours_counts.values())
    hours_mean = sum(hours_values) / len(hours_values) if hours_values else 0.0
    hours_variance = sum((v - hours_mean) ** 2 for v in hours_values) / len(hours_values) if hours_values else 0.0
    hours_std = math.sqrt(hours_variance)
    hours_cv = (hours_std / hours_mean * 100) if hours_mean > 0 else 0.0

    per_shift_cv: Dict[str, float] = {}
    for shift, counts in per_shift.items():
        sv = list(counts.values())
        sm = sum(sv) / len(sv) if sv else 0
        sv_std = math.sqrt(sum((v - sm) ** 2 for v in sv) / len(sv)) if sv else 0
        per_shift_cv[shift] = (sv_std / sm * 100) if sm > 0 else 0.0

    return {
        "mean": mean_val,
        "std": std_val,
        "cv": cv,
        "min": min(values) if values else 0,
        "max": max(values) if values else 0,
        "counts": raw_counts,
        "weighted_counts": weighted_counts,
        "hours_counts": hours_counts,
        "hours_mean": hours_mean,
        "hours_std": hours_std,
        "hours_cv": hours_cv,
        "per_shift": per_shift,
        "per_shift_cv": per_shift_cv,
        "unfilled": unfilled,
    }


# ---------------------------------------------------------------------------
# Helpers (public for repair.py)
# ---------------------------------------------------------------------------

def filter_pool_for_block(
    roster: List[Dict[str, Any]],
    block: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Return the eligible pool for a block using the same logic as schedule_blocks.
    Used by repair.py to get qualified staff for an unfilled slot without duplicating logic.

    Args:
        roster: Full roster list.
        block: Block dict with "config" and optional "subspecialty_gate", "exclude_ir".

    Returns:
        Filtered list of person dicts eligible for this block's shifts.
    """
    config = block.get("config", {})
    pool_filter = config.get("pool_filter")
    subspecialty_gate = block.get("subspecialty_gate") or config.get("subspecialty_gate")
    exclude_ir = block.get("exclude_ir", config.get("exclude_ir", False))

    pool = _filter_pool(roster, pool_filter, subspecialty_gate, exclude_ir=exclude_ir)

    if config.get("require_participates_mri", False):
        pool = [p for p in pool if p.get("participates_MRI", False)]
    if config.get("require_participates_pet", False):
        pool = [p for p in pool if p.get("participates_PET", False)]

    return pool


def _filter_pool(
    roster: List[Dict[str, Any]],
    pool_filter: Optional[str],
    subspecialty_gate: Optional[str] = None,
    exclude_ir: bool = False,
) -> List[Dict[str, Any]]:
    """
    Filter roster by pool membership and optional subspecialty gate.

    Args:
        pool_filter:      Roster key that must be True (e.g. 'participates_mercy').
        subspecialty_gate: Required subspecialty tag (e.g. 'ir', 'MRI').
        exclude_ir:       Hard-exclude participates_ir=True staff regardless of
                          any other flag. Enforces that IR staff never appear in
                          mercy/weekend blocks even if they share a gen pool key.
    """
    result = roster
    if pool_filter:
        result = [p for p in result if p.get(pool_filter, False)]
    if exclude_ir:
        result = [p for p in result if not p.get("participates_ir", False)]
    if subspecialty_gate:
        gate = subspecialty_gate.lower()
        result = [
            p for p in result
            if gate in [s.lower() for s in p.get("subspecialties", [])]
        ]
    return result


def _interactive_confirm(prompt: str, can_skip: bool = True) -> bool:
    """
    Prompt user interactively. Returns True if block should be SKIPPED.
    Non-interactive environments auto-proceed.
    """
    suffix = " [Y/n/skip]" if can_skip else " [Y/n]"
    try:
        ans = input(f"\n▶ {prompt}{suffix}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        # Non-interactive (CI, test) — auto-proceed
        return False
    if ans in ("n", "no"):
        return True  # skip
    if can_skip and ans in ("s", "skip"):
        return True
    return False  # proceed


def get_weekday_dates(start: date, end: date) -> List[date]:
    """Return all Monday-Friday dates in [start, end]."""
    out = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def get_saturday_dates(start: date, end: date) -> List[date]:
    """Return all Saturdays in [start, end]."""
    out = []
    d = start
    while d <= end:
        if d.weekday() == 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def get_weekend_dates(start: date, end: date) -> List[date]:
    """
    Return all Saturdays and Sundays in [start, end], interleaved in
    chronological order (Sat, Sun, Sat, Sun, ...).

    Passing this list as weekend_dates to schedule_blocks() causes the
    cursor to advance after each day, so Saturday and Sunday are assigned
    to DIFFERENT radiologists from the same eligible pool.  Shift types
    are identical (EP, M0_WEEKEND, Dx-CALL, etc.); only personnel differ.
    """
    out = []
    d = start
    while d <= end:
        if d.weekday() in (5, 6):   # Saturday=5, Sunday=6
            out.append(d)
        d += timedelta(days=1)
    return out


def expand_weekend_to_sunday(schedule: "Schedule") -> "Schedule":
    """
    DEPRECATED — replaced by get_weekend_dates().

    Previously mirrored Saturday assignments onto Sunday (same personnel).
    Now Sunday is scheduled independently via get_weekend_dates() so each
    day gets distinct radiologists.  Kept for backward compatibility only.
    """
    import warnings
    warnings.warn(
        "expand_weekend_to_sunday() is deprecated. Pass get_weekend_dates() "
        "as weekend_dates to schedule_blocks() instead.",
        DeprecationWarning, stacklevel=2,
    )
    expanded = dict(schedule)
    for date_str, assignments in list(schedule.items()):
        d = date.fromisoformat(date_str)
        if d.weekday() == 5:
            sunday = d + timedelta(days=1)
            sun_str = sunday.isoformat()
            if sun_str not in expanded:
                expanded[sun_str] = list(assignments)
    return expanded
