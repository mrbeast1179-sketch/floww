/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import NodeClassificationPanel from "./NodeClassificationPanel";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("NodeClassificationPanel", () => {
  test("renders REAL and HEDGE columns with classified nodes", () => {
    useHeatseeker.mockReturnValue({
      data: {
        ticker: "SPY",
        spot: 500,
        real_count: 1,
        hedge_count: 1,
        nodes: [
          { strike: 505, net_gex: 2e9, taps: 2, state: "fresh", tap_probability: 42, gamma_sign: 1, oi_trend: "growing", classification: "real" },
          { strike: 495, net_gex: -1.4e9, taps: 1, state: "decaying", tap_probability: 18, gamma_sign: -1, oi_trend: "fading", classification: "hedge" },
        ],
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<NodeClassificationPanel ticker="SPY" />);
    expect(screen.getByText("Node Classification")).toBeInTheDocument();
    // v2 headers: "Real (N)" with count in nested element — match on the
    // column div's combined textContent.
    expect(screen.getByText((_, el) =>
      el?.className?.includes?.("text-emerald-400") && /real\s*\(\s*1\s*\)/i.test(el.textContent || "")
    )).toBeInTheDocument();
    expect(screen.getByText((_, el) =>
      el?.className?.includes?.("text-amber-400") && /hedge\s*\(\s*1\s*\)/i.test(el.textContent || "")
    )).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.textContent === "$505")).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.textContent === "$495")).toBeInTheDocument();
  });

  test("renders empty columns when no nodes", () => {
    useHeatseeker.mockReturnValue({
      data: { ticker: "SPY", spot: 500, real_count: 0, hedge_count: 0, nodes: [] },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<NodeClassificationPanel ticker="SPY" />);
    // Empty state: v2 collapses to "No classified nodes" + the R/H counter.
    expect(screen.getByText("No classified nodes")).toBeInTheDocument();
  });
});
