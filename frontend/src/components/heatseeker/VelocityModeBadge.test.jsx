/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import VelocityModeBadge from "./VelocityModeBadge";

jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

describe("VelocityModeBadge", () => {
  test("renders calm mode pill with velocity value", () => {
    useHeatseeker.mockReturnValue({
      data: { velocity_strikes_per_min: 0.42, mode: "calm", n_snapshots: 24 },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<VelocityModeBadge ticker="SPY" />);
    expect(screen.getByText("Velocity Mode")).toBeInTheDocument();
    expect(screen.getByText("calm")).toBeInTheDocument();
    expect(screen.getByText("0.42")).toBeInTheDocument();
  });

  test("renders urgent mode when velocity is high", () => {
    useHeatseeker.mockReturnValue({
      data: { velocity_strikes_per_min: 3.5, mode: "urgent", n_snapshots: 12 },
      loading: false,
      error: null,
      refresh: jest.fn(),
    });
    render(<VelocityModeBadge ticker="SPY" />);
    expect(screen.getByText("urgent")).toBeInTheDocument();
    expect(screen.getByText("3.50")).toBeInTheDocument();
  });
});
