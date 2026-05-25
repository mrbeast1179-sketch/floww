import React from "react";
import { render, screen } from "@testing-library/react";
import MLPredictionsPanel from "./MLPredictionsPanel";

describe("MLPredictionsPanel", () => {
  test("renders loading state", () => {
    render(<MLPredictionsPanel loading={true} />);
    expect(screen.getByTestId("ml-predictions")).toBeInTheDocument();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  test("renders error state", () => {
    render(<MLPredictionsPanel error="HTTP 500" />);
    expect(screen.getByTestId("ml-predictions")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
  });

  test("renders empty dash when no predictions", () => {
    render(<MLPredictionsPanel predictions={[]} />);
    expect(screen.getByTestId("ml-predictions")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  test("renders prediction cards with BULLISH/BEARISH labels", () => {
    const predictions = [
      { ticker: "SPY", prediction: 1, prediction_label: "bullish", confidence: 0.72, probabilities: { bearish: 0.28, bullish: 0.72 }, data_age_sec: 30 },
      { ticker: "QQQ", prediction: 0, prediction_label: "bearish", confidence: 0.65, probabilities: { bearish: 0.65, bullish: 0.35 }, data_age_sec: 45 },
    ];
    render(<MLPredictionsPanel predictions={predictions} />);
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("QQQ")).toBeInTheDocument();
    // Use function matcher since arrow character may split text nodes
    expect(screen.getByText((content, el) => el?.textContent === "↑ BULLISH")).toBeInTheDocument();
    expect(screen.getByText((content, el) => el?.textContent === "↓ BEARISH")).toBeInTheDocument();
  });

  test("renders bullish/bearish count summary", () => {
    const predictions = [
      { ticker: "SPY", prediction: 1, prediction_label: "bullish", confidence: 0.6, probabilities: { bearish: 0.4, bullish: 0.6 }, data_age_sec: 10 },
      { ticker: "QQQ", prediction: 1, prediction_label: "bullish", confidence: 0.7, probabilities: { bearish: 0.3, bullish: 0.7 }, data_age_sec: 20 },
      { ticker: "IWM", prediction: 0, prediction_label: "bearish", confidence: 0.55, probabilities: { bearish: 0.55, bullish: 0.45 }, data_age_sec: 30 },
    ];
    render(<MLPredictionsPanel predictions={predictions} />);
    expect(screen.getByText("2↑")).toBeInTheDocument();
    expect(screen.getByText("1↓")).toBeInTheDocument();
  });
});
