/**
 * @jest-environment jsdom
 *
 * Smoke test for SkylitDashboard (the layout mounted by the default
 * `page === "heatseeker"` route in App.js, which is what users actually
 * land on). Confirms the skylit chrome + the steal-list bottom band
 * (rank #1 Dual-GEX, #5 IV-Mid, #3 Wheel income) all mount cleanly. Pairs
 * with HeatseekerDashboard.test.jsx so coverage spans both layouts.
 */
import React from "react";
import { render, screen, act } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock IntersectionObserver — harmless for a smoke test, but defensive in
// case any lazy subcomponent gets pulled in via transitive imports.
global.IntersectionObserver = class IntersectionObserver {
  constructor(callback) { this.callback = callback; }
  observe() { this.callback([{ isIntersecting: true }]); }
  disconnect() {}
  unobserve() {};
};

// Mock Skylit sub-components to null-mounts (no network calls; faster).
jest.mock("./SkylitTickerBar",       () => () => <div data-testid="mock-ticker-bar" />);
jest.mock("./SkylitControlBar",      () => () => <div data-testid="mock-control-bar" />);
jest.mock("./SkylitHeatmapGrid",     () => () => <div data-testid="mock-heatmap" />);
jest.mock("./SkylitMetricsSidebar",  () => () => <div data-testid="mock-metrics" />);

// Mock the steal-list top-3 components (they fetch from :8000 which is not
// running in tests). Use the same data-testids the components expose in
// production so this test also serves as a reality-check on those ids.
jest.mock("./DualGEXBadge",              () => () => <div data-testid="hs-dual-gex" />);
jest.mock("./IVMidBadge",                () => () => <div data-testid="hs-iv-mid" />);
jest.mock("./WheelIncomeScreenerPanel",  () => () => <div data-testid="hs-wheel-income" />);
jest.mock("./MaxPainBadge",              () => () => <div data-testid="hs-max-pain" />);

// Import AFTER mocks are set up.
import SkylitDashboard from "./SkylitDashboard";

describe("SkylitDashboard", () => {
  test("mounts the skylit chrome and the steal-list bottom band", async () => {
    await act(async () => {
      render(<SkylitDashboard ticker="SPY" />);
    });

    // Skylit chrome (top → bottom)
    expect(screen.getByTestId("mock-ticker-bar")).toBeInTheDocument();
    expect(screen.getByTestId("mock-control-bar")).toBeInTheDocument();
    expect(screen.getByTestId("mock-heatmap")).toBeInTheDocument();
    expect(screen.getByTestId("mock-metrics")).toBeInTheDocument();

    // Steal-list bottom band — the whole point of this test
    expect(screen.getByTestId("skylit-steal-list-band")).toBeInTheDocument();
    expect(screen.getByTestId("hs-dual-gex")).toBeInTheDocument();
    expect(screen.getByTestId("hs-iv-mid")).toBeInTheDocument();
    expect(screen.getByTestId("hs-wheel-income")).toBeInTheDocument();
    expect(screen.getByTestId("hs-max-pain")).toBeInTheDocument();
  });
});
