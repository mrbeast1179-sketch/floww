"""
backend/services/dash_ui.py

Dash/Plotly UI for the Confluence Decoder terminal.
Mounts into the existing FastAPI server at /dashboard/.

Tabs:
  1. Heatseeker — GEX heatmap with King Nodes, Air Pockets, Zero Gamma
  2. Flowseeker — Live options flow ticker with color coding
  3. Toxicity — VPIN, Quote Imbalance, Market Fragility gauges
  4. Vol Surface — 3D IV surface with SABR/SVI
  5. Trinity — Multi-ticker alignment and node lifecycle
  6. Atlas — Candlestick chart with overlays (King Nodes, ZG, Air Pockets, Anomaly, Trinity)
  7. Replay — Historical replay mode with play/pause/speed controls
  8. Agent Hub — YAML-defined trading agent archetypes
  9. Nexus — Social trading scaffold (leaderboard, comments)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

try:
    import dash
    from dash import dcc, html, Input, Output, State, callback, clientside_callback
    import dash_bootstrap_components as dbc
    HAS_DASH = True
except ImportError:
    try:
        from dash import dcc, html, Input, Output, State, callback, clientside_callback
        HAS_DASH = True
    except ImportError:
        HAS_DASH = False
        logger.warning("Dash not available — UI will not be mounted")

# ── Color constants ──────────────────────────────────────────────────────────
BG_DARK = "#0a0a1a"
BG_CARD = "#1a1a2e"
BG_PLOT = "#16213e"
ACCENT = "#00ff88"
WARN = "#ffaa00"
DANGER = "#ff4444"
TEXT = "#e0e0e0"
TEXT_DIM = "#888888"

# Light theme colors
BG_DARK_LIGHT = "#f5f5f5"
BG_CARD_LIGHT = "#ffffff"
BG_PLOT_LIGHT = "#fafafa"
TEXT_LIGHT = "#333333"
TEXT_DIM_LIGHT = "#666666"


def _empty_figure(title: str = "Waiting for data...", dark: bool = True) -> go.Figure:
    bg = BG_CARD if dark else BG_CARD_LIGHT
    plot = BG_PLOT if dark else BG_PLOT_LIGHT
    dim = TEXT_DIM if dark else TEXT_DIM_LIGHT
    fig = go.Figure()
    fig.add_annotation(
        text=title, xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False, font=dict(size=16, color=dim),
    )
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor=bg, plot_bgcolor=plot,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


def _error_figure(msg: str, dark: bool = True) -> go.Figure:
    bg = BG_CARD if dark else BG_CARD_LIGHT
    plot = BG_PLOT if dark else BG_PLOT_LIGHT
    fig = go.Figure()
    fig.add_annotation(
        text=f"Error: {msg}", xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False, font=dict(size=14, color=DANGER),
    )
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor=bg, plot_bgcolor=plot,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: HEATSEEKER — GEX Heatmap with Overlays
# ═══════════════════════════════════════════════════════════════════════════════

def _build_gex_heatmap(
    spot: float = 0,
    contracts: Optional[List[Dict]] = None,
    gex_surface: Optional[List[List[float]]] = None,
    strikes: Optional[List[float]] = None,
    expiries: Optional[List[float]] = None,
    king_nodes: Optional[List[Dict]] = None,
    air_pockets: Optional[List[Dict]] = None,
    zero_gamma: Optional[float] = None,
    dark: bool = True,
) -> go.Figure:
    """Build GEX heatmap: strikes x time, with overlays."""
    if not contracts and gex_surface is None:
        return _empty_figure("Waiting for GEX data...", dark)

    try:
        if gex_surface is not None and strikes and expiries:
            z = gex_surface
            y_labels = [f"{s:.1f}" for s in strikes]
            x_labels = [f"T={t:.3f}" for t in expiries]
        elif spot > 0 and contracts:
            try:
                from services.gex_aggregator import GexAggregator
                agg = GexAggregator()
                result = agg.compute(spot, contracts)
                strikes = result.get("strikes", [])
                expiries = result.get("expiries", [])
                z = result.get("gex_surface", [])
                if not z or not strikes or not expiries:
                    return _empty_figure("No GEX surface data available", dark)
                y_labels = [f"{s:.1f}" for s in strikes]
                x_labels = [f"T={t:.3f}" for t in expiries]
            except Exception as e:
                logger.error(f"GEX aggregator error: {e}")
                return _error_figure(f"GEX error: {e}", dark)
        else:
            return _empty_figure("Waiting for GEX data...", dark)

        tpl = "plotly_dark" if dark else "plotly_white"
        bg = BG_CARD if dark else BG_CARD_LIGHT
        plot = BG_PLOT if dark else BG_PLOT_LIGHT
        accent = ACCENT if dark else "#00aa55"

        fig = go.Figure()
        fig.add_trace(go.Heatmap(
            z=z, x=x_labels, y=y_labels,
            colorscale=[[0.0, "#d73027"], [0.25, "#fc8d59"], [0.45, "#fee090"],
                        [0.50, "#ffffbf"], [0.55, "#e0f3f8"], [0.75, "#91bfdb"], [1.0, "#4575b4"]],
            zmid=0, colorbar=dict(title="GEX ($)", x=1.02, thickness=15),
            hovertemplate="Strike: %{y}<br>TTE: %{x}<br>GEX: %{z:,.0f}<extra></extra>",
        ))

        if spot > 0 and strikes:
            closest_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
            fig.add_hline(y=y_labels[closest_idx], line_dash="dash", line_color=accent, line_width=2)
            fig.add_annotation(x=x_labels[-1] if x_labels else 0, y=y_labels[closest_idx],
                text=f"Spot {spot:.2f}", showarrow=False, font=dict(color=accent, size=11),
                xanchor="right", yanchor="bottom")

        if zero_gamma is not None and zero_gamma > 0 and strikes:
            zg_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - zero_gamma))
            fig.add_hline(y=y_labels[zg_idx], line_dash="dot", line_color="#ff00ff", line_width=2)
            fig.add_annotation(x=x_labels[-1] if x_labels else 0, y=y_labels[zg_idx],
                text=f"ZG {zero_gamma:.1f}", showarrow=False, font=dict(color="#ff00ff", size=10),
                xanchor="right", yanchor="top")

        if king_nodes:
            for kn in king_nodes[:3]:
                sv = kn.get("strike", 0)
                mag = kn.get("magnitude", 0)
                if sv > 0 and strikes:
                    kn_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - sv))
                    fig.add_hline(y=y_labels[kn_idx], line_dash="solid", line_color="#ff00ff",
                                  line_width=1.5, opacity=0.7)
                    fig.add_annotation(x=x_labels[-1] if x_labels else 0, y=y_labels[kn_idx],
                        text=f"KN {sv:.0f} ({mag:,.0f})", showarrow=False,
                        font=dict(size=10, color="#ff00ff"), xanchor="right", yanchor="middle")

        if air_pockets:
            for ap in air_pockets:
                lo, hi = ap.get("lo", 0), ap.get("hi", 0)
                if lo < hi:
                    fig.add_hrect(y0=lo, y1=hi, fillcolor="rgba(255,255,0,0.08)", line_width=0, layer="below")

        fig.update_layout(
            title=dict(text="GEX Heatseeker", font=dict(color=TEXT if dark else TEXT_LIGHT, size=18)),
            xaxis_title="Time to Expiry (years)", yaxis_title="Strike ($)",
            template=tpl, paper_bgcolor=bg, plot_bgcolor=plot, height=650,
            margin=dict(l=60, r=80, t=60, b=40),
        )
        return fig
    except Exception as e:
        logger.error(f"GEX heatmap error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: FLOWSEEKER — Live Options Flow Ticker
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_row_color(size: float, daily_volume: float, oi: float, classification: str) -> str:
    if size > daily_volume or size > oi:
        return "rgba(255,68,68,0.25)"
    if classification and classification.lower() == "sweep":
        return "rgba(255,170,0,0.20)"
    return "rgba(26,26,46,0)"


def _build_flow_ticker(flow_data: Optional[List[Dict]] = None, dark: bool = True) -> go.Figure:
    if not flow_data:
        return _empty_figure("Waiting for flow data...", dark)
    try:
        sorted_data = sorted(flow_data, key=lambda p: p.get("timestamp", ""), reverse=True)[:100]
        timestamps = [p.get("timestamp", "")[:19] for p in sorted_data]
        tickers = [p.get("ticker", "") for p in sorted_data]
        strikes = [f"{p.get('strike', 0):.1f}" for p in sorted_data]
        expiries = [p.get("expiration", p.get("expiry", "")) for p in sorted_data]
        sides = [p.get("side", "") for p in sorted_data]
        types_ = [p.get("type", "") for p in sorted_data]
        sizes = [f"{p.get('size', 0):,}" for p in sorted_data]
        premiums = [f"${p.get('premium', p.get('notional', 0)):,.0f}" for p in sorted_data]
        vol_oi = [f"{p.get('vol_oi_ratio', 0):.2f}" for p in sorted_data]
        classifications = [p.get("classification", "") for p in sorted_data]

        row_colors = []
        for p in sorted_data:
            sz = p.get("size", 0)
            dv = p.get("daily_volume", sz + 1)
            oi = p.get("open_interest", sz + 1)
            cl = p.get("classification", "")
            row_colors.append(_classify_row_color(sz, dv, oi, cl))

        fill_colors = [[row_colors[i] for i in range(len(sorted_data))] for _ in range(10)]
        bg = BG_CARD if dark else BG_CARD_LIGHT

        fig = go.Figure(data=[go.Table(
            header=dict(
                values=["Time", "Ticker", "Strike", "Expiry", "Side", "Type", "Size", "Premium", "Vol/OI", "Class"],
                fill_color="#0f3460", font=dict(color=TEXT, size=11, family="monospace"),
                align="left", height=32, line=dict(color="#333", width=1),
            ),
            cells=dict(
                values=[timestamps, tickers, strikes, expiries, sides, types_, sizes, premiums, vol_oi, classifications],
                fill_color=fill_colors, font=dict(color="#ccc" if dark else "#333", size=10, family="monospace"),
                align="left", height=26, line=dict(color="#222" if dark else "#ddd", width=0.5),
            ),
        )])
        tpl = "plotly_dark" if dark else "plotly_white"
        fig.update_layout(
            title=dict(text="Flowseeker — Live Options Flow", font=dict(color=TEXT if dark else TEXT_LIGHT, size=18)),
            template=tpl, paper_bgcolor=bg, margin=dict(l=10, r=10, t=50, b=10), height=650,
        )
        return fig
    except Exception as e:
        logger.error(f"Flow ticker error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: TOXICITY & LIQUIDITY
# ═══════════════════════════════════════════════════════════════════════════════

def _build_toxicity_dashboard(
    vpin_cdf: float = 0, qi_zscore: float = 0, fragility_score: float = 0,
    regime: str = "NORMAL", history_vpin: Optional[List[float]] = None,
    history_qi: Optional[List[float]] = None, history_ts: Optional[List[str]] = None,
    dark: bool = True,
) -> go.Figure:
    try:
        is_toxic = vpin_cdf > 0.5 and abs(qi_zscore) > 1.5
        tpl = "plotly_dark" if dark else "plotly_white"
        bg = BG_CARD if dark else BG_CARD_LIGHT
        plot = BG_PLOT if dark else BG_PLOT_LIGHT
        text_color = TEXT if dark else TEXT_LIGHT
        dim = TEXT_DIM if dark else TEXT_DIM_LIGHT

        fig = make_subplots(
            rows=3, cols=2,
            specs=[[{"type": "indicator"}, {"type": "indicator"}],
                   [{"type": "indicator", "colspan": 2}, None],
                   [{"type": "scatter", "colspan": 2}, None]],
            subplot_titles=["VPIN CDF", "Quote Imbalance Z-Score", "Market Fragility Index", "60-min History"],
            vertical_spacing=0.08, row_heights=[0.25, 0.25, 0.5],
        )
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=vpin_cdf * 100,
            number={"suffix": "%", "font": {"color": text_color, "size": 20}},
            gauge={"axis": {"range": [0, 100], "tickcolor": dim},
                   "bar": {"color": DANGER if vpin_cdf > 0.5 else ACCENT},
                   "bgcolor": plot,
                   "steps": [{"range": [0, 50], "color": "rgba(0,255,136,0.08)"},
                             {"range": [50, 75], "color": "rgba(255,170,0,0.12)"},
                             {"range": [75, 100], "color": "rgba(255,68,68,0.15)"}],
                   "threshold": {"line": {"color": DANGER, "width": 3}, "value": 50}},
        ), row=1, col=1)

        qi_color = DANGER if abs(qi_zscore) > 1.5 else WARN if abs(qi_zscore) > 1.0 else ACCENT
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=qi_zscore,
            number={"prefix": "z=", "font": {"color": text_color, "size": 20}},
            gauge={"axis": {"range": [-5, 5], "tickcolor": dim}, "bar": {"color": qi_color},
                   "bgcolor": plot,
                   "steps": [{"range": [-5, -1.5], "color": "rgba(255,68,68,0.1)"},
                             {"range": [-1.5, 1.5], "color": "rgba(0,255,136,0.05)"},
                             {"range": [1.5, 5], "color": "rgba(255,68,68,0.1)"}]},
        ), row=1, col=2)

        frag_color = DANGER if fragility_score > 66 else WARN if fragility_score > 33 else ACCENT
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=fragility_score,
            number={"suffix": "/100", "font": {"color": text_color, "size": 18}},
            gauge={"axis": {"range": [0, 100], "tickcolor": dim}, "bar": {"color": frag_color},
                   "bgcolor": plot,
                   "steps": [{"range": [0, 33], "color": "rgba(0,255,136,0.08)"},
                             {"range": [33, 66], "color": "rgba(255,170,0,0.1)"},
                             {"range": [66, 100], "color": "rgba(255,68,68,0.15)"}]},
        ), row=2, col=1)

        if history_vpin and history_ts:
            fig.add_trace(go.Scatter(x=history_ts, y=[v * 100 for v in history_vpin],
                mode="lines", name="VPIN CDF %", line=dict(color=DANGER, width=1.5)), row=3, col=1)
        if history_qi and history_ts:
            fig.add_trace(go.Scatter(x=history_ts, y=history_qi,
                mode="lines", name="QI Z-Score", line=dict(color=WARN, width=1.5)), row=3, col=1)

        if is_toxic:
            fig.add_annotation(xref="paper", yref="paper", x=0.5, y=1.08,
                text="TOXIC FLOW DETECTED", showarrow=False,
                font=dict(size=22, color=DANGER, family="monospace"),
                bgcolor="rgba(58,26,26,0.9)", bordercolor=DANGER, borderwidth=2, borderpad=10)
        else:
            fig.add_annotation(xref="paper", yref="paper", x=0.5, y=1.08,
                text=f"Regime: {regime}", showarrow=False,
                font=dict(size=14, color=dim, family="monospace"))

        fig.update_layout(
            title=dict(text="Toxicity & Liquidity", font=dict(color=text_color, size=18)),
            template=tpl, paper_bgcolor=bg, plot_bgcolor=plot, height=750,
            showlegend=True, legend=dict(font=dict(color=dim, size=10)),
        )
        return fig
    except Exception as e:
        logger.error(f"Toxicity dashboard error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: VOL SURFACE — 3D SABR/SVI Surface
# ═══════════════════════════════════════════════════════════════════════════════

def _build_vol_surface(
    spot: float = 0, contracts: Optional[List[Dict]] = None, ticker: str = "SPY",
    grid_strikes: Optional[List[float]] = None, grid_expiries: Optional[List[float]] = None,
    iv_grid: Optional[List[List[float]]] = None, atm_skew: Optional[List[Dict]] = None,
    butterfly: Optional[List[Dict]] = None, dark: bool = True,
) -> go.Figure:
    try:
        if iv_grid is None or grid_strikes is None or grid_expiries is None:
            if spot > 0 and contracts:
                try:
                    from services.stochastic_vol import VolSurfaceConstructor
                    svc = VolSurfaceConstructor()
                    result = svc.build_surface(spot, contracts)
                    grid_strikes = result.get("grid_strikes", [])
                    grid_expiries = result.get("grid_expiries", [])
                    iv_grid = result.get("iv_grid", [])
                except Exception as e:
                    return _error_figure(f"Vol surface error: {e}", dark)
        if not iv_grid or not grid_strikes or not grid_expiries:
            return _empty_figure(f"Waiting for {ticker} vol surface data...", dark)

        tpl = "plotly_dark" if dark else "plotly_white"
        bg = BG_CARD if dark else BG_CARD_LIGHT
        plot = BG_PLOT if dark else BG_PLOT_LIGHT
        text_color = TEXT if dark else TEXT_LIGHT

        fig = make_subplots(
            rows=2, cols=1, row_heights=[0.65, 0.35],
            specs=[[{"type": "surface"}], [{"type": "scatter"}]],
            subplot_titles=["3D Implied Volatility Surface", "ATM Term Structure + 25d Skew"],
            vertical_spacing=0.12,
        )
        fig.add_trace(go.Surface(
            x=grid_strikes, y=grid_expiries, z=iv_grid, colorscale="Viridis",
            colorbar=dict(title="IV", x=1.02, thickness=15),
            hovertemplate="Strike: %{x:.1f}<br>TTE: %{y:.4f}<br>IV: %{z:.4f}<extra></extra>",
            lighting=dict(ambient=0.6, diffuse=0.8, roughness=0.4),
        ), row=1, col=1)

        if atm_skew:
            fig.add_trace(go.Scatter(
                x=[p.get("expiry", 0) for p in atm_skew], y=[p.get("atm_iv", 0) for p in atm_skew],
                mode="lines+markers", name="ATM IV", line=dict(color=ACCENT, width=2)), row=2, col=1)
        if butterfly:
            fig.add_trace(go.Scatter(
                x=[p.get("expiry", 0) for p in butterfly], y=[p.get("butterfly_25d", 0) for p in butterfly],
                mode="lines+markers", name="25d Butterfly", line=dict(color=WARN, width=1.5, dash="dash")), row=2, col=1)

        fig.update_layout(
            title=dict(text=f"Vol Surface — {ticker}", font=dict(color=text_color, size=18)),
            scene=dict(xaxis_title="Strike", yaxis_title="TTE", zaxis_title="Implied Vol",
                       bgcolor=plot, xaxis=dict(gridcolor="#333"), yaxis=dict(gridcolor="#333"), zaxis=dict(gridcolor="#333")),
            template=tpl, paper_bgcolor=bg, height=800, showlegend=True,
            legend=dict(font=dict(color=TEXT_DIM if dark else TEXT_DIM_LIGHT, size=10)),
        )
        return fig
    except Exception as e:
        logger.error(f"Vol surface error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5: TRINITY ALIGNMENT
# ═══════════════════════════════════════════════════════════════════════════════

def _build_trinity_dashboard(
    score: float = 0, regime: str = "NONE",
    spy_zg: Optional[List[Dict]] = None, qqq_zg: Optional[List[Dict]] = None,
    spx_zg: Optional[List[Dict]] = None, cross_corr: Optional[List[List[float]]] = None,
    aligned_levels: Optional[List[Dict]] = None, dark: bool = True,
) -> go.Figure:
    try:
        tpl = "plotly_dark" if dark else "plotly_white"
        bg = BG_CARD if dark else BG_CARD_LIGHT
        plot = BG_PLOT if dark else BG_PLOT_LIGHT
        text_color = TEXT if dark else TEXT_LIGHT
        dim = TEXT_DIM if dark else TEXT_DIM_LIGHT

        fig = make_subplots(
            rows=3, cols=2,
            specs=[[{"type": "indicator", "colspan": 2}, None],
                   [{"type": "scatter"}, {"type": "scatter"}],
                   [{"type": "scatter"}, {"type": "heatmap"}]],
            subplot_titles=["Trinity Alignment Score", "SPY Zero Gamma", "QQQ Zero Gamma", "SPX Zero Gamma", "Cross-Correlation"],
            vertical_spacing=0.1, row_heights=[0.25, 0.35, 0.4],
        )
        score_color = ACCENT if score >= 75 else WARN if score >= 50 else DANGER
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=score, number={"suffix": "/100", "font": {"color": text_color, "size": 24}},
            gauge={"axis": {"range": [0, 100], "tickcolor": dim}, "bar": {"color": score_color}, "bgcolor": plot,
                   "steps": [{"range": [0, 25], "color": "rgba(255,68,68,0.1)"}, {"range": [25, 50], "color": "rgba(255,170,0,0.08)"},
                             {"range": [50, 75], "color": "rgba(0,255,136,0.05)"}, {"range": [75, 100], "color": "rgba(0,255,136,0.1)"}]},
        ), row=1, col=1)

        for col_idx, (data, name, color) in enumerate([(spy_zg, "SPY ZG", ACCENT), (qqq_zg, "QQQ ZG", "#4488ff")], start=1):
            if data:
                ts = [d.get("ts", "") for d in data]
                vals = [d.get("value", d.get("level", 0)) for d in data]
                fig.add_trace(go.Scatter(x=ts, y=vals, mode="lines", name=name, line=dict(color=color, width=1.5)), row=2, col=col_idx)

        if spx_zg:
            ts = [d.get("ts", "") for d in spx_zg]
            vals = [d.get("value", d.get("level", 0)) for d in spx_zg]
            fig.add_trace(go.Scatter(x=ts, y=vals, mode="lines", name="SPX ZG", line=dict(color="#ff44ff", width=1.5)), row=3, col=1)

        if cross_corr:
            fig.add_trace(go.Heatmap(z=cross_corr, x=["SPY", "QQQ", "SPX"], y=["SPY", "QQQ", "SPX"],
                colorscale="RdBu", zmid=0, text=[[f"{v:.2f}" for v in row] for row in cross_corr],
                texttemplate="%{text}", textfont=dict(size=12, color=text_color),
                colorbar=dict(title="corr", x=1.02)), row=3, col=2)

        fig.update_layout(
            title=dict(text="Trinity Alignment & Node Lifecycle", font=dict(color=text_color, size=18)),
            template=tpl, paper_bgcolor=bg, plot_bgcolor=plot, height=850, showlegend=True,
            legend=dict(font=dict(color=dim, size=10)),
        )
        return fig
    except Exception as e:
        logger.error(f"Trinity dashboard error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6: ATLAS — Candlestick + Overlays
# ═══════════════════════════════════════════════════════════════════════════════

def _build_atlas_chart(
    ohlc_data: Optional[List[Dict]] = None,
    overlays: Optional[Dict[str, Any]] = None,
    time_window: str = "4h",
    dark: bool = True,
) -> go.Figure:
    """Build Atlas candlestick chart with toggleable overlays."""
    tpl = "plotly_dark" if dark else "plotly_white"
    bg = BG_CARD if dark else BG_CARD_LIGHT
    plot = BG_PLOT if dark else BG_PLOT_LIGHT
    text_color = TEXT if dark else TEXT_LIGHT

    try:
        if not ohlc_data:
            return _empty_figure("Waiting for candlestick data...<br>Select a ticker and time window", dark)

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=[d.get("timestamp", "") for d in ohlc_data],
            open=[d.get("open", 0) for d in ohlc_data],
            high=[d.get("high", 0) for d in ohlc_data],
            low=[d.get("low", 0) for d in ohlc_data],
            close=[d.get("close", 0) for d in ohlc_data],
            name="Price",
            increasing_line_color=ACCENT, decreasing_line_color=DANGER,
        ))

        if overlays:
            # King Node lines
            if overlays.get("show_king_nodes", True):
                for kn in (overlays.get("king_nodes") or [])[:3]:
                    sv = kn.get("strike", 0)
                    if sv > 0:
                        fig.add_hline(y=sv, line_dash="solid", line_color="#ff00ff",
                                      line_width=1.5, opacity=0.7)
                        fig.add_annotation(x=ohlc_data[-1].get("timestamp", "") if ohlc_data else 0, y=sv,
                            text=f"KN {sv:.0f}", showarrow=False, font=dict(size=9, color="#ff00ff"),
                            xanchor="right", yanchor="middle")

            # Zero Gamma line
            if overlays.get("show_zero_gamma", True):
                zg = overlays.get("zero_gamma")
                if zg and zg > 0:
                    fig.add_hline(y=zg, line_dash="dot", line_color="#ff00ff", line_width=2)
                    fig.add_annotation(x=ohlc_data[-1].get("timestamp", "") if ohlc_data else 0, y=zg,
                        text=f"ZG {zg:.1f}", showarrow=False, font=dict(size=10, color="#ff00ff"),
                        xanchor="right", yanchor="top")

            # Air Pockets
            if overlays.get("show_air_pockets", True):
                for ap in (overlays.get("air_pockets") or []):
                    lo, hi = ap.get("lo", 0), ap.get("hi", 0)
                    if lo < hi:
                        fig.add_hrect(y0=lo, y1=hi, fillcolor="rgba(255,255,0,0.06)", line_width=0, layer="below")

            # Anomaly markers
            if overlays.get("show_anomalies", True):
                for marker in (overlays.get("anomaly_markers") or []):
                    ts = marker.get("timestamp", "")
                    # Find closest candle
                    for d in ohlc_data:
                        if d.get("timestamp", "").startswith(ts[:16]):
                            fig.add_trace(go.Scatter(
                                x=[d.get("timestamp", "")], y=[d.get("high", 0) * 1.001],
                                mode="markers", marker=dict(symbol="triangle-down", size=10, color=DANGER),
                                name="Anomaly", showlegend=False,
                            ))
                            break

        fig.update_layout(
            title=dict(text=f"Atlas — Candlestick ({time_window})", font=dict(color=text_color, size=18)),
            xaxis_title="Time", yaxis_title="Price ($)",
            template=tpl, paper_bgcolor=bg, plot_bgcolor=plot, height=700,
            xaxis_rangeslider_visible=False,
            margin=dict(l=60, r=40, t=60, b=40),
        )
        return fig
    except Exception as e:
        logger.error(f"Atlas chart error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 7: REPLAY — Historical Replay Mode
# ═══════════════════════════════════════════════════════════════════════════════

def _build_replay_controls(
    replay_status: Optional[Dict] = None, dark: bool = True,
) -> html.Div:
    """Build replay mode controls."""
    tpl = "plotly_dark" if dark else "plotly_white"
    bg = BG_CARD if dark else BG_CARD_LIGHT
    text_color = TEXT if dark else TEXT_LIGHT
    dim = TEXT_DIM if dark else TEXT_DIM_LIGHT

    status = replay_status or {"running": False}
    is_running = status.get("running", False)

    return html.Div([
        html.Div([
            html.Label("Start:", style={"color": dim, "marginRight": "8px"}),
            dcc.Input(id="replay-start", type="text", placeholder="2026-05-20T09:30:00",
                      style={"width": "180px", "backgroundColor": plot, "color": text_color, "border": "11px solid #333"}),
            html.Label("End:", style={"color": dim, "marginLeft": "12px", "marginRight": "8px"}),
            dcc.Input(id="replay-end", type="text", placeholder="2026-05-20T10:30:00",
                      style={"width": "180px", "backgroundColor": plot, "color": text_color, "border": "1px solid #333"}),
            html.Label("Speed:", style={"color": dim, "marginLeft": "12px", "marginRight": "8px"}),
            dcc.Dropdown(id="replay-speed", options=[
                {"label": "1x", "value": "1"}, {"label": "10x", "value": "10"},
                {"label": "100x", "value": "100"}, {"label": "1000x", "value": "1000"},
            ], value="10", clearable=False, style={"width": "80px", "display": "inline-block"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "4px", "marginBottom": "10px"}),

        html.Div([
            html.Button("Play", id="replay-play-btn", n_clicks=0,
                        style={"backgroundColor": ACCENT, "color": "#000", "border": "none",
                               "padding": "6px 16px", "marginRight": "8px", "borderRadius": "4px", "cursor": "pointer"}),
            html.Button("Pause", id="replay-pause-btn", n_clicks=0,
                        style={"backgroundColor": WARN, "color": "#000", "border": "none",
                               "padding": "6px 16px", "marginRight": "8px", "borderRadius": "4px", "cursor": "pointer"}),
            html.Button("Stop", id="replay-stop-btn", n_clicks=0,
                        style={"backgroundColor": DANGER, "color": "#fff", "border": "none",
                               "padding": "6px 16px", "marginRight": "8px", "borderRadius": "4px", "cursor": "pointer"}),
            html.Span(id="replay-status-text",
                      children=f"{'Running' if is_running else 'Stopped'} — {status.get('progress_pct', 0):.1f}%",
                      style={"color": ACCENT if is_running else dim, "fontFamily": "monospace", "fontSize": "12px"}),
        ], style={"marginBottom": "10px"}),

        dcc.Store(id="store-replay-status", data=status),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 8: AGENT HUB — YAML-defined Trading Agents
# ═══════════════════════════════════════════════════════════════════════════════

def _build_agent_hub(archetypes: Optional[List[Dict]] = None, dark: bool = True) -> html.Div:
    """Build Agent Hub tab content."""
    bg = BG_CARD if dark else BG_CARD_LIGHT
    plot = BG_PLOT if dark else BG_PLOT_LIGHT
    text_color = TEXT if dark else TEXT_LIGHT
    dim = TEXT_DIM if dark else TEXT_DIM_LIGHT

    if not archetypes:
        return html.Div("Loading agent archetypes...", style={"color": dim, "padding": "20px", "fontFamily": "monospace"})

    rows = []
    for a in archetypes:
        name = a.get("name", "unknown")
        desc = a.get("description", "")
        enabled = a.get("enabled", False)
        last_fired = a.get("last_fired", "Never")
        fire_count = a.get("fire_count", 0)
        status_color = ACCENT if enabled else dim

        rows.append(html.Div([
            html.Div([
                html.Span("●" if enabled else "○", style={"color": status_color, "marginRight": "8px"}),
                html.Strong(name, style={"color": text_color, "fontFamily": "monospace"}),
                html.Span(f" — {desc[:80]}", style={"color": dim, "fontSize": "11px"}),
            ]),
            html.Div([
                html.Span(f"Last fired: {last_fired}", style={"color": dim, "fontSize": "10px", "marginRight": "16px"}),
                html.Span(f"Fires: {fire_count}", style={"color": dim, "fontSize": "10px"}),
            ], style={"marginTop": "2px", "marginBottom": "8px"}),
        ], style={"borderBottom": f"1px solid {'#333' if dark else '#ddd'}", "padding": "6px 0"}))

    return html.Div([
        html.H4("Agent Archetypes", style={"color": text_color, "fontFamily": "monospace"}),
        html.Div(rows, style={"maxHeight": "500px", "overflowY": "auto"}),
    ], style={"padding": "10px", "backgroundColor": bg, "borderRadius": "4px"})


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 9: NEXUS — Social Trading Scaffold
# ═══════════════════════════════════════════════════════════════════════════════

def _build_nexus(dark: bool = True) -> html.Div:
    """Build Nexus social trading scaffold."""
    bg = BG_CARD if dark else BG_CARD_LIGHT
    text_color = TEXT if dark else TEXT_LIGHT
    dim = TEXT_DIM if dark else TEXT_DIM_LIGHT

    return html.Div([
        html.Div([
            html.H4("Nexus — Social Trading", style={"color": text_color, "fontFamily": "monospace"}),
            html.Span("PRIVATE BETA", style={"color": WARN, "fontSize": "10px", "marginLeft": "8px",
                                               "border": f"1px solid {WARN}", "padding": "2px 6px", "borderRadius": "3px"}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),

        # Leaderboard
        html.H5("Leaderboard", style={"color": text_color}),
        html.Div("No entries yet. Be the first to share your track record.",
                 style={"color": dim, "fontSize": "12px", "padding": "8px 0"}),

        html.Hr(style={"borderColor": "#333" if dark else "#ddd"}),

        # Comments
        html.H5("Comment Thread", style={"color": text_color}),
        html.Div("Comments coming soon. Share trade ideas with the community.",
                 style={"color": dim, "fontSize": "12px", "padding": "8px 0"}),

        html.Hr(style={"borderColor": "#333" if dark else "#ddd"}),

        # Waitlist
        html.Div([
            html.P("Nexus is in private beta.", style={"color": dim, "fontSize": "12px"}),
            html.A("Join the waitlist", href="mailto:waitlist@confluencedecoder.ai",
                   style={"color": ACCENT, "fontSize": "12px"}),
        ]),
    ], style={"padding": "10px", "backgroundColor": bg, "borderRadius": "4px"})


# ═══════════════════════════════════════════════════════════════════════════════
# DASH APP CREATION + LAYOUT + CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════

def create_dash_app(fastapi_app, url_base_pathname: str = "/dashboard/"):
    if not HAS_DASH:
        logger.warning("Dash not available — skipping UI mount")
        return None

    try:
        import dash
        from starlette.middleware.wsgi import WSGIMiddleware

        dash_app = dash.Dash(
            __name__, server=fastapi_app, url_base_pathname=url_base_pathname,
            external_stylesheets=[dbc.themes.DARKLY] if 'dbc' in dir() else [],
            suppress_callback_exceptions=True, update_title=None,
            meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
        )

        # ── Layout ──────────────────────────────────────────────────────────
        dash_app.layout = html.Div([
            # Header
            html.Div([
                html.H1("Confluence Decoder Terminal", style={
                    "color": ACCENT, "fontFamily": "monospace", "display": "inline-block",
                    "marginRight": "20px", "fontSize": "22px",
                }),
                html.Span(id="live-indicator", children="LIVE", style={
                    "color": DANGER, "fontFamily": "monospace", "fontSize": "12px", "verticalAlign": "super",
                }),
                html.Button("Light", id="theme-toggle", n_clicks=0, style={
                    "marginLeft": "auto", "backgroundColor": "#333", "color": TEXT,
                    "border": "none", "padding": "4px 12px", "borderRadius": "4px", "cursor": "pointer",
                    "fontFamily": "monospace", "fontSize": "11px",
                }),
                html.Button("?", id="help-btn", n_clicks=0, style={
                    "marginLeft": "8px", "backgroundColor": "#333", "color": TEXT,
                    "border": "none", "padding": "4px 10px", "borderRadius": "4px", "cursor": "pointer",
                    "fontFamily": "monospace", "fontSize": "11px",
                }),
            ], style={
                "padding": "8px 20px", "borderBottom": "1px solid #333",
                "backgroundColor": BG_DARK, "display": "flex", "alignItems": "center",
            }),

            # Ticker selector
            html.Div([
                html.Label("Ticker: ", style={"color": TEXT_DIM, "fontFamily": "monospace"}),
                dcc.Dropdown(
                    id="ticker-selector",
                    options=[{"label": t, "value": t} for t in ["SPY", "QQQ", "SPX"]],
                    value="SPY", clearable=False,
                    style={"width": "120px", "display": "inline-block", "backgroundColor": BG_CARD, "color": TEXT},
                ),
                html.Span(id="last-update", style={
                    "color": TEXT_DIM, "fontFamily": "monospace", "fontSize": "11px", "marginLeft": "20px",
                }),
            ], style={"padding": "8px 20px", "backgroundColor": BG_DARK, "borderBottom": "1px solid #222"}),

            # Tabs
            dcc.Tabs(
                id="main-tabs", value="heatseeker",
                children=[
                    dcc.Tab(label="Heatseeker", value="heatseeker",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Flowseeker", value="flowseeker",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Toxicity", value="toxicity",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Vol Surface", value="vol-surface",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Trinity", value="trinity",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Atlas", value="atlas",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Replay", value="replay",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Agent Hub", value="agent-hub",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Nexus", value="nexus",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                ],
                style={"backgroundColor": BG_DARK, "borderBottom": "1px solid #333", "height": "36px"},
            ),

            # Tab content
            html.Div(id="tab-content", style={"padding": "10px", "backgroundColor": BG_DARK}),

            # Auto-refresh interval (5s)
            dcc.Interval(id="interval-component", interval=5000, n_intervals=0),

            # Data stores
            dcc.Store(id="store-chain", data={}),
            dcc.Store(id="store-flow", data=[]),
            dcc.Store(id="store-toxicity", data={}),
            dcc.Store(id="store-vol", data={}),
            dcc.Store(id="store-trinity", data={}),
            dcc.Store(id="store-atlas", data={}),
            dcc.Store(id="store-replay-status", data={"running": False}),
            dcc.Store(id="store-agent-hub", data=[]),
            dcc.Store(id="store-theme", data={"dark": True}),

            # Help modal
            html.Div(id="help-modal", children=[
                html.Div([
                    html.H4("Keyboard Shortcuts", style={"color": ACCENT}),
                    html.Pre(children="""
1-5: Jump to tabs (1=Heatseeker, 2=Flowseeker, ...)
A: Atlas  R: Replay  H: Agent Hub  N: Nexus
T: Toggle theme  M: Mute alerts  ?: Show this help
                    """, style={"color": TEXT, "fontFamily": "monospace", "fontSize": "12px"}),
                    html.Button("Close", id="help-close-btn", n_clicks=0),
                ], style={"backgroundColor": BG_CARD, "padding": "20px", "borderRadius": "8px",
                          "border": f"1px solid {ACCENT}", "maxWidth": "400px", "margin": "100px auto"}),
            ], style={"display": "none", "position": "fixed", "top": 0, "left": 0, "right": 0, "bottom": 0,
                      "backgroundColor": "rgba(0,0,0,0.7)", "zIndex": 1000}),
        ], style={"backgroundColor": BG_DARK, "minHeight": "100vh", "fontFamily": "monospace"})

        # ── Callbacks ────────────────────────────────────────────────────────

        # Fetch chain data
        @dash_app.callback(
            Output("store-chain", "data"), Output("last-update", "children"),
            Input("interval-component", "n_intervals"), State("ticker-selector", "value"),
        )
        def fetch_chain(n_intervals, ticker):
            import urllib.request
            try:
                url = f"http://localhost:8000/api/chain/{ticker}?expiries=4"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                return data, f"Updated: {data.get('ts', 'now')}"
            except Exception as e:
                return {}, f"Error: {e}"

        # Fetch flow data
        @dash_app.callback(
            Output("store-flow", "data"),
            Input("interval-component", "n_intervals"), State("ticker-selector", "value"),
        )
        def fetch_flow(n_intervals, ticker):
            import urllib.request
            try:
                url = f"http://localhost:8000/api/flowseeker/live?ticker={ticker}&limit=100"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                return data if isinstance(data, list) else data.get("flows", [])
            except Exception:
                return []

        # Fetch toxicity
        @dash_app.callback(
            Output("store-toxicity", "data"),
            Input("interval-component", "n_intervals"), State("ticker-selector", "value"),
        )
        def fetch_toxicity(n_intervals, ticker):
            import urllib.request
            try:
                url = f"http://localhost:8000/api/toxicity-dashboard/{ticker}"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
                    return json.loads(resp.read().decode())
            except Exception:
                return {}

        # Fetch vol surface
        @dash_app.callback(
            Output("store-vol", "data"),
            Input("interval-component", "n_intervals"), State("ticker-selector", "value"),
        )
        def fetch_vol(n_intervals, ticker):
            import urllib.request
            try:
                url = f"http://localhost:8000/api/vol-surface/{ticker}"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
                    return json.loads(resp.read().decode())
            except Exception:
                return {}

        # Fetch trinity
        @dash_app.callback(
            Output("store-trinity", "data"),
            Input("interval-component", "n_intervals"),
        )
        def fetch_trinity(n_intervals):
            import urllib.request
            try:
                with urllib.request.urlopen(urllib.request.Request("http://localhost:8000/api/trinity/align"), timeout=5) as resp:
                    return json.loads(resp.read().decode())
            except Exception:
                return {}

        # Fetch atlas overlays
        @dash_app.callback(
            Output("store-atlas", "data"),
            Input("interval-component", "n_intervals"),
            State("store-chain", "data"), State("ticker-selector", "value"),
        )
        def fetch_atlas(n_intervals, chain_data, ticker):
            import urllib.request
            try:
                spot = chain_data.get("spot", 0) if isinstance(chain_data, dict) else 0
                contracts = chain_data.get("contracts", []) if isinstance(chain_data, dict) else []
                from services.atlas_overlays import build_all_overlays
                overlays = build_all_overlays(spot=spot, contracts=contracts)
                return {"spot": spot, "contracts": contracts, "overlays": overlays, "ohlc": chain_data.get("ohlc", [])}
            except Exception:
                return {}

        # Fetch agent hub
        @dash_app.callback(
            Output("store-agent-hub", "data"),
            Input("interval-component", "n_intervals"),
        )
        def fetch_agent_hub(n_intervals):
            import urllib.request
            try:
                with urllib.request.urlopen(urllib.request.Request("http://localhost:8000/api/agent-hub/archetypes"), timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                return data.get("archetypes", [])
            except Exception:
                return []

        # Theme toggle
        @dash_app.callback(
            Output("store-theme", "data"),
            Input("theme-toggle", "n_clicks"),
            State("store-theme", "data"),
        )
        def toggle_theme(n_clicks, current):
            if n_clicks == 0:
                return current or {"dark": True}
            return {"dark": not current.get("dark", True)}

        # Help modal
        @dash_app.callback(
            Output("help-modal", "style"),
            Input("help-btn", "n_clicks"), Input("help-close-btn", "n_clicks"),
            State("help-modal", "style"),
        )
        def toggle_help(n_open, n_close, current_style):
            ctx = dash.callback_context
            if not ctx.triggered:
                return {"display": "none"}
            btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
            if btn_id == "help-btn":
                return {"position": "fixed", "top": 0, "left": 0, "right": 0, "bottom": 0,
                        "backgroundColor": "rgba(0,0,0,0.7)", "zIndex": 1000}
            return {"display": "none"}

        # Render tab content
        @dash_app.callback(
            Output("tab-content", "children"),
            Input("main-tabs", "value"), Input("interval-component", "n_intervals"),
            State("store-chain", "data"), State("store-flow", "data"),
            State("store-toxicity", "data"), State("store-vol", "data"),
            State("store-trinity", "data"), State("store-atlas", "data"),
            State("store-agent-hub", "data"), State("store-theme", "data"),
            State("ticker-selector", "value"),
        )
        def render_tab(tab, n_intervals, chain_data, flow_data, tox_data, vol_data, trinity_data, atlas_data, agent_data, theme_data, ticker):
            dark = (theme_data or {}).get("dark", True)

            if tab == "heatseeker":
                spot = chain_data.get("spot", 0) if isinstance(chain_data, dict) else 0
                contracts = chain_data.get("contracts", []) if isinstance(chain_data, dict) else []
                fig = _build_gex_heatmap(spot=spot, contracts=contracts, dark=dark)
                return dcc.Graph(figure=fig, style={"height": "650px"})

            elif tab == "flowseeker":
                fig = _build_flow_ticker(flow_data, dark=dark)
                return dcc.Graph(figure=fig, style={"height": "650px"})

            elif tab == "toxicity":
                fig = _build_toxicity_dashboard(
                    vpin_cdf=tox_data.get("vpin_cdf", 0) if isinstance(tox_data, dict) else 0,
                    qi_zscore=tox_data.get("qi_zscore", 0) if isinstance(tox_data, dict) else 0,
                    fragility_score=tox_data.get("fragility_score", 0) if isinstance(tox_data, dict) else 0,
                    regime=tox_data.get("regime", "NORMAL") if isinstance(tox_data, dict) else "NORMAL",
                    history_vpin=tox_data.get("history_vpin") if isinstance(tox_data, dict) else None,
                    history_qi=tox_data.get("history_qi") if isinstance(tox_data, dict) else None,
                    history_ts=tox_data.get("history_ts") if isinstance(tox_data, dict) else None,
                    dark=dark,
                )
                return dcc.Graph(figure=fig, style={"height": "750px"})

            elif tab == "vol-surface":
                spot = chain_data.get("spot", 0) if isinstance(chain_data, dict) else 0
                contracts = chain_data.get("contracts", []) if isinstance(chain_data, dict) else []
                fig = _build_vol_surface(spot=spot, contracts=contracts, ticker=ticker,
                    grid_strikes=vol_data.get("grid_strikes") if isinstance(vol_data, dict) else None,
                    grid_expiries=vol_data.get("grid_expiries") if isinstance(vol_data, dict) else None,
                    iv_grid=vol_data.get("iv_grid") if isinstance(vol_data, dict) else None,
                    atm_skew=vol_data.get("atm_skew") if isinstance(vol_data, dict) else None,
                    butterfly=vol_data.get("butterfly") if isinstance(vol_data, dict) else None, dark=dark)
                return dcc.Graph(figure=fig, style={"height": "800px"})

            elif tab == "trinity":
                fig = _build_trinity_dashboard(
                    score=trinity_data.get("score", 0) if isinstance(trinity_data, dict) else 0,
                    regime=trinity_data.get("regime", "NONE") if isinstance(trinity_data, dict) else "NONE",
                    spy_zg=trinity_data.get("spy_zg") if isinstance(trinity_data, dict) else None,
                    qqq_zg=trinity_data.get("qqq_zg") if isinstance(trinity_data, dict) else None,
                    spx_zg=trinity_data.get("spx_zg") if isinstance(trinity_data, dict) else None,
                    cross_corr=trinity_data.get("cross_correlation") if isinstance(trinity_data, dict) else None,
                    aligned_levels=trinity_data.get("aligned_levels") if isinstance(trinity_data, dict) else None,
                    dark=dark)
                return dcc.Graph(figure=fig, style={"height": "850px"})

            elif tab == "atlas":
                ohlc = (atlas_data or {}).get("ohlc", [])
                overlays = (atlas_data or {}).get("overlays", {})
                fig = _build_atlas_chart(ohlc_data=ohlc, overlays=overlays, dark=dark)
                return html.Div([
                    dcc.Dropdown(id="atlas-time-window", options=[
                        {"label": "1 hour", "value": "1h"}, {"label": "4 hours", "value": "4h"},
                        {"label": "1 day", "value": "1d"}, {"label": "1 week", "value": "1w"},
                    ], value="4h", clearable=False, style={"width": "120px", "marginBottom": "8px"}),
                    dcc.Graph(figure=fig, style={"height": "700px"}),
                ])

            elif tab == "replay":
                replay_status = {}
                return html.Div([
                    _build_replay_controls(replay_status=replay_status, dark=dark),
                    dcc.Graph(figure=_empty_figure("Select a time range and press Play", dark), style={"height": "600px"}),
                ])

            elif tab == "agent-hub":
                return _build_agent_hub(archetypes=agent_data, dark=dark)

            elif tab == "nexus":
                return _build_nexus(dark=dark)

            return html.Div("Select a tab", style={"color": TEXT_DIM if dark else TEXT_DIM_LIGHT, "padding": "20px"})

        # Keyboard shortcuts via clientside callback
        clientside_callback(
            """
            function(n_clicks) {
                // Keyboard shortcuts handled via document.addEventListener
                return window.dash_clientside.no_update;
            }
            """,
            Output("main-tabs", "value"),
            Input("interval-component", "n_intervals"),
        )

        # Add keyboard shortcut JS
        dash_app.index_string = '''
        <!DOCTYPE html>
        <html>
            <head>
                {%metas%}
                <title>Confluence Decoder</title>
                {%favicon%}
                {%css%}
                <script>
                document.addEventListener('keydown', function(e) {
                    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
                    var tabs = {'1':'heatseeker','2':'flowseeker','3':'toxicity','4':'vol-surface','5':'trinity','6':'atlas','7':'replay','8':'agent-hub','9':'nexus'};
                    if (tabs[e.key]) {
                        document.getElementById('main-tabs').value = tabs[e.key];
                    }
                    if (e.key === '?' || e.key === '/') {
                        var modal = document.getElementById('help-modal');
                        if (modal) modal.style.display = modal.style.display === 'none' ? 'block' : 'none';
                    }
                    if (e.key === 't' || e.key === 'T') {
                        var btn = document.getElementById('theme-toggle');
                        if (btn) btn.click();
                    }
                    if (e.key === 'm' || e.key === 'M') {
                        // Mute alerts — toggle notification permission
                        if ('Notification' in window && Notification.permission === 'granted') {
                            // Already granted, show muted indicator
                        } else if ('Notification' in window) {
                            Notification.requestPermission();
                        }
                    }
                });
                // Request notification permission on first load
                if ('Notification' in window && Notification.permission === 'default') {
                    Notification.requestPermission();
                }
                </script>
                <style>
                @media (max-width: 768px) {
                    .dash-graph { height: 400px !important; }
                    div[data-dash-column] { width: 100% !important; }
                }
                </style>
            </head>
            <body>
                {%app_entry%}
                <footer>
                    {%config%}
                    {%scripts%}
                    {%renderer%}
                </footer>
            </body>
        </html>
        '''

        logger.info(f"Dash UI mounted at {url_base_pathname}")
        return dash_app

    except Exception as e:
        logger.error(f"Failed to create Dash app: {e}")
        return None
