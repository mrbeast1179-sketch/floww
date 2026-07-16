/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import FlipZonesPanel from "./FlipZonesPanel";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("FlipZonesPanel", () => {
  test("renders header even while loading", () => {
    useHeatseeker.mockReturnValue({ data: null, loading: true, error: null, refresh: jest.fn() });
    render(<FlipZonesPanel ticker="SPY" />);
    expect(screen.getByText("Flip Zones")).toBeInTheDocument();
    expect(screen.getByTestId("hs-flip-zones")).toBeInTheDocument();
  });

  test("renders flip zones rows with strike price", () => {
    useHeatseeker.mockReturnValue({
      data: {
        window_low: 480,
        window_high: 520,
        flip_zones: [
          { price: 502, from_sign: -1, to_sign: 1, strength: 2e9 },
          { price: 495, from_sign: 1, to_sign: -1, strength: 1.5e9 },
        ],
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<FlipZonesPanel ticker="SPY" spot={500} />);
    expect(screen.getByText("502.0")).toBeInTheDocument();
    expect(screen.getByText("495.0")).toBeInTheDocument();
  });

  test("shows empty-state message when no flip zones", () => {
    useHeatseeker.mockReturnValue({
      data: { flip_zones: [] },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<FlipZonesPanel ticker="SPY" />);
    expect(screen.getByText(/no flip zones/i)).toBeInTheDocument();
  });
});
