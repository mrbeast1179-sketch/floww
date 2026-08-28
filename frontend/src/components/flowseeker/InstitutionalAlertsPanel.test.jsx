/**
 * @jest-environment jsdom
 */

/**
 * InstitutionalAlertsPanel.test.jsx — Tier-lock sigil wire-up (v3.x)
 *
 * Mount tests via @testing-library/react with a mocked useFlowseeker
 * hook. The Conviction v3.x `tierLockFor` helper is unit-tested in
 * convictionUi.test.js (6 cases); THIS file proves the helper's output
 * actually renders as a chip on the panel — i.e. the `tierLockFor()` call,
 * the conditional JSX, the qcell-position, and the aria-label/title
 * conventions all compose correctly. Without this mount-test a refactor
 * that drops the call silently (e.g. accidentally nested inside a
 * `summary.hasData === false` branch) would still pass the helper suite.
 *
 * Coverage matrix (each case maps to a backend payload shape):
 *   1. tier_locks.GOLD.engaged=true, locked_hit_rate=0.75
 *      → chip renders with "🔒 75%", aria carries rate + locked_at
 *   2. tier_locks.{all}.engaged=false
 *      → ZERO chips render (null-safe)
 *   3. tier_locks.{all} field absent (legacy /alerts/quality payload)
 *      → ZERO chips render
 *   4. tier_locks.GOLD.engaged=true BUT locked_hit_rate=null (corrupt)
 *      → GOLD chip DROPPED (per convictionUi null-coercion contract);
 *      other tiers still untouched
 *   5. tier_locks.SILVER.engaged=true with GOLD/BRONZE engaged=false
 *      → chip renders ONLY in the SILVER qcell (per-tier resolution path).
 *      Catches a regression where the panel-level call resolves the wrong
 *      tier key (e.g. accidentally hard-coded to "GOLD").
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import InstitutionalAlertsPanel from "./InstitutionalAlertsPanel";

// Mock the useFlowseeker hook — both surface uses (feed + quality) must
// return valid-shaped mock data so the panel's destructuring doesn't
// throw on `undefined`. Each test sets up its own mock return per path.
jest.mock("../../hooks/useFlowseeker");
import { useFlowseeker } from "../../hooks/useFlowseeker";

const emptyFeed = { alerts: [], count: 0 };

function mockQualityPaths({ tierLocks, qualityWindows, dailySeries = {} }) {
  useFlowseeker.mockImplementation((path) => {
    if (path === "alerts/feed") {
      return {
        data: emptyFeed, loading: false, error: null,
        refresh: jest.fn(),
      };
    }
    if (path === "alerts/quality") {
      return {
        data: {
          quality_windows: qualityWindows,
          days: [7, 14, 30],
          daily_series: dailySeries,
          ...(tierLocks !== undefined ? { tier_locks: tierLocks } : {}),
        },
        loading: false, error: null,
        refresh: jest.fn(),
      };
    }
    return { data: null, loading: false, error: null, refresh: jest.fn() };
  });
}

// Helper: build a quality payload with one row per tier so the strip
// has Data and the qcell render path runs (without rows, summary.hasData
// is false and the strip — including the sigil slot — never renders).
function goldSilverBronzeWindows(hitRate) {
  const row = (tier, hr) => ({
    tier, rule: "SCORE", hit_rate: hr, n_measured: 4, n: 5, wins: 3,
  });
  return {
    "7":  [row("GOLD", hitRate), row("SILVER", hitRate), row("BRONZE", hitRate)],
    "14": [row("GOLD", hitRate), row("SILVER", hitRate), row("BRONZE", hitRate)],
    "30": [row("GOLD", hitRate), row("SILVER", hitRate), row("BRONZE", hitRate)],
  };
}

describe("InstitutionalAlertsPanel — tier-lock sigil (v3.x)", () => {
  beforeEach(() => {
    useFlowseeker.mockReset();
  });

  test("renders 🔒 75% chip when GOLD tier_locks.engaged is true with a valid rate", () => {
    mockQualityPaths({
      qualityWindows: goldSilverBronzeWindows(0.75),
      tierLocks: {
        GOLD: {
          engaged: true,
          locked_hit_rate: 0.75,
          locked_at: "2026-07-21T09:30:00Z",
        },
        SILVER: { engaged: false, locked_hit_rate: null, locked_at: null },
        BRONZE: { engaged: false, locked_hit_rate: null, locked_at: null },
      },
    });
    render(<InstitutionalAlertsPanel active={true} days={7} limit={100} />);
    // The chip carries role=status + aria-label carrying the rate + locked_at.
    const sigil = screen.getByRole("status", { name: /Tier lock engaged for GOLD/i });
    expect(sigil).toBeInTheDocument();
    expect(sigil).toHaveTextContent("🔒");
    expect(sigil).toHaveTextContent("75%");
    expect(sigil).toHaveTextContent("LOCK");
    expect(sigil).toHaveClass("fsp-chip");
    expect(sigil).toHaveClass("fsp-chip-lock");
    expect(sigil.title).toMatch(/75%/);
    expect(sigil.title).toMatch(/2026-07-21/);
    expect(sigil.title).toMatch(/LOCK/);
    expect(sigil.getAttribute("aria-label")).toMatch(/LOCK/);
  });

  test("renders ZERO lock chips when ALL tier_locks have engaged: false", () => {
    mockQualityPaths({
      qualityWindows: goldSilverBronzeWindows(0.65),
      tierLocks: {
        GOLD:   { engaged: false, locked_hit_rate: null, locked_at: null },
        SILVER: { engaged: false, locked_hit_rate: null, locked_at: null },
        BRONZE: { engaged: false, locked_hit_rate: null, locked_at: null },
      },
    });
    render(<InstitutionalAlertsPanel active={true} days={7} limit={100} />);
    expect(screen.queryByRole("status", { name: /Tier lock engaged/i })).toBeNull();
  });

  test("renders ZERO lock chips when tier_locks field is absent (legacy payload)", () => {
    // Pre-v3.x /alerts/quality response shape — no tier_locks key at all.
    mockQualityPaths({
      qualityWindows: goldSilverBronzeWindows(0.62),
      // tierLocks intentionally omitted.
    });
    render(<InstitutionalAlertsPanel active={true} days={7} limit={100} />);
    expect(screen.queryByRole("status", { name: /Tier lock engaged/i })).toBeNull();
  });

  test("DROPS the GOLD chip when locked_hit_rate is null (corrupted upstream)", () => {
    // The convictionUi null-coercion contract: an engaged tier with a
    // null/NaN locked_hit_rate must NOT render a chip on the strip — a
    // "Lock engaged: GOLD null%" would be visually garbage. Other
    // tiers' state is untouched.
    mockQualityPaths({
      qualityWindows: goldSilverBronzeWindows(0.72),
      tierLocks: {
        GOLD: {
          engaged: true,
          locked_hit_rate: null,              // corrupt — chip must drop
          locked_at: "2026-07-21T09:30:00Z",
        },
        SILVER: { engaged: false, locked_hit_rate: null, locked_at: null },
        BRONZE: { engaged: false, locked_hit_rate: null, locked_at: null },
      },
    });
    render(<InstitutionalAlertsPanel active={true} days={7} limit={100} />);
    expect(screen.queryByRole("status", { name: /Tier lock engaged/i })).toBeNull();
  });

  test("renders chip ONLY in the SILVER qcell when SILVER is the lone locked tier", () => {
    // Per-tier resolution: the panel renders THREE qcells, one per tier.
    // If a future refactor accidentally hard-codes the tier key (e.g. to
    // "GOLD") the SILVER-locked test would fail. Verifies the helper's
    // per-tier payload.tier_locks lookup is wired through correctly.
    mockQualityPaths({
      qualityWindows: goldSilverBronzeWindows(0.62),
      tierLocks: {
        GOLD:   { engaged: false, locked_hit_rate: null, locked_at: null },
        SILVER: {
          engaged: true,
          locked_hit_rate: 0.62,
          locked_at: "2026-07-21T09:30:00Z",
        },
        BRONZE: { engaged: false, locked_hit_rate: null, locked_at: null },
      },
    });
    render(<InstitutionalAlertsPanel active={true} days={7} limit={100} />);
    const sigils = screen.getAllByRole("status", { name: /Tier lock engaged/i });
    // Exactly ONE chip on the strip — the SILVER one. Both the GOLD and
    // BRONZE qcells must NOT contribute a chip.
    expect(sigils).toHaveLength(1);
    expect(sigils[0]).toHaveTextContent("LOCK");
    expect(sigils[0]).toHaveTextContent("62%");
    expect(sigils[0].getAttribute("aria-label")).toMatch(/SILVER/);
  });
});
