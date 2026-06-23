/**
 * StatsBar.jsx — Real-time aggregate statistics for the screener.
 */
import React, { useMemo } from "react";

export default function StatsBar({ events }) {
  const stats = useMemo(() => {
    if (!events || events.length === 0) {
      return {
        total: 0,
        buyCount: 0,
        sellCount: 0,
        buyVolume: 0,
        sellVolume: 0,
        totalNotional: 0,
        avgScore: 0,
        maxScore: 0,
        sweepCount: 0,
        blockCount: 0,
        splitCount: 0,
        algoCount: 0,
        callCount: 0,
        putCount: 0,
      };
    }

    let buyCount = 0, sellCount = 0;
    let buyVolume = 0, sellVolume = 0;
    let totalNotional = 0;
    let scoreSum = 0, maxScore = 0;
    let sweepCount = 0, blockCount = 0, splitCount = 0, algoCount = 0;
    let callCount = 0, putCount = 0;

    for (const e of events) {
      const side = String(e.side || "").toUpperCase();
      const contracts = Number(e.contracts) || 0;
      const notional = Number(e.notional) || 0;
      const score = Number(e.score) || 0;
      const flowType = String(e.flowType || "").toUpperCase();
      const optType = String(e.optionType || "").toUpperCase();

      if (side === "BUY") { buyCount++; buyVolume += contracts; }
      else { sellCount++; sellVolume += contracts; }

      totalNotional += notional;
      scoreSum += score;
      if (score > maxScore) maxScore = score;

      if (flowType === "SWEEP") sweepCount++;
      else if (flowType === "BLOCK") blockCount++;
      else if (flowType === "SPLIT") splitCount++;
      else if (flowType === "VWAP_ALGO") algoCount++;

      if (optType === "CALL") callCount++;
      else putCount++;
    }

    return {
      total: events.length,
      buyCount,
      sellCount,
      buyVolume,
      sellVolume,
      totalNotional,
      avgScore: Math.round(scoreSum / events.length),
      maxScore,
      sweepCount,
      blockCount,
      splitCount,
      algoCount,
      callCount,
      putCount,
    };
  }, [events]);

  const fmtVol = (v) => {
    if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
    return String(v);
  };

  const buyPct = stats.total > 0 ? Math.round((stats.buyCount / stats.total) * 100) : 0;

  return (
    <div className="fsp-statsbar">
      <div className="fsp-stat">
        <span className="fsp-stat-label">Events</span>
        <span className="fsp-stat-value">{stats.total.toLocaleString()}</span>
      </div>
      <div className="fsp-stat-divider" />
      <div className="fsp-stat">
        <span className="fsp-stat-label">Buy</span>
        <span className="fsp-stat-value buy">{stats.buyCount} ({buyPct}%)</span>
      </div>
      <div className="fsp-stat">
        <span className="fsp-stat-label">Sell</span>
        <span className="fsp-stat-value sell">{stats.sellCount} ({100 - buyPct}%)</span>
      </div>
      <div className="fsp-stat-divider" />
      <div className="fsp-stat">
        <span className="fsp-stat-label">Buy Vol</span>
        <span className="fsp-stat-value buy">{fmtVol(stats.buyVolume)}</span>
      </div>
      <div className="fsp-stat">
        <span className="fsp-stat-label">Sell Vol</span>
        <span className="fsp-stat-value sell">{fmtVol(stats.sellVolume)}</span>
      </div>
      <div className="fsp-stat-divider" />
      <div className="fsp-stat">
        <span className="fsp-stat-label">Notional</span>
        <span className="fsp-stat-value">${(stats.totalNotional / 1e6).toFixed(1)}M</span>
      </div>
      <div className="fsp-stat-divider" />
      <div className="fsp-stat">
        <span className="fsp-stat-label">Avg Score</span>
        <span className="fsp-stat-value">{stats.avgScore}</span>
      </div>
      <div className="fsp-stat">
        <span className="fsp-stat-label">Max Score</span>
        <span className="fsp-stat-value">{stats.maxScore}</span>
      </div>
      <div className="fsp-stat-divider" />
      <div className="fsp-stat">
        <span className="fsp-stat-label">Sweep</span>
        <span className="fsp-stat-value" style={{ color: "var(--badge-sweep-text)" }}>{stats.sweepCount}</span>
      </div>
      <div className="fsp-stat">
        <span className="fsp-stat-label">Block</span>
        <span className="fsp-stat-value" style={{ color: "var(--badge-block-text)" }}>{stats.blockCount}</span>
      </div>
      <div className="fsp-stat">
        <span className="fsp-stat-label">Split</span>
        <span className="fsp-stat-value" style={{ color: "var(--badge-split-text)" }}>{stats.splitCount}</span>
      </div>
      <div className="fsp-stat">
        <span className="fsp-stat-label">Algo</span>
        <span className="fsp-stat-value" style={{ color: "var(--badge-algo-text)" }}>{stats.algoCount}</span>
      </div>
      <div className="fsp-stat-divider" />
      <div className="fsp-stat">
        <span className="fsp-stat-label">Calls</span>
        <span className="fsp-stat-value" style={{ color: "var(--accent-green)" }}>{stats.callCount}</span>
      </div>
      <div className="fsp-stat">
        <span className="fsp-stat-label">Puts</span>
        <span className="fsp-stat-value" style={{ color: "var(--accent-red)" }}>{stats.putCount}</span>
      </div>
    </div>
  );
}
