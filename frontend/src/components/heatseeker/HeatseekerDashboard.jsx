import React from "react";
import FlipZonesPanel from "./FlipZonesPanel";
import NodeLifecyclePanel from "./NodeLifecyclePanel";
import AirPocketsPanel from "./AirPocketsPanel";
import BeachBallIndicator from "./BeachBallIndicator";
import ReverseRugIndicator from "./ReverseRugIndicator";
import RainbowRoadIndicator from "./RainbowRoadIndicator";
import VelocityModeBadge from "./VelocityModeBadge";
import TrinityConfluenceMeter from "./TrinityConfluenceMeter";

/**
 * Composes all 8 Skylit Heatseeker (Wave 1 + Wave 2) panels.
 *
 * Layout:
 *   Row 1 — 3 pattern indicator cards (Beach Ball / Reverse Rug / Rainbow Road)
 *   Row 2 — 3 detail panels stacked vertically (Flip Zones, Node Lifecycle, Air Pockets)
 *   Row 3 — Velocity + Trinity Confluence (no ticker arg)
 */
export default function HeatseekerDashboard({ ticker = "SPY", spot = null }) {
  return (
    <div className="p-3 space-y-3" data-testid="heatseeker-dashboard">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="label">Skylit Heatseeker</div>
          <div className="text-sm font-bold tracking-wider">
            {String(ticker).replace("^", "")}
            <span className="ml-2 text-[10px] uppercase tracking-widest text-slate-500">
              Wave 1 + 2
            </span>
          </div>
        </div>
      </div>

      {/* Row 1 — pattern indicator cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <BeachBallIndicator ticker={ticker} />
        <ReverseRugIndicator ticker={ticker} />
        <RainbowRoadIndicator ticker={ticker} />
      </div>

      {/* Row 2 — detail panels */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <FlipZonesPanel ticker={ticker} spot={spot} />
        <NodeLifecyclePanel ticker={ticker} />
        <AirPocketsPanel ticker={ticker} />
      </div>

      {/* Row 3 — velocity + trinity confluence (trinity is index-wide) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <VelocityModeBadge ticker={ticker} />
        <TrinityConfluenceMeter />
      </div>
    </div>
  );
}
