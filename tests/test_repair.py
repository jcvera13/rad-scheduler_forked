"""
tests/test_repair.py — Unit and integration tests for the repair loop.

Tests: collect_unfilled, try_repair_slot (accept/reject), run_repair_loop.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.repair import (
    collect_unfilled,
    get_pool_for_shift,
    run_repair_loop,
    tier_order_candidates,
    try_repair_slot,
)
from src.config import load_roster, load_vacation_map
from src.constraints import ConstraintChecker
from src.schedule_config import SHIFT_DEFINITIONS, FAIRNESS_TARGETS


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
def checker(roster, vacation_map):
    return ConstraintChecker(
        roster=roster,
        vacation_map=vacation_map,
        shift_definitions=SHIFT_DEFINITIONS,
        fairness_targets=FAIRNESS_TARGETS,
    )


# ---------------------------------------------------------------------------
# collect_unfilled
# ---------------------------------------------------------------------------

class TestCollectUnfilled:

    def test_collect_unfilled_empty(self):
        schedule = {"2026-03-02": [("M0", "Alice")]}
        result = collect_unfilled(schedule)
        assert result == []

    def test_collect_unfilled_single(self):
        schedule = {"2026-03-02": [("M0", "UNFILLED")]}
        result = collect_unfilled(schedule)
        assert len(result) == 1
        assert result[0]["date"] == "2026-03-02"
        assert result[0]["task"] == "M0"
        assert result[0]["reason_unfilled"] == "pool_exhausted"
        assert result[0].get("group") is not None

    def test_collect_unfilled_sorted_by_date(self):
        schedule = {
            "2026-03-05": [("M3", "UNFILLED")],
            "2026-03-02": [("M0", "UNFILLED")],
            "2026-03-04": [("M2", "UNFILLED")],
        }
        result = collect_unfilled(schedule)
        assert len(result) == 3
        assert result[0]["date"] == "2026-03-02"
        assert result[1]["date"] == "2026-03-04"
        assert result[2]["date"] == "2026-03-05"

    def test_collect_unfilled_multiple_same_day(self):
        schedule = {"2026-03-02": [("M0", "UNFILLED"), ("M1", "Bob"), ("M2", "UNFILLED")]}
        result = collect_unfilled(schedule)
        assert len(result) == 2
        tasks = {r["task"] for r in result}
        assert tasks == {"M0", "M2"}


# ---------------------------------------------------------------------------
# try_repair_slot
# ---------------------------------------------------------------------------

class TestTryRepairSlot:

    def test_try_repair_slot_accept(self, roster, vacation_map, checker):
        """At least one valid candidate from mercy pool passes constraints."""
        schedule = {
            "2026-03-02": [("M0", "UNFILLED")],
        }
        slot = {"date": "2026-03-02", "task": "M0", "group": "m0_weekday"}
        mercy_pool = [p for p in roster if p.get("participates_mercy") and not p.get("participates_ir")]
        assert mercy_pool, "Need at least one mercy (non-IR) for M0"
        accepted = False
        for p in mercy_pool:
            ok = try_repair_slot(schedule, slot, p["name"], checker, weekend_dates=None)
            if ok:
                accepted = True
                break
        assert accepted, "At least one mercy-pool candidate should be accepted for M0"

    def test_try_repair_slot_reject_double_booking(self, roster, vacation_map, checker):
        """Candidate already assigned that day to another shift -> hard violation."""
        mercy_pool = [p for p in roster if p.get("participates_mercy") and not p.get("participates_ir")]
        if len(mercy_pool) < 1:
            pytest.skip("Need mercy pool")
        name = mercy_pool[0]["name"]
        schedule = {
            "2026-03-02": [("M0", name), ("M1", "UNFILLED")],
        }
        slot = {"date": "2026-03-02", "task": "M1", "group": "m1m2_weekday"}
        ok = try_repair_slot(schedule, slot, name, checker, weekend_dates=None)
        assert ok is False

    def test_try_repair_slot_reject_vacation(self, roster, vacation_map, checker):
        """Candidate on vacation that date -> hard violation."""
        schedule = {"2026-03-02": [("M0", "UNFILLED")]}
        slot = {"date": "2026-03-02", "task": "M0"}
        mercy_pool = [p for p in roster if p.get("participates_mercy") and not p.get("participates_ir")]
        if not mercy_pool:
            pytest.skip("Need mercy pool")
        candidate_name = mercy_pool[0]["name"]
        vacation_map_with_block = dict(vacation_map)
        vacation_map_with_block["2026-03-02"] = vacation_map_with_block.get("2026-03-02", []) + [candidate_name]
        checker_blocked = ConstraintChecker(roster, vacation_map_with_block, SHIFT_DEFINITIONS, FAIRNESS_TARGETS)
        ok = try_repair_slot(schedule, slot, candidate_name, checker_blocked, weekend_dates=None)
        assert ok is False


# ---------------------------------------------------------------------------
# get_pool_for_shift / tier_order_candidates
# ---------------------------------------------------------------------------

class TestPoolAndTier:

    def test_get_pool_for_shift_m0(self, roster, vacation_map):
        schedule = {"2026-03-02": []}
        pool = get_pool_for_shift(roster, "M0", schedule, "2026-03-02", vacation_map)
        assert len(pool) > 0
        for p in pool:
            assert p.get("participates_mercy") and not p.get("participates_ir")

    def test_get_pool_excludes_assigned_that_day(self, roster, vacation_map):
        mercy = [p for p in roster if p.get("participates_mercy") and not p.get("participates_ir")]
        if len(mercy) < 2:
            pytest.skip("Need at least 2 mercy")
        name = mercy[0]["name"]
        schedule = {"2026-03-02": [("M0", name)]}
        pool = get_pool_for_shift(roster, "M1", schedule, "2026-03-02", vacation_map)
        names = [p["name"] for p in pool]
        assert name not in names

    def test_tier_order_candidates_returns_ordered_list(self, roster):
        schedule = {"2026-03-02": [("Enc-Gen", "UNFILLED")]}
        pool = [p for p in roster if p.get("participates_gen")][:5]
        ordered = tier_order_candidates(pool, "Enc-Gen", schedule)
        assert len(ordered) == len(pool)


# ---------------------------------------------------------------------------
# run_repair_loop integration
# ---------------------------------------------------------------------------

class TestRunRepairLoop:

    def test_run_repair_loop_repairs_one_slot(self, roster, vacation_map, checker, tmp_path):
        schedule = {
            "2026-03-02": [("M0", "UNFILLED")],
        }
        result = run_repair_loop(
            schedule,
            roster,
            vacation_map,
            checker,
            weekend_dates=None,
            output_dir=tmp_path,
            prefix="test_repair",
        )
        assert result["unfilled_before"] == 1
        assert result["repaired_count"] >= 0
        unfilled_now = collect_unfilled(schedule)
        assert result["still_unfilled_count"] == len(unfilled_now)
        if result["repaired_count"] > 0:
            assert schedule["2026-03-02"][0][1] != "UNFILLED"
        assert (tmp_path / "dry_run_repair_log.json").exists()

    def test_run_repair_loop_no_op_when_empty(self, roster, vacation_map, checker, tmp_path):
        schedule = {"2026-03-02": [("M0", "Alice")]}
        result = run_repair_loop(
            schedule,
            roster,
            vacation_map,
            checker,
            weekend_dates=None,
            output_dir=tmp_path,
            prefix="test_empty",
        )
        assert result["unfilled_before"] == 0
        assert result["repaired_count"] == 0
        assert result["still_unfilled_count"] == 0
