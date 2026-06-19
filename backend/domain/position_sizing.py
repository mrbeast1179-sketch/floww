"""backend/domain/position_sizing.py — Pure-function primitives for delta-adjusted
max-loss-at-stop position sizing & Kelly criterion sizing.

These are state-less mathematical primitives — they take primitives, return
primitives. They do NOT load configuration, do NOT touch databases, do NOT
log to a global handler. They emit `0` (or `0.0`) silently on invalid inputs
in the same observability convention as ``backend/bs_greeks.py`` (the caller
is responsible for surfacing the zero).

Why a separate ``domain/`` module:
  * ``services/risk/sizer.py`` owns *stateful* policy (trade history, daily
    loss locks, half-Kelly halving). It needs the primitives defined here.
  * The choice of WHICH sizing rule to apply lives in
    ``signal_translator.py`` and ``paper_trading.py`` (the policy layer).
  * Pure math (the sizing formula itself, the Kelly equation) is a domain
    primitive that can be reused in backtests, paper, and live trading.

References
----------
  * Vince, R. (1992). *The Mathematics of Money Management.* Wiley.
    Ch. 4 — Optimal f and Kelly.
  * Tharp, D. (1998). *Trade Your Way to Financial Freedom.* McGraw-Hill.
    Ch. 7 — Position sizing models; derives ``contracts = $risk / (m · Δ · ΔS)``.
  * Kelly, J. L. (1956). "A New Interpretation of Information Rate." Bell
    System Technical Journal 35(4). ``f* = (p·b − q)/b``.
"""

from __future__ import annotations

import math
from typing import Final

# Industry conventions ---------------------------------------------------

OPTION_MULTIPLIER: Final[float] = 100.0  # one equity option contract = 100 shares
STOCK_MULTIPLIER: Final[float] = 1.0

# Numerical guards — values below these treat the input as "absent" so we
# emit a sentinel ``0`` instead of dividing by ~zero or producing Inf.
EPSILON_DELTA: Final[float] = 1e-6
EPSILON_DISTANCE: Final[float] = 1e-9
EPSILON_PROBABILITY: Final[float] = 1e-9


# ----------------------------------------------------------------------- #
# Delta-adjusted max-loss-at-stop sizing                                  #
# ----------------------------------------------------------------------- #


def delta_adjusted_max_loss_size(
    account_equity: float,
    risk_pct: float,
    delta: float,
    entry_spot: float,
    stop_spot: float,
    multiplier: float = OPTION_MULTIPLIER,
) -> int:
    """Number of contracts (floor) whose *expected dollar loss at the stop*
    is bounded by ``account_equity * risk_pct``.

    Model: a single contract has linear exposure
        ``multiplier · |delta| · |spot_move|``
    to a move of the underlying from ``entry_spot`` to ``stop_spot``. Solve
    ``contracts · multiplier · |delta| · |entry − stop| ≤ budget`` for
    ``contracts``. We ``floor`` so the realised loss never exceeds budget.

    Parameters
    ----------
    account_equity : float
        Current account equity in dollars. Must be > 0; <=0 → returns 0.
    risk_pct : float
        Fraction of equity acceptable to lose on a single trade (e.g. 0.02).
        Must be in (0, 1]; out-of-range → returns 0.
    delta : float
        Option delta (or 1.0 for a stock-equivalent position). The sign is
        folded via abs() — a -0.50 put delta sizes identically to +0.50 call.
        ``|delta| < EPSILON_DELTA`` → returns 0.
    entry_spot : float
        Spot price at entry. Must be > 0; <=0 → returns 0.
    stop_spot : float
        Spot price at stop-loss trigger. Must be > 0; <=0 → returns 0.
        ``|entry − stop| < EPSILON_DISTANCE`` → returns 0.
    multiplier : float, default 100
        Contract multiplier. Use 100 for listed equity options, 1 for stocks.

    Returns
    -------
    int
        Integer number of contracts (≥ 0). Returns ``0`` on any invalid input;
        caller is responsible for interpreting ``0`` as "do not trade".

    Examples
    --------
    Stock (delta=1, mult=1), $10k equity, 2% risk, entry=100, stop=98:
        budget=$200; loss-per-share=$2 → contracts = 100.
    ATM call (delta=0.5, mult=100), same equity/risk/spots:
        loss-per-contract=$100 → contracts = 2.
    """
    if account_equity <= 0:
        return 0
    if not 0.0 < risk_pct <= 1.0:
        return 0
    if entry_spot <= 0 or stop_spot <= 0:
        return 0
    abs_delta = abs(delta)
    if abs_delta < EPSILON_DELTA:
        return 0
    distance = abs(entry_spot - stop_spot)
    if distance < EPSILON_DISTANCE:
        return 0
    if multiplier <= 0:
        return 0
    budget = account_equity * risk_pct
    loss_per_contract = multiplier * abs_delta * distance
    return math.floor(budget / loss_per_contract)


def max_loss_at_stop(
    contracts: int,
    delta: float,
    entry_spot: float,
    stop_spot: float,
    multiplier: float = OPTION_MULTIPLIER,
) -> float:
    """Realised dollar loss if the underlying hits the stop.

    This is the round-trip inverse of :func:`delta_adjusted_max_loss_size`:
        ``max_loss_at_stop(N) ≈ N · multiplier · |delta| · |entry − stop|``

    Returns 0.0 on any invalid input. Useful for *post-hoc* trade
    journaling and risk dashboarding.

    Parameters
    ----------
    contracts : int
        Number of contracts (can be 0 or negative — we floor at 0 loss).
    delta : float
        Option delta or 1.0 for stock-equivalent. Sign folded via abs().
    entry_spot, stop_spot : float
        Spot prices at entry and stop trigger.
    multiplier : float, default 100
        Contract multiplier.

    Returns
    -------
    float
        Expected dollar loss at stop, >= 0.0.
    """
    if contracts <= 0:
        return 0.0
    if entry_spot <= 0 or stop_spot <= 0:
        return 0.0
    if multiplier <= 0:
        return 0.0
    return float(contracts) * multiplier * abs(delta) * abs(entry_spot - stop_spot)


# ----------------------------------------------------------------------- #
# Kelly criterion primitives                                              #
# ----------------------------------------------------------------------- #


def kelly_fraction(win_prob: float, payoff_ratio: float) -> float:
    """Full-Kelly fraction ``f* = (p·b − q) / b``.

    Parameters
    ----------
    win_prob : float
        Per-trade win probability in [0, 1]. Outside this range → 0.0.
    payoff_ratio : float
        ``b = avg_win / avg_loss``, must be > 0. <=0 → 0.0.
        With ``b ≤ 0`` the formula is undefined.

    Returns
    -------
    float
        ``f*`` in [0, 1) (we ``max`` against 0 — never bet negative). Returns
        0.0 when win_prob falls below the breakeven threshold
        ``p_breakeven = 1/(b+1)``.

    Notes
    -----
    For ``b = avg_win / avg_loss`` and ``p`` + ``q = 1``, the breakeven
    probability (where Kelly = 0) is ``1/(b+1)``. Below that you have a
    negative edge and the rational bet is zero (refuse the trade). Above
    that, partial-Kelly (¼ or ½) is the practical choice — full Kelly
    is too volatile for real-world use (drawdowns of 30-50% are common).
    """
    if win_prob < EPSILON_PROBABILITY or win_prob > 1.0:
        return 0.0
    if payoff_ratio <= 0:
        return 0.0
    q = 1.0 - win_prob
    f_star = (win_prob * payoff_ratio - q) / payoff_ratio
    return max(f_star, 0.0)


def half_kelly(win_prob: float, payoff_ratio: float) -> float:
    """Half-Kelly — the practical default in floww (``SizerConfig.kelly_fraction=0.5``).

    Half-Kelly sacrifices ~25 % of asymptotic growth for ~50 % reduction in
    drawdown volatility. Recommended for nearly all live workflows.
    """
    return 0.5 * kelly_fraction(win_prob, payoff_ratio)


def quarter_kelly(win_prob: float, payoff_ratio: float) -> float:
    """Quarter-Kelly — conservative sizing for noisy / parameter-uncertain edges."""
    return 0.25 * kelly_fraction(win_prob, payoff_ratio)


def kelly_breakeven_probability(payoff_ratio: float) -> float:
    """The minimum win probability ``p`` for which Kelly fraction > 0.

    Derivation: ``(p·b − q) > 0  ⇔  p > q/b  ⇔  p > (1−p)/b``,
    solving for p: ``p·(b+1) > 1`` ⇒ ``p > 1/(b+1)``.

    Returns 1.0 if ``payoff_ratio`` is non-positive (no edge is achievable).
    """
    if payoff_ratio <= 0:
        return 1.0
    return 1.0 / (payoff_ratio + 1.0)


# ----------------------------------------------------------------------- #
# Convenience aggregator — typical entrypoint from sizing policy          #
# ----------------------------------------------------------------------- #


def size_position_at_stop(
    account_equity: float,
    risk_pct: float,
    delta: float,
    entry_spot: float,
    stop_spot: float,
    multiplier: float = OPTION_MULTIPLIER,
    cap: int | None = None,
) -> dict[str, float | int]:
    """Return a sizing summary dict: ``qty``, ``loss_per_contract``,
    ``max_dollar_loss``.

    Combines :func:`delta_adjusted_max_loss_size` with an optional hard cap
    (``MAX_POSITION_SIZE``-style). The cap is applied *after* the floor so
    the realised loss still respects the budget; the cheaper trade wins.
    """
    qty = delta_adjusted_max_loss_size(
        account_equity, risk_pct, delta, entry_spot, stop_spot, multiplier
    )
    if cap is not None and qty > cap:
        qty = int(cap)
    loss_per_contract = max_loss_at_stop(1, delta, entry_spot, stop_spot, multiplier)
    max_dollar_loss = max_loss_at_stop(qty, delta, entry_spot, stop_spot, multiplier)
    return {
        "qty": int(qty),
        "loss_per_contract": float(loss_per_contract),
        "max_dollar_loss": float(max_dollar_loss),
    }


__all__ = [
    "OPTION_MULTIPLIER",
    "STOCK_MULTIPLIER",
    "delta_adjusted_max_loss_size",
    "max_loss_at_stop",
    "kelly_fraction",
    "half_kelly",
    "quarter_kelly",
    "kelly_breakeven_probability",
    "size_position_at_stop",
]
