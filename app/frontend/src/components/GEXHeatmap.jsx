import { useMemo } from "react";
import { Bar, BarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell } from "recharts";

const fmt = (n) => {
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toFixed(0);
};

export default function GEXHeatmap({ strikes, spot, kingNode, gammaFlip }) {
  const data = useMemo(() => strikes.map(r => ({ ...r, strike: r.strike, gex: r.gex })), [strikes]);
  const maxAbs = useMemo(() => Math.max(...data.map(d => Math.abs(d.gex)), 1), [data]);

  return (
    <div className="glass rounded-lg p-5" data-testid="gex-heatmap">
      <div className="flex items-end justify-between mb-3">
        <div>
          <div className="text-[10px] tracking-[0.25em] uppercase text-zinc-500">Gamma Exposure</div>
          <div className="text-lg font-semibold text-zinc-100">GEX by Strike</div>
        </div>
        <div className="flex items-center gap-4 text-[11px]">
          <div className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm bg-yellow-300 glow-pika" />Pika (+GEX, stabilising)</div>
          <div className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm bg-purple-500 glow-barney" />Barney (−GEX, amplifying)</div>
        </div>
      </div>
      <div className="h-[360px]" data-testid="gex-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 24 }}>
            <XAxis dataKey="strike" tick={{ fill: "#7e8590", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#1f232a" }} angle={-35} dy={10} interval={1} />
            <YAxis tickFormatter={fmt} tick={{ fill: "#7e8590", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#1f232a" }} domain={[-maxAbs, maxAbs]} />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
              contentStyle={{ background: "#0d0f12", border: "1px solid #23272e", borderRadius: 6, fontSize: 12 }}
              labelStyle={{ color: "#fafafa" }}
              formatter={(v, n) => [fmt(v), "GEX ($γ)"]}
              labelFormatter={(l) => `Strike $${l}`}
            />
            <ReferenceLine y={0} stroke="#3a3f48" />
            <ReferenceLine x={spot} stroke="#22d3ee" strokeDasharray="3 3" label={{ value: `Spot ${spot?.toFixed?.(2)}`, position: "top", fill: "#22d3ee", fontSize: 11 }} />
            {kingNode != null && <ReferenceLine x={kingNode} stroke="#facc15" label={{ value: "King", position: "insideTopLeft", fill: "#facc15", fontSize: 11 }} />}
            {gammaFlip != null && <ReferenceLine x={gammaFlip} stroke="#a855f7" strokeDasharray="4 2" label={{ value: "γ-flip", position: "insideTopRight", fill: "#a855f7", fontSize: 11 }} />}
            <Bar dataKey="gex" radius={[2, 2, 2, 2]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.gex >= 0 ? "#facc15" : "#a855f7"} fillOpacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="grid grid-cols-3 gap-4 mt-3 text-[11px]">
        <Stat label="King Node" value={kingNode ? `$${kingNode}` : "—"} accent="yellow" />
        <Stat label="γ-Flip Zone" value={gammaFlip ? `$${gammaFlip}` : "—"} accent="purple" />
        <Stat label="Strikes Plotted" value={data.length} />
      </div>
    </div>
  );
}

function Stat({ label, value, accent }) {
  const color = accent === "yellow" ? "text-yellow-300" : accent === "purple" ? "text-purple-400" : "text-zinc-200";
  return (
    <div className="border border-zinc-900 rounded-md px-3 py-2 bg-black/30">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`text-base font-semibold tick ${color}`}>{value}</div>
    </div>
  );
}
