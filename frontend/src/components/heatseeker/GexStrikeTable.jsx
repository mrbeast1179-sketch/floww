import React, { useMemo } from "react";
import { fmt, fmtAbs } from "../../lib/helpers";

const fmtK = (v) => fmtAbs(v);

export default function GexStrikeTable({ rows = [], spot }) {
  const maxAbs = useMemo(() => {
    let m = 1;
    for (const r of rows) {
      const g = Math.abs(r.call_gex || 0);
      const p = Math.abs(r.put_gex || 0);
      const n = Math.abs(r.gex || 0);
      if (g > m) m = g;
      if (p > m) m = p;
      if (n > m) m = n;
    }
    return m;
  }, [rows]);

  const sorted = useMemo(() => [...rows].sort((a, b) => (b?.strike ?? 0) - (a?.strike ?? 0)), [rows]);

  if (!sorted.length) return <div className="panel p-3 text-slate-500 text-xs">No strike data available</div>;

  return (
    <div className="gex-chain-wrap">
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
          {sorted.map((r) => {
            const strike = typeof r.strike === "number" ? r.strike : Number(r.strike || 0);
            const callGex = r.call_gex || 0;
            const putGex = r.put_gex || 0;
            const netGex = r.gex ?? callGex - putGex;

            const near = spot ? Math.abs(strike - spot) / spot < 0.01 : false;

            const flrPct = rows.length > 1 && spot
              ? (((spot - strike) / spot) * 100)
              : 0;

            return (
              <tr key={strike} className={`gex-row${near ? " gex-row-current" : ""}`}>
                <td className="gex-td gex-td-king">{typeof strike === "number" ? (strike < 10 ? strike.toFixed(2) : strike.toFixed(0)) : strike}</td>
                <td className={`gex-td gex-td-flr ${flrPct > 0 ? "text-emerald-400" : flrPct < 0 ? "text-rose-400" : ""}`}> {flrPct > 0 ? "+" : ""}{flrPct.toFixed(1)}%</td>
                <td className="gex-td gex-td-ceil">{callGex === 0 ? "$0.0K" : callGex >= 1e6 ? `$${(callGex / 1e6).toFixed(1)}M` : `$${(callGex / 1e3).toFixed(1)}K`}</td>
                <td className="gex-td gex-td-gate">{putGex === 0 ? "$0.0K" : putGex >= 1e6 ? `$${(putGex / 1e6).toFixed(1)}M` : `$${(putGex / 1e3).toFixed(1)}K`}</td>
                <td className="gex-td gex-td-air">$0.0K</td>
                <td className="gex-td gex-td-net">{netGex === 0 ? "$0.0K" : netGex >= 1e6 ? `$${(netGex / 1e6).toFixed(1)}M` : `$${(netGex / 1e3).toFixed(1)}K`}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
