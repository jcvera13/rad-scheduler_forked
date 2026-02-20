# Implementation Guide: QGenda Data â†’ Fair Scheduling Engine

## Overview

This guide shows how to use your historical QGenda data to configure and initialize the fair scheduling engine described in `docs_architecture.md`.

---

## Step 1: Define Your Rotation Pools

Based on your data, you have different types of shifts that need different pools of radiologists.

### Recommended Pool Structure:

```python
# pools.py

MERCY_WEEKDAY_POOL = [
    # Radiologists who rotate through M0, M1, M2, M3 weekday shifts
    "Ted Rothenberg",
    "Sina Fartash", 
    "Sharjeel Sabir",
    "John Johnson",
    # ... add full list
]

IR_POOL = [
    # Radiologists who cover IR1, IR2, PVH IR
    "Derrick Allen",
    "Ted Rothenberg",
    # ... add full list based on IR qualifications
]

WEEKEND_POOL = [
    # Radiologists who take weekend calls (EP, LP, M0 Weekend)
    # May overlap with weekday pool or be separate
]

SUBSPECIALTY_ASSIGNMENTS = {
    # Fixed assignments outside the rotation engine
    "Skull Base": ["Radiologist A", "Radiologist B"],
    "Cardiac": ["Mark Schechter"],  # Example
}
```

---

## Step 2: Create roster_key.csv

### Format from docs:

```csv
id,index,initials,name,email,role,exempt_dates,notes
```

### Example Based on Your Data:

```csv
id,index,initials,name,email,role,exempt_dates,fte,participates_mercy,participates_ir
1,0,TR,Ted Rothenberg,ted@hospital.org,Radiologist,"",1.0,yes,yes
2,1,SF,Sina Fartash,sina@hospital.org,Radiologist,"",1.0,yes,yes
3,2,SS,Sharjeel Sabir,sharjeel@hospital.org,Radiologist,"",1.0,yes,yes
4,3,JJ,John Johnson,john@hospital.org,Radiologist,"",1.0,yes,yes
5,4,DA,Derrick Allen,derrick@hospital.org,Radiologist,"",1.0,yes,yes
6,5,MG,Michael Grant,michael.g@hospital.org,Radiologist,"",1.0,yes,no
7,6,EC,Eric Chou,eric.c@hospital.org,Radiologist,"",1.0,yes,yes
8,7,GA,Gregory Anderson,greg@hospital.org,Radiologist,"",1.0,yes,yes
9,8,EL,Eric Lizerbram,eric.l@hospital.org,Radiologist,"",1.0,yes,yes
10,9,JV,JuanCarlos Vera,juan@hospital.org,Radiologist,"",1.0,yes,yes
11,10,MB,Michael Booker,michael.b@hospital.org,Radiologist,"",1.0,yes,yes
12,11,BT,Brian Trinh,brian@hospital.org,Radiologist,"",0.8,no,no
13,12,YR,Yonatan Rotman,yonatan@hospital.org,Radiologist,"",1.0,yes,yes
14,13,EK,Eric Kim,eric.k@hospital.org,Radiologist,"",1.0,yes,yes
15,14,KY,Karen Yuan,karen@hospital.org,Radiologist,"",0.8,yes,no
16,15,JC,James Cooper,james@hospital.org,Radiologist,"",0.5,no,no
17,16,RT,Rowena Tena,rowena@hospital.org,Radiologist,"",0.8,yes,no
18,17,KR,Kriti Rishi,kriti@hospital.org,Radiologist,"",0.8,yes,no
19,18,MS,Mark Schechter,mark@hospital.org,Radiologist,"",0.5,no,no
```

**Important Notes:**
1. `index` must be 0 to N-1, contiguous
2. Order matters - this defines rotation sequence
3. Add custom columns (fte, participates_mercy, etc.) as needed
4. You'll need to get actual email addresses

---

## Step 3: Extract Vacation Data from QGenda

### Python Script:

```python
import pandas as pd
from datetime import datetime

# Load your QGenda data
df = pd.read_excel('your_qgenda_export.xlsx', skiprows=1)
df['Date'] = pd.to_datetime(df['Date'])

# Extract vacation entries
vacations = df[df['Task Name'].isin(['VACATION', 'OFF ALL DAY'])]

# Create vacation map
vacation_map = {}
for _, row in vacations.iterrows():
    date_str = row['Date'].strftime('%Y-%m-%d')
    name = f"{row['First Name']} {row['Last Name']}"
    
    if date_str not in vacation_map:
        vacation_map[date_str] = []
    vacation_map[date_str].append(name)

# Save to CSV
import csv
with open('vacation_map.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['date', 'unavailable_staff'])
    for date, staff_list in vacation_map.items():
        writer.writerow([date, ';'.join(staff_list)])
```

### Resulting vacation_map.csv:

```csv
date,unavailable_staff
2025-06-23,John Johnson;Eric Chou
2025-06-24,Sina Fartash
2025-06-25,Sina Fartash
...
```

---

## Step 4: Initialize the Cursor

You have two options:

### Option A: Start Fresh (Recommended if fixing fairness issues)

```python
cursor = 0  # Everyone starts at the same point
```

**Pros:** 
- Guarantees fairness going forward
- Clears historical imbalances

**Cons:**
- Breaks continuity with current rotation
- Some radiologists may feel "skipped"

### Option B: Maintain Continuity

Based on your historical data: **cursor = 3**

This means radiologist at index 3 (John Johnson in example above) would be next up.

**Calculation:**
```
Total rotation assignments made: 883
Number of radiologists: 20
cursor = 883 % 20 = 3
```

**Pros:**
- Maintains continuity
- Feels "fair" based on history

**Cons:**
- Perpetuates existing imbalances
- Assumes historical order matches your new roster_key.csv order

### Option C: Per-Radiologist Cursor (Advanced)

Calculate each radiologist's position individually based on their historical workload.

---

## Step 5: Configure Scheduling Parameters

### Weekday Mercy Shifts:

From your `weekly_rotations.md`, you need **4 shifts per weekday** (M0, M1, M2, M3).

```python
from scheduling_engine import schedule_period

# Get weekday dates (Monday-Friday)
weekday_dates = pd.date_range(start='2026-01-01', end='2026-03-31', freq='B')

# Schedule weekday Mercy shifts
mercy_schedule, cursor = schedule_period(
    people=mercy_pool,           # From roster_key.csv, filtered to participates_mercy=yes
    dates=weekday_dates,
    shifts_per_period=4,         # M0, M1, M2, M3
    cursor=cursor,               # Initialize based on choice above
    vacation_map=vacation_map,   # From Step 3
    avoid_previous=False,        # Don't avoid back-to-back weekdays
)
```

### IR Shifts:

If IR shifts rotate independently:

```python
ir_schedule, ir_cursor = schedule_period(
    people=ir_pool,              # From roster_key.csv, filtered to participates_ir=yes
    dates=weekday_dates,
    shifts_per_period=2,         # IR-1, IR-2
    cursor=ir_cursor,            # Separate cursor for IR rotation
    vacation_map=vacation_map,
    avoid_previous=False,
)
```

### Weekend Shifts:

```python
# Get weekend dates (Saturday dates only, represents full weekend)
weekend_dates = pd.date_range(start='2026-01-01', end='2026-03-31', freq='W-SAT')

weekend_schedule, weekend_cursor = schedule_period(
    people=weekend_pool,
    dates=weekend_dates,
    shifts_per_period=6,         # Per your doc: 3 outpatient + 4-6 Mercy call = ~6 total
    cursor=weekend_cursor,
    vacation_map=vacation_map,
    avoid_previous=True,         # IMPORTANT: Avoid back-to-back weekends!
    allow_fallback=True,         # Allow minimal violations if necessary
)
```

---

## Step 6: Validate Against Historical Data

### Test Run:

Run the engine on your historical date range (2025-06-21 to 2025-12-21) and compare:

```python
# Historical dates
historical_dates = pd.date_range(start='2025-06-21', end='2025-12-21', freq='B')

# Run engine
test_schedule, _ = schedule_period(
    people=mercy_pool,
    dates=historical_dates,
    shifts_per_period=4,
    cursor=0,  # Start fresh for testing
    vacation_map=vacation_map,
    avoid_previous=False,
)

# Compare fairness
actual_counts = get_actual_counts_from_qgenda()
engine_counts = calculate_assignment_counts(test_schedule)

print("Comparison:")
for person in mercy_pool:
    actual = actual_counts.get(person, 0)
    engine = engine_counts.get(person, 0)
    diff = engine - actual
    print(f"{person:20s}: Actual={actual:3d}, Engine={engine:3d}, Diff={diff:+3d}")
```

Expected outcome: The engine should produce more balanced assignments.

---

## Step 7: Export to QGenda or Excel

### Excel Export:

```python
import pandas as pd

# Convert schedule to DataFrame
rows = []
for date_str, assignments in mercy_schedule.items():
    for shift_num, person_name in enumerate(assignments):
        rows.append({
            'Date': date_str,
            'Staff': person_name,
            'Shift': f'Mercy {shift_num}',
        })

df_export = pd.DataFrame(rows)
df_export.to_excel('mercy_schedule_output.xlsx', index=False)
```

### QGenda API Upload:

```python
import requests

# QGenda API configuration
QGENDA_API_URL = "https://api.qgenda.com/v2/schedule"
QGENDA_API_KEY = "your_api_key"

headers = {
    "Authorization": f"Bearer {QGENDA_API_KEY}",
    "Content-Type": "application/json"
}

# Upload assignments
for date_str, assignments in mercy_schedule.items():
    for shift_num, person_name in enumerate(assignments):
        payload = {
            "date": date_str,
            "staffMember": person_name,
            "task": f"Mercy {shift_num}",
            # Add other required fields
        }
        
        response = requests.post(QGENDA_API_URL, headers=headers, json=payload)
        if response.status_code != 200:
            print(f"Error uploading {date_str} {person_name}: {response.text}")
```

---

## Step 8: Monitor and Audit

### Generate Fairness Report:

```python
def generate_fairness_report(schedule, people):
    """Generate assignment counts and fairness metrics."""
    
    counts = {p['name']: 0 for p in people}
    
    for date, assignments in schedule.items():
        for person in assignments:
            counts[person] += 1
    
    mean = sum(counts.values()) / len(counts)
    std = (sum((c - mean)**2 for c in counts.values()) / len(counts))**0.5
    
    print("=== Fairness Report ===")
    print(f"Mean: {mean:.1f}")
    print(f"Std Dev: {std:.1f}")
    print(f"CV: {(std/mean*100):.1f}%")
    print("\nPer-person counts:")
    for name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        diff_from_mean = count - mean
        print(f"  {name:20s}: {count:3d} ({diff_from_mean:+.1f} from mean)")
```

**Goal:** Coefficient of variation should be < 10% for true fairness.

---

## Common Issues & Solutions

### Issue 1: "Insufficient staff for date"

**Cause:** Too many people on vacation on a single day.

**Solution:**
- Enable `allow_fallback=True` to allow minimal back-to-back violations
- Adjust vacation policy
- Increase pool size

### Issue 2: Fairness still poor after implementation

**Cause:** Different FTE levels or pool sizes.

**Solution:** Implement FTE weighting (future enhancement in architecture.md):

```python
# Weighted fairness
for person in people:
    expected_assignments = total_assignments * (person['fte'] / total_fte)
    actual = counts[person['name']]
    fairness_score = actual / expected_assignments
```

### Issue 3: Radiologists complain about cursor position

**Solution:** Communicate clearly:
- "We're starting fresh to ensure fairness going forward"
- Show fairness report from historical data
- Explain the long-term benefit

---

## Recommended Rollout Plan

1. **Week 1:** Configure roster_key.csv and vacation_map.csv
2. **Week 2:** Test engine on historical data, validate fairness
3. **Week 3:** Generate 1-month preview, share with group
4. **Week 4:** Collect feedback, adjust parameters
5. **Month 2:** Go live with 3-month schedule
6. **Month 3:** Generate first fairness audit, adjust as needed

---

## Files You Need to Create

Based on this analysis:

1. âœ… `roster_key.csv` - radiologist roster with rotation pool flags
2. âœ… `vacation_map.csv` - extracted from QGenda vacation data  
3. âœ… `cursor_state.json` - persist cursor between runs
4. â¬œ `schedule_config.py` - configuration parameters
5. â¬œ `fairness_report.py` - audit script

---

## Questions to Answer Before Implementation

1. **Pool membership:**
   - Which radiologists participate in Mercy weekday rotation?
   - Which participate in IR rotation?
   - Which participate in weekend calls?

2. **FTE levels:**
   - Who is full-time (1.0)?
   - Who is part-time (0.8, 0.5)?
   - Should part-timers have reduced shifts?

3. **Cursor strategy:**
   - Start fresh (cursor=0)?
   - Maintain continuity (cursor=3)?
   - Custom per radiologist?

4. **Weekend policy:**
   - Shared cursor with weekdays or separate?
   - Strict back-to-back avoidance or fallback allowed?

5. **Subspecialty handling:**
   - Which shifts stay outside the rotation engine?
   - Who has fixed assignments?

Answer these and you're ready to implement!
