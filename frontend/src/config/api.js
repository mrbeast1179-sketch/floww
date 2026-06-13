/**
 * API configuration — supports both local backend and AlphaPod API proxy.
 * 
 * REACT_APP_BACKEND_URL — local FastAPI backend (default: http://localhost:8000)
 * REACT_APP_API_URL — AlphaPod API (default: https://api.alphapodtrading.com)
 * 
 * When ALPHAPOD_PROXY=true, /api/* requests are proxied to AlphaPod API
 * with JWT auth. Otherwise they go to the local backend.
 */
export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
export const API = `${BACKEND_URL}/api`;
export const ALPHAPOD_API = process.env.REACT_APP_API_URL || "https://api.alphapodtrading.com";
export const USE_ALPHAPOD_PROXY = process.env.REACT_APP_ALPHAPOD_PROXY === "true";
