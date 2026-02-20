* **`docs/architecture.md`** â†’ deep technical design, algorithms, and developer logic
## Documentation

* **System design & algorithms:** `docs/architecture.md`

---

## Summary

This engine provides a single, unified solution for fair, vacation-safe scheduling of multiple daily shifts
across weekdays and weekends, designed for coverage of real-world hospital and outpatient operations by a single radiology group with greater than 10+ radiologists with differences in skillsets/subspecialization.


```markdown
# Scheduling Engine Architecture

This document describes elements of the **internal design, algorithms, and guarantees**
of the Fair Radiologist Scheduling Engine.

It is intended for developers extending or maintaining the system.

---

## Design Goals

1. Long-term fairness
2. Deterministic, auditable schedules
3. Vacation-safe logic
4. Unified handling of weekdays and weekends
5. Simple extensibility

---

## Core Concept: Infinite Modulo Stream

Radiologists are defined in a fixed order:

````

people = [P0, P1, P2, â€¦, PN-1]

```

This list is treated as an infinite stream:

```

P0 â†’ P1 â†’ â€¦ â†’ PN-1 â†’ P0 â†’ P1 â†’ â€¦

````

A **global cursor** (`stream_pos`) moves forward as assignments are made.

Each assignment consumes **exactly one** stream position.

---

## Vacation Handling (Key Fairness Rule)

If a radiologist is unavailable on a given date:

- They are skipped during probing
- Their stream position is **not consumed**
- They retain their place in the long-term rotation

This ensures vacations do **not reduce future workload fairness**.

---

## Back-to-Back Weekend Avoidance

### Purpose
Prevent consecutive weekend assignments when possible.

### Mechanism
- Track `last_week_assigned`
- Soft-block those radiologists for the next weekend

### Modes
- **Strict:** fail if insufficient staff remain
- **Fallback:** allow minimal violation to complete schedule

This rule is **not applied to weekdays** by default.

---

## Scheduling Algorithm (Detailed)

### Pseudocode

```text
Initialize stream_pos

For each scheduling period:
    assigned = {}
    unavailable = vacations + optional policy exclusions

    For each shift:
        probe = stream_pos
        while true:
            candidate = people[probe % N]
            if candidate acceptable:
                assign
                stream_pos = probe + 1
                break
            probe += 1
````

---

## Reference Python Implementation

```python
def schedule_period(
    people,
    dates,
    shifts_per_period,
    cursor=0,
    vacation_map=None,
    avoid_previous=None,
    allow_fallback=True,
):
    N = len(people)
    name_list = [p["name"] for p in people]
    schedule = {}
    stream_pos = cursor
    last_assigned = set()

    for d in dates:
        key = d.strftime("%Y-%m-%d")
        unavailable = set(vacation_map.get(key, []))
        if avoid_previous:
            unavailable |= last_assigned

        assigned = []

        for _ in range(shifts_per_period):
            probe = stream_pos
            tries = 0
            chosen = None

            while tries < N * 2:
                c = name_list[probe % N]
                if c not in unavailable and c not in assigned:
                    chosen = c
                    stream_pos = probe + 1
                    assigned.append(c)
                    break
                probe += 1
                tries += 1

            if chosen is None:
                if allow_fallback:
                    unavailable -= last_assigned
                    continue
                raise RuntimeError(f"Insufficient staff for {key}")

        last_assigned = set(assigned)
        schedule[key] = assigned

    return schedule, stream_pos
```

---

## Weekday vs Weekend Handling

| Aspect       | Weekday     | Weekend  |
| -------------| ----------- | -------- |
| Back-to-back | Disabled    | Optional |
| Cursor       | Shared      | Shared   |

Both use the **same engine**.

---

## Fairness Guarantees

* Equal assignment frequency over time
* No penalty for vacations
* Deterministic output
* No duplicate assignments per period

---

## Validation Rules

Implementations should validate:

* Indices are contiguous (0â€¦N-1)
* Enough staff exist for required shifts
* Dates are normalized (MM-DD-YYYY)
* Cursor is persisted across runs

---

## Extensibility Points

Planned extensions:

* FTE-weighted fairness
* Separate Saturday/Sunday streams
* Preference rules
* GUI / calendar export
* Metrics and audits

---

## Design Summary

This architecture provides:

* A single fairness engine
* Policy layering without complexity
* Clear failure modes
* Long-term operational stability
* Suitable hospital-grade scheduling systems.

```
