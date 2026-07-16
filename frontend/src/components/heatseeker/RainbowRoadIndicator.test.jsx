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
    expect(screen.getByText("42.0%")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  test("renders concentrated empty hint when n=0", () => {
    useHeatseeker.mockReturnValue({
      data: { active: false, top_strike_share: 1.0, n_strikes_significant: 0 },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<RainbowRoadIndicator ticker="SPY" />);
    expect(screen.getByText(/concentrated/i)).toBeInTheDocument();
  });
});
