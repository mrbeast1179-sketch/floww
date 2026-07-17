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
// Per-expiry max-pain-drift multi-line chart tile (steal-list #9 rich
// visualization; fetches /api/max_pain_drift/{ticker}/per_expiry_history).
jest.mock("./MaxPainPerExpiryDriftTile",  () => () => <div data-testid="hs-max-pain-per-expiry-drift" />);
// NEW (2026-07-16): steal-list #10 (strike cone) + #8 (opportunity
// engine) — mocks mirror the production component data-testids so
// these assertions also serve as a reality-check on those ids.
jest.mock("./StrikeConeBadge",              () => () => <div data-testid="hs-strike-cone" />);
jest.mock("./OpportunityBadge",             () => () => <div data-testid="hs-opportunity" />);
// NEW (2026-07-16): News pulse (catalyst + headline count) and the
// full-width Risk-Neutral Density tile — both fetch on mount so the
// mocks keep the test synchronous + side-effect-free.
jest.mock("./NewsBadge",                    () => () => <div data-testid="hs-news" />);
jest.mock("./RndDensityPanel",              () => () => <div data-testid="hs-rnd-density" />);

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
    // Per-expiry max-pain-drift multi-line chart mounted full-width
    // beneath the Wheel panel inside the steal-list band.
    expect(screen.getByTestId("hs-max-pain-per-expiry-drift")).toBeInTheDocument();
    // NEW (2026-07-16): steal-list #10 strike cone + #8 opportunity
    // engine mirror — surfaced into the skylit bottom band alongside
    // the existing #1/#3/#5/#9 mounts. Pairs with the SkylitDashboard.jsx
    // edit that imports + mounts them inside the skylit-steal-list-band
    // container. Count delta: +4 (inner hs-strike-cone + hs-opportunity
    // + outer skylit-steal-strike-cone + skylit-steal-opportunity wrappers
    // — keeps test parity with the existing 4-badge dual-level pattern).
    expect(screen.getByTestId("hs-strike-cone")).toBeInTheDocument();
    expect(screen.getByTestId("hs-opportunity")).toBeInTheDocument();
    // skylit-steal-<feature> wrapper assertions mirror the dual-level
    // pattern the existing 4 badges follow (DualGEX / IVMid / MaxPain /
    // WheelIncome / MaxPainPerExpiryDriftTile) — see lines above.
    // Adding these catches a future regression where a maintainer might
    // rename or remove the wrapper testids without realising the
    // convention is shared across the band.
    expect(screen.getByTestId("skylit-steal-strike-cone")).toBeInTheDocument();
    expect(screen.getByTestId("skylit-steal-opportunity")).toBeInTheDocument();
    // NEW (2026-07-16): bottom-band news pulse + RND full-width mount.
    expect(screen.getByTestId("skylit-steal-news-band")).toBeInTheDocument();
    expect(screen.getByTestId("skylit-steal-rnd-density")).toBeInTheDocument();
    // NEW (2026-07-15): skylit-steal-<feature> wrappers — standardize
    // on the skylit-steal-<feature> prefix so visual verifications can
    // target tiles by semantic purpose (dual-gex / iv-mid / max-pain /
    // wheel-income / max-pain-per-expiry-drift) without screen-scraping
    // the surrounding skylit chrome. Count delta +5 from the prior
    // version of this test.
    expect(screen.getByTestId("skylit-steal-dual-gex")).toBeInTheDocument();
    expect(screen.getByTestId("skylit-steal-iv-mid")).toBeInTheDocument();
    expect(screen.getByTestId("skylit-steal-max-pain")).toBeInTheDocument();
    expect(screen.getByTestId("skylit-steal-wheel-income")).toBeInTheDocument();
    expect(screen.getByTestId("skylit-steal-max-pain-per-expiry-drift")).toBeInTheDocument();
  });
});
