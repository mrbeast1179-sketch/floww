// ============ Formatting Helpers ============

export const fmt = (n, d = 2) => (n === null || n === undefined || isNaN(n)) ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });

export const fmtAbs = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toFixed(0);
};

export const fmtCell = (v) => {
  if (v === null || v === undefined || isNaN(v) || v === 0) return "";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  let s;
  if (a >= 1e6) s = (a / 1e6).toFixed(2) + "M";
  else if (a >= 1e3) s = (a / 1e3).toFixed(1) + "K";
  else s = a.toFixed(0);
  return sign + "$" + s;
};

export const pctClass = (v) => v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-slate-400";

export const tagFor = (kind) => ({
  king: "tag king", floor: "tag floor", ceiling: "tag ceiling", gate: "tag gate", air: "tag air",
  fresh: "tag fresh", tested: "tag tested", delivered: "tag delivered", decaying: "tag decaying",
}[kind] || "tag");

export const expFmt = (e) => { try { const [, m, d] = e.split("-"); return `${m}-${d}`; } catch { return e; } };

// ============ Color Scale ============
// Default GEX: teal (positive) / purple (negative). Zenith: VIRIDIS colormap.

// 8-stop VIRIDIS colormap. t in [0,1] -> {r,g,b}. Robust to NaN / out-of-range so
// cellColor() can never read .r/.g/.b off undefined (the bug that crashed Zenith:
// this function was called but never defined).
export function viridisColor(t) {
  const STOPS = [
    [68, 1, 84], [70, 50, 126], [54, 92, 141], [39, 127, 142],
    [31, 161, 135], [74, 193, 109], [159, 218, 58], [253, 231, 37],
  ];
  let x = Number(t);
  if (!Number.isFinite(x)) x = 0;
  x = Math.min(1, Math.max(0, x));
  const seg = x * (STOPS.length - 1);
  const i = Math.min(STOPS.length - 2, Math.floor(seg));
  const f = seg - i;
  const a = STOPS[i], b = STOPS[i + 1];
  return {
    r: Math.round(a[0] + (b[0] - a[0]) * f),
    g: Math.round(a[1] + (b[1] - a[1]) * f),
    b: Math.round(a[2] + (b[2] - a[2]) * f),
  };
}

export function cellColor(v, maxAbs, isKing = false, mode = "gex", skylitTheme = false) {
  if (!v || maxAbs === 0) {
    return skylitTheme
      ? { bg: "rgba(19, 23, 34, 0.85)", text: "#3a4566" }
      : { bg: "rgba(19, 23, 34, 0.7)", text: "#5a6781" };
  }
  const norm = Math.min(1, Math.abs(v) / maxAbs);

  if (mode === "charm") {
    if (isKing && v > 0) return { bg: `rgba(34, 211, 238, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (isKing && v < 0) return { bg: `rgba(168, 85, 247, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (v > 0) { const alpha = 0.15 + 0.7 * norm; return { bg: `rgba(34, 211, 238, ${alpha})`, text: norm > 0.5 ? "#0b1320" : "#a5f3fc" }; }
    else { const alpha = 0.18 + 0.7 * norm; return { bg: `rgba(168, 85, 247, ${alpha})`, text: norm > 0.5 ? "#fdf4ff" : "#e9d5ff" }; }
  }
  if (mode === "vex") {
    if (isKing && v > 0) return { bg: `rgba(251, 191, 36, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (isKing && v < 0) return { bg: `rgba(219, 39, 119, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (v > 0) { const alpha = 0.15 + 0.7 * norm; return { bg: `rgba(245, 158, 11, ${alpha})`, text: norm > 0.5 ? "#0b1320" : "#fcd34d" }; }
    else { const alpha = 0.18 + 0.7 * norm; return { bg: `rgba(219, 39, 119, ${alpha})`, text: norm > 0.5 ? "#fdf4ff" : "#f9a8d4" }; }
  }

  // ── Zenith VIRIDIS theme ──────────────────────────────────────
  if (skylitTheme) {
    if (isKing) {
      return { bg: `rgba(224, 64, 251, ${0.6 + 0.35 * norm})`, text: norm > 0.3 ? "#ffffff" : "#f5d0fe" };
    }
    if (v < 0 && norm > 0.85) {
      return { bg: `rgba(200, 50, 230, ${0.45 + 0.45 * norm})`, text: "#fce7fe" };
    }
    const t = v >= 0 ? 0.5 + 0.5 * norm : 0.5 - 0.5 * norm;
    const col = viridisColor(t);
    const alpha = 0.35 + 0.55 * norm;
    const luminance = 0.299 * col.r + 0.587 * col.g + 0.114 * col.b;
    return { bg: `rgba(${col.r}, ${col.g}, ${col.b}, ${alpha})`, text: luminance > 140 ? "#0a0e1a" : "#e2e8f0" };
  }

  // ── Default GEX theme (teal/purple) ───────────────────────────
  if (isKing && v > 0) return { bg: `rgba(190, 242, 100, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
  if (isKing && v < 0) return { bg: `rgba(232, 121, 249, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
  if (v > 0) { const alpha = 0.15 + 0.7 * norm; return { bg: `rgba(45, 212, 191, ${alpha})`, text: norm > 0.5 ? "#0b1320" : "#a7f3d0" }; }
  else { const alpha = 0.18 + 0.7 * norm; return { bg: `rgba(168, 85, 247, ${alpha})`, text: norm > 0.5 ? "#fdf4ff" : "#e9d5ff" }; }
}

// ============ Constants ============
export const TRIAD = ["^SPX", "SPY", "QQQ"];
export const DEFAULT_TICKERS = ["SPY", "QQQ", "^SPX", "IWM", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "KO", "XOM", "GM", "MCD", "^VIX"];
export const REFRESH_MS = 30000;
