# Radiology Scheduler — Pool Membership & Assignment Rules

**Version:** 3.1.0  
**Last Updated:** 2026-02-21  
**Source of truth:** `roster_key.csv`, `schedule_config.py`

---

## Pool Definitions

The 19 radiologists are divided into two primary pools. Pool membership is
enforced at two independent levels: roster flags (`roster_key.csv`) and
engine-level `exclude_ir` gate (`schedule_config.py`). Both must pass.

---

### IR Pool — 4 Radiologists

| Initials | Name | Additional Eligibility |
|---|---|---|
| DA | Derrick Allen | MG/Breast + O'Toole + Gen + outpatient sites |
| SS | Sharjeel Sabir | Gen only |
| SF | Sina Fartash | Gen only |
| TR | Ted Rothenberg | Gen only |

**IR pool is eligible for:**
- ✅ IR-1, IR-2, IR-CALL (requires `ir` subspecialty tag)
- ✅ Remote-Gen, Enc-Gen, Poway-Gen, NC-Gen (requires `Gen` tag)
- ✅ DA only: Remote-Breast, Wash-Breast, O'Toole (requires `MG` tag)

**IR pool is hard-excluded from:**
- ❌ M0, M1, M2, M3 (`exclude_ir=True` on all mercy blocks)
- ❌ M0_WEEKEND, EP, Dx-CALL (`exclude_ir=True` on all weekend inpatient blocks)
- ❌ Any MRI shifts — SS/SF/TR do not have `MRI` tag
- ❌ Any PET shifts — IR staff do not have `PET` tag
- ❌ Site-based MRI/Breast for SS/SF/TR (no `MRI`/`MG` tags)

---

### Non-IR Pool — 15 Radiologists

| Initials | Name | Subspecialty Tags |
|---|---|---|
| BT | Brian Trinh | neuro, cardiac, nm, MRI, Gen, MRI+Proc |
| EC | Eric Chou | MRI, Gen |
| EK | Eric Kim | PET, MG, Gen |
| EL | Eric Lizerbram | MRI, Gen, MRI+Proc |
| GA | Gregory Anderson | MRI, Gen, MRI+Proc |
| JC | James Cooper | MG, MRI, Gen, neuro, MRI+Proc |
| JJ | John Johnson | MG, Gen, cardiac |
| JCV | JuanCarlos Vera | neuro, nm, MRI, Gen, MRI+Proc |
| KY | Karen Yuan | MRI, Gen, MRI+Proc, MG |
| KR | Kriti Rishi | MG, Gen |
| MS | Mark Schechter | nm, Gen, MG |
| MB | Michael Booker | MRI, MRI+Proc, PET, Gen, Proc |
| MG | Michael Grant | PET, Gen |
| RT | Rowena Tena | MG, Gen |
| YR | Yonatan Rotman | PET, Gen |

**Non-IR pool is eligible for:**
- ✅ M0, M1, M2, M3
- ✅ M0_WEEKEND, EP, Dx-CALL
- ✅ Gen shifts (all have `Gen` tag)
- ✅ MRI shifts if they have `MRI` tag (BT, EC, EL, GA, JC, JCV, KY, MB); **Wash-MRI** requires `MRI+Proc` (EL, GA, JC, JCV, KY, MB)
- ✅ Breast/O'Toole if they have `MG` tag (EK, JC, JJ, KR, KY, MS, RT)
- ✅ PET shifts if they have `PET` tag (EK, MB, MG, YR)

**Non-IR pool is never assigned:**
- ❌ IR-1, IR-2, IR-CALL (no `ir` tag; `participates_ir=no`)

---

## Assignment Matrix

`✅` = eligible  `❌` = excluded  `—` = N/A (wrong pool)

| Shift | DA | SS/SF/TR | Non-IR (MRI) | Non-IR (MG) | Non-IR (PET) | Non-IR (Gen) |
|---|---|---|---|---|---|---|
| IR-1 / IR-2 | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| IR-CALL | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| M0 / M1 / M2 / M3 | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| EP / Dx-CALL / M0_WEEKEND | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Remote-Gen / Site Gen | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Remote-MRI / Site MRI | ❌ | ❌ | ✅ | depends | depends | ❌ |
| Wash-MRI (Washington MRI) | ❌ | ❌ | ❌ | ✅ (MRI+Proc only) | ❌ | ❌ |
| Remote-Breast / Site Breast | ✅ | ❌ | depends | ✅ | depends | ❌ |
| O'Toole | ✅ | ❌ | depends | ✅ | depends | ❌ |
| Remote-PET / Site PET | ❌ | ❌ | depends | depends | ✅ | ❌ |
| Wknd-MRI | ❌ | ❌ | ✅ | depends | depends | ❌ |
| Wknd-PET | ❌ | ❌ | depends | depends | ✅ | ❌ |

*"depends" = eligible only if that individual also has the required tag*

---

## Concurrent vs. Exclusive Assignments

**Exclusive shifts** — a radiologist may hold only ONE of these per day:

```
M0   M1   M2   M3
IR-1   IR-2   IR-CALL   PVH-IR
EP   Dx-CALL   M0_WEEKEND
```

**Concurrent shifts** — a radiologist may hold any number of these alongside
an exclusive shift or alongside each other on the same day:

```
All outpatient: Remote-Gen, Remote-MRI, Remote-Breast, Remote-PET
All site-based: Wash-MRI, Wash-Breast, Enc-MRI, Enc-Breast, Enc-Gen,
                Poway-MRI, Poway-PET, Poway-Gen, NC-Gen
Weekend outpatient: Wknd-MRI, Wknd-PET
Fixed subspecialty: O'Toole, Skull-Base, Cardiac
```

Real examples from QGenda data (Jan–Mar 2026):
- **James Cooper:** Remote-MRI + Skull-Base (same day)
- **James Cooper:** M3 + O'Toole + Skull-Base (same day, three assignments)
- **John Johnson:** M1 + Cardiac (same day)
- **JuanCarlos Vera:** Remote-MRI + Skull-Base (same day)

---

## Fixed Subspecialty Assignments (Not Engine-Managed)

These assignments are concurrent and not included in fairness rotation:

| Shift | Assigned Staff | Notes |
|---|---|---|
| Skull-Base | JuanCarlos Vera, James Cooper, Brian Trinh | Runs with primary rotation |
| Cardiac | John Johnson, Brian Trinh | Runs with primary rotation |

These appear in QGenda but are excluded from CV calculations (weight = 0.00).

---

## Weekend Rules

- **Same crew Saturday and Sunday.** The engine schedules Saturdays; Sunday
  entries are automatically mirrored.
- **EP shift:** on-site Saturday, remote Sunday. Same person both days;
  location difference is a QGenda shift property.
- **IR staff excluded from all weekend inpatient shifts.**
- **IR staff excluded from Wknd-MRI and Wknd-PET** (no MRI/PET tags).

---

## O'Toole Rules

- Runs **Tuesday, Wednesday, Friday only** (weekdays 1, 2, 4 in Python's 0=Mon). The block scheduler applies `allowed_weekdays` so O'Toole is never scheduled on Mon/Thu.
- Pool: `participates_mg=yes` + `MG` subspecialty tag.
- Eligible staff: DA, EK, JC, JJ, KR, KY, MS, RT (8 total).
- Concurrent with any primary rotation assignment.

## Wash-MRI (Washington MRI)

- Staffed only by radiologists with the **MRI+Proc** subspecialty tag in `roster_key.csv`.
- Eligible staff: EL, GA, JC, JCV, KY, MB (6 with MRI+Proc). Other MRI-tagged staff are not eligible for Wash-MRI.
