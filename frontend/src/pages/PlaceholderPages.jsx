import React from "react";

function ComingSoonPage({ title, subtitle }) {
  return (
    <div className="ap-main" style={{ flex: 1, padding: 0 }}>
      <div className="flow-alerts-terminal-glass" style={{ padding: 0 }}>
        <div className="fa-page-header">
          <h1>{title}</h1>
        </div>
        <div style={{ padding: "16px" }}>
          <div className="card" style={{ padding: 24, textAlign: "center" }}>
            <div className="display text-[14px] font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
              {title}
            </div>
            <div style={{ color: "var(--text-quaternary)", fontSize: 13 }}>
              {subtitle || "Coming in a later phase. Phase 1B ships Flow Alerts."}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export const SignalsPage = () => (
  <ComingSoonPage title="Active Signals" subtitle="Kairos algo active trading signals. Coming in a later phase." />
);

export const TradeLogPage = () => (
  <ComingSoonPage title="Trade Log" subtitle="Historical trade log from Kairos algo. Coming in a later phase." />
);

export const PerformancePage = () => (
  <ComingSoonPage title="Performance" subtitle="Algo performance metrics and equity curve. Coming in a later phase." />
);

export const KeyLevelsPage = () => (
  <ComingSoonPage title="Key Levels" subtitle="SPX key support and resistance levels. Coming in a later phase." />
);

export const SpxAlertsPage = () => (
  <ComingSoonPage title="SPX Alerts" subtitle="SPX-specific flow alerts and unusual activity. Coming in a later phase." />
);

export default ComingSoonPage;
