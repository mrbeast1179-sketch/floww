"""
Institutional flow-alert engine — server-side port of the scanner's alert
math (frontend/src/components/flowseeker/scanLogic.js) plus the enrichment
an institutional feed needs and the browser never had:

  • Black-Scholes per-contract ENTRY price (not the 0.4-approx premium)
  • side/bias inference (BUY + BULLISH/BEARISH from opening-flow shape)
  • GOLD / SILVER / BRONZE conviction tiers from a deterministic factor count
  • DuckDB-persisted feed with rule-namespaced dedup TTLs
  • move-since-alert tracking (the feed's "+3.9%" column)

Runs on EVERY fresh /scan result inside the backend, so alerts fire and
persist regardless of whether the Scanner tab is open — the root cause of
"Blademap alerted PLTR today and we had nothing".

Rule semantics intentionally mirror scanLogic.js (same thresholds, same
priority order, same plain-English `why` discipline) so the frontend tape
and this feed never disagree about what qualifies.

DuckDB invariant: ALL writes go through engine.execute_write (never a raw
conn) — see floww-audit-2026-07-11 (thread-unsafe shared connection).
"""

from __future__ import annotations

import logging
import math
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Column order of the cvforge `screen` call in routes/flowseeker.py:market_scan.
SCAN_COLUMNS = [
    "underlying_ticker", "ticker", "contract_type", "strike_price",
    "expiration_date", "day_volume", "open_interest",
    "implied_volatility", "delta", "underlying_price",
]

_RISK_FREE = 0.045

# Rule-namespaced dedup TTLs (seconds) — mirrors the frontend's ttl choices:
# confirmations are once-a-session claims, intraday prints re-arm faster.
_TTL_S = {
    "OICONF": 20 * 3600,
    "SIGMA": 4 * 3600,
    "SCORE": 2 * 3600,
    "WHALE": 6 * 3600,
    "0DTE": 1 * 3600,
}

_TIER_RANK = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}


# ── helpers ──────────────────────────────────────────────────────────

def _f(v):
    try:
        if v is None:
            return None
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except (TypeError, ValueError):
        return None


def _norm_iv(iv):
    """cvforge sometimes reports IV in percent; <3 means it's already decimal."""
    x = _f(iv)
    if x is None or x <= 0:
        return None
    return x / 100.0 if x >= 3 else x


def biz_dte(exp_str: str, today: date | None = None) -> int | None:
    """Business days from today to expiry (0 = expires today). None if unparseable."""
    try:
        exp = date.fromisoformat(str(exp_str)[:10])
    except (TypeError, ValueError):
        return None
    d = today or datetime.now(_ET).date()
    if exp <= d:
        return 0
    n, cur = 0, d
    while cur < exp:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def norm_rows(raw_rows, columns: list[str] | None = None) -> list[dict]:
    """cvforge screen list-rows → normalized dicts with derived metrics.

    Malformed rows are dropped, never raised — a feed hiccup must not take
    the alert engine down with it.
    """
    cols = columns or SCAN_COLUMNS
    idx = {c: i for i, c in enumerate(cols)}
    out = []
    for raw in raw_rows or []:
        try:
            if not raw or not isinstance(raw, (list, tuple)) or len(raw) < len(cols):
                continue
            under = str(raw[idx["underlying_ticker"]] or "").upper()
            strike = _f(raw[idx["strike_price"]])
            if not under or strike is None or strike <= 0:
                continue
            typ_raw = str(raw[idx["contract_type"]] or "").lower()
            typ = "call" if typ_raw.startswith("c") else "put" if typ_raw.startswith("p") else None
            if typ is None:
                continue
            vol = _f(raw[idx["day_volume"]]) or 0.0
            oi = _f(raw[idx["open_interest"]]) or 0.0
            iv = _norm_iv(raw[idx["implied_volatility"]])
            delta = _f(raw[idx["delta"]])
            spot = _f(raw[idx["underlying_price"]])
            exp = str(raw[idx["expiration_date"]] or "")[:10]
            dte = biz_dte(exp)
            vol_oi = vol / oi if oi > 0 else vol
            r = {
                "under": under, "occ": str(raw[idx["ticker"]] or ""),
                "type": typ, "strike": strike, "exp": exp, "dte": dte,
                "vol": vol, "oi": oi, "iv": iv, "delta": delta, "spot": spot,
                "vol_oi": vol_oi,
                "notional": vol * 100 * strike,
                "ckey": f"{under}|{typ}|{strike:g}|{exp}",
            }
            px = est_entry(r)
            r["est_entry"] = px
            r["premium"] = (vol * 100 * px) if px is not None else None
            out.append(r)
        except Exception:
            continue
    return out


# ── scoring (parity with scanLogic.scanScoreOf) ─────────────────────

def scan_score(r: dict, regime: str | None = None) -> int:
    dl = abs(r.get("delta") or 0.0)
    vol_oi = r.get("vol_oi") or 0.0
    vol = max(r.get("vol") or 0.0, 1.0)
    notional = max(r.get("notional") or 0.0, 1.0)
    dte = r.get("dte")

    pos = min(vol_oi / 3.0, 1.0)
    size = min(math.log(vol) / math.log(50000), 1.0)
    notl = min(math.log(notional) / math.log(50e6), 1.0)
    urg = 0.3 if dte is None else (1.0 if dte <= 2 else 0.7 if dte <= 7 else 0.4 if dte <= 30 else 0.15)
    otm = 0.3 if r.get("delta") is None else max(0.0, min((0.5 - dl) / 0.4, 1.0))

    s = (pos * 0.34 + size * 0.24 + notl * 0.18 + urg * 0.14 + otm * 0.10) * 100
    if regime == "negative" and dte is not None and dte <= 7:
        s += 5
    elif regime == "positive" and vol_oi >= 2:
        s += 3
    # Informed-positioning band (Pan & Poteshman, RFS 2006): 7–90 DTE +
    # vol≥3×OI + ≥$25k premium is where directional bets live.
    if dte is not None and 7 <= dte <= 90 and vol_oi >= 3 and (r.get("premium") or 0) >= 25e3:
        s += 4
    return max(0, min(100, round(s)))


# ── entry price (true Black-Scholes, not the 0.4-approx) ────────────

def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def est_entry(r: dict) -> float | None:
    """Per-contract Black-Scholes entry estimate from the screen row's own
    IV/spot/strike/DTE. Floored at $0.05 (option minimum tick reality)."""
    iv, spot, strike = r.get("iv"), r.get("spot"), r.get("strike")
    if not iv or not spot or not strike or spot <= 0 or strike <= 0:
        return None
    dte = r.get("dte")
    t = max(dte if dte is not None else 5, 0.3) / 365.0
    try:
        srt = iv * math.sqrt(t)
        d1 = (math.log(spot / strike) + (_RISK_FREE + iv * iv / 2.0) * t) / srt
        d2 = d1 - srt
        disc = math.exp(-_RISK_FREE * t)
        if r.get("type") == "put":
            px = strike * disc * _ncdf(-d2) - spot * _ncdf(-d1)
        else:
            px = spot * _ncdf(d1) - strike * disc * _ncdf(d2)
    except (ValueError, OverflowError, ZeroDivisionError):
        return None
    return round(max(0.05, px), 2)


# ── side / bias inference ───────────────────────────────────────────

def infer_side_bias(r: dict) -> tuple[str, str | None]:
    """Opening-dominant flow (vol well above resting OI) reads as initiated
    BUYing on a print-less feed; anything else is unlabeled FLOW — a desk
    never claims a side it can't defend."""
    if (r.get("vol_oi") or 0) >= 1.5:
        return "BUY", ("BULLISH" if r.get("type") == "call" else "BEARISH")
    return "FLOW", None


# ── tiering ─────────────────────────────────────────────────────────

def tier_of(factors: dict) -> str | None:
    n = sum(1 for v in (factors or {}).values() if v)
    if n >= 3:
        return "GOLD"
    if n == 2:
        return "SILVER"
    if n == 1:
        return "BRONZE"
    return None


# ── the engine ──────────────────────────────────────────────────────

def _mk_alert(r: dict, rule: str, extra: dict, factors: dict, asof: str) -> dict:
    side, bias = infer_side_bias(r)
    return {
        "key": f"{rule.lower()}|{r['ckey']}",
        "ckey": r["ckey"], "rule": rule,
        "tier": tier_of(factors) or "BRONZE",
        "side": side, "bias": bias,
        "under": r["under"], "type": r["type"], "strike": r["strike"],
        "exp": r["exp"], "dte": r.get("dte"),
        "score": r.get("_score"),
        "est_entry": r.get("est_entry"), "premium": r.get("premium"),
        "notional": r.get("notional"), "vol_oi": r.get("vol_oi"),
        "sigma": extra.get("sigma"), "oi_chg_pct": extra.get("oi_chg_pct"),
        "under_price": r.get("spot"),
        # Conviction v2 v2.1: surface the cluster factor that the engine
        # already computed in _common_factors(factors). A row whose ticker
        # laddered with ≥3 same-bias qualifying contracts in the snapshot
        # gets cluster=True; the frontend can now render an honest CLUSTER
        # chip without inferring a proxy from tier+SIGMA.
        "cluster": bool(factors.get("cluster", False)),
        "why": extra.get("why", ""),
        "ttl_s": _TTL_S.get(rule, 2 * 3600),
        "asof": asof,
    }


def _finalize(a: dict, r: dict, cw_map: dict | None) -> dict:
    """Conviction v2 post-pass: attach the ticker's CW spread, and demote
    paired strategy legs — a vertical's leg is never a directional whale."""
    cw = (cw_map or {}).get(a["under"])
    a["cw_spread"] = round(cw, 4) if cw is not None else None
    if r.get("spread_leg"):
        a["side"], a["bias"], a["tier"] = "STRATEGY", None, "BRONZE"
        a["why"] = (a.get("why") or "") + " [paired legs: likely spread — direction unclaimed]"
    return a


def _common_factors(r: dict, regimes: dict, sigma_tickers: set,
                    cw_map: dict | None = None, clusters: dict | None = None) -> dict:
    from services.flow_quality import cw_confirms, is_prime

    reg = (regimes or {}).get(r["under"])
    dte, vol_oi = r.get("dte"), r.get("vol_oi") or 0
    _, bias = infer_side_bias(r)
    return {
        "score90": (r.get("_score") or 0) >= 90,
        "whale": (r.get("premium") or 0) >= 10e6,
        "sigma_ticker": r["under"] in sigma_tickers,
        "informed_band": dte is not None and 7 <= dte <= 90 and vol_oi >= 3 and (r.get("premium") or 0) >= 25e3,
        "regime_confluent": (reg == "negative" and dte is not None and dte <= 7)
                            or (reg == "positive" and vol_oi >= 2),
        # Conviction v2 factors (spec: 2026-07-20-flow-quality-conviction-v2)
        "prime": is_prime(r),
        "cluster": bool(clusters) and clusters.get(r["under"]) == bias and bias is not None,
        "cw_confirm": cw_confirms(bias, (cw_map or {}).get(r["under"])),
    }


def eval_institutional(rows, baselines=None, prev_oi=None, regimes=None, opts=None):
    """Evaluate normalized rows into enriched institutional alerts.

    One alert per contract, strongest claim first (OICONF > SCORE > WHALE >
    0DTE), plus per-ticker SIGMA alerts. Pure logic — dedup/persistence are
    the I/O layer's job so this stays unit-testable.
    """
    from services.flow_quality import (
        bh_fdr, cluster_biases, cw_iv_spread, detect_spreads, sigma_pvalue,
    )

    o = {
        "min_score": 85, "whale_premium": 10e6, "zero_dte_score": 70,
        "oiconf_pct": 0.30, "oiconf_notional": 1e6, "sigma_min": 3.0,
        "fdr_q": 0.10,
        **(opts or {}),
    }
    baselines = baselines or {}
    prev_oi = prev_oi or {}
    regimes = regimes or {}
    asof = datetime.now(_ET).isoformat(timespec="seconds")

    rows = list(rows or [])
    for r in rows:
        r["_score"] = scan_score(r, regimes.get(r["under"]))

    # Conviction v2 context: spread-leg flags, Cremers-Weinbaum call-put IV
    # spread, and same-bias laddering — all cross-row reads of THIS snapshot.
    detect_spreads(rows)
    cw_map = cw_iv_spread(rows)
    clusters = cluster_biases(rows)

    # Per-ticker σ vs multi-day baseline. Two-stage quality gate:
    #   1. market-mode removal — a broad volume day lifts every ticker's σ
    #      together; subtract the cross-sectional median (when the cross-
    #      section is wide enough to define one) so only IDIOSYNCRATIC
    #      spikes remain;
    #   2. Benjamini-Hochberg FDR at q — testing hundreds of tickers a day
    #      at a raw cutoff is a multiple-testing machine.
    by_ticker: dict[str, float] = {}
    for r in rows:
        by_ticker[r["under"]] = by_ticker.get(r["under"], 0.0) + (r.get("vol") or 0.0)
    raw_sigma: dict[str, float] = {}
    for under, tot in by_ticker.items():
        b = baselines.get(under)
        if not b or not b.get("std") or (b.get("days") or 0) < 2:
            continue
        raw_sigma[under] = (tot - b["avg"]) / b["std"]
    market_mode = 0.0
    if len(raw_sigma) >= 5:
        ordered = sorted(raw_sigma.values())
        mid = len(ordered) // 2
        med = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
        market_mode = max(0.0, med)
    adj_sigma = {t: s - market_mode for t, s in raw_sigma.items()}
    pvals = {t: sigma_pvalue(s) for t, s in adj_sigma.items() if s >= o["sigma_min"]}
    survivors = bh_fdr(pvals, q=o["fdr_q"])
    sigma_hits = {t: round(raw_sigma[t], 1) for t in survivors}
    sigma_tickers = set(sigma_hits)

    out: list[dict] = []

    # Pass 1 — OICONF: overnight OI build is the one hard "yesterday's flow
    # was real" proof a print-less feed offers. Top 5 by % build.
    cand = []
    for r in rows:
        prev = prev_oi.get(r["ckey"])
        if prev is None or prev <= 0 or not r.get("oi"):
            continue
        chg = r["oi"] - prev
        pct = chg / prev
        add_notl = abs(chg) * 100 * r["strike"]
        if pct >= o["oiconf_pct"] and add_notl >= o["oiconf_notional"]:
            cand.append((pct, add_notl, r))
    cand.sort(key=lambda c: c[0], reverse=True)
    winners = set()
    for pct, add_notl, r in cand[:5]:
        winners.add(r["ckey"])
        f = _common_factors(r, regimes, sigma_tickers, cw_map, clusters)
        f["oiconf"] = True
        out.append(_finalize(_mk_alert(r, "OICONF", {
            "oi_chg_pct": round(pct, 4),
            "why": f"OI +{round(pct * 100)}% overnight (${add_notl / 1e6:.1f}M added notional) — prior-day flow HELD as new positioning",
        }, f, asof), r, cw_map))

    # Pass 2 — intraday per-contract rules, strongest first, one per contract.
    for r in rows:
        if r["ckey"] in winners:
            continue
        f = _common_factors(r, regimes, sigma_tickers, cw_map, clusters)
        rule, why = None, None
        score = r.get("_score") or 0
        if score >= o["min_score"]:
            rule = "SCORE"
            why = f"score {score} — vol {r['vol_oi']:.1f}× OI, ~${(r.get('premium') or 0) / 1e6:.2f}M premium, {r.get('dte')} DTE"
        elif (r.get("premium") or 0) >= o["whale_premium"]:
            rule = "WHALE"
            why = f"~${(r.get('premium') or 0) / 1e6:.1f}M estimated premium on a single line"
        elif r.get("dte") is not None and r["dte"] <= 1 and score >= o["zero_dte_score"]:
            rule = "0DTE"
            why = f"{r['dte']} DTE with score {score} — urgent short-fuse positioning"
        if not rule:
            continue
        out.append(_finalize(_mk_alert(r, rule, {"why": why}, f, asof), r, cw_map))

    # Pass 3 — per-ticker SIGMA alerts (aggregate anomaly, no single strike).
    for under, s in sigma_hits.items():
        best = max((r for r in rows if r["under"] == under), key=lambda r: r.get("_score") or 0)
        b = baselines[under]
        f = {"sigma": True, "score90": (best.get("_score") or 0) >= 90}
        a = _mk_alert(best, "SIGMA", {
            "sigma": s,
            "why": f"{under} options volume {s}σ above its {b.get('days')}-day baseline",
        }, f, asof)
        a["key"] = f"sigma|{under}"
        a["ckey"] = under
        a["type"], a["strike"], a["exp"] = "", None, ""
        cw = cw_map.get(under)
        a["cw_spread"] = round(cw, 4) if cw is not None else None
        out.append(a)

    return out


# ── DuckDB I/O ──────────────────────────────────────────────────────

def init_flow_alert_tables(engine) -> None:
    engine.execute_write("""
        CREATE TABLE IF NOT EXISTS flow_alerts_daily (
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
    try:
        # Migration for pre-Conviction-v2 tables (column added 2026-07-20).
        engine.execute_write(
            "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS cw_spread DOUBLE")
    except Exception:
        pass
    try:
        # Migration for v2.1 — cluster factor surfaced to the feed (2026-07-20).
        engine.execute_write(
            "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS cluster BOOLEAN")
    except Exception:
        pass
    try:
        # Migration for v2.3 — wins column (BIGINT). The alert_quality() SQL
        # CAST(SUM(...) AS BIGINT) requires this column. Pre-v2.3 prod tables
        # upgrade in place without manual SQL. Mirrors cw_spread / cluster
        # migration pattern above.
        engine.execute_write(
            "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS wins BIGINT")
    except Exception:
        pass
    engine.execute_write("""
        CREATE TABLE IF NOT EXISTS flow_alert_dedup (
            key TEXT PRIMARY KEY, last_fired_ts DOUBLE, ttl_s DOUBLE
        )
    """)


def persist_alerts(engine, alerts, snapshot_date: str | None = None) -> int:
    """UPSERT alerts under today's ET session date. Same-day re-evals
    overwrite their row (idempotent) rather than duplicating the feed."""
    if not alerts:
        return 0
    day = snapshot_date or datetime.now(_ET).date().isoformat()
    rows = [[
        day, a.get("asof"), a["key"], a.get("ckey"), a["rule"], a["tier"],
        a.get("side"), a.get("bias"), a["under"], a.get("type"),
        a.get("strike"), a.get("exp"), a.get("dte"), a.get("score"),
        a.get("est_entry"), a.get("premium"), a.get("notional"),
        a.get("vol_oi"), a.get("sigma"), a.get("oi_chg_pct"),
        a.get("under_price"), a.get("cw_spread"), bool(a.get("cluster", False)),
        a.get("why"),
    ] for a in alerts]
    engine.execute_write("""
        INSERT INTO flow_alerts_daily (
            asof_date, asof_ts, key, ckey, rule, tier, side, bias, under, type,
            strike, exp, dte, score, est_entry, premium, notional, vol_oi,
            sigma, oi_chg_pct, under_price, cw_spread, cluster, why
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (asof_date, key) DO UPDATE SET
            asof_ts = excluded.asof_ts, tier = excluded.tier, side = excluded.side,
            bias = excluded.bias, score = excluded.score,
            est_entry = excluded.est_entry, premium = excluded.premium,
            notional = excluded.notional, vol_oi = excluded.vol_oi,
            sigma = excluded.sigma, oi_chg_pct = excluded.oi_chg_pct,
            under_price = excluded.under_price, cw_spread = excluded.cw_spread,
            cluster = excluded.cluster, why = excluded.why
    """, rows)
    return len(rows)


def alert_quality(engine, days: int = 30) -> list[dict]:
    """Per rule × tier precision from realized moves — the calibration loop.

    hit = the underlying moved ≥0.5% in the alert's claimed direction since
    the alert fired (move_pct is stamped by update_moves on every scan).
    Directionless rows (bias NULL — STRATEGY legs, SIGMA) are excluded.

    v2.3: also emits `wins` (integer count of hits) alongside hit_rate so the
    frontend can pool many (rule, tier) rows into a tier-level binomial CI
    (Wilson 90%) using integer-accurate totals. The float-rounding fallback
    n_measured*hit_rate is acceptable when `wins` is absent (older DBs),
    but the integer SUM is the bit-exact source of truth.
    """
    since = (datetime.now(_ET).date() - timedelta(days=max(1, days))).isoformat()
    try:
        return engine.query("""
            SELECT rule, tier, count(*) AS n,
                   count(move_pct) AS n_measured,
                   CAST(SUM(CASE WHEN move_pct IS NULL THEN 0
                                 WHEN bias = 'BULLISH' AND move_pct >= 0.5 THEN 1
                                 WHEN bias = 'BEARISH' AND move_pct <= -0.5 THEN 1
                                 ELSE 0 END) AS BIGINT) AS wins,
                   avg(CASE WHEN move_pct IS NULL THEN NULL
                            WHEN bias = 'BULLISH' AND move_pct >= 0.5 THEN 1.0
                            WHEN bias = 'BEARISH' AND move_pct <= -0.5 THEN 1.0
                            ELSE 0.0 END) AS hit_rate,
                   avg(move_pct) AS avg_move_pct
            FROM flow_alerts_daily
            WHERE asof_date >= ? AND bias IS NOT NULL
            GROUP BY rule, tier
            ORDER BY rule, tier
        """, [since])
    except Exception as e:
        logger.warning(f"flow_alerts.alert_quality: {e}")
        return []


def dedup_filter(engine, alerts, now: float | None = None) -> list[dict]:
    """Drop alerts whose key fired within its TTL; record the survivors."""
    if not alerts:
        return []
    t = time.time() if now is None else now
    keys = [a["key"] for a in alerts]
    ph = ",".join("?" for _ in keys)
    try:
        seen = {r["key"]: r for r in engine.query(
            f"SELECT key, last_fired_ts, ttl_s FROM flow_alert_dedup WHERE key IN ({ph})", keys)}
    except Exception:
        seen = {}
    kept = []
    for a in alerts:
        s = seen.get(a["key"])
        if s and (t - (s["last_fired_ts"] or 0)) < (s["ttl_s"] or 0):
            continue
        kept.append(a)
    if kept:
        engine.execute_write("""
            INSERT INTO flow_alert_dedup (key, last_fired_ts, ttl_s)
            VALUES (?, ?, ?)
            ON CONFLICT (key) DO UPDATE SET
                last_fired_ts = excluded.last_fired_ts, ttl_s = excluded.ttl_s
        """, [[a["key"], t, float(a.get("ttl_s") or 7200)] for a in kept])
    return kept


def update_moves(engine, spot_map: dict) -> int:
    """Stamp the latest underlying price onto open alerts → move-since-alert.
    Called with every fresh scan's spots; zero extra upstream calls."""
    n = 0
    for under, px in (spot_map or {}).items():
        p = _f(px)
        if p is None or p <= 0:
            continue
        try:
            rows = engine.query(
                "SELECT count(*) AS c FROM flow_alerts_daily WHERE under = ? AND under_price > 0", [under])
            c = int(rows[0]["c"]) if rows else 0
            if not c:
                continue
            engine.execute_write("""
                UPDATE flow_alerts_daily
                SET last_price = ?, move_pct = (? - under_price) / under_price * 100.0
                WHERE under = ? AND under_price > 0
            """, [[p, p, under]])
            n += c
        except Exception as e:
            logger.debug(f"flow_alerts.update_moves({under}): {e}")
    return n


def read_alert_feed(engine, days: int = 7, min_tier: str | None = None,
                    ticker: str | None = None) -> list[dict]:
    """The institutional feed: tier-ranked, then most recent first."""
    since = (datetime.now(_ET).date() - timedelta(days=max(1, days))).isoformat()
    sql = """
        SELECT * FROM flow_alerts_daily WHERE asof_date >= ?
    """
    params: list = [since]
    if ticker:
        sql += " AND under = ?"
        params.append(ticker.upper())
    if min_tier:
        rank = _TIER_RANK.get(min_tier.upper(), 2)
        allowed = [t for t, v in _TIER_RANK.items() if v <= rank]
        sql += f" AND tier IN ({','.join('?' for _ in allowed)})"
        params.extend(allowed)
    sql += """
        ORDER BY CASE tier WHEN 'GOLD' THEN 0 WHEN 'SILVER' THEN 1 ELSE 2 END,
                 asof_ts DESC
    """
    try:
        return engine.query(sql, params)
    except Exception as e:
        logger.warning(f"flow_alerts.read_alert_feed: {e}")
        return []
