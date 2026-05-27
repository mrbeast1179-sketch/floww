/**
 * CharmChart.jsx
 *
 * Displays charm (delta decay) exposure.
 *
 * Backend /api/analytics/charm-integral/{ticker} returns:
 *   { spot, expiry, minutes_remaining, days_remaining,
 *     total_charm_to_close, direction,
 *     buckets: [{minutes_remaining, instantaneous_charm, cumulative_charm}] }
 *
 * This chart renders cumulative charm vs time-to-expiry (not vs strike).
 */
import React, { useMemo, memo } from "react";
import Plot from "react-plotly.js";
import { useMarketData } from "../hooks/useMarketData";
import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
import { ErrorState } from "./RetryButton";

var CharmChart = memo(function CharmChart({ ticker = "SPY", spot: spotPrice }) {
  var _useMarketData = useMarketData(
    "analytics/charm-integral/" + ticker,
    { refreshMs: 60000, query: { expiries: 4 } }
  );
  var data = _useMarketData.data;
  var loading = _useMarketData.loading;
  var error = _useMarketData.error;
  var showBadge = _useMarketData.showBadge;
  var refresh = _useMarketData.refresh;

  var useWebGL = useMemo(function () { return isWebGLAvailable(); }, []);

  var chartData = useMemo(function () {
    if (!data) return null;

    // Parse the backend response: buckets array with cumulative_charm
    var buckets = data.buckets;
    if (!Array.isArray(buckets) || buckets.length === 0) return null;

    var minutes = [];
    var cumulative = [];
    var i;

    for (i = 0; i < buckets.length; i++) {
      var b = buckets[i];
      var mins = b.minutes_remaining != null ? b.minutes_remaining : 0;
      var cum = b.cumulative_charm != null ? b.cumulative_charm : 0;
      if (mins == null) mins = 0;
      if (cum == null) cum = 0;
      minutes.push(mins);
      cumulative.push(Number.isFinite(cum) ? cum : 0);
    }

    if (minutes.length === 0) return null;

    var colors = cumulative.map(function (v) { return v >= 0 ? "#a78bfa" : "#fb923c"; });

    var traces = [
      {
        x: minutes,
        y: cumulative,
        type: "scatter",
        mode: "lines+markers",
        line: { color: "#a78bfa", width: 2, shape: "spline" },
        marker: { size: 4, color: colors },
        name: "Cumulative Charm",
        hovertemplate: "T-%{x} min<br>Charm: %{y:,.0f}<extra></extra>",
      },
    ];

    // Zero line
    traces.push({
      x: [Math.min.apply(null, minutes), Math.max.apply(null, minutes)],
      y: [0, 0],
      type: "scatter",
      mode: "lines",
      line: { color: "rgba(100,116,139,0.4)", width: 1 },
      name: "Zero",
      showlegend: false,
      hoverinfo: "skip",
    });

    return traces;
  }, [data]);

  var layout = useMemo(
    function () {
      var titleText = "Charm (Delta Decay) — " + ticker;
      if (data && data.direction) {
        titleText += " · " + data.direction.toUpperCase();
      }
      return {
        title: {
          text: titleText,
          font: { size: 13, color: "#94a3b8" },
        },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#64748b", size: 10 },
        margin: { t: 35, b: 40, l: 55, r: 15 },
        xaxis: {
          title: "Minutes to Expiry",
          autorange: "reversed",
          gridcolor: "rgba(100,116,139,0.15)",
          zerolinecolor: "rgba(100,116,139,0.3)",
        },
        yaxis: {
          title: "Cumulative Charm",
          tickformat: ",.0f",
          gridcolor: "rgba(100,116,139,0.15)",
          zerolinecolor: "rgba(100,116,139,0.3)",
        },
        showlegend: true,
        legend: { x: 0, y: 1.1, orientation: "h", font: { size: 9 } },
        hovermode: "x unified",
        annotations: data && data.total_charm_to_close != null ? [
          {
            x: 0.98,
            y: 0.95,
            xref: "paper",
            yref: "paper",
            text: "Total: " + Number(data.total_charm_to_close).toLocaleString(),
            showarrow: false,
            font: { size: 10, color: "#94a3b8" },
            align: "right",
          },
        ] : [],
      };
    },
    [ticker, data]
  );

  var config = useMemo(
    function () {
      return {
        responsive: true,
        displayModeBar: false,
        plotGlPixelRatio: useWebGL ? 2 : 1,
      };
    },
    [useWebGL]
  );

  if (error && !data) {
    return React.createElement(ErrorState, { error: error, onRetry: refresh, title: "Charm data unavailable" });
  }

  if (loading && !data) {
    return React.createElement(
      "div",
      { className: "panel p-4 flex items-center justify-center", style: { minHeight: 250 } },
      React.createElement("div", { className: "text-[11px] text-slate-500 animate-pulse" }, "Loading charm exposure…")
    );
  }

  if (!chartData) {
    return React.createElement(
      "div",
      { className: "panel p-4 flex items-center justify-center", style: { minHeight: 250 } },
      React.createElement("div", { className: "text-[11px] text-slate-500" }, "No charm data available")
    );
  }

  return React.createElement(
    "div",
    { className: "panel p-3 relative" },
    showBadge ? React.createElement(
      "div",
      { className: "absolute top-2 right-2 z-10" },
      React.createElement(
        "span",
        { className: "text-[8px] uppercase tracking-widest font-bold px-1.5 py-0.5 rounded",
          style: { background: "rgba(251,191,36,0.15)", color: "#fbbf24" } },
        "Stale"
      )
    ) : null,
    React.createElement(Plot, {
      data: chartData,
      layout: layout,
      config: config,
      style: { width: "100%", height: 280 },
      useResizeHandler: true,
    }),
    React.createElement(
      "div",
      { className: "text-[9px] text-slate-600 text-center mt-1" },
      "Charm = d(Delta)/d(Time) \u00b7 Positive = long gamma \u00b7 Negative = short gamma"
    )
  );
});

export default CharmChart;
