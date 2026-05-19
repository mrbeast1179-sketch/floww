import React from "react";
import { render, screen } from "@testing-library/react";
import TrinityConfluenceMeter from "./TrinityConfluenceMeter";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("TrinityConfluenceMeter", () => {
  test("renders score gauge and aligned/divergent lists", () => {
    useHeatseeker.mockReturnValue({
      data: {
        score: 72,
        verdict: "Aligned bull",
        aligned_dimensions: ["GEX", "Vol"],
        divergences: ["OI"],
      },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<TrinityConfluenceMeter />);
    expect(screen.getByText("Trinity Confluence")).toBeInTheDocument();
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.getByText("Aligned bull")).toBeInTheDocument();
    expect(screen.getByText(/GEX/)).toBeInTheDocument();
    expect(screen.getByText(/OI/)).toBeInTheDocument();
  });

  test("renders with empty lists when missing", () => {
    useHeatseeker.mockReturnValue({
      data: { score: 0, verdict: "Neutral", aligned_dimensions: [], divergences: [] },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<TrinityConfluenceMeter />);
    expect(screen.getByText("Aligned")).toBeInTheDocument();
    expect(screen.getByText("Divergent")).toBeInTheDocument();
  });
});
