import React from "react";
import { render } from "@testing-library/react";
import { PositionSizing } from "./PositionSizing";

jest.mock("axios", () => ({
  get: jest.fn(() => Promise.reject(new Error("test"))),
  post: jest.fn(() => Promise.reject(new Error("test"))),
}));

describe("PositionSizing", () => {
  test("renders without crashing on null/undefined props", () => {
    const { container } = render(<PositionSizing ticker="SPY" spot={null} />);
    expect(container).toBeTruthy();
  });
});
