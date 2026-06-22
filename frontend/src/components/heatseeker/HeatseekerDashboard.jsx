/**
 * HeatseekerDashboard.jsx — SKYLIT EDITION
 *
 * Major improvements:
 *   - Hero section: King Node + Spot + Regime at a glance
 *   - Two-column layout: Left = structural panels, Right = analytics
 *   - Better visual hierarchy with section headers
 *   - Pulsing live indicators
 *   - Color-coded gamma regime banner
 *   - Compact mode for smaller screens
 */

import React, { useMemo, useCallback, useState, useEffect, useRef, memo } from "react";
import { autoDecimate } from "../../utils/dataDecimator";

// ── Lazy-loaded below-the-fold rows ─────────────────────────────────

function LazyRow({ children, rootMargin = "200px" }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true); },
      { rootMargin }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [rootMargin]);
  return <div ref={ref}>{visible ? children : <div className="h-12" />}</div>;
}

// ── Stale Data Badge ─────────────────────────────────────────────────

export const StaleDataBadge = memo(function StaleDataBadge({ dataAge, dataFallback }) {
  if (!dataAge && !dataFallback) return null;
  const ageMin = dataAge != null ? Math.round(dataAge / 60000) : null;
  const show = dataFallback || (ageMin != null && ageMin >= 15);
  if (!show) return null;
  return (
    <span className="inline-flex items-center gap-1 text-[9px] uppercase tracking-widest font-bold px-2 py-0.5 rounded"
      style={{ background: "rgba(251,191,36,0.12)", border: "1px solid rgba(251,191,36,0.3)", color: "#fbbf24" }}>
      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
      Stale {ageMin != null ? `${ageMin}m` : ""}
    </span>
  );
});

// ── Offline Banner ───────────────────────────────────────────────────

export const OfflineBanner = memo(function OfflineBanner({ isOffline }) {
  if (!isOffline) return null;
  return (
    <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest font-bold px-3 py-1.5 mb-2 rounded-lg"
      style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#f87171" }}>
      <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
      Offline Mode — showing cached data
    </div>
  );
});

// ── Section Header ───────────────────────────────────────────────────

function SectionHeader({ title, badge, right }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        <div className="w-1 h-4 rounded-full bg-sky-500" />
        <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">{title}</h3>
        {badge}
      </div>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  );
}

// ── Stat Pill ─────────────────────────────────────────────────────────

function StatPill({ label, value, color = "sky" }) {
  const colorMap = {
    emerald: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    rose: "bg-rose-500/10 text-rose-400 border-rose-500/20",
    amber: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    sky: "bg-sky-500/10 text-sky-400 border-sky-500/20",
    purple: "bg-purple-500/10 text-purple-400 border-purple-500/20",
    teal: "bg-teal-500/10 text-teal-400 border-teal-500/20",
  };
  return (
    <div className={`px-2.5 py-1 rounded-lg border text-[10px] font-medium ${colorMap[color] || colorMap.sky}`}>
      <span className="text-slate-400 mr-1">{label}</span>
      <span className="font-bold">{value}</span>
    </div>
  );
}

// ── Gamma Regime Banner ──────────────────────────────────────────────

function GammaRegimeBanner({ data }) {
  if (!data) return null;
  const regime = data?.regime?.gex_regime || data?.gex_regime;
  if (!regime) return null;
  const isPositive = regime === "positive";
  const isNegative = regime === "negative";
  const color = isPositive ? "emerald" : isNegative ? "rose" : "amber";
  const label = isPositive ? "🟢 Positive Gamma" : isNegative ? "🔴 Negative Gamma" : "🟡 Neutral Gamma";
  const desc = isPositive
    ? "Dealers dampen volatility. Mean-reversion plays favored."
    : isNegative
    ? "Dealers amplify moves. Momentum trades favored."
    : "Mixed signals. Exercise caution.";

  return (
    <div className={`rounded-xl border p-3 mb-4`}
      style={{
        background: isPositive ? "rgba(52,211,153,0.05)" : isNegative ? "rgba(244,63,94,0.05)" : "rgba(251,191,36,0.05)",
        borderColor: isPositive ? "rgba(52,211,153,0.2)" : isNegative ? "rgba(244,63,94,0.2)" : "rgba(251,191,36,0.2)",
      }}>
      <div className="flex items-center justify-between">
        <div>
          <div className={`text-sm font-bold ${isPositive ? "text-emerald-400" : isNegative ? "text-rose-400" : "text-amber-400"}`}>
            {label}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">{desc}</div>
        </div>
        {data?.spot && (
          <div className="text-right">
            <div className="text-lg font-bold mono text-slate-200">{data.spot.toFixed(2)}</div>
            <div className="text-[9px] text-slate-500">SPOT</div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Import child panels ───────────────────────────────────────────────

import FlipZonesPanelBase from "./FlipZonesPanel";
import NodeLifecyclePanel from "./NodeLifecyclePanel";
import AirPocketsPanel from "./AirPocketsPanel";
import BeachBallIndicator from "./BeachBallIndicator";
import ReverseRugIndicator from "./ReverseRugIndicator";
import RainbowRoadIndicator from "./RainbowRoadIndicator";
import VelocityModeBadge from "./VelocityModeBadge";
import TrinityConfluenceMeter from "./TrinityConfluenceMeter";
import RollingFloorsCeilingsPanelBase from "./RollingFloorsCeilingsPanel";
import NodeClassificationPanelBase from "./NodeClassificationPanel";
import StackedNodesPanelBase from "./StackedNodesPanel";
import TugOfWarZonesPanelBase from "./TugOfWarZonesPanel";
import ErrorBoundary from "../ErrorBoundary";

const VannaChart = React.lazy(() => import("../VannaChart"));
const CharmChart = React.lazy(() => import("../CharmChart"));

export const FlipZonesPanel = memo(FlipZonesPanelBase);
export const RollingFloorsCeilingsPanel = memo(RollingFloorsCeilingsPanelBase);
export const NodeClassificationPanel = memo(NodeClassificationPanelBase);
export const StackedNodesPanel = memo(StackedNodesPanelBase);
export const TugOfWarZonesPanel = memo(TugOfWarZonesPanelBase);

// ── Hero Section ──────────────────────────────────────────────────────

function HeroSection({ ticker, spot, data, dataAge, dataFallback }) {
  const kongNode = data?.nodes?.find?.(n => n.type === "king") || data?.king_node;
  const netGex = data?.net_gex_total;
  const flipPoint = data?.flip_zones?.[0]?.price;

  return (
    <div className="rounded-xl border border-slate-700/30 bg-gradient-to-br from-slate-900/80 to-slate-900/40 p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs font-bold text-slate-200 uppercase tracking-wider">{ticker}</span>
          <span className="text-[9px] text-slate-500">Live</span>
        </div>
        <StaleDataBadge dataAge={dataAge} dataFallback={dataFallback} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-slate-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">Spot</div>
          <div className="text-xl font-bold mono text-slate-100">{spot ? spot.toFixed(2) : "—"}</div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">King Node</div>
          <div className="text-xl font-bold mono text-amber-400">{kongNode ? `$${Number(kongNode.strike || kongNode).toFixed(0)}` : "—"}</div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">Net GEX</div>
          <div className={`text-xl font-bold mono ${netGex > 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {netGex != null ? `${netGex >= 0 ? "+" : ""}${(netGex / 1e6).toFixed(1)}M` : "—"}
          </div>
        </div>
        <div className="bg-slate-800/30 rounded-lg p-2.5 text-center">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">Flip Point</div>
          <div className="text-xl font-bold mono text-purple-400">{flipPoint ? `$${flipPoint.toFixed(0)}` : "—"}</div>
        </div>
      </div>
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────

export default function HeatseekerDashboard({
  ticker = "SPY",
  spot = null,
  isOffline = false,
  dataAge = null,
  dataFallback = false,
}) {
  const handlePanelClick = useCallback((panelId) => {}, []);
  const normalizedTicker = useMemo(() => String(ticker).toUpperCase(), [ticker]);

  return (
    <div className="p-4 space-y-4" data-testid="heatseeker-dashboard">

      {/* Offline banner */}
      <OfflineBanner isOffline={isOffline} />

      {/* Hero section */}
      <HeroSection ticker={normalizedTicker} spot={spot} dataAge={dataAge} dataFallback={dataFallback} />

      {/* Gamma regime banner */}
      <GammaRegimeBanner data={{ spot }} />

      {/* ── Row 1: Pattern indicators ──────────────────────────────── */}
      <div>
        <SectionHeader title="Pattern Indicators" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <BeachBallIndicator ticker={normalizedTicker} />
          <ReverseRugIndicator ticker={normalizedTicker} />
          <RainbowRoadIndicator ticker={normalizedTicker} />
        </div>
      </div>

      {/* ── Row 2: Structural analysis ─────────────────────────────── */}
      <div>
        <SectionHeader title="Structural Analysis" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <FlipZonesPanel ticker={normalizedTicker} spot={spot} />
          <NodeLifecyclePanel ticker={normalizedTicker} />
          <AirPocketsPanel ticker={normalizedTicker} />
        </div>
      </div>

      {/* ── Row 3: Velocity + Trinity ───────────────────────────────── */}
      <div>
        <SectionHeader title="Confluence & Velocity" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <VelocityModeBadge ticker={normalizedTicker} />
          <TrinityConfluenceMeter />
        </div>
      </div>

      {/* ── Row 4: Wave 3 panels (lazy-loaded) ──────────────────────── */}
      <LazyRow>
        <SectionHeader title="Advanced Structure" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <RollingFloorsCeilingsPanel ticker={normalizedTicker} />
          <TugOfWarZonesPanel ticker={normalizedTicker} spot={spot} />
        </div>
      </LazyRow>

      {/* ── Row 5: Classification + Stacked (lazy-loaded) ───────────── */}
      <LazyRow>
        <SectionHeader title="Node Classification" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="lg:col-span-2">
            <NodeClassificationPanel ticker={normalizedTicker} />
          </div>
          <StackedNodesPanel ticker={normalizedTicker} />
        </div>
      </LazyRow>

      {/* ── Row 6: Vanna + Charm charts (code-split, lazy-loaded) ───── */}
      <LazyRow rootMargin="100px">
        <SectionHeader title="Greek Exposures" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <ErrorBoundary>
            <React.Suspense fallback={<div className="panel p-4 text-slate-500 text-xs">Loading Vanna chart…</div>}>
              <VannaChart ticker={normalizedTicker} spot={spot} />
            </React.Suspense>
          </ErrorBoundary>
          <ErrorBoundary>
            <React.Suspense fallback={<div className="panel p-4 text-slate-500 text-xs">Loading Charm chart…</div>}>
              <CharmChart ticker={normalizedTicker} spot={spot} />
            </React.Suspense>
          </ErrorBoundary>
        </div>
      </LazyRow>
    </div>
  );
}
