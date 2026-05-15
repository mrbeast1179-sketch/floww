import React from "react";

const fmt = (n, d = 2) => (n === null || n === undefined || isNaN(n)) ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });

export default function VelocityGauge({ velocity }) {
  if (!velocity) return null;
  const score = velocity.velocity_score || 0;
  const warming = (velocity.snapshots_count || 0) < 3;
  const angle = score * 180 - 90;
  const color = warming ? "#64748b" : score > 0.4 ? "#ef4444" : score > 0.2 ? "#fbbf24" : "#34d399";
  return (
    <div className="panel-2 p-3" data-testid="velocity-gauge">
      <div className="label mb-2">Velocity Mode</div>
      <div className="flex items-center gap-3">
        <svg viewBox="0 0 100 60" width="100" height="60">
          <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke="#1f2a3a" strokeWidth="6" />
          <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke={color} strokeWidth="6"
            strokeDasharray={`${score * 125} 200`} strokeLinecap="round" />
          <line x1="50" y1="55" x2={50 + 35 * Math.cos((angle - 90) * Math.PI / 180)} y2={55 + 35 * Math.sin((angle - 90) * Math.PI / 180)} stroke={color} strokeWidth="2" />
          <circle cx="50" cy="55" r="3" fill={color} />
        </svg>
        <div>
          <div className="text-2xl font-bold mono" style={{ color }}>{warming ? "…" : (score * 100).toFixed(0)}</div>
          <div className="text-[10px] uppercase tracking-widest text-slate-500">{warming ? "warming up" : "rate of change"}</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-3 text-[11px]">
        <div>
          <div className="label">Floor</div>
          <div className={velocity.rolling_floor === "rolling_up" ? "text-emerald-400" : velocity.rolling_floor === "rolling_down" ? "text-rose-400" : "text-slate-400"}>
            {(velocity.rolling_floor || "stable").replace("_", " ")}
          </div>
        </div>
        <div>
          <div className="label">Ceiling</div>
          <div className={velocity.rolling_ceiling === "rolling_up" ? "text-emerald-400" : velocity.rolling_ceiling === "rolling_down" ? "text-rose-400" : "text-slate-400"}>
            {(velocity.rolling_ceiling || "stable").replace("_", " ")}
          </div>
        </div>
      </div>
      {velocity.floor_sequence?.length > 1 && (
        <div className="mt-2 text-[10px] text-slate-500">Floors: {velocity.floor_sequence.slice(0, 4).map(s => fmt(s, 0)).join(" → ")}</div>
      )}
      {velocity.ceiling_sequence?.length > 1 && (
        <div className="text-[10px] text-slate-500">Ceilings: {velocity.ceiling_sequence.slice(0, 4).map(s => fmt(s, 0)).join(" → ")}</div>
      )}
    </div>
  );
}
