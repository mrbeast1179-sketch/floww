import React, { useEffect, useState } from "react";
import { BACKEND_URL } from "../../config/api";
import FlowTable from "./FlowTable";

const API = `${BACKEND_URL}/api/flowseeker`;

function fmtNum(v) {
  const n = Number(v) || 0;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return n.toFixed(0);
}

export default function FlowDrilldown({ symbol, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetch(`${API}/drilldown/${encodeURIComponent(symbol)}`, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (!cancelled) { setData(json); setError(null); }
      })
      .catch((e) => {
        if (e.name !== "AbortError" && !cancelled) setError(e.message || "Fetch failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; controller.abort(); };
  }, [symbol]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.7)" }}
      onClick={onClose}
    >
      <div
        className="panel p-4 max-w-4xl w-[90%] max-h-[80vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
        data-testid="flow-drilldown-modal"
      >
        {/* Header */}
        <div className="flex justify-between items-center mb-3">
          <div>
            <div className="label">Flow Drilldown</div>
            <div className="text-lg font-bold">{symbol}</div>
          </div>
          <button onClick={onClose} className="btn" data-testid="drilldown-close">
            close ✕
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div className="text-slate-500 text-[11px] animate-pulse">Loading drilldown…</div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="text-rose-400 text-[11px]">Error: {error}</div>
        )}

        {/* Data */}
        {data && !loading && (
          <div>
            {/* Stat row */}
            <div className="flex flex-wrap gap-4 mb-3 text-[11px]">
              <div>
                <span className="label">Volume</span>{" "}
                <span className="mono text-slate-300">{fmtNum(data.volume)}</span>
              </div>
              <div>
                <span className="label">OI</span>{" "}
                <span className="mono text-slate-300">{fmtNum(data.oi)}</span>
              </div>
              <div>
                <span className="label">Chain Ratio</span>{" "}
                <span className="mono text-slate-300">
                  {Number(data.chain_ratio || 0).toFixed(2)}
                </span>
              </div>
            </div>

            {/* Vol/OI sparkline */}
            {data.vol_oi_history && data.vol_oi_history.length > 0 && (
              <div className="mb-3">
                <div className="label mb-1 text-[10px]">Vol/OI History</div>
                <svg width="200" height="40" className="rounded">
                  {(() => {
                    const vals = data.vol_oi_history.filter((v) => !isNaN(Number(v)));
                    if (vals.length < 2) return null;
                    const max = Math.max(...vals, 1);
                    const min = Math.min(...vals, 0);
                    const range = max - min || 1;
                    const w = 200;
                    const h = 40;
                    const pad = 2;
                    const points = vals
                      .map(
                        (v, i) =>
                          `${(i / (vals.length - 1)) * (w - pad * 2) + pad},${
                            h - pad - ((v - min) / range) * (h - pad * 2)
                          }`
                      )
                      .join(" ");
                    return (
                      <polyline
                        points={points}
                        fill="none"
                        stroke="#38bdf8"
                        strokeWidth="1.5"
                      />
                    );
                  })()}
                </svg>
              </div>
            )}

            {/* Recent prints */}
            <div>
              <div className="label mb-1">Recent Prints</div>
              {data.recent_prints && data.recent_prints.length > 0 ? (
                <FlowTable
                  prints={data.recent_prints}
                  loading={false}
                  error={null}
                  onSelect={() => {}}
                />
              ) : (
                <div className="text-slate-500 text-[11px]">No recent prints.</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
