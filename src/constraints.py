"""
Constraint System for Fair Radiology Scheduling

Hard constraints (must not violate):
- Vacation blocks, double-booking, subspecialty qualification,
  FTE limits, minimum rest between shifts

Soft constraints (minimize violations):
- Back-to-back weekends, workload CV target < 10%,
  M0 helper shift weighting (M0 = 0.25 × M1)

Designed for PuLP or Google OR-Tools (prefer OR-Tools for scalability).
See docs/architecture.md, docs/analysis/comprehensive_analysis.md
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class ConstraintSeverity(Enum):
    HARD = "hard"
    SOFT = "soft"


@dataclass
class ConstraintViolation:
    """Represents a constraint violation for reporting"""
    severity: ConstraintSeverity
    constraint_type: str
    description: str
    date: Optional[str] = None
    staff: Optional[str] = None
    shift: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class ConstraintChecker:
    """
    Validates schedules against hard and soft constraints.
    Can be extended with OR-Tools/PuLP for optimization.
    """

    def __init__(
        self,
        roster: List[Dict[str, Any]],
        vacation_map: Dict[str, List[str]],
        shift_definitions: Optional[Dict[str, Dict]] = None,
    ):
        self.roster = roster
        self.vacation_map = vacation_map
        self.shift_definitions = shift_definitions or {}

    def check_vacation(
        self,
        schedule: Dict[str, List[Tuple[str, str]]],
    ) -> List[ConstraintViolation]:
        """Hard: No assignment on vacation dates"""
        violations = []
        for date_str, assignments in schedule.items():
            unavailable = set(self.vacation_map.get(date_str, []))
            for shift_name, person_name in assignments:
                if person_name in unavailable:
                    violations.append(ConstraintViolation(
                        severity=ConstraintSeverity.HARD,
                        constraint_type="vacation",
                        description=f"{person_name} assigned on vacation date",
                        date=date_str,
                        staff=person_name,
                        shift=shift_name,
                    ))
        return violations

    def check_double_booking(
        self,
        schedule: Dict[str, List[Tuple[str, str]]],
    ) -> List[ConstraintViolation]:
        """Hard: No duplicate assignments per date"""
        violations = []
        for date_str, assignments in schedule.items():
            seen: Set[str] = set()
            for shift_name, person_name in assignments:
                key = f"{person_name}:{shift_name}"
                if person_name in seen:
                    violations.append(ConstraintViolation(
                        severity=ConstraintSeverity.HARD,
                        constraint_type="double_booking",
                        description=f"{person_name} assigned multiple shifts on same date",
                        date=date_str,
                        staff=person_name,
                    ))
                seen.add(person_name)
        return violations

    def check_back_to_back_weekend(
        self,
        schedule: Dict[str, List[Tuple[str, str]]],
        weekend_dates: List[str],
    ) -> List[ConstraintViolation]:
        """Soft: Flag consecutive weekend assignments"""
        violations = []
        from datetime import datetime, timedelta
        # Build set of weekend dates that have assignments per person
        person_weekends: Dict[str, List[datetime]] = {}
        for date_str in weekend_dates:
            if date_str not in schedule:
                continue
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            for _shift, person in schedule[date_str]:
                if person not in person_weekends:
                    person_weekends[person] = []
                person_weekends[person].append(dt)
        # Check for consecutive weekends
        for person, dates in person_weekends.items():
            dates_sorted = sorted(set(dates))
            for i in range(1, len(dates_sorted)):
                gap = (dates_sorted[i] - dates_sorted[i - 1]).days
                if gap == 7:  # Consecutive weekends
                    violations.append(ConstraintViolation(
                        severity=ConstraintSeverity.SOFT,
                        constraint_type="back_to_back_weekend",
                        description=f"{person} has consecutive weekend assignments",
                        staff=person,
                        details={"dates": [d.strftime("%Y-%m-%d") for d in [dates_sorted[i - 1], dates_sorted[i]]]},
                    ))
        return violations

    def check_all(
        self,
        schedule: Dict[str, List[Tuple[str, str]]],
        weekend_dates: Optional[List[str]] = None,
    ) -> Tuple[List[ConstraintViolation], List[ConstraintViolation]]:
        """Run all checks. Returns (hard_violations, soft_violations)"""
        hard = []
        soft = []

        hard.extend(self.check_vacation(schedule))
        hard.extend(self.check_double_booking(schedule))
        if weekend_dates:
            soft.extend(self.check_back_to_back_weekend(schedule, weekend_dates))

        return [v for v in hard if v.severity == ConstraintSeverity.HARD], \
               [v for v in soft if v.severity == ConstraintSeverity.SOFT]
