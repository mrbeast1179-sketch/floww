import { useEffect, useState, useRef, useCallback } from "react";

const WS_URL = process.env.REACT_APP_BACKEND_URL?.replace("http", "ws") || "ws://localhost:8000";

export function useWebSocketGex(ticker) {
  const [data, setData] = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  const connect = useCallback(() => {
    if (!ticker) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_URL}/ws/gex/${ticker}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      reconnectRef.current = setTimeout(connect, 5000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try { setData(JSON.parse(e.data)); } catch (err) { /* noop */ }
    };
  }, [ticker]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { data, connected };
}
