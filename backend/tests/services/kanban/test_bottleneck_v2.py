"""
backend/tests/services/kanban/test_bottleneck_v2.py — Tests for bottleneck detector v2.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from kanban.bottleneck_detector import (
    compute_metrics,
    detect_bottlenecks,
    format_alert,
    run_check,
)


class TestComputeMetrics:
    def test_empty(self):
        assert compute_metrics([]) == {}

    def test_single_agent(self):
        cards = [
            {"assignee": "Agent 1", "status": "in_progress", "blockers": [], "last_update": "2026-05-19T20:00:00Z"},
            {"assignee": "Agent 1", "status": "done", "blockers": [], "last_update": "2026-05-19T20:00:00Z"},
        ]
        m = compute_metrics(cards)
        assert "Agent 1" in m
        assert m["Agent 1"]["cards_in_progress"] == 1
        assert m["Agent 1"]["cards_done"] == 1

    def test_blocker_count(self):
        cards = [
            {"assignee": "Agent 1", "status": "blocked", "blockers": ["waiting on X", "waiting on Y"], "last_update": "2026-05-19T20:00:00Z"},
        ]
        m = compute_metrics(cards)
        assert m["Agent 1"]["blocker_count"] == 2
        assert m["Agent 1"]["blocker_rate"] == 2.0

    def test_multiple_agents(self):
        cards = [
            {"assignee": "Agent 1", "status": "in_progress", "blockers": [], "last_update": "2026-05-19T20:00:00Z"},
            {"assignee": "Agent 2", "status": "ready", "blockers": [], "last_update": "2026-05-19T20:00:00Z"},
        ]
        m = compute_metrics(cards)
        assert len(m) == 2


class TestDetectBottlenecks:
    def test_no_bottlenecks(self):
        metrics = {
            "Agent 1": {"cards_in_progress": 1, "blocker_rate": 0.1, "max_stale_hours": 1,
                        "cards_ready": 0, "total_wait_hours": 0},
            "Agent 2": {"cards_in_progress": 1, "blocker_rate": 0.1, "max_stale_hours": 2,
                        "cards_ready": 0, "total_wait_hours": 0},
        }
        result = detect_bottlenecks(metrics)
        assert result == []

    def test_overloaded_agent(self):
        metrics = {
            "Agent 1": {"cards_in_progress": 10, "blocker_rate": 0.1, "max_stale_hours": 1,
                        "cards_ready": 0, "total_wait_hours": 0},
            "Agent 2": {"cards_in_progress": 1, "blocker_rate": 0.1, "max_stale_hours": 1,
                        "cards_ready": 0, "total_wait_hours": 0},
            "Agent 3": {"cards_in_progress": 1, "blocker_rate": 0.1, "max_stale_hours": 1,
                        "cards_ready": 0, "total_wait_hours": 0},
        }
        result = detect_bottlenecks(metrics)
        assert len(result) >= 1
        assert result[0]["agent"] == "Agent 1"
        assert result[0]["severity"] == "critical"

    def test_stale_agent(self):
        metrics = {
            "Agent 1": {"cards_in_progress": 1, "blocker_rate": 0.0, "max_stale_hours": 48,
                        "cards_ready": 0, "total_wait_hours": 0},
            "Agent 2": {"cards_in_progress": 1, "blocker_rate": 0.0, "max_stale_hours": 1,
                        "cards_ready": 0, "total_wait_hours": 0},
        }
        result = detect_bottlenecks(metrics)
        assert len(result) >= 1

    def test_wip_limit_exceeded(self):
        metrics = {
            "Agent 1": {"cards_in_progress": 8, "blocker_rate": 0.0, "max_stale_hours": 1,
                        "cards_ready": 0, "total_wait_hours": 0},
            "Agent 2": {"cards_in_progress": 1, "blocker_rate": 0.0, "max_stale_hours": 1,
                        "cards_ready": 0, "total_wait_hours": 0},
        }
        result = detect_bottlenecks(metrics)
        agents = [r["agent"] for r in result]
        assert "Agent 1" in agents

    def test_queue_backup(self):
        metrics = {
            "Agent 1": {"cards_in_progress": 1, "blocker_rate": 0.0, "max_stale_hours": 1,
                        "cards_ready": 10, "total_wait_hours": 20.0},
            "Agent 2": {"cards_in_progress": 1, "blocker_rate": 0.0, "max_stale_hours": 1,
                        "cards_ready": 0, "total_wait_hours": 0},
        }
        result = detect_bottlenecks(metrics)
        agents = [r["agent"] for r in result]
        assert "Agent 1" in agents


class TestFormatAlert:
    def test_no_bottlenecks(self):
        report = format_alert([], {"Agent 1": {"cards_in_progress": 0, "cards_ready": 0,
                                                     "cards_done": 0, "cards_blocked": 0,
                                                     "blocker_rate": 0.0, "max_stale_hours": 0}})
        assert "No bottlenecks" in report

    def test_with_bottlenecks(self):
        bottlenecks = [{"agent": "Agent 1", "severity": "critical",
                        "reasons": ["Overloaded: 10 in-progress"], "metrics": {},
                        "detected_at": "2026-05-19T20:00:00Z"}]
        report = format_alert(bottlenecks, {"Agent 1": {"cards_in_progress": 10,
                                                         "cards_ready": 0, "cards_done": 0,
                                                         "cards_blocked": 0,
                                                         "blocker_rate": 0.1,
                                                         "max_stale_hours": 1}})
        assert "Agent 1" in report
        assert "critical" in report


class TestRunCheck:
    def test_runs_without_error(self):
        result = run_check()
        assert "bottlenecks" in result
        assert "metrics" in result
        assert "n_cards" in result
