/**
 * usePortfolio.js — TanStack Query hook for /api/portfolio/{name}.
 *
 * Replaces the raw fetch/useState pattern with declarative server-state
 * management: caching, background refetch, loading/error states, and
 * automatic garbage collection.
 *
 * Backend routes (backend/routes/portfolio.py):
 *   GET    /api/portfolio/{name}            — portfolio summary
 *   GET    /api/portfolio/{name}/scenario  — scenario analysis
 *   POST   /api/portfolio/{name}/position  — add position (mutation)
 *   DELETE /api/portfolio/{name}/position/{index} — remove position (mutation)
 *
 * The hook exports query keys + mutation functions so consuming components
 * can stay declarative while the library handles the async lifecycle.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { BACKEND_URL } from "../config/api";

const API = `${BACKEND_URL}/api`;

/**
 * Shared query key factory — single source of truth for portfolio cache keys.
 * Callers pass the portfolio name; the hook and any invalidation logic use
 * this factory so keys never drift out of sync.
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
 * usePortfolio — fetches and caches a portfolio summary.
 *
 * @param {string} name   Portfolio name (path parameter on the backend route).
 * @param {object} [opts] Options.
 * @param {number} [opts.spot=0]   Current spot price for summary calc.
 * @param {number} [opts.iv=0.15] Implied vol for summary calc.
 * @param {boolean} [opts.enabled=true] Whether to auto-fetch.
 * @returns {QueryObserverResult} TanStack query result.
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
 * usePortfolioScenario — fetches scenario analysis for a portfolio.
 *
 * @param {string} name   Portfolio name.
 * @param {object} [opts] Options (spot, iv, enabled).
 * @returns {QueryObserverResult} TanStack query result.
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
    staleTime: 1000 * 60 * 5,
  });
}

/**
 * useAddPosition — mutation to POST a new position to a portfolio.
 * On success, invalidates the portfolio query so the summary refetches.
 *
 * @returns {MutationObserverResult} TanStack mutation result.
 */
export function useAddPosition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ name, position }) => {
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
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: portfolioKeys.individual(variables.name) });
    },
  });
}

/**
 * useRemovePosition — mutation to DELETE a position from a portfolio.
 * On success, invalidates the portfolio query.
 *
 * @returns {MutationObserverResult} TanStack mutation result.
 */
export function useRemovePosition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ name, index }) => {
      const res = await fetch(`${API}/portfolio/${encodeURIComponent(name)}/position/${index}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}${body ? `: ${body.slice(0, 120)}` : ""}`);
      }
      return res.json();
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: portfolioKeys.individual(variables.name) });
    },
  });
}
