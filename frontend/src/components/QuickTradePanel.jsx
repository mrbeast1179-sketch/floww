import React, { useState, useEffect, useCallback } from "react";
import { fmt } from "../lib/helpers";

/**
 * Quick Trade Panel — slide-up panel for rapid trade entry from Trinity
 *
 * Triggered by clicking any strike row in TrinityView.
 * Pre-populates with strike, spot, GEX data.
 * Supports: Buy Call, Buy Put, Sell Call, Sell Put, Iron Condor, Straddle
 */

const STRATEGIES = [
  { id: "buy_call", label: "Buy Call", icon: "▲", color: "#34d399" },
  { id: "buy_put", label: "Buy Put", icon: "▼", color: "#f87171" },
  { id: "sell_call", label: "Sell Call", icon: "▽", color: "#c4b5fd" },
  { id: "sell_put", label: "Sell Put", icon: "△", color: "#c4b5fd" },
  { id: "iron_condor", label: "Iron Condor", icon: "◆", color: "#fbbf24" },
  { id: "straddle", label: "Straddle", icon: "◇", color: "#38bdf8" },
];

export default function QuickTradePanel({ selection, onClose, onSubmit }) {
  const [strategy, setStrategy] = useState("buy_call");
  const [quantity, setQuantity] = useState(1);
  const [limitPrice, setLimitPrice] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);

  const [submitted, setSubmitted] = useState(false);

  // Reset when selection changes
  useEffect(() => {
    setStrategy("buy_call");
    setQuantity(1);
    setLimitPrice("");
    setShowConfirm(false);
    setSubmitted(false);
  }, [selection?.strike]);

  const handleSubmit = useCallback(() => {
    if (!selection) return;
    const trade = {
      ticker: selection.ticker,
      strike: selection.strike,
      spot: selection.spot,
      strategy,
      quantity,
      limitPrice: limitPrice ? parseFloat(limitPrice) : null,
      gex: selection.gex,
      iv: selection.iv,
      delta: selection.delta,
      oi: selection.oi,
      timestamp: new Date().toISOString(),
    };
    setSubmitted(true);
    if (onSubmit) onSubmit(trade);
    // Auto-close after showing success
    setTimeout(() => {
      if (onClose) onClose();
    }, 1500);
  }, [selection, strategy, quantity, limitPrice, onSubmit, onClose]);

  if (!selection) return null;

  const { ticker, strike, spot, gex, iv, delta, oi, call_gex, put_gex, vex, charm } = selection;
  const isCall = strategy.includes("call") || strategy === "straddle" || strategy === "iron_condor";
  const isBuy = strategy.startsWith("buy");

  // Estimate price based on IV (simplified)
  const estPrice = iv ? (spot * iv * 0.01).toFixed(2) : "—";
  const maxRisk = isBuy ? (parseFloat(estPrice) * quantity * 100).toFixed(0) : "Unlimited";
  const maxReward = isBuy ? "Unlimited" : (parseFloat(estPrice) * quantity * 100).toFixed(0);

  const fmtGex = (v) => {
    if (v == null) return "—";
    const a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toFixed(1) + "M";
    if (a >= 1e3) return (v / 1e3).toFixed(1) + "K";
    return v.toFixed(0);
  };

  return (
    <div className="quick-trade-overlay" onClick={onClose}>
      <div className="quick-trade-panel" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="quick-trade-header">
          <div className="quick-trade-title">
            <span className="quick-trade-ticker">{ticker.replace("^", "")}</span>
            <span className="quick-trade-strike">@{fmt(strike, 0)}</span>
            <span className={`quick-trade-gex ${gex >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {gex >= 0 ? "+" : ""}{(gex / 1e3).toFixed(1)}K GEX
            </span>
          </div>
          <button className="quick-trade-close" onClick={onClose}>✕</button>
        </div>

        {/* Spot + context */}
        <div className="quick-trade-context">
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Spot</span>
            <span className="quick-trade-stat-value">${fmt(spot, 2)}</span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Distance</span>
            <span className={`quick-trade-stat-value ${strike >= spot ? "text-emerald-400" : "text-rose-400"}`}>
              {strike >= spot ? "+" : ""}{((strike - spot) / spot * 100).toFixed(2)}%
            </span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">IV</span>
            <span className="quick-trade-stat-value text-indigo-400">{iv ? `${(iv * 100).toFixed(1)}%` : "—"}</span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Delta</span>
            <span className="quick-trade-stat-value">{delta ? delta.toFixed(2) : "—"}</span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">OI</span>
            <span className="quick-trade-stat-value text-slate-400">{oi ? fmtGex(oi) : "—"}</span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">VEX</span>
            <span className={`quick-trade-stat-value ${vex >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {vex != null ? fmtGex(vex) : "—"}
            </span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Charm</span>
            <span className={`quick-trade-stat-value ${charm >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {charm != null ? fmtGex(charm) : "—"}
            </span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Call GEX</span>
            <span className="quick-trade-stat-value text-emerald-400">{call_gex != null ? fmtGex(call_gex) : "—"}</span>
          </div>
          <div className="quick-trade-stat">
            <span className="quick-trade-stat-label">Put GEX</span>
            <span className="quick-trade-stat-value text-rose-400">{put_gex != null ? fmtGex(put_gex) : "—"}</span>
          </div>
        </div>

        {/* Strategy selector */}
        <div className="quick-trade-strategies">
          {STRATEGIES.map(s => (
            <button
              key={s.id}
              className={`quick-trade-strategy-btn${strategy === s.id ? " quick-trade-strategy-active" : ""}`}
              onClick={() => setStrategy(s.id)}
              style={{ "--strategy-color": s.color }}
            >
              <span className="quick-trade-strategy-icon">{s.icon}</span>
              <span className="quick-trade-strategy-label">{s.label}</span>
            </button>
          ))}
        </div>

        {/* Order details */}
        <div className="quick-trade-details">
          <div className="quick-trade-row">
            <label>Qty (contracts)</label>
            <input
              type="number"
              min={1}
              max={100}
              value={quantity}
              onChange={e => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
              className="quick-trade-input"
            />
          </div>
          <div className="quick-trade-row">
            <label>Limit Price</label>
            <input
              type="number"
              step="0.01"
              placeholder={estPrice}
              value={limitPrice}
              onChange={e => setLimitPrice(e.target.value)}
              className="quick-trade-input"
            />
          </div>
        </div>

        {/* Risk summary */}
        <div className="quick-trade-risk">
          <div className="quick-trade-risk-row">
            <span>Est. Price</span>
            <span className="text-amber-400">${limitPrice || estPrice}</span>
          </div>
          <div className="quick-trade-risk-row">
            <span>Max Risk</span>
            <span className="text-rose-400">${maxRisk}</span>
          </div>
          <div className="quick-trade-risk-row">
            <span>Max Reward</span>
            <span className="text-emerald-400">${maxReward}</span>
          </div>
          <div className="quick-trade-risk-row">
            <span>Notional</span>
            <span className="text-slate-300">
              ${((parseFloat(limitPrice || estPrice) || 0) * quantity * 100).toLocaleString()}
            </span>
          </div>
        </div>

        {/* Submit */}
        {submitted ? (
          <div className="quick-trade-success">
            <div className="quick-trade-success-icon">✓</div>
            <div className="quick-trade-success-text">Trade Recorded</div>
            <div className="quick-trade-success-sub">
              {STRATEGIES.find(s => s.id === strategy)?.label} × {quantity} @ ${limitPrice || estPrice}
            </div>
          </div>
        ) : !showConfirm ? (
          <button
            className="quick-trade-submit"
            onClick={() => setShowConfirm(true)}
            style={{
              background: isBuy
                ? "linear-gradient(135deg, #16a34a, #22c55e)"
                : "linear-gradient(135deg, #dc2626, #ef4444)",
            }}
          >
            Review {STRATEGIES.find(s => s.id === strategy)?.label} × {quantity}
          </button>
        ) : (
          <div className="quick-trade-confirm">
            <p className="quick-trade-confirm-text">
              {isBuy ? "Buy" : "Sell"} {quantity} contract{quantity > 1 ? "s" : ""}{" "}
              {ticker.replace("^", "")} {fmt(strike, 0)} {strategy.includes("call") ? "Call" : strategy.includes("put") ? "Put" : ""}{" "}
              @ ${limitPrice || estPrice}?
            </p>
            <div className="quick-trade-confirm-btns">
              <button className="quick-trade-cancel" onClick={() => setShowConfirm(false)}>Cancel</button>
              <button className="quick-trade-confirm-btn" onClick={handleSubmit}>
                ✓ Confirm Order
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
