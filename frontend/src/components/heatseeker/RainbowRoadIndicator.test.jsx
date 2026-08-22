/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import RainbowRoadIndicator from "./RainbowRoadIndicator";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("RainbowRoadIndicator", () => {
  test("renders top strike share and n_strikes_significant", () => {
    useHeatseeker.mockReturnValue({
      data: { active: true, top_strike_share: 0.42, n_strikes_significant: 5 },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<RainbowRoadIndicator ticker="SPY" />);
    expect(screen.getByText("Rainbow Road")).toBeInTheDocument();
    // v2 markup: active state shows the CHAOS pill + no-dominant-structure
    // warning (top_strike_share / n_strikes are no longer displayed).
    expect(screen.getByText("CHAOS")).toBeInTheDocument();
    expect(screen.getByText("⚠️ No Dominant Structure")).toBeInTheDocument();
  });

  test("renders concentrated empty hint when n=0", () => {
    useHeatseeker.mockReturnValue({
      data: { active: false, top_strike_share: 1.0, n_strikes_significant: 0 },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<RainbowRoadIndicator ticker="SPY" />);
    // Idle state shows the structure-detected card.
    expect(screen.getByText("Structure Detected")).toBeInTheDocument();
  });
});
