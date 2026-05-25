import React from "react";
import { render, screen } from "@testing-library/react";
import PaperTrade from "./PaperTrade";

jest.mock("axios", () => ({
  get: jest.fn(() => Promise.reject(new Error("test"))),
  post: jest.fn(() => Promise.reject(new Error("test"))),
}));

describe("PaperTrade", () => {
  test("renders without crashing when portfolio is null", () => {
    const { container } = render(<PaperTrade ticker="SPY" spot={null} />);
    expect(container).toBeTruthy();
  });

  test("renders without crashing when spot is undefined", () => {
    const { container } = render(<PaperTrade ticker="SPY" />);
    expect(container).toBeTruthy();
  });

  test("renders without crashing when ticker is empty", () => {
    const { container } = render(<PaperTrade ticker="" spot={745.64} />);
    expect(container).toBeTruthy();
  });
});
