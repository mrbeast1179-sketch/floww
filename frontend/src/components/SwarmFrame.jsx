import React, { useState, useEffect } from "react";

const SWARM_URL = process.env.REACT_APP_SWARM_URL || "http://localhost:8099/";
const FALLBACK_TIMEOUT_MS = 8000;

export default function SwarmFrame() {
  const [failed, setFailed] = useState(false);

  // Timeout-based fallback — iframe onError is unreliable for cross-origin content.
  useEffect(() => {
    const timer = setTimeout(() => setFailed(true), FALLBACK_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, []);

  if (failed) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-500 text-sm">
        <p>
          SwarmSPX service not reachable at{" "}
          <code className="text-slate-400">{SWARM_URL}</code>
        </p>
        <p className="text-xs text-slate-600">
          Set{" "}
          <code className="text-slate-500">REACT_APP_SWARM_URL</code>{" "}
          or start the service.
        </p>
      </div>
    );
  }

  return (
    <div
      className="flex-1 overflow-hidden"
      style={{ display: "flex", flexDirection: "column" }}
    >
      <iframe
        src={SWARM_URL}
        title="SwarmSPX Neural Intelligence"
        onError={() => setFailed(true)}
        style={{ flex: 1, border: "none", width: "100%", height: "100%" }}
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
      />
    </div>
  );
}
