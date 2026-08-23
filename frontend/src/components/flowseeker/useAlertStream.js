/**
 * useAlertStream.js — SSE client for the Blademap v3 conviction feed.
 * Replaces polling with server push. EventSource auto-reconnects when
 * the stream ends (server caps at max_seconds). Falls back gracefully —
 * the caller keeps its polling hook as the fallback data source.
 *
 * Returns { alerts, connected, lastEvent }.
 */
import { useEffect, useRef, useState } from "react";

const API_BASE = "http://localhost:8000/api";

export function useAlertStream({ minConviction = null, enabled = true } = {}) {
  const [alerts, setAlerts] = useState([]);
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const esRef = useRef(null);

  useEffect(() => {
    if (!enabled) return undefined;
    // jsdom / older browsers have no EventSource — caller's polling hook
    // remains the data source (graceful fallback).
    if (typeof window === "undefined" || typeof window.EventSource !== "function") {
      setConnected(false);
      return undefined;
    }

    const qs = new URLSearchParams();
    if (minConviction != null) qs.set("min_conviction", String(minConviction));
    const url = `${API_BASE}/flowseeker/alerts/stream?${qs}`;

    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("open", () => setConnected(true));
    es.addEventListener("alerts", (e) => {
      try {
        const payload = JSON.parse(e.data);
        setAlerts(payload.alerts || []);
        setLastEvent(payload.ts);
      } catch (err) { /* malformed frame - skip */ }
    });
    es.addEventListener("heartbeat", () => setConnected(true));
    es.addEventListener("error", () => {
      // EventSource auto-reconnects; just flip the badge
      setConnected(false);
    });

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [minConviction, enabled]);

  return { alerts, connected, lastEvent };
}
