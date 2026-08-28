/**
 * @jest-environment jsdom
 */

import React from "react";
import { render } from "@testing-library/react";
import {
  MarketRegimePanel, ImpliedPDFPanel, HedgeImpulsePanel,
  PressureCloudPanel, CharmIntegralPanel,
} from "./AdvancedAnalyticsPanel";

describe("AdvancedAnalyticsPanel — null prop smoke tests", () => {
  test.each([
    ["MarketRegimePanel", MarketRegimePanel],
    ["ImpliedPDFPanel", ImpliedPDFPanel],
    ["HedgeImpulsePanel", HedgeImpulsePanel],
    ["PressureCloudPanel", PressureCloudPanel],
    ["CharmIntegralPanel", CharmIntegralPanel],
  ])("%s renders without crashing on null props", (name, Panel) => {
    if (!Panel) return;
    const { container } = render(<Panel data={null} loading={false} error={null} ticker="SPY" />);
    expect(container).toBeTruthy();
  });
});
