/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import RollingFloorsCeilingsPanel from "./RollingFloorsCeilingsPanel";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("RollingFloorsCeilingsPanel", () => {
  test("renders bullish verdict + floor/ceiling series", () => {
    useHeatseeker.mockReturnValue({
      data: {
        ticker: "SPY",
        floor_series: [480, 482, 485, 488],
        ceiling_series: [510, 512, 514, 515],
        floor_trend: "rising",
        ceiling_trend: "rising",
        signal: "bullish",
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<RollingFloorsCeilingsPanel ticker="SPY" />);
    expect(screen.getByText("Rolling Floors / Ceilings")).toBeInTheDocument();
    expect(screen.getByText("bullish")).toBeInTheDocument();
    expect(screen.getByText(/floors rolling up/i)).toBeInTheDocument();
    expect(screen.getByText("Floors")).toBeInTheDocument();
    expect(screen.getByText("Ceilings")).toBeInTheDocument();
  });

  test("renders bearish verdict label", () => {
    useHeatseeker.mockReturnValue({
      data: {
        ticker: "SPY",
        floor_series: [],
        ceiling_series: [510, 508],
        floor_trend: "flat",
        ceiling_trend: "falling",
        signal: "bearish",
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<RollingFloorsCeilingsPanel ticker="SPY" />);
    expect(screen.getByText("bearish")).toBeInTheDocument();
    expect(screen.getByText(/ceilings rolling down/i)).toBeInTheDocument();
  });
});
