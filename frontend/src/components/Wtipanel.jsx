import React, { useEffect, useState } from "react";
import { API } from "../config/api";
import "./MarketPanels.css";

export default function Wtipanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(`${API}/wti/vol`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        if (!cancelled) setData(await res.json());
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    poll();
    const id = setInterval(poll, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (loading) return <div className="wti-loading">Loading WTI data…</div>;
  if (error) return <div className="wti-error">WTI feed error: {error}</div>;
  if (!data?.ok) return <div className="wti-error">No WTI data: {data?.error || "unknown"}</div>;

  const d = data;
  const dirColor = d.direction === "RISING" ? "var(--neg)" : d.direction === "FALLING" ? "var(--pos)" : "var(--warn)";
  const dirLabel = d.direction === "RISING" ? "Vol Rising" : d.direction === "FALLING" ? "Vol Falling" : "Vol Flat";

  return (
    <div className="wti-panel">
      <div className="wti-header">
        <h2>WTI Crude Oil — HAR-IV Vol Forecast</h2>
        <span className="wti-price">${d.price?.toFixed(2) ?? "—"}</span>
        <span className="wti-asof">{new Date(d.as_of).toLocaleString() || "—"}</span>
      </div>

      <div className="wti-grid">
        <div className="wti-card">
          <div className="wti-label">Forecast (next week)</div>
          <div className="wti-value">{d.forecast_pct?.toFixed(1) ?? "—"}%</div>
          <div className="wti-sub">annualized realized vol</div>
        </div>
        <div className="wti-card">
          <div className="wti-label">Direction</div>
          <div className="wti-value" style={{ color: dirColor }}>{dirLabel}</div>
          <div className="wti-sub">confidence {d.direction_conf?.toFixed(0) ?? "—"}%</div>
        </div>
        <div className="wti-card">
          <div className="wti-label">Realized Vol (5d)</div>
          <div className="wti-value">{d.realized_rv5?.toFixed(1) ?? "—"}%</div>
          <div className="wti-sub">annualized</div>
        </div>
        <div className="wti-card">
          <div className="wti-label">Realized Vol (22d)</div>
          <div className="wti-value">{d.realized_rv22?.toFixed(1) ?? "—"}%</div>
          <div className="wti-sub">annualized</div>
        </div>
        <div className="wti-card">
          <div className="wti-label">Realized Vol (66d)</div>
          <div className="wti-value">{d.realized_rv66?.toFixed(1) ?? "—"}%</div>
          <div className="wti-sub">annualized</div>
        </div>
        <div className="wti-card">
          <div className="wti-label">OVX (oil vol index)</div>
          <div className="wti-value">{d.ovx?.toFixed(1) ?? "—"}</div>
          <div className="wti-sub">CBOE crude oil ETF vol</div>
        </div>
      </div>

      <div className="wti-foot">
        Model: HAR-RV(5/22/66) + OVX regime blend · Data: yfinance (CL=F, ^OVX) · Next refresh 30s
      </div>
    </div>
  );
}
