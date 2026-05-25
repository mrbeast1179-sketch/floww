import React from "react";
import { render } from "@testing-library/react";
import PaperTrade from "./PaperTrade";

test("does not crash when portfolio is null", () => {
  const { container } = render(<PaperTrade ticker="SPY" spot={null} />);
  expect(container).toBeTruthy();
});

test("does not crash when spot is undefined", () => {
  const { container } = render(<PaperTrade ticker="SPY" />);
  expect(container).toBeTruthy();
});

test("renders form fields", () => {
  const { getByDisplayValue } = render(<PaperTrade ticker="SPY" spot={500} />);
  expect(getByDisplayValue("SPY")).toBeTruthy();
  expect(getByDisplayValue("1")).toBeTruthy();
});
