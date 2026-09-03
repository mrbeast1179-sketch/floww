import React, { memo, useCallback, useEffect, useState } from "react";
import SkylitTickerBar from "./SkylitTickerBar";
import SkylitControlBar from "./SkylitControlBar";
import SkylitHeatmapGrid from "./SkylitHeatmapGrid";
import SkylitMetricsSidebar from "./SkylitMetricsSidebar";
// Steal-list top-3 (served by backend/routes/steal_three.py at :8000).
import DualGEXBadge from "./DualGEXBadge";
import IVMidBadge from "./IVMidBadge";
import WheelIncomeScreenerPanel from "./WheelIncomeScreenerPanel";
import MaxPainBadge from "./MaxPainBadge";
// Per-expiry max-pain-drift multi-line chart tile (steal-list #9 rich
// visualization — surfaced via /api/max_pain_drift/{ticker}/per_expiry_history).
import MaxPainPerExpiryDriftTile from "./MaxPainPerExpiryDriftTile";
// NEW (2026-07-16): steal-list #10 (strike cone) + #8 (opportunity
// engine) — surfaced into the skylit bottom band so the steal-three
// is visible without scrolling to Solstice Row 4. Pairs with the
// existing Dual-GEX / IV-Mid / Wheel-Income / Max-Pain mounts already
// in the skylit-steal-list-band container below.
import StrikeConeBadge from "./StrikeConeBadge";
import OpportunityBadge from "./OpportunityBadge";
// Steal-list news/pulse — Row 3.5 tile on Zenith's bottom band,
// mirrors the Solstice Dashboard top-3 pattern so users see the
// same signals on either layout.
import NewsBadge from "./NewsBadge";
// Steal-list #4 — Risk-Neutral Density full-width tile beneath the
// strike-cone / opportunity band so the PDF + CDF SVG gets horizontal
// real estate. (Mirrors Solstice Row 4b mount.)
import RndDensityPanel from "./RndDensityPanel";

/**
 * SkylitDashboard — Full Zenith-style trading dashboard
 *
 * Layout:
 *   1. TickerBar (top ticker tape)
 *   2. ControlBar (GEX/VEX, price, timeframe)
 *   3. Main area: HeatmapGrid + MetricsSidebar
 *
 * Matches Zenith reference from screenshots:
 * - Dark background (#0a0e1a)
 * - Ticker buttons at top
 * - GEX/VEX toggle + LIVE badge
 * - Strike price column on left
 * - Color-coded heatmap cells
 * - Current price row highlighted
 * - POC (highest value) with yellow + star
 * - Right sidebar with KING, |GEX|, TOP FLOOR, etc.
 */

function SkylitDashboard({
  ticker = "SPY",
  spot = null,
  change = null,
  changePct = null,
  data = null,
  viewMode = "gex",
  dte = null,
  onViewModeChange,
  timeframe = "5m",
  onTimeframeChange,
  expiries = 4,
  onExpiriesChange,
  onTickerChange,
  onRefresh,
  onCellClick,
  onStrikeClick,
  isLive = false,
  regime = null,
  loading = false,
}) {
  const [tradeMode, setTradeMode] = useState(false);
  const [selectedCell, setSelectedCell] = useState(null);
  // Bottom signal boxes are out of the way by default (2026-09-03) —
  // toggle to reveal the Meridian & Velocity band.
  const [showSignals, setShowSignals] = useState(false);
  // Full-page grid overlay: the in-frame heatmap only shows what fits;
  // expand renders the same grid + sidebar full-screen with all rows.
  const [expanded, setExpanded] = useState(false);

  // Esc closes the expanded grid (local to this component).
  useEffect(() => {
    if (!expanded) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setExpanded(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  const handleCellClick = useCallback(
    (strike, colKey, value) => {
      if (tradeMode && onCellClick) {
        onCellClick(strike, colKey, value);
      } else {
        setSelectedCell({ strike, colKey, value });
      }
    },
    [tradeMode, onCellClick]
  );

  const handleStrikeClick = useCallback(
    (strike) => {
      if (onStrikeClick) onStrikeClick(strike);
    },
    [onStrikeClick]
  );

  return (
    <div className="skylit-full-dashboard">
      {/* 1. Top Ticker Bar */}
      <SkylitTickerBar
        activeTicker={ticker}
        onTickerChange={onTickerChange}
        allCount={703}
      />

      {/* 2. Control Bar */}
      <SkylitControlBar
        ticker={ticker}
        spot={spot}
        change={change}
        changePct={changePct}
        viewMode={viewMode}
        onViewModeChange={onViewModeChange}
        timeframe={timeframe}
        onTimeframeChange={onTimeframeChange}
        expiries={expiries}
        onExpiriesChange={onExpiriesChange}
        isLive={isLive}
        onRefresh={onRefresh}
        onExpand={() => setExpanded(true)}
      />

      {/* 2.5 Trade Mode bar */}
      <div className="skylit-col-bar">
        <div className="skylit-col-spacer" />
        <button
          className="skylit-trade-mode-btn"
          onClick={() => setExpanded(true)}
          title="Expand grid full-screen (Esc to close)"
          data-testid="skylit-expand-btn"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 3h6v6" /><path d="M9 21H3v-6" />
            <path d="M21 3l-7 7" /><path d="M3 21l7-7" />
          </svg>
          Expand
        </button>
        <button
          className={`skylit-trade-mode-btn${showSignals ? " active" : ""}`}
          onClick={() => setShowSignals(!showSignals)}
          title="Signals: show Meridian & Velocity panels"
          data-testid="skylit-signals-toggle"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
          Signals
        </button>
        <button
          className={`skylit-trade-mode-btn${tradeMode ? " active" : ""}`}
          onClick={() => setTradeMode(!tradeMode)}
          title="Trade Mode: click any cell to open Quick Trade"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
          Trade
        </button>
      </div>

      {/* 3. Main Content Area */}
      <div className="skylit-main-area">
        {/* Heatmap Grid */}
        <div className="skylit-heatmap-area">
          {loading && (
            <div className="skylit-loading-overlay">
              <div className="skylit-loading-spinner" />
              <span>Loading market data…</span>
            </div>
          )}
          {!loading && data && (!data.strikes || data.strikes.length === 0) && (
            <div style={{
              padding: "24px", textAlign: "center", color: "var(--text-secondary, #94a3b8)",
              border: "1px dashed rgba(148,163,184,0.3)", borderRadius: 8, margin: "12px",
            }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                No strikes match the current filters
              </div>
              <div style={{ fontSize: 12 }}>
                {dte != null
                  ? `No listed expiries within ${dte} DTE right now (weekends/holidays). `
                  : ""}
                Try: DTE → All, or Expiries → 4+.
              </div>
            </div>
          )}
          <SkylitHeatmapGrid
            data={data}
            spot={spot}
            ticker={ticker}
            viewMode={viewMode}
            onCellClick={handleCellClick}
            onStrikeClick={handleStrikeClick}
          />
        </div>

        {/* Metrics Sidebar */}
        <div className="skylit-sidebar-area">
          <SkylitMetricsSidebar
            data={data}
            spot={spot}
            viewMode={viewMode}
            regime={regime}
          />
        </div>
      </div>

      {/* 3.5 Meridian & Velocity — behind the Signals toggle (2026-09-03).
          The boxes are out of the main scroll by default; toggle reveals
          the full band. Testids preserved for visual-regression targeting. */}
      {showSignals && (
      <div className="px-3 py-3 space-y-3 border-t border-slate-800/40" data-testid="skylit-steal-list-band">
        <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">
          ◆ Meridian & Velocity · #1 Dual-GEX · #5 IV-Mid · #3 Wheel income
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div data-testid="skylit-steal-dual-gex">
            <DualGEXBadge ticker={ticker} />
          </div>
          <div data-testid="skylit-steal-iv-mid">
            <IVMidBadge ticker={ticker} width={6} />
          </div>
          <div data-testid="skylit-steal-max-pain">
            <MaxPainBadge ticker={ticker} />
          </div>
        </div>
        <div data-testid="skylit-steal-wheel-income">
          <WheelIncomeScreenerPanel ticker={ticker} />
          {/* NEW (2026-07-16): steal-list #10 strike cone + #8 opportunity
              engine — surface classic 16Δ/30Δ cone shape + regime pills
              in the skylit bottom band. Marked with the skylit-steal-<feature>
              wrappers per the test's standardized visual-regression
              convention so downstream visual verifications can locate the
              tile by semantic purpose (strike-cone / opportunity) instead
              of relying on component-internal ids that may shift. */}
          <div data-testid="skylit-steal-strike-cone">
            <StrikeConeBadge ticker={ticker} expiries={1} />
          </div>
          <div data-testid="skylit-steal-opportunity">
            <OpportunityBadge ticker={ticker} />
          </div>
        </div>
        {/* NEW: Per-expiry max-pain-drift multi-line chart — full-width
            beneath the Wheel panel so the multi-line visualization gets
            the horizontal real estate it needs. Standalone fetch via
            /api/max_pain_drift/{ticker}/per_expiry_history. */}
        <div data-testid="skylit-steal-max-pain-per-expiry-drift">
          <MaxPainPerExpiryDriftTile ticker={ticker} />
        </div>

        {/* NEW (2026-07-16): News pulse + Risk-Neutral Density — extend
            the Zenith bottom band to mirror the Solstice Dashboard
            Row 4 (news) + Row 4b (RND full-width). The Zenith layout
            keeps the existing max-pain-drift multi-line chart at the
            top and appends these two tiles below it so the
            visualisation cadence matches the Solstice iteration:
            analytics → flow → expected-moves → RND. */}
        <div className="pt-1" data-testid="skylit-steal-news-band">
          <NewsBadge ticker={ticker} days={14} />
        </div>
        <div data-testid="skylit-steal-rnd-density">
          <RndDensityPanel ticker={ticker} expiries={1} />
        </div>
      </div>
      )}

      {/* 3.6 Expanded full-page grid overlay (2026-09-03). Same grid +
          sidebar, full viewport, all rows visible. Esc or ✕ closes. */}
      {expanded && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 50, background: "#0a0e1a", overflow: "auto", padding: 16 }}
          data-testid="skylit-grid-expanded"
          role="dialog"
          aria-label="Expanded heatmap grid"
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div style={{ fontWeight: 700 }}>
              {ticker} · full grid <span style={{ color: "#94a3b8", fontWeight: 400 }}>(Esc to close)</span>
            </div>
            <button
              className="skylit-trade-mode-btn"
              onClick={() => setExpanded(false)}
              data-testid="skylit-expand-close"
            >
              ✕ Close
            </button>
          </div>
          <div style={{ display: "flex", gap: 16 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <SkylitHeatmapGrid
                data={data}
                spot={spot}
                ticker={ticker}
                viewMode={viewMode}
                onCellClick={handleCellClick}
                onStrikeClick={handleStrikeClick}
              />
            </div>
            <div style={{ width: 280, flexShrink: 0 }}>
              <SkylitMetricsSidebar
                data={data}
                spot={spot}
                viewMode={viewMode}
                regime={regime}
              />
            </div>
          </div>
        </div>
      )}

      {/* 4. Bottom Ticker Info Bar */}
      <div className="skylit-bottom-bar">
        <div className="skylit-bottom-ticker">
          <span className="skylit-bottom-ticker-name">{ticker}</span>
          <span className="skylit-bottom-spot">
            ${spot != null ? Number(spot).toFixed(2) : "—"}
          </span>
          {changePct != null && (
            <span
              className="skylit-bottom-change"
              style={{ color: changePct >= 0 ? "#34d399" : "#f87171" }}
            >
              {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
            </span>
          )}
        </div>
        <div className="skylit-bottom-tabs">
          <button
            className={`skylit-bottom-tab${viewMode === "gex" ? " active" : ""}`}
            onClick={() => onViewModeChange && onViewModeChange("gex")}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
            GEX
          </button>
          <button
            className={`skylit-bottom-tab${viewMode === "vex" ? " active" : ""}`}
            onClick={() => onViewModeChange && onViewModeChange("vex")}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
            VEX
          </button>
        </div>
      </div>
    </div>
  );
}

export default memo(SkylitDashboard);
