import React, { useEffect, useState } from "react";
import axios from "axios";
import { fmtAbs } from "../lib/helpers";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ALERT_TYPES = [
  { v: "gex_cross", l: "GEX Cross", desc: "Total GEX crosses threshold" },
  { v: "gex_spike", l: "GEX Spike", desc: "Single strike GEX spike" },
  { v: "oi_spike", l: "OI Spike", desc: "Open interest spike" },
  { v: "iv_spike", l: "IV Spike", desc: "Implied vol spike" },
];

export default function AlertsPanel({ ticker }) {
  const [rules, setRules] = useState([]);
  const [triggered, setTriggered] = useState([]);
  const [open, setOpen] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newRule, setNewRule] = useState({
    alert_type: "gex_cross", threshold: 0, direction: "below", label: "",
  });
  const [checkResult, setCheckResult] = useState(null);

  const fetchRules = async () => {
    try {
      const res = await axios.get(`${API}/alerts${ticker ? `?ticker=${ticker}` : ""}`);
      setRules(res.data.rules || []);
    } catch (e) { /* noop */ }
  };

  const checkAlerts = async () => {
    if (!ticker) return;
    try {
      const res = await axios.get(`${API}/alerts/check/${ticker}`);
      setTriggered(res.data.triggered || []);
      setCheckResult(res.data);
    } catch (e) { /* noop */ }
  };

  const createRule = async () => {
    if (!ticker) return;
    try {
      await axios.post(`${API}/alerts`, {
        ...newRule, ticker,
        threshold: Number(newRule.threshold),
      });
      setShowCreate(false);
      setNewRule({ alert_type: "gex_cross", threshold: 0, direction: "below", label: "" });
      fetchRules();
    } catch (e) { /* noop */ }
  };

  const deleteRule = async (id) => {
    try {
      await axios.delete(`${API}/alerts/${id}`);
      fetchRules();
    } catch (e) { /* noop */ }
  };

  // Fetch rules and check alerts on mount/ticker change (single effect to avoid double-fetch)
  useEffect(() => {
    if (!ticker) return;
    fetchRules();
    checkAlerts();
    const id = setInterval(checkAlerts, 30000);
    return () => clearInterval(id);
  }, [ticker]);

  return (
    <div className="panel-2 p-2">
      <button className="flex items-center justify-between w-full text-left" onClick={() => setOpen(!open)}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}>
        <div className="label mb-0">
          Alerts
          {triggered.length > 0 && (
            <span className="ml-1 text-[8px] px-1 py-px rounded bg-rose-500/20 text-rose-400 flash-pulse">
              {triggered.length} LIVE
            </span>
          )}
        </div>
        <span className="text-slate-500 text-[10px]">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5">
          {/* Triggered alerts */}
          {triggered.length > 0 && (
            <div className="bg-rose-500/10 rounded px-2 py-1.5 border border-rose-500/20">
              <div className="text-[9px] font-bold text-rose-400 mb-1">⚡ TRIGGERED</div>
              {triggered.map((t, i) => (
                <div key={i} className="text-[9px] text-rose-300 flex justify-between">
                  <span>{t.label || t.type}</span>
                  <span className="mono">{fmtAbs(t.value)} {t.direction} {fmtAbs(t.threshold)}</span>
                </div>
              ))}
            </div>
          )}

          {/* Active rules */}
          {rules.length > 0 && (
            <div className="space-y-1">
              {rules.map(r => (
                <div key={r.id} className="bg-slate-800/50 rounded px-2 py-1 flex justify-between items-center">
                  <div className="text-[9px]">
                    <div className="text-slate-300">{r.label || r.alert_type}</div>
                    <div className="text-slate-500">
                      {r.ticker} · {r.direction} {fmtAbs(r.threshold)}
                      {r.trigger_count > 0 && <span className="ml-1 text-amber-400">({r.trigger_count}x)</span>}
                    </div>
                  </div>
                  <button onClick={() => deleteRule(r.id)} className="text-slate-600 hover:text-rose-400 text-[10px]">✕</button>
                </div>
              ))}
            </div>
          )}

          {/* Create new */}
          {!showCreate ? (
            <button onClick={() => setShowCreate(true)} className="btn text-[9px] w-full">+ New Alert</button>
          ) : (
            <div className="bg-slate-800/50 rounded px-2 py-1.5 space-y-1">
              <select value={newRule.alert_type} onChange={e => setNewRule({...newRule, alert_type: e.target.value})}
                className="btn text-[9px] w-full px-1 py-0.5">
                {ALERT_TYPES.map(t => <option key={t.v} value={t.v}>{t.l}</option>)}
              </select>
              <input type="text" value={newRule.label} onChange={e => setNewRule({...newRule, label: e.target.value})}
                placeholder="Label (optional)" className="btn text-[9px] w-full px-1 py-0.5" />
              <div className="flex gap-1">
                <select value={newRule.direction} onChange={e => setNewRule({...newRule, direction: e.target.value})}
                  className="btn text-[9px] flex-1 px-1 py-0.5">
                  <option value="above">Above</option>
                  <option value="below">Below</option>
                </select>
                <input type="number" value={newRule.threshold} onChange={e => setNewRule({...newRule, threshold: e.target.value})}
                  placeholder="Threshold" className="btn text-[9px] flex-1 px-1 py-0.5" />
              </div>
              <div className="flex gap-1">
                <button onClick={createRule} className="btn text-[9px] flex-1 active">Create</button>
                <button onClick={() => setShowCreate(false)} className="btn text-[9px] flex-1">Cancel</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
