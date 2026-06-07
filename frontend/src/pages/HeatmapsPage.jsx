import React from "react";

export default function HeatmapsPage() {
  return (
    <div className="ap-main" style={{ flex: 1, padding: 0 }}>
      <div className="flow-alerts-terminal-glass" style={{ padding: 0 }}>
        <div className="fa-page-header">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <h1>Heatmaps</h1>
          </div>
        </div>
        <div style={{ padding: "16px" }}>
          <div className="card" style={{ padding: 24, textAlign: "center" }}>
            <div className="display text-[14px] font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
              GEX / VEX / Charm Heatmaps
            </div>
            <div style={{ color: "var(--text-quaternary)", fontSize: 13 }}>
              Coming in a later phase. Phase 1B ships Flow Alerts.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
