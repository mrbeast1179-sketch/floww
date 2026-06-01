import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import FlowFilters from "./FlowFilters";

const noop = () => {};

test("clicking Sweeps calls onChange with classification=sweep", () => {
  const onChange = jest.fn();
  render(<FlowFilters value={{ ticker: "SPY", classification: "all", minPremium: 0 }} onChange={onChange} />);
  fireEvent.click(screen.getByText("Sweeps"));
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ classification: "sweep" }));
});

test("typing a ticker calls onChange with uppercased ticker", () => {
  const onChange = jest.fn();
  render(<FlowFilters value={{ ticker: "", classification: "all", minPremium: 0 }} onChange={onChange} />);
  const input = screen.getByPlaceholderText(/ticker/i);
  fireEvent.change(input, { target: { value: "spy" } });
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ ticker: "SPY" }));
});

test("min-premium input calls onChange with number", () => {
  const onChange = jest.fn();
  render(<FlowFilters value={{ ticker: "SPY", classification: "all", minPremium: 0 }} onChange={onChange} />);
  const input = screen.getByPlaceholderText(/min premium/i);
  fireEvent.change(input, { target: { value: "50000" } });
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ minPremium: 50000 }));
});
