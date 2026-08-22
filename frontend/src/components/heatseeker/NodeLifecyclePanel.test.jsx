/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import NodeLifecyclePanel from "./NodeLifecyclePanel";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("NodeLifecyclePanel", () => {
  test("renders header during loading", () => {
    useHeatseeker.mockReturnValue({ data: null, loading: true, error: null, refresh: jest.fn() });
    render(<NodeLifecyclePanel ticker="SPY" />);
    expect(screen.getByText("Node Lifecycle")).toBeInTheDocument();
  });

  test("renders strike rows with lifecycle state chips", () => {
    useHeatseeker.mockReturnValue({
      data: {
        nodes: [
          { strike: 500, net_gex: 2e9, taps: 3, state: "fresh", tap_probability: 0.42 },
          { strike: 510, net_gex: -1.5e9, taps: 1, state: "tested", tap_probability: 0.18 },
        ],
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<NodeLifecyclePanel ticker="SPY" />);
    expect(screen.getByText((_, el) => el?.textContent === "$500")).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.textContent === "$510")).toBeInTheDocument();
    expect(screen.getByText("fresh")).toBeInTheDocument();
    expect(screen.getByText("tested")).toBeInTheDocument();
  });

  test("shows empty message when no nodes", () => {
    useHeatseeker.mockReturnValue({
      data: { nodes: [] },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<NodeLifecyclePanel ticker="SPY" />);
    expect(screen.getByText(/no lifecycle data/i)).toBeInTheDocument();
  });
});
