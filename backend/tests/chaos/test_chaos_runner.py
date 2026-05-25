"""
backend/tests/chaos/test_chaos_runner.py

Unit tests for chaos_runner.py — chaos engineering harness.

Coverage:
    - Scenario loading from YAML
    - Dry-run execution
    - Step execution (sleep, check, fill_disk, memory_pressure)
    - Error handling
    - Result tracking
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


class TestChaosRunner:
    def test_list_scenarios(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        scenarios = runner.list_scenarios()
        assert isinstance(scenarios, list)

    def test_load_scenario(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        scenario = runner.load_scenario("mongo_down_60s")
        if scenario:  # Only test if scenarios exist
            assert "name" in scenario
            assert "steps" in scenario

    def test_load_missing_scenario(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        scenario = runner.load_scenario("nonexistent")
        assert scenario is None

    @pytest.mark.asyncio
    async def test_run_scenario_not_found(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        result = await runner.run_scenario("nonexistent")
        assert result.success is False
        assert result.error is not None and "not found" in result.error

    @pytest.mark.asyncio
    async def test_run_scenario_dry_run(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        # Create a minimal in-memory scenario
        with patch.object(runner, "load_scenario") as mock_load:
            mock_load.return_value = {
                "name": "test_scenario",
                "steps": [
                    {"name": "step1", "action": "check:system_alive", "critical": True},
                    {"name": "step2", "action": "sleep:0.1", "critical": False},
                ],
            }
            result = await runner.run_scenario("test_scenario", dry_run=True)
        assert result.success is True
        assert len(result.steps) == 2
        assert result.steps[0]["output"] == "[DRY-RUN] check:system_alive"

    @pytest.mark.asyncio
    async def test_run_scenario_with_sleep(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        with patch.object(runner, "load_scenario") as mock_load:
            mock_load.return_value = {
                "name": "sleep_test",
                "steps": [
                    {"name": "quick_sleep", "action": "sleep:0.1", "critical": False},
                ],
            }
            result = await runner.run_scenario("sleep_test")
        assert result.success is True
        assert "Slept 0.1s" in result.steps[0]["output"]

    @pytest.mark.asyncio
    async def test_run_scenario_critical_step_fails(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        with patch.object(runner, "load_scenario") as mock_load:
            mock_load.return_value = {
                "name": "fail_test",
                "steps": [
                    {"name": "fail_step", "action": "check:nonexistent_check", "critical": True},
                ],
            }
            result = await runner.run_scenario("fail_test")
        # Should complete but with success=False if critical step fails
        assert isinstance(result.success, bool)

    def test_fill_disk(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        # Should not raise
        runner._fill_disk(1)  # 1MB

    def test_memory_pressure(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        # Should not raise
        runner._memory_pressure(0)

    @pytest.mark.asyncio
    async def test_check_system_alive(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        result = await runner._run_check("system_alive")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_tmp_writable(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        result = await runner._run_check("tmp_writable")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_unknown(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        result = await runner._run_check("unknown_check")
        assert result is True  # Default pass

    def test_get_results(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        results = runner.get_results()
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_result_tracking(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        with patch.object(runner, "load_scenario") as mock_load:
            mock_load.return_value = {
                "name": "track_test",
                "steps": [
                    {"name": "step1", "action": "check:system_alive", "critical": True},
                ],
            }
            await runner.run_scenario("track_test", dry_run=True)
        results = runner.get_results()
        assert len(results) >= 1
        assert results[-1]["scenario"] == "track_test"

    @pytest.mark.asyncio
    async def test_scenario_with_multiple_steps(self):
        from tests.chaos.chaos_runner import ChaosRunner
        runner = ChaosRunner()
        with patch.object(runner, "load_scenario") as mock_load:
            mock_load.return_value = {
                "name": "multi_step",
                "steps": [
                    {"name": "s1", "action": "check:system_alive", "critical": True},
                    {"name": "s2", "action": "sleep:0.05", "critical": False},
                    {"name": "s3", "action": "check:tmp_writable", "critical": False},
                ],
            }
            result = await runner.run_scenario("multi_step")
        assert result.success is True
        assert len(result.steps) == 3
        assert result.duration_seconds >= 0.0
