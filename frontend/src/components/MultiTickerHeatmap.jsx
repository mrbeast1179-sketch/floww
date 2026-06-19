import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { fmt, TRINITY, DEFAULT_TICKERS } from "../lib/helpers";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

/**
 * Multi-Ticker Heatmap — Skylit reference style
 *
 * Rows = strike prices (descending), Columns = tickers
 * Each cell shows the Net GEX for that ticker at that strike.
 * Color scheme: teal = positive GEX, purple = negative GEX,
 * yellow+star = extreme values
 *
 * Matches reference image: columns are tickers (AMD, AMZN, GOOGL...),
 * rows are SPY strike prices, cells are colored by Net GEX value.
 */

function cellColor(v, maxAbs) {
  if (v === null || v === undefined || isNaN(v) || v === 0) {
    return { bg: "rgba(10, 15, 30, 0.95)", text: "#2a3550" };
  }
  const norm = Math.min(1, Math.abs(v) / maxAbs);
  const isNeg = v < 0;

  if (!isNeg) {
    if (norm > 0.70) return { bg: `rgba(253, 224, 71, 0.85)`, text: "#0a0e1a", star: true };
    if (norm > 0.45) return { bg: `rgba(45, 212, 191, 0.6)`, text: "#0a0e1a" };
    if (norm > 0.20) return { bg: `rgba(45, 212, 191, 0.3)`, text: "#a7f3d0" };
    return { bg: `rgba(22, 78, 99, 0.15)`, text: "#6ee7b7" };
  }
  if (norm > 0.70) return { bg: `rgba(168, 55, 230, 0.65)`, text: "#fce7fe" };
  if (norm > 0.45) return { bg: `rgba(168, 85, 247, 0.45)`, text: "#e9d5ff" };
  if (norm > 0.20) return { bg: `rgba(168, 85, 247, 0.25)`, text: "#d8b4fe" };
  return { bg: `rgba(88, 28, 135, 0.15)`, text: "#c4b5fd" };
}

function fmtCell(v) {
  if (v === null || v === undefined || isNaN(v) || v === 0) return "";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e6) return sign + (a / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return sign + (a / 1e3).toFixed(0) + "K";
  return sign + a.toFixed(0);
}

export default function MultiTickerHeatmap({ tickers }) {
  const [allData, setAllData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const selectedTickers = useMemo(() => {
    // Use popular tickers, max 20 for performance
    const list = (tickers?.popular || DEFAULT_TICKERS).slice(0, 20);
    // Always include SPY as primary
    if (!list.includes("SPY")) list.unshift("SPY");
    return [...new Set(list)];
  }, [tickers]);

  // Use SPY strikes as the reference strike list
  const refTicker = "SPY";

  useEffect(() => {
    let mounted = true;
    const fetchAll = async () => {
      setLoading(true);
      setError(null);
      try {
        const results = await Promise.allSettled(
          selectedTickers.map(t =>
            axios.get(`${API}/heatmap/${t}?expiries=3&mode=day`, { timeout: 15000 })
              .then(r => ({ ticker: t, data: r.data }))
          )
        );
        const newData = {};
        results.forEach(r => {
          if (r.status === "fulfilled") {
            newData[r.value.ticker] = r.value.data;
          }
        });
        if (mounted) {
          setAllData(newData);
          setLoading(false);
        }
      } catch (e) {
        if (mounted) { setError(e.message); setLoading(false); }
      }
    };
    fetchAll();
    const id = setInterval(fetchAll, 30000);
    return () => { mounted = false; clearInterval(id); };
  }, [selectedTickers.join(",")]);

  // Build unified strike list from reference ticker (SPY)
  const strikes = useMemo(() => {
    const ref = allData[refTicker];
    if (!ref?.strikes) return [];
    return ref.strikes
      .filter(s => s.strike != null)
      .sort((a, b) => b.strike - a.strike)
      .map(s => s.strike);
  }, [allData, refTicker]);

  // Current spot from reference ticker
  const spot = allData[refTicker]?.spot;

  // Find closest strike to spot
  const spotRowIdx = useMemo(() => {
    if (!spot || !strikes.length) return -1;
    let bestIdx = 0;
    let bestDist = Math.abs(strikes[0] - spot);
    for (let i = 1; i < strikes.length; i++) {
      const d = Math.abs(strikes[i] - spot);
      if (d < bestDist) { bestDist = d; bestIdx = i; }
    }
    return bestIdx;
  }, [strikes, spot]);

  // Compute max abs Net GEX across all tickers and strikes for color scaling
  const maxAbs = useMemo(() => {
    let m = 1;
    for (const t of selectedTickers) {
      const d = allData[t];
      if (!d?.strikes) continue;
      for (const s of d.strikes) {
        const v = Math.abs(s.gex || 0);
        if (v > m) m = v;
      }
    }
    return m;
  }, [allData, selectedTickers]);

  if (loading && Object.keys(allData).length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-slate-500 text-xs">Loading multi-ticker data…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-rose-400 text-xs">Error: {error}</span>
      </div>
    );
  }

  if (!strikes.length) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-slate-500 text-xs">No data available</span>
      </div>
    );
  }

  // Helper: get Net GEX for a ticker at a strike
  const getGex = (ticker, strike) => {
    const d = allData[ticker];
    if (!d?.strikes) return 0;
    const s = d.strikes.find(s2 => s2.strike === strike);
    return s ? (s.gex || 0) : 0;
  };

  return (
    <div className="multi-heatmap-container" data-testid="multi-ticker-heatmap">
      <table className="multi-heatmap-table">
        <tbody>
          {strikes.map((strike, i) => {
            const isCurrent = i === spotRowIdx;
            return (
              <tr key={strike} className={`multi-row ${isCurrent ? "multi-current-row" : ""}`}>
                {/* Price axis */}
                <td className={`multi-price-cell ${isCurrent ? "multi-current-price" : ""}`}>
                  {isCurrent && <span className="multi-triangle"/>}
                  {fmt(strike, strike >= 1000 ? 0 : 1)}
                </td>

                {/* Ticker columns */}
                {selectedTickers.map(t => {
                  const val = getGex(t, strike);
                  const cc = cellColor(val, maxAbs);
                  return (
                    <td
                      key={t}
                      className="multi-data-cell"
                      style={{ background: cc.bg, color: cc.text }}
                      title={`${t} @ ${strike}: Net GEX ${fmtCell(val)}`}
                    >
                      {fmtCell(val)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
