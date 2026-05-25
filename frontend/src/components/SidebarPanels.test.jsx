import React from "react";
import { render } from "@testing-library/react";
import {
  FlipZonesPanel, StackedNodesPanel, TugOfWarPanel,
  ScenarioPanel, RiskDashboardPanel, OpportunitiesPanel,
  ImpliedMovePanel, VolAnalyticsPanel,
  GreekReferencePanel, UsagePanel, LivePolicyPanel,
} from "./SidebarPanels";

describe("SidebarPanels — null prop smoke tests", () => {
  test.each([
    ["FlipZonesPanel", FlipZonesPanel],
    ["StackedNodesPanel", StackedNodesPanel],
    ["TugOfWarPanel", TugOfWarPanel],
    ["ScenarioPanel", ScenarioPanel],
    ["RiskDashboardPanel", RiskDashboardPanel],
    ["OpportunitiesPanel", OpportunitiesPanel],
    ["ImpliedMovePanel", ImpliedMovePanel],
    ["VolAnalyticsPanel", VolAnalyticsPanel],
    ["GreekReferencePanel", GreekReferencePanel],
    ["UsagePanel", UsagePanel],
    ["LivePolicyPanel", LivePolicyPanel],
  ])("%s renders without crashing on null/undefined props", (name, Panel) => {
    if (!Panel) {
      return;
    }
    const { container } = render(<Panel data={null} loading={false} error={null} />);
    expect(container).toBeTruthy();
  });
});
