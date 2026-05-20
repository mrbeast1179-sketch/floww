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
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

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


def _empty_figure(title: str = "Waiting for data...") -> go.Figure:
    """Create an empty figure with a waiting message."""
    fig = go.Figure()
    fig.add_annotation(
        text=title, xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False, font=dict(size=16, color=TEXT_DIM),
    )
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG_CARD, plot_bgcolor=BG_PLOT,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


def _error_figure(msg: str) -> go.Figure:
    """Create an error figure."""
    fig = go.Figure()
    fig.add_annotation(
        text=f"⚠ {msg}", xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False, font=dict(size=14, color=DANGER),
    )
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG_CARD, plot_bgcolor=BG_PLOT,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: HEATSEEKER — GEX Heatmap with Overlays
# ═══════════════════════════════════════════════════════════════════════════════

def _build_gex_heatmap(
    spot: float = 0,
    contracts: List[Dict] = None,
    gex_surface: List[List[float]] = None,
    strikes: List[float] = None,
    expiries: List[float] = None,
    king_nodes: List[Dict] = None,
    air_pockets: List[Dict] = None,
    zero_gamma: float = None,
) -> go.Figure:
    """Build GEX heatmap: strikes × time, with overlays."""
    if not contracts and gex_surface is None:
        return _empty_figure("Waiting for GEX data...<br>Fetch SPY options chain first")

    try:
        # If we have pre-computed surface data, use it
        if gex_surface is not None and strikes and expiries:
            z = gex_surface
            y_labels = [f"{s:.1f}" for s in strikes]
            x_labels = [f"T={t:.3f}" for t in expiries]
        elif spot > 0 and contracts:
            # Compute from contracts
            try:
                from services.gex_aggregator import GexAggregator
                agg = GexAggregator()
                result = agg.compute(spot, contracts)
                strikes = result.get("strikes", [])
                expiries = result.get("expiries", [])
                z = result.get("gex_surface", [])
                if not z or not strikes or not expiries:
                    return _empty_figure("No GEX surface data available")
                y_labels = [f"{s:.1f}" for s in strikes]
                x_labels = [f"T={t:.3f}" for t in expiries]
            except Exception as e:
                logger.error(f"GEX aggregator error: {e}")
                return _error_figure(f"GEX computation error: {e}")
        else:
            return _empty_figure("Waiting for GEX data...")

        fig = go.Figure()

        # Main GEX heatmap — RdBu diverging colormap, red=negative, green=positive
        fig.add_trace(go.Heatmap(
            z=z, x=x_labels, y=y_labels,
            colorscale=[
                [0.0, "#d73027"],   # strong red (negative GEX)
                [0.25, "#fc8d59"],  # light red
                [0.45, "#fee090"],  # near zero
                [0.50, "#ffffbf"],  # zero (white/yellow)
                [0.55, "#e0f3f8"],  # near zero
                [0.75, "#91bfdb"],  # light blue/green
                [1.0, "#4575b4"],   # strong blue (positive GEX)
            ],
            zmid=0,
            colorbar=dict(title="GEX ($)", x=1.02, thickness=15),
            hovertemplate="Strike: %{y}<br>TTE: %{x}<br>GEX: %{z:,.0f}<extra></extra>",
        ))

        # Spot price horizontal line
        if spot > 0:
            closest_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
            fig.add_hline(
                y=y_labels[closest_idx], line_dash="dash", line_color=ACCENT,
                line_width=2,
            )
            fig.add_annotation(
                x=x_labels[-1] if x_labels else 0, y=y_labels[closest_idx],
                text=f"Spot {spot:.2f}",
                showarrow=False, font=dict(color=ACCENT, size=11),
                xanchor="right", yanchor="bottom",
            )

        # Zero Gamma level
        if zero_gamma is not None and zero_gamma > 0:
            zg_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - zero_gamma))
            fig.add_hline(
                y=y_labels[zg_idx], line_dash="dot", line_color="#ff00ff",
                line_width=2,
            )
            fig.add_annotation(
                x=x_labels[-1] if x_labels else 0, y=y_labels[zg_idx],
                text=f"ZG {zero_gamma:.1f}",
                showarrow=False, font=dict(color="#ff00ff", size=10),
                xanchor="right", yanchor="top",
            )

        # King Nodes — horizontal lines at top-3 |GEX| strikes
        if king_nodes:
            for kn in king_nodes[:3]:
                strike_val = kn.get("strike", 0)
                magnitude = kn.get("magnitude", 0)
                if strike_val > 0:
                    kn_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - strike_val))
                    fig.add_hline(
                        y=y_labels[kn_idx], line_dash="solid", line_color="#ff00ff",
                        line_width=1.5, opacity=0.7,
                    )
                    fig.add_annotation(
                        x=x_labels[-1] if x_labels else 0, y=y_labels[kn_idx],
                        text=f"👑 {strike_val:.0f} ({magnitude:,.0f})",
                        showarrow=False, font=dict(size=10, color="#ff00ff"),
                        xanchor="right", yanchor="middle",
                    )

        # Air Pockets — shaded regions where |GEX| < 0.2 × median
        if air_pockets:
            for ap in air_pockets:
                lo = ap.get("lo", 0)
                hi = ap.get("hi", 0)
                if lo < hi:
                    fig.add_hrect(
                        y0=lo, y1=hi, fillcolor="rgba(255,255,0,0.08)",
                        line_width=0, layer="below",
                    )
                    mid = (lo + hi) / 2
                    mid_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - mid))
                    fig.add_annotation(
                        x=x_labels[0] if x_labels else 0, y=y_labels[mid_idx],
                        text="💨 Air Pocket",
                        showarrow=False, font=dict(size=9, color="rgba(255,255,0,0.6)"),
                        xanchor="left", yanchor="middle",
                    )

        fig.update_layout(
            title=dict(text="⚡ GEX Heatseeker", font=dict(color=TEXT, size=18)),
            xaxis_title="Time to Expiry (years)",
            yaxis_title="Strike ($)",
            template="plotly_dark",
            paper_bgcolor=BG_CARD,
            plot_bgcolor=BG_PLOT,
            height=650,
            margin=dict(l=60, r=80, t=60, b=40),
        )
        return fig

    except Exception as e:
        logger.error(f"GEX heatmap error: {e}")
        return _error_figure(f"Error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: FLOWSEEKER — Live Options Flow Ticker
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_row_color(size: float, daily_volume: float, oi: float,
                         classification: str) -> str:
    """Determine row background color based on flow characteristics."""
    if size > daily_volume or size > oi:
        return "rgba(255,68,68,0.25)"  # red — AUTHENTIC FLOW
    if classification and classification.lower() == "sweep":
        return "rgba(255,170,0,0.20)"  # yellow — sweep
    return "rgba(26,26,46,0)"  # default — transparent


def _build_flow_ticker(flow_data: List[Dict] = None) -> go.Figure:
    """Build flow ticker table with color-coded rows."""
    if not flow_data:
        return _empty_figure("Waiting for flow data...<br>Connect to live feed")

    try:
        # Sort by timestamp descending (newest first)
        sorted_data = sorted(flow_data, key=lambda p: p.get("timestamp", ""), reverse=True)[:100]

        timestamps = [p.get("timestamp", "")[:19] for p in sorted_data]
        tickers = [p.get("ticker", "") for p in sorted_data]
        strikes = [f"{p.get('strike', 0):.1f}" for p in sorted_data]
        expiries = [p.get("expiration", p.get("expiry", "")) for p in sorted_data]
        sides = [p.get("side", "") for p in sorted_data]
        types = [p.get("type", "") for p in sorted_data]
        sizes = [f"{p.get('size', 0):,}" for p in sorted_data]
        premiums = [f"${p.get('premium', p.get('notional', 0)):,.0f}" for p in sorted_data]
        vol_oi = [f"{p.get('vol_oi_ratio', 0):.2f}" for p in sorted_data]
        classifications = [p.get("classification", "") for p in sorted_data]

        # Compute row colors for cell backgrounds
        row_colors = []
        for p in sorted_data:
            size = p.get("size", 0)
            daily_vol = p.get("daily_volume", size + 1)
            oi = p.get("open_interest", size + 1)
            classification = p.get("classification", "")
            row_colors.append(_classify_row_color(size, daily_vol, oi, classification))

        # Build per-cell fill colors (list of lists: 10 columns × N rows)
        fill_colors = [[row_colors[i] for i in range(len(sorted_data))] for _ in range(10)]

        fig = go.Figure(data=[go.Table(
            header=dict(
                values=["Time", "Ticker", "Strike", "Expiry", "Side", "Type",
                        "Size", "Premium", "Vol/OI", "Class"],
                fill_color="#0f3460",
                font=dict(color=TEXT, size=11, family="monospace"),
                align="left", height=32,
                line=dict(color="#333", width=1),
            ),
            cells=dict(
                values=[timestamps, tickers, strikes, expiries, sides, types,
                        sizes, premiums, vol_oi, classifications],
                fill_color=fill_colors,
                font=dict(color="#ccc", size=10, family="monospace"),
                align="left", height=26,
                line=dict(color="#222", width=0.5),
            ),
        )])

        fig.update_layout(
            title=dict(text="🌊 Flowseeker — Live Options Flow", font=dict(color=TEXT, size=18)),
            template="plotly_dark",
            paper_bgcolor=BG_CARD,
            margin=dict(l=10, r=10, t=50, b=10),
            height=650,
        )
        return fig

    except Exception as e:
        logger.error(f"Flow ticker error: {e}")
        return _error_figure(f"Error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: TOXICITY & LIQUIDITY — VPIN, QI, Fragility
# ═══════════════════════════════════════════════════════════════════════════════

def _build_toxicity_dashboard(
    vpin_cdf: float = 0,
    qi_zscore: float = 0,
    fragility_score: float = 0,
    regime: str = "NORMAL",
    history_vpin: List[float] = None,
    history_qi: List[float] = None,
    history_ts: List[str] = None,
) -> go.Figure:
    """Build toxicity dashboard with gauges and time series."""
    try:
        is_toxic = vpin_cdf > 0.5 and abs(qi_zscore) > 1.5

        fig = make_subplots(
            rows=3, cols=2,
            specs=[
                [{"type": "indicator"}, {"type": "indicator"}],
                [{"type": "indicator", "colspan": 2}, None],
                [{"type": "scatter", "colspan": 2}, None],
            ],
            subplot_titles=["VPIN CDF", "Quote Imbalance Z-Score",
                            "Market Fragility Index", "60-min History"],
            vertical_spacing=0.08,
            row_heights=[0.25, 0.25, 0.5],
        )

        # VPIN CDF gauge
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=vpin_cdf * 100,
            number={"suffix": "%", "font": {"color": TEXT, "size": 20}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": TEXT_DIM},
                "bar": {"color": DANGER if vpin_cdf > 0.5 else ACCENT},
                "bgcolor": BG_PLOT,
                "steps": [
                    {"range": [0, 50], "color": "rgba(0,255,136,0.08)"},
                    {"range": [50, 75], "color": "rgba(255,170,0,0.12)"},
                    {"range": [75, 100], "color": "rgba(255,68,68,0.15)"},
                ],
                "threshold": {"line": {"color": DANGER, "width": 3}, "value": 50},
            },
        ), row=1, col=1)

        # QI Z-Score gauge
        qi_color = DANGER if abs(qi_zscore) > 1.5 else WARN if abs(qi_zscore) > 1.0 else ACCENT
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=qi_zscore,
            number={"prefix": "z=", "font": {"color": TEXT, "size": 20}},
            gauge={
                "axis": {"range": [-5, 5], "tickcolor": TEXT_DIM},
                "bar": {"color": qi_color},
                "bgcolor": BG_PLOT,
                "steps": [
                    {"range": [-5, -1.5], "color": "rgba(255,68,68,0.1)"},
                    {"range": [-1.5, 1.5], "color": "rgba(0,255,136,0.05)"},
                    {"range": [1.5, 5], "color": "rgba(255,68,68,0.1)"},
                ],
                "threshold": {"line": {"color": DANGER, "width": 2}, "value": 1.5},
            },
        ), row=1, col=2)

        # Fragility gauge
        frag_color = DANGER if fragility_score > 66 else WARN if fragility_score > 33 else ACCENT
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=fragility_score,
            number={"suffix": "/100", "font": {"color": TEXT, "size": 18}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": TEXT_DIM},
                "bar": {"color": frag_color},
                "bgcolor": BG_PLOT,
                "steps": [
                    {"range": [0, 33], "color": "rgba(0,255,136,0.08)"},
                    {"range": [33, 66], "color": "rgba(255,170,0,0.1)"},
                    {"range": [66, 100], "color": "rgba(255,68,68,0.15)"},
                ],
            },
        ), row=2, col=1)

        # Time series — VPIN and QI history
        if history_vpin and history_ts:
            fig.add_trace(go.Scatter(
                x=history_ts, y=[v * 100 for v in history_vpin],
                mode="lines", name="VPIN CDF %",
                line=dict(color=DANGER, width=1.5),
            ), row=3, col=1)
        if history_qi and history_ts:
            fig.add_trace(go.Scatter(
                x=history_ts, y=history_qi,
                mode="lines", name="QI Z-Score",
                line=dict(color=WARN, width=1.5),
            ), row=3, col=1)

        # Toxic flow alert banner
        if is_toxic:
            fig.add_annotation(
                text="⚠️ TOXIC FLOW DETECTED",
                xref="paper", yref="paper", x=0.5, y=1.08,
                showarrow=False,
                font=dict(size=22, color=DANGER, family="monospace"),
                bgcolor="rgba(58,26,26,0.9)",
                bordercolor=DANGER, borderwidth=2, borderpad=10,
            )
            # Flash effect via background
            fig.update_layout(paper_bgcolor="rgba(58,26,26,0.3)")
        else:
            fig.add_annotation(
                text=f"Regime: {regime}",
                xref="paper", yref="paper", x=0.5, y=1.08,
                showarrow=False,
                font=dict(size=14, color=TEXT_DIM, family="monospace"),
            )

        fig.update_layout(
            title=dict(text="☠ Toxicity & Liquidity Dashboard", font=dict(color=TEXT, size=18)),
            template="plotly_dark",
            paper_bgcolor=BG_CARD,
            plot_bgcolor=BG_PLOT,
            height=750,
            showlegend=True,
            legend=dict(font=dict(color=TEXT_DIM, size=10)),
        )
        return fig

    except Exception as e:
        logger.error(f"Toxicity dashboard error: {e}")
        return _error_figure(f"Error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: VOL SURFACE — 3D SABR/SVI Surface
# ═══════════════════════════════════════════════════════════════════════════════

def _build_vol_surface(
    spot: float = 0,
    contracts: List[Dict] = None,
    ticker: str = "SPY",
    grid_strikes: List[float] = None,
    grid_expiries: List[float] = None,
    iv_grid: List[List[float]] = None,
    atm_skew: List[Dict] = None,
    butterfly: List[Dict] = None,
) -> go.Figure:
    """Build 3D IV surface with ATM skew and butterfly sub-charts."""
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
                    logger.error(f"Vol surface constructor error: {e}")
                    return _error_figure(f"Vol surface error: {e}")

        if not iv_grid or not grid_strikes or not grid_expiries:
            return _empty_figure(f"Waiting for {ticker} vol surface data...")

        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.65, 0.35],
            specs=[[{"type": "surface"}], [{"type": "scatter"}]],
            subplot_titles=["3D Implied Volatility Surface", "ATM Term Structure + 25Δ Skew"],
            vertical_spacing=0.12,
        )

        # 3D Surface
        fig.add_trace(go.Surface(
            x=grid_strikes, y=grid_expiries, z=iv_grid,
            colorscale="Viridis",
            colorbar=dict(title="IV", x=1.02, thickness=15),
            hovertemplate="Strike: %{x:.1f}<br>TTE: %{y:.4f}<br>IV: %{z:.4f}<extra></extra>",
            lighting=dict(ambient=0.6, diffuse=0.8, roughness=0.4),
        ), row=1, col=1)

        # ATM Skew + Butterfly time series
        if atm_skew:
            fig.add_trace(go.Scatter(
                x=[p.get("expiry", 0) for p in atm_skew],
                y=[p.get("atm_iv", 0) for p in atm_skew],
                mode="lines+markers", name="ATM IV",
                line=dict(color=ACCENT, width=2),
            ), row=2, col=1)

        if butterfly:
            fig.add_trace(go.Scatter(
                x=[p.get("expiry", 0) for p in butterfly],
                y=[p.get("butterfly_25d", 0) for p in butterfly],
                mode="lines+markers", name="25Δ Butterfly",
                line=dict(color=WARN, width=1.5, dash="dash"),
            ), row=2, col=1)

        fig.update_layout(
            title=dict(text=f"📊 Vol Surface — {ticker}", font=dict(color=TEXT, size=18)),
            scene=dict(
                xaxis_title="Strike", yaxis_title="TTE", zaxis_title="Implied Vol",
                bgcolor=BG_PLOT,
                xaxis=dict(gridcolor="#333", color=TEXT_DIM),
                yaxis=dict(gridcolor="#333", color=TEXT_DIM),
                zaxis=dict(gridcolor="#333", color=TEXT_DIM),
            ),
            template="plotly_dark",
            paper_bgcolor=BG_CARD,
            height=800,
            showlegend=True,
            legend=dict(font=dict(color=TEXT_DIM, size=10)),
        )
        return fig

    except Exception as e:
        logger.error(f"Vol surface error: {e}")
        return _error_figure(f"Error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5: TRINITY ALIGNMENT
# ═══════════════════════════════════════════════════════════════════════════════

def _build_trinity_dashboard(
    score: float = 0,
    regime: str = "NONE",
    spy_zg: List[Dict] = None,
    qqq_zg: List[Dict] = None,
    spx_zg: List[Dict] = None,
    cross_corr: List[List[float]] = None,
    aligned_levels: List[Dict] = None,
) -> go.Figure:
    """Build Trinity alignment dashboard."""
    try:
        fig = make_subplots(
            rows=3, cols=2,
            specs=[
                [{"type": "indicator", "colspan": 2}, None],
                [{"type": "scatter"}, {"type": "scatter"}],
                [{"type": "scatter"}, {"type": "heatmap"}],
            ],
            subplot_titles=[
                "Trinity Alignment Score",
                "SPY Zero Gamma", "QQQ Zero Gamma",
                "SPX Zero Gamma", "Cross-Correlation Matrix",
            ],
            vertical_spacing=0.1,
            row_heights=[0.25, 0.35, 0.4],
        )

        # Score gauge
        score_color = ACCENT if score >= 75 else WARN if score >= 50 else DANGER
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": "/100", "font": {"color": TEXT, "size": 24}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": TEXT_DIM},
                "bar": {"color": score_color},
                "bgcolor": BG_PLOT,
                "steps": [
                    {"range": [0, 25], "color": "rgba(255,68,68,0.1)"},
                    {"range": [25, 50], "color": "rgba(255,170,0,0.08)"},
                    {"range": [50, 75], "color": "rgba(0,255,136,0.05)"},
                    {"range": [75, 100], "color": "rgba(0,255,136,0.1)"},
                ],
            },
        ), row=1, col=1)

        # Sparkline panels
        for col_idx, (data, name, color) in enumerate([
            (spy_zg, "SPY ZG", ACCENT),
            (qqq_zg, "QQQ ZG", "#4488ff"),
        ], start=1):
            if data:
                ts = [d.get("ts", "") for d in data]
                vals = [d.get("value", d.get("level", 0)) for d in data]
                fig.add_trace(go.Scatter(
                    x=ts, y=vals, mode="lines", name=name,
                    line=dict(color=color, width=1.5),
                    fill="tozeroy", fillcolor=f"rgba{tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (0.1,)}".replace("'", ""),
                ), row=2, col=col_idx)

        # SPX ZG
        if spx_zg:
            ts = [d.get("ts", "") for d in spx_zg]
            vals = [d.get("value", d.get("level", 0)) for d in spx_zg]
            fig.add_trace(go.Scatter(
                x=ts, y=vals, mode="lines", name="SPX ZG",
                line=dict(color="#ff44ff", width=1.5),
            ), row=3, col=1)

        # Cross-correlation heatmap
        if cross_corr:
            fig.add_trace(go.Heatmap(
                z=cross_corr,
                x=["SPY", "QQQ", "SPX"],
                y=["SPY", "QQQ", "SPX"],
                colorscale="RdBu", zmid=0,
                text=[[f"{v:.2f}" for v in row] for row in cross_corr],
                texttemplate="%{text}",
                textfont=dict(size=12, color=TEXT),
                colorbar=dict(title="ρ", x=1.02),
            ), row=3, col=2)

        # Aligned levels annotation
        if aligned_levels:
            levels_text = "<br>".join([
                f"  {l.get('ticker', '')}: {l.get('level', 0):.2f} ({l.get('proximity_pct', 0):.1f}%)"
                for l in aligned_levels[:5]
            ])
            fig.add_annotation(
                xref="paper", yref="paper", x=0.01, y=0.01,
                text=f"Aligned Levels:<br>{levels_text}",
                showarrow=False, font=dict(size=10, color=TEXT_DIM, family="monospace"),
                align="left", valign="bottom",
            )

        fig.update_layout(
            title=dict(text="🔮 Trinity Alignment & Node Lifecycle", font=dict(color=TEXT, size=18)),
            template="plotly_dark",
            paper_bgcolor=BG_CARD,
            plot_bgcolor=BG_PLOT,
            height=850,
            showlegend=True,
            legend=dict(font=dict(color=TEXT_DIM, size=10)),
        )
        return fig

    except Exception as e:
        logger.error(f"Trinity dashboard error: {e}")
        return _error_figure(f"Error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# DASH APP CREATION + LAYOUT + CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════

def create_dash_app(fastapi_app, url_base_pathname: str = "/dashboard/"):
    """Create and mount Dash app onto FastAPI.

    Uses client-side callbacks to fetch API data, avoiding server-side
    async DB access issues in the Dash callback context.
    """
    if not HAS_DASH:
        logger.warning("Dash not available — skipping UI mount")
        return None

    try:
        import dash
        from starlette.middleware.wsgi import WSGIMiddleware

        dash_app = dash.Dash(
            __name__,
            server=fastapi_app,
            url_base_pathname=url_base_pathname,
            external_stylesheets=[dbc.themes.DARKLY] if 'dbc' in dir() else [],
            suppress_callback_exceptions=True,
            update_title=None,
            meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
        )

        # ── Layout ──────────────────────────────────────────────────────────
        dash_app.layout = html.Div([
            # Header
            html.Div([
                html.H1("Confluence Decoder Terminal", style={
                    "color": ACCENT, "fontFamily": "monospace",
                    "display": "inline-block", "marginRight": "20px", "fontSize": "22px",
                }),
                html.Span("● LIVE", style={
                    "color": DANGER, "fontFamily": "monospace",
                    "fontSize": "12px", "verticalAlign": "super",
                }),
                html.Span(id="connection-status", children="Connecting...", style={
                    "color": TEXT_DIM, "fontFamily": "monospace", "fontSize": "11px",
                    "marginLeft": "20px",
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
                    options=[
                        {"label": "SPY", "value": "SPY"},
                        {"label": "QQQ", "value": "QQQ"},
                        {"label": "SPX", "value": "SPX"},
                    ],
                    value="SPY",
                    clearable=False,
                    style={
                        "width": "120px", "display": "inline-block",
                        "backgroundColor": BG_CARD, "color": TEXT,
                    },
                ),
                html.Span(id="last-update", style={
                    "color": TEXT_DIM, "fontFamily": "monospace", "fontSize": "11px",
                    "marginLeft": "20px",
                }),
            ], style={"padding": "8px 20px", "backgroundColor": BG_DARK, "borderBottom": "1px solid #222"}),

            # Tabs
            dcc.Tabs(
                id="main-tabs",
                value="heatseeker",
                children=[
                    dcc.Tab(label="⚡ Heatseeker", value="heatseeker",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="🌊 Flowseeker", value="flowseeker",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="☠ Toxicity", value="toxicity",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="📊 Vol Surface", value="vol-surface",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="🔮 Trinity", value="trinity",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                ],
                style={"backgroundColor": BG_DARK, "borderBottom": "1px solid #333", "height": "36px"},
            ),

            # Tab content
            html.Div(id="tab-content", style={"padding": "10px", "backgroundColor": BG_DARK}),

            # Auto-refresh interval (5s)
            dcc.Interval(id="interval-component", interval=5000, n_intervals=0),

            # Data stores (client-side)
            dcc.Store(id="store-chain", data={}),
            dcc.Store(id="store-flow", data=[]),
            dcc.Store(id="store-toxicity", data={}),
            dcc.Store(id="store-vol", data={}),
            dcc.Store(id="store-trinity", data={}),
        ], style={"backgroundColor": BG_DARK, "minHeight": "100vh", "fontFamily": "monospace"})

        # ── Callbacks ────────────────────────────────────────────────────────

        # Fetch options chain data
        @dash_app.callback(
            Output("store-chain", "data"),
            Output("last-update", "children"),
            Input("interval-component", "n_intervals"),
            State("ticker-selector", "value"),
            prevent_initial_call=False,
        )
        def fetch_chain(n_intervals, ticker):
            import urllib.request
            import urllib.error
            try:
                url = f"http://localhost:8000/api/chain/{ticker}?expiries=4"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                return data, f"Updated: {data.get('ts', 'now')}"
            except Exception as e:
                logger.warning(f"Chain fetch error: {e}")
                return {}, f"Error: {e}"

        # Fetch flow data
        @dash_app.callback(
            Output("store-flow", "data"),
            Input("interval-component", "n_intervals"),
            State("ticker-selector", "value"),
            prevent_initial_call=False,
        )
        def fetch_flow(n_intervals, ticker):
            import urllib.request
            try:
                url = f"http://localhost:8000/api/flowseeker/live?ticker={ticker}&limit=100"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                return data if isinstance(data, list) else data.get("flows", [])
            except Exception as e:
                logger.warning(f"Flow fetch error: {e}")
                return []

        # Fetch toxicity data
        @dash_app.callback(
            Output("store-toxicity", "data"),
            Input("interval-component", "n_intervals"),
            State("ticker-selector", "value"),
            prevent_initial_call=False,
        )
        def fetch_toxicity(n_intervals, ticker):
            import urllib.request
            try:
                url = f"http://localhost:8000/api/toxicity-dashboard/{ticker}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                return data
            except Exception as e:
                logger.warning(f"Toxicity fetch error: {e}")
                return {}

        # Fetch vol surface data
        @dash_app.callback(
            Output("store-vol", "data"),
            Input("interval-component", "n_intervals"),
            State("ticker-selector", "value"),
            prevent_initial_call=False,
        )
        def fetch_vol(n_intervals, ticker):
            import urllib.request
            try:
                url = f"http://localhost:8000/api/vol-surface/{ticker}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                return data
            except Exception as e:
                logger.warning(f"Vol surface fetch error: {e}")
                return {}

        # Fetch trinity data
        @dash_app.callback(
            Output("store-trinity", "data"),
            Input("interval-component", "n_intervals"),
            prevent_initial_call=False,
        )
        def fetch_trinity(n_intervals):
            import urllib.request
            try:
                url = "http://localhost:8000/api/trinity/align"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                return data
            except Exception as e:
                logger.warning(f"Trinity fetch error: {e}")
                return {}

        # Render tab content
        @dash_app.callback(
            Output("tab-content", "children"),
            Input("main-tabs", "value"),
            Input("interval-component", "n_intervals"),
            State("store-chain", "data"),
            State("store-flow", "data"),
            State("store-toxicity", "data"),
            State("store-vol", "data"),
            State("store-trinity", "data"),
            State("ticker-selector", "value"),
            prevent_initial_call=False,
        )
        def render_tab(tab, n_intervals, chain_data, flow_data, tox_data, vol_data, trinity_data, ticker):
            if tab == "heatseeker":
                spot = chain_data.get("spot", 0) if isinstance(chain_data, dict) else 0
                contracts = chain_data.get("contracts", []) if isinstance(chain_data, dict) else []
                # Try to get pre-computed GEX surface from API
                gex_surface = chain_data.get("gex_surface", None) if isinstance(chain_data, dict) else None
                strikes = chain_data.get("gex_strikes", None) if isinstance(chain_data, dict) else None
                expiries = chain_data.get("gex_expiries", None) if isinstance(chain_data, dict) else None
                king_nodes = chain_data.get("king_nodes", None) if isinstance(chain_data, dict) else None
                air_pockets = chain_data.get("air_pockets", None) if isinstance(chain_data, dict) else None
                zero_gamma = chain_data.get("zero_gamma", None) if isinstance(chain_data, dict) else None

                fig = _build_gex_heatmap(
                    spot=spot, contracts=contracts,
                    gex_surface=gex_surface, strikes=strikes, expiries=expiries,
                    king_nodes=king_nodes, air_pockets=air_pockets, zero_gamma=zero_gamma,
                )
                return dcc.Graph(figure=fig, style={"height": "650px"})

            elif tab == "flowseeker":
                fig = _build_flow_ticker(flow_data)
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
                )
                return dcc.Graph(figure=fig, style={"height": "750px"})

            elif tab == "vol-surface":
                spot = chain_data.get("spot", 0) if isinstance(chain_data, dict) else 0
                contracts = chain_data.get("contracts", []) if isinstance(chain_data, dict) else []
                fig = _build_vol_surface(
                    spot=spot, contracts=contracts, ticker=ticker,
                    grid_strikes=vol_data.get("grid_strikes") if isinstance(vol_data, dict) else None,
                    grid_expiries=vol_data.get("grid_expiries") if isinstance(vol_data, dict) else None,
                    iv_grid=vol_data.get("iv_grid") if isinstance(vol_data, dict) else None,
                    atm_skew=vol_data.get("atm_skew") if isinstance(vol_data, dict) else None,
                    butterfly=vol_data.get("butterfly") if isinstance(vol_data, dict) else None,
                )
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
                )
                return dcc.Graph(figure=fig, style={"height": "850px"})

            return html.Div("Select a tab", style={"color": TEXT_DIM, "padding": "20px"})

        logger.info(f"Dash UI mounted at {url_base_pathname}")
        return dash_app

    except Exception as e:
        logger.error(f"Failed to create Dash app: {e}")
        return None
