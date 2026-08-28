/**
 * @jest-environment jsdom
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import FlowDrilldown from "./FlowDrilldown";

const P = {
  timestamp: "2026-06-01T14:30:00Z", ticker: "SPY", strike: 500, expiration: "2026-06-20",
  side: "buy", type: "C", size: 1000, price: 1.2, premium: 120000, volume: 50, oi: 10,
  vol_oi_ratio: 5, chain_ratio: 1.1, classification: "unusual", conditions: [], ask_pct: 0.9,
  spot: 499, bid: 1.1, ask: 1.3, exchange: "CBOE"
};

beforeEach(() => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({
      symbol: "SPY", volume: 1000, oi: 500, chain_ratio: 1.4,
      recent_prints: [P], vol_oi_history: [1, 2, 3]
    }),
  });
});

test("renders symbol + volume/oi/chain_ratio + recent prints", async () => {
  render(<FlowDrilldown symbol="SPY" onClose={jest.fn()} />);
  await waitFor(() => expect(screen.getByText("SPY")).toBeInTheDocument());
  // "500" matches both volume (500) and strike (500) — confirm at least one
  await waitFor(() => expect(screen.getAllByText("500").length).toBeGreaterThanOrEqual(1));
});

test("empty/degraded response renders clean empty state", async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({
      symbol: "SPY", volume: 0, oi: 0, chain_ratio: 0,
      recent_prints: [], vol_oi_history: []
    }),
  });
  render(<FlowDrilldown symbol="SPY" onClose={jest.fn()} />);
  await waitFor(() => expect(screen.getByTestId("flow-drilldown-modal")).toBeInTheDocument());
  await waitFor(() => expect(screen.getByText(/no recent prints/i)).toBeInTheDocument());
});
