import React, { memo, useCallback, useState } from "react";
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

/**
 * SkylitDashboard — Full Skylit-style trading dashboard
 *
 * Layout:
 *   1. TickerBar (top ticker tape)
 *   2. ControlBar (GEX/VEX, price, timeframe)
 *   3. Main area: HeatmapGrid + MetricsSidebar
 *
 * Matches Skylit reference from screenshots:
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
      />

      {/* 2.5 Trade Mode bar */}
      <div className="skylit-col-bar">
        <div className="skylit-col-spacer" />
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

      {/* 3.5 Confluence & Velocity — bottom band of steal-list signals */}
      {/* Mirrors HeatseekerDashboard Row 3 so the steal-list top-3 appear on
          BOTH the default Heatseeker page (this component) AND the
          Sidebar→Skylit page (HeatseekerDashboard legacy layout). */}
      <div className="px-3 py-3 space-y-3 border-t border-slate-800/40" data-testid="skylit-steal-list-band">
        <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">
          ◆ Confluence & Velocity · #1 Dual-GEX · #5 IV-Mid · #3 Wheel income
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <DualGEXBadge ticker={ticker} />
          <IVMidBadge ticker={ticker} width={6} />
          <MaxPainBadge ticker={ticker} />
        </div>
        <WheelIncomeScreenerPanel ticker={ticker} />
        {/* NEW: Per-expiry max-pain-drift multi-line chart — full-width
            beneath the Wheel panel so the multi-line visualization gets
            the horizontal real estate it needs. Standalone fetch via
            /api/max_pain_drift/{ticker}/per_expiry_history. */}
        <MaxPainPerExpiryDriftTile ticker={ticker} />
      </div>

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
