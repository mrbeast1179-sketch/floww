import React, { useEffect, useState } from "react";
import { API } from "../config/api";
import "./MarketPanels.css";

export default function RussellPanel({ onPick }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(`${API}/pairs/scan?top_n=6&universe_size=60`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        if (!cancelled) setData(await res.json());
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    poll();
    const id = setInterval(poll, 60000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (loading) return <div className="pairs-loading">Scanning Russell 3000 for pairs…</div>;
  if (error) return <div className="pairs-error">Pairs scan error: {error}</div>;
  if (!data?.ok) return <div className="pairs-error">No pairs: {data?.error || "unknown"}</div>;

  const palette = [
    "var(--pos)", "var(--accent-2)", "var(--warn)", "var(--neg)", "#8b5cf6", "#ec4899",
  ];

  return (
    <div className="pairs-panel">
      <div className="pairs-header">
        <h2>Russell 3000 Stat-Arb Pairs</h2>
        <span className="pairs-meta">
          {data.universe_size} tickers scanned · {data.lookback_days} days lookback · {data.count} cointegrated pairs
        </span>
      </div>

      {data.count === 0 && (
        <div className="pairs-empty">No cointegrated pairs found this scan. Try again in a few minutes.</div>
      )}

      <table className="pairs-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Pair</th>
            <th>Corr</th>
            <th>Half-life</th>
            <th>ADF p-val</th>
            <th>Z-score</th>
            <th>A price</th>
            <th>B price</th>
            <th>Quality</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.pairs.map((p, i) => {
            const z = p.zscore ?? 0;
            const zColor = Math.abs(z) >= 1.5 ? "var(--neg)" : Math.abs(z) >= 0.8 ? "var(--warn)" : "var(--pos)";
            const zDir = z > 0 ? "A/B rich" : z < 0 ? "A/B cheap" : "fair";
            return (
              <tr key={p.pair} className="pairs-row">
                <td className="pairs-rank">{i + 1}</td>
                <td className="pairs-pair">
                  <span className="pairs-sym pairs-a">{p.symbol_a}</span>
                  <span className="pairs-slash">/</span>
                  <span className="pairs-sym pairs-b">{p.symbol_b}</span>
                </td>
                <td>{p.correlation?.toFixed(2)}</td>
                <td>{p.half_life_days?.toFixed(1)}d</td>
                <td>{p.adf_pvalue?.toFixed(4)}</td>
                <td style={{ color: zColor }}>{z.toFixed(2)} ({zDir})</td>
                <td className="mono">${p.price_a?.toFixed(2) ?? "—"}</td>
                <td className="mono">${p.price_b?.toFixed(2) ?? "—"}</td>
                <td>
                  <div className="pairs-bar-wrap">
                    <div className="pairs-bar" style={{ width: `${p.quality_score * 100}%`, background: palette[i % palette.length] }} />
                  </div>
                  <span className="pairs-q">{p.quality_score?.toFixed(2)}</span>
                </td>
                <td>
                  <button
                    className="pairs-pick"
                    onClick={() => onPick?.(p)}
                    title={`Pick ${p.symbol_a}/${p.symbol_b} pair`}
                  >
                    Pick
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="pairs-foot">
        Cointegration scan: ADF test on log price-ratio spread · Correlation &gt; 0.60 ·
        Half-life 3-60 days · Next scan 60s
      </div>
    </div>
  );
}
