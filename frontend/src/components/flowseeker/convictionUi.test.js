// convictionUi.test.js — Jest tests for the v3.x tier-lock helper.
//
// Mirrors backend/services/tier_lock.py contract: tier_locks payload
// shape is `{GOLD|SILVER|BRONZE: {engaged, locked_hit_rate, locked_at}}`.
// The helper must be null-safe against legacy payloads (no tier_locks)
// and missing-key entries (a tier never engaged should not render a
// sigil even if its neighbors are).

import { tierLockFor } from "./convictionUi.js";

describe("tierLockFor (v3.x tier-lock hysteresis)", () => {
  test("returns the engaged struct when tier_locks[tier].engaged is true", () => {
    const payload = {
      tier_locks: {
        GOLD: { engaged: true, locked_hit_rate: 0.75, locked_at: "2026-07-21T09:30:00" },
        SILVER: { engaged: false, locked_hit_rate: null, locked_at: null },
        BRONZE: { engaged: false, locked_hit_rate: null, locked_at: null },
      },
    };
    expect(tierLockFor("GOLD", payload)).toEqual({
      engaged: true,
      locked_hit_rate: 0.75,
      locked_at: "2026-07-21T09:30:00",
    });
  });

  test("returns null when the tier is not engaged", () => {
    const payload = {
      tier_locks: {
        GOLD: { engaged: false, locked_hit_rate: null, locked_at: null },
        SILVER: { engaged: false, locked_hit_rate: null, locked_at: null },
        BRONZE: { engaged: false, locked_hit_rate: null, locked_at: null },
      },
    };
    expect(tierLockFor("GOLD", payload)).toBeNull();
    expect(tierLockFor("SILVER", payload)).toBeNull();
  });

  test("returns null when tier is missing from tier_locks map", () => {
    const payload = {
      tier_locks: {
        GOLD: { engaged: true, locked_hit_rate: 0.74, locked_at: "2026-07-21T09:30:00" },
        // SILVER / BRONZE absent (legacy partial payload from an earlier  /
        // alerts/quality version)
      },
    };
    expect(tierLockFor("SILVER", payload)).toBeNull();
    expect(tierLockFor("BRONZE", payload)).toBeNull();
  });

  test("returns null for legacy payload lacking tier_locks at all", () => {
    // Pre-v3.x /alerts/quality response shape — the sigil MUST degrade
    // gracefully (no crash, no errant render) since production users
    // could be hitting the route with cached responses before rolling
    // forward to the new shape.
    const payload = {
      quality_windows: { "30": [{ tier: "GOLD", hit_rate: 0.62, n_measured: 5 }] },
      days: [7, 14, 30],
      daily_series: {},
    };
    expect(tierLockFor("GOLD", payload)).toBeNull();
  });

  test("returns null for null/undefined payload (defensive nil-safety)", () => {
    expect(tierLockFor("GOLD", null)).toBeNull();
    expect(tierLockFor("GOLD", undefined)).toBeNull();
    expect(tierLockFor("GOLD", {})).toBeNull();
  });

  test("norm tier to uppercase before lookup (lowercase input must work)", () => {
    const payload = {
      tier_locks: {
        GOLD: { engaged: true, locked_hit_rate: 0.65, locked_at: "2026-07-21T09:30:00" },
      },
    };
    expect(tierLockFor("gold", payload)).toEqual({
      engaged: true,
      locked_hit_rate: 0.65,
      locked_at: "2026-07-21T09:30:00",
    });
  });
});
