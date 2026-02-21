"""
schedule_config.py — Rotation Pool & Block Scheduling Configuration

Pool membership rules (per SHIPMG specifications):

  IR Pool (DA, SS, SF, TR):
    ✅  IR-1, IR-2, IR-CALL       (participates_ir)
    ✅  Gen assignments            (participates_gen)
    ✅  DA only: MG / O'Toole     (participates_mg)
    ❌  M0, M1, M2, M3            (participates_mercy = NO for IR staff)
    ❌  EP, LP, Dx-CALL           (participates_weekend = NO for IR staff)
    ❌  Outpatient / subspecialty  (participates_outpatient = NO for SS, SF, TR)

  Non-IR Pool (everyone else, 15 radiologists):
    ✅  M0, M1, M2, M3            (participates_mercy)
    ✅  EP, LP, Dx-CALL           (participates_weekend)
    ✅  Gen assignments            (participates_gen)
    ✅  MG / O'Toole if qualified  (participates_mg)
    ✅  Outpatient / subspecialty  (participates_outpatient)
    ❌  IR-1, IR-2, IR-CALL       (not participates_ir)

Block scheduling order (priority):
  1. IR-1 / IR-2 / IR-CALL    — IR pool only, qualification-gated
  2. M3 evening                — mercy pool, evening constraints first
  3. M0 helper                 — mercy pool, weighted 0.25
  4. M1 + M2 day shifts        — mercy pool, full weight
  5. Gen (diagnostic)          — mercy pool + gen, shared pool
  6. Gen (IR staff)            — IR pool + gen, separate cursor
  7. Weekend inpatient         — weekend pool (no IR), back-to-back avoidance
"""

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Shift Definitions
# ---------------------------------------------------------------------------
SHIFT_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # Inpatient Weekday Mercy — non-IR pool only
    "M0":         {"hours": 2,    "weight": 0.25, "location": "remote",
                   "description": "Helper 0700-0800, 1130-1230",
                   "pool": "mercy",   "requires": None},
    "M1":         {"hours": 8,    "weight": 1.00, "location": "onsite",
                   "description": "Day shift 0800-1600",
                   "pool": "mercy",   "requires": None},
    "M2":         {"hours": 8,    "weight": 1.00, "location": "remote",
                   "description": "Remote 0930-1730",
                   "pool": "mercy",   "requires": None},
    "M3":         {"hours": 6,    "weight": 0.75, "location": "remote",
                   "description": "Evening 1600-2200",
                   "pool": "mercy",   "requires": None},

    # IR — IR pool only (DA, SS, SF, TR)
    "IR-1":       {"hours": 8,    "weight": 1.00, "location": "onsite",
                   "description": "IR Day 0800-1600",
                   "pool": "ir",     "requires": "ir"},
    "IR-2":       {"hours": 8,    "weight": 1.00, "location": "onsite",
                   "description": "IR Second 0900-1700",
                   "pool": "ir",     "requires": "ir"},
    "IR-CALL":    {"hours": 8,    "weight": 1.00, "location": "onsite",
                   "description": "IR Call / after-hours",
                   "pool": "ir",     "requires": "ir"},

    # Gen — all 19 participate (separate sub-pools: mercy-gen vs ir-gen)
    "Gen-Mercy":  {"hours": 8,    "weight": 1.00, "location": "remote",
                   "description": "General diagnostic (mercy pool staff)",
                   "pool": "gen_mercy", "requires": None},
    "Gen-IR":     {"hours": 8,    "weight": 1.00, "location": "remote",
                   "description": "General diagnostic (IR pool staff)",
                   "pool": "gen_ir",    "requires": None},

    # MG / O'Toole — DA + qualified non-IR staff
    "MG":         {"hours": 8,    "weight": 1.00, "location": "onsite",
                   "description": "Mammography",
                   "pool": "mg",      "requires": "MG"},
    "O'Toole":    {"hours": 8,    "weight": 1.00, "location": "onsite",
                   "description": "O'Toole mammography suite",
                   "pool": "mg",      "requires": "MG"},

    # Weekend Inpatient — non-IR pool only
    "EP":         {"hours": 6.5,  "weight": 0.81, "location": "onsite",
                   "description": "Weekend early 0800-1430",
                   "pool": "weekend", "requires": None},
    "LP":         {"hours": 8.0,  "weight": 1.00, "location": "onsite",
                   "description": "Weekend late 1400-2200",
                   "pool": "weekend", "requires": None},
    "M0_WEEKEND": {"hours": 2,    "weight": 0.25, "location": "remote",
                   "description": "Weekend helper 0700-0800, 1130-1230",
                   "pool": "weekend", "requires": None},
    "Dx-CALL":    {"hours": 8,    "weight": 1.00, "location": "remote",
                   "description": "Weekend diagnostic call 1400-2200",
                   "pool": "weekend", "requires": None},

    # Subspecialty fixed assignments — NOT in rotation engine
    "Skull Base": {"hours": 8,    "weight": 1.00, "location": "onsite",
                   "description": "Fixed — neuro/skull_base",
                   "pool": None,      "requires": "neuro"},
    "Cardiac":    {"hours": 8,    "weight": 1.00, "location": "onsite",
                   "description": "Fixed — cardiac",
                   "pool": None,      "requires": "cardiac"},

    # Pseudo-shifts
    "OFF ALL DAY":{"hours": 0,    "weight": 0.00, "location": None,
                   "description": "Full day off",
                   "pool": None,      "requires": None},
    "VACATION":   {"hours": 0,    "weight": 0.00, "location": None,
                   "description": "Vacation — skip in cursor",
                   "pool": None,      "requires": None},
    "IR-CALL (RMG)": {"hours": 8, "weight": 1.00, "location": "onsite",
                   "description": "IR Call (QGenda label)",
                   "pool": "ir",      "requires": "ir"},
}

# ---------------------------------------------------------------------------
# Rotation Pool Configs
# ---------------------------------------------------------------------------

# Non-IR mercy weekday (15 radiologists)
INPATIENT_WEEKDAY_CONFIG: Dict[str, Any] = {
    "description": "Mercy weekday M0/M1/M2/M3 — non-IR pool only (15 staff)",
    "pool_filter": "participates_mercy",      # excludes DA, SS, SF, TR
    "shifts_per_period": 4,
    "shift_names": ["M0", "M1", "M2", "M3"],
    "shift_weights": {"M0": 0.25, "M1": 1.00, "M2": 1.00, "M3": 0.75},
    "cursor_key": "inpatient_weekday",
    "avoid_previous": False,
    "allow_fallback": True,
    "use_weighted_cursor": True,
    "target_cv": 0.10,
    "schedule_type": "weekday",
}

# IR weekday (DA, SS, SF, TR)
IR_WEEKDAY_CONFIG: Dict[str, Any] = {
    "description": "IR weekday IR-1/IR-2 — IR pool only (4 staff: DA, SS, SF, TR)",
    "pool_filter": "participates_ir",
    "shifts_per_period": 2,
    "shift_names": ["IR-1", "IR-2"],
    "shift_weights": {"IR-1": 1.00, "IR-2": 1.00},
    "cursor_key": "ir_weekday",
    "avoid_previous": False,
    "allow_fallback": True,
    "use_weighted_cursor": True,
    "target_cv": 0.10,
    "schedule_type": "weekday",
}

# Gen — mercy pool staff doing Gen assignments
GEN_MERCY_CONFIG: Dict[str, Any] = {
    "description": "Gen diagnostic — mercy pool (15 non-IR staff)",
    "pool_filter": "participates_gen",
    "exclude_pool": "participates_ir",        # handled separately in engine
    "shifts_per_period": 1,
    "shift_names": ["Gen-Mercy"],
    "shift_weights": {"Gen-Mercy": 1.00},
    "cursor_key": "gen_mercy",
    "avoid_previous": False,
    "allow_fallback": True,
    "use_weighted_cursor": True,
    "target_cv": 0.10,
    "schedule_type": "weekday",
}

# Gen — IR pool staff doing Gen assignments
GEN_IR_CONFIG: Dict[str, Any] = {
    "description": "Gen diagnostic — IR pool (DA, SS, SF, TR)",
    "pool_filter": "participates_ir",          # all IR do Gen
    "shifts_per_period": 1,
    "shift_names": ["Gen-IR"],
    "shift_weights": {"Gen-IR": 1.00},
    "cursor_key": "gen_ir",
    "avoid_previous": False,
    "allow_fallback": True,
    "use_weighted_cursor": True,
    "target_cv": 0.10,
    "schedule_type": "weekday",
}

# MG / O'Toole — DA + qualified non-IR staff
MG_CONFIG: Dict[str, Any] = {
    "description": "MG/O'Toole — DA + non-IR MG-qualified (participates_mg)",
    "pool_filter": "participates_mg",
    "shifts_per_period": 1,
    "shift_names": ["MG"],
    "shift_weights": {"MG": 1.00},
    "cursor_key": "mg",
    "avoid_previous": False,
    "allow_fallback": True,
    "use_weighted_cursor": True,
    "target_cv": 0.10,
    "schedule_type": "weekday",
}

# Weekend — non-IR pool only (EP/LP/Dx-CALL)
INPATIENT_WEEKEND_CONFIG: Dict[str, Any] = {
    "description": "Inpatient weekend EP/LP/Dx-CALL — non-IR pool (15 staff)",
    "pool_filter": "participates_weekend",     # excludes DA, SS, SF, TR
    "shifts_per_period": 3,
    "shift_names": ["M0_WEEKEND", "EP", "Dx-CALL"],
    "shift_weights": {"M0_WEEKEND": 0.25, "EP": 0.81, "LP": 1.00, "Dx-CALL": 1.00},
    "cursor_key": "inpatient_weekend",
    "avoid_previous": True,
    "allow_fallback": True,
    "use_weighted_cursor": True,
    "target_cv": 0.10,
    "schedule_type": "weekend",
}

# ---------------------------------------------------------------------------
# SCHEDULING_BLOCKS — ordered by priority
# ---------------------------------------------------------------------------
SCHEDULING_BLOCKS: List[Dict[str, Any]] = [
    # 1. IR-1 / IR-2 first — qualification-gated, 4-person pool
    {
        "block_id":   "ir_weekday",
        "label":      "IR Shifts (IR-1, IR-2)",
        "config":     IR_WEEKDAY_CONFIG,
        "priority":   1,
        "interactive_prompt": "Schedule IR shifts (IR-1, IR-2)?",
        "can_skip":   False,
        "subspecialty_gate": "ir",
    },
    # 2. M3 evening — constrained availability, schedule before full-day slots
    {
        "block_id":   "m3_weekday",
        "label":      "M3 Evening Shift",
        "config":     {**INPATIENT_WEEKDAY_CONFIG,
                       "shifts_per_period": 1,
                       "shift_names": ["M3"],
                       "shift_weights": {"M3": 0.75},
                       "cursor_key": "inpatient_weekday",
                       "description": "M3 evening block"},
        "priority":   2,
        "interactive_prompt": "Schedule M3 (evening 1600-2200)?",
        "can_skip":   False,
        "subspecialty_gate": None,
    },
    # 3. M0 helper — lowest weight, non-IR pool
    {
        "block_id":   "m0_weekday",
        "label":      "M0 Helper Shift",
        "config":     {**INPATIENT_WEEKDAY_CONFIG,
                       "shifts_per_period": 1,
                       "shift_names": ["M0"],
                       "shift_weights": {"M0": 0.25},
                       "cursor_key": "inpatient_weekday",
                       "description": "M0 helper block"},
        "priority":   3,
        "interactive_prompt": "Schedule M0 (helper 0700-0800/1130-1230)?",
        "can_skip":   False,
        "subspecialty_gate": None,
    },
    # 4. M1 + M2 full day — non-IR pool
    {
        "block_id":   "m1m2_weekday",
        "label":      "M1 + M2 Day Shifts",
        "config":     {**INPATIENT_WEEKDAY_CONFIG,
                       "shifts_per_period": 2,
                       "shift_names": ["M1", "M2"],
                       "shift_weights": {"M1": 1.00, "M2": 1.00},
                       "cursor_key": "inpatient_weekday",
                       "description": "M1+M2 block"},
        "priority":   4,
        "interactive_prompt": "Schedule M1 and M2 (full day shifts)?",
        "can_skip":   False,
        "subspecialty_gate": None,
    },
    # 5. Gen — mercy pool staff (15 non-IR radiologists)
    #    Separate cursor from IR-Gen so each pool is independently fair
    {
        "block_id":   "gen_mercy",
        "label":      "Gen Diagnostic (mercy pool)",
        "config":     GEN_MERCY_CONFIG,
        "priority":   5,
        "interactive_prompt": "Schedule Gen diagnostic for mercy-pool staff?",
        "can_skip":   True,
        "subspecialty_gate": None,
    },
    # 6. Gen — IR pool staff (DA, SS, SF, TR all do Gen)
    {
        "block_id":   "gen_ir",
        "label":      "Gen Diagnostic (IR pool)",
        "config":     GEN_IR_CONFIG,
        "priority":   6,
        "interactive_prompt": "Schedule Gen diagnostic for IR-pool staff?",
        "can_skip":   True,
        "subspecialty_gate": None,
    },
    # 7. MG / O'Toole — DA + MG-qualified non-IR staff
    {
        "block_id":   "mg",
        "label":      "MG / O'Toole",
        "config":     MG_CONFIG,
        "priority":   7,
        "interactive_prompt": "Schedule MG/O'Toole assignments?",
        "can_skip":   True,
        "subspecialty_gate": "mg",
    },
    # 8. Weekend inpatient — non-IR pool, back-to-back avoidance
    {
        "block_id":   "inpatient_weekend",
        "label":      "Weekend Inpatient (M0_WEEKEND, EP, Dx-CALL)",
        "config":     INPATIENT_WEEKEND_CONFIG,
        "priority":   8,
        "interactive_prompt": "Schedule weekend inpatient block?",
        "can_skip":   True,
        "subspecialty_gate": None,
    },
]

# ---------------------------------------------------------------------------
# Constraint Weights
# ---------------------------------------------------------------------------
CONSTRAINT_WEIGHTS: Dict[str, Any] = {
    "back_to_back_weekend":  {"severity": "soft", "penalty": 100},
    "vacation_assignment":   {"severity": "hard", "penalty": 9999},
    "double_booking":        {"severity": "hard", "penalty": 9999},
    "subspecialty_mismatch": {"severity": "hard", "penalty": 9999},
    "ir_pool_gate":          {"severity": "hard", "penalty": 9999},
    "mercy_pool_gate":       {"severity": "hard", "penalty": 9999},
    "weekend_pool_gate":     {"severity": "hard", "penalty": 9999},
    "fte_overload":          {"severity": "soft", "penalty": 50},
    "workload_cv_exceeded":  {"severity": "soft", "penalty": 25},
}

# ---------------------------------------------------------------------------
# Fairness Targets
# ---------------------------------------------------------------------------
FAIRNESS_TARGETS: Dict[str, Any] = {
    "cv_target": 0.10,
    "max_deviation_from_mean": 0.20,
    "weighted_hours": True,
    "per_shift_cv_targets": {
        "M0": 0.10, "M1": 0.10, "M2": 0.10, "M3": 0.10,
        "IR-1": 0.10, "IR-2": 0.10, "IR-CALL": 0.10,
    },
}

# ---------------------------------------------------------------------------
# Fixed Subspecialty Assignments (outside rotation engine)
# ---------------------------------------------------------------------------
FIXED_SUBSPECIALTY_ASSIGNMENTS: Dict[str, List[str]] = {
    "Skull Base": ["JuanCarlos Vera", "James Cooper", "Brian Trinh"],
    "Cardiac":    ["John Johnson", "Brian Trinh"],
    "O'Toole":    ["Derrick Allen", "Kriti Rishi", "Rowena Tena"],
}

# ---------------------------------------------------------------------------
# QGenda task name → engine shift name aliases
# ---------------------------------------------------------------------------
QGENDA_TASK_ALIASES: Dict[str, str] = {
    "Mercy 0 (M0)":       "M0",
    "Mercy 1 (M1)":       "M1",
    "Mercy 2 (M2)":       "M2",
    "Mercy 3 (M3)":       "M3",
    "IR-1":               "IR-1",
    "IR-2":               "IR-2",
    "IR-CALL":            "IR-CALL",
    "IR-CALL (RMG)":      "IR-CALL",
    "PVH IR":             "PVH-IR",
    "EP 0800-1430":       "EP",
    "LP 1400-2200":       "LP",
    "Dx-CALL1400-2200":   "Dx-CALL",
    "OFF ALL DAY":        "OFF ALL DAY",
    "VACATION":           "VACATION",
    "Skull Base":         "Skull Base",
    "Cardiac":            "Cardiac",
    "O'Toole":            "O'Toole",
    "Remote General":     "Gen-Mercy",
    "CBCC General":       "Gen-Mercy",
}
