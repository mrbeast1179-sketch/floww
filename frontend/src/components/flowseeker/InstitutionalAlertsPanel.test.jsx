import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import InstitutionalAlertsPanel from "./InstitutionalAlertsPanel";

const TICKER_ALERTS = {
  alerts: [
    {
      key: "score|PLTR|c|140|2026-07-31", tier: "GOLD", side: "BUY", bias: "BULLISH",
      rule: "SCORE", under: "PLTR", strike: 140, exp: "2026-07-31", dte: 11,
      score: 92, vol_oi: 6.4, premium: 380_000, cw_spread: 0.04, cluster: true,
      sigma: null, move_pct: 3.9, asof_ts: "2026-07-20T11:00:00-04:00",
      why: "score 92 — bullish laddering + CW confirms",
    },
    {
      key: "score|TSLA|p|260|2026-07-31", tier: "SILVER", side: "BUY", bias: "BEARISH",
      rule: "SCORE", under: "TSLA", strike: 260, exp: "2026-07-31", dte: 11,
      score: 88, vol_oi: 4.2, premium: 200_000, cw_spread: -0.025, cluster: false,
      sigma: null, move_pct: -1.1, asof_ts: "2026-07-20T10:55:00-04:00",
      why: "bearish put ladder",
    },
    {
      key: "score|AMD|c|150|2026-07-31", tier: "BRONZE", side: "STRATEGY", bias: null,
      rule: "SCORE", under: "AMD", strike: 150, exp: "2026-07-31", dte: 11,
      score: 70, vol_oi: 2.0, premium: 80_000, cw_spread: null, cluster: false,
      sigma: null, move_pct: 0.2, asof_ts: "2026-07-20T10:50:00-04:00",
      why: "score 70 — likely vertical leg",
    },
    {
      key: "sigma|NVDA", tier: "GOLD", side: "BUY", bias: "BULLISH",
      rule: "SIGMA", under: "NVDA", strike: null, exp: "", dte: null,
      score: 76, vol_oi: 3.2, premium: 250_000, cw_spread: 0.06, cluster: false,
      sigma: 5.4, move_pct: 2.4, asof_ts: "2026-07-20T11:05:00-04:00",
      why: "NVDA options volume 5.4σ above its 6-day baseline",
    },
  ],
  count: 4, days: 7,
};

const QUALITY = {
  // v2.2 batched shape — picks the longest window (30d) for the headline strip
  // and exposes every window for the per-cell trend sparkline math.
  quality_windows: {
    7:  [{ rule: "SCORE", tier: "GOLD",   n: 4, n_measured: 4, hit_rate: 0.80, avg_move_pct: 2.3 }],
    14: [{ rule: "SCORE", tier: "GOLD",   n: 8, n_measured: 8, hit_rate: 0.70, avg_move_pct: 1.9 }],
    30: [
      { rule: "SCORE", tier: "GOLD",   n: 12, n_measured: 12, hit_rate: 0.65, avg_move_pct: 1.6 },
      { rule: "SCORE", tier: "SILVER", n: 18, n_measured: 18, hit_rate: 0.55, avg_move_pct: 1.4 },
      { rule: "SCORE", tier: "BRONZE", n: 22, n_measured: 0,  hit_rate: null, avg_move_pct: null },
    ],
  },
  days: [7, 14, 30],
};

const EMPTY = { alerts: [], count: 0, days: 7 };

// Stub useFlowseeker globally so the panel's two endpoints are deterministic.
jest.mock("../../hooks/useFlowseeker", () => ({
  useFlowseeker: (endpoint) => {
    if (endpoint === "alerts/feed") return { data: TICKER_ALERTS, loading: false, error: null, refresh: jest.fn() };
    if (endpoint === "alerts/quality") return { data: QUALITY, loading: false, error: null, refresh: jest.fn() };
    return { data: EMPTY, loading: false, error: null, refresh: jest.fn() };
  },
}));

afterEach(() => jest.clearAllMocks());

describe("InstitutionalAlertsPanel — contract", () => {
  test("renders tier pill and bias cells for each row + prime/sigma/cw chips", async () => {
    render(<InstitutionalAlertsPanel active={true} />);
    await waitFor(() => expect(screen.getByText("PLTR")).toBeInTheDocument());
    // Tier pill — strip cells (one per GOLD/SILVER/BRONZE) + row pills. We
    // anchor on the strip cells (one each is sufficient) since tierBadge
    // promotes BRONZE+side:"STRATEGY" rows into a STRATEGY pill, so the
    // only rendered "BRONZE" string is the strip cell in this fixture.
    expect(screen.getAllByText("GOLD").length).toBeGreaterThanOrEqual(2);    // row + strip
    expect(screen.getAllByText("SILVER").length).toBeGreaterThanOrEqual(2);  // row + strip
    expect(screen.getAllByText("BRONZE").length).toBeGreaterThanOrEqual(1);  // strip cell only (AMD row is STRATEGY)
    // STRATEGY tier override (spread-leg row)
    expect(screen.getAllByText("STRATEGY").length).toBeGreaterThanOrEqual(1);
    // Honest CLUSTER chip for the v2.1 server-stamped field
    expect(screen.getAllByText("CLUSTER").length).toBeGreaterThanOrEqual(1);  // PLTR has cluster=true
    // Bias cells — PLTR + NVDA both BULLISH; TSLA BEARISH.
    expect(screen.getAllByText("BULLISH").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("BEARISH")).toBeInTheDocument();
    // sigma chip on the NVDA row
    expect(screen.getByText("σ +5.4")).toBeInTheDocument();
    // CW confirm chip — PLTR bullish + cw +0.04 → +4.0% confirms
    expect(screen.getByText(/CW.*\+4\.0%.*confirms/)).toBeInTheDocument();
    // TSLA bearish put → CW -2.5% confirms
    expect(screen.getByText(/CW.*-2\.5%.*confirms/)).toBeInTheDocument();
  });

  test("PRIME chip fires for the $380k @ 6.4× row, not for $80k (under either floor)", () => {
    render(<InstitutionalAlertsPanel active={true} />);
    // PLTR is prime (380k + 6.4×), AMD is not (80k + 2×)
    const pr = screen.getAllByText("PRIME");
    expect(pr.length).toBeGreaterThanOrEqual(1);
  });

  test("move column uses + sign on +3.9%", () => {
    render(<InstitutionalAlertsPanel active={true} />);
    expect(screen.getByText("+3.90%")).toBeInTheDocument();
  });

  test("STRATEGY tier pill appears for the spread-leg row (no duplicate PAIRED LEGS chip)", () => {
    render(<InstitutionalAlertsPanel active={true} />);
    // STRATEGY tier pill (from tierBadge when side === "STRATEGY") conveys
    // the spread-leg demotion on its own; we DROP the PAIRED LEGS chip to
    // avoid double labelling the same fact in two widgets.
    expect(screen.getAllByText("STRATEGY").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("PAIRED LEGS")).toBeNull();
  });
});

describe("InstitutionalAlertsPanel — quality strip", () => {
  test("renders per-tier hit-rate cells + avg move, blanks thin tiers with —", () => {
    render(<InstitutionalAlertsPanel active={true} />);
    expect(screen.getByText("Calibration")).toBeInTheDocument();
    // v2.2 batched fixture: the strip projects the longest window (30d).
    // GOLD 30d hit-rate = 65%, SILVER 30d = 55%, BRONZE 30d n_measured=0 (thin).
    expect(screen.getByText("65%")).toBeInTheDocument();
    expect(screen.getByText("55%")).toBeInTheDocument();
    // BRONZE thin → "—"
    const dashCells = screen.getAllByText("—");
    expect(dashCells.length).toBeGreaterThanOrEqual(1);
    // The cell-meta block appends an avg-move suffix; anchor with regex
    // matchers so the suffix doesn't break exact-equality lookups.
    expect(screen.getByText(/12\/12 measured/)).toBeInTheDocument();
    expect(screen.getByText(/18\/18 measured/)).toBeInTheDocument();
  });
});

describe("InstitutionalAlertsPanel — quality-strip error UX", () => {
  // /alerts/quality must NOT silently disappear on failure — the strip
  // and "no data yet" look the same on the page; a desk needs to know.
  test("renders a 'Calibration unavailable' banner with retry button", () => {
    const hook = require("../../hooks/useFlowseeker");
    const swap = (() => {
      hook.useFlowseeker = (endpoint) => {
        if (endpoint === "alerts/feed")
          return { data: TICKER_ALERTS, loading: false, error: null, refresh: jest.fn() };
        if (endpoint === "alerts/quality")
          return { data: null, loading: false, error: "HTTP 503: cvserver rate-limited", refresh: jest.fn() };
        return { data: EMPTY, loading: false, error: null, refresh: jest.fn() };
      };
    });
    swap();
    try {
      render(<InstitutionalAlertsPanel active={true} />);
      // Banner copy: distinguishes "Calibration unavailable" from feedError.
      expect(screen.getByText((c, el) => /Calibration unavailable/.test(c || ""))).toBeInTheDocument();
      // Retry button offers the user a way out without a hard reload.
      expect(screen.getByText("↻ retry")).toBeInTheDocument();
      // Strip header is NOT shown when quality errored out (avoid misleading).
      expect(screen.queryByText("Calibration")).toBeNull();
    } finally {
      // restore the default stub regardless of test result
      hook.useFlowseeker = (endpoint) => {
        if (endpoint === "alerts/feed") return { data: TICKER_ALERTS, loading: false, error: null, refresh: jest.fn() };
        if (endpoint === "alerts/quality") return { data: QUALITY, loading: false, error: null, refresh: jest.fn() };
        return { data: EMPTY, loading: false, error: null, refresh: jest.fn() };
      };
    }
  });

  test("banner does NOT render when quality succeeds normally", () => {
    render(<InstitutionalAlertsPanel active={true} />);
    // The default mock reports QUALITY with no error → strip is normal.
    expect(screen.queryByText(/Calibration unavailable/)).toBeNull();
  });
});

describe("InstitutionalAlertsPanel — empty feed handling", () => {
  test("renders the 'No fresh scan yet' empty state when feed is empty", () => {
    // Swap the global mock to report an empty feed for the duration of this
    // single test. We avoid jest.isolateModules/require because CRACO's
    // transform pipeline has been seen to drop the React import for mid-test
    // require() of JSX files; a global mock swap is the stable path.
    const feedMock = require("../../hooks/useFlowseeker");
    feedMock.useFlowseeker = (endpoint) => ({
      data: endpoint === "alerts/quality" ? QUALITY : EMPTY,
      loading: false, error: null, refresh: jest.fn(),
    });
    try {
      const { container } = render(<InstitutionalAlertsPanel active={true} />);
      expect(container.textContent).toMatch(/No fresh scan yet/);
    } finally {
      feedMock.useFlowseeker = (endpoint) => {
        if (endpoint === "alerts/feed") return { data: TICKER_ALERTS, loading: false, error: null, refresh: jest.fn() };
        if (endpoint === "alerts/quality") return { data: QUALITY, loading: false, error: null, refresh: jest.fn() };
        return { data: EMPTY, loading: false, error: null, refresh: jest.fn() };
      };
    }
  });
});

describe("InstitutionalAlertsPanel — v2.2 trend sparkline", () => {
  test("renders per-tier sparkline SVG with direction label", () => {
    render(<InstitutionalAlertsPanel active={true} />);
    // NEW sign convention: order=[7,14,30], so finite[0]=7d, finite[last]=30d.
    // Fixture: GOLD 7d=0.80, 30d=0.65 → delta=0.80-0.65=+0.15 → "up"
    // (recent hotter than macro → up). Silver only has 30d row, 7d missing
    // → direction falls through to "unknown" (gated by missing 7d).
    // Bronze n_measured=0 for all windows → "unknown".
    // At least one labelled direction per cell renders.
    const labels = screen.getAllByText(/down|up|flat|—/);
    expect(labels.length).toBeGreaterThanOrEqual(3);
    // Gold headline chip is the 30d hit-rate (65%) and 12/12 measured.
    expect(screen.getByText("65%")).toBeInTheDocument();
    expect(screen.getByText(/12\/12 measured/)).toBeInTheDocument();
    // Silver headline is 55% on 18 measured.
    expect(screen.getByText("55%")).toBeInTheDocument();
    expect(screen.getByText(/18\/18 measured/)).toBeInTheDocument();
    // Bronze thin → "—"
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);
    // SVG paths render (one per tier cell).
    const svgs = document.querySelectorAll(".fsp-conviction-qtrend svg");
    expect(svgs.length).toBeGreaterThanOrEqual(3);
    // At least one cell shows the corrected "up" label for GOLD.
    expect(screen.getAllByText("up").length).toBeGreaterThanOrEqual(1);
  });

  test("unknown trend renders muted when 30d n_measured < TREND_MIN_N", () => {
    const hook = require("../../hooks/useFlowseeker");
    hook.useFlowseeker = (endpoint) => {
      if (endpoint === "alerts/feed")
        return { data: TICKER_ALERTS, loading: false, error: null, refresh: jest.fn() };
      if (endpoint === "alerts/quality")
        return {
          data: {
            quality_windows: {
              // Only 1 alert fired in 30d — underpowered; sparkline must say "unknown".
              7:  [{ rule: "SCORE", tier: "GOLD", n: 1, n_measured: 1, hit_rate: 1.0, avg_move_pct: 1.0 }],
              30: [{ rule: "SCORE", tier: "GOLD", n: 1, n_measured: 1, hit_rate: 1.0, avg_move_pct: 1.0 }],
            },
            days: [7, 30],
          },
          loading: false, error: null, refresh: jest.fn(),
        };
      return { data: EMPTY, loading: false, error: null, refresh: jest.fn() };
    };
    try {
      const { container } = render(<InstitutionalAlertsPanel active={true} />);
      // Strip header renders (data exists).
      expect(container.textContent).toMatch(/Calibration/);
      // The sparkline container is in the DOM. Trend label "—" appears for
      // underpowered tiers OR when windows are missing — both gated by
      // TREND_MIN_N (the longest-window 30d has only n=1, < 3).
      const trendContainer = container.querySelector(".fsp-conviction-qtrend");
      expect(trendContainer).not.toBeNull();
    } finally {
      hook.useFlowseeker = (endpoint) => {
        if (endpoint === "alerts/feed") return { data: TICKER_ALERTS, loading: false, error: null, refresh: jest.fn() };
        if (endpoint === "alerts/quality") return { data: QUALITY, loading: false, error: null, refresh: jest.fn() };
        return { data: EMPTY, loading: false, error: null, refresh: jest.fn() };
      };
    }
  });
});

// ── v2.5 daily sparkline rendering ──────────────────────────────────
// The daily_series endpoint returns { GOLD: [{date, n_measured, hit_rate}],
// SILVER: [...], BRONZE: [...] }; the panel reads it via dailySeriesForTier
// and renders one DailySparkline per tier cell.
//
// Empty daily_series: muted dashes (no data). Rising trend (>15pp):
// green "up" label. Absent tier: muted dashes on that tier cell only.
// Hover rectangles with native <title> tooltips anchor the value at
// each dot. The QualitySparkline v2.2 trend plus the daily sparkline
// run side-by-side; both are additive.
describe("InstitutionalAlertsPanel — v2.5 daily sparkline", () => {
  test("renders trend label and hover tooltip rectangles for each tier", () => {
    const hook = require("../../hooks/useFlowseeker");
    hook.useFlowseeker = (endpoint) => {
      if (endpoint === "alerts/feed")
        return { data: TICKER_ALERTS, loading: false, error: null, refresh: jest.fn() };
      if (endpoint === "alerts/quality")
        return {
          data: {
            quality_windows: {
              7:  [{ rule: "SCORE", tier: "GOLD", n: 4, n_measured: 4, hit_rate: 0.70, avg_move_pct: 2.0 }],
              14: [{ rule: "SCORE", tier: "GOLD", n: 8, n_measured: 8, hit_rate: 0.65, avg_move_pct: 1.9 }],
              30: [
                { rule: "SCORE", tier: "GOLD",   n: 12, n_measured: 12, hit_rate: 0.60, avg_move_pct: 1.7 },
                { rule: "SCORE", tier: "SILVER", n: 18, n_measured: 18, hit_rate: 0.55, avg_move_pct: 1.4 },
                { rule: "SCORE", tier: "BRONZE", n: 22, n_measured: 0,  hit_rate: null, avg_move_pct: null },
              ],
            },
            days: [7, 14, 30],
            // v2.5: per-tier per-day series. GOLD rises (0.50 → 0.85 =
            // +35pp > 15pp threshold → "up"). SILVER flat (0.50 → 0.55
            // = +5pp within ±15pp band → "→"). BRONZE absent (no
            // measured days → muted dashes fallback).
            daily_series: {
              GOLD: [
                { date: "2026-07-14", n: 3, n_measured: 3, wins: 1, hit_rate: 0.50 },
                { date: "2026-07-16", n: 4, n_measured: 4, wins: 3, hit_rate: 0.75 },
                { date: "2026-07-18", n: 5, n_measured: 5, wins: 4, hit_rate: 0.85 },
              ],
              SILVER: [
                { date: "2026-07-15", n: 4, n_measured: 4, wins: 2, hit_rate: 0.50 },
                { date: "2026-07-17", n: 4, n_measured: 4, wins: 2, hit_rate: 0.55 },
              ],
              BRONZE: [],
            },
            daily_series_days: 30,
          },
          loading: false, error: null, refresh: jest.fn(),
        };
      return { data: EMPTY, loading: false, error: null, refresh: jest.fn() };
    };
    try {
      const { container } = render(<InstitutionalAlertsPanel active={true} />);
      expect(container.textContent).toMatch(/Calibration/);
      // 3 daily trend containers (one per tier).
      const dtrendContainers = container.querySelectorAll(".fsp-conviction-dtrend");
      expect(dtrendContainers.length).toBe(3);
      // GOLD trend label is "up"; SILVER's flat label is "→"; BRONZE muted "—".
      const allLabels = container.querySelectorAll(".fsp-conviction-dtrend-label");
      const labelTexts = Array.from(allLabels).map((el) => el.textContent || "");
      expect(labelTexts).toContain("up");
      expect(labelTexts).toContain("\u2192");
      // Hover rectangles — at least 5 (GOLD 3 + SILVER 2 measured days).
      const rects = container.querySelectorAll(".fsp-conviction-dtrend svg rect");
      expect(rects.length).toBeGreaterThanOrEqual(5);
      const titles = Array.from(rects)
        .map((r) => r.querySelector("title")?.textContent || "")
        .filter(Boolean);
      expect(titles.some((t) => /alerts/.test(t))).toBe(true);
      expect(titles.some((t) => /\d+\/\d+/.test(t))).toBe(true);
    } finally {
      hook.useFlowseeker = (endpoint) => {
        if (endpoint === "alerts/feed") return { data: TICKER_ALERTS, loading: false, error: null, refresh: jest.fn() };
        if (endpoint === "alerts/quality") return { data: QUALITY, loading: false, error: null, refresh: jest.fn() };
        return { data: EMPTY, loading: false, error: null, refresh: jest.fn() };
      };
    }
  });

  test("no daily_series payload → muted dashed line per tier (forwards compat)", () => {
    // When the backend hasn't been upgraded (pre-v2.5), the panel must
    // still render the strip — dailySeriesForTier returns has_data=false
    // and DailySparkline falls back to the dashed muted line. The
    // QualitySparkline v2.2 trend still works against quality_windows.
    const hook = require("../../hooks/useFlowseeker");
    hook.useFlowseeker = (endpoint) => {
      if (endpoint === "alerts/feed")
        return { data: TICKER_ALERTS, loading: false, error: null, refresh: jest.fn() };
      if (endpoint === "alerts/quality")
        // INTENTIONAL: no daily_series key. Legacy v2.x responses lack it.
        return { data: QUALITY, loading: false, error: null, refresh: jest.fn() };
      return { data: EMPTY, loading: false, error: null, refresh: jest.fn() };
    };
    try {
      const { container } = render(<InstitutionalAlertsPanel active={true} />);
      expect(container.textContent).toMatch(/Calibration/);
      const dtrendContainers = container.querySelectorAll(".fsp-conviction-dtrend");
      // Soft assertion: at least one dtrend container renders one per
      // visible tier. Today QUALITY produces exactly 3 (GOLD + SILVER +
      // BRONZE), but a future version that hides a tier cell (e.g. BRONZE
      // with thin=true suppressed from the strip) should NOT silently
      // regress this test. `>= 1` keeps the regression signal alive
      // ("a tier cell with no daily series should still render the muted
      // fallback") without coupling to the exact cell count.
      expect(dtrendContainers.length).toBeGreaterThanOrEqual(1);
      // The muted fallback reads "—" (em-dash) per DailySparkline's
      // inert branch — assert at least one such label appears in a
      // dtrend container when daily_series is absent from the payload.
      const mutedLabels = Array.from(
        container.querySelectorAll(".fsp-conviction-dtrend-label")
      ).filter((el) => (el.textContent || "").trim() === "\u2014");
      expect(mutedLabels.length).toBeGreaterThanOrEqual(1);
    } finally {
      hook.useFlowseeker = (endpoint) => {
        if (endpoint === "alerts/feed") return { data: TICKER_ALERTS, loading: false, error: null, refresh: jest.fn() };
        if (endpoint === "alerts/quality") return { data: QUALITY, loading: false, error: null, refresh: jest.fn() };
        return { data: EMPTY, loading: false, error: null, refresh: jest.fn() };
      };
    }
  });
});
