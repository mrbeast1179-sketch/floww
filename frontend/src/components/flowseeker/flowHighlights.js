export function classificationBadge(c) {
  switch (String(c || "").toLowerCase()) {
    case "sweep":   return { label: "SWP", className: "text-amber-400 bg-amber-500/20" };
    case "block":   return { label: "BLK", className: "text-rose-400 bg-rose-500/20" };
    case "unusual": return { label: "UNU", className: "text-sky-400 bg-sky-500/20" };
    default:        return null; // "regular" or unknown -> no badge
  }
}

export function rowHighlightClass(p) {
  const size = Number(p?.size) || 0, oi = Number(p?.oi) || 0, volume = Number(p?.volume) || 0;
  const voi = Number(p?.vol_oi_ratio) || 0;
  if (voi > 2.0 || Number(p?.premium) > 100000) return "bg-sky-500/5";
  if (size > oi && oi > 0) return "bg-amber-500/5";
  if (volume > oi && oi > 0) return "bg-emerald-500/5";
  return "";
}

export function typeColor(t) {
  const s = String(t || "").toUpperCase();
  if (s.startsWith("C")) return "text-emerald-400";
  if (s.startsWith("P")) return "text-rose-400";
  return "text-slate-400";
}

export function sideColor(side) {
  const s = String(side || "").toLowerCase();
  if (s.includes("buy") || s.includes("ask")) return "text-emerald-400";
  if (s.includes("sell") || s.includes("bid")) return "text-rose-400";
  return "text-slate-400";
}
