/**
 * VannaChart.test.jsx
 */
jest.mock("react-plotly.js", () => {
  const React = require("react");
  const MockPlot = React.forwardRef(function MockPlot(props, ref) {
    return React.createElement("div", { "data-testid": "mock-plot" });
  });
  return MockPlot;
});

jest.mock("../hooks/useMarketData", () => ({
  useMarketData: jest.fn(),
}));

jest.mock("../utils/dataDecimator", () => ({
  autoDecimate: function autoDecimate(points, _max) { return points; },
  isWebGLAvailable: function isWebGLAvailable() { return false; },
}));

import React from "react";
import { render } from "@testing-library/react";
import VannaChart from "./VannaChart";
import { useMarketData } from "../hooks/useMarketData";

var backendVannaResponse = {
  ticker: "SPY",
  spot: 510.0,
  strikes: [440, 450, 460, 470, 480, 490, 500, 510, 520, 530, 540],
  vanna: [1200, 800, 500, 200, -100, -400, -900, -1500, -2000, -2300, -2500],
  asof: "2025-06-20T15:00:00Z",
};

describe("VannaChart", () => {
  beforeEach(function() {
    jest.clearAllMocks();
  });

  test("renders without crash when given actual backend data", function() {
    useMarketData.mockReturnValue({
      data: backendVannaResponse,
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var container = render(React.createElement(VannaChart, { ticker: "SPY", spot: 510 })).container;
    expect(container).toBeTruthy();
    expect(container.firstChild).not.toBeNull();
  });

  test("renders empty state when data is null", function() {
    useMarketData.mockReturnValue({
      data: null,
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var container = render(React.createElement(VannaChart, { ticker: "SPY", spot: 510 })).container;
    expect(container.firstChild).not.toBeNull();
    expect(container.textContent).toContain("No vanna data available");
  });

  test("renders loading spinner", function() {
    useMarketData.mockReturnValue({
      data: null,
      loading: true,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var container = render(React.createElement(VannaChart, { ticker: "SPY", spot: 510 })).container;
    expect(container.textContent).toContain("Loading vanna");
  });

  test("renders error state", function() {
    useMarketData.mockReturnValue({
      data: null,
      loading: false,
      error: "HTTP 503",
      showBadge: false,
      refresh: jest.fn(),
    });
    var container = render(React.createElement(VannaChart, { ticker: "SPY", spot: 510 })).container;
    expect(container.textContent).toContain("unavailable");
  });

  test("handles empty arrays", function() {
    useMarketData.mockReturnValue({
      data: { ticker: "SPY", spot: 510, strikes: [], vanna: [], asof: "" },
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var container = render(React.createElement(VannaChart, { ticker: "SPY", spot: 510 })).container;
    expect(container.firstChild).not.toBeNull();
  });

  test("handles null vanna values gracefully", function() {
    useMarketData.mockReturnValue({
      data: {
        ticker: "SPY",
        spot: 510,
        strikes: [440, 450, 460],
        vanna: [1200, null, -500],
        asof: "",
      },
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var container = render(React.createElement(VannaChart, { ticker: "SPY", spot: 510 })).container;
    expect(container.firstChild).not.toBeNull();
  });

  test("handles mismatched strikes/vanna lengths", function() {
    useMarketData.mockReturnValue({
      data: {
        ticker: "SPY",
        spot: 510,
        strikes: [440, 450, 460, 470],
        vanna: [1200, -500],
        asof: "",
      },
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var container = render(React.createElement(VannaChart, { ticker: "SPY", spot: 510 })).container;
    expect(container.firstChild).not.toBeNull();
  });
});
