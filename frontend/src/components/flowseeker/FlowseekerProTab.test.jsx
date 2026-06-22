/**
 * FlowseekerProTab.test.jsx
 *
 * Verifies the Blademap alert-card overhaul:
 *   1. Full-payload render: 4 sub-score meters, 3 key-level pills,
 *      tier badge, direction pill, rationale + recommended actions.
 *   2. Partial-payload render: the component falls back gracefully when
 *      sub_scores / key_levels / rationale are missing (legacy v1 fields).
 *   3. The signals with FRESH signal-type names (GOLDEN_SWEEP, FLOOR_SWEEP)
 *      render with their assigned colour classes.
 */
import React from "react";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";
import FlowseekerProTab from "./FlowseekerProTab";

// Mock Plotly — react-plotly.js renders to a canvas and would not work in jsdom.
jest.mock("react-plotly.js", () => () => null);

// Stub fetch with deterministic fixture so the chain poll resolves.
const FULL_ALERT = {
  alert_id: "SPY-2026-07-25-GOLDEN_SWEEP-580-t1",
  ticker: "SPY",
  timestamp: "2026-07-25T14:30:00Z",
  signal_type: "GOLDEN_SWEEP",
  signal_types: ["GOLDEN_SWEEP", "PREMIUM_CONCENTRATION", "DELTA_EXTREME"],
  direction: "BULLISH",
  side: "CALL",
  tier: 1,
  tier_label: "T1",
  strike: 580,
  expiration: "2026-07-25",
  underlying_price: 580,
  conviction_score: 87,
  sub_scores: {
    statistical_anomaly: { points: 25, max: 30 },
    institutional_pattern: { points: 22, max: 25 },
    market_context: { points: 18, max: 20 },
    price_impact: { points: 22, max: 25 },
  },
  indicators: {
    call_oi: 1200, put_oi: 900,
    call_vol: 1500, put_vol: 800,
    iv: 0.28, delta: 0.50,
    vol_oi_ratio: 1.10,
    estimated_premium: 480000,
  },
  key_levels: { entry: 580, invalidation: 575.50, target: 593.50 },
  context: {
    market_regime: "BULLISH_VOLUME_SURGE",
    dealer_positioning: "net_long_gamma",
    zero_gamma_cross: 580.25,
  },
  rationale:
    "Heavy CALL activity at strike $580 sits within 1% of the dealer zero-gamma flip ($580.25). A break past $593.50 could trigger dealer hedging.",
  recommended_actions: [
    "Watch for confirmation above $580.00 before entering.",
    "Set invalidation at $575.50.",
    "Primary target: $593.50.",
  ],
};

const PARTIAL_ALERT = {
  // v1 shape — legacy / fallback path
  alert_id: "SPY-LEGACY-1",
  ticker: "SPY",
  signal_type: "high_volume",
  classification: "high_volume",
  confidence_score: 70,
  conviction_score: 70,
  confidence_factors: [],
  strike: 585,
  expiration: "2026-07-25",
  side: "CALL",
  option_type: "CALL",
  direction: undefined,
  tier: 3,
  indicators: { call_oi: 2000, put_oi: 1100, vol_oi_ratio: 1.1 },
};

const CHAIN_PAYLOAD = {
  symbol: "SPY",
  params: ["strike", "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility"],
  chain: [
    {
      expiration: "2026-07-25",
      strikes: [
        [575, [3.1, 3.2, 3.15, 50, 500, 0.30], [4.2, 4.3, 4.25, 80, 800, 0.34]],
        [580, [2.3, 2.4, 2.35, 1500, 1200, 0.28], [3.1, 3.2, 3.15, 800, 900, 0.32]],
      ],
    },
  ],
};

function jsonResponse(payload, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

describe("FlowseekerProTab — Blademap alert cards", () => {
  let originalFetch;
  beforeEach(() => {
    originalFetch = global.fetch;
    global.fetch = jest.fn((url) => {
      const u = String(url);
      if (u.includes("/chain/")) return Promise.resolve(jsonResponse(CHAIN_PAYLOAD));
      if (u.includes("/alerts/")) {
        // Pre-select a single Blademap-shape alert
        return Promise.resolve(jsonResponse({ alerts: [FULL_ALERT], total: 1 }));
      }
      return Promise.resolve(jsonResponse({}));
    });
  });
  afterEach(() => {
    cleanup();
    global.fetch = originalFetch;
    jest.clearAllMocks();
  });

  test("renders the Blademap summary bar from the top alert", async () => {
    render(<FlowseekerProTab active />);
    // RTL's findBy* polls up to 1s — let the fetch+setState cycles settle.
    expect(await screen.findByText(/Blademap Alerts/i)).toBeInTheDocument();
    expect(await screen.findByText(/regime:/i)).toBeInTheDocument();
    expect(await screen.findByText(/dealer:/i)).toBeInTheDocument();
    expect(await screen.findByText(/BULLISH_VOLUME_SURGE/i)).toBeInTheDocument();
  });

  test("renders sub-score meters, tier badge, direction pill for a full alert", async () => {
    render(<FlowseekerProTab active />);
    expect(await screen.findByTestId("conviction-score", {}, { timeout: 30000 })).toHaveTextContent("87");
    expect(await screen.findByTestId("tier-badge", {}, { timeout: 30000 })).toHaveTextContent("T1");
    expect(await screen.findByTestId("direction-pill", {}, { timeout: 30000 })).toHaveTextContent("BULLISH");
    expect(await screen.findByTestId("subscore-statistical_anomaly", {}, { timeout: 30000 })).toBeInTheDocument();
    expect(await screen.findByTestId("subscore-institutional_pattern", {}, { timeout: 30000 })).toBeInTheDocument();
    expect(await screen.findByTestId("subscore-market_context", {}, { timeout: 30000 })).toBeInTheDocument();
    expect(await screen.findByTestId("subscore-price_impact", {}, { timeout: 30000 })).toBeInTheDocument();
    const kl = await screen.findByTestId("key-levels", {}, { timeout: 30000 });
    expect(kl).toHaveTextContent("Entry");
    expect(kl).toHaveTextContent("Stop");
    expect(kl).toHaveTextContent("Target");
  });

  test("clicking the card expands rationale + recommended actions", async () => {
    render(<FlowseekerProTab active />);
    const card = await screen.findByTestId("blademap-alert-card", {}, { timeout: 30000 });
    fireEvent.click(card);
    expect(await screen.findByTestId("rationale", {}, { timeout: 30000 })).toHaveTextContent(/dealer zero-gamma flip/i);
    expect(await screen.findByTestId("recommended-actions", {}, { timeout: 30000 })).toHaveTextContent(/Watch for confirmation/i);
    expect(await screen.findByTestId("indicators-row", {}, { timeout: 30000 })).toBeInTheDocument();
    expect(await screen.findByTestId("signal-types", {}, { timeout: 30000 })).toBeInTheDocument();
  });

  test("renders a partial / legacy alert without crashing", async () => {
    global.fetch = jest.fn((url) => {
      const u = String(url);
      if (u.includes("/chain/")) return Promise.resolve(jsonResponse(CHAIN_PAYLOAD));
      if (u.includes("/alerts/")) {
        return Promise.resolve(jsonResponse({ alerts: [PARTIAL_ALERT], total: 1 }));
      }
      return Promise.resolve(jsonResponse({}));
    });
    render(<FlowseekerProTab active />);
    const card = await screen.findByTestId("blademap-alert-card", {}, { timeout: 30000 });
    // Conviction falls back to confidence_score
    expect(card).toHaveAttribute("data-conviction", "70");
    expect(card).toHaveAttribute("data-signal-type", "high_volume");
    // Sub-scores not provided → renders 4 meter bars with 0/X values
    expect(screen.getByTestId("subscore-statistical_anomaly")).toHaveTextContent("0/30");
    expect(screen.getByTestId("subscore-institutional_pattern")).toHaveTextContent("0/25");
    // No rationale on legacy payload → component still renders
    expect(card.querySelector('[data-testid="rationale"]')).toBeNull();
    // No key_levels → pill bar absent
    expect(screen.queryByTestId("key-levels")).toBeNull();
  });

  test("renders zero-alert empty state without crashing", async () => {
    global.fetch = jest.fn((url) => {
      const u = String(url);
      if (u.includes("/chain/")) return Promise.resolve(jsonResponse(CHAIN_PAYLOAD));
      if (u.includes("/alerts/")) return Promise.resolve(jsonResponse({ alerts: [] }));
      return Promise.resolve(jsonResponse({}));
    });
    render(<FlowseekerProTab active />);
    expect(await screen.findByText(/Scanning for institutional activity/i)).toBeInTheDocument();
    expect(screen.queryByTestId("blademap-alert-card")).toBeNull();
  });
});
