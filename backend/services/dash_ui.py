"""
backend/services/dash_ui.py

Dash/Plotly UI for the Confluence Decoder terminal.
Mounts into the existing FastAPI server at /dashboard/.

Tabs:
  1. Heatseeker — GEX heatmap with King Nodes and Air Pockets
  2. Flowseeker — Live options flow ticker
  3. Toxicity — VPIN, Quote Imbalance, Market Fragility
  4. Vol Surface — 3D IV surface with SABR/SVI
  5. Trinity — Multi-ticker alignment and node lifecycle
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

try:
    import dash
    from dash import dcc, html, Input, Output, State, callback
    import dash_bootstrap_components as dbc
    HAS_DASH = True
except ImportError:
    try:
        from dash import dcc, html, Input, Output, State, callback
        HAS_DASH = True
    except ImportError:
        HAS_DASH = False
        logger.warning("Dash not available — UI will not be mounted")


def _empty_figure(title: str = "Waiting for data...") -> go.Figure:
    """Create an empty figure with a waiting message."""
    fig = go.Figure()
    fig.add_annotation(
        text=title,
        xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=16, color="#888"),
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#16213e",
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


def _gex_heatmap(spot: float = 0, contracts: List[Dict] = None) -> go.Figure:
    """Create GEX heatmap: strikes x expiries, colored by GEX."""
    if not contracts or spot <= 0:
        return _empty_heatmap()

    try:
        from services.gex_aggregator import GexAggregator
        agg = GexAggregator()
        result = agg.compute(spot, contracts)
        strikes = result.get("strikes", [])
        expiries = result.get("expiries", [])
        surface = result.get("gex_surface", [])

        if not strikes or not expiries or not surface:
            return _empty_heatmap()

        fig = go.Figure()

        # GEX heatmap
        fig.add_trace(go.Heatmap(
            z=surface,
            x=[f"T={t:.3f}" for t in expiries],
            y=[f"{s:.1f}" for s in strikes],
            colorscale="RdBu",
            zmid=0,
            colorbar=dict(title="GEX", x=1.02),
            hovertemplate="Strike: %{y}<br>Expiry: %{x}<br>GEX: %{z:,.0f}<extra></extra>",
        ))

        # Spot price line
        fig.add_hline(
            y=spot, line_dash="dash", line_color="#00ff88",
            annotation_text=f"Spot: {spot:.2f}",
            annotation_position="top left",
        )

        # King Nodes (max GEX strikes)
        gex_1d = result.get("gex_1d", [])
        if gex_1d and strikes:
            for i in range(1, len(gex_1d) - 1):
                if gex_1d[i] > gex_1d[i - 1] and gex_1d[i] > gex_1d[i + 1] and gex_1d[i] > 0:
                    fig.add_trace(go.Scatter(
                        x=[f"T={expiries[0]:.3f}"],
                        y=[strikes[i]],
                        mode="markers",
                        marker=dict(symbol="diamond", size=12, color="#ff00ff"),
                        name=f"King Node {strikes[i]:.0f}",
                        showlegend=False,
                    ))

        fig.update_layout(
            title=dict(text="GEX Heatseeker", font=dict(color="#e0e0e0")),
            xaxis_title="Time to Expiry",
            yaxis_title="Strike",
            template="plotly_dark",
            paper_bgcolor="#1a1a2e",
            plot_bgcolor="#16213e",
            height=600,
        )
        return fig
    except Exception as e:
        logger.error(f"GEX heatmap error: {e}")
        return _empty_heatmap()


def _empty_heatmap() -> go.Figure:
    return _empty_figure("Waiting for GEX data...")


def _flow_ticker(flow_data: List[Dict] = None) -> go.Figure:
    """Create flow ticker table."""
    if not flow_data:
        return _empty_figure("Waiting for flow data...")

    try:
        fig = go.Figure(data=[go.Table(
            header=dict(
                values=["Time", "Ticker", "Strike", "Expiry", "Side", "Size", "Price", "Premium", "Vol/OI", "Class"],
                fill_color="#0f3460",
                font=dict(color="#e0e0e0", size=11),
                align="left",
                height=30,
            ),
            cells=dict(
                values=[
                    [p.get("timestamp", "")[:19] for p in flow_data],
                    [p.get("ticker", "") for p in flow_data],
                    [f"{p.get('strike', 0):.1f}" for p in flow_data],
                    [p.get("expiration", "") for p in flow_data],
                    [p.get("side", "") for p in flow_data],
                    [f"{p.get('size', 0):,}" for p in flow_data],
                    [f"${p.get('price', 0):.2f}" for p in flow_data],
                    [f"${p.get('premium', 0):,.0f}" for p in flow_data],
                    [f"{p.get('vol_oi_ratio', 0):.2f}" for p in flow_data],
                    [p.get("classification", "") for p in flow_data],
                ],
                fill_color=[
                    ["#1a1a2e" if i % 2 == 0 else "#16213e" for i in range(len(flow_data))]
                ] * 10,
                font=dict(color="#ccc", size=10),
                align="left",
                height=25,
            ),
        )])
        fig.update_layout(
            title=dict(text="Flowseeker — Live Options Flow", font=dict(color="#e0e0e0")),
            template="plotly_dark",
            paper_bgcolor="#1a1a2e",
            margin=dict(l=20, r=20, t=60, b=20),
            height=600,
        )
        return fig
    except Exception as e:
        logger.error(f"Flow ticker error: {e}")
        return _empty_figure("Waiting for flow data...")


def _toxicity_dashboard(vpin: float = 0, vpin_cdf: float = 0, qi: float = 0,
                        qi_zscore: float = 0, is_toxic: bool = False,
                        fragility_score: float = 0, regime: str = "NORMAL") -> go.Figure:
    """Create toxicity dashboard with VPIN, QI, and fragility gauges."""
    try:
        fig = make_subplots(
            rows=2, cols=2,
            specs=[
                [{"type": "indicator"}, {"type": "indicator"}],
                [{"type": "indicator", "colspan": 2}, None],
            ],
            subplot_titles=["VPIN CDF", "Quote Imbalance Z-Score", "Market Fragility"],
            vertical_spacing=0.15,
        )

        # VPIN CDF gauge
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=vpin_cdf * 100,
            number={"suffix": "%", "font": {"color": "#e0e0e0"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#888"},
                "bar": {"color": "#ff4444" if vpin_cdf > 0.5 else "#44ff44"},
                "steps": [
                    {"range": [0, 50], "color": "#1a3a1a"},
                    {"range": [50, 75], "color": "#3a3a1a"},
                    {"range": [75, 100], "color": "#3a1a1a"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 3},
                    "value": 50,
                },
            },
        ), row=1, col=1)

        # QI Z-Score gauge
        fig.add_trace(go.Indicator(
            mode="number+delta",
            value=qi_zscore,
            number={"prefix": "z=", "font": {"color": "#e0e0e0"}},
            delta={"reference": 1.5, "relative": False},
        ), row=1, col=2)

        # Fragility gauge
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=fragility_score,
            number={"suffix": "/100", "font": {"color": "#e0e0e0"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#888"},
                "bar": {"color": "#ff4444" if fragility_score > 66 else "#ffaa00" if fragility_score > 33 else "#44ff44"},
                "steps": [
                    {"range": [0, 33], "color": "#1a3a1a"},
                    {"range": [33, 66], "color": "#3a3a1a"},
                    {"range": [66, 100], "color": "#3a1a1a"},
                ],
            },
        ), row=2, col=1)

        # Alert annotation
        if is_toxic:
            fig.add_annotation(
                text="⚠️ TOXIC FLOW DETECTED",
                xref="paper", yref="paper",
                x=0.5, y=1.05,
                showarrow=False,
                font=dict(size=20, color="#ff0000"),
                bgcolor="#3a1a1a",
                bordercolor="#ff0000",
                borderwidth=2,
                borderpad=8,
            )

        fig.update_layout(
            title=dict(text="Toxicity & Liquidity Dashboard", font=dict(color="#e0e0e0")),
            template="plotly_dark",
            paper_bgcolor="#1a1a2e",
            height=700,
        )
        return fig
    except Exception as e:
        logger.error(f"Toxicity dashboard error: {e}")
        return _empty_figure("Waiting for toxicity data...")


def _vol_surface_3d(spot: float = 0, contracts: List[Dict] = None) -> go.Figure:
    """Create 3D IV surface plot."""
    if not contracts or spot <= 0:
        return _empty_figure("Waiting for vol surface data...")

    try:
        from services.stochastic_vol import VolSurfaceConstructor
        constructor = VolSurfaceConstructor()
        result = constructor.build_surface(spot, contracts)

        strikes = result.get("grid_strikes", [])
        expiries = result.get("grid_expiries", [])
        iv_grid = result.get("iv_grid", [])

        if not strikes or not expiries or not iv_grid:
            return _empty_figure("Insufficient data for vol surface...")

        fig = go.Figure()

        # 3D surface
        fig.add_trace(go.Surface(
            x=strikes,
            y=expiries,
            z=iv_grid,
            colorscale="Viridis",
            colorbar=dict(title="IV"),
            hovertemplate="Strike: %{x:.1f}<br>TTE: %{y:.4f}<br>IV: %{z:.4f}<extra></extra>",
        ))

        fig.update_layout(
            title=dict(text="3D Implied Volatility Surface", font=dict(color="#e0e0e0")),
            scene=dict(
                xaxis_title="Strike",
                yaxis_title="TTE",
                zaxis_title="Implied Vol",
                bgcolor="#16213e",
                xaxis=dict(gridcolor="#333"),
                yaxis=dict(gridcolor="#333"),
                zaxis=dict(gridcolor="#333"),
            ),
            template="plotly_dark",
            paper_bgcolor="#1a1a2e",
            height=700,
        )
        return fig
    except Exception as e:
        logger.error(f"Vol surface error: {e}")
        return _empty_figure("Waiting for vol surface data...")


def _trinity_dashboard(aligned_levels: List[Dict] = None, score: float = 0,
                       regime: str = "NONE", nodes: List[Dict] = None) -> go.Figure:
    """Create Trinity Alignment and Node Lifecycle visualization."""
    try:
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.4, 0.6],
            subplot_titles=["Trinity Alignment Score", "Node Lifecycle"],
            vertical_spacing=0.12,
        )

        # Trinity score gauge
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": "/100", "font": {"color": "#e0e0e0"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#888"},
                "bar": {"color": "#00ff88" if score >= 75 else "#ffaa00" if score >= 50 else "#ff4444"},
                "steps": [
                    {"range": [0, 25], "color": "#3a1a1a"},
                    {"range": [25, 50], "color": "#3a3a1a"},
                    {"range": [50, 75], "color": "#1a3a1a"},
                    {"range": [75, 100], "color": "#1a3a1a"},
                ],
            },
        ), row=1, col=1)

        # Node lifecycle scatter
        if nodes:
            strikes_n = [n.get("strike", 0) for n in nodes]
            weights = [n.get("structural_weight", 0) for n in nodes]
            opacities = [n.get("opacity", 1) for n in nodes]
            states = [n.get("state", "formed") for n in nodes]
            state_colors = {
                "formed": "#4488ff",
                "active": "#00ff88",
                "tapped": "#ffaa00",
                "decaying": "#ff4444",
                "expired": "#666666",
            }
            colors = [state_colors.get(s, "#888") for s in states]

            fig.add_trace(go.Scatter(
                x=strikes_n,
                y=weights,
                mode="markers+text",
                marker=dict(
                    size=[max(10, w * 30) for w in weights],
                    color=colors,
                    opacity=opacities,
                    line=dict(width=1, color="#fff"),
                ),
                text=[f"{s:.0f}" for s in strikes_n],
                textposition="top center",
                textfont=dict(size=9, color="#aaa"),
                hovertemplate="Strike: %{x}<br>Weight: %{y:.4f}<br>State: %{text}<extra></extra>",
            ), row=2, col=1)

        fig.update_layout(
            title=dict(text="Trinity Alignment & Node Lifecycle", font=dict(color="#e0e0e0")),
            template="plotly_dark",
            paper_bgcolor="#1a1a2e",
            plot_bgcolor="#16213e",
            height=800,
        )
        return fig
    except Exception as e:
        logger.error(f"Trinity dashboard error: {e}")
        return _empty_figure("Waiting for trinity data...")


def create_dash_app(fastapi_app, url_base_pathname: str = "/dashboard/"):
    """Create and mount Dash app onto FastAPI.

    Args:
        fastapi_app: The FastAPI application instance
        url_base_pathname: URL prefix for the dashboard

    Returns:
        The Dash app instance, or None if Dash is not available
    """
    if not HAS_DASH:
        logger.warning("Dash not available — skipping UI mount")
        return None

    try:
        from starlette.middleware.wsgi import WSGIMiddleware
        import dash

        dash_app = dash.Dash(
            __name__,
            server=fastapi_app,
            url_base_pathname=url_base_pathname,
            external_stylesheets=[dbc.themes.DARKLY] if 'dbc' in dir() else [],
            suppress_callback_exceptions=True,
            update_title=None,
            meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
        )

        # Layout with tabs
        dash_app.layout = html.Div([
            # Header
            html.Div([
                html.H1("Confluence Decoder Terminal",
                        style={"color": "#00ff88", "fontFamily": "monospace",
                               "display": "inline-block", "marginRight": "20px"}),
                html.Span("LIVE", style={
                    "color": "#ff0000", "fontFamily": "monospace",
                    "animation": "blink 1s infinite", "fontSize": "14px",
                }),
            ], style={"padding": "10px 20px", "borderBottom": "1px solid #333",
                       "backgroundColor": "#0a0a1a"}),

            # Tabs
            dcc.Tabs(
                id="main-tabs",
                value="heatseeker",
                children=[
                    dcc.Tab(label="Heatseeker", value="heatseeker",
                            style={"backgroundColor": "#1a1a2e", "color": "#888"},
                            selected_style={"backgroundColor": "#0f3460", "color": "#00ff88"}),
                    dcc.Tab(label="Flowseeker", value="flowseeker",
                            style={"backgroundColor": "#1a1a2e", "color": "#888"},
                            selected_style={"backgroundColor": "#0f3460", "color": "#00ff88"}),
                    dcc.Tab(label="Toxicity", value="toxicity",
                            style={"backgroundColor": "#1a1a2e", "color": "#888"},
                            selected_style={"backgroundColor": "#0f3460", "color": "#00ff88"}),
                    dcc.Tab(label="Vol Surface", value="vol-surface",
                            style={"backgroundColor": "#1a1a2e", "color": "#888"},
                            selected_style={"backgroundColor": "#0f3460", "color": "#00ff88"}),
                    dcc.Tab(label="Trinity", value="trinity",
                            style={"backgroundColor": "#1a1a2e", "color": "#888"},
                            selected_style={"backgroundColor": "#0f3460", "color": "#00ff88"}),
                ],
                style={"backgroundColor": "#0a0a1a", "borderBottom": "1px solid #333"},
            ),

            # Tab content
            html.Div(id="tab-content", style={"padding": "10px"}),

            # Auto-refresh interval
            dcc.Interval(id="interval-component", interval=2000, n_intervals=0),

            # Client-side stores
            dcc.Store(id="store-spy-chain", data={}),
            dcc.Store(id="store-qqq-chain", data={}),
            dcc.Store(id="store-spx-chain", data={}),
            dcc.Store(id="store-flow-data", data=[]),
            dcc.Store(id="store-toxicity", data={}),
        ], style={"backgroundColor": "#0a0a1a", "minHeight": "100vh", "fontFamily": "monospace"})

        # Callbacks
        @dash_app.callback(
            Output("tab-content", "children"),
            Input("main-tabs", "value"),
            Input("interval-component", "n_intervals"),
        )
        def render_tab(tab, n_intervals):
            from services.duckdb_engine import db

            if tab == "heatseeker":
                # Try to get data from DuckDB
                rows = db.query("SELECT * FROM ticks WHERE symbol='SPY' ORDER BY timestamp DESC LIMIT 1")
                spot = rows[0]["last"] if rows else 0
                fig = _gex_heatmap(spot=spot)
                return dcc.Graph(figure=fig, style={"height": "650px"})

            elif tab == "flowseeker":
                rows = db.query("SELECT * FROM flow_prints ORDER BY timestamp DESC LIMIT 50")
                fig = _flow_ticker(rows)
                return dcc.Graph(figure=fig, style={"height": "650px"})

            elif tab == "toxicity":
                rows = db.query("SELECT * FROM vpin_buckets ORDER BY timestamp DESC LIMIT 1")
                if rows:
                    r = rows[0]
                    fig = _toxicity_dashboard(
                        vpin=r.get("vpin_value", 0),
                        vpin_cdf=r.get("vpin_value", 0),
                        qi=0,
                        qi_zscore=r.get("qi_zscore", 0),
                    )
                else:
                    fig = _toxicity_dashboard()
                return dcc.Graph(figure=fig, style={"height": "650px"})

            elif tab == "vol-surface":
                fig = _vol_surface_3d()
                return dcc.Graph(figure=fig, style={"height": "650px"})

            elif tab == "trinity":
                fig = _trinity_dashboard()
                return dcc.Graph(figure=fig, style={"height": "650px"})

            return html.Div("Select a tab")

        logger.info(f"Dash UI mounted at {url_base_pathname}")
        return dash_app

    except Exception as e:
        logger.error(f"Failed to create Dash app: {e}")
        return None
