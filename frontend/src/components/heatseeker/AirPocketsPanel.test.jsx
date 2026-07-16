/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import AirPocketsPanel from "./AirPocketsPanel";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("AirPocketsPanel", () => {
  test("renders header during loading", () => {
    useHeatseeker.mockReturnValue({ data: null, loading: true, error: null, refresh: jest.fn() });
    render(<AirPocketsPanel ticker="SPY" />);
    expect(screen.getByText("Air Pockets")).toBeInTheDocument();
  });

  test("renders pocket rows with low/high range", () => {
    useHeatseeker.mockReturnValue({
      data: {
        air_pockets: [
          { low: 495, high: 502, span_pct: 1.41, max_abs_gex_in_run: 3e9 },
          { low: 510, high: 514, span_pct: 0.78, max_abs_gex_in_run: 1e9 },
        ],
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<AirPocketsPanel ticker="SPY" />);
    expect(screen.getByText("495 – 502")).toBeInTheDocument();
    expect(screen.getByText("510 – 514")).toBeInTheDocument();
    expect(screen.getByText(/pathways, not targets/i)).toBeInTheDocument();
  });

  test("shows empty message when no pockets", () => {
    useHeatseeker.mockReturnValue({
      data: { air_pockets: [] },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<AirPocketsPanel ticker="SPY" />);
    expect(screen.getByText(/no air pockets/i)).toBeInTheDocument();
  });
});
