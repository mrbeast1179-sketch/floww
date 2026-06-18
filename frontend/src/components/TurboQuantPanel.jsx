import React, { useState, useEffect } from "react";

// turboQuantDC KV-cache compression panel.
// Mirrors SwarmFrame's defensive pattern: probe the backend first, and if it's
// not reachable show a calm placeholder instead of a wall of failed fetches.
// Talks to the floww backend routes in backend/routes/llm.py (prefix /api):
//   GET /api/turboquant/status   -> { available, default_preset, default_bits, fp16_window, ... }
//   GET /api/turboquant/presets  -> { available, presets: {id:{description,compression}}, default }
const API_BASE = process.env.REACT_APP_API_URL || "";

export default function TurboQuantPanel() {
  const [state, setState] = useState({
    loading: true,
    error: null,
    status: null,
    presets: null,
    defaultPreset: null,
  });

  useEffect(() => {
    let cancelled = false;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 4000);

    async function load() {
      try {
        const [sRes, pRes] = await Promise.all([
          fetch(`${API_BASE}/api/turboquant/status`, { signal: ctrl.signal }),
          fetch(`${API_BASE}/api/turboquant/presets`, { signal: ctrl.signal }),
        ]);
        if (!sRes.ok) throw new Error(`status ${sRes.status}`);
        const status = await sRes.json();
        const presetsBody = pRes.ok ? await pRes.json() : {};
        if (!cancelled) {
          setState({
            loading: false,
            error: null,
            status,
            presets: presetsBody.presets || {},
            defaultPreset: presetsBody.default || status.default_preset || null,
          });
        }
      } catch (e) {
        if (!cancelled) {
          setState({
            loading: false,
            error: e.message || "unreachable",
            status: null,
            presets: null,
            defaultPreset: null,
          });
        }
      } finally {
        clearTimeout(timer);
      }
    }

    load();
    return () => {
      cancelled = true;
      ctrl.abort();
      clearTimeout(timer);
    };
  }, []);

  const { loading, error, status, presets, defaultPreset } = state;

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
        Loading turboQuantDC status…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-500 text-sm">
        <p>
          turboQuantDC backend not reachable at{" "}
          <code className="text-slate-400">/api/turboquant/status</code>
        </p>
        <p className="text-xs text-slate-600">
          Start the floww backend on :8000, then reopen this tab. ({error})
        </p>
      </div>
    );
  }

  const installed = !!(status && status.available);

  return (
    <div className="flex-1 overflow-auto" style={{ padding: "20px 24px" }}>
      <div style={{ maxWidth: 880, margin: "0 auto" }}>
        <header style={{ marginBottom: 18 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--gold, #e3b341)", margin: 0 }}>
            turboQuantDC
          </h1>
          <p className="text-slate-500 text-sm" style={{ marginTop: 4 }}>
            3-bit KV-cache compression for local LLM inference — 3–5× VRAM reduction, &lt;0.5% quality loss.
          </p>
        </header>

        {/* Service status */}
        <section style={CARD}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
            <span style={{ ...BADGE, ...(installed ? BADGE_GREEN : BADGE_GRAY) }}>
              {installed ? "● installed" : "○ not installed"}
            </span>
            {!installed && (
              <code className="text-xs text-slate-500">pip install turboquantdc[all]</code>
            )}
          </div>
          <div style={KV_GRID}>
            <KV label="Default preset" value={status?.default_preset} />
            <KV label="KV bits" value={status?.default_bits} />
            <KV label="FP16 window" value={status?.fp16_window} />
          </div>
        </section>

        {/* Quality presets */}
        <section style={{ ...CARD, marginTop: 14 }}>
          <h2 style={SECTION_TITLE}>Quality presets</h2>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                <th style={TH}>Preset</th>
                <th style={TH}>Compression</th>
                <th style={TH}>Description</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(presets || {}).map(([id, p]) => (
                <tr key={id}>
                  <td style={TD}>
                    {id}
                    {id === defaultPreset && (
                      <span className="text-xs text-slate-500"> (default)</span>
                    )}
                  </td>
                  <td style={TD}>{p?.compression ?? "—"}</td>
                  <td style={{ ...TD, color: "var(--text-muted, #8b949e)" }}>{p?.description ?? ""}</td>
                </tr>
              ))}
              {Object.keys(presets || {}).length === 0 && (
                <tr>
                  <td style={TD} colSpan={3}>No presets reported.</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>

        <p className="text-xs text-slate-600" style={{ marginTop: 14 }}>
          Repo: dhawalc/turboQuantDC · Service: backend/services/turboquant_cache.py · Routes: /api/turboquant/*
        </p>
      </div>
    </div>
  );
}

function KV({ label, value }) {
  return (
    <div>
      <div className="text-xs text-slate-500" style={{ textTransform: "uppercase", letterSpacing: ".5px" }}>
        {label}
      </div>
      <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2 }}>{value ?? "—"}</div>
    </div>
  );
}

const CARD = {
  background: "var(--surface, #161b22)",
  border: "1px solid var(--border, #30363d)",
  borderRadius: 10,
  padding: 16,
};
const KV_GRID = { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))", gap: 14 };
const SECTION_TITLE = {
  fontSize: 12,
  textTransform: "uppercase",
  letterSpacing: ".6px",
  color: "var(--gold, #e3b341)",
  marginBottom: 10,
};
const BADGE = { display: "inline-flex", alignItems: "center", padding: "2px 10px", borderRadius: 12, fontSize: 11, fontWeight: 600 };
const BADGE_GREEN = { background: "rgba(63,185,80,.14)", color: "#3fb950", border: "1px solid rgba(63,185,80,.3)" };
const BADGE_GRAY = { background: "rgba(139,148,158,.12)", color: "#8b949e", border: "1px solid #30363d" };
const TH = {
  textAlign: "left",
  padding: "8px 10px",
  borderBottom: "1px solid var(--border,#30363d)",
  color: "#8b949e",
  fontWeight: 500,
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: ".5px",
};
const TD = { padding: "9px 10px", borderBottom: "1px solid rgba(48,54,61,.55)" };
