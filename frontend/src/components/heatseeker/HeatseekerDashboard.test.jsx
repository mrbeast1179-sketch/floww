import React from "react";
import { render, screen } from "@testing-library/react";
import HeatseekerDashboard from "./HeatseekerDashboard";

// Mock the shared fetch hook once — every child panel calls it. We return a
// minimal { data: null, loading: false, error: null } so children render their
// empty/idle states without exploding on missing fields.
jest.mock("../../hooks/useHeatseeker", () => ({
  __esModule: true,
  useHeatseeker: jest.fn(),
}));

import { useHeatseeker } from "../../hooks/useHeatseeker";

const IDLE = { data: null, loading: false, error: null, refresh: () => {} };

describe("HeatseekerDashboard", () => {
  beforeEach(() => {
    useHeatseeker.mockReturnValue(IDLE);
  });

  test("renders header with ticker and Wave 1+2+3 caption", () => {
    render(<HeatseekerDashboard ticker="SPY" spot={500} />);
    expect(screen.getByText("Skylit Heatseeker")).toBeInTheDocument();
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText(/Wave 1 \+ 2 \+ 3/i)).toBeInTheDocument();
  });

  test("mounts all 12 child panels via their test-ids", () => {
    render(<HeatseekerDashboard ticker="SPY" spot={500} />);
    expect(screen.getByTestId("heatseeker-dashboard")).toBeInTheDocument();
    [
      "hs-flip-zones",
      "hs-node-lifecycle",
      "hs-air-pockets",
      "hs-beach-ball",
      "hs-reverse-rug",
      "hs-rainbow-road",
      "hs-velocity-mode",
      "hs-trinity-confluence",
      "hs-rolling-floors-ceilings",
      "hs-tug-of-war",
      "hs-node-classification",
      "hs-stacked-nodes",
    ].forEach((tid) => expect(screen.getByTestId(tid)).toBeInTheDocument());
  });

  test("strips leading caret from index symbols like ^SPX", () => {
    render(<HeatseekerDashboard ticker="^SPX" />);
    expect(screen.getByText("SPX")).toBeInTheDocument();
  });
});
