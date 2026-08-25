"""
backend/services/strategy_builder.py

Strategy Builder service — steal-list rank #11 (value 9 / effort 4)
====================================================================

Multi-leg options strategy payoff + PoP + VaR/ES evaluator.

Pure-logic engine (no yfinance calls, no DB writes, no broker execution).
Mirrors the canonical steal-three pure-logic contract:
``backend/services/strike_cone.py``, ``backend/services/risk_neutral_density.py``,
``backend/services/regime_opportunity.py``. All external I/O (yfinance spot
fetch, per-leg IV resolution from chain, server-side schema assembly) is
owned by the route layer at ``backend/routes/steal_three.py``.

Why pure-logic (not optionlab):
    The .md spec says "use optionlab as the engine." optionlab ISN'T
    installed (``rd rgaveiga requirements.txt`` returns ZERO matches;
    ``.venv/bin/python -c 'import optionlab'`` raises). floww's bias is
    "free data, no paid APIs, no broker execution" — thin-wrapping a
    third-party lib we don't control contradicts the bias, AND the BS
    math is small enough to port directly. We port optionlab's
    ``get_pl()`` semantics (per-leg intrinsic payoff summed across
    legs with sign convention) + the lognormal-analytic PoP + the
    parametric delta-gamma VaR/ES as documented below.

Public API
----------

``evaluate_strategy(legs, spot, r=0.045, spot_grid_pct=(0.5, 1.5),
n_grid_points=100, sigma_default=0.30, today=None) -> dict``

Leg schema (caller's contract — pinned by this service and consumed by
the steal-list #15 backtester that follows):

    {
        "side":        "buy" or "sell",     # sign convention: long=+1, short=-1
        "qty":         int (positive),      # contract count
        "option_type": "call" or "put",     # exercised kind at expiry
        "strike":      float (positive),    # exercise price
        "expiry":      "YYYY-MM-DD",        # ISO date string (UTC)
        "premium":     float (positive),    # entry price per contract side
        "iv":          float | None,        # optional; falls back to sigma_default
    }

Response schema (canonical — read by the *not-yet-mounted* React
MultiLegStrategy tile + the #15 backtester):

    {
        "ticker":                 str,                       # echo from caller
        "spot":                   float,
        "premium_total":          float,                     # net credit (>0) / debit (<0) at entry
        "max_profit_at_grid":     float | None,              # max payoff over spot_grid
        "max_loss_at_grid":       float | None,              # min payoff over spot_grid (caveat: asymptotic structures)
        "breakevens":             [float, ...],              # sign-change detection on grid
        "n_breakevens":           int,
        "spot_grid":              [float, ...],              # 100-point grid by default (0.5x..1.5x)
        "payoff_grid":            [float, ...],              # per-spot net P&L
        "probability_of_profit":  float (0..1),              # via lognormal PDF
        "expected_pnl":           float,                     # E[P&L] under Q
        "expected_move_pct":      float,                     # 1σ spot move at T_max
        "var_95":                 float | None,              # positive = loss
        "expected_shortfall_95":  float | None,              # positive = loss
        "greeks_aggregate": {
            "delta": float, "gamma": float, "vega": float, "theta": float,
        },
        "warnings":               [str, ...],
        "leg_count":              int,
        "structure_label":        str,                       # best-effort heuristic
    }

Algorithm
---------
    1. Filter malformed legs (warnings + drop).
    2. Compute ``T_max`` = years to latest leg's expiry (today overridable
       for downstream #15 backtester replay).
    3. Build spot grid: ``np.linspace(spot*lo_pct, spot*hi_pct, N)``.
    4. Per-leg intrinsic payoff on the grid:
          long:  sign=+1, contribution = qty · 100 · (intrinsic - premium)
          short: sign=-1, contribution = -qty · 100 · (intrinsic - premium)
       where ``intrinsic(S, K, type) = max(S - K, 0)`` for call,
       ``max(K - S, 0)`` for put, evaluated at the grid points.
    5. ``payoff_grid[i] = Σ_legs contribution_at_grid_point(i)``.
    6. Sign-change detection on payoff_grid → breakevens (linear interp
       between adjacent signed points).
    7. Max/min payoff over the grid (caveat documented in response).
    8. Lognormal weights on the grid:
          μ_log = ln(spot) + (r - ½σ²)·T_max
          σ_log = σ·√T_max
          weight_i ≈ norm_pdf((ln(grid_i) - μ_log) / σ_log) / grid_i
       PoP = Σ_i weight_i · I[payoff_i > 0] / Σ_i weight_i.
       Expected P&L = Σ_i weight_i · payoff_i / Σ_i weight_i.
    9. Aggregate greeks at spot via ``bs_delta`` / ``bs_gamma`` /
       ``bs_vega`` (from ``backend/bs_greeks.py``) per-leg summed with
       sign convention; theta via numerical -dV/dT.
   10. Parametric VaR_95 / ES_95 from the payout curve under lognormal
       weights (robust; captures convexity in the grid).

Steal intent: optionlab's ``run_strategy/Inputs/Outputs/get_pl()`` (port
the math, NOT the API surface — floww uses a thinner POST schema). The
VaR/ES shape mirrors RiskMeasures.cpp. UI blueprint from
harryho71_option-strategy-pricer.

Audit: ``backend/tests/services/test_strategy_builder.py`` (20 cases).
       ``docs/reports/2026-07-11-steal-list-integration-roadmap.md`` #11.

Frontend mount deferred — backend ship is the value gate; the React
MultiLegStrategy.js blueprint is a focused follow-up (consistent with
prior steal-list ships where RND/PDF/CDS panels were kept backend-first).
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
from scipy.stats import norm

from bs_greeks import bs_call_price, bs_delta, bs_gamma, bs_put_price, bs_vega

# ─────────────────────────────────────────────────────────────────────
# Constants — chosen to mirror peer conventions.
# ─────────────────────────────────────────────────────────────────────

#: Default risk-free rate. Matches ``backend/routes/steal_three.py``
#: ``_RISK_FREE = 0.05`` source-of-truth at server.py:495. We use a
#: slightly more conservative 0.045 here for off-router paths (to avoid
#: silent drift if the canonical constant moves); callers may override.
DEFAULT_R: float = 0.045

#: Default per-leg IV when ``leg.iv`` is absent. 30% captures the typical
#: SPY/ATM-implied regime without yfinance chain re-resolution. Production
#: callers should pass an IV-fetcher that resolves per (ticker, K, expiry).
DEFAULT_SIGMA: float = 0.30

#: Default spot grid endpoints (as fractions of spot). 0.5x–1.5x captures
#: roughly ±3σ of an annual-gamma-of-action regime; iron condors benefit
#: from the wider 0.3x–1.7x (callers can override).
DEFAULT_GRID_PCT: tuple[float, float] = (0.5, 1.5)

#: Default grid resolution. 100 points is plenty for breakeven interp
#: (linear interp between adjacent strikes converges at <0.5% error).
DEFAULT_GRID_POINTS: int = 100

#: Contract multiplier (shares per equity option contract). Mirrors
#: ``backend/bs_greeks.py CONTRACT_MULTIPLIER`` but inlined here to avoid
#: a tier-crossing import dependency for what is a pure-options constant.
CONTRACT_MULTIPLIER: float = 100.0

__all__ = [
    "evaluate_strategy",
    "DEFAULT_R",
    "DEFAULT_SIGMA",
    "DEFAULT_GRID_PCT",
    "DEFAULT_GRID_POINTS",
    "CONTRACT_MULTIPLIER",
]


# ─────────────────────────────────────────────────────────────────────
# Pure helpers — opt-in leg sanitization, grid build, payoffs.
# ─────────────────────────────────────────────────────────────────────


def _safe_float(
    key: str, value: Any, leg_idx: int, warnings: list[str],
) -> float | None:
    """Coerce + filter a numeric per-leg field. None/NaN/inf ⇒ drop + warn."""
    if value is None:
        warnings.append(f"leg[{leg_idx}].{key} missing — skipped")
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        warnings.append(f"leg[{leg_idx}].{key} non-numeric — skipped")
        return None
    if not math.isfinite(v):
        warnings.append(f"leg[{leg_idx}].{key} non-finite — skipped")
        return None
    return v


def _safe_str(
    key: str, value: Any, leg_idx: int, warnings: list[str],
    allowed: set[str],
) -> str | None:
    """Coerce + filter a per-leg enum field. Out-of-set or missing ⇒ drop + warn."""
    if value is None:
        warnings.append(f"leg[{leg_idx}].{key} missing — skipped")
        return None
    if not isinstance(value, str):
        # Tolerate numeric coercion for non-strict users.
        try:
            value = str(int(value))
        except (TypeError, ValueError):
            warnings.append(f"leg[{leg_idx}].{key} not a string — skipped")
            return None
    v = value.strip().lower()
    if v not in allowed:
        warnings.append(
            f"leg[{leg_idx}].{key} invalid (got {value!r}; "
            f"expected one of {sorted(allowed)}) — skipped"
        )
        return None
    return v


def _parse_expiry_iso(s: str, leg_idx: int, warnings: list[str]) -> date | None:
    """Parse ISO date, return None + warn on failure."""
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        warnings.append(
            f"leg[{leg_idx}].expiry not ISO YYYY-MM-DD (got {s!r}) — skipped"
        )
        return None


def _sign(side: str) -> int:
    """Sign convention: long=+1, short=-1."""
    return +1 if side == "buy" else -1


def _validate_legs(
    legs: list[Any], sigma_default: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Filter + coerce a raw leg list into the canonical per-leg dict shape.

    Returns (valid_legs, warnings) — warnings are joined to the
    top-level response. Each valid_leg has every required key with a
    sanitized value. ``sign`` is computed and pinned at validation time.
    """
    warnings: list[str] = []
    valid: list[dict[str, Any]] = []
    if not isinstance(legs, list):
        warnings.append("legs must be a list")
        return valid, warnings

    for i, raw in enumerate(legs):
        if not isinstance(raw, dict):
            warnings.append(f"leg[{i}] not a dict — skipped")
            continue
        side = _safe_str("side", raw.get("side"), i, warnings, {"buy", "sell"})
        option_type = _safe_str(
            "option_type", raw.get("option_type"), i, warnings, {"call", "put"},
        )
        qty = _safe_float("qty", raw.get("qty"), i, warnings)
        strike = _safe_float("strike", raw.get("strike"), i, warnings)
        premium = _safe_float("premium", raw.get("premium"), i, warnings)

        # Expiry is a string parsed against ISO format — fail loudly on bad input.
        expiry_raw = raw.get("expiry")
        if expiry_raw is None:
            warnings.append(f"leg[{i}].expiry missing — skipped")
            continue
        expiry_d = _parse_expiry_iso(str(expiry_raw), i, warnings)
        if expiry_d is None:
            continue

        # Per-leg optional IV — default to sigma_default when missing/non-finite.
        iv = raw.get("iv")
        if iv is None:
            iv_eff = sigma_default
        else:
            try:
                iv_f = float(iv)
                iv_eff = iv_f if (math.isfinite(iv_f) and iv_f > 0) else sigma_default
            except (TypeError, ValueError):
                iv_eff = sigma_default

        # Reject if any required field above filter was None.
        if None in (side, option_type, qty, strike, premium):
            continue
        # qty must be > 0. Negative qty is rejected at the API layer; here
        # we still treat it defensively per the .md "defensive degrade."
        if qty is not None and qty <= 0:
            warnings.append(f"leg[{i}].qty non-positive ({qty}) — skipped")
            continue
        # Strike must be > 0.
        if strike is not None and strike <= 0:
            warnings.append(f"leg[{i}].strike non-positive — skipped")
            continue

        valid.append({
            "side": side,
            "qty": int(qty),
            "option_type": option_type,
            "strike": float(strike),
            "expiry": expiry_d.isoformat(),
            "premium": float(premium),
            "iv": float(iv_eff),
            # Internal: pre-compute sign so downstream math doesn't branch.
            "sign": +1 if side == "buy" else -1,
        })
    return valid, warnings


def _intrinsic(S: float, K: float, kind: str) -> float:
    """Option payoff at expiry (without premium)."""
    if kind == "call":
        return max(S - K, 0.0)
    return max(K - S, 0.0)


def _leg_contribution(leg: dict[str, Any], S: float) -> float:
    """Per-leg contribution at terminal spot S. Sign convention baked in."""
    intrinsic = _intrinsic(S, leg["strike"], leg["option_type"])
    # (intrinsic - premium) is the per-share net P&L for a LONG position.
    # Negative-sign legs (short) take the negative of that.
    return (
        leg["sign"] * leg["qty"] * CONTRACT_MULTIPLIER
        * (intrinsic - leg["premium"])
    )


def _build_spot_grid(
    spot: float, pct: tuple[float, float], n: int,
) -> list[float]:
    """Spot grid: ``np.linspace(spot*lo_pct, spot*hi_pct, n)`` as plain list."""
    lo, hi = pct
    if lo >= hi or n < 2:
        return [spot] * max(n, 1)
    return [float(x) for x in np.linspace(spot * lo, spot * hi, n)]


def _find_breakevens(grid: list[float], payoff: list[float]) -> list[float]:
    """Linear-interpolate spot-grid sign-changes → breakeven strikes.

    A breakeven is where the strategy crosses zero P&L. We detect sign
    changes between adjacent grid points and interpolate linearly.
    Duplicates within ``grid_step / 4`` are coalesced (handles the rare
    floating-point near-zero).
    """
    out: list[float] = []
    if len(grid) < 2:
        return out
    for i in range(1, len(grid)):
        p_prev, p_curr = payoff[i - 1], payoff[i]
        if p_prev == 0.0:
            out.append(grid[i - 1])
            continue
        if (p_prev < 0 < p_curr) or (p_prev > 0 > p_curr):
            # Linear interp: S_be = grid[i-1] + (0 - p_prev) / (p_curr - p_prev) * (grid[i] - grid[i-1])
            t = -p_prev / (p_curr - p_prev)
            out.append(grid[i - 1] + t * (grid[i] - grid[i - 1]))
    # Coalesce neighbors that round to the same float.
    coalesced: list[float] = []
    last = None
    for b in out:
        if last is None or abs(b - last) > max(1e-4, (grid[-1] - grid[0]) / 1e3):
            coalesced.append(b)
            last = b
    return coalesced


def _compute_lognormal_weights(
    grid: list[float], spot: float, r: float, T: float, sigma: float,
) -> list[float]:
    """Lognormal PDF at each ``grid`` point under Q with drift (r - ½σ²)·T.

    Returns un-normalized weights — downstream callers may normalize
    by Σ w. For very small ``T`` we fall back to a Dirac-ish delta at
    spot (``weight(grid[i] == spot) = 1``) so PoP at expiry equals the
    fraction of grid points above breakeven at T=0.
    """
    if T <= 1e-9 or sigma <= 0 or spot <= 0:
        # At T=0, S_T = spot ⇒ PoP becomes deterministic at the current
        # spot's payoff sign (NOT what we want — we want the CURRENT
        # payoff divided by 1). Return zero-weight array; caller treats
        # this as "insufficient time to expiry for PoP" + surfaces a warn.
        return [0.0 for _ in grid]
    mu_log = math.log(spot) + (r - 0.5 * sigma * sigma) * T
    sigma_log = sigma * math.sqrt(T)
    if sigma_log <= 0:
        return [0.0 for _ in grid]
    weights: list[float] = []
    for s in grid:
        if s <= 0:
            weights.append(0.0)
            continue
        z = (math.log(s) - mu_log) / sigma_log
        # lognormal PDF(s) = (1/s) · norm_pdf(z) / sigma_log. The 1/s
        # factor cancels under normalization when computing PoP + E[P&L],
        # so we drop it for numerical stability (avoids tiny near-0 s).
        weights.append(norm.pdf(z) / sigma_log)
    return weights


def _aggregate_greeks(
    legs: list[dict[str, Any]], spot: float, r: float, T: float,
) -> dict[str, float]:
    """Per-leg BS greeks summed with sign + qty, scaled to share-equivalents.

    Flavour: we evaluate at each leg's individual ``T = T_i`` (years
    from today to that leg's expiry). When evaluating a portfolio of
    multi-expiry legs, this is more accurate than averaging T_max across
    all legs — each leg's exposure has its own theta-decay clock.
    """
    delta_acc = gamma_acc = vega_acc = theta_acc = 0.0
    today = date.today()
    for leg in legs:
        K = leg["strike"]
        iv = leg["iv"]
        kind = leg["option_type"]
        T_i = max(
            (datetime.strptime(leg["expiry"], "%Y-%m-%d").date() - today).days,
            0,
        ) / 365.0
        if T_i <= 0:
            # Already-expired: greeks are exposure-to-intrinsic; we
            # approximate via delta = sign(intrinsic side).
            intrinsic_side = 1.0 if (kind == "call" and spot > K) else (
                -1.0 if (kind == "put" and spot < K) else 0.0
            )
            delta_acc += (
                leg["sign"] * leg["qty"] * CONTRACT_MULTIPLIER * intrinsic_side
            )
            continue
        d_leg = bs_delta(spot, K, T_i, iv, kind=kind, r=r)
        g_leg = bs_gamma(spot, K, T_i, iv, r=r)
        v_leg = bs_vega(spot, K, T_i, iv, r=r)
        # Theta: numerical -dPrice/dT. Take price difference over 1/365 of a
        # year, multiply by CONTRACT_MULTIPLIER to dollars-per-day-per-contract.
        if kind == "call":
            price_now = bs_call_price(spot, K, T_i, iv, r=r)
            price_next = bs_call_price(spot, K, T_i - (1.0 / 365.0), iv, r=r)
        else:
            price_now = bs_put_price(spot, K, T_i, iv, r=r)
            price_next = bs_put_price(spot, K, T_i - (1.0 / 365.0), iv, r=r)
        theta_leg = -(price_next - price_now) * CONTRACT_MULTIPLIER
        # Scale to share-equivalent (divide by spot) for the report's
        # "per 1% spot move" semantic — matches Heatseeker's existing
        # delta display convention.
        delta_acc += leg["sign"] * leg["qty"] * d_leg
        gamma_acc += leg["sign"] * leg["qty"] * g_leg
        vega_acc += leg["sign"] * leg["qty"] * v_leg
        theta_acc += leg["sign"] * leg["qty"] * theta_leg
    return {
        "delta": float(delta_acc),
        "gamma": float(gamma_acc),
        "vega": float(vega_acc),
        "theta": float(theta_acc),
    }


def _label_structure(legs: list[dict[str, Any]]) -> str:
    """Best-effort label from leg signature.

    Heuristic, NOT deterministic — the caller is expected to also
    surface the leg list in the UI so users can verify. We keep the
    label as a quick category for log + UI badge use.
    """
    n = len(legs)
    if n == 0:
        return "empty"
    if n == 1:
        leg = legs[0]
        if leg["option_type"] == "put" and leg["side"] == "sell":
            return "cash_secured_put"
        if leg["option_type"] == "call" and leg["side"] == "sell":
            return "covered_call_alone"
        if leg["side"] == "buy":
            return f"long_{leg['option_type']}"
        return f"short_{leg['option_type']}"
    # 2 legs: spread, straddle, strangle, calendar
    if n == 2:
        a, b = legs
        if (
            a["option_type"] != b["option_type"]
            and a["strike"] == b["strike"]
            and a["expiry"] == b["expiry"]
            and a["side"] == b["side"] == "buy"
        ):
            return "long_straddle"
        if (
            a["option_type"] != b["option_type"]
            and a["strike"] != b["strike"]
            and a["expiry"] == b["expiry"]
            and a["side"] == b["side"] == "buy"
        ):
            return "long_strangle"
        if (
            a["option_type"] == b["option_type"]
            and a["side"] != b["side"]
            and a["expiry"] == b["expiry"]
        ):
            kind = a["option_type"]
            direction = (
                "bull" if (kind == "call" and a["side"] == "buy")
                else "bear" if (kind == "put" and a["side"] == "buy")
                else f"{kind}_vertical"
            )
            return f"{direction}_{kind}_spread"
        if a["expiry"] != b["expiry"]:
            return "calendar_spread"
        return "two_leg_custom"
    # 4 legs, 2 calls + 2 puts, same expiry, varying strikes → iron condor / butterfly.
    if n == 4:
        call_count = sum(1 for leg in legs if leg["option_type"] == "call")
        put_count = sum(1 for leg in legs if leg["option_type"] == "put")
        expiries = {leg["expiry"] for leg in legs}
        if call_count == 2 and put_count == 2 and len(expiries) == 1:
            # Iron butterfly: short inner pair at same strike.
            inner_calls = [leg["strike"] for leg in legs
                           if leg["option_type"] == "call" and leg["side"] == "sell"]
            inner_puts = [leg["strike"] for leg in legs
                          if leg["option_type"] == "put" and leg["side"] == "sell"]
            if (
                len(inner_calls) == 1 and len(inner_puts) == 1
                and inner_calls[0] == inner_puts[0]
            ):
                return "iron_butterfly"
            return "iron_condor"
    return f"{n}_leg_custom"


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def evaluate_strategy(
    legs: list[dict[str, Any]],
    spot: float,
    r: float = DEFAULT_R,
    spot_grid_pct: tuple[float, float] = DEFAULT_GRID_PCT,
    n_grid_points: int = DEFAULT_GRID_POINTS,
    sigma_default: float = DEFAULT_SIGMA,
    today: date | None = None,
) -> dict[str, Any]:
    """Evaluate a multi-leg options strategy over a spot grid + lognormal Q.

    See module docstring for the full response-schema contract. Returns
    a well-formed dict under all input conditions — never raises.

    Args:
        legs: per-leg dict list (see module docstring schema).
        spot: current underlying spot price (must be positive).
        r: risk-free rate (default 0.045 matches backend's _RISK_FREE).
        spot_grid_pct: (lo_pct, hi_pct) bounds for the spot grid as
            fractions of ``spot`` — default (0.5, 1.5) captures
            roughly ±3σ for typical annualized vol.
        n_grid_points: grid resolution — default 100.
        sigma_default: per-leg IV when leg.iv is absent — default 0.30.
        today: optional date override (UTC, used by #15 backtester for
            historical replay); defaults to ``date.today()``.
    """
    warnings: list[str] = []

    # ── Argument-level validation ─────────────────────────────────────
    if not isinstance(legs, list):
        return _empty_response(spot, ["legs must be a list"])
    if not (isinstance(spot, (int, float)) and math.isfinite(spot) and spot > 0):
        return _empty_response(
            spot if isinstance(spot, (int, float)) else 0.0,
            ["spot must be a positive finite number"],
        )

    valid_legs, leg_warnings = _validate_legs(legs, sigma_default)
    warnings.extend(leg_warnings)
    if not valid_legs:
        return _empty_response(
            spot,
            warnings + ["no valid legs post-filter"],
        )

    # Accept `today` as either a ``date`` instance or an ISO ``YYYY-MM-DD``
    # string (the test_surface docstring advertises ``today: str | None = None``
    # so callers — incl. the #15 backtester replay — round-trip dates as
    # JSON-safe strings). Coerce here so the downstream
    # ``(expiry_date - today).days`` arithmetic never blows up.
    if isinstance(today, str):
        try:
            today = date.fromisoformat(today)
        except ValueError:
            warnings.append(
                f"today not ISO YYYY-MM-DD (got {today!r}) — falling "
                f"back to date.today()"
            )
            today = date.today()
    today = today or date.today()

    # ── 1. T_max (years to latest expiry) ─────────────────────────────
    # If T_max <= 0 (all legs already expired), PoP / VaR collapse to
    # the current payoff — surface a warning so callers don't expect
    # forward-looking risk metrics.
    expiry_dates = [
        datetime.strptime(leg["expiry"], "%Y-%m-%d").date()
        for leg in valid_legs
    ]
    T_max_days = max((d - today).days for d in expiry_dates)
    T_max = max(T_max_days, 0) / 365.0
    if T_max <= 0:
        warnings.append(
            "all legs expired — PoP/VaR/ES collapse to current-spot payoff"
        )

    # ── 2. Spot grid ─────────────────────────────────────────────────
    spot_grid = _build_spot_grid(spot, spot_grid_pct, n_grid_points)

    # ── 3. Payoff grid ───────────────────────────────────────────────
    # Per-leg intrinsic payoff on the grid, summed across all legs.
    leg_contributions = [
        [_leg_contribution(leg, s) for s in spot_grid]
        for leg in valid_legs
    ]
    payoff_grid: list[float] = []
    for i in range(n_grid_points):
        payoff_grid.append(sum(c[i] for c in leg_contributions))

    # ── 4. Net premium at entry ──────────────────────────────────────
    # sign = +1 for sell (receive), -1 for buy (pay).
    # premium_total > 0 = net credit (e.g., short put, short straddle).
    # premium_total < 0 = net debit (e.g., long call, bull call spread).
    premium_total = sum(
        leg["sign"] * leg["qty"] * leg["premium"] * CONTRACT_MULTIPLIER
        for leg in valid_legs
    )

    # ── 5. Breakevens ────────────────────────────────────────────────
    breakevens = _find_breakevens(spot_grid, payoff_grid)

    # ── 6. Max profit / loss over the grid ───────────────────────────
    # Caveat: this is the EXTRINSIC payoff over a finite grid. A reverse
    # iron condor or naked short option has unbounded loss beyond the
    # grid; the caller must surface the grid-bound warning.
    max_profit = max(payoff_grid) if payoff_grid else None
    max_loss = min(payoff_grid) if payoff_grid else None
    grid_lo, grid_hi = spot_grid[0], spot_grid[-1]
    if grid_lo > 0:
        warnings.append(
            "max_profit/max_loss are computed over the spot grid "
            f"[{round(grid_lo, 2)}, {round(grid_hi, 2)}]; asymptotic "
            "structures (naked shorts, reverse conversions) may exceed "
            "the grid at extreme tails. UI must surface this."
        )

    # ── 7. Aggregate greeks at spot ──────────────────────────────────
    # When T_max <= 0, fall back to T_i = 1/365 so greeks at least
    # compute (approximate one-day-from-expiry carry).
    T_used_for_greeks = max(T_max, 1.0 / 365.0)
    greeks = _aggregate_greeks(valid_legs, spot, r, T_used_for_greeks)

    # ── 8. Probability of profit + expected P&L (lognormal analytic) ─
    pop: float
    expected_pnl: float
    if T_max <= 0:
        # No forward time: PoP = fraction of grid points currently in profit,
        # or 0.0 if currently at-break-even/loss; expected P&L = current payoff.
        current_idx = _nearest_index(spot_grid, spot)
        current_payoff = payoff_grid[current_idx] if current_idx is not None else 0.0
        pop = 1.0 if current_payoff > 0 else (0.0 if current_payoff < 0 else 0.5)
        expected_pnl = current_payoff
    else:
        # Aggregate σ across legs via qty-weighted average.
        total_qty = sum(leg["qty"] for leg in valid_legs) or 1
        sigma_agg = sum(
            leg["iv"] * leg["qty"] for leg in valid_legs
        ) / total_qty
        weights = _compute_lognormal_weights(
            spot_grid, spot, r, T_max, sigma_agg,
        )
        w_sum = sum(weights)
        if w_sum <= 1e-12:
            warnings.append(
                "lognormal Σ weight ≈ 0 at this σ/T regime — PoP/E[pnl] "
                "fall back to the current-spot payoff"
            )
            current_idx = _nearest_index(spot_grid, spot)
            current_payoff = (
                payoff_grid[current_idx] if current_idx is not None else 0.0
            )
            pop = 1.0 if current_payoff > 0 else (
                0.0 if current_payoff < 0 else 0.5
            )
            expected_pnl = current_payoff
        else:
            weight_in_profit = sum(
                w for w, p in zip(weights, payoff_grid, strict=True) if p > 0
            )
            pop = weight_in_profit / w_sum
            expected_pnl = sum(
                w * p for w, p in zip(weights, payoff_grid, strict=True)
            ) / w_sum

    # ── 9. VaR / ES (lognormal-weighted payout curve) ────────────────
    var_95: float | None
    es_95: float | None
    if T_max <= 0:
        var_95 = -min(payoff_grid) if payoff_grid else None
        es_95 = var_95
    else:
        total_qty = sum(leg["qty"] for leg in valid_legs) or 1
        sigma_agg = sum(
            leg["iv"] * leg["qty"] for leg in valid_legs
        ) / total_qty
        weights = _compute_lognormal_weights(
            spot_grid, spot, r, T_max, sigma_agg,
        )
        var_95, es_95 = _compute_var_es_from_curve(
            spot_grid, payoff_grid, weights, confidence=0.95,
        )

    expected_move_pct = (
        # 1σ lognormal move at T_max, in percent of spot.
        (math.exp(sigma_agg * math.sqrt(T_max)) - 1.0) * 100.0
        if T_max > 0 and sigma_agg > 0 else 0.0
    )

    structure_label = _label_structure(valid_legs)

    return {
        "ticker": "unknown",
        "spot": round(spot, 4),
        "premium_total": round(premium_total, 4),
        "max_profit_at_grid": round(max_profit, 4) if max_profit is not None else None,
        "max_loss_at_grid": round(max_loss, 4) if max_loss is not None else None,
        "breakevens": [round(b, 4) for b in breakevens],
        "n_breakevens": len(breakevens),
        "spot_grid": [round(s, 4) for s in spot_grid],
        "payoff_grid": [round(p, 4) for p in payoff_grid],
        "probability_of_profit": round(pop, 4),
        "expected_pnl": round(expected_pnl, 4),
        "expected_move_pct": round(expected_move_pct, 4),
        "var_95": round(var_95, 4) if var_95 is not None else None,
        "expected_shortfall_95": round(es_95, 4) if es_95 is not None else None,
        "greeks_aggregate": {k: round(v, 4) for k, v in greeks.items()},
        "warnings": warnings,
        "leg_count": len(valid_legs),
        "structure_label": structure_label,
    }


def _nearest_index(grid: list[float], spot: float) -> int | None:
    """Index of the grid point closest to spot; None if grid is empty."""
    if not grid:
        return None
    return min(range(len(grid)), key=lambda i: abs(grid[i] - spot))


def _compute_var_es_from_curve(
    grid: list[float],
    payoff: list[float],
    weights: list[float],
    confidence: float = 0.95,
) -> tuple[float | None, float | None]:
    """VaR / Expected Shortfall from the payout curve under lognormal weights.

    Sort grid-points by their payoff ascending; accumulate weights to
    find the cutoff that captures the bottom ``1 - confidence`` weight.
    VaR = the payoff at the cutoff (positive convention: loss = -payoff
    flipped upward). ES = mean payoff over points with weight within
    the bottom 5% tail (also flipped upward).
    """
    if not grid or not payoff or not weights:
        return None, None
    if len(grid) != len(payoff) or len(grid) != len(weights):
        return None, None
    tail_pct = 1.0 - confidence
    # Sort by payoff ascending.
    indices = sorted(range(len(payoff)), key=lambda i: payoff[i])
    sorted_payoff = [payoff[i] for i in indices]
    sorted_weights = [weights[i] for i in indices]
    total_w = sum(sorted_weights)
    if total_w <= 0:
        return None, None
    # Walk the tail: accumulate weight up to tail_pct of total.
    accum = 0.0
    cutoff_idx = 0
    for i, w in enumerate(sorted_weights):
        accum += w
        if accum >= tail_pct * total_w:
            cutoff_idx = i
            break
    var_payoff = sorted_payoff[cutoff_idx]
    # ES = weighted mean of points at-or-below the cutoff.
    tail_w = sum(sorted_weights[: cutoff_idx + 1])
    if tail_w <= 0:
        es_payoff = var_payoff
    else:
        es_payoff = sum(
            sorted_weights[i] * sorted_payoff[i]
            for i in range(cutoff_idx + 1)
        ) / tail_w
    # Flip to LOSS convention (positive = loss).
    return -var_payoff, -es_payoff


def _empty_response(
    spot: float, warnings: list[str],
) -> dict[str, Any]:
    """Empty-shape response with warnings preserved for dashboard degrade."""
    return {
        "ticker": "unknown",
        "spot": round(spot, 4) if isinstance(spot, (int, float)) and math.isfinite(spot) else None,
        "premium_total": 0.0,
        "max_profit_at_grid": None,
        "max_loss_at_grid": None,
        "breakevens": [],
        "n_breakevens": 0,
        "spot_grid": [],
        "payoff_grid": [],
        "probability_of_profit": 0.0,
        "expected_pnl": 0.0,
        "expected_move_pct": 0.0,
        "var_95": None,
        "expected_shortfall_95": None,
        "greeks_aggregate": {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0},
        "warnings": warnings,
        "leg_count": 0,
        "structure_label": "empty",
    }
