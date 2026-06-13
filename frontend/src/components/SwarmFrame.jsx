import React, { useState, useEffect } from "react";

const SWARM_URL = process.env.REACT_APP_SWARM_URL || "http://localhost:8099/";

export default function SwarmFrame() {
  // Default to the calm placeholder; only mount the iframe once we've confirmed
  // the service actually answers. This prevents the browser's native
  // ERR_CONNECTION_REFUSED page from flashing inside the iframe when nothing
  // is serving :8099 (the common case in dev).
  const [reachable, setReachable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 3000);
    // no-cors HEAD probe: resolves (opaque) if a server answers, rejects if the
    // connection is refused / times out.
    fetch(SWARM_URL, { method: "HEAD", mode: "no-cors", signal: ctrl.signal })
      .then(() => { if (!cancelled) setReachable(true); })
      .catch(() => { /* service down — stay on the placeholder */ })
      .finally(() => clearTimeout(timer));
    return () => { cancelled = true; ctrl.abort(); clearTimeout(timer); };
  }, []);

  if (!reachable) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-500 text-sm">
        <p>
          SwarmSPX service not running at{" "}
          <code className="text-slate-400">{SWARM_URL}</code>
        </p>
        <p className="text-xs text-slate-600">
          Start the service, or set{" "}
          <code className="text-slate-500">REACT_APP_SWARM_URL</code>.
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
        style={{ flex: 1, border: "none", width: "100%", height: "100%" }}
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
      />
    </div>
  );
}
