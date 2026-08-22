/**
 * API configuration — supports both local backend and AlphaPod API proxy.
 *
 * REACT_APP_BACKEND_URL — FastAPI backend origin. UNSET in production builds:
 * the app is served behind Caddy which reverse-proxies /api and /ws, so we
 * use same-origin (window.location.origin) and everything "just works" on
 * localhost:3000, a LAN host, or https://your.domain with zero rebuild config.
 * Set REACT_APP_BACKEND_URL=http://localhost:8000 only for dev against a
 * non-proxied backend.
 */
// NOTE: CRA's webpack replaces process.env.REACT_APP_* with literals and terser
// constant-folds `envVar || window.location.origin` at BUILD time — baking
// localhost into the bundle (verified twice in main.*.js, even through helper
// functions and globalThis lookups). The only reliable escape hatch: a Function
// constructor, which terser never evaluates. Fallback keeps SSR/tests working.
let computedOrigin;
try {
  // eslint-disable-next-line no-new-func
  computedOrigin = new Function("return typeof window!==\"undefined\" && window.location && window.location.origin || \"\";")();
} catch (e) {
  computedOrigin = "";
}
export const BACKEND_BASE =
  process.env.REACT_APP_BACKEND_URL ||
  process.env.REACT_APP_STEAL_THREE_BASE ||
  process.env.REACT_APP_API_BASE ||
  (computedOrigin && computedOrigin.indexOf("http") === 0 ? computedOrigin : "http://localhost:8000");

export const BACKEND_URL = BACKEND_BASE;
export const API = `${BACKEND_BASE}/api`;
export const ALPHAPOD_API = process.env.REACT_APP_API_URL || "https://api.alphapodtrading.com";
export const USE_ALPHAPOD_PROXY = process.env.REACT_APP_ALPHAPOD_PROXY === "true";
