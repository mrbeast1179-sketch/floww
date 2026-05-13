import { useMemo } from "react";
import { Bar, BarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell } from "recharts";

const fmt = (n) => {
  const abs = Math.abs(n);
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toFixed(1);
};

export default function VEXHeatmap({ strikes, spot }) {
  const data = useMemo(() => strikes.map(r => ({ strike: r.strike, vex: r.vex })), [strikes]);
  const maxAbs = useMemo(() => Math.max(...data.map(d => Math.abs(d.vex)), 1), [data]);

  return (
    <div className="glass rounded-lg p-5" data-testid="vex-heatmap">
      <div className="flex items-end justify-between mb-3">
        <div>
          <div className="text-[10px] tracking-[0.25em] uppercase text-zinc-500">Vanna Exposure</div>
          <div className="text-lg font-semibold text-zinc-100">VEX by Strike</div>
        </div>
        <div className="flex items-center gap-4 text-[11px]">
          <div className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm bg-emerald-400" />+VEX (vol↓ → bid)</div>
          <div className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm bg-rose-500" />−VEX (vol↓ → offer)</div>
        </div>
      </div>
      <div className="h-[280px]" data-testid="vex-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 24 }}>
            <XAxis dataKey="strike" tick={{ fill: "#7e8590", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#1f232a" }} angle={-35} dy={10} interval={1} />
            <YAxis tickFormatter={fmt} tick={{ fill: "#7e8590", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#1f232a" }} domain={[-maxAbs, maxAbs]} />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
              contentStyle={{ background: "#0d0f12", border: "1px solid #23272e", borderRadius: 6, fontSize: 12 }}
              labelStyle={{ color: "#fafafa" }}
              formatter={(v) => [fmt(v), "VEX"]}
              labelFormatter={(l) => `Strike $${l}`}
            />
            <ReferenceLine y={0} stroke="#3a3f48" />
            <ReferenceLine x={spot} stroke="#22d3ee" strokeDasharray="3 3" />
            <Bar dataKey="vex" radius={[2, 2, 2, 2]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.vex >= 0 ? "#34d399" : "#f43f5e"} fillOpacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[11px] text-zinc-500 mt-2 leading-snug">
        +VEX below spot = supportive in vol compression. −VEX below spot = fragile floor — evaporates when vol settles.
      </p>
    </div>
  );
}
