"""backend/domain/kelly_replay.py — Pure-function replay math for scaling
backtest P&L under different Kelly sizing policies.

This module is a sibling of ``domain/position_sizing.py``: it consumes the
sizing primitives exposed there (``kelly_fraction``, ``half_kelly``,
``quarter_kelly``, ``kelly_breakeven_probability``) and applies them to
realised P&L records from ``/Users/nav/dvt_backtest_v2.json``.

**Linear-scaling assumption.** Each record's ``total_pnl`` was realised
under fixed ``baseline_pct`` of equity (the current paper_trading.py
default is 2%). Under an alternative uniform sizing ``policy_pct`` we
replay as ``total_pnl * (policy_pct / baseline_pct)`` — i.e. we assume
the same trade magnitudes in the same order, just scaled. This is a
*first-order* approximation: it cannot model compounding/dynamic-sizing
dynamics from a Kelly-sized equity curve (those require trade-by-trade
ordering, not aggregates). Suitable for backtest comparison; **not** a
walk-forward simulation.

**Kelly no-trade filter.** For per-record empirical Kelly sizing we
apply a filter: if a record's empirical win-rate falls below its breakeven
``1/(avg_rr+1)``, the empirical Kelly fraction is 0 and replayed P&L is
forced to ``$0``. Under Kelly-aware discipline that strategy would not
have been traded at all. The raw ``naive 2%`` baseline still applies
the actual realised loss.

Reference: Vince (1992) Optimal f; Tharp (1998) Position Sizing Ch. 7;
Kelly (1956) f* = (p·b − q) / b.
"""

from __future__ import annotations

import statistics
from typing import Final

from domain.position_sizing import (
    half_kelly,
    kelly_breakeven_probability,
    kelly_fraction,
    quarter_kelly,
)

# ----------------------------------------------------------------------- #
# Constants                                                                #
# ----------------------------------------------------------------------- #


# Reference baseline (current paper_trading.py default) and the
# calibration anchor (mirrors kelly_calibration_report.py:3).
NAIVE_BASELINE_PCT: Final[float] = 0.02
ANCHOR_WIN_PROB: Final[float] = 0.55
ANCHOR_PAYOFF: Final[float] = 1.65
DEFAULT_EQUITY: Final[float] = 10_000.0


# ----------------------------------------------------------------------- #
# Policy registry                                                          #
# ----------------------------------------------------------------------- #


def theoretical_policies(baseline_pct: float = NAIVE_BASELINE_PCT) -> dict[str, float]:
    """Registry of theoretical sizing policies to compare.

    Returns a mapping of policy-name to fractional-equity wager for that
    policy. Includes the naive baseline as a key for convenience so the
    caller can iterate a single dict.
    """
    return {
        "naive_2pct": baseline_pct,
        "theoretical_quarter_kelly_p055_b165": quarter_kelly(
            ANCHOR_WIN_PROB, ANCHOR_PAYOFF
        ),
        "theoretical_half_kelly_p055_b165": half_kelly(
            ANCHOR_WIN_PROB, ANCHOR_PAYOFF
        ),
    }


# ----------------------------------------------------------------------- #
# Linear P&L scaling                                                       #
# ----------------------------------------------------------------------- #


def scale_pnl_linear(
    total_pnl: float,
    policy_pct: float,
    baseline_pct: float = NAIVE_BASELINE_PCT,
) -> float:
    """Linear P&L scaling under a uniform alternative sizing policy.

    Returns ``total_pnl * (policy_pct / baseline_pct)``. Identity when
    policy_pct == baseline_pct. If baseline_pct <= 0 (degenerate),
    returns total_pnl unchanged.
    """
    if policy_pct == baseline_pct:
        return total_pnl
    if baseline_pct <= 0:
        return total_pnl
    return total_pnl * (policy_pct / baseline_pct)


# ----------------------------------------------------------------------- #
# Percentile (inline, no numpy)                                            #
# ----------------------------------------------------------------------- #


def percentile(values: list[float], p: float) -> float:
    """Linear interpolation percentile over a finite list.

    ``p=0`` → minimum, ``p=1`` → maximum, ``p=0.5`` → median. Empty
    list returns 0.0 to keep downstream aggregates well-defined.
    """
    if not values:
        return 0.0
    sorted_v = sorted(values)
    if p <= 0:
        return sorted_v[0]
    if p >= 1:
        return sorted_v[-1]
    k = (len(sorted_v) - 1) * p
    lo_i = int(k)
    frac = k - lo_i
    if lo_i + 1 >= len(sorted_v):
        return sorted_v[lo_i]
    return sorted_v[lo_i] + frac * (sorted_v[lo_i + 1] - sorted_v[lo_i])


# ----------------------------------------------------------------------- #
# Per-record replay                                                        #
# ----------------------------------------------------------------------- #


def replay_record(
    record: dict,
    baseline_pct: float = NAIVE_BASELINE_PCT,
) -> dict:
    """Replay a single backtest record under five sizing policies.

    Returns a dict with:
      * Source fields (symbol, strategy, win_rate, avg_rr, trades)
      * Per-policy scaled P&L (under naive + 2 theoretical Kelly anchors)
      * Empirical full/half/quarter-Kelly computed from THIS record's
        win-rate and avg-rr; replayed P&L under empirical half/quarter
        is 0 if the empirical full-Kelly is 0 (no-trade filter).
      * Boolean `empirical_filtered` indicating whether the record's
        empirical win-rate fell below breakeven.
    """
    total_pnl = float(record.get("total_pnl", 0.0))
    win_rate_pct = float(record.get("win_rate", 0.0))
    win_rate = win_rate_pct / 100.0  # JSON win_rate is in [0, 100]
    avg_rr = float(record.get("avg_rr", 0.0))
    symbol = str(record.get("symbol", "?"))
    strategy = str(record.get("name", "?"))
    trades = int(record.get("trades", 0))

    # Theoretical-policy columns. Identity under naive baseline.
    policies = theoretical_policies(baseline_pct)
    pnl_by_policy: dict[str, float] = {}
    for name, policy_pct in policies.items():
        pnl_by_policy[name] = round(
            scale_pnl_linear(total_pnl, policy_pct, baseline_pct), 2
        )

    # Empirical Kelly per record (uses THIS record's win_rate / avg_rr).
    if win_rate > 0 and avg_rr > 0:
        empirical_full = kelly_fraction(win_rate, avg_rr)
    else:
        empirical_full = 0.0
    empirical_half = 0.5 * empirical_full
    empirical_quarter = 0.25 * empirical_full
    breakeven_p = kelly_breakeven_probability(avg_rr) if avg_rr > 0 else 1.0

    if empirical_full == 0.0:
        # No-trade filter — strictly-zero edge only.
        #
        # This branch fires when ``kelly_fraction(win_rate, avg_rr)``
        # returns exactly 0.0, i.e. ``win_rate <= 1/(avg_rr+1)`` — the
        # empirical breakeven. Records in this branch would NOT have
        # been traded at all under Kelly-aware discipline; their
        # empirical half/quarter-Kelly scaled P&L is forced to $0.
        #
        # IMPORTANT corner: a record with ``win_rate = 0.3781`` at
        # ``avg_rr = 1.65`` produces ``f* ≈ 0.0001`` (barely-positive
        # edge). That record is NOT filtered — it falls into the else
        # branch where ``empirical_half = 0.5 * 0.0001 ≈ 0.00005``
        # scales the raw P&L by ~0.005% (essentially zero, but not
        # literally $0). The "no-trade" semantics are reserved for
        # strictly-non-positive edge cases only. Half-Kelly drawdown
        # discipline handles the barely-positive regime.
        empirical_half_pnl = 0.0
        empirical_quarter_pnl = 0.0
    else:
        empirical_half_pnl = round(
            scale_pnl_linear(
                total_pnl, empirical_half, baseline_pct
            ),
            2,
        )
        empirical_quarter_pnl = round(
            scale_pnl_linear(
                total_pnl, empirical_quarter, baseline_pct
            ),
            2,
        )

    return {
        "symbol": symbol,
        "strategy": strategy,
        "win_rate": round(win_rate, 4),
        "avg_rr": round(avg_rr, 4),
        "trades": trades,
        "pnl_naive_2pct": round(total_pnl, 2),
        # `pnl_naive_1pct` lives outside `theoretical_policies()` registry
        # by design: it's a fixed-rate alternative (constant 1% across
        # all records), not an anchor that varies by strategy. Adding it
        # to the registry would conflate two semantic roles (anchor-candidates
        # vs. baseline-candidates) — keep that separation here.
        "pnl_naive_1pct": round(scale_pnl_linear(total_pnl, 0.01, baseline_pct), 2),
        "pnl_theoretical_quarter_kelly": pnl_by_policy[
            "theoretical_quarter_kelly_p055_b165"
        ],
        "pnl_theoretical_half_kelly": pnl_by_policy[
            "theoretical_half_kelly_p055_b165"
        ],
        "pnl_empirical_quarter_kelly": empirical_quarter_pnl,
        "pnl_empirical_half_kelly": empirical_half_pnl,
        "empirical_full_kelly": round(empirical_full, 4),
        "breakeven_probability": round(breakeven_p, 4),
        "empirical_filtered": empirical_full == 0.0,
    }


# ----------------------------------------------------------------------- #
# Aggregate replay over a list of records                                  #
# ----------------------------------------------------------------------- #


POLICY_COLUMNS: Final[tuple[str, ...]] = (
    "pnl_naive_2pct",
    "pnl_naive_1pct",
    "pnl_theoretical_quarter_kelly",
    "pnl_theoretical_half_kelly",
    "pnl_empirical_quarter_kelly",
    "pnl_empirical_half_kelly",
)


def _aggregate_one_policy(pnls: list[float], policy_pct: float) -> dict:
    """Return aggregate metrics for one policy across all records."""
    n = len(pnls)
    if n == 0:
        return {
            "policy_pct": round(policy_pct, 4),
            "n_records": 0,
            "total_pnl": 0.0,
            "mean_pnl_per_record": 0.0,
            "mean_final_equity": 0.0,
            "median_final_equity": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "sharpe_proxy": 0.0,
            "mdd_proxy": 0.0,
        }
    final_eqs = [DEFAULT_EQUITY + p for p in pnls]
    wins = sum(1 for p in pnls if p > 0.0)
    losses = n - wins
    std_pnl = statistics.pstdev(pnls) if n > 1 else 0.0
    sharpe = (sum(pnls) / n) / std_pnl if std_pnl > 0 else 0.0
    return {
        "policy_pct": round(policy_pct, 4),
        "n_records": n,
        "total_pnl": round(sum(pnls), 2),
        "mean_pnl_per_record": round(sum(pnls) / n, 2),
        "mean_final_equity": round(sum(final_eqs) / n, 2),
        "median_final_equity": round(percentile(final_eqs, 0.5), 2),
        "win_count": wins,
        "loss_count": losses,
        "sharpe_proxy": round(sharpe, 4),
        "mdd_proxy": round(max(pnls) - min(pnls), 2),
    }


def replay_all(records: list[dict], baseline_pct: float = NAIVE_BASELINE_PCT) -> dict:
    """Replay a list of records. Returns per-record + per-policy aggregates.

    Output schema::

        {
            "baseline_pct": float,
            "anchor": {win_prob, payoff_ratio},
            "theoretical_policies": {name → pct},
            "per_record": [<replay_record output>, ...],
            "aggregates": {column_name → aggregate_metrics},
            "avoided_loss_count": int,
            "avoided_loss_pnl": float (raw P&L that empirical Kelly
                                       filtered out of the total),
            "capital_risked_proxy": {column_name → total_dollars_risked}
        }
    """
    per_record: list[dict] = []
    avoided_loss_pnl = 0.0
    for r in records:
        rec = replay_record(r, baseline_pct)
        per_record.append(rec)
        # Avoided loss: raw P&L was negative AND Kelly filter skipped this row.
        if rec["empirical_filtered"] and rec["pnl_naive_2pct"] < 0:
            avoided_loss_pnl += rec["pnl_naive_2pct"]

    aggregates: dict[str, dict] = {}
    policies = theoretical_policies(baseline_pct)
    # Build aggregates keyed by the same column names used in per_record.
    column_policy_map = {
        "pnl_naive_2pct": policies["naive_2pct"],
        "pnl_naive_1pct": 0.01,
        "pnl_theoretical_quarter_kelly": policies[
            "theoretical_quarter_kelly_p055_b165"
        ],
        "pnl_theoretical_half_kelly": policies[
            "theoretical_half_kelly_p055_b165"
        ],
        "pnl_empirical_quarter_kelly": None,  # varies per record
        "pnl_empirical_half_kelly": None,
    }
    for col in POLICY_COLUMNS:
        pnls = [rec[col] for rec in per_record]
        # For empirical policies use a representative pct (median over records).
        if col in ("pnl_empirical_quarter_kelly", "pnl_empirical_half_kelly"):                # Per-record pct is fractional Kelly (we're storing dollar
                # P&L by column_name, not the fraction). The fraction is
                # derived directly from `empirical_full_kelly` (always in
                # the per_record dict, even when 0 for filtered rows).
                # quarter = full / 4; half = full / 2.
                unpct = [
                    rec["empirical_full_kelly"] * 0.25
                    if col == "pnl_empirical_quarter_kelly"
                    else rec["empirical_full_kelly"] * 0.5
                    for rec in per_record
                ]
                pct_repr = (
                    percentile(unpct, 0.5) if unpct else 0.0
                )
        else:
            pct_repr = float(column_policy_map[col])
        aggregates[col] = _aggregate_one_policy(pnls, pct_repr)

    avoided_loss_count = sum(
        1 for r in per_record if r["empirical_filtered"]
    )

    # Capital risked proxy: total trades × equity × pct.
    trade_counts = {col: 0 for col in POLICY_COLUMNS}
    for rec in per_record:
        # All columns use the same trade count (sizing doesn't change trade count).
        for col in POLICY_COLUMNS:
            trade_counts[col] += rec["trades"]
    capital_risked: dict[str, float] = {}
    for col in POLICY_COLUMNS:
        pct = aggregates[col]["policy_pct"]
        capital_risked[col] = round(
            trade_counts[col] * DEFAULT_EQUITY * pct, 2
        )

    return {
        "baseline_pct": baseline_pct,
        "anchor": {
            "win_prob": ANCHOR_WIN_PROB,
            "payoff_ratio": ANCHOR_PAYOFF,
        },
        "theoretical_policies": {
            k: round(v, 4) for k, v in policies.items()
        },
        "per_record": per_record,
        "aggregates": aggregates,
        "avoided_loss_count": avoided_loss_count,
        "avoided_loss_pnl": round(avoided_loss_pnl, 2),
        "capital_risked_proxy": capital_risked,
    }


__all__ = [
    "NAIVE_BASELINE_PCT",
    "ANCHOR_WIN_PROB",
    "ANCHOR_PAYOFF",
    "DEFAULT_EQUITY",
    "POLICY_COLUMNS",
    "theoretical_policies",
    "scale_pnl_linear",
    "percentile",
    "replay_record",
    "replay_all",
]
