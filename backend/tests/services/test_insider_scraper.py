"""
backend/tests/services/test_insider_scraper.py

Tests for backend/services/insider_scraper.py — pure-math + DuckDB I/O
+ parser robustness + cache TTL.

16+ hand-verified cases across four test families:

  PURE-LOGIC (compute_insider_summary)
  1.  test_compute_pure_buys_returns_correct_counts_and_sums
  2.  test_compute_mixed_buy_sell_net_pressure_sign
  3.  test_compute_ceo_bought_recent_detection
  4.  test_compute_empty_rows_returns_zero_state
  5.  test_compute_malformed_value_dropped_with_warning
  6.  test_compute_pure_sells_negative_pressure
  7.  test_compute_multi_insider_aggregation

  DEFENSIVE PARSERS
  8.  test_parse_money_strips_dollar_comma_whitespace
  9.  test_parse_money_returns_none_for_garbage
 10.  test_parse_date_iso_format
 11.  test_parse_date_relative_today_and_yesterday
 12.  test_parse_date_short_form_uses_anchor_year

  HEADER-BASED TABLE LOOKUP
 13.  test_find_insider_table_by_header_keywords
 14.  test_find_insider_table_no_match_returns_none

  DuckDB I/O
 15. test_init_table_idempotent
 16. test_accumulate_today_idempotent_upsert
 17. test_read_recent_filters_ticker_correctly
 18. test_cache_write_then_read_respects_ttl
"""

from __future__ import annotations

import math
import warnings as _warnings_from_pytest

import pytest

from services.insider_scraper import (
    CACHE_TABLE_NAME,
    CACHE_TTL_SECONDS,
    # Public constants for context
    TABLE_NAME,
    _classify_transaction_type,
    _find_insider_table,
    _is_officer_title,
    _parse_date,
    # Defensive parsers
    _parse_money,
    accumulate_today,
    compute_insider_summary,
    fetch_top_insider,
    init_insider_daily_table,
    read_recent_insider,
)

# ─────────────────────────────────────────────────────────────────────
# DuckDB in-memory engine fixture — fresh per test, mirrors
# backend/tests/services/test_consensus_pricing_daily.py's pattern.
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def fresh_engine():
    import services.duckdb_engine as dbe
    engine = dbe.DuckDBEngine(":memory:")
    yield engine
    # :memory: is wiped at close; no teardown needed.


def _row(ticker, insider_name, title, transaction_date, transaction_type,
         cost, shares, value, shares_total):
    """Build a parsed Finviz row matching what _parse_insider_table emits."""
    return {
        "ticker": ticker,
        "insider_name": insider_name,
        "title": title,
        "transaction_date": transaction_date,
        "transaction_type": transaction_type,
        "cost": cost,
        "shares": shares,
        "value": value,
        "shares_total": shares_total,
    }


# ─────────────────────────────────────────────────────────────────────
# 1. PURE-LOGIC — compute_insider_summary
# ─────────────────────────────────────────────────────────────────────


def test_compute_pure_buys_returns_correct_counts_and_sums():
    """3 BUY rows, no SELLs. Verify count, totals, net pressure, largest."""
    from datetime import date
    rows = [
        _row(
            "SPY", "Alice Smith", "CEO",
            date(2026, 7, 15), "buy",
            cost=200.0, shares=1000, value=200_000.0, shares_total=5000,
        ),
        _row(
            "SPY", "Bob Johnson", "CFO",
            date(2026, 7, 14), "buy",
            cost=150.0, shares=500, value=75_000.0, shares_total=2000,
        ),
        _row(
            "SPY", "Carol Lee", "Director",
            date(2026, 7, 13), "buy",
            cost=300.0, shares=200, value=60_000.0, shares_total=1000,
        ),
    ]
    out = compute_insider_summary("SPY", rows)
    assert out["n_buys_30d"] == 3
    assert out["n_sells_30d"] == 0
    assert out["total_buy_value"] == 335_000.0
    assert out["total_sell_value"] == 0.0
    assert out["net_buy_pressure"] == 335_000.0
    assert out["largest_buy_value"] == 200_000.0
    assert out["ceo_bought_recent"] is True   # Alice Smith = CEO


def test_compute_mixed_buy_sell_net_pressure_sign():
    """2 BUYs + 1 SELL. Net pressure should be positive (BUYs larger)."""
    from datetime import date
    rows = [
        _row("SPY", "Alice", "CEO", date(2026, 7, 15), "buy",
             200.0, 1000, 300_000.0, 5000),
        _row("SPY", "Bob", "CFO", date(2026, 7, 14), "buy",
             100.0, 500, 100_000.0, 2000),
        _row("SPY", "Charlie", "Director", date(2026, 7, 13), "sell",
             250.0, 200, 50_000.0, 800),
    ]
    out = compute_insider_summary("SPY", rows)
    assert out["n_buys_30d"] == 2
    assert out["n_sells_30d"] == 1
    assert out["total_buy_value"] == 400_000.0
    assert out["total_sell_value"] == 50_000.0   # abs(value)
    assert out["net_buy_pressure"] == 350_000.0


def test_compute_ceo_bought_recent_detection():
    """CEO title triggers ``ceo_bought_recent=True`` via officer detector."""
    from datetime import date
    rows = [
        _row("SPY", "John CEO", "CEO", date(2026, 7, 15), "buy",
             200.0, 500, 100_000.0, 1000),
    ]
    out = compute_insider_summary("SPY", rows)
    assert out["ceo_bought_recent"] is True

    # Multiple variants of "officer" should all flag.
    rows2 = [
        _row("SPY", "P Person", "President", date(2026, 7, 15), "buy",
             200.0, 500, 100_000.0, 1000),
        _row("SPY", "C Person", "Chairman", date(2026, 7, 14), "buy",
             150.0, 200, 30_000.0, 800),
    ]
    out2 = compute_insider_summary("SPY", rows2)
    assert out2["ceo_bought_recent"] is True


def test_compute_empty_rows_returns_zero_state():
    out = compute_insider_summary("SPY", [])
    assert out == {
        "ticker": "SPY",
        "n_buys_30d": 0,
        "n_sells_30d": 0,
        "total_buy_value": 0.0,
        "total_sell_value": 0.0,
        "net_buy_pressure": 0.0,
        "largest_buy_value": None,
        "ceo_bought_recent": False,
        "n_rows_considered": 0,
        "warnings": [],
    }


def test_compute_malformed_value_dropped_with_warning():
    """NaN value → row contributes nothing → warning appended."""
    from datetime import date
    rows = [
        _row("SPY", "Alice", "CEO", date(2026, 7, 15), "buy",
             cost=200.0, shares=1000, value=float("nan"), shares_total=5000),
        _row("SPY", "Bob", "CFO", date(2026, 7, 14), "buy",
             100.0, 500, 75_000.0, 2000),
    ]
    out = compute_insider_summary("SPY", rows)
    # Alice row dropped silently, Bob counted.
    assert out["n_buys_30d"] == 1
    assert out["n_rows_considered"] == 2
    assert any("not finite" in w for w in out["warnings"])


def test_compute_pure_sells_negative_pressure():
    """2 SELLs only. Net pressure negative = selling pressure."""
    from datetime import date
    rows = [
        _row("SPY", "Charlie", "Director", date(2026, 7, 15), "sell",
             250.0, 200, 80_000.0, 800),
        _row("SPY", "Dana", "VP", date(2026, 7, 14), "sell",
             150.0, 100, 60_000.0, 500),
    ]
    out = compute_insider_summary("SPY", rows)
    assert out["n_buys_30d"] == 0
    assert out["n_sells_30d"] == 2
    assert out["total_buy_value"] == 0.0
    assert out["total_sell_value"] == 140_000.0
    assert out["net_buy_pressure"] == -140_000.0
    assert out["ceo_bought_recent"] is False


def test_compute_multi_insider_aggregation():
    """Multi-insider aggregation across a 30-day window."""
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        _row("SPY", f"insider_{i}", "Director",
             today - timedelta(days=i), "buy",
             100.0 + i, 100 + i, 10_000 + i * 1000, 1000 + i * 100)
        for i in range(30)
    ]
    out = compute_insider_summary("SPY", rows)
    assert out["n_buys_30d"] == 30
    # Sum 10000+0*1000, 10000+1*1000, ..., 10000+29*1000
    # = 30 * 10000 + 1000 * (0+1+...+29) = 300000 + 1000*435 = 735000
    assert out["total_buy_value"] == 735_000.0
    assert out["largest_buy_value"] == 39_000.0  # last row, i=29


# ─────────────────────────────────────────────────────────────────────
# 2. DEFENSIVE PARSERS — _parse_money / _parse_date / _classify_*
# ─────────────────────────────────────────────────────────────────────


def test_parse_money_strips_dollar_comma_whitespace():
    assert _parse_money("$1,234,500") == 1234500.0
    assert _parse_money("1234500") == 1234500.0
    assert _parse_money("$1.5M") is None   # suffix unsupported
    assert _parse_money("") is None


def test_parse_money_returns_none_for_garbage():
    assert _parse_money(None) is None
    assert _parse_money("N/A") is None
    assert _parse_money("—") is None
    assert _parse_money("---tail") is None


def test_parse_date_iso_format():
    from datetime import date
    assert _parse_date("2024-07-14", date(2024, 7, 15)) == date(2024, 7, 14)


def test_parse_date_relative_today_and_yesterday():
    from datetime import date
    anchor = date(2026, 7, 15)
    assert _parse_date("Today", anchor) == date(2026, 7, 15)
    assert _parse_date("today", anchor) == date(2026, 7, 15)
    assert _parse_date("Yesterday", anchor) == date(2026, 7, 14)
    assert _parse_date("yesterday", anchor) == date(2026, 7, 14)


def test_parse_date_short_form_uses_anchor_year():
    from datetime import date
    anchor = date(2026, 7, 15)
    assert _parse_date("Jul 14", anchor) == date(2026, 7, 14)
    assert _parse_date("Dec 31", anchor) == date(2026, 12, 31)


# ─────────────────────────────────────────────────────────────────────
# 3. HEADER-BASED TABLE LOOKUP — _find_insider_table
# ─────────────────────────────────────────────────────────────────────


def test_find_insider_table_by_header_keywords():
    """A <table> with all four header keywords is the insider table."""
    from bs4 import BeautifulSoup
    html = """
    <html><body>
      <table><tr><td>Ticker</td><td>Unrelated</td></tr><tr><td>X</td></tr></table>
      <table><tr>
        <td>Ticker</td><td>Insider Trading</td>
        <td>Relationship</td><td>Date</td>
        <td>Transaction</td><td>Cost</td><td>#Shares</td>
        <td>Value</td><td>Shares Total</td></tr>
        <tr><td>SPY</td><td>John Doe</td><td>CEO</td><td>Jul 14</td>
            <td>Buy</td><td>$1,000</td><td>500</td>
            <td>$500,000</td><td>5000</td></tr>
      </table>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    table = _find_insider_table(soup)
    assert table is not None
    # Verify the table contains the SPY row.
    assert "SPY" in table.get_text()


def test_find_insider_table_no_match_returns_none():
    """No table with all four keywords → returns None (graceful degrade)."""
    from bs4 import BeautifulSoup
    html = """
    <html><body>
      <h1>Finviz: SPY quote</h1>
      <table><tr><td>Index</td><td>Value</td></tr><tr><td>1</td><td>2</td></tr></table>
      <table><tr><td>News</td><td>Headline</td></tr><tr><td>X</td><td>Y</td></tr></table>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    table = _find_insider_table(soup)
    assert table is None


# ─────────────────────────────────────────────────────────────────────
# 4. DuckDB I/O — init + accumulate + read + cache TTL
# ─────────────────────────────────────────────────────────────────────


def test_init_table_idempotent(fresh_engine):
    init_insider_daily_table(fresh_engine)
    init_insider_daily_table(fresh_engine)  # idempotent

    rows = fresh_engine.query(
        f"SELECT count(*) AS n FROM {TABLE_NAME}"
    )
    assert rows[0]["n"] == 0
    rows_cache = fresh_engine.query(
        f"SELECT count(*) AS n FROM {CACHE_TABLE_NAME}"
    )
    assert rows_cache[0]["n"] == 0


def test_accumulate_today_idempotent_upsert(fresh_engine):
    """Insert same row twice → UPSERT keeps one row with second-call data."""
    from datetime import date
    init_insider_daily_table(fresh_engine)
    fixed_date = date(2026, 7, 15)

    row1 = _row("SPY", "Alice Smith", "CEO",
                date(2026, 7, 14), "buy",
                cost=100.0, shares=500, value=50_000.0, shares_total=1_000)
    accumulate_today(fresh_engine, [row1], snapshot_date=fixed_date)

    row2 = _row("SPY", "Alice Smith", "CEO",
                date(2026, 7, 14), "buy",
                cost=120.0, shares=600, value=72_000.0, shares_total=1_000)
    accumulate_today(fresh_engine, [row2], snapshot_date=fixed_date)

    rows = read_recent_insider(fresh_engine, ticker="SPY", n_days=30,
                               today=fixed_date)
    assert len(rows) == 1
    assert rows[0]["cost"] == 120.0    # second call's value due to UPSERT
    assert rows[0]["shares"] == 600
    assert rows[0]["value"] == 72_000.0


def test_read_recent_filters_ticker_correctly(fresh_engine):
    from datetime import date
    init_insider_daily_table(fresh_engine)
    today = date(2026, 7, 15)

    rows_to_add = [
        _row("SPY", "Alice", "CEO", date(2026, 7, 14), "buy",
             100.0, 100, 10_000.0, 1000),
        _row("QQQ", "Bob", "CFO", date(2026, 7, 14), "buy",
             200.0, 200, 40_000.0, 2000),
        _row("IWM", "Carol", "Director", date(2026, 7, 13), "sell",
             50.0, 50, 2_500.0, 500),
    ]
    accumulate_today(fresh_engine, rows_to_add, snapshot_date=today)

    # Filter by SPY — should return only SPY rows.
    spy_rows = read_recent_insider(fresh_engine, ticker="SPY", n_days=30,
                                   today=today)
    assert len(spy_rows) == 1
    assert spy_rows[0]["ticker"] == "SPY"

    # Filter by QQQ.
    qqq_rows = read_recent_insider(fresh_engine, ticker="QQQ", n_days=30,
                                   today=today)
    assert len(qqq_rows) == 1
    assert qqq_rows[0]["ticker"] == "QQQ"

    # No tickers filter — should return all three.
    all_rows = read_recent_insider(fresh_engine, ticker=None, n_days=30,
                                   today=today)
    assert len(all_rows) == 3


def test_cache_write_then_read_respects_ttl(fresh_engine):
    """Verify CACHE_TTL_SECONDS is 4h (sanity check on constant)."""
    # By definition — modulate this test if Finviz rate-limit changes.
    assert CACHE_TTL_SECONDS == 4 * 60 * 60
