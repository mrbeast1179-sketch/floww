import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import FlowseekerTab from "./FlowseekerTab";

const SWEEP = {
  timestamp: "2026-06-01T14:30:00Z", ticker: "SPY", strike: 500, expiration: "2026-06-20",
  side: "buy", type: "C", size: 1000, price: 1.2, premium: 120000, volume: 50, oi: 10,
  vol_oi_ratio: 5, chain_ratio: 1.1, classification: "sweep", conditions: [], ask_pct: 0.9,
  spot: 499, bid: 1.1, ask: 1.3, exchange: "CBOE"
};
const BLOCK = { ...SWEEP, classification: "block", strike: 510, premium: 80000 };
const REGULAR = { ...SWEEP, classification: "regular", strike: 520, premium: 5000 };

beforeEach(() => {
  global.fetch = jest.fn().mockImplementation((url) => {
    if (url.includes("/flowseeker/drilldown")) {
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => ({
          symbol: "SPY", volume: 1000, oi: 500, chain_ratio: 1.4,
          recent_prints: [SWEEP], vol_oi_history: [1, 2, 3]
        }),
      });
    }
    return Promise.resolve({
      ok: true, status: 200,
      json: async () => ({ ticker: "SPY", count: 3, prints: [SWEEP, BLOCK, REGULAR] }),
    });
  });
});

test("renders all rows + filter to Sweeps + click opens drilldown", async () => {
  render(<FlowseekerTab active={true} />);

  // All 3 rows show
  await waitFor(() => expect(screen.getByText("SWP")).toBeInTheDocument());
  expect(screen.getByText("BLK")).toBeInTheDocument();
  // regular has no badge, but its strike should be visible
  expect(screen.getByText("520")).toBeInTheDocument();

  // Click "Sweeps" filter
  fireEvent.click(screen.getByText("Sweeps"));
  // Only sweep row should remain
  await waitFor(() => expect(screen.queryByText("BLK")).not.toBeInTheDocument());
  expect(screen.getByText("SWP")).toBeInTheDocument();

  // Click a row → FlowDrilldown modal appears
  fireEvent.click(screen.getByText("500").closest("tr"));
  await waitFor(() =>
    expect(screen.getByTestId("flow-drilldown-modal")).toBeInTheDocument()
  );
});
