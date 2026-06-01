import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import FlowTable from "./FlowTable";

const P = {
  timestamp: "2026-06-01T14:30:00Z", ticker: "SPY", strike: 500, expiration: "2026-06-20",
  side: "buy", type: "C", size: 1000, price: 1.2, premium: 120000, volume: 50, oi: 10,
  vol_oi_ratio: 5, chain_ratio: 1.1, classification: "unusual", conditions: [], ask_pct: 0.9,
  spot: 499, bid: 1.1, ask: 1.3, exchange: "CBOE"
};

test("renders rows + classification badge", () => {
  render(<FlowTable prints={[P]} loading={false} error={null} onSelect={() => {}} />);
  expect(screen.getByText("UNU")).toBeInTheDocument();
  expect(screen.getByText("500")).toBeInTheDocument();
});

test("empty state when no prints", () => {
  render(<FlowTable prints={[]} loading={false} error={null} onSelect={() => {}} />);
  expect(screen.getByText(/no flow/i)).toBeInTheDocument();
});

test("row click calls onSelect with the print", () => {
  const onSelect = jest.fn();
  render(<FlowTable prints={[P]} loading={false} error={null} onSelect={onSelect} />);
  fireEvent.click(screen.getByText("500").closest("tr"));
  expect(onSelect).toHaveBeenCalledWith(P);
});
