import React, { memo, useCallback } from "react";
import SkylitTickerBar from "./SkylitTickerBar";
import SkylitControlBar from "./SkylitControlBar";
import SkylitHeatmapGrid from "./SkylitHeatmapGrid";
import SkylitMetricsSidebar from "./SkylitMetricsSidebar";

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
  const [visibleCols, setVisibleCols] = useState(["call_gex", "gex", "put_gex"]);
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

  // Column toggle options
  const colGroups = [
    { label: "GEX", cols: ["call_gex", "gex", "put_gex"] },
    { label: "OI", cols: ["call_oi", "put_oi", "total_oi"] },
    { label: "VEX", cols: ["vex"] },
    { label: "Vega", cols: ["vega", "vomma", "zomma"] },
    { label: "Charm", cols: ["charm"] },
  ];

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

      {/* 2.5 Column Toggle Bar + Trade Mode */}
      <div className="skylit-col-bar">
        <div className="skylit-col-group">
          {colGroups.map(g => (
            <button
              key={g.label}
              className={`skylit-col-btn${visibleCols.some(c => g.cols.includes(c)) ? " active" : ""}`}
              onClick={() => {
                const allVisible = g.cols.every(c => visibleCols.includes(c));
                if (allVisible) {
                  setVisibleCols(prev => prev.filter(c => !g.cols.includes(c)));
                } else {
                  setVisibleCols(prev => [...new Set([...prev, ...g.cols])]);
                }
              }}
            >
              {g.label}
            </button>
          ))}
        </div>
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
            viewMode={viewMode}
            visibleColumns={visibleCols}
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
