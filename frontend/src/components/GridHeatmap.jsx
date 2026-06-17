import React from "react";
import { fmt, fmtAbs, pctClass, tagFor, cellColor, expFmt, fmtCell } from "../lib/helpers";

export default function GridHeatmap({ data, filters, onCellClick, viewMode = "gex", skylitTheme = false }) {
  const spotRowRef = React.useRef(null);
  React.useEffect(() => {
    if (spotRowRef.current) spotRowRef.current.scrollIntoView({ block: "center", behavior: "auto" });
  }, [data?.ticker, data?.mode]);

  if (!data?.grid) return <div className="text-slate-500 text-xs p-4">No grid data</div>;
  const { spot, grid, nodes } = data;
  // Charm + vex grids are NESTED under grid.* per backend response shape (verified 2026-05-25).
  // Prior code destructured charm_grid from top-level data → got undefined → CHARM rendered empty.
  // Backend currently provides grid.charm_grid; grid.vex_grid is not yet implemented (falls back to gex).
  const charm_grid = grid.charm_grid;
  const vex_grid = grid.vex_grid;  // currently undefined; safe fallback below
  const expiries = grid.expiries || [];
  let strikes = (grid.strikes || []).slice().sort((a, b) => b - a);
  if (filters?.side === "above") strikes = strikes.filter(s => s > spot);
  if (filters?.side === "below") strikes = strikes.filter(s => s < spot);

  const cellOf = (e, s) => {
    const g = (viewMode === "charm" ? charm_grid
            : viewMode === "vex"   ? (vex_grid || grid.grid)
            : grid.grid) || {};
    const ge = g[e];
    if (!ge) return 0;
    return ge[String(Number.isInteger(s) ? s : s)] ?? ge[String(s)] ?? ge[String(s.toFixed(1))] ?? ge[String(parseInt(s))] ?? 0;
  };

  strikes = strikes.filter(s => expiries.some(e => Math.abs(cellOf(e, s)) > 0));

  if (filters?.lifecycle && filters.lifecycle !== "all") {
    const lifecycleStrikes = new Set((data.strikes || []).filter(s => s.lifecycle === filters.lifecycle).map(s => s.strike));
    strikes = strikes.filter(s => lifecycleStrikes.has(s));
  }

  let maxAbs = 1;
  for (const e of expiries) for (const s of strikes) { const v = cellOf(e, s); if (Math.abs(v) > maxAbs) maxAbs = Math.abs(v); }

  const kingStrike = nodes?.king?.strike;
  const floorSet = new Set((nodes?.floors || []).map(f => f.strike));
  const ceilSet = new Set((nodes?.ceilings || []).map(f => f.strike));
  const gkSet = new Set((nodes?.gatekeepers || []).map(f => f.strike));
  const inAir = (s) => (nodes?.air_pockets || []).some(a => s >= a.low && s <= a.high);
  const spotIdx = strikes.findIndex(s => s <= spot);

  return (
    <div className={`overflow-auto${skylitTheme ? ' skylit-grid-container' : ''}`} data-testid="grid-heatmap" style={{ maxHeight: skylitTheme ? "65vh" : "60vh" }}>
      <table className="border-collapse mono text-[10px]" style={{ borderSpacing: skylitTheme ? 0 : undefined }}>
        <thead className="sticky top-0 z-10" style={{ background: skylitTheme ? "#0d1225" : "var(--panel)" }}>
          <tr>
            <th className="px-1.5 py-1 text-left text-slate-500 sticky left-0 z-20" style={{ background: skylitTheme ? "#0d1225" : "var(--panel)", fontSize: skylitTheme ? 9 : undefined, letterSpacing: skylitTheme ? "0.05em" : undefined }}>Strike</th>
            {expiries.map((e) => <th key={e} className="px-1 py-1 text-slate-400 font-normal text-center" style={{ minWidth: skylitTheme ? 56 : 64, fontSize: skylitTheme ? 9 : undefined, letterSpacing: skylitTheme ? "0.03em" : undefined }}>{expFmt(e)}</th>)}
            <th className="px-1 py-1 text-slate-500 text-left" style={{ fontSize: skylitTheme ? 9 : undefined }}>Tags</th>
          </tr>
        </thead>
        <tbody>
          {strikes.map((s, i) => {
            const isKing = s === kingStrike;
            const isFloor = floorSet.has(s);
            const isCeil = ceilSet.has(s);
            const isGate = gkSet.has(s);
            const airy = inAir(s);
            const isATM = i === spotIdx;
            return (
              <React.Fragment key={s}>
                {isATM && (
                  <tr ref={spotRowRef} className={skylitTheme ? "skylit-atm-row" : undefined}>
                    <td colSpan={expiries.length + 2} style={{ padding: 0, height: skylitTheme ? 2 : undefined }}>
                      <div className="relative" style={{ height: 18 }}>
                        <div className="absolute inset-x-0 top-1/2" style={{ height: 1, background: skylitTheme ? "rgba(255,255,255,0.4)" : "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)", boxShadow: skylitTheme ? "0 0 8px rgba(255,255,255,0.3)" : "0 0 6px rgba(94,234,212,0.55)" }} />
                        {skylitTheme && <div className="absolute left-0 top-0" style={{ width: 0, height: 0, borderTop: "7px solid transparent", borderBottom: "7px solid transparent", borderLeft: "10px solid #ffffff" }} />}
                        <div className={`absolute ${skylitTheme ? 'left-3' : 'left-2'} top-0 text-[10px] font-bold tracking-widest ${skylitTheme ? 'text-white' : 'text-teal-300'} px-1`} style={{ background: skylitTheme ? "#0a0e1a" : "var(--panel)", textShadow: skylitTheme ? "0 0 4px rgba(255,255,255,0.4)" : "0 0 6px rgba(94,234,212,0.6)" }}>◆ SPOT {fmt(spot, 2)}</div>
                      </div>
                    </td>
                  </tr>
                )}
                <tr className={`${skylitTheme ? 'skylit-grid-row' : 'bar-row'}${airy ? " opacity-50" : ""}${skylitTheme && isATM ? " skylit-atm-highlight" : ""}`} data-testid={`grid-row-${s}`} style={skylitTheme && isATM ? { background: "rgba(255,255,255,0.04)" } : {}}>
                  <td className={`${skylitTheme ? 'px-1.5 py-0.5' : 'px-2 py-1'} font-bold sticky left-0 z-10 ${skylitTheme && isKing ? "text-fuchsia-300" : isKing ? "text-amber-300" : isFloor ? "text-emerald-400" : isCeil ? "text-rose-400" : isGate ? "text-sky-400" : "text-slate-400"}`} style={{ background: skylitTheme ? (isATM ? "rgba(10,14,26,0.95)" : "#0a0e1a") : "var(--panel)", fontSize: skylitTheme ? 10 : undefined }}>
                    {skylitTheme && isKing && <span className="mr-0.5" style={{ color: "#e040fb" }}>★</span>}
                    {fmt(s, s >= 1000 ? 0 : 1)}
                  </td>
                  {expiries.map((e) => {
                    const v = cellOf(e, s);
                    const isKingCell = isKing && Math.abs(v) > 0.6 * maxAbs;
                    const col = cellColor(v, maxAbs, isKingCell, viewMode, skylitTheme);
                    return (
                      <td key={e} className={`${skylitTheme ? 'text-right' : 'text-center'} cursor-pointer ${skylitTheme ? 'hover:ring-1 hover:ring-white/30' : 'hover:outline hover:outline-1 hover:outline-teal-400'}`} style={{ background: col.bg, color: col.text, minWidth: skylitTheme ? 54 : 60, padding: skylitTheme ? "1px 3px" : undefined, fontSize: skylitTheme ? 10 : undefined, fontFamily: skylitTheme ? "'JetBrains Mono', monospace" : undefined, fontVariantNumeric: skylitTheme ? "tabular-nums" : undefined }} onClick={() => onCellClick && onCellClick(s, e, v)} title={`strike ${s} · exp ${e} · ${viewMode === "charm" ? "charm" : "gex"} ${fmtCell(v)}`}>
                        {skylitTheme && isKingCell ? <span>★{fmtCell(v)}</span> : fmtCell(v)}
                      </td>
                    );
                  })}
                  <td className={skylitTheme ? "px-1 py-0.5" : "px-2 py-1"}>
                    <div className={`flex ${skylitTheme ? 'gap-0.5' : 'gap-1'} items-center`}>
                      {isKing && <span className="tag king">KING</span>}
                      {isFloor && <span className="tag floor">FLR</span>}
                      {isCeil && <span className="tag ceiling">CEIL</span>}
                      {isGate && <span className="tag gate">GATE</span>}
                      {airy && <span className="tag air">AIR</span>}
                    </div>
                  </td>
                </tr>
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
