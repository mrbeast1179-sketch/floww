import React from "react";
import { render } from "@testing-library/react";
import { DashboardSummary } from "./DashboardSummary";

jest.mock("axios", () => ({
  get: jest.fn(() => Promise.reject(new Error("test"))),
  post: jest.fn(() => Promise.reject(new Error("test"))),
}));

describe("DashboardSummary", () => {
  test("renders without crashing on null/undefined props", () => {
    const { container } = render(<DashboardSummary ticker="SPY" spot={null} />);
    expect(container).toBeTruthy();
  });
});
