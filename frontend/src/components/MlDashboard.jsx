/**
 * MlDashboard.jsx — ML Prediction Dashboard
 *
 * Shows live ML predictions, model health, feature importance,
 * and prediction history. Connects to the backend ML API.
 *
 * API endpoints used:
 *   GET  /api/ml/predict/{ticker}       - Raw ML prediction
 *   GET  /api/ml/model-info/{ticker}    - Model metadata
 *   GET  /api/ml/dashboard/{ticker}     - Full ML briefing
 *   POST /api/ml/train                  - Trigger retraining
 */
import React, { useState, useEffect, useCallback } from "react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// ─── Signal Badge ───────────────────────────────────────────────────────────
function SignalBadge({ signal, confidence }) {
  const colorMap = {
    STRONG_BULLISH: "bg-emerald-500/20 border-emerald-500 text-emerald-400",
    BULLISH: "bg-emerald-500/10 border-emerald-500/50 text-emerald-300",
    NEUTRAL: "bg-slate-700/50 border-slate-600 text-slate-400",
    BEARISH: "bg-rose-500/10 border-rose-500/50 text-rose-300",
    STRONG_BEARISH: "bg-rose-500/20 border-rose-500 text-rose-400",
    UP: "bg-emerald-500/20 border-emerald-500 text-emerald-400",
    DOWN: "bg-rose-500/20 border-rose-500 text-rose-400",
  };
  const color = colorMap[signal] || colorMap.NEUTRAL;
  return (
    <span className={`inline-block px-2 py-0.5 rounded border text-[10px] font-bold tracking-wider ${color}`}>
      {signal?.replace("_", " ") ?? "—"}
      {confidence != null && <span className="ml-1 opacity-70">{(confidence * 100).toFixed(0)}%</span>}
    </span>
  );
}

// ─── Confidence Bar ─────────────────────────────────────────────────────────
function ConfidenceBar({ value, label, color = "emerald" }) {
  const pct = Math.min(100, Math.max(0, (value || 0) * 100));
  const barColor = color === "emerald"
    ? "bg-emerald-500"
    : color === "rose"
    ? "bg-rose-500"
    : "bg-amber-500";
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

// ─── Feature Importance Chart ───────────────────────────────────────────────
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

// ─── Prediction History Row ─────────────────────────────────────────────────
function PredictionRow({ pred }) {
  const bullish = pred.prediction === "UP" || pred.prediction === "BULLISH" || pred.prediction === "STRONG_BULLISH";
  return (
    <div className="flex items-center justify-between py-1 border-b border-slate-800/50 text-[10px]">
      <span className="text-slate-500">{pred.ticker}</span>
      <SignalBadge signal={pred.prediction} confidence={pred.confidence} />
      <span className="text-slate-500">{pred.spot ? `$${Number(pred.spot).toFixed(2)}` : "—"}</span>
      <span className="text-slate-600">
        {pred.computed_at ? new Date(pred.computed_at).toLocaleTimeString() : "—"}
      </span>
    </div>
  );
}

// ─── Main ML Dashboard Component ────────────────────────────────────────────
export function MlDashboard({ ticker = "SPY", spot }) {
  const [prediction, setPrediction] = useState(null);
  const [modelInfo, setModelInfo] = useState(null);
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
      setHistory(prev => {
        const next = [{...prev.filter(p => !(p.ticker === data.ticker && p.ts === data.ts))}, data].slice(0, 20);
        return next;
      });
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  const fetchModelInfo = useCallback(async () => {
    if (!ticker) return;
    try {
      const r = await fetch(`${API}/ml/model-info/${ticker}`);
      if (r.ok) setModelInfo(await r.json());
    } catch { /* noop */ }
  }, [ticker]);

  const triggerTraining = useCallback(async () => {
    setTraining(true);
    try {
      const r = await fetch(`${API}/ml/retrain/${ticker}`, { method: "POST" });
      if (r.ok) {
        setTimeout(() => {
          fetchPrediction();
          fetchModelInfo();
        }, 2000);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setTraining(false);
    }
  }, [ticker, fetchPrediction, fetchModelInfo]);

  useEffect(() => {
    fetchPrediction();
    fetchModelInfo();
    const id = setInterval(fetchPrediction, 60000);
    return () => clearInterval(id);
  }, [fetchPrediction, fetchModelInfo]);

  const predSignal = prediction?.combined_signal || prediction?.prediction;
  const predConf = prediction?.combined_confidence || prediction?.confidence;
  const probs = prediction?.probabilities || {};
  const features = prediction?.top_features || modelInfo?.top_features || {};
  const regime = prediction?.regime || prediction?.gex_regime;

  return (
    <div className="panel p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="label mb-0">ML Dashboard</div>
        <div className="flex items-center gap-2">
          {loading && <span className="inline-block w-2 h-2 rounded-full bg-amber-500 animate-pulse" />}
          {predSignal && <SignalBadge signal={predSignal} confidence={predConf} />}
          <button
            onClick={fetchPrediction}
            disabled={loading}
            className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700 disabled:opacity-50"
          >
            ↻
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="text-[10px] text-rose-400 bg-rose-500/10 rounded px-2 py-1 border border-rose-500/20">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 text-[9px]">
        {["predict", "model", "history"].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-2 py-0.5 rounded border transition-colors ${
              activeTab === tab
                ? "bg-slate-700 border-slate-600 text-slate-200"
                : "bg-slate-800/50 border-slate-800 text-slate-500 hover:text-slate-400"
            }`}
          >
            {tab === "predict" ? "Prediction" : tab === "model" ? "Model" : "History"}
          </button>
        ))}
      </div>

      {/* Prediction Tab */}
      {activeTab === "predict" && (
        <div className="space-y-3">
          {/* Main signal */}
          {prediction ? (
            <div className="bg-slate-800/50 rounded p-3 border border-slate-700/50 text-center">
              <div className="text-[9px] text-slate-500 mb-1">ML PREDICTION</div>
              <div className={`text-xl font-bold ${
                predSignal && (predSignal.includes("BULL") || predSignal === "UP")
                  ? "text-emerald-400"
                  : predSignal && (predSignal.includes("BEAR") || predSignal === "DOWN")
                  ? "text-rose-400"
                  : "text-slate-400"
              }`}>
                {predSignal?.replace("_", " ") ?? "—"}
              </div>
              <div className="flex items-center justify-center gap-3 mt-2">
                <ConfidenceBar
                  value={probs.down ?? (1 - (predConf || 0))}
                  label="DOWN"
                  color="rose"
                />
                <ConfidenceBar
                  value={probs.up ?? (predConf || 0)}
                  label="UP"
                  color="emerald"
                />
              </div>
              {regime && (
                <div className="mt-2 text-[9px] text-slate-500">
                  GEX Regime: <span className={regime === "POSITIVE" || regime === "positive" ? "text-emerald-400" : "text-rose-400"}>{regime}</span>
                </div>
              )}
              {prediction.spot && (
                <div className="mt-1 text-[9px] text-slate-500">
                  Spot: <span className="mono text-slate-300">${Number(prediction.spot).toFixed(2)}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center text-[10px] text-slate-500 py-4">
              {loading ? "Loading prediction…" : "No prediction available"}
            </div>
          )}

          {/* Feature importance mini */}
          {Object.keys(features).length > 0 && (
            <div>
              <div className="label mb-1">Top Features</div>
              <FeatureChart features={features} />
            </div>
          )}
        </div>
      )}

      {/* Model Tab */}
      {activeTab === "model" && (
        <div className="space-y-2">
          {prediction ? (
            <>
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                <div className="bg-slate-800/50 rounded p-2">
                  <div className="label mb-0.5">Type</div>
                  <div className="text-slate-200 mono">{prediction.model_type || "—"}</div>
                </div>
                <div className="bg-slate-800/50 rounded p-2">
                  <div className="label mb-0.5">Features</div>
                  <div className="text-slate-200 mono">{prediction.n_features || "—"}</div>
                </div>
                <div className="bg-slate-800/50 rounded p-2">
                  <div className="label mb-0.5">Train Acc</div>
                  <div className="text-slate-200 mono">{prediction.train_accuracy ? prediction.train_accuracy.toFixed(4) : "—"}</div>
                </div>
                <div className="bg-slate-800/50 rounded p-2">
                  <div className="label mb-0.5">Drift</div>
                  <div className={`mono ${prediction.drift_status === "drift_detected" ? "text-amber-400" : "text-emerald-400"}`}>
                    {prediction.drift_status || "—"}
                  </div>
                </div>
              </div>
              {/* Rolling accuracy */}
              {(prediction.rolling_7d_accuracy != null || prediction.rolling_30d_accuracy != null) && (
                <div>
                  <div className="label mb-1">Rolling Accuracy</div>
                  <div className="grid grid-cols-2 gap-2 text-[10px]">
                    <div className="bg-slate-800/50 rounded p-2">
                      <div className="text-slate-500">7d</div>
                      <div className="text-slate-200 mono">
                        {prediction.rolling_7d_accuracy != null
                          ? `${(prediction.rolling_7d_accuracy * 100).toFixed(1)}%`
                          : "—"}
                        <span className="text-slate-600 ml-1">({prediction.rolling_7d_n || 0})</span>
                      </div>
                    </div>
                    <div className="bg-slate-800/50 rounded p-2">
                      <div className="text-slate-500">30d</div>
                      <div className="text-slate-200 mono">
                        {prediction.rolling_30d_accuracy != null
                          ? `${(prediction.rolling_30d_accuracy * 100).toFixed(1)}%`
                          : "—"}
                        <span className="text-slate-600 ml-1">({prediction.rolling_30d_n || 0})</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
          ) : (
            <div className="text-[10px] text-slate-500 text-center py-4">
              No model info available
            </div>
          )}

          {/* Retrain button */}
          <button
            onClick={triggerTraining}
            disabled={training}
            className="w-full text-[11px] py-1.5 rounded bg-slate-800 border border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-600 disabled:opacity-50 transition-colors"
          >
            {training ? "Training…" : "↻ Retrain Model"}
          </button>
        </div>
      )}

      {/* History Tab */}
      {activeTab === "history" && (
        <div className="space-y-0.5 max-h-48 overflow-y-auto">
          {history.length > 0 ? (
            history.map((h, i) => <PredictionRow key={i} pred={h} />)
          ) : (
            <div className="text-[10px] text-slate-500 text-center py-4">
              No prediction history yet
            </div>
          )}
        </div>
      )}

      {/* Chain meta */}
      {prediction?.chain_meta && (
        <div className="text-[8px] text-slate-600 border-t border-slate-800 pt-2">
          {prediction.chain_available
            ? `Chain: ${prediction.chain_meta.expiries || "N/A"} expiries`
            : "No live chain data"}
        </div>
      )}
    </div>
  );
}
