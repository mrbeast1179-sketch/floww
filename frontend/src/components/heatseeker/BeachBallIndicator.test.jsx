import React from "react";
import { render, screen } from "@testing-library/react";
import BeachBallIndicator from "./BeachBallIndicator";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("BeachBallIndicator", () => {
  test("renders header and idle pill when inactive", () => {
    useHeatseeker.mockReturnValue({
      data: { active: false, king_node: 500, spot_distance_pct: 0.5, direction: "up", confidence: 0.4 },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<BeachBallIndicator ticker="SPY" />);
    expect(screen.getByText("Beach Ball")).toBeInTheDocument();
    expect(screen.getByText(/○ idle/i)).toBeInTheDocument();
  });

  test("renders ACTIVE pill when active=true", () => {
    useHeatseeker.mockReturnValue({
      data: { active: true, king_node: 500, spot_distance_pct: -0.8, direction: "down", confidence: 0.75 },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<BeachBallIndicator ticker="SPY" />);
    expect(screen.getByText(/● active/i)).toBeInTheDocument();
    expect(screen.getByText("500")).toBeInTheDocument();
  });
});
