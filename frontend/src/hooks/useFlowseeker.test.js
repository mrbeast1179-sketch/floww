/**
 * @jest-environment jsdom
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { useFlowseeker } from "./useFlowseeker";

function Harness({ endpoint, params }) {
  const { data, loading, error } = useFlowseeker(endpoint, params);
  return <div>{loading ? "loading" : error ? `err:${error}` : `count:${data?.count}`}</div>;
}

test("useFlowseeker fetches /api/flowseeker/<endpoint> and returns data", async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ ticker: "SPY", count: 2, prints: [{}, {}] }),
  });
  render(<Harness endpoint="live" params={{ ticker: "SPY", refreshMs: 0 }} />);
  await waitFor(() => expect(screen.getByText("count:2")).toBeInTheDocument());
  const calledUrl = global.fetch.mock.calls[0][0];
  expect(calledUrl).toContain("/flowseeker/live");
  expect(calledUrl).toContain("ticker=SPY");
});
