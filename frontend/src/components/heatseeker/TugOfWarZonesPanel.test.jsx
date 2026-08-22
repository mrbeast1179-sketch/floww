/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import TugOfWarZonesPanel from "./TugOfWarZonesPanel";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("TugOfWarZonesPanel", () => {
  test("renders ACTIVE state when in tug of war with balanced verdict", () => {
    useHeatseeker.mockReturnValue({
      data: {
        ticker: "SPY",
        in_tug_of_war: true,
        zone_low: 497.5,
        zone_high: 502.5,
        positive_strikes: 4,
        negative_strikes: 3,
        positive_gex: 5e9,
        negative_gex: -4.5e9,
        gex_balance: 0.05,
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<TugOfWarZonesPanel ticker="SPY" spot={500} />);
    expect(screen.getByText("Tug-of-War Zones")).toBeInTheDocument();
    // v2 pill reads "ACTIVE" (no ● glyph), split across the pulse dot span.
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
    expect(screen.getByText(/balanced — tug of war/i)).toBeInTheDocument();
  });

  test("shows no-conflict message when in_tug_of_war=false", () => {
    useHeatseeker.mockReturnValue({
      data: {
        ticker: "SPY",
        in_tug_of_war: false,
        zone_low: null,
        zone_high: null,
        gex_balance: 0,
        positive_gex: 0,
        negative_gex: 0,
        positive_strikes: 0,
        negative_strikes: 0,
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<TugOfWarZonesPanel ticker="SPY" />);
    expect(screen.getByText(/no gex conflict/i)).toBeInTheDocument();
    expect(screen.getByText(/○ idle/i)).toBeInTheDocument();
  });
});
