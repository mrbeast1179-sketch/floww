import React from "react";

const CLASSES = [
  { key: "all", label: "All" },
  { key: "sweep", label: "Sweeps" },
  { key: "block", label: "Blocks" },
  { key: "unusual", label: "Unusual" },
];

export default function FlowFilters({ value, onChange }) {
  const { ticker = "", classification = "all", minPremium = 0 } = value || {};

  function emit(patch) {
    if (onChange) onChange({ ticker, classification, minPremium, ...patch });
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {CLASSES.map((c) => (
        <button
          key={c.key}
          className={`btn ${classification === c.key ? "active" : ""}`}
          onClick={() => emit({ classification: c.key })}
        >
          {c.label}
        </button>
      ))}
      <input
        className="bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-[11px] mono text-slate-300 w-16"
        placeholder="Ticker"
        value={ticker}
        onChange={(e) => emit({ ticker: (e.target.value || "").toUpperCase() })}
      />
      <input
        className="bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-[11px] mono text-slate-300 w-24"
        placeholder="Min premium"
        type="number"
        min="0"
        value={minPremium || ""}
        onChange={(e) => {
          const v = e.target.value === "" ? 0 : Number(e.target.value);
          emit({ minPremium: isNaN(v) ? 0 : Math.max(0, v) });
        }}
      />
    </div>
  );
}
