/**
 * usePortfolio — fetches and caches a portfolio summary.
 *
 * Parameters:
 *   name   - Portfolio name (path parameter on the backend route).
 *   opts   - Options object.
 *   opts.spot  - Current spot price for summary calc (default 0).
 *   opts.iv    - Implied vol for summary calc (default 0.15).
 *   opts.enabled - Whether to auto-fetch (default true).
 * Returns: TanStack query result.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { BACKEND_URL } from "../config/api";

const API = `${BACKEND_URL}/api`;

/**
 * Shared query key factory - single source of truth for portfolio cache keys.
 */
export const portfolioKeys = {
  /** All portfolio queries (invalidates every portfolio cache) */
  all: ["portfolio"],
  /** A single portfolio by name */
  individual: (name) => [...portfolioKeys.all, name],
  /** Scenario analysis for a portfolio */
  scenario: (name) => [...portfolioKeys.all, name, "scenario"],
};

/**
 * usePortfolio - fetches and caches a portfolio summary.
 */
export function usePortfolio(name, opts = {}) {
  const { spot = 0, iv = 0.15, enabled = true } = opts;

  return useQuery({
    queryKey: portfolioKeys.individual(name),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (spot > 0) params.set("spot", String(spot));
      if (iv > 0 && iv !== 0.15) params.set("iv", String(iv));
      const qs = params.toString();
      const url = qs
        ? `${API}/portfolio/${encodeURIComponent(name)}?${qs}`
        : `${API}/portfolio/${encodeURIComponent(name)}`;
      const res = await fetch(url);
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 120)}` : ""}`);
      }
      return res.json();
    },
    enabled,
    staleTime: 1000 * 60 * 5, // 5 min
  });
}

/**
 * usePortfolioScenario - fetches scenario analysis for a portfolio.
 */
export function usePortfolioScenario(name, opts = {}) {
  const { spot = 0, iv = 0.15, enabled = true } = opts;

  return useQuery({
    queryKey: portfolioKeys.scenario(name),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (spot > 0) params.set("spot", String(spot));
      if (iv > 0 && iv !== 0.15) params.set("iv", String(iv));
      const qs = params.toString();
      const url = qs
        ? `${API}/portfolio/${encodeURIComponent(name)}/scenario?${qs}`
        : `${API}/portfolio/${encodeURIComponent(name)}/scenario`;
      const res = await fetch(url);
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 120)}` : ""}`);
      }
      return res.json();
    },
    enabled,
    staleTime: 1000 * 60 * 5, // 5 min
  });
}

/**
 * useAddPosition - mutation to add a position to a portfolio.
 */
export function useAddPosition(name) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (position) => {
      const res = await fetch(`${API}/portfolio/${encodeURIComponent(name)}/position`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(position),
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 120)}` : ""}`);
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portfolioKeys.individual(name) });
    },
  });
}

/**
 * useRemovePosition - mutation to remove a position from a portfolio.
 */
export function useRemovePosition(name) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (index) => {
      const res = await fetch(`${API}/portfolio/${encodeURIComponent(name)}/position/${index}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 120)}` : ""}`);
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portfolioKeys.individual(name) });
    },
  });
}
