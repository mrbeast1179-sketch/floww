import { useEffect, useState, useRef, useCallback } from "react";

const WS_URL = process.env.REACT_APP_BACKEND_URL?.replace("http", "ws") || "ws://localhost:8000";

export function useWebSocketGex(ticker) {
  const [data, setData] = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!ticker) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_URL}/ws/gex/${ticker}`);
    wsRef.current = ws;

    ws.onopen = () => {
      if (mountedRef.current) setConnected(true);
    };
    ws.onclose = () => {
      if (mountedRef.current) setConnected(false);
      // Only reconnect if this socket is still the current one
      if (wsRef.current === ws && mountedRef.current) {
        reconnectRef.current = setTimeout(connect, 5000);
      }
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      if (!mountedRef.current) return;
      try { setData(JSON.parse(e.data)); } catch (err) { /* noop */ }
    };
  }, [ticker]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on unmount
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { data, connected };
}
