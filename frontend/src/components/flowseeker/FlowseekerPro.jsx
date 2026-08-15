/**
 * FlowseekerPro.jsx — Complete BladeMap-style FlowSeeker Pro screener
 *
 * Integrates: FilterBar, StatsBar, ScreenerTable, FlowEngine
 * Fetches LIVE options flow from /api/flowseeker/live with 5s polling.
 * Synthetic data is used as a fallback ONLY when the backend returns
 * zero prints (so users see a populated UI rather than an empty table).
 */
import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { List } from 'react-window';
import { useFlowseeker } from '../../hooks/useFlowseeker';
import { syntheticDataGenerator as generateSyntheticFlowEvents, formatMoney as fmtMoney, formatTime as fmtTime, formatExpiry as fmtDate, dteOf, sentimentLabel } from './FlowEngine';
import InstitutionalAlertsPanel from './InstitutionalAlertsPanel';
import './FlowseekerPro.css';

/**
 * Map a raw cvserver/options-flow print into the 17-column Flowseeker
 * table row shape that the existing Row component expects.
 */
function mapPrintToRow(print) {
  return {
    id: print.id || print.key || Math.random().toString(36),
    timestamp: print.timestamp || print.asof_ts || Date.now() / 1000,
    ticker: print.ticker || '',
    side: print.side || (print.delta > 0 ? 'BUY' : 'SELL'),
    option_type: print.option_type || print.type || 'CALL',
    flow_type: print.flow_type || print.classification || 'SWEEP',
    strike: print.strike || 0,
    expiry: print.expiry || print.exp || new Date().toISOString().split('T')[0],
    dte: print.dte || 0,
    otm_pct: print.otm_pct || 0,
    contracts: print.contracts || print.size || 0,
    premium: print.premium || 0,
    notional: print.notional || 0,
    vol_vs_oi: print.vol_vs_oi || print.vol_oi || 0,
    delta: print.delta || 0,
    total_delta: print.total_delta || print.delta * print.contracts || 0,
    total_gamma: print.gamma || print.total_gamma || 0,
    total_vega: print.vega || 0,
    total_notional_delta: print.total_notional_delta || 0,
    flow_score: print.flow_score || print.score || 50,
    iv: print.iv || 0,
    oi: print.oi || 0,
    oi_change: print.oi_change || 0,
    oi_change_pct: print.oi_change_pct || 0,
    directionConfidence: print.directionConfidence || 0.5,
    sentiment: print.sentiment || 'NEUTRAL',
    sentiment_color: print.sentiment_color || '#94a3b8',
    greeks: {
      theta: print.greeks?.theta || print.theta || 0,
      vanna: print.greeks?.vanna || print.vanna || 0,
      charm: print.greeks?.charm || print.charm || 0,
    },
  };
}

// Helper: Map timeRange to date parameter for historical queries
function getDateParam(timeRange) {
  const now = new Date();
  switch(timeRange) {
    case 'yesterday':
      const d1 = new Date(now);
      d1.setDate(now.getDate() - 1);
      return d1.toISOString().split('T')[0];
    case '2_days_ago':
      const d2 = new Date(now);
      d2.setDate(now.getDate() - 2);
      return d2.toISOString().split('T')[0];
    case '3_days_ago':
      const d3 = new Date(now);
      d3.setDate(now.getDate() - 3);
      return d3.toISOString().split('T')[0];
    default:
      return null;
  }
}

// Helper: Get human-readable label for timeRange
function getTimeRangeLabel(timeRange) {
  switch(timeRange) {
    case 'yesterday': return 'Yesterday';
    case '2_days_ago': return '2 Days Ago';
    case '3_days_ago': return '3 Days Ago';
    case 'today': return 'Today (Live)';
    default: return timeRange.replace('_', ' ').split(' ')[0];
  }
}

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
        <option value="today">Today (Live)</option>
        <option value="yesterday">Yesterday</option>
        <option value="2_days_ago">2 Days Ago</option>
        <option value="3_days_ago">3 Days Ago</option>
        <option value="1h">Last Hour</option>
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

  // Fetch REAL options flow from backend with auto-refresh. Falls back to
  // synthetic data ONLY when the backend returns zero prints (so users see
  // a populated UI rather than an empty table).
  const {
    data: liveData,
    loading: liveLoading,
    error: liveError,
    refresh: refreshLive,
  } = useFlowseeker('live', {
    refreshMs: active && !['yesterday', '2_days_ago', '3_days_ago'].includes(filters.timeRange) ? 5000 : 0,
    skip: !active,
    date: getDateParam(filters.timeRange),
    limit: 300,
  });

  // Map live prints to table rows, fall back to synthetic when empty
  const [events, setEvents] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const [usingSynthetic, setUsingSynthetic] = useState(false);
  const newIdsRef = useRef(new Set());
  const listRef = useRef(null);

  useEffect(() => {
    if (!active) return;
    if (liveLoading || liveError) return;
    if (!liveData) {
      // No data yet — show synthetic so UI isn't empty
      const result = generateSyntheticFlowEvents({ eventCount: 50 });
      const initial = Array.isArray(result) ? result : result.events || [];
      setEvents(initial);
      setUsingSynthetic(true);
      return;
    }
    const prints = liveData.prints || [];
    if (prints.length === 0) {
      // Backend has no prints — still show synthetic fallback
      const result = generateSyntheticFlowEvents({ eventCount: 50 });
      const initial = Array.isArray(result) ? result : result.events || [];
      setEvents(initial);
      setUsingSynthetic(true);
    } else {
      // Map real prints to table rows
      const mapped = prints.map(mapPrintToRow);
      setEvents(mapped);
      setUsingSynthetic(false);
      // Mark first 3 as new for animation
      mapped.slice(0, 3).forEach(e => newIdsRef.current.add(e.id));
      const timer = setTimeout(() => newIdsRef.current.clear(), 3000);
      return () => clearTimeout(timer);
    }
  }, [liveData, liveLoading, liveError, active]);

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
        <span className="fsp-live-badge">
          <i className={`fsp-live-dot ${usingSynthetic ? 'synthetic' : liveError ? 'error' : ''}`} />
          {usingSynthetic ? 'LIVE · Fallback (demo)' : liveError ? 'LIVE · Error' : 'LIVE · Real Flow'}
        </span>
      </div>

      {/* Conviction v2 institutional feed — the server-side engine's
          persisted alerts (spread demoted, CW-confirmed, BH-FDR-screened,
          prime-bracketed). Subscribes to /alerts/feed + /alerts/quality and
          surfaces every tier, chip, and the calibration strip. */}
      <InstitutionalAlertsPanel active={active} days={7} limit={100} />

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
