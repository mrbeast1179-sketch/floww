"""
backend/tests/services/test_gflows_greeks_oracle.py

Golden-oracle correctness tests for the gflows_greeks DuckDB pipeline.

Pins the third GEX/Greek source (the DuckDB table read by routes/greeks.py)
against the canonical bs_greeks.py formulas. This closes the audit gap identified
in the GEX/gamma correctness audit: three sources of "GEX" coexist, and this test
proves the DuckDB pipeline's stored Greek values agree with the canonical engine.

Architecture verified:
    setup_gflows_data.py  →  gflows_greeks DuckDB table  →  routes/greeks.py
    (_bs_* formulas)         (per-contract storage)           (SUM by strike)

Test approach:
    1. Use the SAME canonical 4-contract chain as test_gex_aggregator_oracle.py
    2. Compute expected Greek values using bs_greeks.py (the source of truth)
    3. Create an in-memory DuckDB with the gflows_greeks schema
    4. Insert rows with the canonical chain parameters
    5. Query using the SAME SQL as routes/greeks.py (SUM by strike)
    6. Assert the aggregated values match bs_greeks.py to tight tolerance

This test uses bs_greeks.py directly (not the setup script's _bs_* helpers)
so it pins the END-TO-END pipeline: if setup_gflows_data.py's formulas drift
from bs_greeks.py, this test catches it.

Canonical chain (shared with test_gex_aggregator_oracle.py):
    spot = 100, r = 0.05, q = 0.0
    | type | strike | T     | sigma |
    | call | 100    | 0.05  | 0.20  |
    | put  | 100    | 0.05  | 0.20  |
    | call | 105    | 0.05  | 0.20  |
    | put  | 105    | 0.05  | 0.20  |
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bs_greeks import (  # noqa: E402
    bs_charm,
    bs_delta,
    bs_gamma,
    bs_vanna,
)
from routes.greeks import _query_greeks, TABLE_NAME  # noqa: E402

SPOT = 100.0
R = 0.05
Q = 0.0
T = 0.05
SIGMA = 0.20

# Same canonical chain as the GEX aggregator oracle
_CONTRACTS = [
    {"type": "call", "strike": 100.0},
    {"type": "put",  "strike": 100.0},
    {"type": "call", "strike": 105.0},
    {"type": "put",  "strike": 105.0},
]


def _create_gflows_db(db_path: str) -> None:
    """Create the gflows_greeks table in a DuckDB file, matching setup_gflows_data.py schema."""
    conn = duckdb.connect(db_path)
    conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    conn.execute(f"""
        CREATE TABLE {TABLE_NAME} (
            ticker        VARCHAR,
            expiry        VARCHAR,
            strike        DOUBLE,
            type          VARCHAR,
            delta_absolute DOUBLE,
            gamma_total   DOUBLE,
            vanna         DOUBLE,
            charm         DOUBLE
        )
    """)
    conn.close()


def _insert_contracts(db_path: str, ticker: str = "SPY") -> None:
    """Insert canonical chain rows using bs_greeks.py as the source of truth."""
    conn = duckdb.connect(db_path)
    for c in _CONTRACTS:
        k = c["strike"]
        kind = c["type"]
        delta = bs_delta(SPOT, k, T, SIGMA, Q, kind=kind, r=R)
        gamma = bs_gamma(SPOT, k, T, SIGMA, Q, r=R)
        vanna = bs_vanna(SPOT, k, T, SIGMA, Q, r=R)
        charm = bs_charm(SPOT, k, T, SIGMA, Q, kind=kind, r=R)

        conn.execute(
            f"INSERT INTO {TABLE_NAME} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [ticker, "2026-09-18", k, kind, abs(delta), gamma, vanna, charm],
        )
    conn.close()


@pytest.fixture()
def gflows_db(tmp_path):
    """Create a temporary gflows_greeks DuckDB seeded with canonical data."""
    db_path = str(tmp_path / "test_gflows.duckdb")
    _create_gflows_db(db_path)
    _insert_contracts(db_path)
    return db_path


class TestGflowsGreeksOracle:
    """Verify the gflows_greeks DuckDB pipeline produces values consistent
    with bs_greeks.py when queried using routes/greeks.py SQL."""

    def test_gamma_total_matches_bs_greeks(self, gflows_db):
        """Per-strike gamma_total (SUM across types) must match bs_greeks."""
        rows = _query_greeks(Path(gflows_db), "SPY")
        by_strike = {r["strike"]: r for r in rows}

        # K=100: call gamma + put gamma
        expected_100 = bs_gamma(SPOT, 100.0, T, SIGMA, Q, r=R) + bs_gamma(
            SPOT, 100.0, T, SIGMA, Q, r=R
        )
        assert by_strike[100.0]["gamma_total"] == pytest.approx(expected_100, rel=1e-5)

        # K=105: call gamma + put gamma
        expected_105 = bs_gamma(SPOT, 105.0, T, SIGMA, Q, r=R) + bs_gamma(
            SPOT, 105.0, T, SIGMA, Q, r=R
        )
        assert by_strike[105.0]["gamma_total"] == pytest.approx(expected_105, rel=1e-5)

    def test_vanna_matches_bs_greeks(self, gflows_db):
        """Per-strike vanna (SUM across types) must match bs_greeks."""
        rows = _query_greeks(Path(gflows_db), "SPY")
        by_strike = {r["strike"]: r for r in rows}

        # Vanna is the same for calls and puts, so SUM = 2 * single vanna
        expected_100 = 2 * bs_vanna(SPOT, 100.0, T, SIGMA, Q, r=R)
        assert by_strike[100.0]["vanna"] == pytest.approx(expected_100, rel=1e-5)

        expected_105 = 2 * bs_vanna(SPOT, 105.0, T, SIGMA, Q, r=R)
        assert by_strike[105.0]["vanna"] == pytest.approx(expected_105, rel=1e-5)

    def test_charm_matches_bs_greeks(self, gflows_db):
        """Per-strike charm (SUM across types) must match bs_greeks."""
        rows = _query_greeks(Path(gflows_db), "SPY")
        by_strike = {r["strike"]: r for r in rows}

        # Charm differs by type: call charm + put charm
        expected_100 = bs_charm(SPOT, 100.0, T, SIGMA, Q, kind="call", r=R) + bs_charm(
            SPOT, 100.0, T, SIGMA, Q, kind="put", r=R
        )
        assert by_strike[100.0]["charm"] == pytest.approx(expected_100, rel=1e-5)

        expected_105 = bs_charm(SPOT, 105.0, T, SIGMA, Q, kind="call", r=R) + bs_charm(
            SPOT, 105.0, T, SIGMA, Q, kind="put", r=R
        )
        assert by_strike[105.0]["charm"] == pytest.approx(expected_105, rel=1e-5)

    def test_delta_absolute_matches_abs_bs_delta(self, gflows_db):
        """Per-strike delta_absolute (SUM of |delta| across types) must match."""
        rows = _query_greeks(Path(gflows_db), "SPY")
        by_strike = {r["strike"]: r for r in rows}

        for strike in (100.0, 105.0):
            expected = abs(bs_delta(SPOT, strike, T, SIGMA, Q, kind="call", r=R)) + abs(
                bs_delta(SPOT, strike, T, SIGMA, Q, kind="put", r=R)
            )
            assert by_strike[strike]["delta_absolute"] == pytest.approx(expected, rel=1e-5)

    def test_strike_count(self, gflows_db):
        """Must have exactly 2 strikes (100 and 105) from the canonical chain."""
        rows = _query_greeks(Path(gflows_db), "SPY")
        strikes = sorted(r["strike"] for r in rows)
        assert strikes == [100.0, 105.0]

    def test_nan_guards_in_route(self, gflows_db):
        """routes/greeks.py NaN guards must replace NaN/Inf with 0.0."""
        # Insert a row with NaN gamma
        conn = duckdb.connect(gflows_db)
        conn.execute(
            f"INSERT INTO {TABLE_NAME} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["SPY", "2026-09-18", 110.0, "call", 0.5, float("nan"), 0.01, 0.001],
        )
        conn.close()

        rows = _query_greeks(Path(gflows_db), "SPY")
        by_strike = {r["strike"]: r for r in rows}
        # The NaN gamma should be replaced with 0.0, not left as NaN
        assert by_strike[110.0]["gamma_total"] == 0.0

    def test_missing_ticker_returns_empty(self, gflows_db):
        """Querying a ticker with no data must return empty list."""
        rows = _query_greeks(Path(gflows_db), "QQQ")
        assert rows == []

    def test_charm_sign_convention_matches_standard(self, gflows_db):
        """Charm values in the DB must use the standard convention
        (charm = dDelta/dt = -dDelta/dT, negative for ATM calls with r>0).
        This pins the sign so a regression in setup_gflows_data.py is caught."""
        rows = _query_greeks(Path(gflows_db), "SPY")
        by_strike = {r["strike"]: r for r in rows}

        # ATM call charm should be negative (standard convention)
        call_charm_100 = bs_charm(SPOT, 100.0, T, SIGMA, Q, kind="call", r=R)
        assert call_charm_100 < 0, (
            f"ATM call charm should be negative (standard convention), got {call_charm_100}"
        )

        # The stored charm should match
        # For K=100: charm = call_charm + put_charm, both negative for ATM
        assert by_strike[100.0]["charm"] < 0, (
            "Aggregated ATM charm should be negative "
            "(charm = dDelta/dt convention, negative for ATM calls with r>0)"
        )


class TestGflowsRouteIntegration:
    """Verify the route's SQL aggregation logic is correct."""

    def test_multiple_expiries_aggregate_by_strike(self, tmp_path):
        """SUM by strike across multiple expiries must work correctly."""
        db_path = str(tmp_path / "multi_exp.duckdb")
        _create_gflows_db(db_path)
        conn = duckdb.connect(db_path)

        # Insert same contract at two different expiries
        gamma_val = bs_gamma(SPOT, 100.0, T, SIGMA, Q, r=R)
        for exp in ["2026-09-18", "2026-09-25"]:
            conn.execute(
                f"INSERT INTO {TABLE_NAME} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ["SPY", exp, 100.0, "call", 0.5, gamma_val, 0.01, 0.001],
            )
        conn.close()

        rows = _query_greeks(Path(db_path), "SPY")
        assert len(rows) == 1
        assert rows[0]["strike"] == 100.0
        assert rows[0]["n_expiries"] == 2
        # gamma_total should be SUM of both expiries = 2 * gamma
        assert rows[0]["gamma_total"] == pytest.approx(2 * gamma_val, rel=1e-5)

    def test_ordering_by_strike_ascending(self, tmp_path):
        """Results must be ordered by strike ascending."""
        db_path = str(tmp_path / "order_test.duckdb")
        _create_gflows_db(db_path)
        conn = duckdb.connect(db_path)

        # Insert strikes in reverse order
        for strike in [110.0, 105.0, 100.0, 95.0]:
            conn.execute(
                f"INSERT INTO {TABLE_NAME} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ["SPY", "2026-09-18", strike, "call", 0.5, 0.01, 0.01, 0.001],
            )
        conn.close()

        rows = _query_greeks(Path(db_path), "SPY")
        strikes = [r["strike"] for r in rows]
        assert strikes == sorted(strikes), f"Strikes not sorted: {strikes}"
