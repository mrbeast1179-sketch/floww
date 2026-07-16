/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import ReverseRugIndicator from "./ReverseRugIndicator";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("ReverseRugIndicator", () => {
  test("renders Floor/Ceiling headers when data present", () => {
    useHeatseeker.mockReturnValue({
      data: { active: true, floor_strike: 490, floor_gex: 2e9, ceiling_strike: 510, ceiling_gex: -1.8e9 },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<ReverseRugIndicator ticker="SPY" />);
    expect(screen.getByText("Reverse Rug")).toBeInTheDocument();
    expect(screen.getByText("Floor")).toBeInTheDocument();
    expect(screen.getByText("Ceiling")).toBeInTheDocument();
    expect(screen.getByText("490")).toBeInTheDocument();
    expect(screen.getByText("510")).toBeInTheDocument();
  });

  test("shows idle pill when active=false", () => {
    useHeatseeker.mockReturnValue({
      data: { active: false, floor_strike: null, ceiling_strike: null },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<ReverseRugIndicator ticker="SPY" />);
    expect(screen.getByText(/○ idle/i)).toBeInTheDocument();
  });
});
