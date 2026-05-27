import React, { useState, useEffect } from "react";
import { fmt, pctClass } from "../lib/helpers";
import { BACKEND_URL, API } from "../config/api";

// API imported from config/api.js

export function SocialFlowPanel({ ticker }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ticker) return;
    const ctrl = new AbortController();
    setLoading(true);
    fetch(`${API}/social/report/${ticker}`, { signal: ctrl.signal })
      .then(r => r.json())
      .then(d => {
        setReport(d.cached ? d : null);
        setError(null);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [ticker]);

  if (loading) return <div className="panel p-3 text-slate-500 text-xs">Loading social flow data…</div>;
  if (error) return <div className="panel p-3 text-rose-400 text-xs">Error: {error}</div>;

  return (
    <div className="panel p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="label mb-0">Social & Flow Intelligence</div>
        {report?.generated_at && (
          <div className="text-[8px] text-slate-600">
            {new Date(report.generated_at).toLocaleTimeString()}
          </div>
        )}
      </div>

      {!report ? (
        <div className="text-[10px] text-slate-500">
          No social flow data available. Run the data pipeline to collect Twitter sentiment and options flow signals.
        </div>
      ) : (
        <>
          {/* Combined Score */}
          <div className="flex items-center gap-3">
            <div className="flex-1 text-center">
              <div className="label">Combined Score</div>
              <div className={`text-lg mono font-bold ${getScoreColor(report.combined_score)}`}>
                {formatScore(report.combined_score)}
              </div>
            </div>
            <div className="flex-1 text-center">
              <div className="label">Social</div>
              <div className={`text-lg mono font-bold ${getScoreColor(report.social_score)}`}>
                {formatScore(report.social_score)}
              </div>
            </div>
            <div className="flex-1 text-center">
              <div className="label">Flow</div>
              <div className={`text-lg mono font-bold ${getScoreColor(report.flow_score)}`}>
                {formatScore(report.flow_score)}
              </div>
            </div>
          </div>

          {/* Sentiment */}
          {report.sentiment && (
            <div>
              <div className="label mb-1">Twitter Sentiment</div>
              <div className="grid grid-cols-3 gap-2 text-center text-[10px]">
                <div>
                  <div className="text-slate-500">Tweets</div>
                  <div className="mono text-slate-200">{report.sentiment.tweet_count}</div>
                </div>
                <div>
                  <div className="text-slate-500">Bullish</div>
                  <div className="mono text-emerald-400">{report.sentiment.bullish_count}</div>
                </div>
                <div>
                  <div className="text-slate-500">Bearish</div>
                  <div className="mono text-rose-400">{report.sentiment.bearish_count}</div>
                </div>
              </div>
              <div className="mt-1 flex items-center gap-1">
                <span className={`text-[10px] font-bold ${report.sentiment.sentiment_label === "bullish" ? "text-emerald-400" : report.sentiment.sentiment_label === "bearish" ? "text-rose-400" : "text-slate-400"}`}>
                  {report.sentiment.sentiment_label.toUpperCase()}
                </span>
                <span className="text-[9px] text-slate-600">
                  (confidence: {(report.sentiment.confidence * 100).toFixed(0)}%)
                </span>
              </div>
            </div>
          )}

          {/* Flow Signals */}
          {report.flow_signals && report.flow_signals.length > 0 && (
            <div>
              <div className="label mb-1">Flow Signals ({report.flow_signals.length})</div>
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {report.flow_signals.slice(0, 10).map((signal, i) => (
                  <div key={i} className="bg-slate-800/40 rounded px-2 py-1 text-[9px] flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span className={signal.option_type === "call" ? "text-teal-400" : "text-purple-400"}>
                        {signal.option_type.toUpperCase()}
                      </span>
                      <span className="mono">{signal.strike}</span>
                      <span className="text-slate-500">{signal.expiry}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500">Vol: {signal.volume}</span>
                      <span className="mono text-amber-400">
                        ${fmt(signal.premium_usd / 1000, 0)}K
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* GEX Summary */}
          {report.gex_summary && (
            <div>
              <div className="label mb-1">GEX Summary</div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Net GEX</span>
                  <span className={`mono ${report.gex_summary.net_gex >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    ${fmt(report.gex_summary.net_gex / 1e9, 1)}B
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Vanna Exp</span>
                  <span className="mono text-slate-200">
                    ${fmt(report.gex_summary.total_vanna_exposure / 1e9, 1)}B
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Gamma Flip</span>
                  <span className="mono text-amber-400">
                    {report.gex_summary.gamma_flip ? fmt(report.gex_summary.gamma_flip, 0) : "—"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">GEX Ratio</span>
                  <span className="mono text-slate-200">
                    {report.gex_summary.gex_ratio ? report.gex_summary.gex_ratio.toFixed(2) : "—"}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Signals */}
          {report.signals && report.signals.length > 0 && (
            <div>
              <div className="label mb-1">Signals</div>
              <div className="space-y-0.5">
                {report.signals.map((signal, i) => (
                  <div key={i} className="text-[9px] text-slate-300">
                    {signal}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function formatScore(score) {
  if (score === undefined || score === null) return "—";
  const pct = (score * 100).toFixed(0);
  return score >= 0 ? `+${pct}%` : `${pct}%`;
}

function getScoreColor(score) {
  if (score === undefined || score === null) return "text-slate-400";
  if (score > 0.2) return "text-emerald-400";
  if (score < -0.2) return "text-rose-400";
  return "text-amber-400";
}
