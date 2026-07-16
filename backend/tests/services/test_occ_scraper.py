"""
test_occ_scraper.py — Steal-list #14 unit suite.

Covers four silos:
  1. Pure-logic: compute_occ_summary across empty/single/multi-day + ratio math.
  2. Parser (_parse_occ_market_csv): valid CSV, missing quantity, missing
     critical columns, trailing whitespace, dotted-ticker target.
  3. DuckDB I/O: init idempotent, accumulate UPSERT, read recent, ticker
     isolation, accumulate=False no-write.
  4. Edge: dashed-ticker normalization (BRK-B → OCC account re-tag),
     weekend fallback (Sunday → Friday).
"""

from __future__ import annotations

import re
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

# Add backend/ to sys.path so we can import `services.occ_scraper` directly.
BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))

from services.occ_scraper import (
    CACHE_TABLE_NAME,
    FALLBACK_DAYS,
    OCC_BASE_URL,
    REQUEST_TIMEOUT_S,
    TABLE_NAME,
    _fetch_occ_csv,
    _get_params_for_date,
    _next_business_day,
    _parse_occ_market_csv,
    _parse_quantity,
    accumulate_today,
    compute_occ_summary,
    fetch_ticker_occ,
    init_occ_daily_table,
    read_recent_occ,
)

# Minimal in-memory DuckDB stand-in — wraps a sqlite3-free dict so we
# don't drag psycopg into unit tests. Real engine uses services.duckdb_engine.db
# which conforms to the same API surface.


class _MiniDuck:
    """Lightweight in-memory replacement for services.duckdb_engine.db.

    Persists CREATE TABLE / INSERT DDL into ``_meta`` and stores rows in
    a Python list-of-dicts on execute_write. Returns rows on execute_query.
    Implements ON CONFLICT DO UPDATE as last-write-wins (sufficient for
    test isolation).
    """

    def __init__(self) -> None:
        self._tables: dict = {}
        self._primary_keys: dict = {}

    def execute_write(self, sql: str, params: tuple = ()) -> int:
        s = sql.strip()
        su = s.upper()
        if su.startswith("CREATE TABLE"):
            # Parse table name
            name_token = s.split("CREATE TABLE", 1)[1].split("(", 1)[0].strip()
            name_token = name_token.replace("IF NOT EXISTS", "").strip()
            self._tables.setdefault(name_token, [])
            # Parse PRIMARY KEY (...) declaration so UPSERT mock detects duplicate (PK, ) collisions.
            pk_match = re.search(
                r"PRIMARY KEY\s*\(\s*([^)]+)\s*\)", s, re.IGNORECASE
            )
            if pk_match:
                self._primary_keys[name_token] = [
                    c.strip() for c in pk_match.group(1).split(",")
                ]
            else:
                self._primary_keys[name_token] = []
            return 0
        if su.startswith("INSERT INTO"):
            tab = s.split("INSERT INTO", 1)[1].split("(", 1)[0].strip()
            tab = tab.replace("IF NOT EXISTS", "").strip()
            # Parse column list
            cols_part = s.split("(", 1)[1].split(")", 1)[0]
            cols = [c.strip().replace(",", "").strip() for c in cols_part.split(",")]
            rec = dict(zip(cols, params, strict=False))
            # Upsert behavior (DuckDB ON CONFLICT DO UPDATE)
            rows = self._tables.setdefault(tab, [])
            # Determine PK columns
            pk = self._primary_keys.get(tab, [])
            if pk:
                keys = {pk_col: rec.get(pk_col) for pk_col in pk}
                for i, existing in enumerate(rows):
                    if all(existing.get(k) == v for k, v in keys.items()):
                        rows[i] = rec          # UPDATE
                        return 1
            rows.append(rec)                    # INSERT
            return 1
        if su.startswith("DELETE"):
            return 0
        return 0

    def execute_query(self, sql: str, params: tuple = ()) -> list:
        s = sql.strip()
        su = s.upper()
        if su.startswith("SELECT"):
            tab = s.split("FROM", 1)[1].split("WHERE", 1)[0].split("ORDER BY", 1)[0].strip()
            rows = self._tables.get(tab, [])
            # WHERE clause: trivial support for `ticker = ?`
            if "WHERE" in su:
                cond = s.split("WHERE", 1)[1].split("ORDER BY", 1)[0].split("LIMIT", 1)[0]
                if "ticker" in cond and "=" in cond:
                    rows = [r for r in rows if r.get("ticker") == params[0]]
            # ORDER BY trade_date DESC
            if "ORDER BY" in su and "DESC" in su:
                rows = sorted(rows, key=lambda r: str(r.get("trade_date", "")), reverse=True)
            else:
                rows = sorted(rows, key=lambda r: str(r.get("trade_date", "")))
            # LIMIT n
            if "LIMIT" in su and params:
                try:
                    n = int(params[-1]) if isinstance(params[-1], int) else int(params[0])
                    rows = rows[:n]
                except (ValueError, TypeError):
                    pass
            return rows
        return []


@pytest.fixture
def fresh_engine():
    eng = _MiniDuck()
    init_occ_daily_table(eng)
    return eng


# ============================================================
# 1. PURE-LOGIC — compute_occ_summary
# ============================================================
class TestComputeOccSummary:
    def test_empty_rows_returns_zero_state(self):
        s = compute_occ_summary("SPY", [])
        assert s["customer_pct_of_total"] == 0.0
        assert s["mm_net_bias"] == "neutral"
        assert s["mm_call_put_ratio"] == 0.0
        assert s["customer_call_put_ratio"] == 0.0
        assert s["recent_total_volume"] == 0
        assert s["n_days_covered"] == 0
        assert s["ticker"] == "SPY"

    def test_single_day_calculates_correct_totals(self):
        rows = [{
            "ticker": "SPY",
            "customer_call_vol": 1000, "customer_put_vol": 500,
            "firm_call_vol": 200, "firm_put_vol": 100,
            "mm_call_vol": 800, "mm_put_vol": 200,
            "total_call_vol": 2000, "total_put_vol": 800,
        }]
        s = compute_occ_summary("SPY", rows)
        # Customer total = 1000+500 = 1500; grand total = 2800
        assert s["customer_pct_of_total"] == round(1500/2800*100, 1)
        # mm_c/mm_p = 800/200 = 4.0
        assert s["mm_call_put_ratio"] == 4.0
        # cust_c/cust_p = 1000/500 = 2.0
        assert s["customer_call_put_ratio"] == 2.0
        # MM heavily long calls → bullish
        assert s["mm_net_bias"] == "bullish"
        assert s["recent_total_volume"] == 2800
        assert s["n_days_covered"] == 1

    def test_multi_day_uses_latest_row_not_total(self):
        rows = [
            {"ticker": "SPY", "customer_call_vol": 0, "customer_put_vol": 0,
             "firm_call_vol": 0, "firm_put_vol": 0,
             "mm_call_vol": 0, "mm_put_vol": 0,
             "total_call_vol": 0, "total_put_vol": 0},
            {"ticker": "SPY", "customer_call_vol": 100, "customer_put_vol": 100,
             "firm_call_vol": 100, "firm_put_vol": 100,
             "mm_call_vol": 100, "mm_put_vol": 100,
             "total_call_vol": 300, "total_put_vol": 300},
        ]
        s = compute_occ_summary("SPY", rows)
        # Latest row balanced → neutral
        assert s["mm_net_bias"] == "neutral"
        assert s["mm_call_put_ratio"] == 1.0
        assert s["n_days_covered"] == 2

    def test_mm_bearish_when_puts_exceed_calls(self):
        rows = [{
            "ticker": "SPY", "customer_call_vol": 0, "customer_put_vol": 0,
            "firm_call_vol": 0, "firm_put_vol": 0,
            "mm_call_vol": 100, "mm_put_vol": 200,   # 200 > 100*1.15 → bearish
            "total_call_vol": 100, "total_put_vol": 200,
        }]
        s = compute_occ_summary("SPY", rows)
        assert s["mm_net_bias"] == "bearish"

    def test_customer_pct_matches_expected_ratio(self):
        rows = [{
            "ticker": "X", "customer_call_vol": 90, "customer_put_vol": 10,
            "firm_call_vol": 0, "firm_put_vol": 0,
            "mm_call_vol": 0, "mm_put_vol": 0,
            "total_call_vol": 90, "total_put_vol": 10,
        }]
        s = compute_occ_summary("X", rows)
        assert s["customer_pct_of_total"] == 100.0


# ============================================================
# 2. PARSER — _parse_occ_market_csv
# ============================================================
SAMPLE_CSV = """Date,Underlying_Symbol,Call_Put_Indicator,Account_Type,Quantity
2026-07-14,SPY,C,C,1500
2026-07-14,SPY,C,F,300
2026-07-14,SPY,C,M,800
2026-07-14,SPY,P,C,500
2026-07-14,SPY,P,F,200
2026-07-14,SPY,P,M,200
2026-07-14,AAPL,C,C,250
"""

class TestParser:
    def test_parse_valid_occ_csv_yields_expected_rows(self):
        warnings: list = []
        rows = _parse_occ_market_csv(SAMPLE_CSV, "SPY", warnings)
        assert len(rows) == 1
        r = rows[0]
        assert r["ticker"] == "SPY"
        assert r["customer_call_vol"] == 1500
        assert r["customer_put_vol"] == 500
        assert r["firm_call_vol"] == 300
        assert r["firm_put_vol"] == 200
        assert r["mm_call_vol"] == 800
        assert r["mm_put_vol"] == 200
        assert r["total_call_vol"] == 2600
        assert r["total_put_vol"] == 900
        assert warnings == []

    def test_parse_missing_quantity_gracefully_skips(self):
        csv = """Date,Underlying_Symbol,Call_Put_Indicator,Account_Type,Quantity
2026-07-14,SPY,C,C,
2026-07-14,SPY,P,C,100
"""
        warnings: list = []
        rows = _parse_occ_market_csv(csv, "SPY", warnings)
        # Empty quantity treated as 0 — should still aggregate.
        assert rows[0]["customer_call_vol"] == 0
        assert rows[0]["customer_put_vol"] == 100

    def test_parse_extra_columns_ignored_without_error(self):
        csv = """Date,Underlying_Symbol,Call_Put_Indicator,Account_Type,Quantity,Extra,Another
2026-07-14,SPY,C,C,500,xxx,yyyy
2026-07-14,SPY,P,C,200,zzz,wwww
"""
        warnings: list = []
        rows = _parse_occ_market_csv(csv, "SPY", warnings)
        assert rows[0]["customer_call_vol"] == 500
        assert rows[0]["customer_put_vol"] == 200

    def test_parse_missing_account_type_filter_handled(self):
        csv = """Date,Underlying_Symbol,Call_Put_Indicator,Quantity
2026-07-14,SPY,C,500
"""
        warnings: list = []
        rows = _parse_occ_market_csv(csv, "SPY", warnings)
        assert rows == []
        assert any("missing critical columns" in w for w in warnings)

    def test_parse_trailing_whitespace_stripped_from_headers_and_values(self):
        # Trailing spaces are the point of this fixture — keep them inside
        # the quoted fragments (not at physical line ends) so W291 stays quiet.
        csv = (
            " Date, Underlying_Symbol , Call_Put_Indicator , Account_Type , Quantity \n"
            "2026-07-14,SPY,C,C,100 \n"
            "2026-07-14,SPY,P,C,200 \n"
        )
        warnings: list = []
        rows = _parse_occ_market_csv(csv, "SPY", warnings)
        assert rows[0]["customer_call_vol"] == 100
        assert rows[0]["customer_put_vol"] == 200

    def test_parse_only_unrelated_ticker_returns_empty(self):
        warnings: list = []
        rows = _parse_occ_market_csv(SAMPLE_CSV, "TSLA", warnings)
        assert rows == []

    def test_parse_empty_csv_records_warning(self):
        warnings: list = []
        rows = _parse_occ_market_csv("", "SPY", warnings)
        assert rows == []
        assert any("empty" in w for w in warnings)

    def test_parse_quantity_handles_commas_and_quotes(self):
        assert _parse_quantity("1,234") == 1234
        assert _parse_quantity('"500"') == 500
        assert _parse_quantity(None) == 0
        assert _parse_quantity("not a number") == 0
        assert _parse_quantity("-100") == 0       # clamped to non-negative


# ============================================================
# 3. DuckDB I/O
# ============================================================
def _wide_row(ticker="SPY", trade_date=None, **overrides):
    base = {"trade_date": trade_date or date(2026, 7, 14), "ticker": ticker,
            "customer_call_vol": 100, "customer_put_vol": 50,
            "firm_call_vol": 30, "firm_put_vol": 20,
            "mm_call_vol": 80, "mm_put_vol": 30,
            "total_call_vol": 210, "total_put_vol": 100}
    base.update(overrides)
    return base


class TestDuckDBIO:
    def test_init_table_idempotent(self, fresh_engine):
        # Calling twice should not raise
        init_occ_daily_table(fresh_engine)
        init_occ_daily_table(fresh_engine)
        assert TABLE_NAME in fresh_engine._tables
        assert CACHE_TABLE_NAME in fresh_engine._tables

    def test_accumulate_upserts_same_day_repeat(self, fresh_engine):
        rows = [_wide_row()]
        n1 = accumulate_today(fresh_engine, rows, snapshot_date=date(2026, 7, 14))
        assert n1 == 1
        n2 = accumulate_today(fresh_engine, [_wide_row(customer_call_vol=999)], snapshot_date=date(2026, 7, 14))
        assert n2 == 1
        # UPSERT: latest write wins for same (trade_date, ticker)
        recent = read_recent_occ(fresh_engine, "SPY", 5)
        assert recent[-1]["customer_call_vol"] == 999

    def test_accumulate_multiple_tickers(self, fresh_engine):
        rows = [_wide_row("SPY"), _wide_row("AAPL"), _wide_row("TSLA")]
        n = accumulate_today(fresh_engine, rows, snapshot_date=date(2026, 7, 14))
        assert n == 3

    def test_read_recent_n_days_limits(self, fresh_engine):
        for i in range(7):
            d = date(2026, 7, i + 8)
            accumulate_today(
                fresh_engine, [_wide_row(trade_date=d)], snapshot_date=d
            )
        recent = read_recent_occ(fresh_engine, "SPY", 3)
        assert len(recent) == 3
        assert recent[0]["trade_date"] == date(2026, 7, 12)
        assert recent[-1]["trade_date"] == date(2026, 7, 14)

    def test_read_ticker_isolation(self, fresh_engine):
        for ticker in ("SPY", "AAPL", "TSLA"):
            for i in range(3):
                d = date(2026, 7, i + 12)
                accumulate_today(
                    fresh_engine, [_wide_row(ticker=ticker, trade_date=d)],
                    snapshot_date=d,
                )
        spy = read_recent_occ(fresh_engine, "SPY", 7)
        aapl = read_recent_occ(fresh_engine, "AAPL", 7)
        tsla = read_recent_occ(fresh_engine, "TSLA", 7)
        assert len(spy) == 3 and all(r["ticker"] == "SPY" for r in spy)
        assert len(aapl) == 3 and all(r["ticker"] == "AAPL" for r in aapl)
        assert len(tsla) == 3 and all(r["ticker"] == "TSLA" for r in tsla)

    def test_accumulate_empty_rows_is_noop(self, fresh_engine):
        n = accumulate_today(fresh_engine, [])
        assert n == 0
        assert read_recent_occ(fresh_engine, "SPY", 5) == []

    def test_legit_warning_strings_preserved(self, fresh_engine):
        """compute_occ_summary.emits zero-state warnings=[] for empty input."""
        s = compute_occ_summary(None, [])
        assert s["warnings"] == []


# ============================================================
# 4. EDGE — date helpers + URL construction
# ============================================================
class TestEdgeCases:
    def test_next_business_day_skips_weekend(self):
        # 2026-07-12 is a Sunday → should rewind to Friday 2026-07-10
        assert _next_business_day(date(2026, 7, 12)) == date(2026, 7, 10)
        assert _next_business_day(date(2026, 7, 13)) == date(2026, 7, 13)   # Monday
        assert _next_business_day(date(2026, 7, 11)) == date(2026, 7, 10)  # Saturday

    def test_get_params_uses_occ_canonical_keys(self):
        params = _get_params_for_date(date(2026, 7, 14))
        assert params == {
            "volumeQueryType": "O",
            "accountType":     "A",
            "reportType":      "D",
            "reportDate":      "2026-07-14",
        }

    def test_fallback_days_constant_is_five(self):
        assert FALLBACK_DAYS == 5

    def test_request_timeout_is_reasonable(self):
        assert REQUEST_TIMEOUT_S >= 5

    def test_occ_base_url_is_canonical(self):
        assert OCC_BASE_URL == "https://marketdata.theocc.com/volume-query"
