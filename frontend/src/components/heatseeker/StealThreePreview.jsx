/**
 * StealThreePreview.jsx — STEAL-TOP-3 PREVIEW PAGE
 *
 * Renders all three top-ranked steals (#1 Dual-GEX badge, #3 Wheel income
 * panel, #5 IV-Mid badge) in a layout that matches HeatseekerDashboard's
 * visual tier. Intended to be the entry point for the "Steal Three"
 * nav-item delivered by this turn. Meridian-decoder surface: this
 * page lives alongside Solstice, Triad, Tidehunter Pro in the
 * Decoder group.
 *
 * Endpoint base: http://localhost:8000 (canonical floww backend; the same
 * routes also live on the dev sidecar at :8001 — see
 * services/steal_three_server.py).
 *
 * To mount in AppShell: add a NAV_ITEMS entry
 *   { id: "steal-three", label: "Steal Three", group: "Decoder",
 *     icon: "sparkles" }
 * to frontend/src/shell/navConfig.js. If AppShell's router is id-based
 * the page renders automatically (existing convention for Triad,
 * Tidehunter Pro, etc.).
 */

import React, { memo, useState } from "react";
import DualGEXBadge from "./DualGEXBadge";
import IVMidBadge from "./IVMidBadge";
import WheelIncomeScreenerPanel from "./WheelIncomeScreenerPanel";

const QUICK_PICKS = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL"];

function StealThreePreview({ defaultTicker = "SPY" }) {
  const [ticker, setTicker] = useState(defaultTicker);
  const [widthIV, setWidthIV] = useState(6);

  return (
    <div className="p-4 space-y-4" data-testid="steal-three-preview">
      {/* Page Header */}
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <div className="label">Meridian · Steal Three</div>
          <div className="text-sm font-bold tracking-wider flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
            {ticker}
            <span className="ml-2 text-[10px] uppercase tracking-widest text-slate-500">
              ranks #1 · #3 · #5 of the steal-list
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1.5 bg-slate-900/40 rounded-md border border-slate-700/30 p-1">
          {QUICK_PICKS.map((q) => (
            <button
              key={q}
              onClick={() => setTicker(q)}
              className={`text-[9px] uppercase tracking-widest font-bold px-2 py-1 rounded ${
                ticker === q
                  ? "bg-sky-500/20 text-sky-300"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {q}
            </button>
          ))}
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase().replace(/[^A-Z0-9.\-^]/g, ""))}
            className="bg-transparent text-[10px] font-mono text-slate-200 px-2 py-1 w-20 focus:outline-none"
            placeholder="ticker"
          />
        </div>
      </div>

      {/* Top row: Dual-GEX + IV-Mid */}
      <div>
        <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold mb-2">
          ∑ Inputs (one extra aggregation pass each, no compute() edits)
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <DualGEXBadge ticker={ticker} />
          <IVMidBadge ticker={ticker} width={widthIV} />
        </div>
      </div>

      {/* Bottom row: Wheel income screener */}
      <div>
        <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold mb-2">
          ∑ Surface (first premium-selling surface in floww — journal-validated edge)
        </div>
        <WheelIncomeScreenerPanel ticker={ticker} />
      </div>

      {/* Footer */}
      <div className="text-[9px] text-slate-600 uppercase tracking-widest pt-2 border-t border-slate-800">
        Endpoint base <code className="text-slate-400">http://localhost:8000</code> (canonical floww backend · mounted via <code className="text-slate-400">backend/routes/steal_three.py</code>) ·
        standalone dev sidecar:
        <code className="ml-1 text-slate-400">cd backend &amp;&amp; python -m services.steal_three_server</code>
        (port 8001) · rank #2 (0DTE OI→Volume) ships as a 1-line toggle in
        <code className="ml-1 text-slate-400">gex_aggregator.compute()</code> once the other
        session is idle.
      </div>
    </div>
  );
}

export default memo(StealThreePreview);
