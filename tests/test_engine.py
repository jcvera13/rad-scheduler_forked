"""
Tests for scheduling engine (cursor fairness, vacation awareness, weighted shifts)
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.engine import schedule_period, schedule_weekday_mercy, calculate_fairness_metrics
from src.config import load_roster, load_vacation_map, filter_pool, get_shift_weight


class TestSchedulePeriod:
    """Test core schedule_period algorithm"""

    @pytest.fixture
    def sample_people(self):
        return [
            {"name": "Alice", "index": 0, "fte": 1.0},
            {"name": "Bob", "index": 1, "fte": 1.0},
            {"name": "Carol", "index": 2, "fte": 1.0},
        ]

    def test_basic_schedule(self, sample_people):
        """Simple 3-day schedule, 2 shifts/day"""
        dates = [date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)]
        schedule, cursor = schedule_period(
            people=sample_people,
            dates=dates,
            shifts_per_period=2,
            shift_names=["S1", "S2"],
            cursor=0,
            use_weighted_cursor=False,
        )
        assert len(schedule) == 3
        for d, assignments in schedule.items():
            assert len(assignments) == 2
            names = [a[1] for a in assignments]
            assert len(names) == len(set(names))  # No duplicates per day

    def test_vacation_skipped(self, sample_people):
        """Vacation person is skipped, cursor advances for others"""
        dates = [date(2026, 3, 1)]
        vacation_map = {"2026-03-01": ["Alice"]}
        schedule, _ = schedule_period(
            people=sample_people,
            dates=dates,
            shifts_per_period=2,
            cursor=0,
            vacation_map=vacation_map,
        )
        names = [a[1] for a in schedule["2026-03-01"]]
        assert "Alice" not in names
        assert len(names) == 2


class TestShiftWeights:
    """Test weighted cursor (M0=0.25, M1=1.0)"""

    def test_m0_weight(self):
        assert get_shift_weight("M0") == 0.25

    def test_m1_weight(self):
        assert get_shift_weight("M1") == 1.0

    def test_m3_weight(self):
        assert get_shift_weight("M3") == 0.75


class TestFairnessMetrics:
    """Test calculate_fairness_metrics"""

    def test_metrics_shape(self):
        schedule = {
            "2026-03-01": [("M0", "Alice"), ("M1", "Bob")],
            "2026-03-02": [("M0", "Carol"), ("M1", "Alice")],
        }
        people = [
            {"name": "Alice", "index": 0},
            {"name": "Bob", "index": 1},
            {"name": "Carol", "index": 2},
        ]
        metrics = calculate_fairness_metrics(schedule, people)
        assert "mean" in metrics
        assert "cv" in metrics
        assert "counts" in metrics
        assert "weighted_counts" in metrics
