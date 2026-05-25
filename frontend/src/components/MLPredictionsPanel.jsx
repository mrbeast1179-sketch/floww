import React from "react";

/**
 * MLPredictionsPanel — Displays live ML model predictions for all registered tickers.
 *
 * Fetches from /api/ml/batch-predict and renders a card per ticker with:
 *   - Prediction (BULLISH/BEARISH) with color coding
 *   - Confidence bar
 *   - Data freshness indicator
 *
 * States: loading / error / empty / data
 */

const PREDICTION_STYLES = {
  bullish: {
    text: "text-emerald-300",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/40",
    bar: "bg-emerald-400/70",
    label: "↑ BULLISH",
  },
  bearish: {
    text: "text-rose-300",
    bg: "bg-rose-500/10",
    border: "border-rose-500/40",
    bar: "bg-rose-400/70",
    label: "↓ BEARISH",
  },
};

function PredictionCard({ pred }) {
  const style = PREDICTION_STYLES[pred.prediction_label] || PREDICTION_STYLES.bearish;
  const conf = pred.confidence ?? 0.5;
  const confPct = Math.round(conf * 100);
  const dataAgeMin = pred.data_age_sec != null ? Math.round(pred.data_age_sec / 60) : null;
  const isStale = dataAgeMin != null && dataAgeMin > 60;

  return (
    <div className={`rounded border p-2.5 ${style.bg} ${style.border}`}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-bold tracking-wider text-slate-200">
          {pred.ticker}
        </span>
        <span className={`text-[10px] font-bold ${style.text}`}>
          {style.label}
        </span>
      </div>
      <div className="mb-1.5">
        <div className="flex justify-between text-[9px] mb-0.5">
          <span className="text-slate-500">Confidence</span>
          <span className={`mono ${style.text}`}>{confPct}%</span>
        </div>
        <div className="relative h-1.5 bg-slate-800/60 rounded overflow-hidden">
          <div
            className={`absolute inset-y-0 left-0 rounded ${style.bar}`}
            style={{ width: `${confPct}%` }}
          />
        </div>
      </div>
      <div className="flex justify-between text-[9px] mono">
        <span className="text-rose-400">
          ↓ {((pred.probabilities?.bearish ?? 0) * 100).toFixed(1)}%
        </span>
        <span className="text-emerald-400">
          ↑ {((pred.probabilities?.bullish ?? 0) * 100).toFixed(1)}%
        </span>
      </div>
      {isStale && (
        <div className="mt-1 text-[8px] text-amber-400">
          Data {dataAgeMin}m old
        </div>
      )}
    </div>
  );
}

export default function MLPredictionsPanel({ predictions = [], loading = false, error = null, onRefresh = null }) {
  if (loading) {
    return (
      <div className="panel p-3" data-testid="ml-predictions">
        <div className="label mb-2">ML Predictions</div>
        <div className="text-slate-500 text-[11px]">Loading…</div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="panel p-3" data-testid="ml-predictions">
        <div className="label mb-2">ML Predictions</div>
        <div className="text-rose-400 text-[10px]">{String(error)}</div>
      </div>
    );
  }
  if (!predictions || predictions.length === 0) {
    return (
      <div className="panel p-3" data-testid="ml-predictions">
        <div className="label mb-2">ML Predictions</div>
        <div className="text-slate-500 text-[11px]">—</div>
      </div>
    );
  }
  const bullish = predictions.filter((p) => p.prediction_label === "bullish").length;
  const bearish = predictions.length - bullish;

  return (
    <div className="panel p-3" data-testid="ml-predictions">
      <div className="flex items-center justify-between mb-2">
        <div className="label">ML Predictions</div>
        <div className="flex items-center gap-2">
          <span className="text-[9px] text-emerald-400">{bullish}↑</span>
          <span className="text-[9px] text-rose-400">{bearish}↓</span>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="text-[9px] text-slate-500 hover:text-slate-300 transition-colors"
              title="Refresh predictions"
            >
              ↻
            </button>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {predictions.map((pred) => (
          <PredictionCard key={pred.ticker} pred={pred} />
        ))}
      </div>
      <div className="text-[9px] text-slate-600 mt-2 italic">
        Walk-forward GBM models · 44 features · directional move prediction
      </div>
    </div>
  );
}
