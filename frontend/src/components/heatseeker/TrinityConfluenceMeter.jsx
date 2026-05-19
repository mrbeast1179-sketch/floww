import React from "react";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 2 — GET /api/heatseeker/trinity-confluence (no ticker arg)
 * Returns { score, aligned_dimensions, divergences, verdict }.
 *
 * Score is rendered as a 0-100 gauge; colour graduates from rose → amber → emerald.
 */
function scoreColor(s) {
  if (s >= 70) return { stroke: "#34d399", text: "text-emerald-400" };
  if (s >= 40) return { stroke: "#fbbf24", text: "text-amber-400" };
  return { stroke: "#f87171", text: "text-rose-400" };
}

export default function TrinityConfluenceMeter() {
  const { data, loading, error } = useHeatseeker("trinity-confluence", {});
  const score = Math.max(0, Math.min(100, Number(data?.score) || 0));
  const c = scoreColor(score);

  // Half-circle arc length: full = 125 (matches velocity-gauge style)
  const dash = (score / 100) * 125;

  const aligned = Array.isArray(data?.aligned_dimensions)
    ? data.aligned_dimensions
    : [];
  const divergences = Array.isArray(data?.divergences) ? data.divergences : [];

  return (
    <div className="panel p-3" data-testid="hs-trinity-confluence">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Trinity Confluence</div>
        <span className="text-[9px] text-slate-500">SPY · QQQ · SPX</span>
      </div>
      {loading && !data && <div className="text-slate-500 text-[11px]">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <>
          <div className="flex items-center gap-3 mb-2">
            <svg viewBox="0 0 100 60" width="110" height="66">
              <path
                d="M 10 55 A 40 40 0 0 1 90 55"
                fill="none"
                stroke="#1f2a3a"
                strokeWidth="6"
              />
              <path
                d="M 10 55 A 40 40 0 0 1 90 55"
                fill="none"
                stroke={c.stroke}
                strokeWidth="6"
                strokeDasharray={`${dash} 200`}
                strokeLinecap="round"
              />
            </svg>
            <div>
              <div className={`text-2xl font-bold mono ${c.text}`}>
                {score.toFixed(0)}
              </div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">
                {data.verdict || "—"}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <div>
              <div className="label text-emerald-400">Aligned</div>
              {aligned.length === 0 ? (
                <div className="text-slate-600">—</div>
              ) : (
                <ul className="space-y-0.5">
                  {aligned.map((d, i) => (
                    <li key={i} className="text-emerald-300 mono">
                      ✓ {d}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <div className="label text-rose-400">Divergent</div>
              {divergences.length === 0 ? (
                <div className="text-slate-600">—</div>
              ) : (
                <ul className="space-y-0.5">
                  {divergences.map((d, i) => (
                    <li key={i} className="text-rose-300 mono">
                      ✗ {d}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
