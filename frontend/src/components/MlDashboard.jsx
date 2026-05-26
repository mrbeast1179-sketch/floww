/**
 * MlDashboard.jsx — ML Prediction Dashboard
 *
 * Shows live ML predictions, model health, rolling accuracy,
 drift status, and prediction history. Uses the unified /api/ml/briefing endpoint.
 */
import React, { useState, useEffect, useCallback } from "react";
import { BACKEND_URL, API } from "../config/api";

// API imported from config/api.js

function SignalBadge({ signal, confidence }) {
  const colorMap = {
    STRONG_BULLISH: "bg-emerald-500/20 border-emerald-500 text-emerald-400",
    BULLISH: "bg-emerald-500/10 border-emerald-500/50 text-emerald-300",
    NEUTRAL: "bg-slate-700/50 border-slate-600 text-slate-400",
    BEARISH: "bg-rose-500/10 border-rose-500/50 text-rose-300",
    STRONG_BEARISH: "bg-rose-500/20 border-rose-500 text-rose-400",
  };
  const color = colorMap[signal] || colorMap.NEUTRAL;
  return (
    <span className={`inline-block px-2 py-0.5 rounded border text-[10px] font-bold tracking-wider ${color}`}>
      {signal?.replace("_", " ") ?? "—"}
      {confidence != null && <span className="ml-1 opacity-70">{(confidence * 100).toFixed(0)}%</span>}
    </span>
  );
}

function ConfidenceBar({ value, label, color = "emerald" }) {
  const pct = Math.min(100, Math.max(0, (value || 0) * 100));
  const barColor = color === "emerald" ? "bg-emerald-500" : color === "rose" ? "bg-rose-500" : "bg-amber-500";
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="text-slate-500 w-8 text-right">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-slate-400 w-10 text-right">{(value || 0).toFixed(2)}</span>
    </div>
  );
}

function FeatureChart({ features }) {
  if (!features || Object.keys(features).length === 0) {
    return <div className="text-[10px] text-slate-500 py-2">No feature data</div>;
  }
  const sorted = Object.entries(features).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 8);
  const maxVal = Math.max(...sorted.map(([, v]) => Math.abs(v)));
  return (
    <div className="space-y-1">
      {sorted.map(([name, val]) => {
        const pct = maxVal > 0 ? (Math.abs(val) / maxVal) * 100 : 0;
        return (
          <div key={name} className="flex items-center gap-2 text-[9px]">
            <span className="text-slate-500 w-24 truncate text-right" title={name}>{name}</span>
            <div className="flex-1 h-1 bg-slate-800 rounded-full overflow-hidden">
              <div className="h-full bg-sky-500/70 rounded-full" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-slate-400 w-12 text-right">{val.toFixed(4)}</span>
          </div>
        );
      })}
    </div>
  );
}

export function MlDashboard({ ticker = "SPY", spot }) {
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const [training, setTraining] = useState(false);
  const [activeTab, setActiveTab] = useState("predict");

  const fetchPrediction = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API}/ml/briefing/${ticker}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setPrediction(data);
      setHistory(prev => [data, ...prev.filter(p => !(p.ticker === data.ticker && p.ts === data.ts))].slice(0, 20));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  const triggerTraining = useCallback(async () => {
    setTraining(true);
    try {
      await fetch(`${API}/ml/retrain/${ticker}`, { method: "POST" });
      setTimeout(fetchPrediction, 3000);
    } catch (e) {
      setError(e.message);
    } finally {
      setTraining(false);
    }
  }, [ticker, fetchPrediction]);

  useEffect(() => {
    fetchPrediction();
    const id = setInterval(fetchPrediction, 60000);
    return () => clearInterval(id);
  }, [fetchPrediction]);

  const predSignal = prediction?.combined_signal || prediction?.prediction_label?.toUpperCase();
  const predConf = prediction?.combined_confidence || prediction?.confidence;
  const probs = prediction?.probabilities || {};
  const features = prediction?.feature_values || {};

  return (
    <div className="panel-2 p-2 space-y-2">
      <div className="flex items-center justify-between">
        <div className="label mb-0">ML</div>
        <div className="flex items-center gap-1.5">
          {loading && <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />}
          {predSignal && <SignalBadge signal={predSignal} confidence={predConf} />}
          <button onClick={fetchPrediction} disabled={loading}
            className="text-[8px] px-1 py-px rounded bg-slate-800 text-slate-500 hover:text-slate-300 border border-slate-700 disabled:opacity-50">
            ↻
          </button>
        </div>
      </div>

      {error && (
        <div className="text-[9px] text-amber-400/70 bg-amber-500/5 rounded px-1.5 py-0.5 border border-amber-500/20">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-0.5 text-[8px]">
        {["predict", "model", "history"].map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={`px-1.5 py-px rounded border ${activeTab === tab ? "bg-slate-700 border-slate-600 text-slate-200" : "bg-slate-800/50 border-slate-800 text-slate-500 hover:text-slate-400"}`}>
            {tab === "predict" ? "Signal" : tab === "model" ? "Model" : "History"}
          </button>
        ))}
      </div>

      {/* Predict Tab */}
      {activeTab === "predict" && (
        <div className="space-y-2">
          {prediction ? (
            <>
              <div className="bg-slate-800/50 rounded p-2 border border-slate-700/50 text-center">
                <div className={`text-sm font-bold ${predSignal?.includes("BULL") ? "text-emerald-400" : predSignal?.includes("BEAR") ? "text-rose-400" : "text-slate-400"}`}>
                  {predSignal?.replace("_", " ") ?? "—"}
                </div>
                <div className="flex items-center justify-center gap-2 mt-1.5">
                  <ConfidenceBar value={probs.bearish ?? (1 - (predConf || 0))} label="DOWN" color="rose" />
                  <ConfidenceBar value={probs.bullish ?? (predConf || 0)} label="UP" color="emerald" />
                </div>
              </div>
              {Object.keys(features).length > 0 && (
                <div>
                  <div className="label mb-0.5">Features</div>
                  <FeatureChart features={features} />
                </div>
              )}
            </>
          ) : (
            <div className="text-center text-[10px] text-slate-500 py-3">
              {loading ? "Loading…" : "No prediction"}
            </div>
          )}
        </div>
      )}

      {/* Model Tab */}
      {activeTab === "model" && (
        <div className="space-y-1.5">
          {prediction ? (
            <>
              <div className="grid grid-cols-2 gap-1 text-[9px]">
                <div className="bg-slate-800/50 rounded p-1.5">
                  <div className="label mb-0">Type</div>
                  <div className="text-slate-200 mono">{prediction.model_type || "—"}</div>
                </div>
                <div className="bg-slate-800/50 rounded p-1.5">
                  <div className="label mb-0">Features</div>
                  <div className="text-slate-200 mono">{prediction.n_features || "—"}</div>
                </div>
                <div className="bg-slate-800/50 rounded p-1.5">
                  <div className="label mb-0">Train Acc</div>
                  <div className="text-slate-200 mono">{prediction.train_accuracy?.toFixed(4) || "—"}</div>
                </div>
                <div className="bg-slate-800/50 rounded p-1.5">
                  <div className="label mb-0">Drift</div>
                  <div className={`mono ${prediction.drift_status === "drift_detected" ? "text-amber-400" : "text-emerald-400"}`}>
                    {prediction.drift_status || "—"}
                  </div>
                </div>
              </div>
              {(prediction.rolling_7d_accuracy != null || prediction.rolling_30d_accuracy != null) && (
                <div>
                  <div className="label mb-0.5">Rolling Accuracy</div>
                  <div className="grid grid-cols-2 gap-1 text-[9px]">
                    <div className="bg-slate-800/50 rounded p-1.5">
                      <div className="text-slate-500">7d</div>
                      <div className="text-slate-200 mono">
                        {prediction.rolling_7d_accuracy != null ? `${(prediction.rolling_7d_accuracy * 100).toFixed(1)}%` : "—"}
                        <span className="text-slate-600 ml-1">({prediction.rolling_7d_n || 0})</span>
                      </div>
                    </div>
                    <div className="bg-slate-800/50 rounded p-1.5">
                      <div className="text-slate-500">30d</div>
                      <div className="text-slate-200 mono">
                        {prediction.rolling_30d_accuracy != null ? `${(prediction.rolling_30d_accuracy * 100).toFixed(1)}%` : "—"}
                        <span className="text-slate-600 ml-1">({prediction.rolling_30d_n || 0})</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-[10px] text-slate-500 text-center py-3">No model info</div>
          )}
          <button onClick={triggerTraining} disabled={training}
            className="w-full text-[10px] py-1 rounded bg-slate-800 border border-slate-700 text-slate-400 hover:text-slate-200 disabled:opacity-50">
            {training ? "Training…" : "↻ Retrain"}
          </button>
        </div>
      )}

      {/* History Tab */}
      {activeTab === "history" && (
        <div className="space-y-0.5 max-h-32 overflow-y-auto">
          {history.length > 0 ? history.map((h, i) => (
            <div key={i} className="flex items-center justify-between py-0.5 border-b border-slate-800/50 text-[9px]">
              <span className="text-slate-500">{h.ticker}</span>
              <SignalBadge signal={h.combined_signal || h.prediction_label?.toUpperCase()} confidence={h.combined_confidence || h.confidence} />
              <span className="text-slate-600">{h.ts ? new Date(h.ts).toLocaleTimeString() : "—"}</span>
            </div>
          )) : (
            <div className="text-[10px] text-slate-500 text-center py-3">No history yet</div>
          )}
        </div>
      )}
    </div>
  );
}
