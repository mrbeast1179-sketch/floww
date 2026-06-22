import React, { useMemo, useRef, useCallback, useEffect, useState } from "react";
import { fmtAbs } from "../../lib/helpers";

function fmtGex(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e6) return `$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(a / 1e3).toFixed(1)}K`;
  return `$${a.toFixed(0)}`;
}

const ROW_HEIGHT = 22;
const OVERSCAN = 6;

export default function GexStrikeTable({ rows = [], spot }) {
  const sorted = useMemo(
    () => [...rows].sort((a, b) => (b?.strike ?? 0) - (a?.strike ?? 0)),
    [rows]
  );

  const kingRow = useMemo(() => {
    if (!sorted.length) return null;
    let best = sorted[0];
    let bestAbs = 0;
    for (const r of sorted) {
      const p = Math.abs(r.put_gex || 0);
      if (p > bestAbs) { bestAbs = p; best = r; }
    }
    return best;
  }, [sorted]);

  const maxPut = useMemo(() => {
    let m = 1;
    for (const r of sorted) {
      const p = Math.abs(r.put_gex || 0);
      if (p > m) m = p;
    }
    return m;
  }, [sorted]);

  const wrapRef = useRef(null);
  const [viewport, setViewport] = useState({ start: 0, end: 40 });

  const onScroll = useCallback(() => {
    const el = wrapRef.current;
    if (!el) return;
    const start = Math.max(0, Math.floor(el.scrollTop / ROW_HEIGHT) - OVERSCAN);
    const end = Math.min(sorted.length, Math.ceil((el.scrollTop + el.clientHeight) / ROW_HEIGHT) + OVERSCAN);
    setViewport((v) => (v.start === start && v.end === end ? v : { start, end }));
  }, [sorted.length]);

  useEffect(() => {
    onScroll();
  }, [onScroll]);

  const visible = sorted.slice(viewport.start, viewport.end);
  const padTop = viewport.start * ROW_HEIGHT;
  const padBottom = Math.max(0, (sorted.length - viewport.end) * ROW_HEIGHT);

  if (!sorted.length)
    return <div className="panel p-3 text-slate-500 text-xs">No strike data available</div>;

  return (
    <div className="gex-chain-wrap" ref={wrapRef} onScroll={onScroll}>
      <table className="gex-chain-table">
        <thead>
          <tr>
            <th className="gex-th gex-th-king">KING</th>
            <th className="gex-th gex-th-flr">FLR %</th>
            <th className="gex-th gex-th-ceil">CEIL</th>
            <th className="gex-th gex-th-gate">GATE</th>
            <th className="gex-th gex-th-air">AIR</th>
            <th className="gex-th gex-th-net">+NET</th>
          </tr>
        </thead>
        <tbody>
          <tr aria-hidden="true" style={{ height: padTop }}>
            <td colSpan="6" style={{ padding: 0, border: "none" }} />
          </tr>
          {visible.map((r) => {
            const strike =
              typeof r.strike === "number" ? r.strike : Number(r.strike || 0);
            const callGex = r.call_gex || 0;
            const putGex = r.put_gex || 0;
            const netGex = r.gex ?? callGex - putGex;

            const isKing = kingRow && r.strike === kingRow.strike;
            const near = spot ? Math.abs(strike - spot) / spot < 0.01 : false;

            const flrPct = maxPut > 0 && putGex > 0 ? (putGex / maxPut) * 100 : 0;

            let rowCls = "gex-row";
            if (isKing) rowCls += " gex-row-king";
            else if (flrPct >= 99) rowCls += " gex-row-king";
            else if (flrPct >= 40) rowCls += " gex-row-extreme";
            else if (flrPct >= 10) rowCls += " gex-row-high";
            else if (flrPct >= 2) rowCls += " gex-row-low";
            if (near && !isKing) rowCls += " gex-row-near";

            return (
              <tr key={strike} className={rowCls} style={{ height: ROW_HEIGHT }}>
                <td className="gex-td gex-td-king">
                  {strike < 10 ? strike.toFixed(2) : typeof strike === "number" ? strike.toFixed(0) : strike}
                </td>
                <td
                  className={`gex-td gex-td-flr ${flrPct > 0 ? "text-emerald-400" : "text-rose-400"}`}
                >
                  {flrPct > 0 ? "+" : "-"}
                  {Math.abs(flrPct).toFixed(1)}%
                </td>
                <td className="gex-td gex-td-ceil">{fmtGex(callGex)}</td>
                <td className="gex-td gex-td-gate">{fmtGex(putGex)}</td>
                <td className="gex-td gex-td-air">$0.0K</td>
                <td className="gex-td gex-td-net" style={{ color: "#fbbf24" }}>
                  {fmtGex(netGex)}
                </td>
              </tr>
            );
          })}
          <tr aria-hidden="true" style={{ height: padBottom }}>
            <td colSpan="6" style={{ padding: 0, border: "none" }} />
          </tr>
        </tbody>
      </table>
    </div>
  );
}
