/**
 * InstitutionalAlertsPanel.jsx — Conviction v2 in the scanner tab.
 *
 * Fetches the server-side engine's persisted feed (`/alerts/feed`) and the
 * calibration strip (`/alerts/quality`), then renders every Conviction v2
 * lever as a chip:
 *
 *   spread_leg  → STRATEGY tier pill (engine demotes paired legs); we
 *                 deliberately do NOT stack a separate PAIRED LEGS chip on
 *                 top — the pill already conveys the demotion.
 *   cw_spread   → +X% confirms / -X% confirms chip (only when it CONFIRMS bias)
 *   cluster     → CLUSTER chip (v2.1 — backend stamps a per-ticker bool; we
 *                 light up IFF `alert.cluster === true`, never on a proxy)
 *   sigma       → σ X.X chip (BH-FDR-surviving spike)
 *   prime       → PRIME chip (premium ≥ $250k AND vol/OI ≥ 5)
 *   tier        → GOLD / SILVER / BRONZE pill
 *
 * Quality strip under the table: per-tier n, hit-rate, avg move since alert.
 * Thin rows (n_measured == 0) read "—" so an underpowered tier doesn't look
 * like a 0%-hit rate. Network/parse failures on /alerts/quality are surfaced
 * as a same-shape banner rather than silently disappearing — when the strip
 * is unavailable a desk needs to see it (otherwise a real measurement gap
 * would look identical to "no measured alerts yet").
 *
 * The panel is tolerant of an empty feed (no fresh scan yet — see
 * backend/services/cvserver_client.py cadence) and degrades gracefully to
 * a "waiting for first scan" empty state instead of a misleading table.
 */
import React, { useMemo, useState, useCallback } from "react";
import { useFlowseeker } from "../../hooks/useFlowseeker";
import {
  previewAutoTrades,
  executeAutoTrades,
  persistJournalSeeds,
} from "./autoTrade";
import {
  compareAlerts,
  clusterChip,
  cwConfirmChip,
  dailySeriesForTier,
  DAILY_MIN_N,
  fmtCW,
  fmtMovePct,
  primeChip,
  qualityTrendForTier,
  sigmaChip,
  summarizeQuality,
  tierBadge,
  tierLockFor,
  TREND_COLOR,
} from "./convictionUi";

export default function InstitutionalAlertsPanel({ active = true, days = 7, limit = 100 }) {
  const { data: feedData, loading: feedLoading, error: feedError, refresh: refreshFeed } = useFlowseeker(
    "alerts/feed", { days, ticker: "", refreshMs: 12_000, skip: !active }
  );
  // v2.2 — single batched call returns {quality_windows: {7: [...], 14: [...], 30: [...]}}
  // The strip project the longest window (the macro read); each cell's
  // sparkline reads every window via qualityTrendForTier.
  const { data: qualityData, error: qualityError, refresh: refreshQuality } = useFlowseeker(
    "alerts/quality", { days: "7,14,30", refreshMs: 60_000, skip: !active }
  );

  const rows = useMemo(() => {
    const arr = feedData?.alerts || [];
    return [...arr].sort(compareAlerts).slice(0, limit);
  }, [feedData, limit]);

  const summary = useMemo(
    () => summarizeQuality(qualityData),
    [qualityData]
  );

  // Convenience accessor for the trend helper — strip just the rows keyed
  // by window so the helper signature stays clean.
  const qualityWindows = qualityData?.quality_windows || null;
  const dailyMap = qualityData?.daily_series || null;
  const dailyDays = qualityData?.daily_series_days || 30;

  const hasData = rows.length > 0;
  const empty = !feedLoading && !feedError && !hasData;
  // Distinguish three strip states: error (banner), measured (strip), idle.
  const qualityUnavailable = !!qualityError && !summary.hasData;

  // ── Signal-to-trade bridge UI state (two-step arm/fire) ──
  // preview → shows what WOULD trade (read-only) → execute submits paper
  // orders AND persists journal_seeds into floww_trades_v2.
  const [atState, setAtState] = useState("idle"); // idle|preview|executing|done
  const [atPreview, setAtPreview] = useState(null);
  const [atResult, setAtResult] = useState(null);
  const [atError, setAtError] = useState(null);

  const handlePreview = useCallback(async () => {
    setAtError(null);
    try {
      const data = await previewAutoTrades({ tier: "SILVER", minDte: 2 });
      setAtPreview(data);
      setAtState("preview");
    } catch (e) {
      setAtError(String(e.message || e));
    }
  }, []);

  const handleExecute = useCallback(async () => {
    setAtState("executing");
    setAtError(null);
    try {
      const data = await executeAutoTrades({ tier: "SILVER", minDte: 2 });
      const added = persistJournalSeeds(data.journal_seeds || []);
      setAtResult({ ...data, journal_added: added });
      setAtState("done");
      refreshFeed();
    } catch (e) {
      setAtError(String(e.message || e));
      setAtState("preview");
    }
  }, [refreshFeed]);


  return (
    <div className="fsp-conviction" aria-label="Conviction v2 institutional alerts">
      <header className="fsp-conviction-h">
        <div className="fsp-conviction-title">
          <span className="fsp-conviction-dot" />
          <span className="fsp-conviction-name">Conviction v2</span>
          <span className="fsp-conviction-sub">
            tier-weighted · spread demoted · CW-confirmed · BH-FDR σ
          </span>
        </div>
        <div className="fsp-conviction-meta">
          <span className="fsp-conviction-count">
            {hasData ? `${rows.length} / ${feedData.count || rows.length}` : "—"}
          </span>
          <button
            type="button"
            className="fsp-conviction-refresh"
            onClick={refreshFeed}
            title="Re-fetch from /alerts/feed + /alerts/quality"
          >
            ↻
          </button>
        </div>
      </header>

      {atError && (
        <div className="fsp-conviction-err" role="alert">Auto-trade: <code>{atError}</code></div>
      )}

      {/* Signal-to-trade bridge bar — preview then arm/fire */}
      {hasData && (
        <div className="fsp-at-bar" aria-label="Signal to trade bridge">
          {atState === "idle" && (
            <>
              <span className="fsp-at-hint">
                Auto-trade qualifying alerts → paper portfolio + journal
              </span>
              <button type="button" className="fsp-at-btn" onClick={handlePreview}>
                Preview trades
              </button>
            </>
          )}
          {atState === "preview" && atPreview && (
            <>
              <span className="fsp-at-hint">
                {atPreview.count} trade{atPreview.count === 1 ? "" : "s"} pass gates
                {" "}({atPreview.gates?.min_tier ?? "SILVER"}+, DTE ≥ {atPreview.gates?.min_dte ?? 2})
                {atPreview.count > 0 && (
                  <> · {(atPreview.trades || []).slice(0, 4).map(t => t.order.symbol).join(", ")}
                    {(atPreview.trades || []).length > 4 ? "…" : ""}</>
                )}
              </span>
              <button type="button" className="fsp-at-btn fsp-at-btn-arm" onClick={handleExecute}
                      disabled={atPreview.count === 0}>
                Execute + journal
              </button>
              <button type="button" className="fsp-at-btn" onClick={() => setAtState("idle")}>
                Cancel
              </button>
            </>
          )}
          {atState === "executing" && (
            <span className="fsp-at-hint">Executing…</span>
          )}
          {atState === "done" && atResult && (
            <>
              <span className="fsp-at-hint fsp-at-ok">
                ✓ {atResult.accepted}/{atResult.count} orders accepted
                {" "}· {atResult.journal_added} journal card{atResult.journal_added === 1 ? "" : "s"} written
              </span>
              <button type="button" className="fsp-at-btn" onClick={() => setAtState("idle")}>
                Dismiss
              </button>
            </>
          )}
        </div>
      )}

      {feedError && (
        <div className="fsp-conviction-err">
          Alerts feed unreachable: <code>{String(feedError).slice(0, 160)}</code>
        </div>
      )}

      {empty && (
        <div className="fsp-conviction-empty">
          <div className="fsp-conviction-empty-headline">No fresh scan yet.</div>
          <div className="fsp-conviction-empty-body">
            The institutional alert engine stamps rows on every{" "}
            <code>/api/flowseeker/scan</code>; alerts appear here once the next cvforge budget
            slot populates the feed.
          </div>
        </div>
      )}

      {hasData && (
        <div className="fsp-conviction-table-wrap">
          <table className="fsp-conviction-table">
            <thead>
              <tr>
                <th>Tier</th>
                <th>Ticker</th>
                <th>Bias</th>
                <th>Rule</th>
                <th>Strike</th>
                <th className="num">DTE</th>
                <th className="num">Score</th>
                <th className="num">Vol/OI</th>
                <th className="num">Premium</th>
                <th>Chips</th>
                <th className="num">Move</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a, i) => {
                const tier = tierBadge(a.tier, a.side);
                const cw = cwConfirmChip(a);
                const cluster = clusterChip(a);
                const prime = primeChip(a);
                const sigma = sigmaChip(a.sigma);
                return (
                  <tr key={`${a.key || a.under}_${i}`} title={a.why || ""}>
                    <td><span className={tier.className}>{tier.label}</span></td>
                    <td className="fsp-conviction-tk">{a.under}</td>
                    <td className={`fsp-conviction-bias ${biasClass(a)}`}>
                      {a.bias || (a.side === "STRATEGY" ? "—" : a.side || "—")}
                    </td>
                    <td className="fsp-conviction-rule">{a.rule || "—"}</td>
                    <td className="fsp-conviction-strike">
                      {a.strike ? `$${fmtStrike(a.strike)}` :
                        (a.rule === "SIGMA" ? <em className="fsp-conviction-ticker-only">ticker-level</em> : "—")}
                    </td>
                    <td className="num">{a.dte ?? "—"}</td>
                    <td className="num">{a.score ?? "—"}</td>
                    <td className="num">{a.vol_oi != null ? `${Number(a.vol_oi).toFixed(1)}×` : "—"}</td>
                    <td className="num">
                      {a.premium != null ? fmtPremium(a.premium) : "—"}
                    </td>
                    <td className="fsp-conviction-chips">
                      {cw && <span className={cw.className}>{cw.label}</span>}
                      {cluster && <span className={cluster.className}>{cluster.label}</span>}
                      {prime && <span className={prime.className}>{prime.label}</span>}
                      {sigma && <span className={sigma.className}>{sigma.label}</span>}
                      {a.cw_spread != null && !cw && (
                        <span className="fsp-chip fsp-chip-cw-neutral" title={`CW ${fmtCW(a.cw_spread)} — not confirming bias`}>
                          CW {fmtCW(a.cw_spread)}
                        </span>
                      )}
                    </td>
                    <td className={`num ${moveClass(a.move_pct, a.bias)}`}>
                      {fmtMovePct(a.move_pct)}
                    </td>
                    <td className="fsp-conviction-why">{a.why || ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {qualityUnavailable && (
        <div className="fsp-conviction-err" role="alert" aria-label="Calibration unavailable">
          Calibration unavailable — <code>/alerts/quality</code>{" "}
          returned: <code>{String(qualityError).slice(0, 160)}</code>.{" "}
          <button
            type="button"
            className="fsp-conviction-retry"
            onClick={refreshQuality}
            title="Re-fetch /alerts/quality"
          >
            ↻ retry
          </button>
        </div>
      )}

      {summary.hasData && (
        <div className="fsp-conviction-quality" role="group" aria-label="Quality calibration">
          <div className="fsp-conviction-qtitle">
            <span>Calibration</span>
            <span className="fsp-conviction-qsub">
              last {summary.days}d · hit-rate (|move| ≥ 0.5% in alert direction)
              {qualityWindows && " · trend 7→30d"}
            </span>
          </div>
          <div className="fsp-conviction-qstrip">
            {summary.tiers.map((t) => (
              <div key={t.tier} className={`fsp-conviction-qcell fsp-conviction-qcell-${t.tier.toLowerCase()}`}>
                <div className="fsp-conviction-qcell-tier">{t.tier}</div>
                <TierLockSigil tier={t.tier} payload={qualityData} />
                <div className="fsp-conviction-qcell-hr">                   {t.thin
                     ? "—"
                     : (
                       <>
                         {`${Math.round((t.hit_rate || 0) * 100)}%`}
                         {t.hit_lo != null && t.hit_hi != null && (
                           <span
                             className="fsp-conviction-ci"
                             title={`Wilson 90% CI from ${t.hits ?? 0}/${t.n_measured} resolved hits`}
                           >
                             {` [${Math.round((t.hit_lo || 0) * 100)}, ${Math.round((t.hit_hi || 0) * 100)}]`}
                           </span>
                         )}
                       </>
                     )}
                </div>
                <div className="fsp-conviction-qcell-meta">
                  {t.n_measured}/{t.n} measured
                  {!t.thin && t.avg_move_pct != null && (
                    <> · avg move {t.avg_move_pct >= 0 ? "+" : ""}{t.avg_move_pct.toFixed(2)}%</>
                  )}
                </div>
                {t.best_rule && (
                  <div
                    className="fsp-conviction-bestrule"
                    title={`Top-producing rule in ${t.tier}: ${t.best_rule.rule} with ${Math.round(t.best_rule.hit_rate * 100)}% over ${t.best_rule.n_measured} measured alerts`}
                  >
                    via <strong>{t.best_rule.rule}</strong>{" "}
                    {`${Math.round(t.best_rule.hit_rate * 100)}%`}
                    <span className="fsp-conviction-bestrule-meta">
                      ({t.best_rule.n_measured})
                    </span>
                  </div>
                )}
                <QualitySparkline tier={t.tier} windows={qualityWindows} />
                <DailySparkline tier={t.tier} daily={dailyMap} days={dailyDays} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── tiny helpers (local — table cells only) ──────────────────────────

// Tier-lock sigil (v3.x — tier-lock hysteresis UI). Renders a small chip
// alongside the tier label when /alerts/quality's `tier_locks[tier]` entry
// reads `engaged: true` with a finite `locked_hit_rate`. The chip is the
// desk-visible signal that the retuner is HOLDING the tier's threshold
// rather than chasing noise — "Lock engaged: GOLD 75%" is proof the
// measured hit-rate is stable, not a random sample.
// Strictly informational; the retuner enforces the lock on the data
// side independently. Renders `null` (no DOM) when the tier is not
// engaged, when the source `locked_hit_rate` is null/NaN, or when the
// payload's `tier_locks` field is missing entirely — same null-safety
// contract as `convictionUi.tierLockFor()` (which has 6 helper tests
// pinning that contract). The aria-label / title carry the engaged
// rate + the locked_at timestamp the desk needs to triangulate "when
// did this lock engage" without leaving the strip.
// CSS classes: `fsp-chip fsp-chip-lock` extend the existing chip
// naming (sibling to `fsp-chip-prime`, `fsp-chip-cluster`,
// `fsp-chip-sigma`, etc.). The 🔒 glyph is decorative; the
// aria-label carries the semantic weight so screen-readers announce
// the rate, not the lock icon.
function TierLockSigil({ tier, payload }) {
  const lock = tierLockFor(tier, payload);
  if (!lock) return null;
  const rate = lock.locked_hit_rate;
  const rateStr = `${Math.round(rate * 100)}%`;
  const ariaLabel = `Tier lock engaged for ${tier}: ${rateStr} — LOCK`
    + (lock.locked_at ? ` (held since ${lock.locked_at})` : "");
  return (
    <span
      className="fsp-chip fsp-chip-lock"
      role="status"
      aria-label={ariaLabel}
      title={ariaLabel}
    >
      <span className="fsp-chip-lock-icon" aria-hidden="true">🔒</span>
      <span className="fsp-chip-lock-label">LOCK</span>
      <span className="fsp-chip-lock-rate">{rateStr}</span>
    </span>
  );
}

// Quality-trend sparkline (v2.2). Pure inline SVG; the parent component
// passes the batched quality_windows map and tier label. Three tiny dots
// connected by a line whose color reflects direction. Longest-window
// n_measured is gated server-side via TREND_MIN_N so single-alert tiers
// render as a muted unknown — never a misleading up/down on n=1.
function QualitySparkline({ tier, windows }) {
  const trend = qualityTrendForTier(tier, windows);
  const color = TREND_COLOR[trend.direction] || TREND_COLOR.unknown;
  const finite = trend.points.filter((p) => p.hr != null);
  // If only one window has data, a line is misleading — show a single dot.
  const dims = { width: 56, height: 14, padX: 2, padY: 4 };
  if (!finite.length) {
    return (
      <div className="fsp-conviction-qtrend" aria-label={`Calibration trend: unknown (${tier})`}>
        <svg width={dims.width} height={dims.height}>
          <line x1={dims.padX} y1={dims.height / 2} x2={dims.width - dims.padX} y2={dims.height / 2}
                stroke={TREND_COLOR.unknown} strokeWidth="1" strokeDasharray="2 2" />
        </svg>
        <span className="fsp-conviction-qtrend-label">—</span>
      </div>
    );
  }
  const xs = [dims.padX, dims.width / 2, dims.width - dims.padX];
  const ys = trend.points.map((p, i) => {
    const hr = p.hr == null ? null : Math.max(0, Math.min(1, p.hr));
    // Map 0–1 hit-rate to top (best) → bottom (worst) on the SVG.
    return hr == null ? dims.height / 2 : dims.padY + (1 - hr) * (dims.height - dims.padY * 2);
  });
  const path = finite.map((_, i) => {
    const x = xs[i], y = ys[i];
    return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const delta = trend.delta;
  const tipText = `Calibration trend: ${trend.direction}`
    + (delta != null ? ` (Δ ${(delta * 100).toFixed(1)} percentage points)` : "")
    + (trend.thin ? " · underpowered" : "");
  return (
    <div className="fsp-conviction-qtrend" aria-label={tipText} title={tipText}>
      <svg width={dims.width} height={dims.height} aria-hidden="true">
        <path d={path} stroke={color} strokeWidth="1.5" fill="none" />
        {trend.points.map((p, i) => (
          <circle key={i} cx={xs[i]} cy={ys[i]} r="1.6"
                  fill={p.hr != null ? color : TREND_COLOR.unknown} />
        ))}
      </svg>
      <span className="fsp-conviction-qtrend-label"
            style={{ color }}>{trend.direction === "unknown" ? "—" : trend.direction}</span>
    </div>
  );
}

// Daily sparkline (v2.5). Pure inline SVG, one dot per trading-day cell,
// and a polyline that breaks at calendar gaps. Color reflects the LAST
// measured day's direction relative to the FIRST measured day's rate —
// "up", "down", "flat" — when at least 2 measured days exist and the
// n_measured sum is above the per-day threshold. The trend label sits to
// the right of the SVG so a desk can scan whether today's calibration
// is hotter or colder than yesterday's WITHOUT reading the line itself.
//
// A missing day in the payload is information — the polyline stops at
// the previous dot and starts again at the next dot. We do NOT
// backfill zeros; doing so would render a day that produced no alerts
// as a 0% loss, which a desk would read as the tier "failing" when
// in fact there was simply nothing to measure.
//
// DailySparkline is intentionally distinct from QualitySparkline: the
// latter reads the 7/14/30 window endpoints (cheap, sparse), the former
// reads actual day-by-day data (richer, expose the "fade"). When both
// are present the desk sees a directional pair — endpoints vs. raw
// trajectory — and can spot a calculation window that disagrees with
// the day's actual behavior.
//
// Null handling post-v2.5.1: a point with `hit_rate === null` is rendered
// as a small hollow dot (not a 0% marker) so the desk reads it as
// "observation gap" rather than "0% loss". Slots where the SQL row had
// `n_measured === 0` (e.g. restart-skipped move-update) likewise render
// muted per the DAILY_MIN_N contract — never as a 100% win, never as a
// 0% loss, always as a neutral observation gap.
function DailySparkline({ tier, daily, days }) {
  const series = dailySeriesForTier(tier || "GOLD", daily, { maxPoints: 30 });
  const dims = { width: 84, height: 22, padX: 2, padY: 4 };
  const dayCount = Number(days) || 30;
  if (!series.has_data) {
    return (
      <div className="fsp-conviction-dtrend"
           aria-label={`Daily calibration sparkline: no data (${tier})`}
           title={`No measured alerts in last ${dayCount}d for ${tier}`}>
        <svg width={dims.width} height={dims.height}>
          <line x1={dims.padX} y1={dims.height / 2}
                x2={dims.width - dims.padX} y2={dims.height / 2}
                stroke={TREND_COLOR.unknown} strokeWidth="1"
                strokeDasharray="2 2" />
        </svg>
        <span className="fsp-conviction-dtrend-label">—</span>
      </div>
    );
  }
  const pts = series.points;
  // Distribute dots evenly across the strip width — the visual encodes
  // RECENT (right) vs OLDER (left), not calendar position. A bursty
  // tier that fires Mon-Wed-Fri and dies the rest of the week shows as
  // a 3-point line, not 30 dashes.
  const n = pts.length;
  const xs = pts.map((_, i) => {
    if (n === 1) return dims.padX + (dims.width - 2 * dims.padX) / 2;
    return dims.padX + (i / (n - 1)) * (dims.width - 2 * dims.padX);
  });
  const yFor = (hr) => {
    if (hr == null) return dims.height / 2;            // gap = midway, muted
    const c = Math.max(0, Math.min(1, hr));
    return dims.padY + (1 - c) * (dims.height - dims.padY * 2);
  };
  // Heuristic: a tier is "fading" when the second-half mean < first-half mean
  // by >= 15 percentage points; "rising" when second-half > first-half by
  // >=15pp; otherwise "flat". Two-point tiers can't tell first-half from
  // second-half, so we use delta = last - first as the canonical read.
  let trend = "flat";
  const first = pts[0]?.hit_rate;
  const last = pts[pts.length - 1]?.hit_rate;
  if (first != null && last != null) {
    const delta = last - first;
    if (delta > 0.15) trend = "up";
    else if (delta < -0.15) trend = "down";
  }
  // The fade signal (down) gets a louder red so it doesn't get lost
  // against the noise of "down" as ordinary drift.
  const color = TREND_COLOR[trend] || TREND_COLOR.unknown;
  // Build a single path that breaks at gaps: each M starts a new segment
  // after the previous L. Missing days stay absent (no `L`).
  const segments = [];
  let current = null;
  for (let i = 0; i < n; i++) {
    const hr = pts[i].hit_rate;
    if (hr == null) {
      if (current) {
        segments.push(current.join(" "));
        current = null;
      }
      continue;
    }
    const cmd = current == null ? "M" : "L";
    current = current || [];
    current.push(`${cmd} ${xs[i].toFixed(1)} ${yFor(hr).toFixed(1)}`);
  }
  if (current) segments.push(current.join(" "));
  const fmtDate = (s) => {
    const m = s?.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return s || "";
    return `${m[2]}/${m[3]}`;                       // 2026-07-20 → 07/20
  };
  return (
    <div className="fsp-conviction-dtrend"
         aria-label={`${tier} daily calibration sparkline: last ${dayCount}d`}
         title={`${tier} daily hit-rate over ${dayCount}d · ${pts.length} measured days${series.gaps ? ` · ${series.gaps} gap(s)` : ""}`}>
      <svg width={dims.width} height={dims.height} aria-hidden="true">
        {segments.map((d, i) => (
          <path key={`dseg${i}`} d={d} stroke={color} strokeWidth="1.5" fill="none" />
        ))}
        {pts.map((p, i) => (
          <circle key={`dd${i}`} cx={xs[i]} cy={yFor(p.hit_rate)} r="1.4"
                  fill={p.hit_rate != null ? color : TREND_COLOR.unknown}
                  opacity={p.n_measured < DAILY_MIN_N ? 0.35 : 1} />
        ))}
        {/* Hover layer: one invisible rect per cell with a <title> for native
            tooltip on mouseover — avoids React state churn for a 30-point
            strip the desk glances at, not clicks. */}
        {pts.map((p, i) => (
          <rect key={`dh${i}`} x={xs[i] - 2}
                y={dims.padY}
                width={Math.max(dims.width / n, 4)}
                height={dims.height - dims.padY * 2}
                fill="transparent"
                pointerEvents="all">
            <title>
              {fmtDate(p.date)}
              {`: ${p.n_measured} alerts · ${p.hits != null ? p.hits : p.wins}/${p.n_measured} hit (`
              + `${p.hit_rate != null ? Math.round(p.hit_rate * 100) : "—"}%)`}
            </title>
          </rect>
        ))}
      </svg>
      <span className="fsp-conviction-dtrend-label" style={{ color }}>{trend === "flat" ? "→" : trend}</span>
    </div>
  );
}

function fmtStrike(v) {
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}
function fmtPremium(v) {
  const n = Number(v) || 0;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}k`;
  return `$${n.toFixed(0)}`;
}
function biasClass(a) {
  if (String(a.side || "").toUpperCase() === "STRATEGY") return "fsp-conviction-bias-strategy";
  const b = String(a.bias || "").toUpperCase();
  if (b === "BULLISH") return "fsp-conviction-bias-bull";
  if (b === "BEARISH") return "fsp-conviction-bias-bear";
  return "fsp-conviction-bias-flow";
}
function moveClass(mv, bias) {
  if (mv == null || bias == null) return "fsp-conviction-move-na";
  const m = Number(mv);
  if (Number.isNaN(m)) return "fsp-conviction-move-na";
  const s = String(bias).toUpperCase();
  // STRATEGY rows never claim a direction
  if (s === "STRATEGY") return "fsp-conviction-move-neutral";
  if (s === "BULLISH" && m >= 0.5) return "fsp-conviction-move-bull";
  if (s === "BEARISH" && m <= -0.5) return "fsp-conviction-move-bear";
  return "fsp-conviction-move-neutral";
}
