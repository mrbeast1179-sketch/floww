/**
 * queryClient.js — singleton TanStack QueryClient for floww frontend.
 *
 * Exported as a module-level singleton so the same instance is shared
 * between the QueryClientProvider (wired in index.js) and any hook that
 * calls useQueryClient() for invalidation.
 */
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 min — data considered fresh
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 1,
    },
  },
});
