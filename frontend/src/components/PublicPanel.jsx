import React, { useEffect, useState } from "react";
import { API } from "../config/api";
import "./MarketPanels.css";

export default function PublicPanel() {
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState([]);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const fetchAll = async () => {
      try {
        const [acctRes, posRes, ordRes] = await Promise.all([
          fetch(`${API}/public/brokerage/account`),
          fetch(`${API}/public/brokerage/portfolio`),
          fetch(`${API}/public/brokerage/orders`),
        ]);
        if (!cancelled) {
          const acct = await acctRes.json();
          const pos = await posRes.json();
          const ord = await ordRes.json();
          // The 3rd agent's /api/public/portfolio nests positions under .portfolio
          setAccount(acct);
          setPositions((pos.portfolio && pos.portfolio.positions) || (pos.positions || []));
          setOrders((ord.orders && ord.orders.orders) || (ord.orders || []));
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchAll();
    const id = setInterval(fetchAll, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (loading) return <div className="pub-loading">Loading Public.com account…</div>;
  if (error) return <div className="pub-error">Public.com feed error: {error}</div>;

  const connected = account?.ok && !error;
  const accountValue = account?.account_value ?? 0;
  const buyingPower = account?.buying_power ?? 0;
  const cash = account?.cash ?? 0;
  const pnl = positions.reduce((s, p) => s + (p.pnl || 0), 0);
  const dayPnl = positions.reduce((s, p) => s + ((p.market_value * (p.day_gain_pct || 0)) / 100), 0);

  const byType = {};
  for (const p of positions) {
    const t = p.asset_type || "STOCK";
    (byType[t] = byType[t] || 0) + (p.market_value || 0);
  }
  const typeRows = Object.entries(byType).sort((a, b) => b[1] - a[1]);

  return (
    <div className="pub-panel">
      <div className="pub-header">
        <h2>Public.com Brokerage</h2>
        <span className={`pub-status ${connected ? "connected" : "disconnected"}`}>
          {connected ? "● Connected" : "○ Not connected"}
        </span>
        {connected && (
          <span className="pub-asof">{new Date().toLocaleTimeString()}</span>
        )}
      </div>

      {!connected && (
        <div className="pub-no-conn">
          Public.com API key not configured. Generate a secret key at{" "}
          <a href="https://public.com/settings/security/api" target="_blank" rel="noreferrer">
            public.com/settings/security/api
          </a>{" "}
          and set PUBLIC_API_KEY in the backend environment.
        </div>
      )}

      {connected && (
        <>
          <div className="pub-metrics">
            <div className="pub-metric">
              <div className="pub-metric-label">Account Value</div>
              <div className="pub-metric-value">${accountValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            </div>
            <div className="pub-metric">
              <div className="pub-metric-label">Buying Power</div>
              <div className="pub-metric-value">${buyingPower.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            </div>
            <div className="pub-metric">
              <div className="pub-metric-label">Cash</div>
              <div className="pub-metric-value">${cash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            </div>
            <div className="pub-metric">
              <div className="pub-metric-label">Today P&L</div>
              <div className="pub-metric-value" style={{ color: dayPnl >= 0 ? "var(--pos)" : "var(--neg)" }}>
                {dayPnl >= 0 ? "+" : ""}${dayPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
            <div className="pub-metric">
              <div className="pub-metric-label">Total P&L</div>
              <div className="pub-metric-value" style={{ color: pnl >= 0 ? "var(--pos)" : "var(--neg)" }}>
                {pnl >= 0 ? "+" : ""}${pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
            <div className="pub-metric">
              <div className="pub-metric-label">Positions</div>
              <div className="pub-metric-value">{positions.length}</div>
            </div>
          </div>

          {typeRows.length > 0 && (
            <div className="pub-types">
              <div className="pub-types-label">Exposure by asset type</div>
              <div className="pub-types-grid">
                {typeRows.map(([t, v]) => (
                  <div key={t} className="pub-type-chip">
                    <span className="pub-type-name">{t}</span>
                    <span className="pub-type-val">${v.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {positions.length > 0 && (
            <table className="pub-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>Market Value</th>
                  <th>Cost Basis</th>
                  <th>Total Gain</th>
                  <th>Day Gain</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.symbol} className="pub-row">
                    <td className="pub-sym">{p.symbol}</td>
                    <td className="pub-name">{p.name || "—"}</td>
                    <td className="mono">{p.quantity?.toLocaleString()}</td>
                    <td className="mono">
                      ${typeof p.current_price === "number"
                        ? p.current_price.toFixed(2)
                        : p.current_price || "—"}
                    </td>
                    <td className="mono">
                      ${(p.market_value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="mono">
                      ${(p.cost_basis || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="mono" style={{ color: (p.total_gain_pct || 0) >= 0 ? "var(--pos)" : "var(--neg)" }}>
                      {(p.total_gain_pct || 0) >= 0 ? "+" : ""}
                      {(p.total_gain_pct || 0).toFixed(2)}% (
                      ${(p.pnl || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })})
                    </td>
                    <td className="mono" style={{ color: (p.day_gain_pct || 0) >= 0 ? "var(--pos)" : "var(--neg)" }}>
                      {(p.day_gain_pct || 0) >= 0 ? "+" : ""}{(p.day_gain_pct || 0).toFixed(2)}%
                    </td>
                    <td>
                      <span className={`pub-type-badge ${p.asset_type?.toLowerCase() || "stock"}`}>
                        {p.asset_type || "STOCK"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {orders.length > 0 && (
            <div className="pub-orders">
              <div className="pub-orders-label">Recent Orders ({orders.length})</div>
              <table className="pub-orders-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Type</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Status</th>
                    <th>Filled</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.slice(0, 20).map((o) => (
                    <tr key={o.order_id}>
                      <td className="mono">{o.symbol}</td>
                      <td>{o.side}</td>
                      <td>{o.type}</td>
                      <td className="mono">{o.quantity?.toLocaleString()}</td>
                      <td className="mono">{o.price ? `$${o.price.toFixed(2)}` : "—"}</td>
                      <td>
                        <span className={`pub-status-badge ${o.status?.toLowerCase().replace(" ", "-")}`}>
                          {o.status}
                        </span>
                      </td>
                      <td className="mono">
                        {o.filled_at ? new Date(o.filled_at).toLocaleTimeString() : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <div className="pub-foot">
        Data: Public.com Trading API · Paper trading only by default · Refreshes every 30s
      </div>
    </div>
  );
}
