import React, { memo, useState } from "react";

/**
 * SkylitTickerBar — Top ticker tape with quick-select buttons + free-text
 * search. Receives `tickers` from App.js (fetched via /api/tickers) and
 * renders EVERY available ticker (trinity + default + popular = all 80) as
 * a scrollable row of buttons. Search is the fast path for deep cuts.
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
}) {
  // trinity (^SPX, SPY, QQQ) + default (17) + popular (up to 5000 from
  // /api/tickers/all) = every tradable name. Cap rendered buttons at 500 for
  // smooth scrolling; search box is the fast path for deep cuts.
  const RENDER_CAP = 500;
  const tickerList = (() => {
    const seen = new Set();
    const out = [];
    const push = (arr) => {
      if (!arr) return;
      for (const t of arr) {
        const k = t.toUpperCase();
        if (!seen.has(k)) { seen.add(k); out.push(k); }
      }
    };
    push(tickers?.trinity);
    push(tickers?.default);
    push(tickers?.popular);
    if (out.length === 0) {
      // Final fallback: hardcoded defaults when API hasn't loaded yet.
      for (const t of DEFAULT_TICKERS) { if (!seen.has(t)) { seen.add(t); out.push(t); } }
    }
    // Slice for render perf — the full list is still available via search.
    if (out.length > RENDER_CAP) return out.slice(0, RENDER_CAP);
    return out;
  })();

  const totalCount = (() => {
    const seen = new Set();
    for (const arr of [tickers?.trinity, tickers?.default, tickers?.popular]) {
      if (!arr) continue;
      for (const t of arr) { const k = t.toUpperCase(); seen.add(k); }
    }
    if (seen.size === 0) { for (const t of DEFAULT_TICKERS) seen.add(t); }
    return seen.size;
  })();
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
            {totalCount.toLocaleString()} tickers
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
