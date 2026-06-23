/**
 * FilterBar.jsx — 12 filter controls matching BladeMap's screener flow.
 */
import React from "react";

const FLOW_TYPES = [
  { value: "all", label: "All Flows" },
  { value: "SWEEP", label: "Sweep" },
  { value: "BLOCK", label: "Block" },
  { value: "SPLIT", label: "Split" },
  { value: "VWAP_ALGO", label: "VWAP Algo" },
];

const SIDES = [
  { value: "all", label: "All Sides" },
  { value: "BUY", label: "Buy" },
  { value: "SELL", label: "Sell" },
];

const OPTION_TYPES = [
  { value: "all", label: "All Types" },
  { value: "CALL", label: "Calls" },
  { value: "PUT", label: "Puts" },
];

const DTE_RANGES = [
  { value: "all", label: "All DTE" },
  { value: "0-5", label: "0-5d" },
  { value: "6-21", label: "6-21d" },
  { value: "22-60", label: "22-60d" },
  { value: "60+", label: "60d+" },
];

const NOTIONAL_RANGES = [
  { value: "0", label: "Any" },
  { value: "10000", label: "$10K+" },
  { value: "50000", label: "$50K+" },
  { value: "100000", label: "$100K+" },
  { value: "500000", label: "$500K+" },
  { value: "1000000", label: "$1M+" },
];

const SCORE_RANGES = [
  { value: "0", label: "All" },
  { value: "25", label: "25+" },
  { value: "50", label: "50+" },
  { value: "70", label: "70+" },
  { value: "80", label: "80+" },
  { value: "90", label: "90+" },
];

const OTM_RANGES = [
  { value: "all", label: "All OTM" },
  { value: "0-10", label: "0-10%" },
  { value: "10-20", label: "10-20%" },
  { value: "20-30", label: "20-30%" },
  { value: "30+", label: "30%+" },
];

const EXCHANGES = [
  { value: "all", label: "All Exchanges" },
  { value: "NYSE", label: "NYSE" },
  { value: "NASDAQ", label: "NASDAQ" },
  { value: "CBOE", label: "CBOE" },
  { value: "ISE", label: "ISE" },
  { value: "MIAX", label: "MIAX" },
  { value: "BATS", label: "BATS" },
  { value: "ARCA", label: "ARCA" },
  { value: "MEMX", label: "MEMX" },
];

const TIME_RANGES = [
  { value: "all", label: "All Day" },
  { value: "open", label: "Open (9:30-10:30)" },
  { value: "mid", label: "Mid (10:30-14:00)" },
  { value: "close", label: "Close (14:00-16:00)" },
  { value: "after", label: "After (16:00-20:00)" },
];

export default function FilterBar({ filters, onFilterChange }) {
  const set = (key, value) => onFilterChange({ ...filters, [key]: value });

  const activeCount = Object.values(filters).filter(
    (v) => v && v !== "all" && v !== "0"
  ).length;

  return (
    <div className="fsp-filterbar">
      {/* 1. Search */}
      <div className="fsp-filter-group">
        <span className="fsp-filter-label">Search</span>
        <input
          className="fsp-filter-input"
          type="text"
          placeholder="Ticker…"
          value={filters.search || ""}
          onChange={(e) => set("search", e.target.value)}
        />
      </div>

      {/* 2. Side */}
      <div className="fsp-filter-group">
        <span className="fsp-filter-label">Side</span>
        <select
          className="fsp-filter-select"
          value={filters.side || "all"}
          onChange={(e) => set("side", e.target.value)}
        >
          {SIDES.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>

      {/* 3. Flow Type */}
      <div className="fsp-filter-group">
        <span className="fsp-filter-label">Flow</span>
        <select
          className="fsp-filter-select"
          value={filters.flowType || "all"}
          onChange={(e) => set("flowType", e.target.value)}
        >
          {FLOW_TYPES.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
      </div>

      {/* 4. Option Type */}
      <div className="fsp-filter-group">
        <span className="fsp-filter-label">Type</span>
        <select
          className="fsp-filter-select"
          value={filters.optionType || "all"}
          onChange={(e) => set("optionType", e.target.value)}
        >
          {OPTION_TYPES.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {/* 5. DTE Range */}
      <div className="fsp-filter-group">
        <span className="fsp-filter-label">DTE</span>
        <select
          className="fsp-filter-select"
          value={filters.dteRange || "all"}
          onChange={(e) => set("dteRange", e.target.value)}
        >
          {DTE_RANGES.map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>
      </div>

      {/* 6. Min Contracts */}
      <div className="fsp-filter-group">
        <span className="fsp-filter-label">Min Contracts</span>
        <input
          className="fsp-filter-input"
          type="number"
          placeholder="0"
          style={{ width: 80 }}
          value={filters.minContracts || ""}
          onChange={(e) => set("minContracts", e.target.value)}
        />
      </div>

      {/* 7. Min Notional */}
      <div className="fsp-filter-group">
        <span className="fsp-filter-label">Min Notional</span>
        <select
          className="fsp-filter-select"
          value={filters.minNotional || "0"}
          onChange={(e) => set("minNotional", e.target.value)}
        >
          {NOTIONAL_RANGES.map((n) => (
            <option key={n.value} value={n.value}>{n.label}</option>
          ))}
        </select>
      </div>

      {/* 8. Min Flow Score */}
      <div className="fsp-filter-group">
        <span className="fsp-filter-label">Min Score</span>
        <select
          className="fsp-filter-select"
          value={filters.minScore || "0"}
          onChange={(e) => set("minScore", e.target.value)}
        >
          {SCORE_RANGES.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>

      {/* 9. OTM Range */}
      <div className="fsp-filter-group">
        <span className="fsp-filter-label">OTM</span>
        <select
          className="fsp-filter-select"
          value={filters.otmRange || "all"}
          onChange={(e) => set("otmRange", e.target.value)}
        >
          {OTM_RANGES.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {/* 10. Exchanges */}
      <div className="fsp-filter-group">
        <span className="fsp-filter-label">Exchange</span>
        <select
          className="fsp-filter-select"
          value={filters.exchange || "all"}
          onChange={(e) => set("exchange", e.target.value)}
        >
          {EXCHANGES.map((ex) => (
            <option key={ex.value} value={ex.value}>{ex.label}</option>
          ))}
        </select>
      </div>

      {/* 11. Time Range */}
      <div className="fsp-filter-group">
        <span className="fsp-filter-label">Time</span>
        <select
          className="fsp-filter-select"
          value={filters.timeRange || "all"}
          onChange={(e) => set("timeRange", e.target.value)}
        >
          {TIME_RANGES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      {/* 12. Reset Filters */}
      <button
        className="fsp-filter-reset"
        onClick={() =>
          onFilterChange({
            search: "",
            side: "all",
            flowType: "all",
            optionType: "all",
            dteRange: "all",
            minContracts: "",
            minNotional: "0",
            minScore: "0",
            otmRange: "all",
            exchange: "all",
            timeRange: "all",
          })
        }
      >
        Reset{activeCount > 0 ? ` (${activeCount})` : ""}
      </button>
    </div>
  );
}
