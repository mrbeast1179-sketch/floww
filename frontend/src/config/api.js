/**
 * Single source of truth for backend URL configuration.
 * Falls back to localhost:8000 when REACT_APP_BACKEND_URL is missing,
 * preventing "undefined/api/..." bug. Added Round 9 H8.
 */
export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
export const API = `${BACKEND_URL}/api`;
