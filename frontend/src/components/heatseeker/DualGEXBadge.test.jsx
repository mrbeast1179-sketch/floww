/**
 * @jest-environment jsdom
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import DualGEXBadge from "./DualGEXBadge";

function mockFetchOnce(payload) {
  global.fetch = jest.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(payload) })
  );
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("DualGEXBadge", () => {
  test("renders badge tone and ratio on a full payload", async () => {
    mockFetchOnce({
      activity_badge: "live",
      activity_ratio: 1.42,
      positive_gex_oi: 12_000_000,
      positive_gex_volume: 17_000_000,
    });
    render(<DualGEXBadge ticker="SPY" />);
    expect(await screen.findByText("LIVE")).toBeInTheDocument();
    expect(screen.getByText("1.42×")).toBeInTheDocument();
  });

  test("degrades without crashing when activity_badge is missing", async () => {
    // Backend degrade path can return a partial body; the badge must not
    // throw on activity_badge.toUpperCase().
    mockFetchOnce({ activity_ratio: 0 });
    render(<DualGEXBadge ticker="SPY" />);
    // Must reach the data-loaded render (not the loading placeholder) and
    // fall back to the QUIET tone instead of throwing.
    expect(await screen.findByText("QUIET")).toBeInTheDocument();
    expect(screen.getByText("Activity Ratio")).toBeInTheDocument();
  });
});
