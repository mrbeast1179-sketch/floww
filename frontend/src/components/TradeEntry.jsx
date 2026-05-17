import React, { useState, useEffect } from "react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const TRADE_TEMPLATES = {
  iron_condor: {
    name: "Iron Condor",
    description: "Sell premium between put wall and call wall. Best in positive gamma.",
    fields: [
      { key: "put_short", label: "Put Short Strike", type: "number", hint: "Put wall strike" },
      { key: "put_long", label: "Put Long Strike", type: "number", hint: "5-10 points below short" },
      { key: "call_short", label: "Call Short Strike", type: "number", hint: "Call wall strike" },
      { key: "call_long", label: "Call Long Strike", type: "number", hint: "5-10 points above short" },
      { key: "contracts", label: "Contracts", type: "number", hint: "From position sizing" },
      { key: "credit", label: "Expected Credit", type: "number", step: "0.01" },
    ],
  },
  long_straddle: {
    name: "Long Straddle",
    description: "Buy ATM call + put. Best in negative gamma when expecting breakout.",
    fields: [
      { key: "strike", label: "ATM Strike", type: "number", hint: "Nearest to spot" },
      { key: "contracts", label: "Contracts (each leg)", type: "number" },
      { key: "call_premium", label: "Call Premium", type: "number", step: "0.01" },
      { key: "put_premium", label: "Put Premium", type: "number", step: "0.01" },
    ],
  },
  call_spread: {
    name: "Bull Call Spread",
    description: "Buy lower call, sell higher call. Directional bullish with defined risk.",
    fields: [
      { key: "long_strike", label: "Long Call Strike", type: "number", hint: "ATM or slightly OTM" },
      { key: "short_strike", label: "Short Call Strike", type: "number", hint: "Call wall or above" },
      { key: "contracts", label: "Contracts", type: "number" },
      { key: "debit", label: "Max Debit", type: "number", step: "0.01" },
    ],
  },
  put_spread: {
    name: "Bear Put Spread",
    description: "Buy higher put, sell lower put. Directional bearish with defined risk.",
    fields: [
      { key: "long_strike", label: "Long Put Strike", type: "number", hint: "ATM or slightly OTM" },
      { key: "short_strike", label: "Short Put Strike", type: "number", hint: "Put wall or below" },
      { key: "contracts", label: "Contracts", type: "number" },
      { key: "debit", label: "Max Debit", type: "number", step: "0.01" },
    ],
  },
  single_leg: {
    name: "Single Leg (Call or Put)",
    description: "Buy or sell a single option. Higher risk, higher reward.",
    fields: [
      { key: "action", label: "Action", type: "select", options: ["Buy Call", "Buy Put", "Sell Call", "Sell Put"] },
      { key: "strike", label: "Strike", type: "number" },
      { key: "contracts", label: "Contracts", type: "number" },
      { key: "premium", label: "Premium", type: "number", step: "0.01" },
    ],
  },
};

export function TradeEntry({ ticker, spot }) {
  const [checklist, setChecklist] = useState(null);
  const [selectedTemplate, setSelectedTemplate] = useState("iron_condor");
  const [formData, setFormData] = useState({});
  const [savedTrades, setSavedTrades] = useState([]);

  useEffect(() => {
    if (!ticker) return;
    fetch(`${API}/daily-checklist/${ticker}?expiries=4`)
      .then(r => r.json())
      .then(d => {
        setChecklist(d);
        // Pre-fill form with GEX levels
        const gf = d.key_levels || {};
        setFormData({
          put_short: gf.put_wall || "",
          put_long: gf.put_wall ? gf.put_wall - 5 : "",
          call_short: gf.call_wall || "",
          call_long: gf.call_wall ? gf.call_wall + 5 : "",
          strike: Math.round(spot || 0),
          long_strike: Math.round(spot || 0),
          short_strike: gf.call_wall || "",
          contracts: 1,
        });
      })
      .catch(() => setChecklist(null));
  }, [ticker, spot]);

  const template = TRADE_TEMPLATES[selectedTemplate];
  const regime = checklist?.regime?.gex_regime || "unknown";

  // Recommend template based on regime
  const recommendedTemplate = regime === "positive_gamma" ? "iron_condor" :
    regime === "negative_gamma" ? "long_straddle" : "single_leg";

  const handleSave = () => {
    const trade = {
      id: Date.now(),
      template: selectedTemplate,
      templateName: template.name,
      ticker,
      spot,
      data: { ...formData },
      regime,
      timestamp: new Date().toISOString(),
    };
    setSavedTrades(prev => [trade, ...prev].slice(0, 10));
  };

  return (
    <div className="panel p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="label mb-0">Trade Entry</div>
        <div className="text-[9px] text-slate-500">
          {regime === "positive_gamma" ? "🟢" : regime === "negative_gamma" ? "🔴" : "⚪"} {regime.replace("_", " ")}
        </div>
      </div>

      {/* Template Selector */}
      <div>
        <div className="label mb-1">Template</div>
        <select
          value={selectedTemplate}
          onChange={e => setSelectedTemplate(e.target.value)}
          className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
        >
          {Object.entries(TRADE_TEMPLATES).map(([key, tmpl]) => (
            <option key={key} value={key}>
              {tmpl.name}{key === recommendedTemplate ? " ⭐" : ""}
            </option>
          ))}
        </select>
        <div className="text-[9px] text-slate-500 mt-0.5">{template.description}</div>
        {recommendedTemplate !== selectedTemplate && (
          <div className="text-[9px] text-amber-400 mt-0.5">
            ⭐ Recommended for {regime.replace("_", " ")} regime: {TRADE_TEMPLATES[recommendedTemplate].name}
          </div>
        )}
      </div>

      {/* Form Fields */}
      <div className="space-y-1.5">
        {template.fields.map(field => (
          <div key={field.key}>
            <div className="label mb-0.5">{field.label}</div>
            {field.type === "select" ? (
              <select
                value={formData[field.key] || ""}
                onChange={e => setFormData(prev => ({ ...prev, [field.key]: e.target.value }))}
                className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
              >
                {field.options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            ) : (
              <div className="flex items-center gap-1">
                <input
                  type={field.type}
                  step={field.step || "1"}
                  value={formData[field.key] || ""}
                  onChange={e => setFormData(prev => ({ ...prev, [field.key]: parseFloat(e.target.value) || 0 }))}
                  placeholder={field.hint || ""}
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
                />
              </div>
            )}
            {field.hint && <div className="text-[8px] text-slate-600">{field.hint}</div>}
          </div>
        ))}
      </div>

      {/* Risk Preview */}
      {formData.contracts > 0 && (
        <div className="bg-slate-800/50 rounded p-2 border border-slate-700/50 text-[10px]">
          <div className="label mb-1">Risk Preview</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
            <div className="flex justify-between">
              <span className="text-slate-500">Contracts</span>
              <span className="mono text-slate-200">{formData.contracts}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Max Risk</span>
              <span className="mono text-rose-400">
                ${formData.credit ? (formData.contracts * 100 * (formData.credit || 0)).toFixed(0) :
                  formData.debit ? (formData.contracts * 100 * (formData.debit || 0)).toFixed(0) :
                  "TBD"}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Save Button */}
      <button onClick={handleSave} className="btn w-full text-[11px]">
        + Save Trade Idea
      </button>

      {/* Saved Trades */}
      {savedTrades.length > 0 && (
        <div>
          <div className="label mb-1">Saved Trades ({savedTrades.length})</div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {savedTrades.map(trade => (
              <div key={trade.id} className="bg-slate-800/30 rounded px-2 py-1 text-[9px] flex justify-between items-center">
                <div>
                  <span className="font-bold text-slate-300">{trade.templateName}</span>
                  <span className="text-slate-500 ml-1">@ {trade.spot ? Math.round(trade.spot) : "—"}</span>
                </div>
                <div className="text-slate-600">
                  {new Date(trade.timestamp).toLocaleTimeString()}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
