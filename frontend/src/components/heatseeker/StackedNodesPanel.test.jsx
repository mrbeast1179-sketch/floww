import React from "react";
import { render, screen } from "@testing-library/react";
import StackedNodesPanel from "./StackedNodesPanel";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("StackedNodesPanel", () => {
  test("renders stacked strike rows with put/call labels", () => {
    useHeatseeker.mockReturnValue({
      data: {
        ticker: "SPY",
        spot: 500,
        count: 2,
        stacked_nodes: [
          { strike: 500, call_gex: 2e9, put_gex: -1.8e9, conflict: true },
          { strike: 505, call_gex: 1e9, put_gex: -0.9e9, conflict: true },
        ],
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<StackedNodesPanel ticker="SPY" />);
    expect(screen.getByText("Stacked Nodes")).toBeInTheDocument();
    expect(screen.getByText("500")).toBeInTheDocument();
    expect(screen.getByText("505")).toBeInTheDocument();
    expect(screen.getByText(/two-sided dealer footprint/i)).toBeInTheDocument();
  });

  test("shows empty message when no stacked nodes", () => {
    useHeatseeker.mockReturnValue({
      data: { ticker: "SPY", spot: 500, count: 0, stacked_nodes: [] },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<StackedNodesPanel ticker="SPY" />);
    expect(screen.getByText(/no stacked conflict/i)).toBeInTheDocument();
  });
});
