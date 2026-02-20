"""
Fair Radiology Scheduling Engine

Modules:
- config: Roster, shift definitions, constraint weights
- engine: Core scheduling algorithm (weighted cursor, vacation-aware)
- scheduling_engine: Legacy scheduling engine (backwards compatibility)
- qgenda_client: QGenda API integration
"""

from .config import (
    load_roster,
    load_vacation_map,
    load_cursor_state,
    save_cursor_state,
    filter_pool,
    get_shift_weight,
    get_config,
    INPATIENT_WEEKDAY_CONFIG,
    INPATIENT_WEEKEND_CONFIG,
    IR_WEEKDAY_CONFIG,
    DEFAULT_SHIFT_DEFINITIONS,
)

from .engine import (
    schedule_period,
    schedule_weekday_mercy,
    schedule_weekend_mercy,
    schedule_ir_weekday,
    calculate_fairness_metrics,
)

__all__ = [
    "load_roster",
    "load_vacation_map",
    "load_cursor_state",
    "save_cursor_state",
    "filter_pool",
    "get_shift_weight",
    "get_config",
    "INPATIENT_WEEKDAY_CONFIG",
    "INPATIENT_WEEKEND_CONFIG",
    "IR_WEEKDAY_CONFIG",
    "DEFAULT_SHIFT_DEFINITIONS",
    "schedule_period",
    "schedule_weekday_mercy",
    "schedule_weekend_mercy",
    "schedule_ir_weekday",
    "calculate_fairness_metrics",
]
