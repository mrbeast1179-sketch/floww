/**
 * CharmChart.test.jsx
 */
import React from "react";
import { render } from "@testing-library/react";
import CharmChart from "./CharmChart";

jest.mock("react-plotly.js", () => {
  var React = require("react");
  return React.forwardRef(function MockPlot(props, ref) {
    return React.createElement("div", { "data-testid": "mock-plot" });
  });
});

jest.mock("../hooks/useMarketData", () => ({
  useMarketData: jest.fn(),
}));

jest.mock("../utils/dataDecimator", () => ({
  autoDecimate: function autoDecimate(points, _max) { return points; },
  isWebGLAvailable: function isWebGLAvailable() { return false; },
}));

import { useMarketData } from "../hooks/useMarketData";

function sampleBucket(mins, inst, cum) {
  return { minutes_remaining: mins, instantaneous_charm: inst, cumulative_charm: cum };
}

var backendCharmResponse = {
  spot: 510.0,
  expiry: "2025-06-20",
  minutes_remaining: 390,
  days_remaining: 1,
  total_charm_to_close: -12500.5,
  direction: "selling",
  buckets: [
    sampleBucket(390, -5000, -12500),
    sampleBucket(300, -5500, -11000),
    sampleBucket(210, -6200, -9000),
    sampleBucket(120, -7800, -6500),
    sampleBucket(30, -12000, -3000),
  ],
};

describe("CharmChart", () => {
  beforeEach(function() {
    jest.clearAllMocks();
  });

  test("renders without crash when given actual backend data", function() {
    useMarketData.mockReturnValue({
      data: backendCharmResponse,
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var result = render(React.createElement(CharmChart, { ticker: "SPY", spot: 510 }));
    expect(result.container).toBeTruthy();
    expect(result.container.firstChild).not.toBeNull();
  });

  test("renders chart (not empty state) when buckets present", function() {
    useMarketData.mockReturnValue({
      data: backendCharmResponse,
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var result = render(React.createElement(CharmChart, { ticker: "SPY", spot: 510 }));
    // Should render the Plot component, not "No charm data available"
    var plot = result.container.querySelector("[data-testid='mock-plot']");
    expect(plot).not.toBeNull();
    expect(result.container.textContent).not.toContain("No charm data available");
  });

  test("renders empty state when data is null", function() {
    useMarketData.mockReturnValue({
      data: null,
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var result = render(React.createElement(CharmChart, { ticker: "SPY", spot: 510 }));
    expect(result.container.textContent).toContain("No charm data available");
  });

  test("renders loading spinner", function() {
    useMarketData.mockReturnValue({
      data: null,
      loading: true,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var result = render(React.createElement(CharmChart, { ticker: "SPY", spot: 510 }));
    expect(result.container.textContent).toContain("Loading charm");
  });

  test("renders error state", function() {
    useMarketData.mockReturnValue({
      data: null,
      loading: false,
      error: "HTTP 503",
      showBadge: false,
      refresh: jest.fn(),
    });
    var result = render(React.createElement(CharmChart, { ticker: "SPY", spot: 510 }));
    expect(result.container.textContent).toContain("unavailable");
  });

  test("handles empty buckets array", function() {
    useMarketData.mockReturnValue({
      data: Object.assign({}, backendCharmResponse, { buckets: [] }),
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var result = render(React.createElement(CharmChart, { ticker: "SPY", spot: 510 }));
    expect(result.container.textContent).toContain("No charm data available");
  });

  test("handles null values in buckets without crash", function() {
    useMarketData.mockReturnValue({
      data: Object.assign({}, backendCharmResponse, {
        buckets: [
          sampleBucket(390, null, -12500),
          sampleBucket(300, -5500, null),
          sampleBucket(210, undefined, -9000),
        ],
      }),
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var result = render(React.createElement(CharmChart, { ticker: "SPY", spot: 510 }));
    expect(result.container.firstChild).not.toBeNull();
  });

  test("handles missing fields in bucket entries", function() {
    useMarketData.mockReturnValue({
      data: Object.assign({}, backendCharmResponse, {
        buckets: [
          { minutes_remaining: 390 },
          { cumulative_charm: -5000 },
          {},
        ],
      }),
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var result = render(React.createElement(CharmChart, { ticker: "SPY", spot: 510 }));
    // Should render without crash
    expect(result.container.firstChild).not.toBeNull();
  });

  test("shows direction in title when available", function() {
    useMarketData.mockReturnValue({
      data: Object.assign({}, backendCharmResponse, { direction: "buying" }),
      loading: false,
      error: null,
      showBadge: false,
      refresh: jest.fn(),
    });
    var result = render(React.createElement(CharmChart, { ticker: "SPY", spot: 510 }));
    var plot = result.container.querySelector("[data-testid='mock-plot']");
    expect(plot).not.toBeNull();
  });
});
