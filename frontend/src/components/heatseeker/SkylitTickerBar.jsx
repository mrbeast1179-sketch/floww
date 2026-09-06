import React, { memo, useState } from "react";

/**
 * SkylitTickerBar — Top ticker tape with quick-select buttons + free-text
 * search. Receives the full market universe from App.js (fetched via
 * /api/tickers/all) and renders all available tickers as a scrollable list.
 * Matches Zenith reference: scrollable row of ticker buttons.
 *
 * Renders the full universe (up to ~11k tickers) inside a scrollable row so
 * every market symbol is one click away. Search is the fast path for deep
 * cuts; the scrollable bar is the browse path. No caps — the browser handles
 * virtualization natively for a single row of buttons.
 */
const DEFAULT_TICKERS = [
  "SPY", "QQQ", "IWM", "DIA", "AAPL", "NVDA", "TSLA", "META",
  "AMZN", "MSFT", "AMD", "GOOGL", "RIVN", "RBLX", "HIMS",
  "IREN", "MU", "NOW", "OSCR", "PATH", "UPS", "ZETA", "SPXW",
];

export const TICKER_SETS = {
  default: DEFAULT_TICKERS,
  popular: ["SPY", "QQQ", "IWM", "DIA", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT"],
  tech: ["AAPL", "NVDA", "MSFT", "GOOGL", "META", "AMD", "TSLA"],
  etfs: ["SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "ARKK", "XLF", "XLE", "XLV"],
};

function SkylitTickerBar({
  activeTicker = "SPY",
  onTickerChange,
  tickers = null,
  allCount = 703,
  universe = null,
}) {
  // Use the full universe when provided; fall back to popular/default/hardcoded.
  const tickerList = universe && universe.length > 0
    ? universe
    : (tickers?.popular || tickers?.default || DEFAULT_TICKERS);
  const totalCount = tickerList.length || 0;
  const [query, setQuery] = useState("");

  const submitQuery = () => {
    const t = query.trim().toUpperCase().replace(/^\$/, "");
    if (t && onTickerChange) {
      onTickerChange(t);
      setQuery("");
    }
  };

  return (
    <div className="skylit-ticker-bar">
      <div className="skylit-ticker-scroll">
        <div className="skylit-ticker-inner">
          <span className="skylit-ticker-count">
            Market {totalCount.toLocaleString()} tickers
          </span>
          <span className="skylit-ticker-sep">|</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submitQuery(); }}
            placeholder="Search any ticker…"
            aria-label="Search any ticker"
            data-testid="skylit-ticker-search"
            className="skylit-ticker-search"
          />
          <button
            className="skylit-ticker-btn"
            onClick={submitQuery}
            title="Load ticker"
            data-testid="skylit-ticker-go"
          >
            Go
          </button>
          <span className="skylit-ticker-sep">|</span>
          {tickerList.map((t) => (
            <button
              key={t}
              className={`skylit-ticker-btn${t === activeTicker ? " active" : ""}`}
              onClick={() => onTickerChange && onTickerChange(t)}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default memo(SkylitTickerBar);
