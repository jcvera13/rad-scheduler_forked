"""
schedule_config.py — Complete Rotation Pool & Shift Configuration

Derived from real QGenda data (Jan–Mar 2026) + explicit pool rules.

POOL RULES
──────────
  IR pool (DA, SS, SF, TR):
    ✅  IR-1, IR-2, IR-CALL          (participates_ir)
    ✅  Gen assignments               (Remote Gen, site Gen — participates_gen)
    ✅  DA only: O'Toole / Breast     (participates_mg)
    ❌  M0, M1, M2, M3               (exclude_ir = True on mercy blocks)
    ❌  EP, LP, Dx-CALL, M0_WEEKEND   (exclude_ir = True on weekend blocks)
    ❌  MRI / PET / Breast outpatient (only Gen for SS/SF/TR)

  Non-IR pool (15 radiologists):
    ✅  M0, M1, M2, M3, EP, Dx-CALL  (participates_mercy / participates_weekend)
    ✅  Gen assignments               (participates_gen)
    ✅  MRI outpatient if MRI tag     (subspecialty gate: MRI)
    ✅  Breast/O'Toole if MG tag      (subspecialty gate: MG)
    ✅  PET if PET tag                (subspecialty gate: PET)
    ❌  IR-1, IR-2, IR-CALL
"""

import re
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# QGenda task name → engine shift code
# Regex-based: first matching pattern wins.
# Patterns are applied to the raw QGenda task string (case-insensitive).
# ---------------------------------------------------------------------------
QGENDA_TASK_REGEX_ALIASES: List[tuple] = [
    # ── IR ──────────────────────────────────────────────────────────────────
    (r"ir-call|ir call|rmg",                        "IR-CALL"),
    (r"mercy hospital ir-1|mercy.*ir-1|ir-1",        "IR-1"),
    (r"mercy hospital ir-2|mercy.*ir-2|ir-2",        "IR-2"),
    (r"pvh.*ir|providence.*ir",                      "PVH-IR"),

    # ── Mercy inpatient ─────────────────────────────────────────────────────
    (r"mercy 0 weekend|m0 weekend",                  "M0_WEEKEND"),
    (r"mercy 0|m0.*(remote)?.*0700",                 "M0"),
    (r"mercy 1|m1.*(on.?site)",                      "M1"),
    (r"mercy 2|m2.*(remote)",                        "M2"),
    (r"mercy 3|m3.*(remote)",                        "M3"),

    # ── Weekend calls ────────────────────────────────────────────────────────
    (r"late person call|dx-call|dx call",            "Dx-CALL"),
    (r"early person call|ep 0800",                   "EP"),

    # ── Weekend outpatient ───────────────────────────────────────────────────
    (r"weekend.*mri|mri.*weekend",                   "Wknd-MRI"),
    (r"weekend.*pet|pet.*weekend",                   "Wknd-PET"),

    # ── Remote outpatient ────────────────────────────────────────────────────
    (r"ihs remote mri|remote mri",                   "Remote-MRI"),
    (r"ihs remote breast|remote breast",             "Remote-Breast"),
    (r"ihs remote pet|remote pet",                   "Remote-PET"),
    (r"ihs remote general|remote general",           "Remote-Gen"),

    # ── Washington site ──────────────────────────────────────────────────────
    (r"washington.*mri|wash.*mri.*0800",             "Wash-MRI"),
    (r"washington.*breast|wash.*breast",             "Wash-Breast"),
    (r"washington.*general|wash.*gen",               "Wash-Gen"),

    # ── Poway site ───────────────────────────────────────────────────────────
    (r"poway.*pet",                                   "Poway-PET"),
    (r"poway.*mri",                                   "Poway-MRI"),
    (r"poway.*general|poway.*gen",                   "Poway-Gen"),

    # ── Encinitas site ───────────────────────────────────────────────────────
    (r"encinitas.*breast|enc.*breast",               "Enc-Breast"),
    (r"encinitas.*mri|enc.*mri",                     "Enc-MRI"),
    (r"encinitas.*general|enc.*gen",                 "Enc-Gen"),

    # ── National City site ───────────────────────────────────────────────────
    (r"national city.*general|nc.*gen",              "NC-Gen"),
    (r"national city.*pet|nc.*pet",                  "NC-PET"),
    (r"national city.*breast|nc.*breast",            "NC-Breast"),
    (r"national city.*mri|nc.*mri",                  "NC-MRI"),

    # ── Fixed subspecialty (concurrent, not rotation-managed) ────────────────
    (r"o'toole|otoole|scripps.*toole",               "O'Toole"),
    (r"skull base",                                   "Skull-Base"),
    (r"cardiac imaging|cardiac",                      "Cardiac"),

    # ── Admin / off ──────────────────────────────────────────────────────────
    (r"off all day",                                  "OFF"),
    (r"vacation",                                     "VACATION"),
    (r"administrative|admin",                         "ADMIN"),
    (r"extra full day",                               "Extra-Day"),
    (r"no call",                                      "No-Call"),
    (r"no ep",                                        "No-EP"),
]

_compiled_aliases = [(re.compile(pat, re.IGNORECASE), code)
                     for pat, code in QGENDA_TASK_REGEX_ALIASES]


def normalize_task_name(raw: str) -> str:
    """
    Map a raw QGenda task string to an engine shift code using regex.
    Falls back to the raw string if no pattern matches.

    Examples:
        "Mercy 0 (M0 (remote) 0700-0800, 1130-1230)" → "M0"
        "IHS Remote General (Remote General)"          → "Remote-Gen"
        "IHS Poway PET x1680 (Poway PET 0800-1700)"   → "Poway-PET"
        "gen", "general", "Remote General"             → "Remote-Gen"
    """
    raw = raw.strip()
    for pattern, code in _compiled_aliases:
        if pattern.search(raw):
            return code
    # Fallback: bare "gen" or "general" → Remote-Gen
    if re.match(r"^gen(eral)?$", raw, re.IGNORECASE):
        return "Remote-Gen"
    return raw


# ---------------------------------------------------------------------------
# Shift Definitions
# pool:     'mercy' | 'ir' | 'gen' | 'mri' | 'breast' | 'pet' | 'weekend' | None
# requires: subspecialty tag that must be in person's subspecialties list
# ---------------------------------------------------------------------------
SHIFT_DEFINITIONS: Dict[str, Dict[str, Any]] = {

    # ── Mercy inpatient (non-IR pool only) ───────────────────────────────────
    "M0":          {"hours": 2,   "weight": 0.25, "pool": "mercy",   "requires": None,
                    "description": "Mercy helper 0700-0800/1130-1230 (remote)"},
    "M1":          {"hours": 8,   "weight": 1.00, "pool": "mercy",   "requires": None,
                    "description": "Mercy day 0800-1600 (on-site)"},
    "M2":          {"hours": 8,   "weight": 1.00, "pool": "mercy",   "requires": None,
                    "description": "Mercy remote 0930-1730"},
    "M3":          {"hours": 6,   "weight": 0.75, "pool": "mercy",   "requires": None,
                    "description": "Mercy evening 1600-2200 (remote)"},

    # ── IR (IR pool only) ─────────────────────────────────────────────────────
    "IR-1":        {"hours": 8,   "weight": 1.00, "pool": "ir",      "requires": "ir",
                    "description": "Mercy Hospital IR-1 0800-1600"},
    "IR-2":        {"hours": 8,   "weight": 1.00, "pool": "ir",      "requires": "ir",
                    "description": "Mercy Hospital IR-2 0900-1700"},
    "IR-CALL":     {"hours": 8,   "weight": 1.00, "pool": "ir",      "requires": "ir",
                    "description": "IR Call / RMG after-hours"},
    "PVH-IR":      {"hours": 8,   "weight": 1.00, "pool": "ir",      "requires": "ir",
                    "description": "Providence IR"},

    # ── Weekend inpatient (non-IR pool only) ─────────────────────────────────
    "M0_WEEKEND":  {"hours": 2,   "weight": 0.25, "pool": "weekend", "requires": None,
                    "description": "Mercy 0 Weekend"},
    "EP":          {"hours": 6.5, "weight": 0.81, "pool": "weekend", "requires": None,
                    "description": "Early Person 0800-1430 (on-site Sat / remote Sun)"},
    "Dx-CALL":     {"hours": 8,   "weight": 1.00, "pool": "weekend", "requires": None,
                    "description": "Late Person Call 1400-2200 (remote)"},

    # ── Remote outpatient ─────────────────────────────────────────────────────
    # Gen: all staff with Gen tag (IR + non-IR)
    "Remote-Gen":  {"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS Remote General"},
    # MRI: non-IR MRI-tagged staff
    "Remote-MRI":  {"hours": 8,   "weight": 1.00, "pool": "mri",     "requires": "MRI",
                    "description": "IHS Remote MRI"},
    # Breast: MG-tagged staff (DA + non-IR with MG)
    "Remote-Breast":{"hours": 8,  "weight": 1.00, "pool": "breast",  "requires": "MG",
                    "description": "IHS Remote Breast & US"},
    # PET: PET-tagged non-IR staff
    "Remote-PET":  {"hours": 8,   "weight": 1.00, "pool": "pet",     "requires": "PET",
                    "description": "IHS Remote PET"},

    # ── Washington site ───────────────────────────────────────────────────────
    "Wash-MRI":    {"hours": 8,   "weight": 1.00, "pool": "mri",     "requires": "MRI",
                    "description": "IHS Washington MRI 0800-1700"},
    "Wash-Breast": {"hours": 8,   "weight": 1.00, "pool": "breast",  "requires": "MG",
                    "description": "IHS Washington Breast & US 0800-1700"},
    "Wash-Gen":    {"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS Washington General"},

    # ── Poway site ────────────────────────────────────────────────────────────
    "Poway-PET":   {"hours": 8,   "weight": 1.00, "pool": "pet",     "requires": "PET",
                    "description": "IHS Poway PET 0800-1700"},
    "Poway-MRI":   {"hours": 8,   "weight": 1.00, "pool": "mri",     "requires": "MRI",
                    "description": "IHS Poway MRI 0800-1700"},
    "Poway-Gen":   {"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS Poway General 0800-1700"},

    # ── Encinitas site ────────────────────────────────────────────────────────
    "Enc-Breast":  {"hours": 8,   "weight": 1.00, "pool": "breast",  "requires": "MG",
                    "description": "IHS Encinitas Breast & US 0800-1700"},
    "Enc-MRI":     {"hours": 8,   "weight": 1.00, "pool": "mri",     "requires": "MRI",
                    "description": "IHS Encinitas MRI 0800-1700"},
    "Enc-Gen":     {"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS Encinitas General 0800-1700"},

    # ── National City site ────────────────────────────────────────────────────
    "NC-Gen":      {"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS National City General 0800-1700"},
    "NC-PET":      {"hours": 8,   "weight": 1.00, "pool": "pet",     "requires": "PET",
                    "description": "IHS National City PET 0800-1700"},
    "NC-Breast":   {"hours": 8,   "weight": 1.00, "pool": "breast",  "requires": "MG",
                    "description": "IHS National City Breast 0800-1700"},
    "NC-MRI":      {"hours": 8,   "weight": 1.00, "pool": "mri",     "requires": "MRI",
                    "description": "IHS National City MRI 0800-1700"},

    # ── Weekend outpatient ────────────────────────────────────────────────────
    "Wknd-MRI":    {"hours": 8,   "weight": 1.00, "pool": "mri",     "requires": "MRI",
                    "description": "Weekend IHS MRI"},
    "Wknd-PET":    {"hours": 8,   "weight": 1.00, "pool": "pet",     "requires": "PET",
                    "description": "Weekend IHS PET"},

    # ── O'Toole (MG-qualified + DA) ───────────────────────────────────────────
    "O'Toole":     {"hours": 8,   "weight": 1.00, "pool": "mg",      "requires": "MG",
                    "description": "Scripps O'Toole Breast Center 0730-1630 (Tue/Wed/Fri)"},

    # ── Fixed subspecialty — NOT managed by rotation engine ───────────────────
    "Skull-Base":  {"hours": 8,   "weight": 0.00, "pool": None,      "requires": "neuro",
                    "description": "Skull Base (concurrent fixed)"},
    "Cardiac":     {"hours": 8,   "weight": 0.00, "pool": None,      "requires": "cardiac",
                    "description": "Cardiac Imaging (concurrent fixed)"},

    # ── Misc ──────────────────────────────────────────────────────────────────
    "OFF":         {"hours": 0,   "weight": 0.00, "pool": None,      "requires": None},
    "VACATION":    {"hours": 0,   "weight": 0.00, "pool": None,      "requires": None},
    "ADMIN":       {"hours": 0,   "weight": 0.00, "pool": None,      "requires": None},
    "Extra-Day":   {"hours": 8,   "weight": 1.00, "pool": None,      "requires": None},
    "No-Call":     {"hours": 0,   "weight": 0.00, "pool": None,      "requires": None},
    "No-EP":       {"hours": 0,   "weight": 0.00, "pool": None,      "requires": None},
}

# ---------------------------------------------------------------------------
# Pool Config Templates
# ---------------------------------------------------------------------------
def _mercy_cfg(shift_names, weights, cursor_key="inpatient_weekday", n_per_day=1):
    return {
        "pool_filter":       "participates_mercy",
        "exclude_ir":        True,          # HARD: IR staff never in mercy/weekend
        "shift_names":       shift_names,
        "shift_weights":     weights,
        "shifts_per_period": n_per_day,
        "cursor_key":        cursor_key,
        "avoid_previous":    False,
        "allow_fallback":    True,
        "use_weighted_cursor": True,
        "target_cv":         0.10,
        "schedule_type":     "weekday",
    }

def _weekend_cfg(shift_names, weights):
    return {
        "pool_filter":       "participates_weekend",
        "exclude_ir":        True,          # HARD: IR staff never in EP/LP/Dx-CALL
        "shift_names":       shift_names,
        "shift_weights":     weights,
        "shifts_per_period": len(shift_names),
        "cursor_key":        "inpatient_weekend",
        "avoid_previous":    True,
        "allow_fallback":    True,
        "use_weighted_cursor": True,
        "target_cv":         0.10,
        "schedule_type":     "weekend",
    }

def _ir_cfg(shift_names, weights, cursor_key="ir_weekday"):
    return {
        "pool_filter":       "participates_ir",
        "exclude_ir":        False,
        "shift_names":       shift_names,
        "shift_weights":     weights,
        "shifts_per_period": len(shift_names),
        "cursor_key":        cursor_key,
        "avoid_previous":    False,
        "allow_fallback":    True,
        "use_weighted_cursor": True,
        "target_cv":         0.10,
        "schedule_type":     "weekday",
    }

def _gen_cfg(cursor_key, exclude_ir=False):
    """Gen assignments — all Gen-tagged staff. exclude_ir=True for non-IR gen blocks."""
    return {
        "pool_filter":        "participates_gen",
        "exclude_ir":         exclude_ir,
        "subspecialty_gate":  "gen",         # requires 'Gen' tag (lowercase matched)
        "shift_names":        ["Remote-Gen"],
        "shift_weights":      {"Remote-Gen": 1.00},
        "shifts_per_period":  1,
        "cursor_key":         cursor_key,
        "avoid_previous":     False,
        "allow_fallback":     True,
        "use_weighted_cursor": True,
        "target_cv":          0.10,
        "schedule_type":      "weekday",
    }

def _outpt_cfg(shift_names, weights, cursor_key, subspecialty, schedule_type="weekday",
               exclude_ir=True, n_per_day=1):
    return {
        "pool_filter":        "participates_gen",   # broad; gate does real filtering
        "exclude_ir":         exclude_ir,
        "subspecialty_gate":  subspecialty,
        "shift_names":        shift_names,
        "shift_weights":      weights,
        "shifts_per_period":  n_per_day,
        "cursor_key":         cursor_key,
        "avoid_previous":     False,
        "allow_fallback":     True,
        "use_weighted_cursor": True,
        "target_cv":          0.10,
        "schedule_type":      schedule_type,
    }

# ---------------------------------------------------------------------------
# Block configs
# ---------------------------------------------------------------------------
IR_WEEKDAY_CONFIG         = _ir_cfg(["IR-1","IR-2"], {"IR-1":1.00,"IR-2":1.00})
IR_CALL_CONFIG            = _ir_cfg(["IR-CALL"],     {"IR-CALL":1.00}, "ir_call")

M3_CONFIG  = _mercy_cfg(["M3"],     {"M3":0.75})
M0_CONFIG  = _mercy_cfg(["M0"],     {"M0":0.25})
M1M2_CONFIG= _mercy_cfg(["M1","M2"],{"M1":1.00,"M2":1.00}, n_per_day=2)

WEEKEND_CONFIG = _weekend_cfg(
    ["M0_WEEKEND","EP","Dx-CALL"],
    {"M0_WEEKEND":0.25,"EP":0.81,"Dx-CALL":1.00}
)

# Gen — two separate cursors, one per pool
GEN_NONIR_CONFIG = {**_gen_cfg("gen_nonir", exclude_ir=True),
                    "description": "Remote Gen (non-IR staff)"}
GEN_IR_CONFIG    = {**_gen_cfg("gen_ir",    exclude_ir=False),
                    "pool_filter": "participates_ir",
                    "description": "Remote Gen (IR staff)"}

# Outpatient remote
REMOTE_MRI_CONFIG    = _outpt_cfg(["Remote-MRI"],   {"Remote-MRI":1.00},   "remote_mri",   "mri")
REMOTE_BREAST_CONFIG = _outpt_cfg(["Remote-Breast"],{"Remote-Breast":1.00},"remote_breast","mg",
                                   exclude_ir=False)  # DA does Remote Breast
REMOTE_PET_CONFIG    = _outpt_cfg(["Remote-PET"],   {"Remote-PET":1.00},   "remote_pet",   "pet")

# Site-based — MRI
WASH_MRI_CONFIG  = _outpt_cfg(["Wash-MRI"], {"Wash-MRI":1.00}, "site_mri", "mri")
ENC_MRI_CONFIG   = _outpt_cfg(["Enc-MRI"],  {"Enc-MRI":1.00},  "site_mri", "mri")
POWAY_MRI_CONFIG = _outpt_cfg(["Poway-MRI"],{"Poway-MRI":1.00},"site_mri", "mri")

# Site-based — Breast
WASH_BREAST_CONFIG  = _outpt_cfg(["Wash-Breast"], {"Wash-Breast":1.00}, "site_breast","mg",
                                  exclude_ir=False)  # DA eligible
ENC_BREAST_CONFIG   = _outpt_cfg(["Enc-Breast"],  {"Enc-Breast":1.00},  "site_breast","mg",
                                  exclude_ir=True)   # DA not on this one in data
POWAY_BREAST_CONFIG = _outpt_cfg(["NC-Breast"],   {"NC-Breast":1.00},   "site_breast","mg",
                                  exclude_ir=True)

# Site-based — PET
POWAY_PET_CONFIG = _outpt_cfg(["Poway-PET"],{"Poway-PET":1.00},"site_pet","pet")

# Site-based — Gen (IR staff eligible for all Gen sites)
ENC_GEN_CONFIG   = _outpt_cfg(["Enc-Gen"], {"Enc-Gen":1.00}, "site_gen","gen", exclude_ir=False)
POWAY_GEN_CONFIG = _outpt_cfg(["Poway-Gen"],{"Poway-Gen":1.00},"site_gen","gen",exclude_ir=False)
NC_GEN_CONFIG    = _outpt_cfg(["NC-Gen"],  {"NC-Gen":1.00},  "site_gen","gen", exclude_ir=False)

# O'Toole — MG-tagged staff (DA + non-IR MG)
OTOOLE_CONFIG = {
    "pool_filter":        "participates_mg",
    "exclude_ir":         False,             # DA is MG-qualified
    "subspecialty_gate":  "mg",
    "shift_names":        ["O'Toole"],
    "shift_weights":      {"O'Toole": 1.00},
    "shifts_per_period":  1,
    "cursor_key":         "otoole",
    "avoid_previous":     False,
    "allow_fallback":     True,
    "use_weighted_cursor": True,
    "target_cv":          0.10,
    "schedule_type":      "weekday",
    "description":        "Scripps O'Toole (Tue/Wed/Fri only)",
}

# Weekend outpatient
WKND_MRI_CONFIG = _outpt_cfg(["Wknd-MRI"],{"Wknd-MRI":1.00},"wknd_mri","mri",
                               schedule_type="weekend")
WKND_PET_CONFIG = _outpt_cfg(["Wknd-PET"],{"Wknd-PET":1.00},"wknd_pet","pet",
                               schedule_type="weekend")

# ---------------------------------------------------------------------------
# SCHEDULING_BLOCKS — Priority order
# exclude_ir=True means IR staff are HARD-excluded from that block's pool
# ---------------------------------------------------------------------------
SCHEDULING_BLOCKS: List[Dict[str, Any]] = [

    # ── 1. IR weekday — IR pool only ─────────────────────────────────────────
    {"block_id": "ir_weekday", "label": "IR-1 / IR-2",
     "config": IR_WEEKDAY_CONFIG, "priority": 1,
     "can_skip": False, "exclude_ir": False,
     "interactive_prompt": "Schedule IR shifts (IR-1, IR-2)?"},

    # ── 2. IR-CALL — IR pool only ─────────────────────────────────────────────
    {"block_id": "ir_call", "label": "IR-CALL",
     "config": IR_CALL_CONFIG, "priority": 2,
     "can_skip": True, "exclude_ir": False,
     "interactive_prompt": "Schedule IR-CALL?"},

    # ── 3–5. Mercy inpatient — NON-IR ONLY (exclude_ir=True enforced) ─────────
    {"block_id": "m3_weekday", "label": "M3 Evening",
     "config": M3_CONFIG, "priority": 3,
     "can_skip": False, "exclude_ir": True,
     "interactive_prompt": "Schedule M3 (evening 1600-2200)?"},

    {"block_id": "m0_weekday", "label": "M0 Helper",
     "config": M0_CONFIG, "priority": 4,
     "can_skip": False, "exclude_ir": True,
     "interactive_prompt": "Schedule M0 (helper 0700-0800/1130-1230)?"},

    {"block_id": "m1m2_weekday", "label": "M1 + M2",
     "config": M1M2_CONFIG, "priority": 5,
     "can_skip": False, "exclude_ir": True,
     "interactive_prompt": "Schedule M1 and M2?"},

    # ── 6. Gen (non-IR staff) ────────────────────────────────────────────────
    {"block_id": "gen_nonir", "label": "Remote Gen (non-IR)",
     "config": GEN_NONIR_CONFIG, "priority": 6,
     "can_skip": True, "exclude_ir": True, "concurrent_ok": True,
     "interactive_prompt": "Schedule Gen diagnostic (non-IR staff)?"},

    # ── 7. Gen (IR staff) ─────────────────────────────────────────────────────
    {"block_id": "gen_ir", "label": "Remote Gen (IR staff)",
     "config": GEN_IR_CONFIG, "priority": 7,
     "can_skip": True, "exclude_ir": False,
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Gen diagnostic (IR staff)?"},

    # ── 8. Remote outpatient ─────────────────────────────────────────────────
    {"block_id": "remote_mri", "label": "Remote MRI",
     "config": REMOTE_MRI_CONFIG, "priority": 8,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "mri",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Remote MRI?"},

    {"block_id": "remote_breast", "label": "Remote Breast",
     "config": REMOTE_BREAST_CONFIG, "priority": 9,
     "can_skip": True, "exclude_ir": False,  # DA eligible
     "subspecialty_gate": "mg",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Remote Breast?"},

    {"block_id": "remote_pet", "label": "Remote PET",
     "config": REMOTE_PET_CONFIG, "priority": 10,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "pet",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Remote PET?"},

    # ── 9. Site-based MRI ────────────────────────────────────────────────────
    {"block_id": "wash_mri", "label": "Washington MRI",
     "config": WASH_MRI_CONFIG, "priority": 11,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "mri",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Washington MRI?"},

    {"block_id": "enc_mri", "label": "Encinitas MRI",
     "config": ENC_MRI_CONFIG, "priority": 12,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "mri",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Encinitas MRI?"},

    {"block_id": "poway_mri", "label": "Poway MRI",
     "config": POWAY_MRI_CONFIG, "priority": 13,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "mri",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Poway MRI?"},

    # ── 10. Site-based Breast ─────────────────────────────────────────────────
    {"block_id": "wash_breast", "label": "Washington Breast",
     "config": WASH_BREAST_CONFIG, "priority": 14,
     "can_skip": True, "exclude_ir": False,  # DA eligible
     "subspecialty_gate": "mg",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Washington Breast?"},

    {"block_id": "enc_breast", "label": "Encinitas Breast",
     "config": ENC_BREAST_CONFIG, "priority": 15,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "mg",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Encinitas Breast?"},

    # ── 11. Site-based PET ────────────────────────────────────────────────────
    {"block_id": "poway_pet", "label": "Poway PET",
     "config": POWAY_PET_CONFIG, "priority": 16,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "pet",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Poway PET?"},

    # ── 12. Site-based Gen (IR-inclusive) ────────────────────────────────────
    {"block_id": "enc_gen", "label": "Encinitas Gen",
     "config": ENC_GEN_CONFIG, "priority": 17,
     "can_skip": True, "exclude_ir": False,
     "subspecialty_gate": "gen",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Encinitas Gen?"},

    {"block_id": "poway_gen", "label": "Poway Gen",
     "config": POWAY_GEN_CONFIG, "priority": 18,
     "can_skip": True, "exclude_ir": False,
     "subspecialty_gate": "gen",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Poway Gen?"},

    {"block_id": "nc_gen", "label": "NC Gen",
     "config": NC_GEN_CONFIG, "priority": 19,
     "can_skip": True, "exclude_ir": False,
     "subspecialty_gate": "gen",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule National City Gen?"},

    # ── 13. O'Toole (Tue/Wed/Fri) ────────────────────────────────────────────
    {"block_id": "otoole", "label": "O'Toole",
     "config": OTOOLE_CONFIG, "priority": 20,
     "can_skip": True, "exclude_ir": False,  # DA eligible
     "subspecialty_gate": "mg",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule O'Toole?"},

    # ── 14. Weekend inpatient — NON-IR ONLY ───────────────────────────────────
    {"block_id": "inpatient_weekend", "label": "Weekend Inpatient (M0/EP/Dx-CALL)",
     "config": WEEKEND_CONFIG, "priority": 21,
     "can_skip": True, "exclude_ir": True,
     "concurrent_ok": True,
     "interactive_prompt": "Schedule weekend inpatient block?"},

    # ── 15. Weekend outpatient ────────────────────────────────────────────────
    {"block_id": "wknd_mri", "label": "Weekend MRI",
     "config": WKND_MRI_CONFIG, "priority": 22,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "mri",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Weekend MRI?"},

    {"block_id": "wknd_pet", "label": "Weekend PET",
     "config": WKND_PET_CONFIG, "priority": 23,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "pet",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Weekend PET?"},
]

# ---------------------------------------------------------------------------
# Cursor state keys — all blocks need an entry in cursor_state.json
# ---------------------------------------------------------------------------
ALL_CURSOR_KEYS = sorted({
    b["config"]["cursor_key"] for b in SCHEDULING_BLOCKS
})

# ---------------------------------------------------------------------------
# Fairness / constraint config
# ---------------------------------------------------------------------------
CONSTRAINT_WEIGHTS: Dict[str, Any] = {
    "back_to_back_weekend":  {"severity": "soft",  "penalty": 100},
    "vacation_assignment":   {"severity": "hard",  "penalty": 9999},
    "double_booking":        {"severity": "hard",  "penalty": 9999},
    "subspecialty_mismatch": {"severity": "hard",  "penalty": 9999},
    "ir_pool_gate":          {"severity": "hard",  "penalty": 9999},
    "mercy_pool_gate":       {"severity": "hard",  "penalty": 9999},
    "weekend_pool_gate":     {"severity": "hard",  "penalty": 9999},
    "workload_cv_exceeded":  {"severity": "soft",  "penalty": 25},
}

FAIRNESS_TARGETS: Dict[str, Any] = {
    "cv_target":            0.10,
    "max_deviation":        0.20,
    "weighted_hours":       True,
}

# ---------------------------------------------------------------------------
# Fixed subspecialty assignments (concurrent — not in rotation engine)
# ---------------------------------------------------------------------------
FIXED_SUBSPECIALTY_ASSIGNMENTS: Dict[str, List[str]] = {
    "Skull-Base": ["JuanCarlos Vera", "James Cooper", "Brian Trinh"],
    "Cardiac":    ["John Johnson", "Brian Trinh"],
}

# O'Toole runs Tue/Wed/Fri only
OTOOLE_WEEKDAYS = {1, 2, 4}   # Mon=0 … Fri=4
