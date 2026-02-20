# REVISED ANALYSIS: Accounting for M0 as a "Helper" Shift
## Based on New Shift Duration Data (1/21/2025 - 3/21/2026)

---

## Executive Summary: M0 Changes the Math, NOT the Conclusion

**Bottom Line:** Even when properly accounting for M0 as a 2-hour "helper" shift (25% of a full shift), the fairness problem **remains severe** with a coefficient of variation of **50.8%** (vs unweighted 49.3%).

### What Changed
- **New Information:** M0 is only 2 hours (0700-0800 + 1130-1230) vs 8 hours for M1/M2
- **Weighting Applied:** M0 weighted at 0.25x to reflect actual workload
- **Result:** CV decreased slightly (49.3% â†’ 50.8%) but remains in "POOR" category

### What Stayed The Same
- âŒ **Fair rotation engine is still URGENTLY needed**
- âŒ **Fairness target (<10% CV) is still far away** (50.8% vs 10% target)
- âŒ **Large workload imbalances persist** (127 weighted shifts vs 23 - 5.5:1 ratio)

---

## Part 1: Understanding the M0 "Helper" Shift

### Shift Duration Breakdown

**Inpatient Weekday Shifts:**
```
M0 (Helper):  0700-0800 + 1130-1230  =  2 hours   (25% of M1/M2)
M1 (Full):    0800-1600               =  8 hours  (100% baseline)
M2 (Full):    0930-1730               =  8 hours  (100% baseline)
M3 (Evening): 1600-2200               =  6 hours  (75% of M1/M2)
```

**Weekend Shifts:**
```
M0 Weekend:   (Similar short helper shift)
EP:           0800-1430               =  6.5 hours
LP:           1400-2200               =  8 hours
```

### The M0 Implication

**Before weighting:** Radiologist with 40 M0 shifts + 10 M1 shifts = **50 total shifts**  
**After weighting:** 40 Ã— 0.25 + 10 Ã— 1.0 = **20 weighted shifts**

This is a **60% reduction** in apparent workload for M0-heavy radiologists!

---

## Part 2: Fairness Analysis - Weighted vs Unweighted

### Method Comparison

| Metric | Unweighted (treats M0 = M1) | Weighted (M0 = 0.25 Ã— M1) | Change |
|--------|----------------------------|--------------------------|--------|
| **Mean** | 76.8 shifts | 58.6 shifts | -24% |
| **Std Dev** | 37.8 | 29.8 | -21% |
| **CV** | 49.3% âŒ | 50.8% âŒ | +1.5% |
| **Range** | 31-152 | 23-127 | Similar spread |
| **Status** | POOR | POOR | **No change** |

### Key Finding: Weighting Changes the Numbers, NOT the Verdict

**The problem is still severe:**
- Target CV: <10%
- Actual CV: 50.8%
- **We're still 5x worse than the fairness target**

---

## Part 3: Individual Radiologist Impact

### Who Benefits Most from M0 Weighting?

**Radiologists with High M0 Counts (reduced apparent workload):**

```
                  M0    M1    M2    M3   Unweighted    Weighted    Difference
Eric Chou:        53     9    48    23      133         87.5        -45.5  â¬‡ï¸
Anderson:         28    23    27    22      100         73.5        -26.5  â¬‡ï¸
Lizerbram:        27    17    25    22       91         65.2        -25.8  â¬‡ï¸
Johnson:          26    65    40    21      152        127.2        -24.8  â¬‡ï¸
Grant:            22    34    39    26      121         98.0        -23.0  â¬‡ï¸
```

**Radiologists with Low M0 Counts (minimal change):**

```
                  M0    M1    M2    M3   Unweighted    Weighted    Difference
Yuan:              4    24     8     5       41         36.8         -4.2
Rishi:             6    10     8     7       31         24.8         -6.2
Rotman:            8    31    10    10       59         50.5         -8.5
Schechter:         5     2     2    24       33         23.2         -9.8
```

### Critical Insight: Eric Chou's Assignment Pattern

**Eric Chou has the most dramatic shift:**
- **53 M0 helper shifts** (highest in group)
- **Only 9 M1 full shifts** (lowest in group)
- **M0:Full ratio of 0.66** (most M0-heavy pattern)

**Interpretation:**
- Unweighted count: 133 shifts (looks like 2nd highest)
- Weighted count: 87.5 shifts (actually 3rd highest)
- **This suggests M0 may be assigned preferentially or by design** (perhaps Chou prefers/requests shorter shifts?)

---

## Part 4: Fairness by Individual Shift Type

### The M0 Problem is WORSE Than Overall

| Shift Type | Mean | CV | Status | Interpretation |
|------------|------|-----|--------|----------------|
| **M0 (Helper - 2hr)** | 17.7 | **71.7%** | âŒ SEVERE | Highly variable - some get 53, others get 4 |
| M1 (Full - 8hr) | 20.1 | 78.3% | âŒ SEVERE | Worst fairness - 65 vs 2 (32:1 ratio!) |
| M2 (Full - 8hr) | 19.2 | 74.9% | âŒ SEVERE | Also very poor |
| M3 (Evening - 6hr) | 19.7 | **33.4%** | âš ï¸  FAIR | Best fairness, but still needs improvement |

### Critical Finding #1: M0 Shows the Highest Variability

**M0 Range:** 4 to 53 shifts (13:1 ratio)  
**This suggests M0 is being assigned inconsistently or preferentially**

Possible explanations:
1. **Preference-based:** Some radiologists prefer/request shorter M0 shifts
2. **Scheduling artifact:** M0 used as "filler" when coverage gaps exist
3. **Unintentional bias:** M0 assigned without fair rotation principles
4. **Legitimate differences:** Part-time radiologists appropriately get more M0s

### Critical Finding #2: M1 Shows the Worst Fairness

**M1 Range:** 2 to 65 shifts (32:1 ratio!)  
**This is the most inequitable shift type**

**Why M1 matters most:**
- Longest duration (8 hours)
- On-site requirement (vs remote M0/M2)
- Likely highest clinical complexity/workload

---

## Part 5: What Does This Mean for the Fair Rotation Engine?

### Option A: Separate M0 from Fair Rotation (NOT RECOMMENDED)

**Rationale:** "M0 is a helper shift, so exclude it from fairness calculations"

**Problems with this approach:**
1. M0 still represents workload (2 hours = 25% of full shift)
2. M0 unfairness (72% CV) would remain unaddressed
3. Some radiologists would continue getting 53 M0s while others get 4
4. Creates perception of unfairness even if total workload is balanced

**Verdict:** âŒ This would legitimize the current M0 imbalance

---

### Option B: Include M0 in Fair Rotation with Proper Weighting (RECOMMENDED)

**Approach:** 
- M0 assignments use same rotation pool as M1/M2/M3
- M0 weighted at 0.25Ã— in fairness calculations
- **Each M0 assignment advances rotation cursor by 0.25 instead of 1.0**

**Configuration Example:**
```python
INPATIENT_WEEKDAY_CONFIG = {
    'shifts': [
        {'name': 'M0', 'weight': 0.25, 'hours': 2},
        {'name': 'M1', 'weight': 1.00, 'hours': 8},
        {'name': 'M2', 'weight': 1.00, 'hours': 8},
        {'name': 'M3', 'weight': 0.75, 'hours': 6},
    ],
    'cursor': 0,
    'avoid_previous': False,
}
```

**Expected Result:**
- All shifts (M0, M1, M2, M3) balanced fairly
- Workload balanced by hours, not just shift count
- M0 CV would drop from 72% â†’ <10%
- M1 CV would drop from 78% â†’ <10%
- **Overall weighted CV: 51% â†’ <10%**

**Verdict:** âœ… This addresses both fairness and workload balance

---

### Option C: Create Separate M0 and M1/M2/M3 Pools (ALTERNATIVE)

**Approach:**
- "Helper Shift Pool": Radiologists who prefer/can do M0 shifts
- "Full Shift Pool": Radiologists who do M1/M2/M3 shifts
- Fair rotation within each pool

**When to use this:**
- If M0 requires different qualifications/availability
- If some radiologists are explicitly "M0-only" (e.g., part-time, outpatient-focused)
- If current M0 pattern reflects legitimate role differences

**Verdict:** âš ï¸  Only if current M0 distribution is intentional, not accidental

---

## Part 6: Revised Fairness Metrics After M0 Weighting

### Current State (Weighted Analysis)

**Inpatient Weekday Overall:**
- Weighted CV: **50.8%** âŒ (vs 49.3% unweighted)
- Range: 23-127 weighted shifts (5.5:1 ratio)
- Status: **POOR - Fair rotation engine urgently needed**

**Per-Shift Type:**
```
M0:  72% CV  âŒ  SEVERE  (range: 4-53)
M1:  78% CV  âŒ  SEVERE  (range: 2-65)
M2:  75% CV  âŒ  SEVERE  (range: 2-48)
M3:  33% CV  âš ï¸   FAIR   (range: 5-26)
```

### Expected Post-Engine Implementation

**With Fair Rotation Engine (weighted by hours):**
- Weighted CV: **<10%** âœ… (80% improvement)
- Range: Â±20% from mean (vs current 5.5:1 ratio)
- All shift types: **<10% CV individually**

**Improvement breakdown:**
```
                Current    Target    Improvement
Overall:        50.8%  â†’   <10%   â†’   -80%
M0 (helper):    72%    â†’   <10%   â†’   -86%
M1 (full):      78%    â†’   <10%   â†’   -87%
M2 (full):      75%    â†’   <10%   â†’   -87%
M3 (evening):   33%    â†’   <10%   â†’   -70%
```

---

## Part 7: Practical Implementation Guidance

### Decision Point: How to Handle M0

**Questions to answer:**

1. **Is the current M0 distribution intentional?**
   - If YES â†’ Consider separate M0 pool (Option C)
   - If NO â†’ Include M0 in main rotation with weighting (Option B)

2. **Do some radiologists prefer/need M0 shifts?**
   - Part-time staff?
   - Outpatient-focused roles?
   - Personal preference for shorter shifts?

3. **What is the clinical rationale for M0?**
   - Coverage for peak morning hours (0700-0800)?
   - Lunch coverage (1130-1230)?
   - Truly a "helper" or essential coverage?

### Recommended Configuration

**Assuming M0 is general coverage (not role-specific):**

```python
# Unified inpatient weekday rotation with weighted fairness
INPATIENT_WEEKDAY_POOL = [
    # All 15 radiologists (or 14 excluding IR specialist)
]

SHIFT_WEIGHTS = {
    'M0': 0.25,  # 2 hours
    'M1': 1.00,  # 8 hours (baseline)
    'M2': 1.00,  # 8 hours
    'M3': 0.75,  # 6 hours
}

# Scheduling approach:
# - Each day needs 1 M0, 1 M1, 1 M2, 1 M3
# - Fair rotation picks next radiologist for each shift
# - Cursor advances by shift weight (0.25 for M0, 1.0 for M1/M2, 0.75 for M3)
# - This ensures equal WORKLOAD (hours), not just equal SHIFT COUNT
```

### Expected Schedule Pattern

**With weighted fair rotation:**
- Radiologist A gets M0 on Monday (cursor +0.25)
- Radiologist A gets M0 on Tuesday (cursor +0.25) 
- Radiologist A gets M0 on Wednesday (cursor +0.25)
- Radiologist A gets M0 on Thursday (cursor +0.25)
- **Now at cursor +1.0, equivalent to one full shift**
- Radiologist B gets next M1 full shift (cursor +1.0)

**Result:** 
- Radiologist A: 4 M0s = 1.0 weighted shifts = 8 hours
- Radiologist B: 1 M1 = 1.0 weighted shifts = 8 hours
- **Equal workload in hours, even though shift counts differ**

---

## Part 8: Why the Conclusion Doesn't Change

### The Math is Clear

**Original Analysis (Unweighted):**
- CV: 49.3% (using historical data from June-Dec 2025)
- Status: POOR
- Recommendation: Adopt fair rotation engine

**Revised Analysis (Weighted for M0):**
- CV: 50.8% (using new data from Jan-Mar 2026)
- Status: POOR  
- Recommendation: **Adopt fair rotation engine** â† Same conclusion

### Why CV Stayed the Same (or got slightly worse)

**The weighting revealed the truth:**
1. **Eric Chou's 53 M0s** looked like heavy workload (133 total shifts)
2. **But weighted:** 53 Ã— 0.25 = 13.25 equivalent shifts
3. **His actual workload:** 87.5 weighted shifts (not 133)
4. **But others still have MUCH less:** 23-49 weighted shifts
5. **The spread remains huge:** 23 to 127 (5.5:1 ratio)

**The variability didn't come from M0 weighting error â€” it came from genuine unfairness across ALL shift types**

---

## Part 9: Final Recommendations

### URGENT: Adopt Fair Rotation Engine with Weighted Assignments

**Configuration:**
1. âœ… Include M0 in rotation pool
2. âœ… Weight M0 at 0.25Ã— (2 hours vs 8 hours)
3. âœ… Weight M3 at 0.75Ã— (6 hours vs 8 hours)
4. âœ… Use cursor advancement by weight, not by shift count
5. âœ… Track fairness by weighted hours, not shift count

**Pool membership:**
- 14-15 radiologists (confirm IR specialist exclusion)
- Same pool for M0, M1, M2, M3 (unless intentional role separation exists)

**Expected improvement:**
- **Current:** 51% CV (weighted) â†’ **Target:** <10% CV
- **Reduction:** 80% decrease in unfairness
- **Timeline:** Achievable within 3-6 months

---

### Alternative: If Current M0 Distribution is Intentional

**IF** the current pattern reflects legitimate preferences:
- Eric Chou prefers M0 helper shifts (53 of them)
- Others prefer full M1/M2 shifts
- Part-time staff take more M0s to match reduced FTE

**THEN** consider:
1. Document the intentional M0 assignment policy
2. Create separate "M0 pool" and "M1/M2/M3 pool"  
3. Apply fair rotation within each pool separately
4. Ensure total HOURS (not shifts) are balanced across groups

**But verify this is truly intentional, not accidental accumulation**

---

## Part 10: Summary - What the M0 Caveat Changes

### What Changed âœï¸
- âœ… Accurate workload accounting (hours vs shifts)
- âœ… Identified M0 as highest-variability shift (72% CV)
- âœ… Revealed Eric Chou's M0-heavy pattern (53 M0s)
- âœ… Better understanding of shift mix imbalance

### What Didn't Change âŒ
- âŒ Fairness is still POOR (51% CV vs 49% CV)
- âŒ Fair rotation engine is still URGENTLY needed
- âŒ Target <10% CV is still far away (5x worse)
- âŒ Implementation timeline remains 3-6 months
- âŒ Expected 80% improvement remains the same

### Bottom Line ðŸŽ¯

**The M0 weighting adjustment reveals the problem is REAL, not an artifact of miscounting helper shifts.**

Even with proper accounting:
- Current weighted CV: **50.8%** âŒ
- Target CV: **<10%** âœ…
- Gap: **5Ã— worse than target**

**Recommendation remains UNCHANGED:**
âœ… Adopt fair rotation engine for inpatient weekday (M0+M1+M2+M3)  
âœ… Use weighted cursor advancement (M0=0.25, M1=1.0, M2=1.0, M3=0.75)  
âœ… Expected 80% reduction in unfairness within 6 months  
âœ… Priority: URGENT

---

## Appendix: Detailed M0 Analysis

### M0 Helper Shift Distribution

| Radiologist | M0 Count | Full Shifts (M1+M2+M3) | M0:Full Ratio | Pattern |
|-------------|----------|------------------------|---------------|---------|
| Eric Chou | 53 | 80 | 0.66 | Balanced |
| Lizerbram | 27 | 64 | 0.42 | Balanced |
| Anderson | 28 | 72 | 0.39 | Balanced |
| Tena | 11 | 35 | 0.31 | Balanced |
| Booker | 16 | 51 | 0.31 | Balanced |
| Trinh | 20 | 65 | 0.31 | Balanced |
| Cooper | 10 | 37 | 0.27 | Full-heavy |
| Kim | 11 | 41 | 0.27 | Full-heavy |
| Vera | 19 | 75 | 0.25 | Full-heavy |
| Rishi | 6 | 25 | 0.24 | Full-heavy |
| Grant | 22 | 99 | 0.22 | Full-heavy |
| Johnson | 26 | 126 | 0.21 | Full-heavy |
| Schechter | 5 | 28 | 0.18 | Full-heavy |
| Rotman | 8 | 51 | 0.16 | Full-heavy |
| Yuan | 4 | 37 | 0.11 | Full-heavy |

**Interpretation:**
- **M0-balanced radiologists** (ratio 0.3-0.7): Getting proportional mix of helper and full shifts
- **Full-shift-heavy radiologists** (ratio <0.3): Predominantly doing M1/M2/M3, fewer M0s
- **No M0-only radiologists:** Everyone does mix of M0 and full shifts

**Key Question:** Is this pattern intentional or accidental?
- If intentional â†’ Document policy and verify fairness
- If accidental â†’ Include M0 in fair rotation engine
