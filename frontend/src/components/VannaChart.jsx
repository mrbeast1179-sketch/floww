/**
 * VannaChart.jsx
 *
 * Displays vanna exposure by strike price.
 * Vanna = d(Delta)/d(Vol) — how delta changes with implied volatility.
 *
 * Backend /api/vanna-exposure/{ticker} returns:
 *   { ticker, spot, strikes: [...], vanna: [...], asof }
 */
import React, { useMemo, memo } from "react";
import Plot from "react-plotly.js";
import { useMarketData } from "../hooks/useMarketData";
import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
import { ErrorState } from "./RetryButton";

var VannaChart = memo(function VannaChart({ ticker = "SPY", spot: spotPrice }) {
  var _useMarketData = useMarketData(
    "vanna-exposure/" + ticker,
    { refreshMs: 60000, query: { expiries: 4 } }
  );
  var data = _useMarketData.data;
  var loading = _useMarketData.loading;
  var error = _useMarketData.error;
  var showBadge = _useMarketData.showBadge;
  var refresh = _useMarketData.refresh;

  var useWebGL = useMemo(function () { return isWebGLAvailable(); }, []);

  var chartData = useMemo(function () {
    if (!data || !data.strikes || !data.vanna) return null;

    var strikes = data.strikes;
    var vannaValues = data.vanna;

    // Handle mismatched array lengths safely
    var len = Math.min(strikes.length, vannaValues.length);
    if (len === 0) return null;

    // Filter out entries with null/undefined vanna values
    var filteredStrikes = [];
    var filteredVanna = [];
    var i;
    for (i = 0; i < len; i++) {
      var v = vannaValues[i];
      if (v != null && Number.isFinite(v)) {
        filteredStrikes.push(strikes[i]);
        filteredVanna.push(v);
      }
    }

    if (filteredStrikes.length === 0) return null;

    // Decimate if too many points
    var plotStrikes = filteredStrikes;
    var plotVanna = filteredVanna;
    if (filteredStrikes.length > 200) {
      var points = filteredStrikes.map(function (s, idx) {
        return { x: s, y: filteredVanna[idx] };
      });
      var decimated = autoDecimate(points, 200);
      plotStrikes = decimated.map(function (d) { return d.x; });
      plotVanna = decimated.map(function (d) { return d.y; });
    }

    var colors = plotVanna.map(function (v) { return v >= 0 ? "#5eead4" : "#f87171"; });

    var traces = [
      {
        x: plotStrikes,
        y: plotVanna,
        type: "bar",
        marker: { color: colors, opacity: 0.8 },
        name: "Vanna Exposure",
        hovertemplate: "Strike: $%{x}<br>Vanna: %{y:,.0f}<extra></extra>",
      },
    ];

    // Spot price line
    if (spotPrice != null && Number.isFinite(spotPrice)) {
      traces.push({
        x: [spotPrice, spotPrice],
        y: [
          Math.min.apply(null, plotVanna) * 1.1,
          Math.max.apply(null, plotVanna) * 1.1,
        ],
        type: "scatter",
        mode: "lines",
        line: { color: "#fbbf24", width: 2, dash: "dash" },
        name: "Spot",
        hovertemplate: "Spot: $%{x}<extra></extra>",
      });
    }

    // Zero line
    traces.push({
      x: [Math.min.apply(null, plotStrikes), Math.max.apply(null, plotStrikes)],
      y: [0, 0],
      type: "scatter",
      mode: "lines",
      line: { color: "rgba(100,116,139,0.4)", width: 1 },
      name: "Zero",
      showlegend: false,
      hoverinfo: "skip",
    });

    return traces;
  }, [data, spotPrice]);

  var layout = useMemo(
    function () {
      return {
        title: {
          text: "Vanna Exposure — " + ticker,
          font: { size: 13, color: "#94a3b8" },
        },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#64748b", size: 10 },
        margin: { t: 35, b: 40, l: 55, r: 15 },
        xaxis: {
          title: "Strike",
          tickformat: "$,.0f",
          gridcolor: "rgba(100,116,139,0.15)",
          zerolinecolor: "rgba(100,116,139,0.3)",
        },
        yaxis: {
          title: "Vanna",
          tickformat: ",.0f",
          gridcolor: "rgba(100,116,139,0.15)",
          zerolinecolor: "rgba(100,116,139,0.3)",
        },
        showlegend: true,
        legend: { x: 0, y: 1.1, orientation: "h", font: { size: 9 } },
        hovermode: "x unified",
        bargap: 0.05,
      };
    },
    [ticker]
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
    return React.createElement(ErrorState, { error: error, onRetry: refresh, title: "Vanna data unavailable" });
  }

  if (loading && !data) {
    return React.createElement(
      "div",
      { className: "panel p-4 flex items-center justify-center", style: { minHeight: 250 } },
      React.createElement("div", { className: "text-[11px] text-slate-500 animate-pulse" }, "Loading vanna exposure\u2026")
    );
  }

  if (!chartData) {
    return React.createElement(
      "div",
      { className: "panel p-4 flex items-center justify-center", style: { minHeight: 250 } },
      React.createElement("div", { className: "text-[11px] text-slate-500" }, "No vanna data available")
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
      "Vanna = d(Delta)/d(Vol) \u00b7 Positive = call-heavy \u00b7 Negative = put-heavy"
    )
  );
});

export default VannaChart;
