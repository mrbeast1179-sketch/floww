const fmt = (n, digits = 2) => {
  if (n == null || isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toFixed(digits)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(digits)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(digits)}K`;
  return n.toFixed(digits);
};

const ROWS = [
  { k: "delta", label: "Δ Delta", hint: "Net directional exposure" },
  { k: "gamma", label: "Γ Gamma", hint: "Rate of delta change" },
  { k: "vega", label: "ν Vega", hint: "Per 1% IV move" },
  { k: "theta", label: "Θ Theta", hint: "Per day" },
  { k: "vanna", label: "Vanna", hint: "Δ change per IV move" },
  { k: "charm", label: "Charm", hint: "Δ decay per day" },
  { k: "vomma", label: "Vomma", hint: "ν convexity" },
];

export default function GreeksAggregateTable({ totals, summary, kingNode, gammaFlip }) {
  return (
    <div className="glass rounded-lg p-5 h-full" data-testid="greeks-aggregate">
      <div className="flex items-end justify-between mb-3">
        <div>
          <div className="text-[10px] tracking-[0.25em] uppercase text-zinc-500">Market Net</div>
          <div className="text-lg font-semibold text-zinc-100">Aggregate Greeks</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-4 text-[11px]">
        <Block label="Net GEX" value={fmt(summary?.net_gex)} accent={summary?.net_gex >= 0 ? "yellow" : "purple"} />
        <Block label="Net VEX" value={fmt(summary?.net_vex)} />
        <Block label="Net DEX" value={fmt(summary?.net_dex)} />
        <Block label="P/C Ratio" value={summary?.pcr_oi?.toFixed?.(2) ?? "—"} />
      </div>

      <div className="space-y-1" data-testid="greeks-rows">
        {ROWS.map((row) => {
          const v = totals?.[row.k];
          const positive = v >= 0;
          return (
            <div key={row.k} className="flex items-center justify-between border border-zinc-900 rounded-md px-3 py-2 bg-black/30 hover:bg-black/50 transition-colors">
              <div>
                <div className="text-sm text-zinc-200 font-medium">{row.label}</div>
                <div className="text-[10px] text-zinc-500">{row.hint}</div>
              </div>
              <div className={`tick text-sm font-semibold ${positive ? "text-yellow-300" : "text-purple-400"}`}>
                {fmt(v, 3)}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-[11px]">
        <Block label="Call OI" value={fmt(totals?.call_oi, 1)} />
        <Block label="Put OI" value={fmt(totals?.put_oi, 1)} />
      </div>
    </div>
  );
}

function Block({ label, value, accent }) {
  const color = accent === "yellow" ? "text-yellow-300" : accent === "purple" ? "text-purple-400" : "text-zinc-200";
  return (
    <div className="border border-zinc-900 rounded-md px-2.5 py-1.5 bg-black/30">
      <div className="text-[9px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`text-sm font-semibold tick ${color}`}>{value}</div>
    </div>
  );
}
