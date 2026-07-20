/**
 * FlowseekerPro.jsx — Complete BladeMap-style FlowSeeker Pro screener
 * 
 * Integrates: FilterBar, StatsBar, ScreenerTable, FlowEngine
 * Uses synthetic data generator for demo (no live trade stream from cvforge)
 * 17-column table with virtual scrolling, row expansion, real-time updates
 */
import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { List } from 'react-window';
import { syntheticDataGenerator as generateSyntheticFlowEvents, formatMoney as fmtMoney, formatTime as fmtTime, formatExpiry as fmtDate, dteOf, sentimentLabel } from './FlowEngine';
import InstitutionalAlertsPanel from './InstitutionalAlertsPanel';
import './FlowseekerPro.css';

// ── Filter Bar ───────────────────────────────────────────────────────
function FilterBar({ filters, onChange, onReset }) {
  const set = (k, v) => onChange({ ...filters, [k]: v });
  return (
    <div className="fsp-filter-bar">
      <input className="fsp-search" placeholder="Search tickers…" value={filters.search}
        onChange={e => set('search', e.target.value)} />
      <select className="fsp-select" value={filters.side} onChange={e => set('side', e.target.value)}>
        <option value="all">All Sides</option><option value="BUY">Buy</option><option value="SELL">Sell</option>
      </select>
      <select className="fsp-select" value={filters.flowType} onChange={e => set('flowType', e.target.value)}>
        <option value="all">All Flows</option><option value="SWEEP">Sweep</option>
        <option value="BLOCK">Block</option><option value="SPLIT">Split</option><option value="VWAP_ALGO">VWAP Algo</option>
      </select>
      <select className="fsp-select" value={filters.optionType} onChange={e => set('optionType', e.target.value)}>
        <option value="all">Calls + Puts</option><option value="CALL">Calls</option><option value="PUT">Puts</option>
      </select>
      <div className="fsp-range"><span>DTE</span>
        <input type="number" className="fsp-input-sm" value={filters.dteMin} onChange={e => set('dteMin', +e.target.value)} placeholder="0" />
        <span>–</span>
        <input type="number" className="fsp-input-sm" value={filters.dteMax} onChange={e => set('dteMax', +e.target.value)} placeholder="365" />
      </div>
      <input className="fsp-input" type="number" placeholder="Min Contracts" value={filters.minContracts}
        onChange={e => set('minContracts', +e.target.value)} />
      <input className="fsp-input" type="number" placeholder="Min Notional ($)" value={filters.minNotional}
        onChange={e => set('minNotional', +e.target.value)} />
      <div className="fsp-range"><span>Score</span>
        <input type="range" min="0" max="100" value={filters.minScore} onChange={e => set('minScore', +e.target.value)} />
        <span className="fsp-range-val">{filters.minScore}</span>
      </div>
      <div className="fsp-range"><span>OTM%</span>
        <input type="number" className="fsp-input-sm" value={filters.otmMin} onChange={e => set('otmMin', +e.target.value)} placeholder="-50" />
        <span>–</span>
        <input type="number" className="fsp-input-sm" value={filters.otmMax} onChange={e => set('otmMax', +e.target.value)} placeholder="50" />
      </div>
      <select className="fsp-select" value={filters.timeRange} onChange={e => set('timeRange', e.target.value)}>
        <option value="today">Today</option><option value="1h">Last Hour</option>
        <option value="30m">Last 30min</option><option value="pre">Pre-Market</option>
        <option value="after">After-Hours</option>
      </select>
      <button className="fsp-reset" onClick={onReset}>Reset</button>
    </div>
  );
}

// ── Stats Bar ────────────────────────────────────────────────────────
function StatsBar({ events }) {
  const stats = useMemo(() => {
    if (!events.length) return null;
    const totalNotional = events.reduce((s, e) => s + (e.notional || 0), 0);
    const buyCount = events.filter(e => e.side === 'BUY').length;
    const avgScore = events.reduce((s, e) => s + (e.flow_score || 0), 0) / events.length;
    const byTicker = {};
    events.forEach(e => { byTicker[e.ticker] = (byTicker[e.ticker] || 0) + (e.notional || 0); });
    const topTicker = Object.entries(byTicker).sort((a, b) => b[1] - a[1])[0]?.[0] || '—';
    return { count: events.length, totalNotional, buyPct: buyCount / events.length, avgScore: avgScore.toFixed(0), topTicker, uniqueTickers: Object.keys(byTicker).length };
  }, [events]);

  if (!stats) return null;
  return (
    <div className="fsp-stats-bar">
      <span className="fsp-stat"><label>Flows</label><b>{stats.count.toLocaleString()}</b></span>
      <span className="fsp-stat"><label>Notional</label><b>{fmtMoney(stats.totalNotional)}</b></span>
      <span className="fsp-stat"><label>Buy/Sell</label>
        <div className="fsp-ratio"><div className="fsp-ratio-buy" style={{ width: `${stats.buyPct * 100}%` }} /></div>
      </span>
      <span className="fsp-stat"><label>Avg Score</label><b style={{ color: sentimentLabel(+stats.avgScore).color }}>{stats.avgScore}</b></span>
      <span className="fsp-stat"><label>Top</label><b>{stats.topTicker}</b></span>
      <span className="fsp-stat"><label>Tickers</label><b>{stats.uniqueTickers}</b></span>
    </div>
  );
}

// ── Flow Score Circle ────────────────────────────────────────────────
function FlowScoreCircle({ score }) {
  const s = sentimentLabel(score);
  const r = 14, c = 2 * Math.PI * r, offset = c - (score / 100) * c;
  return (
    <svg width="32" height="32" className="fsp-score-svg">
      <circle cx="16" cy="16" r={r} fill="none" stroke="var(--fsp-border)" strokeWidth="3" />
      <circle cx="16" cy="16" r={r} fill="none" stroke={s.color} strokeWidth="3"
        strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
        transform="rotate(-90 16 16)" />
      <text x="16" y="16" textAnchor="middle" dy="4" fill={s.color} fontSize="9" fontWeight="700">{score}</text>
    </svg>
  );
}

// ── Row Component ────────────────────────────────────────────────────
const ROW_HEIGHT = 42;
function Row({ index, style, data }) {
  const event = data.events[index];
  if (!event) return null;
  const isNew = data.newIds.has(event.id);
  const isExpanded = data.expandedId === event.id;

  return (
    <>
      <div className={`fsp-row${isNew ? ' fsp-row-new' : ''}${isExpanded ? ' fsp-row-expanded' : ''}`}
        style={style} onClick={() => data.onToggleExpand(event.id)}>
        <span className="fsp-cell t">{fmtTime(event.timestamp)}</span>
        <span className="fsp-cell tk">{event.ticker}</span>
        <span className={`fsp-cell side ${event.side === 'BUY' ? 'buy' : 'sell'}`}>{event.side}</span>
        <span className={`fsp-cell type ${event.option_type === 'CALL' ? 'call' : 'put'}`}>
          {event.option_type === 'CALL' ? 'C' : 'P'}
        </span>
        <span className={`fsp-cell flow ${event.flow_type.toLowerCase()}`}>{event.flow_type}</span>
        <span className="fsp-cell num">${event.strike.toFixed(2)}</span>
        <span className="fsp-cell">{fmtDate(event.expiry)}</span>
        <span className={`fsp-cell num dte${event.dte <= 5 ? ' hot' : ''}`}>{event.dte}</span>
        <span className={`fsp-cell num otm${event.otm_pct > 20 ? ' high' : ''}`}>{event.otm_pct.toFixed(1)}%</span>
        <span className="fsp-cell num">{event.contracts.toLocaleString()}</span>
        <span className="fsp-cell num">{fmtMoney(event.premium)}</span>
        <span className="fsp-cell num bold">{fmtMoney(event.notional)}</span>
        <span className={`fsp-cell num voi${event.vol_vs_oi > 0.5 ? ' hot' : ''}`}>{event.vol_vs_oi.toFixed(1)}x</span>
        <span className="fsp-cell num">{event.total_delta > 0 ? '+' : ''}{fmtMoney(event.total_delta)}</span>
        <span className="fsp-cell num">{event.total_gamma.toFixed(2)}</span>
        <span className="fsp-cell"><FlowScoreCircle score={event.flow_score} /></span>
        <span className="fsp-cell exp" onClick={e => { e.stopPropagation(); data.onToggleExpand(event.id); }}>⟩</span>
      </div>
      {isExpanded && (
        <div className="fsp-row-detail" style={{ top: style.top + ROW_HEIGHT }}>
          <div className="fsp-detail-grid">
            <div><label>Delta (total)</label><span>{event.total_delta > 0 ? '+' : ''}{fmtMoney(event.total_delta)}</span></div>
            <div><label>Gamma (total)</label><span>{event.total_gamma.toFixed(4)}</span></div>
            <div><label>Vega (total)</label><span>{event.total_vega > 0 ? '+' : ''}{fmtMoney(event.total_vega)}</span></div>
            <div><label>Theta (per day)</label><span>{event.greeks.theta.toFixed(4)}</span></div>
            <div><label>Vanna</label><span>{event.greeks.vanna.toFixed(6)}</span></div>
            <div><label>Charm</label><span>{event.greeks.charm.toFixed(6)}</span></div>
            <div><label>IV</label><span>{event.iv}%</span></div>
            <div><label>OI Change</label><span>{event.oi_change > 0 ? '+' : ''}{event.oi_change.toLocaleString()} ({event.oi_change_pct}%)</span></div>
            <div><label>Direction Confidence</label><span>{(event.directionConfidence * 100).toFixed(0)}%</span></div>
            <div><label>Notional Delta</label><span>{fmtMoney(event.total_notional_delta)}</span></div>
            <div><label>Sentiment</label><span style={{ color: event.sentiment_color }}>{event.sentiment}</span></div>
          </div>
        </div>
      )}
    </>
  );
}

// ── Main Component ───────────────────────────────────────────────────
export default function FlowseekerPro({ active = true }) {
  const [filters, setFilters] = useState({
    search: '', side: 'all', flowType: 'all', optionType: 'all',
    dteMin: 0, dteMax: 365, minContracts: 0, minNotional: 0, minScore: 0,
    otmMin: -50, otmMax: 50, timeRange: 'today',
  });
  const [events, setEvents] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const newIdsRef = useRef(new Set());
  const listRef = useRef(null);

  // Generate synthetic data on mount
  useEffect(() => {
    if (!active) return;
    const result = generateSyntheticFlowEvents({ eventCount: 300 });
    const initial = Array.isArray(result) ? result : result.events || [];
    setEvents(initial);
    // Mark first 5 as "new" for animation
    initial.slice(0, 5).forEach(e => newIdsRef.current.add(e.id));
    const timer = setTimeout(() => newIdsRef.current.clear(), 3000);
    return () => clearTimeout(timer);
  }, [active]);

  // Filter events
  const filtered = useMemo(() => {
    return events.filter(e => {
      if (filters.search && !e.ticker.toLowerCase().includes(filters.search.toLowerCase())) return false;
      if (filters.side !== 'all' && e.side !== filters.side) return false;
      if (filters.flowType !== 'all' && e.flow_type !== filters.flowType) return false;
      if (filters.optionType !== 'all' && e.option_type !== filters.optionType) return false;
      if (e.dte < filters.dteMin || e.dte > filters.dteMax) return false;
      if (e.contracts < filters.minContracts) return false;
      if (e.notional < filters.minNotional) return false;
      if (e.flow_score < filters.minScore) return false;
      if (e.otm_pct < filters.otmMin || e.otm_pct > filters.otmMax) return false;
      return true;
    });
  }, [events, filters]);

  const handleReset = useCallback(() => {
    setFilters({ search: '', side: 'all', flowType: 'all', optionType: 'all', dteMin: 0, dteMax: 365, minContracts: 0, minNotional: 0, minScore: 0, otmMin: -50, otmMax: 50, timeRange: 'today' });
  }, []);

  const handleToggleExpand = useCallback((id) => {
    setExpandedId(prev => prev === id ? null : id);
  }, []);

  const listData = useMemo(() => ({
    events: filtered,
    newIds: newIdsRef.current,
    expandedId,
    onToggleExpand: handleToggleExpand,
  }), [filtered, expandedId, handleToggleExpand]);

  return (
    <div className="fsp-root">
      <div className="fsp-header">
        <span className="fsp-brand">◢ FlowSeeker <b>Pro</b></span>
        <span className="fsp-live"><i />LIVE · SYNTHETIC DATA</span>
      </div>

      {/* Conviction v2 institutional feed — the server-side engine's
          persisted alerts (spread demoted, CW-confirmed, BH-FDR-screened,
          prime-bracketed). Subscribes to /alerts/feed + /alerts/quality and
          surfaces every tier, chip, and the calibration strip. */}
      <InstitutionalAlertsPanel active={active} days={7} limit={24} />

      <FilterBar filters={filters} onChange={setFilters} onReset={handleReset} />
      <StatsBar events={filtered} />
      <div className="fsp-table-wrap">
        <div className="fsp-thead">
          <span style={{ width: 90 }}>Time</span>
          <span style={{ width: 70 }}>Ticker</span>
          <span style={{ width: 60 }}>Side</span>
          <span style={{ width: 50 }}>Type</span>
          <span style={{ width: 70 }}>Flow</span>
          <span style={{ width: 70 }}>Strike</span>
          <span style={{ width: 65 }}>Exp</span>
          <span style={{ width: 45 }}>DTE</span>
          <span style={{ width: 55 }}>OTM%</span>
          <span style={{ width: 80 }}>Contracts</span>
          <span style={{ width: 90 }}>Premium</span>
          <span style={{ width: 100 }}>Notional</span>
          <span style={{ width: 60 }}>Vol/OI</span>
          <span style={{ width: 75 }}>Δ Delta</span>
          <span style={{ width: 75 }}>Γ Gamma</span>
          <span style={{ width: 85 }}>Score</span>
          <span style={{ width: 40 }}></span>
        </div>
        {filtered.length > 0 ? (
          <List ref={listRef} height={Math.min(600, filtered.length * ROW_HEIGHT + 2)}
            rowCount={filtered.length} rowHeight={ROW_HEIGHT}
            rowComponent={Row} rowData={listData} className="fsp-list" />
        ) : (
          <div className="fsp-empty">No flows match your filters.</div>
        )}
      </div>
    </div>
  );
}
