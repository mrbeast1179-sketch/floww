/**
 * useMarketData.js
 *
 * Offline-first data hook with IndexedDB caching.
 *
 * Strategy:
 *   1. Check IndexedDB cache first (instant).
 *   2. If cache miss or stale (>5 min), fetch from backend.
 *   3. On fetch error, fall back to cached data regardless of staleness.
 *   4. On success, update cache and serve fresh data.
 *   5. Display "Stale Data" badge when data is >15 min old.
 *
 * Returns: { data, loading, error, isStale, dataAge, refresh }
 */

import { useEffect, useState, useRef, useCallback } from "react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

// IndexedDB configuration
const DB_NAME = "floww-market-data";
const DB_VERSION = 1;
const STORE = "cache";
const STALE_THRESHOLD_MS = 5 * 60 * 1000;       // 5 min — triggers background fetch
const BADGE_THRESHOLD_MS = 15 * 60 * 1000;       // 15 min — show "Stale Data" badge

// ── IndexedDB helpers ────────────────────────────────────────────────

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "key" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function cacheGet(key) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const req = tx.objectStore(STORE).get(key);
      req.onsuccess = () => {
        const entry = req.result;
        if (!entry) { resolve(null); return; }
        resolve({ data: entry.data, ts: entry.ts });
      };
      req.onerror = () => reject(req.error);
    });
  } catch {
    return null;  // IndexedDB unavailable — graceful degradation
  }
}

async function cachePut(key, data) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      const req = tx.objectStore(STORE).put({
        key,
        data,
        ts: Date.now(),
      });
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  } catch {
    // silently fail — cache write is non-critical
  }
}

// ── Hook ─────────────────────────────────────────────────────────────

/**
 * @param {string} endpoint   API path after /api/, e.g. "data/SPY"
 * @param {Object} options
 * @param {number} [options.refreshMs=30000]  Polling interval (0 to disable)
 * @param {boolean} [options.skip=false]      If true, don't fetch
 * @param {Object} [options.query={}]         Extra query params
 */
export function useMarketData(endpoint, options = {}) {
  const { refreshMs = 30000, skip = false, query = {} } = options;

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [dataAge, setDataAge] = useState(null);         // ms since data was cached
  const [isStale, setIsStale] = useState(false);         // > STALE_THRESHOLD_MS
  const [showBadge, setShowBadge] = useState(false);     // > BADGE_THRESHOLD_MS

  const mountedRef = useRef(true);
  const abortRef = useRef(null);
  const cacheKey = useRef(`${endpoint}?${JSON.stringify(query)}`).current;

  // ── Fetch from network ────────────────────────────────────────────

  const fetchFromNetwork = useCallback(async (opts = {}) => {
    if (!endpoint) return;

    // Cancel previous in-flight request
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch { /* noop */ }
    }
    const controller = new AbortController();
    abortRef.current = controller;

    if (!opts.silent) setLoading(true);

    try {
      const qs = new URLSearchParams();
      Object.entries(query).forEach(([k, v]) => {
        if (v != null && v !== "") qs.set(k, String(v));
      });
      const url = `${API}/${endpoint}${qs.toString() ? `?${qs}` : ""}`;

      const res = await fetch(url, { signal: controller.signal, timeout: 30000 });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 120)}` : ""}`);
      }
      const json = await res.json();

      if (!mountedRef.current || abortRef.current !== controller) return;

      // Update state
      const now = Date.now();
      setData(json);
      setDataAge(0);
      setIsStale(false);
      setShowBadge(false);
      setError(null);

      // Write to IndexedDB cache (async, non-blocking)
      cachePut(cacheKey, json).catch(() => {});

    } catch (e) {
      if (e.name === "AbortError") return;
      if (!mountedRef.current) return;

      // On network error: fall back to whatever cache we have
      const cached = await cacheGet(cacheKey);
      if (cached && !data) {
        // Only use cache if we don't already have data displayed
        setData(cached.data);
        const age = Date.now() - cached.ts;
        setDataAge(age);
        setIsStale(age > STALE_THRESHOLD_MS);
        setShowBadge(age > BADGE_THRESHOLD_MS);
        setError(null);  // suppress error since we have cached data
      } else {
        setError(e.message || "Fetch failed");
      }
    } finally {
      if (mountedRef.current && abortRef.current === controller) {
        setLoading(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, cacheKey, JSON.stringify(query)]);

  // ── Initial load: cache-first ─────────────────────────────────────

  useEffect(() => {
    mountedRef.current = true;

    let cancelled = false;

    (async () => {
      if (skip || !endpoint) return;

      // 1. Serve from cache immediately (if available)
      const cached = await cacheGet(cacheKey);
      if (cancelled) return;

      if (cached) {
        const age = Date.now() - cached.ts;
        setData(cached.data);
        setDataAge(age);
        setIsStale(age > STALE_THRESHOLD_MS);
        setShowBadge(age > BADGE_THRESHOLD_MS);

        // 2. If stale (>5 min), trigger background fetch
        if (age > STALE_THRESHOLD_MS) {
          fetchFromNetwork({ silent: true });
        }
      } else {
        // 3. No cache — show loading and fetch
        setLoading(true);
        await fetchFromNetwork();
      }
    })();

    return () => {
      cancelled = true;
      mountedRef.current = false;
      if (abortRef.current) {
        try { abortRef.current.abort(); } catch { /* noop */ }
        abortRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey, skip]);

  // ── Polling ───────────────────────────────────────────────────────

  useEffect(() => {
    if (skip || refreshMs <= 0) return;
    const id = setInterval(() => {
      fetchFromNetwork({ silent: true });
    }, refreshMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchFromNetwork, refreshMs, skip]);

  // Recalculate staleness on each render
  useEffect(() => {
    if (dataAge == null) return;
    setIsStale(dataAge > STALE_THRESHOLD_MS);
    setShowBadge(dataAge > BADGE_THRESHOLD_MS);
  }, [dataAge]);

  const refresh = useCallback(() => fetchFromNetwork(), [fetchFromNetwork]);

  return { data, loading, error, isStale, showBadge, dataAge, refresh };
}

export default useMarketData;
