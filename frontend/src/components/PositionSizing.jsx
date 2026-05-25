import React, { useState, useEffect } from "react";
import { fmt, fmtAbs } from "../lib/helpers";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function PositionSizing({ ticker, spot }) {
  const [accountSize, setAccountSize] = useState("5000");
  const [riskPct, setRiskPct] = useState("1");
  const [maxPositions, setMaxPositions] = useState("3");
  const [checklist, setChecklist] = useState(null);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    fetch(`${API}/daily-checklist/${ticker}?expiries=4`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(d => {
        if (!cancelled) setChecklist(d);
      })
      .catch(() => {
        if (!cancelled) setChecklist(null);
      });
    return () => { cancelled = true; };
  }, [ticker]);

  const account = parseFloat(accountSize) || 0;
  const risk = parseFloat(riskPct) || 1;
  const maxPos = parseInt(maxPositions) || 3;
  const riskDollars = account * (risk / 100);

  // GEX-based position sizing
  const regime = checklist?.regime?.gex_regime || "unknown";
  const distToFlip = checklist?.key_levels?.dist_to_flip;
  const callWall = checklist?.key_levels?.call_wall;
  const putWall = checklist?.key_levels?.put_wall;

  // Adjust risk based on regime
  let riskMultiplier = 1.0;
  if (regime === "negative_gamma") {
    riskMultiplier = distToFlip != null && distToFlip < -10 ? 0.5 : 0.75;
  } else if (regime === "positive_gamma") {
    riskMultiplier = distToFlip != null && Math.abs(distToFlip) < 5 ? 0.75 : 1.0;
  }

  const adjustedRiskDollars = riskDollars * riskMultiplier;
  const perPositionDollars = adjustedRiskDollars / maxPos;

  // Calculate contract sizes for different strategies
  const spyPrice = spot || 0;
  const contractMultiplier = 100;

  // Iron condor: risk = width of spread - credit received
  // Assume 5-point spread, 2 credit → max loss = 3 points = $300 per contract
  const icMaxLoss = 300;
  const icContracts = Math.floor(perPositionDollars / icMaxLoss);

  // Long straddle: risk = premium paid
  // Assume ATM straddle costs ~$5 = $500 per contract
  const straddleCost = 500;
  const straddleContracts = Math.floor(perPositionDollars / straddleCost);

  // Single leg (call or put): risk = premium paid
  // Assume ATM option costs ~$2.50 = $250 per contract
  const singleLegCost = 250;
  const singleLegContracts = Math.floor(perPositionDollars / singleLegCost);

  // Stop distance based on GEX levels
  const stopDistance = putWall && spot ? spot - putWall : 10;
  const stopRiskPerContract = Math.abs(stopDistance) * contractMultiplier;

  return (
    <div className="panel p-3 space-y-3">
      <div className="label mb-0">Position Sizing Calculator</div>

      {/* Account Inputs */}
      <div className="grid grid-cols-3 gap-2">
        <div>
          <div className="label mb-0.5">Account $</div>
          <input
            type="number"
            value={accountSize}
            onChange={e => setAccountSize(e.target.value)}
            className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
          />
        </div>
        <div>
          <div className="label mb-0.5">Risk %</div>
          <input
            type="number"
            step="0.5"
            value={riskPct}
            onChange={e => setRiskPct(e.target.value)}
            className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
          />
        </div>
        <div>
          <div className="label mb-0.5">Max Positions</div>
          <input
            type="number"
            value={maxPositions}
            onChange={e => setMaxPositions(e.target.value)}
            className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Risk Summary */}
      <div className="bg-slate-800/50 rounded p-2 border border-slate-700/50">
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
          <div className="flex justify-between">
            <span className="text-slate-500">Total Risk $</span>
            <span className="mono text-slate-200">${fmt(riskDollars, 0)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">GEX Multiplier</span>
            <span className={`mono ${riskMultiplier < 1 ? "text-rose-400" : "text-emerald-400"}`}>
              {riskMultiplier}x
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Adjusted Risk $</span>
            <span className="mono text-amber-400">${fmt(adjustedRiskDollars, 0)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Per Position $</span>
            <span className="mono text-sky-400">${fmt(perPositionDollars, 0)}</span>
          </div>
        </div>
      </div>

      {/* Strategy Sizing */}
      <div>
        <div className="label mb-1">Strategy Sizing</div>
        <div className="space-y-1 text-[10px]">
          <div className="flex justify-between items-center bg-slate-800/30 rounded px-2 py-1">
            <div>
              <span className="text-slate-300">Iron Condor (5pt spread)</span>
              <span className="text-slate-600 ml-1">~${icMaxLoss}/contract</span>
            </div>
            <span className="mono text-emerald-400 font-bold">{icContracts} contracts</span>
          </div>
          <div className="flex justify-between items-center bg-slate-800/30 rounded px-2 py-1">
            <div>
              <span className="text-slate-300">Long Straddle (ATM)</span>
              <span className="text-slate-600 ml-1">~${straddleCost}/contract</span>
            </div>
            <span className="mono text-sky-400 font-bold">{straddleContracts} contracts</span>
          </div>
          <div className="flex justify-between items-center bg-slate-800/30 rounded px-2 py-1">
            <div>
              <span className="text-slate-300">Single Leg (ATM)</span>
              <span className="text-slate-600 ml-1">~${singleLegCost}/contract</span>
            </div>
            <span className="mono text-amber-400 font-bold">{singleLegContracts} contracts</span>
          </div>
        </div>
      </div>

      {/* GEX-Based Recommendation */}
      {checklist && (
        <div>
          <div className="label mb-1">GEX-Based Guidance</div>
          <div className="text-[10px] space-y-1">
            <div className={`p-1.5 rounded border ${regime === "negative_gamma" ? "bg-rose-500/10 border-rose-500/20" : "bg-emerald-500/10 border-emerald-500/20"}`}>
              <span className={regime === "negative_gamma" ? "text-rose-400" : "text-emerald-400"}>
                {regime === "negative_gamma" ? "🔴 Negative Gamma" : "🟢 Positive Gamma"}
              </span>
              <span className="text-slate-400 ml-1">
                — {regime === "negative_gamma" ? "Reduce size, momentum trades" : "Normal size, mean-reversion OK"}
              </span>
            </div>
            {distToFlip != null && Math.abs(distToFlip) < 5 && (
              <div className="p-1.5 rounded border bg-amber-500/10 border-amber-500/20">
                <span className="text-amber-400">⚠️ Near Gamma Flip</span>
                <span className="text-slate-400 ml-1">— Reduce size by 50%, regime could change</span>
              </div>
            )}
            {checklist?.strategy?.position_sizing_note && (
              <div className="text-[9px] text-slate-500 italic">
                {checklist.strategy.position_sizing_note}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Quick Reference */}
      <div className="text-[9px] text-slate-600 border-t border-slate-800 pt-2">
        <div className="font-bold text-slate-500 mb-0.5">Quick Reference (SPY ~{spot ? fmt(spot, 0) : "—"})</div>
        <div>• 1 contract = $100 per point move</div>
        <div>• 1% account risk = ${fmt(riskDollars, 0)} max loss</div>
        <div>• GEX walls act as magnets — price tends to stay between them</div>
        <div>• Place stops beyond GEX walls, not at them</div>
      </div>
    </div>
  );
}
