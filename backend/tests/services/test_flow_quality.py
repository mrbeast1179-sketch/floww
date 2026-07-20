"""
backend/tests/services/test_flow_quality.py

Conviction v2 — the quality-over-quantity layer (spec:
docs/superpowers/specs/2026-07-20-flow-quality-conviction-v2-design.md).

Families:
  SPREADS   — vertical + straddle leg pairing, ratio gate, volume floor
  CW SPREAD — Cremers-Weinbaum volume-weighted call-put IV spread
  CLUSTERS  — same-ticker same-bias laddering
  BH-FDR    — Benjamini-Hochberg control on sigma alerts
  PRIME     — the $250k + vol/OI>=5 empirical conviction bracket
  INTEGRATION — eval_institutional caps spread legs, CW/cluster factors count
"""

import pytest

from services.flow_alerts import (
    alert_quality,
    eval_institutional,
    init_flow_alert_tables,
    norm_rows,
    persist_alerts,
    update_moves,
)
from services.flow_quality import (
    bh_fdr,
    cluster_biases,
    cw_iv_spread,
    detect_spreads,
    is_prime,
    sigma_pvalue,
)
from tests.services.test_flow_alerts import _future_exp, _raw


def _rows(*specs):
    return norm_rows([_raw(**s) for s in specs])


# ── SPREADS ─────────────────────────────────────────────────────────

def test_vertical_spread_legs_flagged():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="AMD", occ="O:A1", strike=150.0, exp=exp, vol=5000, oi=800),
        dict(under="AMD", occ="O:A2", strike=155.0, exp=exp, vol=5200, oi=700),
    )
    detect_spreads(rows)
    assert rows[0]["spread_leg"] and rows[1]["spread_leg"]


def test_straddle_legs_flagged_opposite_types_same_strike():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="AMD", occ="O:A1", typ="call", strike=150.0, exp=exp, vol=4000, oi=500, delta=0.5),
        dict(under="AMD", occ="O:A2", typ="put", strike=150.0, exp=exp, vol=4100, oi=600, delta=-0.5),
    )
    detect_spreads(rows)
    assert rows[0]["spread_leg"] and rows[1]["spread_leg"]


def test_mismatched_sizes_not_a_spread():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="AMD", occ="O:A1", strike=150.0, exp=exp, vol=9000, oi=800),
        dict(under="AMD", occ="O:A2", strike=155.0, exp=exp, vol=2000, oi=700),
    )
    detect_spreads(rows)
    assert not rows[0].get("spread_leg") and not rows[1].get("spread_leg")


def test_sub_floor_volume_not_paired():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="AMD", occ="O:A1", strike=150.0, exp=exp, vol=400, oi=100),
        dict(under="AMD", occ="O:A2", strike=155.0, exp=exp, vol=420, oi=100),
    )
    detect_spreads(rows)
    assert not rows[0].get("spread_leg")


def test_different_expiries_not_paired():
    rows = _rows(
        dict(under="AMD", occ="O:A1", strike=150.0, exp=_future_exp(5), vol=5000, oi=800),
        dict(under="AMD", occ="O:A2", strike=155.0, exp=_future_exp(20), vol=5100, oi=700),
    )
    detect_spreads(rows)
    assert not rows[0].get("spread_leg")


# ── CW SPREAD ───────────────────────────────────────────────────────

def test_cw_positive_when_calls_richer_than_puts():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="PLTR", occ="O:C", typ="call", strike=140.0, exp=exp, vol=8000, iv=0.65, delta=0.4),
        dict(under="PLTR", occ="O:P", typ="put", strike=140.0, exp=exp, vol=6000, iv=0.55, delta=-0.4),
    )
    cw = cw_iv_spread(rows)
    assert cw["PLTR"] > 0.05


def test_cw_volume_weighted_across_pairs():
    exp = _future_exp(10)
    rows = _rows(
        # tiny pair, huge positive spread
        dict(under="X", occ="O:C1", typ="call", strike=100.0, exp=exp, vol=100, iv=0.9, delta=0.4),
        dict(under="X", occ="O:P1", typ="put", strike=100.0, exp=exp, vol=100, iv=0.3, delta=-0.4),
        # big pair, small negative spread — should dominate
        dict(under="X", occ="O:C2", typ="call", strike=105.0, exp=exp, vol=50000, iv=0.40, delta=0.4),
        dict(under="X", occ="O:P2", typ="put", strike=105.0, exp=exp, vol=50000, iv=0.45, delta=-0.4),
    )
    cw = cw_iv_spread(rows)
    assert cw["X"] < 0


def test_cw_no_matched_pairs_returns_no_entry():
    rows = _rows(dict(under="Y", occ="O:C", typ="call", strike=100.0, vol=5000))
    assert "Y" not in cw_iv_spread(rows)


# ── CLUSTERS ────────────────────────────────────────────────────────

def test_three_same_bias_contracts_cluster():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="NVDA", occ="O:1", strike=1300.0, exp=exp, vol=30000, oi=2000, delta=0.3),
        dict(under="NVDA", occ="O:2", strike=1320.0, exp=_future_exp(15), vol=25000, oi=1500, delta=0.25),
        dict(under="NVDA", occ="O:3", strike=1350.0, exp=exp, vol=28000, oi=1800, delta=0.2),
    )
    for r in rows:
        r["_score"] = 80
    assert "NVDA" in cluster_biases(rows)
    assert cluster_biases(rows)["NVDA"] == "BULLISH"


def test_two_contracts_do_not_cluster():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="NVDA", occ="O:1", strike=1300.0, exp=exp, vol=30000, oi=2000),
        dict(under="NVDA", occ="O:2", strike=1320.0, exp=exp, vol=25000, oi=1500),
    )
    for r in rows:
        r["_score"] = 80
    assert "NVDA" not in cluster_biases(rows)


def test_low_score_rows_do_not_cluster():
    exp = _future_exp(10)
    rows = _rows(
        dict(under="NVDA", occ="O:1", strike=1300.0, exp=exp, vol=30000, oi=2000),
        dict(under="NVDA", occ="O:2", strike=1320.0, exp=exp, vol=25000, oi=1500),
        dict(under="NVDA", occ="O:3", strike=1350.0, exp=exp, vol=28000, oi=1800),
    )
    for r in rows:
        r["_score"] = 40
    assert "NVDA" not in cluster_biases(rows)


# ── BH-FDR ──────────────────────────────────────────────────────────

def test_sigma_pvalue_monotone():
    assert sigma_pvalue(5.0) < sigma_pvalue(4.0) < sigma_pvalue(3.0)
    assert 0 < sigma_pvalue(4.0) < 1e-3


def test_bh_fdr_null_like_grid_rejects_nothing():
    # Uniform-looking p-values (what a true null cross-section produces) —
    # BH must reject none of them.
    pvals = {f"T{i}": 0.03 + i * 0.048 for i in range(20)}
    assert bh_fdr(pvals, q=0.10) == set()


def test_bh_fdr_one_strong_signal_survives_among_nulls():
    pvals = {f"T{i}": 0.4 for i in range(50)}
    pvals["PLTR"] = sigma_pvalue(6.0)
    assert bh_fdr(pvals, q=0.10) == {"PLTR"}


def test_bh_fdr_empty_input():
    assert bh_fdr({}, q=0.10) == set()


# ── PRIME ───────────────────────────────────────────────────────────

def test_prime_bracket_thresholds():
    assert is_prime({"premium": 300e3, "vol_oi": 6.0})
    assert not is_prime({"premium": 100e3, "vol_oi": 6.0})
    assert not is_prime({"premium": 300e3, "vol_oi": 2.0})
    assert not is_prime({"premium": None, "vol_oi": None})


# ── INTEGRATION ─────────────────────────────────────────────────────

def test_eval_caps_spread_legs_to_bronze_strategy():
    exp = _future_exp(10)
    rows = norm_rows([
        _raw(under="AMD", occ="O:A1", strike=150.0, exp=exp, vol=60000, oi=1500, delta=0.3),
        _raw(under="AMD", occ="O:A2", strike=155.0, exp=exp, vol=62000, oi=1400, delta=0.25),
    ])
    alerts = eval_institutional(rows)
    assert alerts, "spread legs still alert, but demoted"
    for a in alerts:
        if a["rule"] == "SIGMA":
            continue
        assert a["tier"] == "BRONZE"
        assert a["side"] == "STRATEGY" and a["bias"] is None


def test_eval_sigma_respects_fdr_not_raw_cutoff():
    # 30 tickers all at ~3.2 sigma: every one passes the OLD raw >=3 style
    # gate individually, but jointly they are exactly the multiple-testing
    # trap — BH at q=0.10 must NOT pass all of them.
    rows, baselines = [], {}
    for i in range(30):
        t = f"T{i:02d}"
        rows.append(_raw(under=t, occ=f"O:{t}", strike=100.0, vol=18000, oi=17000))
        baselines[t] = {"avg": 10000, "std": 2500, "days": 6}
    normed = norm_rows(rows)
    alerts = eval_institutional(normed, baselines=baselines,
                                opts={"min_score": 101, "whale_premium": 1e12})
    sigma_alerts = [a for a in alerts if a["rule"] == "SIGMA"]
    assert len(sigma_alerts) < 30


def test_eval_cluster_and_cw_lift_tier():
    # Laddered accumulation across DIFFERENT expiries (so no vertical
    # pairing) + a strike-matched put whose IV sits 20 vols under the call
    # (Cremers-Weinbaum bullish confirmation).
    exp = _future_exp(10)
    rows = norm_rows([
        _raw(under="PLTR", occ="O:1", strike=138.0, exp=exp, vol=60000, oi=1500, delta=0.35, iv=0.70),
        _raw(under="PLTR", occ="O:2", strike=142.0, exp=_future_exp(15), vol=55000, oi=1300, delta=0.30, iv=0.70),
        _raw(under="PLTR", occ="O:3", strike=145.0, exp=_future_exp(20), vol=50000, oi=1200, delta=0.25, iv=0.70),
        _raw(under="PLTR", occ="O:P", typ="put", strike=138.0, exp=exp, vol=8000, oi=9000, delta=-0.35, iv=0.50),
    ])
    alerts = eval_institutional(rows)
    top = [a for a in alerts if a["rule"] in ("SCORE", "WHALE")]
    assert top and top[0]["tier"] == "GOLD"
    assert top[0].get("cw_spread") is not None and top[0]["cw_spread"] > 0


def test_eval_stamps_cluster_field_per_ticker():
    # cluster_biases is per-ticker: any PLTR alert fired in the snapshot
    # should carry cluster=True once ≥3 same-bias laddering rows qualify.
    exp = _future_exp(10)
    rows = norm_rows([
        _raw(under="PLTR", occ="O:1", strike=138.0, exp=exp, vol=60000, oi=1500, delta=0.35),
        _raw(under="PLTR", occ="O:2", strike=142.0, exp=_future_exp(15), vol=55000, oi=1300, delta=0.30),
        _raw(under="PLTR", occ="O:3", strike=145.0, exp=_future_exp(20), vol=50000, oi=1200, delta=0.25),
    ])
    for r in rows:
        r["_score"] = 90   # force the SCORE rule above the 85-floor
    alerts = eval_institutional(rows)
    pltr_alerts = [a for a in alerts if a["under"] == "PLTR"]
    assert pltr_alerts, "PLTR should fire"
    assert all(a["cluster"] is True for a in pltr_alerts), \
        "every PLTR alert in a 3-leg laddering snapshot must carry cluster=True"


def test_eval_does_not_stamp_cluster_for_two_legs():
    # Two same-bias qualifying contracts aren't a cluster yet — the
    # frontend chip must NOT light up under that threshold. Use non-matching
    # volumes (60k vs 12k) so detect_spreads leaves both rows as BUY/BULLISH
    # (otherwise the test would pass for the wrong reason — via vertical
    # spread demotion to STRATEGY, never entering cluster_biases).
    exp = _future_exp(10)
    rows = norm_rows([
        _raw(under="PLTR", occ="O:1", strike=138.0, exp=exp, vol=60000, oi=1500, delta=0.35),
        _raw(under="PLTR", occ="O:2", strike=142.0, exp=exp, vol=12000, oi=1300, delta=0.30),
    ])
    for r in rows:
        r["_score"] = 90
    alerts = eval_institutional(rows)
    pltr_alerts = [a for a in alerts if a["under"] == "PLTR"]
    assert pltr_alerts, "PLTR should fire on score"
    assert all(a["cluster"] is False for a in pltr_alerts), \
        "two legs doesn't meet the ≥3 cluster threshold; cluster must stay False"


@pytest.fixture
def fresh_engine():
    import services.duckdb_engine as dbe

    engine = dbe.DuckDBEngine(":memory:")
    yield engine


def test_alert_quality_hit_rate_round_trip(fresh_engine):
    # BULLISH alert at spot 133 → spot moves to 138.2 (+3.9%) = a hit.
    init_flow_alert_tables(fresh_engine)
    rows = norm_rows([_raw(vol=60000, oi=1500, delta=0.25, spot=133.0)])
    persist_alerts(fresh_engine, eval_institutional(rows))
    update_moves(fresh_engine, {"PLTR": 138.2})
    q = alert_quality(fresh_engine, days=3)
    assert q, "quality report has a row"
    row = q[0]
    assert row["n"] == 1 and row["n_measured"] == 1
    assert row["hit_rate"] == pytest.approx(1.0)
    assert row["avg_move_pct"] == pytest.approx(3.9, abs=0.1)
    # v2.3 — wins column is the bit-exact integer count (not float-rounded
    # AVG-derived). The frontend consumer (summarizeQuality) reads it
    # directly when non-null and falls back to Math.round(x.hits) only
    # when the column is absent. Decimal precision at small n is the actual
    # reason to ship this column instead of reconstructing from hit_rate.
    assert row["wins"] == 1
    assert isinstance(row["wins"], int), "backend SUM must produce integer wins, not a float reconstruction"


def test_alert_quality_wins_is_bit_exact_with_mixed_outcomes(fresh_engine):
    # v2.3 close-out: 4 distinct tickers, 1 hits (>=0.5% move in BULLISH
    # direction) and 3 miss. Each ticker has explicit distinct `under` so
    # update_moves can stamp the per-ticker move_pct correctly (under is
    # the join key, NOT occ). wins must equal exactly 1 as a literal
    # integer -- the SUM column is what the frontend's summarizeQuality
    # prefers over the float-round fallback.
    init_flow_alert_tables(fresh_engine)
    rows = norm_rows([
        _raw(under="T_HIT",  occ="O:HIT_1234567",    strike=133.0, vol=60000, oi=1500, delta=0.25, spot=133.0),  # hits (133->138.2 = +3.9%)
        _raw(under="T_MISS", occ="O:MISS_A0123456",  strike=200.0, vol=60000, oi=1500, delta=0.25, spot=200.0),  # miss (200->195 = -2.5%)
        _raw(under="T_MISS2", occ="O:MISS_B0123456", strike=200.0, vol=60000, oi=1500, delta=0.25, spot=200.0),  # miss
        _raw(under="T_MISS3", occ="O:MISS_C0123456", strike=200.0, vol=60000, oi=1500, delta=0.25, spot=200.0),  # miss
    ])
    persist_alerts(fresh_engine, eval_institutional(rows))
    # update_moves keys by `under` (the column in flow_alerts_daily), not by occ.
    update_moves(fresh_engine, {
        "T_HIT":  138.2,   # +3.9% (BULLISH >= 0.5 --> HIT)
        "T_MISS": 195.0,   # -2.5% (BULLISH < 0.5 --> miss)
        "T_MISS2": 195.0,
        "T_MISS3": 195.0,
    })
    q = alert_quality(fresh_engine, days=3)
    assert q, "quality rows emitted"
    total_wins = sum(r["wins"] for r in q)
    total_measured = sum(r["n_measured"] for r in q)
    assert total_measured == 4, "every alert had a measurable move_pct"
    assert total_wins == 1, "exactly one of the four alerts scored a hit"
    assert isinstance(total_wins, int), "wins aggregate must stay integer (no float drift)"
    # Per-row wins are bit-exact integers (CAST AS BIGINT) -- the SUM column
    # the frontend prefers over Math.round(x.hits).
    for r in q:
        assert isinstance(r["wins"], int), f"row wins must be integer, got {type(r['wins'])}"
    # hit_rate averaging matches: 1/4 = 0.25.
    assert pytest.approx(
        sum(r["hit_rate"] * r["n_measured"] for r in q) / total_measured,
        abs=1e-6,
    ) == 0.25


def test_init_flow_alert_tables_migrates_legacy_table_to_v2_3(fresh_engine):
    # v2.3.1 migration canary: pre-create flow_alerts_daily with the v2.2
    # schema (no `wins` column), then call init_flow_alert_tables() and
    # verify the column was added in-place. Without this, the prod upgrade
    # path from v2.2 -> v2.3 silently fails on the first alert_quality()
    # call after deploy (DuckDB error: "column wins does not exist").
    fresh_engine.execute_write("""
        CREATE TABLE flow_alerts_daily (
            asof_date DATE, asof_ts TIMESTAMP, key TEXT, ckey TEXT,
            rule TEXT, tier TEXT, side TEXT, bias TEXT,
            under TEXT, type TEXT, strike DOUBLE, exp TEXT, dte INTEGER,
            score INTEGER, est_entry DOUBLE, premium DOUBLE, notional DOUBLE,
            vol_oi DOUBLE, sigma DOUBLE, oi_chg_pct DOUBLE,
            under_price DOUBLE, last_price DOUBLE, move_pct DOUBLE,
            cw_spread DOUBLE, cluster BOOLEAN, why TEXT,
            PRIMARY KEY (asof_date, key)
        )
    """)
    # Pre-v2.3 prod module wouldn't have a `wins` BIGINT column here.
    init_flow_alert_tables(fresh_engine)
    # Schema probe -- wins column must exist and be queryable.
    cols = fresh_engine.query("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'flow_alerts_daily' AND column_name = 'wins'
    """)
    assert cols, "wins column was not added by init_flow_alert_tables migration"
    data_type = cols[0]["data_type"].upper()
    # Strict equality. DuckDB returns exactly "BIGINT" given the explicit
    # CAST AS BIGINT in alert_quality's SQL. A regression to INTEGER (or any
    # smaller family) would silently pass a looser LIKE check and break
    # JSON number precision on the DuckDB → JS JSON boundary (JS numbers
    # lose precision above 2^53; cumulative tier wins over months can
    # approach that range when a tier has thousands of alerts).
    assert data_type == "BIGINT", \
        f"wins column must be exactly BIGINT (got {data_type})"
    # Round-trip alert_quality() MUST NOT throw "column wins does not exist"
    # on the migrated table -- the canary passes iff the SQL succeeds.
    rows = norm_rows([_raw(under="T_LEGACY", vol=60000, oi=1500, delta=0.25, spot=100.0)])
    persist_alerts(fresh_engine, eval_institutional(rows))
    update_moves(fresh_engine, {"T_LEGACY": 104.0})  # +4% BULLISH hit
    q = alert_quality(fresh_engine, days=3)
    assert q and q[0]["wins"] == 1, "wins column queryable + first row integer 1"


def test_alert_quality_returns_one_row_per_rule_tier_pair(fresh_engine):
    # The aggregation groups by (rule, tier). With two rules firing into
    # different tiers you get exactly as many rows as (rule × tier) seen.
    # This is the invariant the trend sparkline relies on — every window
    # in the batched response shares the same key set.
    init_flow_alert_tables(fresh_engine)
    rows = [
        _raw(under="SPY", occ="O:1", strike=100.0, exp=_future_exp(10), vol=25000, oi=2000, delta=0.4, spot=100.0),
        _raw(under="SPY", occ="O:2", strike=110.0, exp=_future_exp(15), vol=10000, oi=2000, delta=0.4, spot=100.0),
    ]
    persist_alerts(fresh_engine, eval_institutional(norm_rows(rows)))
    update_moves(fresh_engine, {"SPY": 102.0, "_rest_": 102.0})
    q7 = alert_quality(fresh_engine, days=7)
    keys7 = {(r["rule"], r["tier"]) for r in q7}
    # Each call returns the same shape → the trend sparkline helper can
    # index by tier across windows.
    q14 = alert_quality(fresh_engine, days=14)
    keys14 = {(r["rule"], r["tier"]) for r in q14}
    assert keys7 == keys14, "window length must not change the (rule, tier) keyset"


def test_eval_market_wide_volume_day_suppressed_by_median_removal():
    # 30 tickers ALL at ~3.2 sigma simultaneously = a market-wide volume
    # day, not 30 independent institutional footprints. Cross-sectional
    # median removal must suppress essentially all of them.
    rows, baselines = [], {}
    for i in range(30):
        t = f"T{i:02d}"
        rows.append(_raw(under=t, occ=f"O:{t}", strike=100.0, vol=18000, oi=17000))
        baselines[t] = {"avg": 10000, "std": 2500, "days": 6}
    normed = norm_rows(rows)
    alerts = eval_institutional(normed, baselines=baselines,
                                opts={"min_score": 101, "whale_premium": 1e12})
    assert len([a for a in alerts if a["rule"] == "SIGMA"]) == 0
