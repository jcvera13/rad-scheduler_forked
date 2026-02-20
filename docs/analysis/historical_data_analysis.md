# QGenda Historical Data Analysis
## Analysis Period: June 21, 2025 - December 21, 2025 (6.1 months)

---

## Executive Summary

**Total Assignments:** 3,316 across 21 staff members  
**Core Rotation Shifts:** 883 assignments across 8 shift types  
**Fairness Status:** âš ï¸ **HIGHLY VARIABLE** (coefficient of variation: 56.7%)

---

## Key Findings

### 1. Current System Shows Significant Workload Imbalance

**Rotation-Managed Shifts Only:**
- **Most assigned:** Ted Rothenberg - 97 shifts
- **Least assigned:** LOCUMS - 1 shift
- **Spread:** 96 shift difference between highest and lowest
- **Standard deviation:** 25.0 (mean: 44.1)

This suggests the current system is **NOT** using strict round-robin rotation, or there are legitimate reasons for imbalance:
- Part-time vs full-time staff
- Subspecialty requirements
- Mid-year hiring/departures
- IR specialists vs general radiologists

### 2. Shift Categories Identified

#### **A. Rotation-Managed Shifts (Should use fair scheduling engine):**

**Weekday Mercy Shifts (4 types):**
- Mercy 0 (M0): 126 assignments
- Mercy 1 (M1): 149 assignments  
- Mercy 2 (M2): 129 assignments
- Mercy 3 (M3): 126 assignments

**IR Shifts (3 types):**
- Mercy Hospital IR-1: 126 assignments
- Mercy Hospital IR-2: 126 assignments
- PVH IR: 43 assignments

**Weekend Mercy:**
- Mercy 0 Weekend: 58 assignments

**Total rotation-managed:** 883 assignments (26.6% of all shifts)

#### **B. Non-Rotation Shifts (Should NOT use fair scheduling engine):**

These are likely fixed assignments or specialty-based:
- Subspecialty rotations (Skull Base: 113, Cardiac: 104)
- Outpatient site rotations (Washington MRI, Poway PET, etc.)
- Administrative time
- Vacation/OFF (594 combined)
- Other specialty shifts

---

## Mapping to Your Weekly Rotation Structure

From your `weekly_rotations.md`, you have:
- **12 shifts per weekday** across M0, M1, M2, M3, O'Toole, IR1, IR2, MR1-3, PET1-2, MG1-2
- **3 outpatient shifts per weekend**
- **4-6 Mercy Call shifts per weekend**

### What the data reveals:

1. **Weekday coverage averages 6.4 rotation-managed shifts/day** (not the full 12)
   - This means OTHER shifts in your rotation (MR, PET, MG, O'Toole) are being handled separately

2. **Weekend coverage shows only 1 shift/day average**
   - The EP/LP weekend call shifts appear in the data but weren't counted in "rotation-managed"
   - Need to decide if these should be in the fair rotation or handled separately

3. **IR shifts are being rotated** - IR1 and IR2 show consistent assignment patterns

---

## Critical Insights for Scheduling Engine Implementation

### 1. **Not All Radiologists Participate Equally**

Current participation in rotation-managed shifts varies drastically:

```
Ted Rothenberg:     97 shifts (220% of mean)
Sina Fartash:       85 shifts (193% of mean)
Sharjeel Sabir:     77 shifts (175% of mean)
...
Mark Schechter:     16 shifts (36% of mean)
LOCUMS:              1 shift  (2% of mean)
```

**Key Question:** Is this by design (part-time, specialists, FTE differences) or a fairness problem?

**Recommendation:** Before implementing the fair rotation engine:
1. Categorize radiologists by FTE status (1.0, 0.8, 0.5, etc.)
2. Identify who should participate in which rotations
3. Implement FTE-weighted fairness (mentioned in architecture.md as planned extension)

### 2. **Cursor Initialization for Continuity**

If you want to maintain continuity with the current rotation:

```
Total assignments made: 883
Number of radiologists: 20
Suggested cursor position: 883 % 20 = 3
```

This means the 4th radiologist in your `roster_key.csv` order would be next up.

**However:** Given the high variability, you may want to **reset to 0** to start fresh with true fairness.

### 3. **Weekend Strategy Needed**

Your data shows minimal weekend rotation assignments (54 total). Need to clarify:
- Should EP/LP weekend calls be in the rotation engine?
- Should weekend Mercy shifts be separate from weekday rotations?
- Do you want shared cursor or separate weekend cursor?

---

## Recommendations for Moving Forward

### Immediate Actions:

1. **Categorize Your Radiologists:**
   ```csv
   name,fte,participates_in_mercy,participates_in_ir,subspecialty
   Ted Rothenberg,1.0,yes,yes,none
   Mark Schechter,0.5,yes,no,cardiac
   ...
   ```

2. **Define Rotation Pools:**
   - **Mercy Rotation Pool:** Who rotates through M0-M3?
   - **IR Rotation Pool:** Who rotates through IR1/IR2?
   - **Weekend Pool:** Who takes EP/LP/M0 Weekend?

3. **Decide on Cursor Strategy:**
   - **Option A:** Reset to 0 (start fresh, fix existing imbalances)
   - **Option B:** Initialize to 3 (maintain continuity, accept some unfairness)
   - **Option C:** Calculate separate cursors for each radiologist based on their historical assignments

4. **Handle Subspecialty Shifts:**
   Keep these OUTSIDE the rotation engine:
   - Skull Base â†’ assigned to specific radiologist(s)
   - Cardiac â†’ assigned to specific radiologist(s)
   - Site-specific outpatient rotations â†’ may need separate scheduling

---

## Weekday Distribution Analysis

**Average weekday coverage:** 6.4 rotation-managed shifts/day (out of 12 total shifts)

**Known weekday structure from your doc:**
- M0, M1, M2, M3 (4 shifts)
- IR1, IR2 (2 shifts)
- MR1, MR2, MR3 (? shifts - not in rotation data)
- PET1, PET2 (? shifts - not in rotation data)
- MG1, MG2 (? shifts - not in rotation data)
- O'Toole (? shifts - not in rotation data)

**Interpretation:** The MR/PET/MG/O'Toole shifts are likely being handled through:
- Direct assignment to subspecialists
- Separate outpatient scheduling system
- Site-based scheduling (not in QGenda?)

---

## Data Quality Notes

âœ… **Good:**
- Clean date ranges
- Consistent naming
- 6 months of data (sufficient for analysis)
- Clear shift type labels

âš ï¸ **Issues to Address:**
- "OPEN OPEN" (75 assignments) - unfilled positions
- "LOCUMS LOCUMS" (66 assignments) - temporary coverage
- Inconsistent participation rates need investigation

---

## Next Steps

### For Scheduling Engine Configuration:

1. Create `roster_key.csv` with:
   - Fixed index order
   - FTE weights
   - Rotation pool assignments
   - Vacation dates

2. Decide scope:
   - **Minimal:** Just Mercy weekday shifts (M0-M3)
   - **Moderate:** Mercy + IR weekday + weekend Mercy
   - **Comprehensive:** All rotation-managed + weekend calls

3. Configure vacation handling:
   - Extract historical vacation dates from this data
   - Build vacation_map.csv

4. Test the engine:
   - Run on historical dates
   - Compare outputs
   - Tune back-to-back weekend avoidance

---

## Appendix: Complete Assignment Counts

### By Radiologist (All Shifts):
```
John Johnson:        221
Brian Trinh:         220
James Cooper:        211
JuanCarlos Vera:     200
Sharjeel Sabir:      195
Ted Rothenberg:      188
Derrick Allen:       185
Eric Lizerbram:      179
Sina Fartash:        179
Gregory Anderson:    174
Michael Booker:      171
Mark Schechter:      156
Michael Grant:       154
Eric Kim:            151
Eric Chou:           149
Rowena Tena:         135
Yonatan Rotman:      109
Kriti Rishi:         106
Karen Yuan:           92
OPEN OPEN:            75
LOCUMS LOCUMS:        66
```

### By Shift Type (Top 20):
```
VACATION:            410
IR-CALL (RMG):       184
OFF ALL DAY:         184
Mercy 1 (M1):        149
Mercy 2 (M2):        129
IR-1:                126
IR-2:                126
Mercy 0 (M0):        126
Mercy 3 (M3):        126
Remote MRI:          125
Remote Breast:       119
Skull Base:          113
Cardiac:             104
Remote General:       83
Washington MRI:       82
Poway PET:            76
O'Toole:              68
Remote PET:           68
CBCC General:         64
Encinitas Breast:     61
```
