import { useMemo } from "react";

const fmt = (n, d = 1) => {
  if (n == null) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e6) return `${(n / 1e6).toFixed(d)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(d)}K`;
  return n.toFixed(d);
};

export default function StrikeTable({ strikes, spot }) {
  const sorted = useMemo(() => {
    return [...strikes].sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex)).slice(0, 8);
  }, [strikes]);

  return (
    <div className="glass rounded-lg p-5 h-full" data-testid="strike-table">
      <div className="flex items-end justify-between mb-3">
        <div>
          <div className="text-[10px] tracking-[0.25em] uppercase text-zinc-500">High-Impact</div>
          <div className="text-lg font-semibold text-zinc-100">Top Strikes by |GEX|</div>
        </div>
      </div>
      <div className="overflow-hidden rounded-md border border-zinc-900">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="bg-black/40 text-zinc-500 text-[10px] uppercase tracking-wider">
              <th className="text-left px-3 py-2">Strike</th>
              <th className="text-right px-3 py-2">GEX</th>
              <th className="text-right px-3 py-2">VEX</th>
              <th className="text-right px-3 py-2">Call OI</th>
              <th className="text-right px-3 py-2">Put OI</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const above = r.strike > spot;
              return (
                <tr key={r.strike} className="border-t border-zinc-900 hover:bg-black/30" data-testid={`strike-row-${r.strike}`}>
                  <td className="px-3 py-2 tick text-zinc-200 font-medium">
                    <span className={`inline-block w-1.5 h-1.5 rounded-full mr-2 ${above ? "bg-cyan-400" : "bg-zinc-600"}`} />
                    ${r.strike}
                  </td>
                  <td className={`px-3 py-2 text-right tick font-semibold ${r.gex >= 0 ? "text-yellow-300" : "text-purple-400"}`}>{fmt(r.gex)}</td>
                  <td className={`px-3 py-2 text-right tick ${r.vex >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{fmt(r.vex)}</td>
                  <td className="px-3 py-2 text-right tick text-zinc-400">{fmt(r.call_oi)}</td>
                  <td className="px-3 py-2 text-right tick text-zinc-400">{fmt(r.put_oi)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-zinc-500 mt-3">Cyan dot = above spot. Magnitude ordered by absolute gamma exposure.</p>
    </div>
  );
}
