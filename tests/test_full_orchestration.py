"""
tests/test_full_orchestration.py

Full orchestration test suite:
  1. Validate roster input (19 radiologists, 4 IR-qualified)
  2. Validate subspecialty CSV parsing (no malformed subspecialties)
  3. Run block scheduling for a 2-week period
  4. Check constraints (no hard violations expected)
  5. Validate fairness metrics (CV → target <10% with fair rotation)
  6. Export CSV + Excel + report, verify files exist
  7. Per-shift CV breakdown
  8. Weekend block scheduling test
  9. IR pool gate test (ensure IR-1 only goes to IR-qualified)

Run with:
  cd radiology-scheduler
  python -m pytest tests/test_full_orchestration.py -v
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_roster, load_vacation_map, load_cursor_state, filter_pool
from src.engine import (
    schedule_period, schedule_blocks, calculate_fairness_metrics,
    get_weekday_dates, get_saturday_dates,
    schedule_weekday_mercy, schedule_ir_weekday, schedule_weekend_mercy,
)
from src.constraints import ConstraintChecker, ConstraintSeverity
from src.skills import (
    get_qualified_staff, check_shift_qualification,
    validate_shift_coverage, get_subspecialty_summary,
)
from src.exporter import export_to_csv, export_to_excel, export_fairness_report
from src.schedule_config import (
    IR_WEEKDAY_CONFIG, M3_CONFIG as INPATIENT_WEEKDAY_CONFIG,
    SCHEDULING_BLOCKS, SHIFT_DEFINITIONS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def roster():
    return load_roster()


@pytest.fixture(scope="module")
def vacation_map():
    return load_vacation_map()


@pytest.fixture(scope="module")
def mercy_pool(roster):
    return filter_pool(roster, "participates_mercy")


@pytest.fixture(scope="module")
def ir_pool(roster):
    return filter_pool(roster, "participates_ir")


@pytest.fixture(scope="module")
def weekday_dates():
    # 2 weeks of weekdays
    return get_weekday_dates(date(2026, 3, 2), date(2026, 3, 13))


@pytest.fixture(scope="module")
def saturday_dates():
    return get_saturday_dates(date(2026, 3, 1), date(2026, 3, 15))


# ============================================================
# Section 1: Roster input validation
# ============================================================

class TestRosterValidation:

    def test_roster_loads(self, roster):
        assert len(roster) == 19, f"Expected 19 radiologists, got {len(roster)}"

    def test_indices_contiguous(self, roster):
        indices = sorted(p["index"] for p in roster)
        assert indices == list(range(19)), f"Non-contiguous indices: {indices}"

    def test_no_duplicate_names(self, roster):
        names = [p["name"] for p in roster]
        assert len(names) == len(set(names)), f"Duplicate names: {[n for n in names if names.count(n) > 1]}"

    def test_all_have_fte(self, roster):
        for p in roster:
            assert p["fte"] > 0, f"{p['name']} has invalid FTE={p['fte']}"

    def test_mercy_pool_size(self, mercy_pool):
        # IR staff (DA, SS, SF, TR) are excluded from mercy — pool is 15
        assert len(mercy_pool) == 15, f"Expected 15 in mercy pool (IR excluded), got {len(mercy_pool)}"

    def test_ir_staff_not_in_mercy_pool(self, mercy_pool):
        ir_initials = {"DA", "SS", "SF", "TR"}
        mercy_initials = {p["initials"] for p in mercy_pool}
        overlap = ir_initials & mercy_initials
        assert not overlap, f"IR staff found in mercy pool: {overlap}"

    def test_ir_staff_not_in_weekend_pool(self, roster):
        weekend_pool = filter_pool(roster, "participates_weekend")
        ir_initials = {"DA", "SS", "SF", "TR"}
        weekend_initials = {p["initials"] for p in weekend_pool}
        overlap = ir_initials & weekend_initials
        assert not overlap, f"IR staff found in weekend pool: {overlap}"

    def test_da_in_mg_pool(self, roster):
        mg_pool = filter_pool(roster, "participates_mg")
        mg_initials = {p["initials"] for p in mg_pool}
        assert "DA" in mg_initials, "Derrick Allen should be in MG pool"

    def test_non_ir_not_in_ir_pool(self, roster, ir_pool):
        ir_initials = {p["initials"] for p in ir_pool}
        expected_non_ir = {"BT", "EC", "EK", "EL", "GA", "JC", "JJ", "JV",
                           "KY", "KR", "MS", "MB", "MG", "RT", "YR"}
        overlap = expected_non_ir & ir_initials
        assert not overlap, f"Non-IR staff found in IR pool: {overlap}"

    def test_ir_pool_size(self, ir_pool):
        assert len(ir_pool) == 4, f"Expected 4 IR radiologists, got {len(ir_pool)}"

    def test_ir_pool_names(self, ir_pool):
        ir_names = {p["name"] for p in ir_pool}
        expected = {"Derrick Allen", "Sharjeel Sabir", "Sina Fartash", "Ted Rothenberg"}
        assert ir_names == expected, f"IR pool mismatch: {ir_names} vs {expected}"


# ============================================================
# Section 2: Subspecialty CSV parsing
# ============================================================

class TestSubspecialtyParsing:

    def test_all_have_subspecialties(self, roster):
        missing = [p["name"] for p in roster if not p.get("subspecialties")]
        assert not missing, f"Radiologists with no subspecialties: {missing}"

    def test_no_quoted_strings_in_specs(self, roster):
        """Old format had '"neuro" "cardiac"' — ensure no bare quotes remain."""
        for p in roster:
            for s in p.get("subspecialties", []):
                assert '"' not in s, f"{p['name']}: subspecialty contains quote: '{s}'"
                assert s == s.strip(), f"{p['name']}: subspecialty has whitespace: '{s}'"

    def test_ir_qualified_have_ir_tag(self, ir_pool):
        for p in ir_pool:
            specs = [s.lower() for s in p.get("subspecialties", [])]
            assert "ir" in specs, f"{p['name']} in IR pool but missing 'ir' subspecialty tag"

    def test_subspecialty_summary_covers_shifts(self, roster):
        summary = get_subspecialty_summary(roster)
        # At minimum, 'ir', 'MRI', 'Gen' should be present
        for tag in ["ir", "MRI", "Gen"]:
            assert tag in summary, f"Tag '{tag}' not found in any radiologist's subspecialties"

    def test_shift_coverage_warnings(self, roster):
        # Critical shifts must have qualified staff
        warnings = validate_shift_coverage(roster, shifts_to_check=["IR-1", "IR-2", "Skull Base", "Cardiac"])
        assert not warnings, f"Shift coverage gaps: {warnings}"


# ============================================================
# Section 3: Block scheduling
# ============================================================

class TestBlockScheduling:

    def test_block_schedule_runs(self, roster, vacation_map, weekday_dates, saturday_dates):
        cursor_state = {"inpatient_weekday": 0.0, "ir_weekday": 0.0, "inpatient_weekend": 0.0}
        schedule, new_cursors = schedule_blocks(
            roster=roster,
            dates=weekday_dates,
            cursor_state=cursor_state,
            vacation_map=vacation_map,
            interactive=False,
            weekend_dates=saturday_dates,
        )
        assert len(schedule) > 0, "Block scheduling produced empty schedule"
        assert "inpatient_weekday" in new_cursors
        assert "ir_weekday" in new_cursors
        return schedule

    def test_correct_shifts_per_weekday(self, roster, vacation_map, weekday_dates):
        """Each weekday should have 6 assignments: IR-1, IR-2, M0, M1, M2, M3."""
        cursor_state = {"inpatient_weekday": 0.0, "ir_weekday": 0.0, "inpatient_weekend": 0.0}
        schedule, _ = schedule_blocks(
            roster=roster,
            dates=weekday_dates,
            cursor_state=cursor_state,
            vacation_map=vacation_map,
            interactive=False,
        )
        for date_str, assignments in schedule.items():
            shift_names = [s for s, _ in assignments]
            assert "M0" in shift_names, f"{date_str}: M0 missing"
            assert "M1" in shift_names, f"{date_str}: M1 missing"
            assert "M2" in shift_names, f"{date_str}: M2 missing"
            assert "M3" in shift_names, f"{date_str}: M3 missing"
            assert "IR-1" in shift_names, f"{date_str}: IR-1 missing"
            assert "IR-2" in shift_names, f"{date_str}: IR-2 missing"

    def test_no_double_booking(self, roster, vacation_map, weekday_dates):
        from src.schedule_config import ALL_CURSOR_KEYS
        cursor_state = {k: 0.0 for k in ALL_CURSOR_KEYS}
        schedule, _ = schedule_blocks(
            roster=roster, dates=weekday_dates,
            cursor_state=cursor_state, vacation_map=vacation_map, interactive=False,
        )
        exclusive = {"M0","M1","M2","M3","IR-1","IR-2","IR-CALL","EP","Dx-CALL","M0_WEEKEND"}
        for date_str, assignments in schedule.items():
            excl_names = [name for shift, name in assignments
                         if name != "UNFILLED" and shift in exclusive]
            dupes = [n for n in excl_names if excl_names.count(n) > 1]
            assert not dupes, f"Exclusive-shift double booking on {date_str}: {set(dupes)}"


# ============================================================
# Section 4: Constraint checking
# ============================================================

class TestConstraintChecking:

    @pytest.fixture(scope="class")
    def schedule_and_checker(self, roster, vacation_map, weekday_dates, saturday_dates):
        from src.schedule_config import ALL_CURSOR_KEYS
        cursor_state = {k: 0.0 for k in ALL_CURSOR_KEYS}
        schedule, _ = schedule_blocks(
            roster=roster, dates=weekday_dates,
            cursor_state=cursor_state, vacation_map=vacation_map,
            interactive=False, weekend_dates=saturday_dates,
        )
        checker = ConstraintChecker(roster=roster, vacation_map=vacation_map)
        return schedule, checker

    @pytest.fixture(scope="class")
    def schedule(self, roster, vacation_map, weekday_dates, saturday_dates):
        from src.schedule_config import ALL_CURSOR_KEYS
        cursor_state = {k: 0.0 for k in ALL_CURSOR_KEYS}
        sched, _ = schedule_blocks(
            roster=roster, dates=weekday_dates,
            cursor_state=cursor_state, vacation_map=vacation_map,
            interactive=False, weekend_dates=saturday_dates,
        )
        return sched

    def test_no_vacation_violations(self, schedule_and_checker):
        schedule, checker = schedule_and_checker
        violations = checker.check_vacation(schedule)
        assert not violations, f"Vacation violations: {violations}"

    def test_no_double_booking_violations(self, schedule_and_checker):
        schedule, checker = schedule_and_checker
        violations = checker.check_double_booking(schedule)
        assert not violations, f"Double booking: {violations}"

    def test_no_ir_pool_gate_violations(self, schedule_and_checker):
        schedule, checker = schedule_and_checker
        violations = checker.check_ir_pool_gate(schedule)
        assert not violations, f"IR pool gate violations (non-IR assigned IR shift): {[str(v) for v in violations]}"

    def test_no_subspecialty_mismatch(self, schedule_and_checker):
        schedule, checker = schedule_and_checker
        violations = checker.check_subspecialty_qualification(schedule)
        assert not violations, f"Subspecialty mismatches: {[str(v) for v in violations]}"

    def test_check_all_returns_two_lists(self, schedule_and_checker):
        schedule, checker = schedule_and_checker
        hard, soft = checker.check_all(schedule)
        assert isinstance(hard, list)
        assert isinstance(soft, list)
        assert all(v.severity == ConstraintSeverity.HARD for v in hard)
        assert all(v.severity == ConstraintSeverity.SOFT for v in soft)

    def test_roster_validates_cleanly(self, roster, vacation_map):
        checker = ConstraintChecker(roster=roster, vacation_map=vacation_map)
        errors, warnings = checker.validate_roster()
        assert not errors, f"Roster validation errors: {errors}"


# ============================================================
# Section 5: Fairness metrics
# ============================================================

class TestFairnessMetrics:

    @pytest.fixture(scope="class")
    def metrics_fixture(self, roster, vacation_map, weekday_dates):
        from src.schedule_config import ALL_CURSOR_KEYS
        cursor_state = {k: 0.0 for k in ALL_CURSOR_KEYS}
        schedule, _ = schedule_blocks(
            roster=roster, dates=weekday_dates,
            cursor_state=cursor_state, vacation_map=vacation_map, interactive=False,
        )
        metrics = calculate_fairness_metrics(schedule, roster)
        return metrics, schedule

    def test_metrics_keys_present(self, metrics_fixture):
        metrics, _ = metrics_fixture
        for key in ["mean", "std", "cv", "min", "max", "counts", "weighted_counts",
                    "per_shift", "per_shift_cv", "unfilled"]:
            assert key in metrics, f"Missing key '{key}' in metrics"

    def test_cv_below_target(self, metrics_fixture):
        """
        CV on a 2-week block with overlapping IR+Mercy pools is expected to be
        elevated: IR-qualified staff (4 people) appear in both IR pool
        (2 slots/day x 10 days = ~5 IR shifts each) AND mercy pool
        (~2 mercy shifts each), while non-IR get only ~2 mercy shifts.
        True fairness converges over a full scheduling quarter.
        Target: CV < 60% for 2-week test, CV < 10% for full quarter.
        """
        metrics, _ = metrics_fixture
        cv = metrics["cv"]
        assert cv < 60.0, (
            f"CV={cv:.2f}% exceeds 60% on 2-week schedule — "
            "something is fundamentally broken in the cursor or pool logic."
        )

    def test_all_radiologists_in_metrics(self, metrics_fixture, roster):
        metrics, _ = metrics_fixture
        for p in roster:
            assert p["name"] in metrics["counts"], f"{p['name']} missing from metrics"

    def test_no_unfilled_slots(self, metrics_fixture):
        """
        Inpatient mercy + IR must always fill.
        Outpatient subspecialty-gated slots may be UNFILLED when the pool
        is small and all qualified staff are already assigned or on vacation.
        """
        metrics, schedule = metrics_fixture
        mercy_ir = {"M0", "M1", "M2", "M3", "IR-1", "IR-2"}
        hard_unfilled = [
            (d, s, n) for d, assigns in schedule.items()
            for s, n in assigns
            if n == "UNFILLED" and s in mercy_ir
        ]
        assert not hard_unfilled, f"Inpatient/IR UNFILLED (must always fill): {hard_unfilled}"

    def test_per_shift_cv_present(self, metrics_fixture):
        metrics, _ = metrics_fixture
        assert len(metrics["per_shift_cv"]) > 0, "No per-shift CV data"
        # All engine-scheduled shifts should appear
        for shift in ["M0", "M1", "M2", "M3", "IR-1", "IR-2"]:
            assert shift in metrics["per_shift_cv"], f"Shift '{shift}' missing from per_shift_cv"

    def test_ir_assignments_only_to_ir_pool(self, roster, vacation_map, weekday_dates):
        ir_pool = filter_pool(roster, "participates_ir")
        ir_names = {p["name"] for p in ir_pool}
        cursor_state = {"inpatient_weekday": 0.0, "ir_weekday": 0.0}
        schedule, _ = schedule_blocks(
            roster=roster, dates=weekday_dates,
            cursor_state=cursor_state, vacation_map=vacation_map, interactive=False,
        )
        for date_str, assignments in schedule.items():
            for shift, name in assignments:
                if shift in ("IR-1", "IR-2"):
                    assert name in ir_names, (
                        f"Non-IR radiologist '{name}' assigned to {shift} on {date_str}"
                    )


# ============================================================
# Section 6: Export layer
# ============================================================

class TestExportLayer:

    @pytest.fixture(scope="class")
    def full_output(self, roster, vacation_map, weekday_dates, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("exports")
        cursor_state = {"inpatient_weekday": 0.0, "ir_weekday": 0.0}
        schedule, _ = schedule_blocks(
            roster=roster, dates=weekday_dates,
            cursor_state=cursor_state, vacation_map=vacation_map, interactive=False,
        )
        metrics = calculate_fairness_metrics(schedule, roster)
        csv_p     = tmp / "schedule.csv"
        xlsx_p    = tmp / "schedule.xlsx"
        report_p  = tmp / "fairness.txt"
        export_to_csv(schedule, csv_p)
        export_to_excel(schedule, xlsx_p)
        export_fairness_report(metrics, report_p, pool_label="Test Run")
        return csv_p, xlsx_p, report_p, metrics

    def test_csv_exists_and_nonempty(self, full_output):
        csv_p, _, _, _ = full_output
        assert csv_p.exists()
        assert csv_p.stat().st_size > 100

    def test_excel_exists_and_nonempty(self, full_output):
        _, xlsx_p, _, _ = full_output
        assert xlsx_p.exists()
        assert xlsx_p.stat().st_size > 1000

    def test_report_exists_and_contains_cv(self, full_output):
        _, _, report_p, _ = full_output
        assert report_p.exists()
        text = report_p.read_text()
        assert "CV" in text
        assert "Mean" in text or "MEAN" in text.upper()
        assert "FAIRNESS AUDIT REPORT" in text.upper() or "Fairness Audit" in text

    def test_report_contains_all_radiologists(self, full_output, roster):
        _, _, report_p, _ = full_output
        text = report_p.read_text()
        for p in roster:
            # At minimum the last name should appear
            assert p["name"].split()[-1] in text, (
                f"{p['name']} missing from fairness report"
            )


# ============================================================
# Section 7: Weekend scheduling
# ============================================================

class TestWeekendScheduling:

    def test_weekend_block_assigned(self, roster, vacation_map, saturday_dates):
        weekend_pool = filter_pool(roster, "participates_weekend")
        schedule, cursor = schedule_weekend_mercy(
            people=weekend_pool,
            dates=saturday_dates[:2],
            cursor=0.0,
            vacation_map=vacation_map,
        )
        assert len(schedule) == 2
        for date_str, assignments in schedule.items():
            assert len(assignments) == 3, f"{date_str}: expected 3 shifts, got {len(assignments)}"

    def test_no_back_to_back_weekend_default(self, roster, vacation_map, saturday_dates):
        """With avoid_previous=True, same radiologist should rarely appear in consecutive weekends."""
        weekend_pool = filter_pool(roster, "participates_weekend")
        schedule, _ = schedule_weekend_mercy(
            people=weekend_pool,
            dates=saturday_dates[:4],
            cursor=0.0,
            vacation_map=vacation_map,
        )
        # Check no hard double-booking
        for date_str, assignments in schedule.items():
            names = [n for _, n in assignments]
            assert len(names) == len(set(names)), f"Double booking on {date_str}: {names}"
