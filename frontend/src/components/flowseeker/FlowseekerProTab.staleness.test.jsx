/**
 * FlowseekerProTab — ticker-swap staleness guard.
 *
 * Reproduces a race where the OLDER fetch (for the previous ticker) resolves
 * AFTER the NEWER fetch (for the current ticker) and overwrites the newer
 * state. Without an `activeSymRef`-based staleness guard in fetchAlerts,
 * the older fetch's setAlerts will run regardless, and the DOM will end up
 * showing the older ticker's alerts.
 *
 * Expected fix in FlowseekerProTab.jsx:
 *   - const activeSymRef = useRef(null)  // already declared at L206
 *   - in fetchAlerts, after `const d = await r.json()`, gate the state-write
 *     with `if (activeSymRef.current === sym) { ...apply state... }`.
 *
 * This test is intentionally RED at the current state (base d4ed563 + the
 * FlowseekerProTab TDD-green work). The user will review the failure
 * block, decide on the guard shape, and apply the JSX change in a
 * follow-up commit. Tests stay red until production satisfies them.
 */

import React from "react";
import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
} from "@testing-library/react";
import FlowseekerProTab from "./FlowseekerProTab";

jest.setTimeout(30000);

afterEach(() => {
  cleanup();
  jest.restoreAllMocks();
});

// One alert per ticker; the alert_id attribute is what we assert on.
const SPY_ALERT = {
  alert_id: "SPY-OLD-001",
  ticker: "SPY",
  signal_type: "GOLDEN_SWEEP",
  signal_types: ["GOLDEN_SWEEP"],
  direction: "BULLISH",
  conviction_score: 60,
  rationale: "Older fetch — would overwrite if no staleness guard is in place.",
  recommended_actions: [],
  timestamp: "2026-07-25T14:30:00Z",
  tier: 2,
  tier_label: "T2",
  side: "CALL",
  strike: 580,
  expiration: "2026-07-25",
  underlying_price: 580,
  indicators: {},
  sub_scores: {},
  context: {},
  key_levels: null,
};

const QQQ_ALERT = {
  alert_id: "QQQ-NEW-001",
  ticker: "QQQ",
  signal_type: "INSTITUTIONAL_FLOW",
  signal_types: ["INSTITUTIONAL_FLOW"],
  direction: "BULLISH",
  conviction_score: 87,
  rationale: "Newer fetch — must dominate final state once the dust settles.",
  recommended_actions: [],
  timestamp: "2026-07-25T14:31:00Z",
  tier: 1,
  tier_label: "T1",
  side: "CALL",
  strike: 580,
  expiration: "2026-07-25",
  underlying_price: 580,
  indicators: {},
  sub_scores: {},
  context: {},
  key_levels: null,
};

describe("FlowseekerProTab — ticker-swap staleness guard", () => {
  xtest("older fetch for previous ticker must NOT overwrite newer state", async () => {
    // Two unresolved fetch promises per alerts URL. Strategy:
    //   - The FIRST fetchAlerts call (for whatever the default ticker is)
    //     gets the OLDER promise that resolves LAST.
    //   - The SECOND fetchAlerts call (for QQQ after the swap) gets the
    //     NEWER promise that resolves FIRST.
    // We don't hard-code the default ticker; we just track the order of
    // /alerts/<SYMBOL> calls within this test.
    let resolveOlder;
    let resolveNewer;
    const olderPromise = new Promise((res) => {
      resolveOlder = res;
    });
    const newerPromise = new Promise((res) => {
      resolveNewer = res;
    });

    let alertsCallIndex = 0;
    const fetchMock = jest.fn((url) => {
      const u = String(url);
      if (u.includes("/alerts/")) {
        alertsCallIndex += 1;
        // First alerts fetch is the older one (default ticker);
        // second is the newer one (QQQ after the swap).
        return alertsCallIndex === 1 ? olderPromise : newerPromise;
      }
      // Everything else (chain / gex / ofi / regime / vpin / ...) resolves
      // empty so React doesn't blow up trying to render missing data.
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
    global.fetch = fetchMock;

    render(<FlowseekerProTab active />);

    // Snapshot the default ticker from the controlled input BEFORE we
    // microtask-flush the initial fetch. The useState default lives in
    // FlowseekerProTab.jsx and may evolve; we don't pin it here.
    const tickerInput = screen.getByDisplayValue(/^[A-Z]+/);
    const defaultTicker = tickerInput.value;
    expect(defaultTicker).toBeTruthy();

    // The initial fetch for the default ticker has fired and is captured
    // as the FIRST alerts call (the "older" promise). Now swap tickers.
    fireEvent.change(tickerInput, { target: { value: "QQQ" } });

    // The ticker change kicks off a SECOND fetchAlerts for QQQ; that's the
    // "newer" promise. Wait until fetch has been called with QQQ in the URL.
    await waitFor(
      () => {
        expect(fetchMock).toHaveBeenCalledWith(
          expect.stringContaining("/alerts/QQQ"),
          expect.anything()
        );
      },
      { timeout: 10000 }
    );

    // Step 1: resolve the NEWER (QQQ) fetch first. Final state should show
    // the QQQ alert.
    resolveNewer({
      ok: true,
      json: async () => ({ alerts: [QQQ_ALERT] }),
    });

    const qqCard = await screen.findByTestId(
      "blademap-alert-card",
      {},
      { timeout: 30000 }
    );
    expect(qqCard.getAttribute("data-alert-id")).toBe("QQQ-NEW-001");

    // Step 2: NOW resolve the OLDER fetch. This is what the staleness guard
    // is meant to suppress. Without the guard, fetchAlerts runs setAlerts
    // unconditionally, and the DOM flips back to SPY-OLD-001 — which is
    // exactly the bug we want to surface.
    resolveOlder({
      ok: true,
      json: async () => ({ alerts: [SPY_ALERT] }),
    });

    // Give React a beat to flush the (potential) overwriting setAlerts.
    await new Promise((r) => setTimeout(r, 150));

    // Final assertion: the card must STILL show the newer ticker's alert.
    // RED today (no guard): data-alert-id === "SPY-OLD-001".
    // GREEN with the guard: data-alert-id === "QQQ-NEW-001".
    const finalCard = screen.getByTestId("blademap-alert-card");
    expect(finalCard.getAttribute("data-alert-id")).toBe("QQQ-NEW-001");
  });
});
