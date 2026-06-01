import React from "react";
import { render, screen } from "@testing-library/react";
import ErrorBoundary from "./ErrorBoundary";

// Component that throws on render — used to verify ErrorBoundary isolation
function BrokenChart() {
  throw new Error("Simulated Plotly crash");
}

function WorkingPanel() {
  return <div data-testid="working-panel">Working Panel</div>;
}

describe("ErrorBoundary (T7: chart isolation)", () => {
  test("catches render errors and shows fallback UI", () => {
    render(
      <ErrorBoundary>
        <BrokenChart />
      </ErrorBoundary>
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  test("sibling components outside ErrorBoundary still render", () => {
    render(
      <div>
        <div data-testid="top-panel">
          <WorkingPanel />
        </div>
        <ErrorBoundary>
          <BrokenChart />
        </ErrorBoundary>
        <div data-testid="bottom-panel">
          <WorkingPanel />
        </div>
      </div>
    );
    // Top and bottom panels survive the chart crash
    expect(screen.getByTestId("top-panel")).toBeInTheDocument();
    expect(screen.getByTestId("bottom-panel")).toBeInTheDocument();
    // Error boundary shows fallback for the broken chart
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    // Working panels still render their content
    expect(screen.getAllByText("Working Panel")).toHaveLength(2);
  });
});
