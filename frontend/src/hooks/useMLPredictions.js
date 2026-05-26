import { useEffect, useState, useCallback, useRef } from "react";
import { BACKEND_URL } from "../config/api";

const API = `${BACKEND_URL}/api/ml`;

/**
 * Fetch ML predictions for all registered tickers.
 *
 * Returns: { predictions, loading, error, refresh }
 */
export function useMLPredictions({ refreshMs = 60000, skip = false } = {}) {
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);

  const fetcher = useCallback(async () => {
    if (skip) return;
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch (e) { /* noop */ }
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    try {
      const res = await fetch(`${API}/batch-predict`, {
        method: "POST",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 120)}` : ""}`);
      }
      const json = await res.json();
      if (abortRef.current === controller) {
        setPredictions(json.predictions || []);
        setError(null);
      }
    } catch (e) {
      if (e.name === "AbortError") return;
      if (abortRef.current === controller) {
        setError(e.message || "Fetch failed");
      }
    } finally {
      if (abortRef.current === controller) {
        setLoading(false);
        abortRef.current = null;
      }
    }
  }, [skip]);

  useEffect(() => {
    fetcher();
    let id = null;
    if (refreshMs > 0 && !skip) {
      id = setInterval(fetcher, refreshMs);
    }
    return () => {
      if (id) clearInterval(id);
      if (abortRef.current) {
        try { abortRef.current.abort(); } catch (e) { /* noop */ }
        abortRef.current = null;
      }
    };
  }, [fetcher, refreshMs, skip]);

  return { predictions, loading, error, refresh: fetcher };
}

export default useMLPredictions;
