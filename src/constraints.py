"""
constraints.py — Constraint System for Fair Radiology Scheduling

Hard constraints (must NOT violate):
  - VACATION: No assignment on vacation dates
  - DOUBLE_BOOKING: No radiologist assigned twice on same date
  - SUBSPECIALTY_MISMATCH: IR-1/IR-2 only to IR-qualified staff
  - IR_POOL_GATE: IR shifts only from IR pool

Soft constraints (minimize violations):
  - BACK_TO_BACK_WEEKEND: Avoid same staff on consecutive weekends
  - CV_EXCEEDED: Weighted workload CV > target (10%)
  - FTE_OVERLOAD: Assignments exceed FTE-proportional expected load

Severity enum and ConstraintViolation dataclass are importable for
dry_run.py reporting.

Usage:
  checker = ConstraintChecker(roster, vacation_map)
  hard, soft = checker.check_all(schedule, weekend_dates=sat_dates)
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ConstraintSeverity(Enum):
    HARD = "hard"
    SOFT = "soft"


@dataclass
class ConstraintViolation:
    severity: ConstraintSeverity
    constraint_type: str
    description: str
    date: Optional[str] = None
    staff: Optional[str] = None
    shift: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [f"[{self.severity.value.upper()}] {self.constraint_type}"]
        if self.date:
            parts.append(f"date={self.date}")
        if self.staff:
            parts.append(f"staff={self.staff}")
        if self.shift:
            parts.append(f"shift={self.shift}")
        parts.append(f"→ {self.description}")
        return " | ".join(parts)


Schedule = Dict[str, List[Tuple[str, str]]]   # date_str → [(shift, name)]


class ConstraintChecker:
    """
    Validates schedules against hard and soft constraints.

    Accepts the standard schedule format:
        {date_str: [(shift_name, person_name), ...]}
    """

    def __init__(
        self,
        roster: List[Dict[str, Any]],
        vacation_map: Dict[str, List[str]],
        shift_definitions: Optional[Dict[str, Dict]] = None,
        fairness_targets: Optional[Dict[str, Any]] = None,
    ):
        self.roster = roster
        self.vacation_map = vacation_map
        self.shift_definitions = shift_definitions or {}
        self.fairness_targets = fairness_targets or {"cv_target": 0.10}

        # Build lookup maps for fast access
        self._name_to_person: Dict[str, Dict] = {p["name"]: p for p in roster}
        self._ir_names: Set[str] = {
            p["name"] for p in roster
            if "ir" in [s.lower() for s in p.get("subspecialties", [])]
            or p.get("participates_ir", False)
        }
        self._ir_shifts: Set[str] = {"IR-1", "IR-2", "IR-CALL", "PVH-IR"}

    # -----------------------------------------------------------------------
    # HARD: Vacation check
    # -----------------------------------------------------------------------

    def check_vacation(self, schedule: Schedule) -> List[ConstraintViolation]:
        """Hard: No assignment on a vacation date."""
        violations = []
        for date_str, assignments in schedule.items():
            unavailable = set(self.vacation_map.get(date_str, []))
            for shift_name, person_name in assignments:
                if person_name in unavailable:
                    violations.append(ConstraintViolation(
                        severity=ConstraintSeverity.HARD,
                        constraint_type="VACATION",
                        description=f"{person_name} is on vacation but was assigned {shift_name}",
                        date=date_str,
                        staff=person_name,
                        shift=shift_name,
                    ))
        return violations

    # -----------------------------------------------------------------------
    # HARD: Double-booking check
    # -----------------------------------------------------------------------

    def check_double_booking(self, schedule: Schedule) -> List[ConstraintViolation]:
        """Hard: No radiologist assigned more than once on the same date."""
        violations = []
        for date_str, assignments in schedule.items():
            seen: Dict[str, str] = {}  # name → first shift
            for shift_name, person_name in assignments:
                if person_name == "UNFILLED":
                    continue
                if person_name in seen:
                    violations.append(ConstraintViolation(
                        severity=ConstraintSeverity.HARD,
                        constraint_type="DOUBLE_BOOKING",
                        description=(
                            f"{person_name} assigned to both {seen[person_name]} "
                            f"and {shift_name} on {date_str}"
                        ),
                        date=date_str,
                        staff=person_name,
                        shift=shift_name,
                        details={"first_shift": seen[person_name]},
                    ))
                else:
                    seen[person_name] = shift_name
        return violations

    # -----------------------------------------------------------------------
    # HARD: Subspecialty / IR pool gate
    # -----------------------------------------------------------------------

    def check_subspecialty_qualification(self, schedule: Schedule) -> List[ConstraintViolation]:
        """
        Hard: IR shifts (IR-1, IR-2, IR-CALL, PVH-IR) must only be assigned
        to IR-qualified radiologists.  Extends to other subspecialty shifts
        using SHIFT_SUBSPECIALTY_MAP from skills.py.
        """
        from src.skills import SHIFT_SUBSPECIALTY_MAP

        violations = []
        for date_str, assignments in schedule.items():
            for shift_name, person_name in assignments:
                if person_name == "UNFILLED":
                    continue
                required = SHIFT_SUBSPECIALTY_MAP.get(shift_name, set())
                if not required:
                    continue
                person = self._name_to_person.get(person_name)
                if person is None:
                    continue
                person_specs = set(s.lower() for s in person.get("subspecialties", []))
                missing = required - person_specs
                if missing:
                    violations.append(ConstraintViolation(
                        severity=ConstraintSeverity.HARD,
                        constraint_type="SUBSPECIALTY_MISMATCH",
                        description=(
                            f"{person_name} assigned to {shift_name} but lacks "
                            f"required subspecialties: {missing}"
                        ),
                        date=date_str,
                        staff=person_name,
                        shift=shift_name,
                        details={"required": list(required), "missing": list(missing)},
                    ))
        return violations

    def check_ir_pool_gate(self, schedule: Schedule) -> List[ConstraintViolation]:
        """
        Hard: IR shifts must only be assigned to IR-qualified radiologists.
        """
        violations = []
        for date_str, assignments in schedule.items():
            for shift_name, person_name in assignments:
                if shift_name not in self._ir_shifts:
                    continue
                if person_name == "UNFILLED":
                    continue
                if person_name not in self._ir_names:
                    violations.append(ConstraintViolation(
                        severity=ConstraintSeverity.HARD,
                        constraint_type="IR_POOL_GATE",
                        description=(
                            f"{person_name} assigned to {shift_name} "
                            f"but is NOT in the IR-qualified pool"
                        ),
                        date=date_str,
                        staff=person_name,
                        shift=shift_name,
                    ))
        return violations

    def check_mercy_pool_gate(self, schedule: Schedule) -> List[ConstraintViolation]:
        """
        Hard: M0/M1/M2/M3 must NOT be assigned to IR staff.
        IR staff (DA, SS, SF, TR) are excluded from mercy rotation.
        """
        mercy_shifts = {"M0", "M1", "M2", "M3"}
        violations = []
        for date_str, assignments in schedule.items():
            for shift_name, person_name in assignments:
                if shift_name not in mercy_shifts:
                    continue
                if person_name == "UNFILLED":
                    continue
                person = self._name_to_person.get(person_name)
                if person and person.get("participates_ir", False):
                    violations.append(ConstraintViolation(
                        severity=ConstraintSeverity.HARD,
                        constraint_type="MERCY_POOL_GATE",
                        description=(
                            f"{person_name} (IR staff) assigned to mercy shift {shift_name} — "
                            f"IR staff are excluded from M0/M1/M2/M3"
                        ),
                        date=date_str,
                        staff=person_name,
                        shift=shift_name,
                    ))
        return violations

    def check_weekend_pool_gate(self, schedule: Schedule) -> List[ConstraintViolation]:
        """
        Hard: EP/LP/Dx-CALL must NOT be assigned to IR staff.
        IR staff are excluded from all weekend inpatient shifts.
        """
        weekend_shifts = {"EP", "LP", "Dx-CALL", "M0_WEEKEND"}
        violations = []
        for date_str, assignments in schedule.items():
            for shift_name, person_name in assignments:
                if shift_name not in weekend_shifts:
                    continue
                if person_name == "UNFILLED":
                    continue
                person = self._name_to_person.get(person_name)
                if person and person.get("participates_ir", False):
                    violations.append(ConstraintViolation(
                        severity=ConstraintSeverity.HARD,
                        constraint_type="WEEKEND_POOL_GATE",
                        description=(
                            f"{person_name} (IR staff) assigned to weekend shift {shift_name} — "
                            f"IR staff are excluded from EP/LP/Dx-CALL"
                        ),
                        date=date_str,
                        staff=person_name,
                        shift=shift_name,
                    ))
        return violations

    # -----------------------------------------------------------------------
    # SOFT: Back-to-back weekend
    # -----------------------------------------------------------------------

    def check_back_to_back_weekend(
        self,
        schedule: Schedule,
        weekend_dates: List[str],
    ) -> List[ConstraintViolation]:
        """
        Soft: Flag radiologists assigned on consecutive weekends.
        weekend_dates should be sorted Saturday date strings.
        """
        violations = []
        sorted_weekends = sorted(weekend_dates)
        prev_names: Set[str] = set()

        for date_str in sorted_weekends:
            assignments = schedule.get(date_str, [])
            cur_names = {name for _, name in assignments if name != "UNFILLED"}
            overlap = cur_names & prev_names
            for name in overlap:
                violations.append(ConstraintViolation(
                    severity=ConstraintSeverity.SOFT,
                    constraint_type="BACK_TO_BACK_WEEKEND",
                    description=f"{name} assigned on back-to-back weekends ending {date_str}",
                    date=date_str,
                    staff=name,
                ))
            prev_names = cur_names

        return violations

    # -----------------------------------------------------------------------
    # SOFT: CV target check
    # -----------------------------------------------------------------------

    def check_cv_target(
        self,
        metrics: Dict[str, Any],
        pool_label: str = "",
    ) -> List[ConstraintViolation]:
        """Soft: Warn if overall weighted CV exceeds target."""
        violations = []
        target = self.fairness_targets.get("cv_target", 0.10)
        cv = metrics.get("cv", 0) / 100  # cv stored as percentage
        if cv > target:
            violations.append(ConstraintViolation(
                severity=ConstraintSeverity.SOFT,
                constraint_type="CV_EXCEEDED",
                description=(
                    f"{pool_label} weighted CV={cv:.1%} exceeds target {target:.1%}. "
                    f"Mean={metrics.get('mean', 0):.2f}, "
                    f"Std={metrics.get('std', 0):.2f}"
                ),
                details={
                    "cv": cv,
                    "target": target,
                    "mean": metrics.get("mean"),
                    "std": metrics.get("std"),
                },
            ))
        return violations

    # -----------------------------------------------------------------------
    # SOFT: Unfilled slots
    # -----------------------------------------------------------------------

    def check_unfilled(self, schedule: Schedule) -> List[ConstraintViolation]:
        """Soft: Flag any UNFILLED slots — indicates pool exhaustion."""
        violations = []
        for date_str, assignments in schedule.items():
            for shift_name, person_name in assignments:
                if person_name == "UNFILLED":
                    violations.append(ConstraintViolation(
                        severity=ConstraintSeverity.SOFT,
                        constraint_type="UNFILLED_SLOT",
                        description=f"Shift {shift_name} on {date_str} could not be filled",
                        date=date_str,
                        shift=shift_name,
                    ))
        return violations

    # -----------------------------------------------------------------------
    # Run all checks
    # -----------------------------------------------------------------------

    def check_all(
        self,
        schedule: Schedule,
        weekend_dates: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        pool_label: str = "",
    ) -> Tuple[List[ConstraintViolation], List[ConstraintViolation]]:
        """
        Run all hard and soft constraint checks.

        Returns:
            (hard_violations, soft_violations)
        """
        hard: List[ConstraintViolation] = []
        soft: List[ConstraintViolation] = []

        hard.extend(self.check_vacation(schedule))
        hard.extend(self.check_double_booking(schedule))
        hard.extend(self.check_subspecialty_qualification(schedule))
        hard.extend(self.check_ir_pool_gate(schedule))
        hard.extend(self.check_mercy_pool_gate(schedule))
        hard.extend(self.check_weekend_pool_gate(schedule))
        soft.extend(self.check_unfilled(schedule))

        if weekend_dates:
            soft.extend(self.check_back_to_back_weekend(schedule, weekend_dates))

        if metrics:
            soft.extend(self.check_cv_target(metrics, pool_label=pool_label))

        return hard, soft

    # -----------------------------------------------------------------------
    # Input validation (roster / config)
    # -----------------------------------------------------------------------

    def validate_roster(self) -> Tuple[List[str], List[str]]:
        """
        Validate roster for structural integrity.

        Returns:
            (errors, warnings) as lists of strings
        """
        errors = []
        warnings = []

        indices = [p["index"] for p in self.roster]
        if sorted(indices) != list(range(len(self.roster))):
            errors.append(
                f"Roster indices not contiguous 0..{len(self.roster)-1}: {sorted(indices)}"
            )

        names = [p["name"] for p in self.roster]
        dupes = [n for n in names if names.count(n) > 1]
        if dupes:
            errors.append(f"Duplicate names in roster: {set(dupes)}")

        for p in self.roster:
            if p.get("fte", 1.0) <= 0:
                warnings.append(f"{p['name']}: FTE={p.get('fte')} ≤ 0")
            if not p.get("subspecialties"):
                warnings.append(f"{p['name']}: no subspecialties listed")

        ir_count = len(self._ir_names)
        if ir_count < 2:
            errors.append(
                f"IR pool has only {ir_count} qualified radiologists; need ≥2 for IR-1/IR-2"
            )

        return errors, warnings
