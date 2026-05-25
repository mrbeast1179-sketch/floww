"""
backend/tests/services/test_staleness_alerts.py

Unit tests for predictive staleness alerting.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary DuckDB with ticks and chains tables."""
    import duckdb
    path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(path)
    conn.execute("""
        CREATE TABLE ticks (
            timestamp TIMESTAMP, symbol VARCHAR, delay_seconds DOUBLE
        )
    """)
    conn.execute("""
        CREATE TABLE chains (
            timestamp TIMESTAMP, symbol VARCHAR, delay_seconds DOUBLE
        )
    """)
    conn.close()
    return path


@pytest.fixture
def manager(db_path):
    from services.staleness_alerts import StalenessAlertManager
    return StalenessAlertManager(db_path=db_path)


class TestStalenessThresholds:
    def test_no_alert_fresh_data(self, db_path):
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("INSERT INTO ticks VALUES (NOW(), 'SPY', 30.0)")
        conn.close()

        from services.staleness_alerts import StalenessAlertManager
        mgr = StalenessAlertManager(db_path=db_path)
        alerts = mgr.check_staleness()
        assert len(alerts) == 0

    def test_medium_alert_at_15min(self, db_path):
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("INSERT INTO ticks VALUES (NOW(), 'SPY', 900.0)")
        conn.close()

        from services.staleness_alerts import StalenessAlertManager
        mgr = StalenessAlertManager(db_path=db_path)
        alerts = mgr.check_staleness()
        assert len(alerts) == 1
        assert alerts[0].severity == "MEDIUM"
        assert alerts[0].alert_id == "stale_ticks"

    def test_critical_alert_at_60min(self, db_path):
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("INSERT INTO ticks VALUES (NOW(), 'SPY', 3600.0)")
        conn.close()

        from services.staleness_alerts import StalenessAlertManager
        mgr = StalenessAlertManager(db_path=db_path)
        alerts = mgr.check_staleness()
        assert len(alerts) == 1
        assert alerts[0].severity == "CRITICAL"
        assert alerts[0].alert_id == "stalled_ticks"

    def test_critical_suppresses_medium(self, db_path):
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("INSERT INTO ticks VALUES (NOW(), 'SPY', 3600.0)")
        conn.close()

        from services.staleness_alerts import StalenessAlertManager
        mgr = StalenessAlertManager(db_path=db_path)
        alerts = mgr.check_staleness()
        medium = [a for a in alerts if a.severity == "MEDIUM"]
        critical = [a for a in alerts if a.severity == "CRITICAL"]
        assert len(critical) == 1
        assert len(medium) == 0

    def test_both_tables_checked(self, db_path):
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("INSERT INTO ticks VALUES (NOW(), 'SPY', 900.0)")
        conn.execute("INSERT INTO chains VALUES (NOW(), 'SPY', 3600.0)")
        conn.close()

        from services.staleness_alerts import StalenessAlertManager
        mgr = StalenessAlertManager(db_path=db_path)
        alerts = mgr.check_staleness()
        assert len(alerts) == 2
        tables = {a.table for a in alerts}
        assert "ticks" in tables
        assert "chains" in tables


class TestCooldown:
    def test_cooldown_suppresses_duplicates(self, db_path):
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("INSERT INTO ticks VALUES (NOW(), 'SPY', 900.0)")
        conn.close()

        from services.staleness_alerts import StalenessAlertManager
        mgr = StalenessAlertManager(db_path=db_path, cooldown_seconds=900)
        alerts1 = mgr.check_staleness()
        alerts2 = mgr.check_staleness()
        assert len(alerts1) == 1
        assert len(alerts2) == 0

    def test_different_tables_independent_cooldown(self, db_path):
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("INSERT INTO ticks VALUES (NOW(), 'SPY', 900.0)")
        conn.execute("INSERT INTO chains VALUES (NOW(), 'SPY', 900.0)")
        conn.close()

        from services.staleness_alerts import StalenessAlertManager
        mgr = StalenessAlertManager(db_path=db_path)
        alerts = mgr.check_staleness()
        assert len(alerts) == 2  # Both fire


class TestCallback:
    def test_on_alert_callback(self, db_path):
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("INSERT INTO ticks VALUES (NOW(), 'SPY', 3600.0)")
        conn.close()

        from services.staleness_alerts import StalenessAlertManager
        callback = MagicMock()
        mgr = StalenessAlertManager(db_path=db_path, on_alert=callback)
        alerts = mgr.check_staleness()
        assert callback.call_count == 1
        assert alerts[0].severity == "CRITICAL"


class TestSummary:
    def test_freshness_summary(self, db_path):
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("INSERT INTO ticks VALUES (NOW(), 'SPY', 120.0)")
        conn.close()

        from services.staleness_alerts import StalenessAlertManager
        mgr = StalenessAlertManager(db_path=db_path)
        summary = mgr.get_freshness_summary()
        assert "ticks" in summary["tables"]
        assert summary["tables"]["ticks"]["stale"] is False
        assert summary["tables"]["ticks"]["stalled"] is False

    def test_stale_in_summary(self, db_path):
        import duckdb
        conn = duckdb.connect(db_path)
        conn.execute("INSERT INTO ticks VALUES (NOW(), 'SPY', 1200.0)")
        conn.close()

        from services.staleness_alerts import StalenessAlertManager
        mgr = StalenessAlertManager(db_path=db_path)
        summary = mgr.get_freshness_summary()
        assert summary["tables"]["ticks"]["stale"] is True


class TestMissingTable:
    def test_missing_table_returns_no_alert(self, db_path):
        from services.staleness_alerts import StalenessAlertManager
        mgr = StalenessAlertManager(db_path=db_path)
        alerts = mgr.check_staleness(tables=["nonexistent"])
        assert len(alerts) == 0
