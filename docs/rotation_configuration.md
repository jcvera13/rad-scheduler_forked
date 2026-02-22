# Fair Scheduling Engine Configuration Guide
## Based on 6-Month Historical Data (Sept 2025 - March 2026)

---

## Executive Summary

**Data Period:** September 21, 2025 - March 21, 2026 (181 days / ~6 months)  
**Total Radiologists:** 15 active in rotations  
**Total Inpatient Assignments:** 1,417 (excluding IR)  
**Total Outpatient Assignments:** 1,628 (excluding IR)

### Current Fairness Status by Rotation Type

| Rotation Type | CV (%) | Status | Cursor | Needs Engine? |
|--------------|--------|--------|--------|---------------|
| **Inpatient Weekday** (M0-M3) | 47.0% | âš ï¸ Poor | 3 | âœ… YES |
| **Inpatient Weekend** (M0/EP/LP) | 14.4% | âœ… Good | 6 | âš ï¸ Maybe |
| **Outpatient Remote** | 33.0% | âš ï¸ Fair | 3 | âœ… YES |
| **Outpatient Site-Based** | 41.6% | âš ï¸ Poor | 3 | âœ… YES |
| **Combined Outpatient** | 26.0% | âš ï¸ Fair | 6 | âœ… YES |

**Target:** <10% CV for true fairness

---

## Part 1: Inpatient Rotation Configuration

### 1.1 Inpatient Weekday (M0, M1, M2, M3)

**Current Status:**
- 498 total assignments over 125 weekdays
- 3.98 shifts/day average (target: 4.0)
- 15 radiologists participate
- **CV: 47.0%** âš ï¸ Needs improvement

**Assignment Distribution:**
```
John Johnson:      66  (199% of mean) â¬†ï¸ Over-assigned
Eric Chou:         54  (163% of mean) â¬†ï¸ Over-assigned
Michael Grant:     54  (163% of mean) â¬†ï¸ Over-assigned
Yonatan Rotman:    46  (139% of mean)
Brian Trinh:       35  (105% of mean)
Gregory Anderson:  34  (102% of mean)
Eric Lizerbram:    33  ( 99% of mean)
Karen Yuan:        32  ( 96% of mean)
JuanCarlos Vera:   30  ( 90% of mean)
Michael Booker:    24  ( 72% of mean)
Kriti Rishi:       21  ( 63% of mean) â¬‡ï¸ Under-assigned
James Cooper:      19  ( 57% of mean) â¬‡ï¸ Under-assigned
Eric Kim:          19  ( 57% of mean) â¬‡ï¸ Under-assigned
Rowena Tena:       19  ( 57% of mean) â¬‡ï¸ Under-assigned
Mark Schechter:    12  ( 36% of mean) â¬‡ï¸ Under-assigned
---
Mean: 33.2  |  Std Dev: 15.6  |  Range: 12-66
```

**Recommended Configuration:**

```python
# schedule_config.py

INPATIENT_WEEKDAY_CONFIG = {
    'shifts_per_period': 4,  # M0, M1, M2, M3
    'cursor': 3,  # or 0 to reset
    'avoid_previous': False,  # Allow back-to-back weekdays
    'allow_fallback': True,
}

# Shift order (matches your weekly_rotations.md)
INPATIENT_WEEKDAY_SHIFTS = ['M0', 'M1', 'M2', 'M3']
```

**Roster Order (index 0-14):**
Based on current assignment patterns, suggested order:
```csv
index,name,participates_inp_weekday,fte
0,John Johnson,yes,1.0
1,Eric Chou,yes,1.0
2,Michael Grant,yes,1.0
3,Yonatan Rotman,yes,1.0
4,Brian Trinh,yes,0.8
5,Gregory Anderson,yes,1.0
6,Eric Lizerbram,yes,1.0
7,Karen Yuan,yes,0.8
8,JuanCarlos Vera,yes,1.0
9,Michael Booker,yes,1.0
10,Kriti Rishi,yes,0.8
11,James Cooper,yes,0.5
12,Eric Kim,yes,1.0
13,Rowena Tena,yes,0.8
14,Mark Schechter,yes,0.5
```

**Note:** FTE values are estimated based on assignment patterns. Please verify actual FTE status.

---

### 1.2 Inpatient Weekend (M0 Weekend, EP, Dx-CALL)

**Current Status:**
- 171 total assignments over 57 weekend days
- 3.0 shifts/weekend day (perfect!)
- 15 radiologists participate
- **CV: 14.4%** âœ… Already relatively fair!

**Assignment Distribution:**
```
Michael Grant:     14  (123% of mean)
John Johnson:      13  (114% of mean)
Eric Chou:         13  (114% of mean)
Rowena Tena:       13  (114% of mean)
JuanCarlos Vera:   12  (105% of mean)
Gregory Anderson:  12  (105% of mean)
Brian Trinh:       12  (105% of mean)
Yonatan Rotman:    12  (105% of mean)
Mark Schechter:    11  ( 96% of mean)
Eric Kim:          11  ( 96% of mean)
Michael Booker:    11  ( 96% of mean)
Kriti Rishi:       10  ( 88% of mean)
Karen Yuan:        10  ( 88% of mean)
Eric Lizerbram:     9  ( 79% of mean)
James Cooper:       8  ( 70% of mean)
---
Mean: 11.4  |  Std Dev: 1.6  |  Range: 8-14
```

**Analysis:** Weekend rotation is already MUCH better than weekday (14.4% vs 47.0% CV).

**Recommended Configuration:**

```python
INPATIENT_WEEKEND_CONFIG = {
    'shifts_per_period': 3,  # M0 Weekend, EP, Dx-CALL
    'cursor': 6,
    'avoid_previous': True,  # CRITICAL: Avoid back-to-back weekends
    'allow_fallback': True,  # Allow minimal violations if necessary
}

INPATIENT_WEEKEND_SHIFTS = ['M0 Weekend', 'EP', 'Dx-CALL']
```

**Decision Point:** Given the weekend rotation is already fairly balanced (14.4% CV), you could:
- **Option A:** Keep using current system (if it's manual, it's working well!)
- **Option B:** Move to engine to guarantee strict back-to-back weekend avoidance
- **Recommendation:** Use the engine primarily for the **back-to-back avoidance** feature

---

### 1.3 O'Toole Mammography (Subspecialty)

**Current Status:**
- 64 total assignments
- Only 5 radiologists assigned
- Heavily concentrated: Kriti Rishi (22), Rowena Tena (15), Eric Kim/James Cooper (13 each)

**Recommendation:** â›” **DO NOT** include in rotation engine.

This appears to be a **subspecialty assignment** (mammography expertise required). Keep as manual/fixed assignment.

---

## Part 2: Outpatient Rotation Configuration

### 2.1 Remote Rotations (Remote MRI/Breast/General/PET)

**Current Status:**
- 453 total assignments
- 4 shift types rotating
- 15 radiologists participate
- **CV: 33.0%** âš ï¸ Needs improvement

**Assignment Distribution:**
```
James Cooper:      49  (162% of mean) â¬†ï¸ Over-assigned
Rowena Tena:       43  (142% of mean) â¬†ï¸ Over-assigned
Eric Chou:         40  (132% of mean)
Mark Schechter:    39  (129% of mean)
Michael Booker:    36  (119% of mean)
JuanCarlos Vera:   34  (113% of mean)
Eric Kim:          34  (113% of mean)
Eric Lizerbram:    27  ( 89% of mean)
Gregory Anderson:  27  ( 89% of mean)
Brian Trinh:       26  ( 86% of mean)
Michael Grant:     22  ( 73% of mean)
Yonatan Rotman:    22  ( 73% of mean)
Kriti Rishi:       20  ( 66% of mean)
Karen Yuan:        19  ( 63% of mean)
John Johnson:      15  ( 50% of mean) â¬‡ï¸ Under-assigned
---
Mean: 30.2  |  Std Dev: 10.0  |  Range: 15-49
```

**Note:** John Johnson has significantly fewer outpatient assignments overall (18 total vs mean 55.4), suggesting he may have a different role distribution or more inpatient focus.

**Recommended Configuration:**

```python
OUTPATIENT_REMOTE_CONFIG = {
    'shifts_per_period': 4,  # Variable based on demand
    'cursor': 3,  # or 0 to reset
    'avoid_previous': False,
    'allow_fallback': True,
}

REMOTE_SHIFTS = [
    'Remote MRI',
    'Remote Breast',
    'Remote General',
    'Remote PET',
]
```

---

### 2.2 Site-Based Rotations (Washington/Encinitas/Poway/NC)

**Current Status:**
- 378 total assignments across 12 site/modality combinations
- 15 radiologists participate
- **CV: 41.6%** âš ï¸ Needs improvement

**Assignment Distribution:**
```
Karen Yuan:        42  (167% of mean) â¬†ï¸ Over-assigned
Mark Schechter:    40  (159% of mean) â¬†ï¸ Over-assigned
Yonatan Rotman:    35  (139% of mean)
Gregory Anderson:  32  (127% of mean)
Eric Kim:          29  (115% of mean)
JuanCarlos Vera:   28  (111% of mean)
Rowena Tena:       28  (111% of mean)
Kriti Rishi:       27  (107% of mean)
Michael Grant:     24  ( 95% of mean)
Brian Trinh:       23  ( 91% of mean)
Michael Booker:    22  ( 87% of mean)
James Cooper:      19  ( 75% of mean)
Eric Lizerbram:    16  ( 63% of mean)
Eric Chou:         10  ( 40% of mean) â¬‡ï¸ Under-assigned
John Johnson:       3  ( 12% of mean) â¬‡ï¸ Severely under-assigned
---
Mean: 25.2  |  Std Dev: 10.5  |  Range: 3-42
```

**Recommended Configuration:**

```python
OUTPATIENT_SITE_CONFIG = {
    'shifts_per_period': 'variable',  # Depends on daily demand
    'cursor': 3,
    'avoid_previous': False,
    'allow_fallback': True,
}

SITE_LOCATIONS = [
    'Washington MRI',
    'Encinitas Breast',
    'Poway PET',
    # ... etc
]
```

**Key Question:** Should site-based rotations use a **single shared pool** or **separate pools per location**?

---

### 2.3 Weekend Outpatient (Weekend MRI/PET)

**Current Status:**
- 101 total assignments
- Only 10 radiologists assigned (not all 15)
- Not scheduled for John Johnson, Yonatan Rotman, Karen Yuan, Kriti Rishi, Rowena Tena

**Assignment Distribution:**
```
Brian Trinh:       14
Mark Schechter:    13
Michael Grant:     12
Eric Kim:          12
Gregory Anderson:  12
JuanCarlos Vera:   11
Eric Chou:         10
James Cooper:       8
Michael Booker:     7
Eric Lizerbram:     2
```

**Recommendation:** Per your request, **EXCLUDE from initial implementation**.

When you're ready to add these:
```python
OUTPATIENT_WEEKEND_CONFIG = {
    'shifts_per_period': 2,  # Weekend MRI + Weekend PET
    'cursor': 0,
    'avoid_previous': True,  # Coordinate with inpatient weekend if same pool
    'allow_fallback': True,
}
```

---

### 2.4 Skull Base (Subspecialty)

**Status:**
- 116 assignments to only 3 radiologists
- James Cooper (49), JuanCarlos Vera (40), Brian Trinh (27)

**Recommendation:** â›” **DO NOT** include in rotation engine. This is clearly subspecialty-based.

---

## Part 3: Combined Strategy Options

You have multiple ways to configure the rotation engine. Here are three approaches:

### Strategy A: Separate Rotations with Independent Cursors

**Use separate engines for:**
1. Inpatient Weekday (cursor=3)
2. Inpatient Weekend (cursor=6)
3. Outpatient Remote (cursor=3)
4. Outpatient Site-Based (cursor=3)

**Pros:** 
- Maximum flexibility
- Can have different radiologist pools per rotation
- Independent fairness tracking

**Cons:**
- More complex to manage
- 4 separate cursor states to track
- Could create total workload imbalance even if each rotation is fair

---

### Strategy B: Unified Inpatient + Unified Outpatient (2 Engines)

**Engine 1 - All Inpatient:**
- Weekday: M0, M1, M2, M3 (4 shifts/day)
- Weekend: M0 Weekend, EP, Dx-CALL (3 shifts/weekend)
- Single cursor tracking total inpatient assignments
- Enable back-to-back weekend avoidance

**Engine 2 - All Outpatient:**
- Remote + Site-Based rotations
- Single cursor tracking total outpatient assignments
- More complex scheduling logic for site availability

**Pros:**
- Simpler than 4 separate engines
- Ensures inpatient fairness and outpatient fairness independently
- Two cursor states

**Cons:**
- Still could have imbalance if someone gets heavy inpatient but light outpatient
- Doesn't account for total workload across both

---

### Strategy C: Tiered Rotation Pools

**Different pools for different commitment levels:**

**Pool 1 (Full-time hospital):** Heavy inpatient rotation
```
John Johnson, Eric Chou, Michael Grant, Yonatan Rotman, Gregory Anderson
```

**Pool 2 (Balanced):** Mix of inpatient and outpatient
```
Eric Lizerbram, Karen Yuan, JuanCarlos Vera, Michael Booker, Kriti Rishi
```

**Pool 3 (Outpatient-heavy):** More outpatient, less inpatient
```
James Cooper, Eric Kim, Rowena Tena, Mark Schechter, Brian Trinh
```

**Pros:**
- Matches actual workload distribution patterns
- Can weight each pool differently

**Cons:**
- Requires clear definition of who goes in which pool
- Less flexible for coverage

---

## Part 4: Recommended Implementation Plan

### Phase 1: Start with Inpatient Weekday Only (Highest Impact)

**Why:** 47.0% CV is the worst fairness metric. This needs fixing first.

```python
# roster_key.csv - all 15 radiologists in order
# Use index 0-14 as shown in section 1.1

# Configuration
config = {
    'rotation_type': 'inpatient_weekday',
    'shifts_per_period': 4,
    'cursor': 3,  # or 0 to reset for fairness
    'avoid_previous': False,
}

# Generate next 3 months
schedule, new_cursor = schedule_period(
    people=load_roster('roster_key.csv'),
    dates=get_weekdays('2026-04-01', '2026-06-30'),
    **config
)
```

**Expected Result:** CV should drop to <10% over 3 months.

---

### Phase 2: Add Inpatient Weekend (Back-to-Back Prevention)

**Why:** Already fair (14.4% CV) but adding engine ensures strict back-to-back weekend avoidance.

```python
config = {
    'rotation_type': 'inpatient_weekend',
    'shifts_per_period': 3,
    'cursor': 6,
    'avoid_previous': True,  # KEY FEATURE
}
```

---

### Phase 3: Add Outpatient Rotations

Once inpatient is stable, add outpatient remote and site-based rotations.

**Decision needed:** Should outpatient use the same cursor as inpatient (unified workload) or separate?

---

## Part 5: Critical Configuration Questions

Before implementation, you need to decide:

### Q1: Cursor Strategy

**For Inpatient Weekday:**
- **Option A:** Reset to 0 (start fresh, fix 47% CV immediately)
- **Option B:** Use 3 (maintain some continuity)
- **Recommendation:** Reset to 0 to fix fairness

**For Inpatient Weekend:**
- **Option A:** Use 6 (maintain current fair distribution)
- **Option B:** Reset to 0 (align with weekday)
- **Recommendation:** Use 6 to preserve current fairness

### Q2: FTE Weighting

Should the engine account for part-time radiologists?

**Current assumption:** Everyone gets equal assignment frequency.

**Alternative:** Weight assignments by FTE:
- 1.0 FTE â†’ 100% of rotations
- 0.8 FTE â†’ 80% of rotations
- 0.5 FTE â†’ 50% of rotations

**Estimated FTE levels (based on patterns):**
```
Full-time (1.0): John Johnson, Eric Chou, Michael Grant, Gregory Anderson, 
                 Eric Lizerbram, JuanCarlos Vera, Michael Booker, 
                 Yonatan Rotman, Eric Kim

Part-time (0.8): Brian Trinh, Karen Yuan, Rowena Tena, Kriti Rishi

Part-time (0.5): James Cooper, Mark Schechter
```

### Q3: Pool Membership

**Who participates in which rotations?**

Based on historical data, it appears all 15 radiologists participate in all rotation types (except subspecialties).

**Confirm:**
- Are there any radiologists who should NOT be in certain rotations?
- Should John Johnson be excluded from outpatient (only 18 assignments)?
- Are there subspecialty requirements beyond O'Toole and Skull Base?

### Q4: Shared vs Separate Cursors

**Option A - Separate cursors:**
- Inpatient Weekday cursor
- Inpatient Weekend cursor
- Outpatient cursor

**Option B - Unified cursor:**
- One cursor tracks total assignments across ALL rotations
- Ensures true fairness of total workload

**Recommendation:** Start with separate cursors (simpler), move to unified once stable.

---

## Part 6: Files to Create

### 1. roster_key.csv

```csv
id,index,initials,name,email,role,exempt_dates,fte,participates_inp_weekday,participates_inp_weekend,participates_outpatient
1,0,JJ,John Johnson,john@hospital.org,Radiologist,"",1.0,yes,yes,limited
2,1,EC,Eric Chou,eric.c@hospital.org,Radiologist,"",1.0,yes,yes,yes
3,2,MG,Michael Grant,michael.g@hospital.org,Radiologist,"",1.0,yes,yes,yes
4,3,YR,Yonatan Rotman,yonatan@hospital.org,Radiologist,"",1.0,yes,yes,yes
5,4,BT,Brian Trinh,brian@hospital.org,Radiologist,"",0.8,yes,yes,yes
6,5,GA,Gregory Anderson,greg@hospital.org,Radiologist,"",1.0,yes,yes,yes
7,6,EL,Eric Lizerbram,eric.l@hospital.org,Radiologist,"",1.0,yes,yes,yes
8,7,KY,Karen Yuan,karen@hospital.org,Radiologist,"",0.8,yes,yes,yes
9,8,JCV,JuanCarlos Vera,juan@hospital.org,Radiologist,"",1.0,yes,yes,yes
10,9,MB,Michael Booker,michael.b@hospital.org,Radiologist,"",1.0,yes,yes,yes
11,10,KR,Kriti Rishi,kriti@hospital.org,Radiologist,"",0.8,yes,yes,yes
12,11,JC,James Cooper,james@hospital.org,Radiologist,"",0.5,yes,yes,yes
13,12,EK,Eric Kim,eric.k@hospital.org,Radiologist,"",1.0,yes,yes,yes
14,13,RT,Rowena Tena,rowena@hospital.org,Radiologist,"",0.8,yes,yes,yes
15,14,MS,Mark Schechter,mark@hospital.org,Radiologist,"",0.5,yes,yes,yes
```

### 2. vacation_map.csv

Extract from your QGenda data (see implementation guide for script).

### 3. cursor_state.json

```json
{
  "inpatient_weekday": 3,
  "inpatient_weekend": 6,
  "outpatient_remote": 3,
  "outpatient_site": 3,
  "last_updated": "2026-03-21"
}
```

### 4. schedule_config.py

```python
INPATIENT_WEEKDAY = {
    'shifts_per_period': 4,
    'shift_names': ['M0', 'M1', 'M2', 'M3'],
    'avoid_previous': False,
    'allow_fallback': True,
}

INPATIENT_WEEKEND = {
    'shifts_per_period': 3,
    'shift_names': ['M0 Weekend', 'EP 0800-1430', 'Dx-CALL1400-2200'],
    'avoid_previous': True,
    'allow_fallback': True,
}

OUTPATIENT_REMOTE = {
    'shifts_per_period': 'variable',
    'shift_names': ['Remote MRI', 'Remote Breast', 'Remote General', 'Remote PET'],
    'avoid_previous': False,
    'allow_fallback': True,
}
```

---

## Part 7: Next Actions

1. **Verify FTE status** for all 15 radiologists
2. **Confirm pool membership** - who participates in which rotations?
3. **Decide cursor strategy** - reset or maintain?
4. **Choose implementation strategy** - A, B, or C from Part 3
5. **Extract vacation data** from QGenda
6. **Create roster_key.csv** with verified information
7. **Test on historical data** (Sept 2025 - March 2026)
8. **Generate 3-month preview** (April - June 2026)
9. **Review with group** and collect feedback
10. **Go live** with engine

---

## Summary Table: All Rotations at a Glance

| Rotation | Assignments | CV (%) | Cursor | Radiologists | Use Engine? |
|----------|------------|--------|--------|--------------|-------------|
| Inp Weekday | 498 | 47.0% âš ï¸ | 3 | 15 | âœ… Priority 1 |
| Inp Weekend | 171 | 14.4% âœ… | 6 | 15 | âš ï¸ Optional |
| Out Remote | 453 | 33.0% âš ï¸ | 3 | 15 | âœ… Priority 2 |
| Out Site-Based | 378 | 41.6% âš ï¸ | 3 | 15 | âœ… Priority 3 |
| Out Weekend MRI/PET | 101 | N/A | 0 | 10 | â¸ï¸ Later |
| O'Toole | 64 | N/A | - | 5 | âŒ Subspecialty |
| Skull Base | 116 | N/A | - | 3 | âŒ Subspecialty |
| Cardiac | 104 | N/A | - | ? | âŒ Concurrent |

**Total rotation-managed assignments:** 1,502 (498 + 171 + 453 + 378)  
**Average per radiologist:** 100.1 over 6 months  
**Target fairness:** <10% CV for all rotations
