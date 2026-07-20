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
