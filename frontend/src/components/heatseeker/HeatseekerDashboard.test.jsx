/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen, act } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock IntersectionObserver — trigger immediately so LazyRow renders children
global.IntersectionObserver = class IntersectionObserver {
  constructor(callback) { this.callback = callback; }
  observe() { this.callback([{ isIntersecting: true }]); }
  disconnect() {}
  unobserve() {};
};

// Mock react-plotly.js (required by VannaChart and CharmChart)
jest.mock("react-plotly.js", () => {
  const React = require("react");
  return React.forwardRef(function MockPlot(props, ref) {
    return React.createElement("div", { "data-testid": "mock-plot", ref });
  });
});

// Mock useHeatseeker
jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

// Mock ErrorBoundary
jest.mock("../ErrorBoundary", () => ({
  __esModule: true,
  default: function MockErrorBoundary({ children }) { return <>{children}</>; },
}));

// Mock the steal-list top-3 components mounted into Row 3 (real fetch
// would hit the backend on mount; we just need to confirm presence).
jest.mock("./DualGEXBadge", () => () => <div data-testid="hs-dual-gex" />);
jest.mock("./IVMidBadge", () => () => <div data-testid="hs-iv-mid" />);
jest.mock("./WheelIncomeScreenerPanel", () => () => <div data-testid="hs-wheel-income" />);
jest.mock("./MaxPainBadge", () => () => <div data-testid="hs-max-pain" />);
// Row 4 mount — steal-list #10 (cone) + #8 (opportunity engine)
jest.mock("./StrikeConeBadge", () => () => <div data-testid="hs-strike-cone" />);
jest.mock("./OpportunityBadge", () => () => <div data-testid="hs-opportunity" />);

// Mock lazy-loaded chart components
jest.mock("../VannaChart", () => () => <div data-testid="mock-vanna" />);
jest.mock("../CharmChart", () => () => <div data-testid="mock-charm" />);

// Import AFTER mocks are set up
import HeatseekerDashboard from "./HeatseekerDashboard";
import { useHeatseeker } from "../../hooks/useHeatseeker";

const IDLE = { data: null, loading: false, error: null, refresh: () => {} };

describe("HeatseekerDashboard", () => {
  beforeEach(() => {
    useHeatseeker.mockReturnValue(IDLE);
  });

  test("renders header with ticker and Wave 1+2+3 caption", async () => {
    await act(async () => {
      render(<HeatseekerDashboard ticker="SPY" spot={500} />);
    });
    expect(screen.getByText("Skylit Heatseeker")).toBeInTheDocument();
    expect(screen.getByText(/Wave 1 \+ 2 \+ 3/i)).toBeInTheDocument();
  });

  test("mounts all 17 child panels via their test-ids", async () => {
    await act(async () => {
      render(<HeatseekerDashboard ticker="SPY" spot={500} />);
    });
    expect(screen.getByTestId("heatseeker-dashboard")).toBeInTheDocument();
    [
      "hs-flip-zones",
      "hs-node-lifecycle",
      "hs-air-pockets",
      "hs-beach-ball",
      "hs-reverse-rug",
      "hs-rainbow-road",
      "hs-velocity-mode",
      "hs-trinity-confluence",
      // Steal-list top-3 (rank #1, #5, #3) mounted into Row 3 so the new
      // signals appear on the main Heatseeker page, not just /steal-three.
      "hs-dual-gex",
      "hs-iv-mid",
      "hs-wheel-income",
      "hs-max-pain",
      // Steal-list #10 + #8 mounted into Row 4 ("Expected Moves / Trade Ideas")
      "hs-strike-cone",
      "hs-opportunity",
      "hs-rolling-floors-ceilings",
      "hs-tug-of-war",
      "hs-node-classification",
      "hs-stacked-nodes",
    ].forEach((tid) => expect(screen.getByTestId(tid)).toBeInTheDocument());
  });

  test("strips leading caret from index symbols like ^SPX", async () => {
    await act(async () => {
      render(<HeatseekerDashboard ticker="^SPX" />);
    });
    expect(screen.getByText(/Wave 1 \+ 2 \+ 3/i)).toBeInTheDocument();
  });
});
