import React from "react";
import { render, screen } from "@testing-library/react";

// Mock IntersectionObserver — trigger immediately so LazyRow renders children
global.IntersectionObserver = class IntersectionObserver {
  constructor(callback) {
    this.callback = callback;
  }
  observe() {
    this.callback([{ isIntersecting: true }]);
  }
  disconnect() {}
  unobserve() {}
};

// Mock react-plotly.js (required by VannaChart and CharmChart)
// Must be before any component imports
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
  default: function MockErrorBoundary({ children }) {
    return <>{children}</>;
  },
}));

// Import AFTER mocks are set up
import HeatseekerDashboard from "./HeatseekerDashboard";
import { useHeatseeker } from "../../hooks/useHeatseeker";

const IDLE = { data: null, loading: false, error: null, refresh: () => {} };

describe("HeatseekerDashboard", () => {
  beforeEach(() => {
    useHeatseeker.mockReturnValue(IDLE);
  });

  test("renders header with ticker and Wave 1+2+3 caption", () => {
    render(<HeatseekerDashboard ticker="SPY" spot={500} />);
    expect(screen.getByText("Skylit Heatseeker")).toBeInTheDocument();
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText(/Wave 1 \+ 2 \+ 3/i)).toBeInTheDocument();
  });

  test("mounts all 12 child panels via their test-ids", () => {
    render(<HeatseekerDashboard ticker="SPY" spot={500} />);
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
      "hs-rolling-floors-ceilings",
      "hs-tug-of-war",
      "hs-node-classification",
      "hs-stacked-nodes",
    ].forEach((tid) => expect(screen.getByTestId(tid)).toBeInTheDocument());
  });

  test("strips leading caret from index symbols like ^SPX", () => {
    render(<HeatseekerDashboard ticker="^SPX" />);
    expect(screen.getByText("SPX")).toBeInTheDocument();
  });
});
