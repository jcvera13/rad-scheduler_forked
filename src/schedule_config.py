"""
schedule_config.py — Complete Rotation Pool & Shift Configuration

Derived from real QGenda data (Mar–May 2026) + explicit pool rules.

ROSTER (config/roster_key.csv)
──────────────────────────────
  Pool flags: participates_mercy, participates_ir, participates_weekend,
              participates_gen, participates_outpatient, participates_mg,
              participates_MRI, participates_PET (optional; inferred from
              subspecialties if column missing).
  Subspecialty tags (comma-separated): Gen, MG, MRI, MRI+Proc, PET, ir, neuro,
              cardiac, nm; plus preference/site tags Breast-Proc (Wash/Enc Breast,
              O'Toole), North_Gen+Cont (Enc/Poway Gen), South_Gen+Cont (NC Gen).
  Pool filtering uses strict subspecialty_gate match (engine); repair may use
  participates_MRI/participates_PET and preference tags when filling unfilled slots.

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
    ✅  Gen assignments               (participates_gen; gate: Gen)
    ✅  MRI outpatient                (subspecialty_gate: MRI or MRI+Proc per shift)
    ✅  Breast/O'Toole                (subspecialty_gate: MG)
    ✅  PET                           (subspecialty_gate: PET)
    ❌  IR-1, IR-2, IR-CALL

2-WEEK CYCLE (anchored to nc_week_anchor in dry_run.py / schedule_blocks)
──────────────────────────────────────────────────────────────────────────
  NC Week (week with National City IHS coverage):
    • NC-Gen: Mon–Fri (1 person, onsite)
    • Remote-Gen-1: Mon, Tue, Wed, Fri (1 person, remote) — no Thu in NC weeks
    • All fixed-day site blocks run as normal (Enc-MRI Mon, Enc-Breast Tue/Wed, etc.)

  KM Week (Kearny Mesa week — no NC-Gen):
    • Remote-Gen-1: Mon, Tue, Wed, Thu, Fri (1 person, remote)
    • Remote-Gen-2: Mon, Tue only (2nd simultaneous remote Gen slot)
    • NC-Gen block is skipped entirely

  Default anchor: 2026-03-02 (Monday of first NC week in real schedule).
  Engine key: block config key "week_type": "nc"|"km"|None

FIXED DAY-OF-WEEK (site assignments — apply every week):
  Enc-MRI:    Mon
  Enc-Breast: Tue, Wed
  Enc-Gen:    Thu, Fri
  Poway-Gen:  Mon, Tue
  Poway-MRI:  Wed
  Poway-PET:  Thu, Fri
  Wash-Breast: Mon, Fri
  Wash-MRI:   Tue, Wed, Thu

IR-CALL WEEKEND MIRROR:
  Same IR staff covers Fri + Sat + Sun of each weekend.
  Engine: block schedules on Fridays (allowed_weekdays={4}), mirror_weekend=True
  copies each Fri assignment to the following Sat and Sun.
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
                    "description": "IR Call / RMG — Fri+Sat+Sun (same person, mirrored)"},
    "PVH-IR":      {"hours": 8,   "weight": 1.00, "pool": "ir",      "requires": "ir",
                    "description": "Providence IR"},

    # ── Weekend inpatient (non-IR pool only) ─────────────────────────────────
    "M0_WEEKEND":  {"hours": 2,   "weight": 0.25, "pool": "weekend", "requires": None,
                    "description": "Mercy 0 Weekend"},
    "EP":          {"hours": 6.5, "weight": 0.81, "pool": "weekend", "requires": None,
                    "description": "Early Person 0800-1430 (on-site Sat / remote Sun)"},
    "Dx-CALL":     {"hours": 8,   "weight": 1.00, "pool": "weekend", "requires": None,
                    "description": "Late Person Call 1400-2200 (remote)"},

    # ── Remote Gen (numbered to allow simultaneous slots on KM weeks) ─────────
    # Remote-Gen-1: primary slot (both NC and KM weeks).
    # Remote-Gen-2: second simultaneous slot (KM weeks Mon/Tue only).
    # Remote-Gen:   backward-compat alias (used for QGenda import normalisation).
    "Remote-Gen":  {"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS Remote General (QGenda alias)"},
    "Remote-Gen-1":{"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS Remote General — slot 1 (every applicable weekday)"},
    "Remote-Gen-2":{"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS Remote General — slot 2 (KM weeks Mon/Tue only)"},

    # ── Remote outpatient ─────────────────────────────────────────────────────
    "Remote-MRI":  {"hours": 8,   "weight": 1.00, "pool": "mri",     "requires": "MRI",
                    "description": "IHS Remote MRI"},
    "Remote-Breast":{"hours": 8,  "weight": 1.00, "pool": "breast",  "requires": "MG",
                    "description": "IHS Remote Breast & US"},
    "Remote-PET":  {"hours": 8,   "weight": 1.00, "pool": "pet",     "requires": "PET",
                    "description": "IHS Remote PET"},

    # ── Washington site ───────────────────────────────────────────────────────
    "Wash-MRI":    {"hours": 8,   "weight": 1.00, "pool": "mri",     "requires": "MRI+Proc",
                    "description": "IHS Washington MRI 0800-1700 (Tue/Wed/Thu)"},
    "Wash-Breast": {"hours": 8,   "weight": 1.00, "pool": "breast",  "requires": "MG",
                    "description": "IHS Washington Breast & US 0800-1700 (Mon/Fri)"},
    "Wash-Gen":    {"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS Washington General"},

    # ── Poway site ────────────────────────────────────────────────────────────
    "Poway-PET":   {"hours": 8,   "weight": 1.00, "pool": "pet",     "requires": "PET",
                    "description": "IHS Poway PET 0800-1700 (Thu/Fri)"},
    "Poway-MRI":   {"hours": 8,   "weight": 1.00, "pool": "mri",     "requires": "MRI",
                    "description": "IHS Poway MRI 0800-1700 (Wed)"},
    "Poway-Gen":   {"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS Poway General 0800-1700 (Mon/Tue)"},

    # ── Encinitas site ────────────────────────────────────────────────────────
    "Enc-Breast":  {"hours": 8,   "weight": 1.00, "pool": "breast",  "requires": "MG",
                    "description": "IHS Encinitas Breast & US 0800-1700 (Tue/Wed)"},
    "Enc-MRI":     {"hours": 8,   "weight": 1.00, "pool": "mri",     "requires": "MRI",
                    "description": "IHS Encinitas MRI 0800-1700 (Mon)"},
    "Enc-Gen":     {"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS Encinitas General 0800-1700 (Thu/Fri)"},

    # ── National City site (NC weeks only) ────────────────────────────────────
    "NC-Gen":      {"hours": 8,   "weight": 1.00, "pool": "gen",     "requires": "Gen",
                    "description": "IHS National City General 0800-1700 (Mon–Fri, NC weeks)"},
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
                    "description": "Scripps O'Toole Breast Center 0730-1630 (Tue/Wed/Thu)"},

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

# Shifts that count as "one outpatient assignment" — at most one per person per day.
# Excludes inpatient (M0,M1,M2,M3), IR, weekend inpatient (EP,Dx-CALL,M0_WEEKEND),
# and fixed concurrent (Skull-Base, Cardiac). See docs/qgenda_integration.md.
# Remote-Gen-1 and Remote-Gen-2 are DIFFERENT people on the same day (KM Mon/Tue),
# so each person still gets at most one outpatient slot.
OUTPATIENT_SHIFTS: Set[str] = frozenset({
    "Remote-Gen", "Remote-Gen-1", "Remote-Gen-2",
    "Remote-MRI", "Remote-Breast", "Remote-PET",
    "Wash-MRI", "Wash-Breast", "Wash-Gen",
    "Poway-PET", "Poway-MRI", "Poway-Gen",
    "Enc-Breast", "Enc-MRI", "Enc-Gen",
    "NC-Gen", "NC-PET", "NC-Breast", "NC-MRI",
    "Wknd-MRI", "Wknd-PET",
    "O'Toole",
})


# ---------------------------------------------------------------------------
# Pool Config Templates (task grouping)
# ---------------------------------------------------------------------------

def _mercy_weekday_cfg(shift_names, weights, cursor_key="inpatient_weekday", n_per_day=1):
    return {
        "pool_filter":       "participates_mercy",
        "exclude_ir":        True,
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


def _mercy_weekend_cfg(shift_names, weights):
    return {
        "pool_filter":       "participates_weekend",
        "exclude_ir":        True,
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


def _outpt_cfg(shift_names, weights, cursor_key, subspecialty, schedule_type="weekday",
               exclude_ir=True, n_per_day=1):
    return {
        "pool_filter":        "participates_gen",
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

IR_WEEKDAY_CONFIG = _ir_cfg(["IR-1", "IR-2"], {"IR-1": 1.00, "IR-2": 1.00})

# IR-CALL: schedule on Fridays; engine mirrors same person to following Sat+Sun.
IR_CALL_CONFIG = {
    **_ir_cfg(["IR-CALL"], {"IR-CALL": 1.00}, "ir_call"),
    "allowed_weekdays": {4},          # Friday only — mirror_weekend copies to Sat+Sun
    "mirror_weekend":   True,         # engine: copy Fri assignment to Sat + Sun
    "description":      "IR-CALL (Fri+Sat+Sun, same person)",
}

# Mercy weekday (M0, M1, M2, M3)
M3_CONFIG   = _mercy_weekday_cfg(["M3"],      {"M3": 1.00})
M0_CONFIG   = _mercy_weekday_cfg(["M0"],      {"M0": 0.25})
M1M2_CONFIG = _mercy_weekday_cfg(["M1", "M2"],{"M1": 1.00, "M2": 1.00}, n_per_day=2)

# Mercy weekend (M0_WEEKEND, EP, Dx-CALL)
WEEKEND_CONFIG = _mercy_weekend_cfg(
    ["M0_WEEKEND", "EP", "Dx-CALL"],
    {"M0_WEEKEND": 0.25, "EP": 0.81, "Dx-CALL": 1.00},
)

# ---------------------------------------------------------------------------
# Fixed-day site blocks — each block has a unique cursor_key and allowed_weekdays
# set from the real QGenda schedule.
#
# Mon=0  Tue=1  Wed=2  Thu=3  Fri=4
# ---------------------------------------------------------------------------

# Washington site — Mon/Fri Breast, Tue/Wed/Thu MRI
WASH_BREAST_CONFIG = {
    **_outpt_cfg(["Wash-Breast"], {"Wash-Breast": 1.00}, "wash_breast", "mg",
                 exclude_ir=False),
    "allowed_weekdays": {0, 4},   # Mon, Fri
}
WASH_MRI_CONFIG = {
    **_outpt_cfg(["Wash-MRI"], {"Wash-MRI": 1.00}, "wash_mri", "mri+proc"),
    "allowed_weekdays": {1, 2, 3},  # Tue, Wed, Thu
}

# Encinitas site — Mon MRI, Tue/Wed Breast, Thu/Fri Gen
ENC_MRI_CONFIG = {
    **_outpt_cfg(["Enc-MRI"], {"Enc-MRI": 1.00}, "enc_mri", "mri"),
    "allowed_weekdays": {0},        # Mon
}
ENC_BREAST_CONFIG = {
    **_outpt_cfg(["Enc-Breast"], {"Enc-Breast": 1.00}, "enc_breast", "mg",
                 exclude_ir=False),
    "allowed_weekdays": {1, 2},     # Tue, Wed
}
ENC_GEN_CONFIG = {
    **_outpt_cfg(["Enc-Gen"], {"Enc-Gen": 1.00}, "enc_gen", "gen",
                 exclude_ir=False),
    "allowed_weekdays": {3, 4},     # Thu, Fri
}

# Poway site — Mon/Tue Gen, Wed MRI, Thu/Fri PET
POWAY_GEN_CONFIG = {
    **_outpt_cfg(["Poway-Gen"], {"Poway-Gen": 1.00}, "poway_gen", "gen",
                 exclude_ir=False),
    "allowed_weekdays": {0, 1},     # Mon, Tue
}
POWAY_MRI_CONFIG = {
    **_outpt_cfg(["Poway-MRI"], {"Poway-MRI": 1.00}, "poway_mri", "mri"),
    "allowed_weekdays": {2},        # Wed
}
POWAY_PET_CONFIG = {
    **_outpt_cfg(["Poway-PET"], {"Poway-PET": 1.00}, "poway_pet", "pet"),
    "allowed_weekdays": {3, 4},     # Thu, Fri
}

# ---------------------------------------------------------------------------
# NC-Gen — NC weeks only, Mon–Fri
# week_type="nc" tells the engine to only include dates in NC-cycle weeks.
# ---------------------------------------------------------------------------
NC_GEN_CONFIG = {
    **_outpt_cfg(["NC-Gen"], {"NC-Gen": 1.00}, "nc_gen", "gen", exclude_ir=False),
    "week_type":      "nc",         # NC weeks only
    "allowed_weekdays": {0, 1, 2, 3, 4},  # Mon–Fri
    "description":    "NC Gen (Mon–Fri, NC weeks only)",
}

# ---------------------------------------------------------------------------
# Remote Gen — numbered slots, week-type-aware day restrictions.
#
# Real schedule pattern:
#   NC weeks: 1x Remote-Gen on Mon, Tue, Wed, Fri  (no Thu)
#   KM weeks: 1x Remote-Gen every day (Mon–Fri)  +  2nd slot Mon, Tue
#
# Remote-Gen-1 uses allowed_weekdays_nc / allowed_weekdays_km so the engine
# applies the right day-set per week.
# Remote-Gen-2 is KM-only, Mon/Tue.
# ---------------------------------------------------------------------------
REMOTE_GEN_1_CONFIG = {
    "pool_filter":         "participates_gen",
    "exclude_ir":          True,
    "subspecialty_gate":   "gen",
    "shift_names":         ["Remote-Gen-1"],
    "shift_weights":       {"Remote-Gen-1": 1.00},
    "shifts_per_period":   1,
    "cursor_key":          "remote_gen_1",
    "avoid_previous":      False,
    "allow_fallback":      True,
    "use_weighted_cursor": True,
    "target_cv":           0.10,
    "schedule_type":       "weekday",
    # Per-week-type allowed days (engine reads these when nc_week_anchor is set)
    "allowed_weekdays_nc": {0, 1, 2, 4},       # Mon, Tue, Wed, Fri in NC weeks
    "allowed_weekdays_km": {0, 1, 2, 3, 4},    # Mon–Fri in KM weeks
    "description":         "Remote Gen slot 1 (NC: Mon/Tue/Wed/Fri; KM: Mon–Fri)",
}

REMOTE_GEN_2_CONFIG = {
    "pool_filter":         "participates_gen",
    "exclude_ir":          True,
    "subspecialty_gate":   "gen",
    "shift_names":         ["Remote-Gen-2"],
    "shift_weights":       {"Remote-Gen-2": 1.00},
    "shifts_per_period":   1,
    "cursor_key":          "remote_gen_2",
    "avoid_previous":      False,
    "allow_fallback":      True,
    "use_weighted_cursor": True,
    "target_cv":           0.10,
    "schedule_type":       "weekday",
    "week_type":           "km",        # KM weeks only
    "allowed_weekdays":    {0, 1},      # Mon, Tue
    "description":         "Remote Gen slot 2 (KM weeks Mon/Tue only — 2nd simultaneous)",
}

# Remote outpatient — demand-based; no fixed-day restriction (remote = flexible)
REMOTE_MRI_CONFIG = {
    **_outpt_cfg(["Remote-MRI"], {"Remote-MRI": 1.00}, "remote_mri", "mri"),
    "slots_per_week": 3,
}
REMOTE_BREAST_CONFIG = {
    **_outpt_cfg(["Remote-Breast"], {"Remote-Breast": 1.00}, "remote_breast", "mg",
                 exclude_ir=False),
    "slots_per_week": 3,
}
REMOTE_PET_CONFIG = {
    **_outpt_cfg(["Remote-PET"], {"Remote-PET": 1.00}, "remote_pet", "pet"),
    "slots_per_week": 2,
}

# O'Toole — MG-tagged staff (DA + non-IR MG). Tue/Wed/Thu only.
# (Real schedule shows O'Toole on Tue, Wed, Thu per QGenda integration doc)
OTOOLE_CONFIG = {
    "pool_filter":        "participates_mg",
    "exclude_ir":         False,
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
    "allowed_weekdays":   {1, 2, 3},  # Tue, Wed, Thu
    "description":        "Scripps O'Toole (Tue/Wed/Thu only)",
}

# Weekend outpatient
WKND_MRI_CONFIG = _outpt_cfg(["Wknd-MRI"], {"Wknd-MRI": 1.00}, "wknd_mri", "mri",
                               schedule_type="weekend")
WKND_PET_CONFIG = _outpt_cfg(["Wknd-PET"], {"Wknd-PET": 1.00}, "wknd_pet", "pet",
                               schedule_type="weekend")

# ---------------------------------------------------------------------------
# SCHEDULING_BLOCKS — Priority order
# exclude_ir=True means IR staff are HARD-excluded from that block's pool.
# week_type on a block config restricts it to NC or KM weeks via the engine.
# ---------------------------------------------------------------------------
SCHEDULING_BLOCKS: List[Dict[str, Any]] = [

    # ── 1. IR weekday — IR pool only ─────────────────────────────────────────
    {"block_id": "ir_weekday", "label": "IR-1 / IR-2",
     "config": IR_WEEKDAY_CONFIG, "priority": 1,
     "can_skip": False, "exclude_ir": False,
     "interactive_prompt": "Schedule IR shifts (IR-1, IR-2)?"},

    # ── 2. IR-CALL — Fri+Sat+Sun mirror (same IR person all 3 days) ──────────
    {"block_id": "ir_call", "label": "IR-CALL (Fri+Sat+Sun mirror)",
     "config": IR_CALL_CONFIG, "priority": 2,
     "can_skip": True, "exclude_ir": False,
     "interactive_prompt": "Schedule IR-CALL (Fri+Sat+Sun)?"},

    # ── 3–5. Mercy inpatient — NON-IR ONLY ────────────────────────────────────
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

    # ── 6–20. Outpatient blocks — optimised priority order ───────────────────
    # Simulation-derived ordering: schedule scarce-pool specialties (Breast/MG,
    # MRI, PET) BEFORE general specialties.  The Gen pool is large and absorbs
    # being scheduled later without increasing unfilled slots.
    #
    # Priority order found by scripts/simulate_priority.py (120 evals):
    #   Enc-Breast → Remote-Breast → Wash-MRI → Remote-MRI → O'Toole →
    #   Remote-PET → Remote-Gen-1 → Poway-MRI → Poway-PET → Wash-Breast →
    #   Remote-Gen-2 → NC-Gen → Enc-MRI → Enc-Gen → Poway-Gen

    {"block_id": "enc_breast", "label": "Encinitas Breast (Tue/Wed)",
     "config": ENC_BREAST_CONFIG, "priority": 6,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "mg",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Encinitas Breast (Tue/Wed)?"},

    {"block_id": "remote_breast", "label": "Remote Breast",
     "config": REMOTE_BREAST_CONFIG, "priority": 7,
     "can_skip": True, "exclude_ir": False,
     "subspecialty_gate": "mg",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Remote Breast?"},

    {"block_id": "wash_mri", "label": "Washington MRI (Tue/Wed/Thu)",
     "config": WASH_MRI_CONFIG, "priority": 8,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "mri+proc",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Washington MRI (Tue/Wed/Thu)?"},

    {"block_id": "remote_mri", "label": "Remote MRI",
     "config": REMOTE_MRI_CONFIG, "priority": 9,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "mri",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Remote MRI?"},

    {"block_id": "otoole", "label": "O'Toole",
     "config": OTOOLE_CONFIG, "priority": 10,
     "can_skip": True, "exclude_ir": False,
     "subspecialty_gate": "mg",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule O'Toole?"},

    {"block_id": "remote_pet", "label": "Remote PET",
     "config": REMOTE_PET_CONFIG, "priority": 11,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "pet",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Remote PET?"},

    {"block_id": "remote_gen_1", "label": "Remote Gen (slot 1)",
     "config": REMOTE_GEN_1_CONFIG, "priority": 12,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "gen",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Remote Gen slot 1?"},

    {"block_id": "poway_mri", "label": "Poway MRI (Wed)",
     "config": POWAY_MRI_CONFIG, "priority": 13,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "mri",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Poway MRI (Wed)?"},

    {"block_id": "poway_pet", "label": "Poway PET (Thu/Fri)",
     "config": POWAY_PET_CONFIG, "priority": 14,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "pet",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Poway PET (Thu/Fri)?"},

    {"block_id": "wash_breast", "label": "Washington Breast (Mon/Fri)",
     "config": WASH_BREAST_CONFIG, "priority": 15,
     "can_skip": True, "exclude_ir": False,
     "subspecialty_gate": "mg",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Washington Breast (Mon/Fri)?"},

    {"block_id": "remote_gen_2", "label": "Remote Gen (slot 2, KM Mon/Tue)",
     "config": REMOTE_GEN_2_CONFIG, "priority": 16,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "gen",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Remote Gen slot 2 (KM weeks)?"},

    {"block_id": "nc_gen", "label": "NC Gen (NC weeks Mon–Fri)",
     "config": NC_GEN_CONFIG, "priority": 17,
     "can_skip": True, "exclude_ir": False,
     "subspecialty_gate": "gen",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule National City Gen (NC weeks only)?"},

    {"block_id": "enc_mri", "label": "Encinitas MRI (Mon)",
     "config": ENC_MRI_CONFIG, "priority": 18,
     "can_skip": True, "exclude_ir": True,
     "subspecialty_gate": "mri",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Encinitas MRI (Mon)?"},

    {"block_id": "enc_gen", "label": "Encinitas Gen (Thu/Fri)",
     "config": ENC_GEN_CONFIG, "priority": 19,
     "can_skip": True, "exclude_ir": False,
     "subspecialty_gate": "gen",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Encinitas Gen (Thu/Fri)?"},

    {"block_id": "poway_gen", "label": "Poway Gen (Mon/Tue)",
     "config": POWAY_GEN_CONFIG, "priority": 20,
     "can_skip": True, "exclude_ir": False,
     "subspecialty_gate": "gen",
     "concurrent_ok": True,
     "interactive_prompt": "Schedule Poway Gen (Mon/Tue)?"},

    # ── 14. Weekend inpatient — exclusive ─────────────────────────────────────
    {"block_id": "inpatient_weekend", "label": "Weekend Inpatient (M0/EP/Dx-CALL)",
     "config": WEEKEND_CONFIG, "priority": 21,
     "can_skip": True, "exclude_ir": True,
     "concurrent_ok": False,
     "interactive_prompt": "Schedule weekend inpatient block?"},

    # ── 15. Weekend outpatient — concurrent ───────────────────────────────────
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
    "back_to_back_weekend":       {"severity": "soft",  "penalty": 100},
    "vacation_assignment":        {"severity": "hard",  "penalty": 9999},
    "double_booking":             {"severity": "hard",  "penalty": 9999},
    "duplicate_task_assignment":  {"severity": "hard",  "penalty": 9999},
    "ir_and_gen_same_day":        {"severity": "hard",  "penalty": 9999},
    "ir_weekday_exclusive":       {"severity": "hard",  "penalty": 9999},
    "multiple_outpatient_same_day": {"severity": "hard", "penalty": 9999},
    "two_weekday_tasks":          {"severity": "hard",  "penalty": 9999},
    "subspecialty_mismatch":      {"severity": "hard",  "penalty": 9999},
    "ir_pool_gate":               {"severity": "hard",  "penalty": 9999},
    "mercy_pool_gate":            {"severity": "hard",  "penalty": 9999},
    "weekend_pool_gate":          {"severity": "hard",  "penalty": 9999},
    "workload_cv_exceeded":       {"severity": "soft",  "penalty": 25},
    "task_day_of_week":           {"severity": "soft",  "penalty": 50},
}

FAIRNESS_TARGETS: Dict[str, Any] = {
    "cv_target":    0.10,
    "max_deviation": 0.20,
    "weighted_hours": True,
}

# ---------------------------------------------------------------------------
# Fixed subspecialty assignments (concurrent — not in rotation engine)
# ---------------------------------------------------------------------------
FIXED_SUBSPECIALTY_ASSIGNMENTS: Dict[str, List[str]] = {
    "Skull-Base": ["JuanCarlos Vera", "James Cooper", "Brian Trinh"],
    "Cardiac":    ["John Johnson", "Brian Trinh"],
}

# ---------------------------------------------------------------------------
# Day-of-week validation map — used by constraints.check_task_day_of_week
# Maps shift code → frozenset of allowed weekday ints (Mon=0 … Fri=4; Sat=5, Sun=6)
# ---------------------------------------------------------------------------
TASK_ALLOWED_WEEKDAYS: Dict[str, frozenset] = {
    "Enc-MRI":    frozenset({0}),
    "Enc-Breast": frozenset({1, 2}),
    "Enc-Gen":    frozenset({3, 4}),
    "Poway-Gen":  frozenset({0, 1}),
    "Poway-MRI":  frozenset({2}),
    "Poway-PET":  frozenset({3, 4}),
    "Wash-Breast":frozenset({0, 4}),
    "Wash-MRI":   frozenset({1, 2, 3}),
    "O'Toole":    frozenset({1, 2, 3}),
    "IR-CALL":    frozenset({4, 5, 6}),   # Fri, Sat, Sun
}
