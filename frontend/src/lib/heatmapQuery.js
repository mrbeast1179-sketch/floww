// Single source of truth for the heatmap data query string.
//
// BOTH data paths must use this — the 25s polling effect (`/api/data/{ticker}`)
// and the manual-refresh fetch (`/api/heatmap/{ticker}`) — otherwise the poll
// overwrites the user's DTE/Expiries/mode selection with backend defaults
// (the Round-8 "controls don't work" regression).
//
// `dte` uses a `!= null` check: 0 (0DTE) is a real value and must be sent.
export function buildHeatmapQuery({ expiries, mode, dte } = {}) {
  const parts = [
    `expiries=${expiries != null ? expiries : 4}`,
    `mode=${mode || "day"}`,
  ];
  if (dte != null) parts.push(`dte=${dte}`);
  return parts.join("&");
}
