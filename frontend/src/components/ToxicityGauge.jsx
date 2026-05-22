import React from "react";

const HORIZONS = [
  { key: "p_toxic_1min", label: "1m", seconds: 60 },
  { key: "p_toxic_5min", label: "5m", seconds: 300 },
  { key: "p_toxic_15min", label: "15m", seconds: 900 },
  { key: "p_toxic_60min", label: "60m", seconds: 3600 },
];

function probColor(p) {
  if (p === null || p === undefined || isNaN(p)) return "#64748b";
  if (p >= 0.7) return "#ef4444";
  if (p >= 0.4) return "#fbbf24";
  return "#34d399";
}

function probLabel(p) {
  if (p === null || p === undefined || isNaN(p) || p < 0) return "—";
  return (p * 100).toFixed(1) + "%";
}

function GaugeArc({ prob, size = 80 }) {
  const r = 30;
  const cx = size / 2;
  const cy = size / 2;
  const startAngle = -210;
  const endAngle = 30;
  const totalAngle = endAngle - startAngle;
  const filledAngle = startAngle + totalAngle * Math.max(0, Math.min(1, prob || 0));

  function angleToXY(angle) {
    const rad = ((angle - 90) * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  function arcPath(start, end, radius) {
    const s = angleToXY(start);
    const e = angleToXY(end);
    const largeArc = end - start > 180 ? 1 : 0;
    return `M ${s.x} ${s.y} A ${radius} ${radius} 0 ${largeArc} 1 ${e.x} ${e.y}`;
  }

  const color = probColor(prob);
  const bgPath = arcPath(startAngle, endAngle, r);
  const filledPath = prob > 0.005 ? arcPath(startAngle, filledAngle, r) : "";

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <path d={bgPath} fill="none" stroke="#1f2a3a" strokeWidth="5" strokeLinecap="round" />
      {filledPath && (
        <path d={filledPath} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round" />
      )}
      <text x={cx} y={cy + 4} textAnchor="middle" fill={color} fontSize="11" fontWeight="bold" className="mono">
        {probLabel(prob)}
      </text>
    </svg>
  );
}

export default function ToxicityGauge({ ensemble, onRefresh }) {
  const probs = ensemble?.ensemble_probabilities || {};
  const components = ensemble?.component_scores || {};
  const status = ensemble?.status || "inactive";
  const ticker = ensemble?.ticker || "";

  const maxProb = Math.max(...HORIZONS.map(h => probs[h.key] || 0));
  const overallColor = probColor(maxProb);

  return (
    <div className="panel-2 p-3" data-testid="toxicity-gauge">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Toxicity Ensemble {ticker && `· ${ticker}`}</div>
        {onRefresh && (
          <button onClick={onRefresh} className="btn text-[10px] px-2 py-0.5">refresh</button>
        )}
      </div>

      {/* Status badge */}
      <div className="flex items-center gap-2 mb-3">
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{ background: status === "active" ? "#34d399" : "#64748b" }}
        />
        <span className="text-[10px] uppercase tracking-widest text-slate-500">
          {status === "active" ? "LIVE" : status.toUpperCase()}
        </span>
        {maxProb >= 0.7 && (
          <span className="tag danger ml-auto text-[10px]">HIGH TOXICITY</span>
        )}
        {maxProb >= 0.4 && maxProb < 0.7 && (
          <span className="tag warning ml-auto text-[10px]">ELEVATED</span>
        )}
      </div>

      {/* Horizon gauges */}
      <div className="grid grid-cols-4 gap-2 mb-3">
        {HORIZONS.map(h => (
          <div key={h.key} className="flex flex-col items-center">
            <GaugeArc prob={probs[h.key] || 0} />
            <div className="text-[10px] text-slate-500 mt-1">{h.label}</div>
          </div>
        ))}
      </div>

      {/* Component scores */}
      <div className="border-t border-slate-800/60 pt-2 mt-2">
        <div className="text-[10px] uppercase tracking-widest text-slate-600 mb-1">Component Scores</div>
        <div className="grid grid-cols-3 gap-2 text-[11px]">
          <div>
            <div className="label">CNN-AE</div>
            <div className="mono text-slate-300">
              {components.cnn_ae !== undefined ? components.cnn_ae.toFixed(4) : "—"}
            </div>
          </div>
          <div>
            <div className="label">Statistical</div>
            <div className="mono text-slate-300">
              {components.statistical !== undefined ? components.statistical.toFixed(4) : "—"}
            </div>
          </div>
          <div>
            <div className="label">Forecast</div>
            <div className="mono text-slate-300">
              {components.forecast_residual !== undefined ? components.forecast_residual.toFixed(4) : "—"}
            </div>
          </div>
        </div>
      </div>

      {/* Anomaly flags */}
      <div className="flex gap-2 mt-2">
        {ensemble?.cnn_anomaly && (
          <span className="tag danger text-[10px]">CNN ANOMALY</span>
        )}
        {ensemble?.statistical_anomaly && (
          <span className="tag warning text-[10px]">STATISTICAL ANOMALY</span>
        )}
        {!ensemble?.cnn_anomaly && !ensemble?.statistical_anomaly && (
          <span className="text-[10px] text-slate-600">No anomalies detected</span>
        )}
      </div>
    </div>
  );
}
