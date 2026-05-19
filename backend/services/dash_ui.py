"""
backend/services/dash_ui.py

Confluence Decoder — Dash/Plotly Dashboard UI
Mounts into the existing FastAPI server via starlette WSGI middleware.

Five tabs:
  1. Heatseeker  — GEX heatmap with King Nodes and Air Pockets
  2. Flowseeker — Live options flow ticker
  3. Toxicity   — VPIN + Quote Imbalance dashboard
  4. Vol Surface — 3D IV surface with SABR overlay
  5. Trinity    — Multi-ticker gamma alignment

All callbacks are stubs that read from services.duckdb_engine.db.
Auto-refresh every 2 seconds via dcc.Interval.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

try:
    import dash
    from dash import dcc, html, dash_table, Input, Output, State, callback
    from dash.exceptions import PreventUpdate
    from dash import no_update
except ImportError:
    raise ImportError("dash is required. Install with: pip install dash")

try:
    import dash_bootstrap_components as dbc
    HAS_DBC = True
except ImportError:
    HAS_DBC = False

try:
    from starlette.middleware.wsgi import WSGIMiddleware
    HAS_WSGI = True
except ImportError:
    HAS_WSGI = False

# ---------------------------------------------------------------------------
# Attempt to import the DuckDB engine; provide a graceful fallback
# ---------------------------------------------------------------------------
try:
    from services.duckdb_engine import db as duck
except ImportError:
    try:
        from backend.services.duckdb_engine import db as duck
    except ImportError:
        duck = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Default Plotly dark template
pio.templates.default = "plotly_dark"

# ---------------------------------------------------------------------------
# Colour palette (institutional neon-on-dark)
# ---------------------------------------------------------------------------
C = {
    "bg":           "#0d1117",
    "bg_card":       "#161b22",
    "bg_card_alt":   "#1c2333",
    "text":          "#c9d1d9",
    "text_muted":    "#8b949e",
    "neon_green":    "#39ff14",
    "neon_red":      "#ff3f5a",
    "neon_cyan":     "#00e5ff",
    "neon_purple":   "#bf5af2",
    "neon_orange":   "#ff9f43",
    "neon_yellow":   "#ffd54f",
    "neon_gold":     "#f0b429",
    "grid":          "#21262d",
    "border":        "#30363d",
    "header_bg":     "#010409",
    "sweep":         "#bf5af2",
    "block":         "#ff9f43",
    "unusual":       "#ffd54f",
    "regular":       "#6e7681",
    "bull":          "#3fb950",
    "bear":          "#f85149",
    "warning":       "#f0883e",
    "danger":        "#da3633",
}

# Dark template override for consistent styling
_DARK_LAYOUT = dict(
    paper_bgcolor=C["bg"],
    plot_bgcolor=C["bg_card"],
    font=dict(color=C["text"], family="SF Mono, Fira Code, monospace", size=12),
    xaxis=dict(
        gridcolor=C["grid"], zerolinecolor=C["grid"],
        linecolor=C["border"], tickfont=dict(color=C["text_muted"]),
    ),
    yaxis=dict(
        gridcolor=C["grid"], zerolinecolor=C["grid"],
        linecolor=C["border"], tickfont=dict(color=C["text_muted"]),
    ),
)

TEMPLATE = "plotly_dark"


def _merge_layout(fig: go.Figure) -> go.Figure:
    """Apply the global dark layout dict to a figure."""
    fig.update_layout(**_DARK_LAYOUT)
    return fig


def _empty_figure(title: str) -> go.Figure:
    """Return a placeholder figure with 'Waiting for data…' annotation."""
    fig = go.Figure()
    fig.add_annotation(
        text="Waiting for data…",
        xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False, font=dict(size=18, color=C["text_muted"]),
    )
    fig.update_layout(
        title=dict(text=title, font=dict(color=C["text"], size=16)),
        **{k: v for k, v in _DARK_LAYOUT.items() if k not in ("xaxis", "yaxis")},
    )
    return fig


def _safe_query(sql: str, params: Optional[List] = None) -> List[Dict[str, Any]]:
    """Run a DuckDB query and return list of dicts, or [] on error / no engine."""
    if duck is None:
        logger.debug("DuckDB engine not available; returning empty result.")
        return []
    try:
        return duck.query(sql, params)
    except Exception as exc:
        logger.error("Query failed: %s — %s", sql[:80], exc)
        return []


def _safe_query_df(sql: str, params: Optional[List] = None) -> Optional[pd.DataFrame]:
    """Run a DuckDB query and return a DataFrame, or None."""
    if duck is None:
        return None
    try:
        return duck.query_df(sql, params)
    except Exception as exc:
        logger.error("Query (df) failed: %s — %s", sql[:80], exc)
        return None


# ===========================================================================
# TAB HELPERS — each returns a component tree for its tab
# ===========================================================================

def _build_heatseeker_tab() -> Any:
    """GEX Heatmap tab layout."""
    container_cls = dbc.Card if HAS_DBC else html.Div
    body_cls = dbc.CardBody if HAS_DBC else html.Div

    inner = body_cls(
        children=[
            html.Div(
                [
                    html.Span("✦ GEX Heatseeker", style={
                        "color": C["neon_cyan"], "fontSize": 20,
                        "fontWeight": "bold", "letterSpacing": 1,
                    }),
                    html.Span("  ·  Gamma Exposure Heatmap", style={
                        "color": C["text_muted"], "fontSize": 13,
                        "marginLeft": 8,
                    }),
                ],
                style={"marginBottom": 12, "borderBottom": f"1px solid {C['grid']}", "paddingBottom": 8},
            ),
            # Ticker selector row
            html.Div(
                [
                    dcc.Dropdown(
                        id="heatseeker-ticker-dropdown",
                        options=[
                            {"label": "SPY", "value": "SPY"},
                            {"label": "QQQ", "value": "QQQ"},
                            {"label": "IWM", "value": "IWM"},
                            {"label": "SPX", "value": "SPX"},
                        ],
                        value="SPY",
                        clearable=False,
                        style={
                            "width": 160, "display": "inline-block",
                            "verticalAlign": "middle",
                        },
                    ),
                    html.Span(id="heatseeker-spot-label", children="Spot: —",
                              style={"marginLeft": 16, "color": C["text_muted"]}),
                    html.Span(id="heatseeker-net-gex-label", children="Net GEX: —",
                              style={"marginLeft": 16, "color": C["neon_cyan"]}),
                ],
                style={"marginBottom": 8},
            ),
            dcc.Graph(id="heatseeker-graph", figure=_empty_figure("GEX Heatmap"),
                      config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d"]}),
            # King Nodes table
            html.Div(
                html.H5("King Nodes (Local GEX Maxima)", style={"color": C["neon_gold"]}),
                style={"marginTop": 16, "marginBottom": 8},
            ),
            html.Div(id="heatseeker-king-nodes-table"),
            # Air Pockets table
            html.Div(
                html.H5("Air Pockets (Zero-GEX Zones)", style={"color": C["neon_purple"]}),
                style={"marginTop": 16, "marginBottom": 8},
            ),
            html.Div(id="heatseeker-air-pockets-table"),
        ]
    )

    if HAS_DBC:
        return dbc.Card(body_cls, style={
            "backgroundColor": C["bg_card"], "border": f"1px solid {C['border']}",
            "borderRadius": 8, "padding": 16, "marginBottom": 12,
        })
    return html.Div(inner, style={
        "backgroundColor": C["bg_card"], "border": f"1px solid {C['border']}",
        "borderRadius": 8, "padding": 16, "marginBottom": 12,
    })


def _build_flowseeker_tab() -> Any:
    """Live Flow Ticker tab layout."""
    container_cls = dbc.Card if HAS_DBC else html.Div
    body_cls = dbc.CardBody if HAS_DBC else html.Div

    inner = body_cls(
        children=[
            html.Div(
                [
                    html.Span("⚡ Flowseeker", style={
                        "color": C["neon_orange"], "fontSize": 20,
                        "fontWeight": "bold", "letterSpacing": 1,
                    }),
                    html.Span("  ·  Real-Time Options Flow Ticker", style={
                        "color": C["text_muted"], "fontSize": 13,
                        "marginLeft": 8,
                    }),
                ],
                style={"marginBottom": 12, "borderBottom": f"1px solid {C['grid']}", "paddingBottom": 8},
            ),
            html.Div(
                [
                    dcc.Input(
                        id="flowseeker-search",
                        type="text", placeholder="Filter ticker…",
                        debounce=True,
                        style={
                            "backgroundColor": C["bg"], "color": C["text"],
                            "border": f"1px solid {C['border']}", "borderRadius": 4,
                            "padding": "6px 10px", "width": 200,
                            "fontFamily": "SF Mono, monospace", "fontSize": 13,
                        },
                    ),
                    html.Span(id="flowseeker-count", children="0 prints",
                              style={"marginLeft": 16, "color": C["text_muted"]}),
                ],
                style={"marginBottom": 12},
            ),
            # Data table
            html.Div(id="flowseeker-table-container"),
        ]
    )

    if HAS_DBC:
        return dbc.Card(body_cls, style={
            "backgroundColor": C["bg_card"], "border": f"1px solid {C['border']}",
            "borderRadius": 8, "padding": 16, "marginBottom": 12,
        })
    return html.Div(inner, style={
        "backgroundColor": C["bg_card"], "border": f"1px solid {C['border']}",
        "borderRadius": 8, "padding": 16, "marginBottom": 12,
    })


def _build_toxicity_tab() -> Any:
    """VPIN + Quote Imbalance dashboard tab layout."""
    container_cls = dbc.Card if HAS_DBC else html.Div
    body_cls = dbc.CardBody if HAS_DBC else html.Div

    inner = body_cls(
        children=[
            html.Div(
                [
                    html.Span("☢ Toxicity", style={
                        "color": C["neon_red"], "fontSize": 20,
                        "fontWeight": "bold", "letterSpacing": 1,
                    }),
                    html.Span("  ·  VPIN + Quote Imbalance Dashboard", style={
                        "color": C["text_muted"], "fontSize": 13,
                        "marginLeft": 8,
                    }),
                ],
                style={"marginBottom": 12, "borderBottom": f"1px solid {C['grid']}", "paddingBottom": 8},
            ),
            # Alert banner (hidden by default)
            html.Div(
                id="toxicity-alert-banner",
                children=html.Span("⚠ TOXIC FLOW DETECTED", style={
                    "color": "#fff", "fontWeight": "bold", "fontSize": 16,
                    "letterSpacing": 2,
                }),
                style={
                    "display": "none",
                    "backgroundColor": C["danger"],
                    "padding": "10px 16px",
                    "borderRadius": 6,
                    "marginBottom": 12,
                    "textAlign": "center",
                },
            ),
            # Gauges row
            html.Div(
                [
                    html.Div(
                        dcc.Graph(id="toxicity-vpin-gauge",
                                  figure=_empty_figure("VPIN CDF"),
                                  config={"displaylogo": False},
                                  style={"height": 220}),
                        style={"flex": 1, "marginRight": 8},
                    ),
                    html.Div(
                        dcc.Graph(id="toxicity-fragility-gauge",
                                  figure=_empty_figure("Market Fragility"),
                                  config={"displaylogo": False},
                                  style={"height": 220}),
                        style={"flex": 1, "marginLeft": 8},
                    ),
                ],
                style={"display": "flex", "marginBottom": 12},
            ),
            # VPIN time series
            dcc.Graph(id="toxicity-vpin-series",
                      figure=_empty_figure("VPIN Time Series"),
                      config={"displaylogo": False}),
            # Quote Imbalance row
            html.Div(
                [
                    html.Div(
                        dcc.Graph(id="toxicity-qi-bars",
                                  figure=_empty_figure("Quote Imbalance"),
                                  config={"displaylogo": False}),
                        style={"flex": 2, "marginRight": 8},
                    ),
                    html.Div(
                        dcc.Graph(id="toxicity-qi-zscore",
                                  figure=_empty_figure("QI Z-Score"),
                                  config={"displaylogo": False}),
                        style={"flex": 1, "marginLeft": 8},
                    ),
                ],
                style={"display": "flex", "marginTop": 12},
            ),
        ]
    )

    if HAS_DBC:
        return dbc.Card(body_cls, style={
            "backgroundColor": C["bg_card"], "border": f"1px solid {C['border']}",
            "borderRadius": 8, "padding": 16, "marginBottom": 12,
        })
    return html.Div(inner, style={
        "backgroundColor": C["bg_card"], "border": f"1px solid {C['border']}",
        "borderRadius": 8, "padding": 16, "marginBottom": 12,
    })


def _build_vol_surface_tab() -> Any:
    """3D IV Surface tab layout."""
    container_cls = dbc.Card if HAS_DBC else html.Div
    body_cls = dbc.CardBody if HAS_DBC else html.Div

    inner = body_cls(
        children=[
            html.Div(
                [
                    html.Span("◈ Vol Surface", style={
                        "color": C["neon_purple"], "fontSize": 20,
                        "fontWeight": "bold", "letterSpacing": 1,
                    }),
                    html.Span("  ·  3D Implied Volatility Surface + SABR", style={
                        "color": C["text_muted"], "fontSize": 13,
                        "marginLeft": 8,
                    }),
                ],
                style={"marginBottom": 12, "borderBottom": f"1px solid {C['grid']}", "paddingBottom": 8},
            ),
            # 3D surface
            dcc.Graph(id="vol-surface-3d",
                      figure=_empty_figure("IV Surface (3D)"),
                      config={"displaylogo": False},
                      style={"height": 520}),
            # ATM term structure
            dcc.Graph(id="vol-surface-atm",
                      figure=_empty_figure("ATM Term Structure"),
                      config={"displaylogo": False},
                      style={"height": 260, "marginTop": 12}),
        ]
    )

    if HAS_DBC:
        return dbc.Card(body_cls, style={
            "backgroundColor": C["bg_card"], "border": f"1px solid {C['border']}",
            "borderRadius": 8, "padding": 16, "marginBottom": 12,
        })
    return html.Div(inner, style={
        "backgroundColor": C["bg_card"], "border": f"1px solid {C['border']}",
        "borderRadius": 8, "padding": 16, "marginBottom": 12,
    })


def _build_trinity_tab() -> Any:
    """Multi-Ticker Alignment tab layout."""
    container_cls = dbc.Card if HAS_DBC else html.Div
    body_cls = dbc.CardBody if HAS_DBC else html.Div

    inner = body_cls(
        children=[
            html.Div(
                [
                    html.Span("△ Trinity", style={
                        "color": C["neon_green"], "fontSize": 20,
                        "fontWeight": "bold", "letterSpacing": 1,
                    }),
                    html.Span("  ·  Multi-Ticker Gamma Alignment", style={
                        "color": C["text_muted"], "fontSize": 13,
                        "marginLeft": 8,
                    }),
                ],
                style={"marginBottom": 12, "borderBottom": f"1px solid {C['grid']}", "paddingBottom": 8},
            ),
            # Alignment score gauge + price chart
            html.Div(
                [
                    html.Div(
                        dcc.Graph(id="trinity-alignment-gauge",
                                  figure=_empty_figure("Alignment Score"),
                                  config={"displaylogo": False},
                                  style={"height": 240}),
                        style={"flex": 1, "marginRight": 8},
                    ),
                    html.Div(
                        dcc.Graph(id="trinity-price-chart",
                                  figure=_empty_figure("Zero-Gamma Levels"),
                                  config={"displaylogo": False},
                                  style={"height": 240}),
                        style={"flex": 2, "marginLeft": 8},
                    ),
                ],
                style={"display": "flex", "marginBottom": 12},
            ),
            # Node lifecycle visualization
            dcc.Graph(id="trinity-node-lifecycle",
                      figure=_empty_figure("Node Lifecycle"),
                      config={"displaylogo": False},
                      style={"height": 340}),
        ]
    )

    if HAS_DBC:
        return dbc.Card(body_cls, style={
            "backgroundColor": C["bg_card"], "border": f"1px solid {C['border']}",
            "borderRadius": 8, "padding": 16, "marginBottom": 12,
        })
    return html.Div(inner, style={
        "backgroundColor": C["bg_card"], "border": f"1px solid {C['border']}",
        "borderRadius": 8, "padding": 16, "marginBottom": 12,
    })


# ===========================================================================
# CALLBACK STUBS
# ===========================================================================

def _register_callbacks(app: dash.Dash) -> None:
    """Register all Dash callbacks (stubs that read from DuckDB)."""

    # ------------------------------------------------------------------
    # HEATSEEKER callbacks
    # ------------------------------------------------------------------

    @app.callback(
        Output("heatseeker-graph", "figure"),
        Output("heatseeker-spot-label", "children"),
        Output("heatseeker-net-gex-label", "children"),
        Output("heatseeker-king-nodes-table", "children"),
        Output("heatseeker-air-pockets-table", "children"),
        Input("dash-interval", "n_intervals"),
        State("heatseeker-ticker-dropdown", "value"),
    )
    def update_heatseeker(n_intervals, ticker):
        if not ticker:
            raise PreventUpdate

        # Query GEX grid data from DuckDB
        rows = _safe_query(
            """
            SELECT strike, expiry, gex, call_gex, put_gex, total_oi
            FROM gex_grid
            WHERE symbol = ?
            ORDER BY expiry, strike
            LIMIT 500
            """,
            [ticker],
        )

        if not rows:
            return (
                _empty_figure("GEX Heatmap"),
                f"Spot: —",
                "Net GEX: —",
                html.Span("No King Node data", style={"color": C["text_muted"]}),
                html.Span("No Air Pocket data", style={"color": C["text_muted"]}),
            )

        df = pd.DataFrame(rows)
        spot = float(df.get("spot", pd.Series([0])).iloc[0]) if "spot" in df.columns else 0

        # Build heatmap: pivot strikes × expiries
        try:
            pivot = df.pivot_table(index="strike", columns="expiry", values="gex", aggfunc="sum")
            strikes = pivot.index.tolist()
            expiries = pivot.columns.tolist()
            z = pivot.values.tolist()
        except Exception:
            return (
                _empty_figure("GEX Heatmap"),
                f"Spot: {spot:.2f}" if spot else "Spot: —",
                "Net GEX: —",
                html.Span("No King Node data", style={"color": C["text_muted"]}),
                html.Span("No Air Pocket data", style={"color": C["text_muted"]}),
            )

        fig = go.Figure()

        # GEX heatmap
        fig.add_trace(go.Heatmap(
            z=z, x=expiries, y=strikes,
            colorscale="RdBu_r",
            zmid=0,
            colorbar=dict(title="GEX", thickness=15, len=0.9),
            hovertemplate="Strike: %{y}<br>Expiry: %{x}<br>GEX: %{z:,.0f}<extra></extra>",
        ))

        # Spot price line (horizontal across all expiries)
        if spot and expiries:
            fig.add_trace(go.Scatter(
                x=expiries, y=[spot] * len(expiries),
                mode="lines", name="Spot",
                line=dict(color=C["neon_cyan"], width=2, dash="dot"),
                hovertemplate=f"Spot: {spot:.2f}<extra></extra>",
            ))

        # King Nodes — local GEX maxima
        king_nodes = _detect_king_nodes(df)
        if king_nodes:
            fig.add_trace(go.Scatter(
                x=[kn["expiry"] for kn in king_nodes],
                y=[kn["strike"] for kn in king_nodes],
                mode="markers", name="King Nodes",
                marker=dict(
                    symbol="diamond", size=14,
                    color=C["neon_gold"], line=dict(color="#fff", width=1),
                ),
                hovertemplate="King Node<br>Strike: %{y}<br>Expiry: %{x}<br>GEX: %{customdata:,.0f}<extra></extra>",
                customdata=[[kn["gex"]] for kn in king_nodes],
            ))

        # Air Pockets — zero-GEX zones (shaded rectangles)
        air_pockets = _detect_air_pockets(df)
        shapes = []
        for ap in air_pockets:
            shapes.append(dict(
                type="rect", x0=ap["expiry_start"], x1=ap["expiry_end"],
                y0=ap["strike_low"], y1=ap["strike_high"],
                fillcolor="rgba(191, 90, 242, 0.12)",
                line=dict(color=C["neon_purple"], width=1, dash="dash"),
                layer="below",
            ))
        fig.update_layout(shapes=shapes)

        fig.update_layout(
            title=dict(text=f"GEX Heatmap — {ticker}", font=dict(color=C["text"], size=16)),
            xaxis_title="Expiry", yaxis_title="Strike",
            template=TEMPLATE,
            height=480,
        )
        _merge_layout(fig)

        # Net GEX
        net_gex = float(df["gex"].sum()) if "gex" in df.columns else 0
        net_gex_str = f"Net GEX: {net_gex/1e9:,.2f}B" if abs(net_gex) >= 1e9 else f"Net GEX: {net_gex/1e6:,.2f}M"

        # King Nodes table
        king_table = _build_king_nodes_table(king_nodes) if king_nodes else html.Span(
            "No King Nodes detected", style={"color": C["text_muted"]}
        )

        # Air Pockets table
        air_table = _build_air_pockets_table(air_pockets) if air_pockets else html.Span(
            "No Air Pockets detected", style={"color": C["text_muted"]}
        )

        return (
            fig,
            f"Spot: {spot:.2f}" if spot else "Spot: —",
            net_gex_str,
            king_table,
            air_table,
        )

    # ------------------------------------------------------------------
    # FLOWSEEKER callbacks
    # ------------------------------------------------------------------

    @app.callback(
        Output("flowseeker-table-container", "children"),
        Output("flowseeker-count", "children"),
        Input("dash-interval", "n_intervals"),
        State("flowseeker-search", "value"),
    )
    def update_flowseeker(n_intervals, search_term):
        sql = """
            SELECT timestamp, ticker, strike, expiration AS expiry, side, type,
                   size, price, premium, volume, oi, classification
            FROM flow_prints
            ORDER BY timestamp DESC
            LIMIT 200
        """
        rows = _safe_query(sql)

        if not rows:
            return (
                html.Span("Waiting for flow data…", style={"color": C["text_muted"]}),
                "0 prints",
            )

        df = pd.DataFrame(rows)

        # Apply search filter
        if search_term:
            mask = df["ticker"].str.contains(search_term, case=False, na=False)
            df = df[mask]

        count = len(df)

        # Determine bullish/bearish per row
        def _row_color(row):
            if row.get("type") == "call" and row.get("price", 0) > row.get("ask", 0):
                return C["bull"]
            if row.get("type") == "put" and row.get("price", 0) < row.get("bid", 0):
                return C["bear"]
            return C["text"]

        # Classification badge colours
        badge_colors = {
            "sweep": C["sweep"],
            "block": C["block"],
            "unusual": C["unusual"],
            "regular": C["regular"],
        }

        columns = [
            {"name": "Time", "id": "timestamp"},
            {"name": "Ticker", "id": "ticker"},
            {"name": "Strike", "id": "strike"},
            {"name": "Expiry", "id": "expiry"},
            {"name": "Side", "id": "side"},
            {"name": "Size", "id": "size"},
            {"name": "Price", "id": "price"},
            {"name": "Premium", "id": "premium"},
            {"name": "Vol/OI", "id": "vol_oi"},
            {"name": "Class", "id": "classification"},
        ]

        # Format data
        display_df = df.copy()
        display_df["timestamp"] = pd.to_datetime(display_df["timestamp"]).dt.strftime("%H:%M:%S")
        display_df["vol_oi"] = display_df.apply(
            lambda r: f"{r.get('volume', 0):,} / {r.get('oi', 0):,}", axis=1
        )
        display_df["premium"] = display_df["premium"].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "—")
        display_df["price"] = display_df["price"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
        display_df["strike"] = display_df["strike"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")

        data = display_df[["timestamp", "ticker", "strike", "expiry", "side",
                           "size", "price", "premium", "vol_oi", "classification"]].to_dict("records")

        # Build conditional row styling
        style_data_conditional = []
        for i, row in enumerate(data):
            color = _row_color(row)
            style_data_conditional.append(
                {"if": {"row_index": i}, "backgroundColor": f"rgba(255,255,255,0.02)",
                 "color": color}
            )

        # Classification badge styling
        for cls_name, cls_color in badge_colors.items():
            style_data_conditional.append({
                "if": {"filter_query": f'{{classification}} = "{cls_name}"',
                       "column_id": "classification"},
                "backgroundColor": cls_color, "color": "#000",
                "fontWeight": "bold", "borderRadius": 4,
                "textAlign": "center",
            })

        table = dash_table.DataTable(
            id="flowseeker-table",
            columns=columns,
            data=data,
            style_table={"overflowX": "auto"},
            style_cell={
                "backgroundColor": "transparent", "color": C["text"],
                "border": f"1px solid {C['grid']}", "padding": "6px 10px",
                "fontFamily": "SF Mono, Fira Code, monospace", "fontSize": 12,
                "textAlign": "center",
            },
            style_header={
                "backgroundColor": C["header_bg"], "color": C["neon_cyan"],
                "fontWeight": "bold", "border": f"1px solid {C['border']}",
                "padding": "8px 10px",
            },
            style_data_conditional=style_data_conditional,
            page_size=50,
            sort_action="native",
        )

        return table, f"{count} prints"

    # ------------------------------------------------------------------
    # TOXICITY callbacks
    # ------------------------------------------------------------------

    @app.callback(
        Output("toxicity-vpin-series", "figure"),
        Output("toxicity-vpin-gauge", "figure"),
        Output("toxicity-fragility-gauge", "figure"),
        Output("toxicity-qi-bars", "figure"),
        Output("toxicity-qi-zscore", "figure"),
        Output("toxicity-alert-banner", "style"),
        Input("dash-interval", "n_intervals"),
    )
    def update_toxicity(n_intervals):
        # VPIN time series
        vpin_rows = _safe_query(
            """
            SELECT timestamp, vpin_value, qi_zscore
            FROM vpin_buckets
            ORDER BY timestamp DESC
            LIMIT 200
            """
        )

        if not vpin_rows:
            empty = _empty_figure("VPIN Time Series")
            gauge_empty = _empty_figure("VPIN CDF")
            frag_empty = _empty_figure("Market Fragility")
            qi_empty = _empty_figure("Quote Imbalance")
            zscore_empty = _empty_figure("QI Z-Score")
            return empty, gauge_empty, frag_empty, qi_empty, zscore_empty, {"display": "none"}

        vdf = pd.DataFrame(vpin_rows)
        vdf = vdf.sort_values("timestamp")

        # VPIN CDF value (latest)
        vpin_cdf = float(vdf["vpin_value"].iloc[-1]) if "vpin_value" in vdf.columns else 0
        qi_zscore = float(vdf["qi_zscore"].iloc[-1]) if "qi_zscore" in vdf.columns else 0

        # Market Fragility Score (composite)
        fragility = min(100, max(0, int(vpin_cdf * 60 + max(0, qi_zscore) * 20)))

        # --- VPIN time series ---
        fig_vpin = go.Figure()
        fig_vpin.add_trace(go.Scatter(
            x=vdf["timestamp"], y=vdf["vpin_value"],
            mode="lines", name="VPIN",
            line=dict(color=C["neon_cyan"], width=2),
            fill="tozeroy", fillcolor="rgba(0,229,255,0.08)",
        ))
        fig_vpin.add_hline(y=0.5, line_dash="dash", line_color=C["neon_yellow"],
                           annotation_text="Threshold", annotation_position="top left")
        fig_vpin.update_layout(
            title=dict(text="VPIN (Rolling)", font=dict(color=C["text"], size=14)),
            xaxis_title="Time", yaxis_title="VPIN",
            template=TEMPLATE, height=260,
        )
        _merge_layout(fig_vpin)

        # --- VPIN CDF gauge ---
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=round(vpin_cdf * 100, 1),
            number={"suffix": "%", "font": {"color": C["text"], "size": 28}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": C["text_muted"]},
                "bar": {"color": C["neon_cyan"]},
                "bgcolor": C["bg_card"],
                "bordercolor": C["border"],
                "steps": [
                    {"range": [0, 50], "color": "rgba(63,185,80,0.25)"},
                    {"range": [50, 75], "color": "rgba(255,213,79,0.25)"},
                    {"range": [75, 100], "color": "rgba(248,81,73,0.25)"},
                ],
                "threshold": {
                    "line": {"color": C["neon_red"], "width": 3},
                    "thickness": 0.75, "value": 50,
                },
            },
            title=dict(text="VPIN CDF", font=dict(color=C["text_muted"], size=12)),
        ))
        fig_gauge.update_layout(
            paper_bgcolor=C["bg"], font=dict(color=C["text"]),
            height=220, margin=dict(t=40, b=10, l=20, r=20),
        )

        # --- Fragility gauge ---
        fig_frag = go.Figure(go.Indicator(
            mode="gauge+number",
            value=fragility,
            number={"font": {"color": C["text"], "size": 28}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": C["text_muted"]},
                "bar": {"color": C["neon_red"] if fragility > 60 else C["neon_orange"]},
                "bgcolor": C["bg_card"],
                "bordercolor": C["border"],
                "steps": [
                    {"range": [0, 40], "color": "rgba(63,185,80,0.2)"},
                    {"range": [40, 70], "color": "rgba(255,213,79,0.2)"},
                    {"range": [70, 100], "color": "rgba(248,81,73,0.2)"},
                ],
            },
            title=dict(text="Fragility Score", font=dict(color=C["text_muted"], size=12)),
        ))
        fig_frag.update_layout(
            paper_bgcolor=C["bg"], font=dict(color=C["text"]),
            height=220, margin=dict(t=40, b=10, l=20, r=20),
        )

        # --- Quote Imbalance bar chart ---
        lob_rows = _safe_query(
            """
            SELECT symbol, bid_size, ask_size
            FROM lob_snapshots
            ORDER BY timestamp DESC
            LIMIT 20
            """
        )
        if lob_rows:
            ldf = pd.DataFrame(lob_rows)
            symbols = ldf["symbol"].tolist()
            bid_sz = ldf["bid_size"].tolist()
            ask_sz = ldf["ask_size"].tolist()
        else:
            symbols, bid_sz, ask_sz = [], [], []

        fig_qi = go.Figure()
        fig_qi.add_trace(go.Bar(
            x=symbols, y=bid_sz, name="Bid Size",
            marker_color=C["neon_green"], opacity=0.85,
        ))
        fig_qi.add_trace(go.Bar(
            x=symbols, y=[-a for a in ask_sz], name="Ask Size",
            marker_color=C["neon_red"], opacity=0.85,
        ))
        fig_qi.update_layout(
            title=dict(text="Quote Imbalance", font=dict(color=C["text"], size=14)),
            barmode="relative", template=TEMPLATE, height=260,
            xaxis_title="Symbol", yaxis_title="Size",
        )
        _merge_layout(fig_qi)

        # --- QI Z-Score indicator ---
        fig_zscore = go.Figure(go.Indicator(
            mode="number+delta",
            value=round(qi_zscore, 2),
            number={"font": {"color": C["neon_yellow"] if abs(qi_zscore) > 1.5 else C["text"], "size": 32}},
            delta={"reference": 1.5, "relative": False,
                   "valueformat": ".2f", "increasing": {"color": C["neon_red"]},
                   "decreasing": {"color": C["neon_green"]}},
            title=dict(text="QI Z-Score", font=dict(color=C["text_muted"], size=12)),
        ))
        fig_zscore.update_layout(
            paper_bgcolor=C["bg"], font=dict(color=C["text"]),
            height=260, margin=dict(t=40, b=10),
        )

        # Alert banner visibility
        alert_style = {"display": "none"}
        if vpin_cdf > 0.5 and qi_zscore > 1.5:
            alert_style = {
                "display": "block",
                "backgroundColor": C["danger"],
                "padding": "10px 16px",
                "borderRadius": 6,
                "marginBottom": 12,
                "textAlign": "center",
            }

        return fig_vpin, fig_gauge, fig_frag, fig_qi, fig_zscore, alert_style

    # ------------------------------------------------------------------
    # VOL SURFACE callbacks
    # ------------------------------------------------------------------

    @app.callback(
        Output("vol-surface-3d", "figure"),
        Output("vol-surface-atm", "figure"),
        Input("dash-interval", "n_intervals"),
    )
    def update_vol_surface(n_intervals):
        rows = _safe_query(
            """
            SELECT strike, expiry, iv, moneyness, tte
            FROM iv_surface
            ORDER BY tte, strike
            LIMIT 1000
            """
        )

        if not rows:
            return _empty_figure("IV Surface (3D)"), _empty_figure("ATM Term Structure")

        df = pd.DataFrame(rows)

        try:
            pivot_iv = df.pivot_table(index="moneyness", columns="tte", values="iv", aggfunc="mean")
            x = pivot_iv.columns.tolist()  # TTE
            y = pivot_iv.index.tolist()    # moneyness
            z = pivot_iv.values.tolist()
        except Exception:
            return _empty_figure("IV Surface (3D)"), _empty_figure("ATM Term Structure")

        # --- 3D Surface ---
        fig_3d = go.Figure()

        fig_3d.add_trace(go.Surface(
            x=x, y=y, z=z,
            colorscale="Viridis",
            colorbar=dict(title="IV", thickness=15),
            opacity=0.85,
            hovertemplate="TTE: %{x:.3f}<br>Moneyness: %{y:.4f}<br>IV: %{z:.4f}<extra></extra>",
        ))

        # SABR wireframe overlay (stub — would come from SABR fit)
        sabr_rows = _safe_query("SELECT tte, moneyness, iv_sabr FROM sabr_surface LIMIT 500")
        if sabr_rows:
            sdf = pd.DataFrame(sabr_rows)
            try:
                sabr_pivot = sdf.pivot_table(index="moneyness", columns="tte", values="iv_sabr", aggfunc="mean")
                fig_3d.add_trace(go.Surface(
                    x=sabr_pivot.columns.tolist(),
                    y=sabr_pivot.index.tolist(),
                    z=sabr_pivot.values.tolist(),
                    colorscale="Plasma",
                    opacity=0.35,
                    showscale=False,
                    name="SABR Fit",
                ))
            except Exception:
                pass

        fig_3d.update_layout(
            title=dict(text="IV Surface (3D)", font=dict(color=C["text"], size=16)),
            scene=dict(
                xaxis_title="TTE", yaxis_title="K/S", zaxis_title="IV",
                bgcolor=C["bg_card"],
                xaxis=dict(gridcolor=C["grid"], color=C["text_muted"]),
                yaxis=dict(gridcolor=C["grid"], color=C["text_muted"]),
                zaxis=dict(gridcolor=C["grid"], color=C["text_muted"]),
            ),
            template=TEMPLATE,
            height=520,
            paper_bgcolor=C["bg"],
            font=dict(color=C["text"]),
        )

        # --- ATM Term Structure (2D) ---
        atm_rows = _safe_query(
            """
            SELECT tte, iv
            FROM iv_surface
            WHERE ABS(moneyness - 1.0) < 0.02
            ORDER BY tte
            """
        )
        if atm_rows:
            adf = pd.DataFrame(atm_rows)
            fig_atm = go.Figure(go.Scatter(
                x=adf["tte"], y=adf["iv"],
                mode="lines+markers", name="ATM IV",
                line=dict(color=C["neon_purple"], width=2),
                marker=dict(size=5, color=C["neon_purple"]),
                fill="tozeroy", fillcolor="rgba(191,90,242,0.08)",
            ))
        else:
            fig_atm = _empty_figure("ATM Term Structure")

        fig_atm.update_layout(
            title=dict(text="ATM Term Structure", font=dict(color=C["text"], size=14)),
            xaxis_title="TTE (years)", yaxis_title="ATM IV",
            template=TEMPLATE, height=260,
        )
        _merge_layout(fig_atm)

        return fig_3d, fig_atm

    # ------------------------------------------------------------------
    # TRINITY callbacks
    # ------------------------------------------------------------------

    @app.callback(
        Output("trinity-alignment-gauge", "figure"),
        Output("trinity-price-chart", "figure"),
        Output("trinity-node-lifecycle", "figure"),
        Input("dash-interval", "n_intervals"),
    )
    def update_trinity(n_intervals):
        # Zero-gamma levels per ticker
        zg_rows = _safe_query(
            """
            SELECT symbol, zero_gamma_level, spot
            FROM trinity_levels
            WHERE symbol IN ('SPY','QQQ','SPX')
            ORDER BY symbol
            """
        )

        if not zg_rows:
            return (
                _empty_figure("Alignment Score"),
                _empty_figure("Zero-Gamma Levels"),
                _empty_figure("Node Lifecycle"),
            )

        zdf = pd.DataFrame(zg_rows)

        # Alignment score (stub — would compute overlap)
        alignment = _compute_trinity_alignment(zdf)

        # --- Alignment Gauge ---
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=alignment,
            number={"font": {"color": C["text"], "size": 28}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": C["text_muted"]},
                "bar": {"color": C["neon_green"] if alignment > 60 else C["neon_yellow"]},
                "bgcolor": C["bg_card"],
                "bordercolor": C["border"],
                "steps": [
                    {"range": [0, 33], "color": "rgba(248,81,73,0.2)"},
                    {"range": [33, 66], "color": "rgba(255,213,79,0.2)"},
                    {"range": [66, 100], "color": "rgba(63,185,80,0.2)"},
                ],
            },
            title=dict(text="Trinity Alignment", font=dict(color=C["text_muted"], size=12)),
        ))
        fig_gauge.update_layout(
            paper_bgcolor=C["bg"], font=dict(color=C["text"]),
            height=240, margin=dict(t=40, b=10, l=20, r=20),
        )

        # --- Price chart with zero-gamma levels ---
        price_rows = _safe_query(
            """
            SELECT timestamp, symbol, last
            FROM ticks
            WHERE symbol IN ('SPY','QQQ')
            ORDER BY timestamp DESC
            LIMIT 500
            """
        )
        fig_price = go.Figure()

        if price_rows:
            pdf = pd.DataFrame(price_rows)
            pdf = pdf.sort_values("timestamp")
            for sym, color in [("SPY", C["neon_cyan"]), ("QQQ", C["neon_orange"])]:
                sub = pdf[pdf["symbol"] == sym]
                if not sub.empty:
                    fig_price.add_trace(go.Scatter(
                        x=sub["timestamp"], y=sub["last"],
                        mode="lines", name=sym,
                        line=dict(color=color, width=1.5),
                    ))

        # Zero-gamma horizontal lines
        line_colors = {"SPY": C["neon_cyan"], "QQQ": C["neon_orange"], "SPX": C["neon_purple"]}
        for _, row in zdf.iterrows():
            sym = row.get("symbol", "")
            zg = row.get("zero_gamma_level", 0)
            if zg:
                fig_price.add_hline(
                    y=float(zg), line_dash="dash",
                    line_color=line_colors.get(sym, C["text_muted"]),
                    annotation_text=f"{sym} γ=0: {zg:.2f}",
                    annotation_position="top left",
                    annotation_font_color=line_colors.get(sym, C["text_muted"]),
                )

        fig_price.update_layout(
            title=dict(text="Zero-Gamma Levels", font=dict(color=C["text"], size=14)),
            xaxis_title="Time", yaxis_title="Price",
            template=TEMPLATE, height=240,
        )
        _merge_layout(fig_price)

        # --- Node Lifecycle ---
        node_rows = _safe_query(
            """
            SELECT strike, gex, structural_weight, state, expiry
            FROM node_lifecycle
            ORDER BY gex DESC
            LIMIT 100
            """
        )
        fig_nodes = go.Figure()

        if node_rows:
            ndf = pd.DataFrame(node_rows)
            state_colors = {
                "active": C["neon_green"],
                "decaying": C["neon_yellow"],
                "expired": C["regular"],
                "emerging": C["neon_cyan"],
            }
            for state, color in state_colors.items():
                sub = ndf[ndf["state"] == state]
                if sub.empty:
                    continue
                fig_nodes.add_trace(go.Scatter(
                    x=sub["strike"], y=sub["expiry"],
                    mode="markers", name=state.capitalize(),
                    marker=dict(
                        size=sub["gex"].abs() / sub["gex"].abs().max() * 40 + 4
                        if sub["gex"].abs().max() > 0 else 8,
                        color=color,
                        opacity=sub.get("structural_weight", pd.Series([0.5] * len(sub))).clip(0.2, 1),
                        line=dict(color="#fff", width=0.5),
                    ),
                    hovertemplate=(
                        "Strike: %{x}<br>Expiry: %{y}<br>"
                        "GEX: %{marker.size:.0f}<br>State: " + state + "<extra></extra>"
                    ),
                ))

        fig_nodes.update_layout(
            title=dict(text="Node Lifecycle", font=dict(color=C["text"], size=14)),
            xaxis_title="Strike", yaxis_title="Expiry",
            template=TEMPLATE, height=340,
        )
        _merge_layout(fig_nodes)

        return fig_gauge, fig_price, fig_nodes


# ===========================================================================
# DETECTION HELPERS
# ===========================================================================

def _detect_king_nodes(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Algorithmically detect King Nodes (local GEX maxima per expiry)."""
    if df.empty or "gex" not in df.columns:
        return []
    nodes = []
    if "expiry" in df.columns:
        for exp, grp in df.groupby("expiry"):
            grp = grp.sort_values("strike")
            gex_vals = grp["gex"].values
            strikes = grp["strike"].values
            for i in range(1, len(gex_vals) - 1):
                if gex_vals[i] > gex_vals[i - 1] and gex_vals[i] > gex_vals[i + 1] and gex_vals[i] > 0:
                    nodes.append({
                        "strike": float(strikes[i]),
                        "expiry": str(exp),
                        "gex": float(gex_vals[i]),
                    })
    return nodes


def _detect_air_pockets(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Detect Air Pockets (zero-GEX or sign-change zones)."""
    if df.empty or "gex" not in df.columns:
        return []
    pockets = []
    if "expiry" in df.columns:
        for exp, grp in df.groupby("expiry"):
            grp = grp.sort_values("strike")
            strikes = grp["strike"].values
            gex_vals = grp["gex"].values
            for i in range(len(gex_vals)):
                if abs(gex_vals[i]) < 1e-6:
                    low = strikes[max(0, i - 1)]
                    high = strikes[min(len(strikes) - 1, i + 1)]
                    pockets.append({
                        "strike_low": float(low),
                        "strike_high": float(high),
                        "expiry_start": str(exp),
                        "expiry_end": str(exp),
                    })
    return pockets


def _compute_trinity_alignment(zdf: pd.DataFrame) -> int:
    """Compute Trinity Alignment Score (0-100) from zero-gamma levels."""
    if zdf.empty or "zero_gamma_level" not in zdf.columns:
        return 0
    levels = zdf["zero_gamma_level"].dropna().values
    if len(levels) < 2:
        return 0
    # Simple heuristic: inverse of coefficient of variation
    mean_l = np.mean(levels)
    std_l = np.std(levels)
    if mean_l == 0:
        return 0
    cv = std_l / abs(mean_l)
    score = max(0, min(100, int((1 - cv) * 100)))
    return score


def _build_king_nodes_table(nodes: List[Dict[str, Any]]) -> Any:
    """Build a small HTML table for King Nodes."""
    if HAS_DBC:
        return dbc.Table.from_dataframe(
            pd.DataFrame(nodes).head(20),
            striped=True, bordered=True, hover=True, size="sm",
            style={"color": C["text"]},
        )
    rows = [html.Tr([html.Th("Strike"), html.Th("Expiry"), html.Th("GEX")],
                    style={"backgroundColor": C["header_bg"], "color": C["neon_gold"]})]
    for n in nodes[:20]:
        rows.append(html.Tr([
            html.Td(f"{n['strike']:.1f}"),
            html.Td(str(n["expiry"])),
            html.Td(f"{n['gex']:,.0f}"),
        ], style={"borderBottom": f"1px solid {C['grid']}"}))
    return html.Table(rows, style={"width": "100%", "borderCollapse": "collapse"})


def _build_air_pockets_table(pockets: List[Dict[str, Any]]) -> Any:
    """Build a small HTML table for Air Pockets."""
    if HAS_DBC:
        return dbc.Table.from_dataframe(
            pd.DataFrame(pockets).head(20),
            striped=True, bordered=True, hover=True, size="sm",
            style={"color": C["text"]},
        )
    rows = [html.Tr([html.Th("Strike Low"), html.Th("Strike High"), html.Th("Expiry")],
                    style={"backgroundColor": C["header_bg"], "color": C["neon_purple"]})]
    for p in pockets[:20]:
        rows.append(html.Tr([
            html.Td(f"{p['strike_low']:.1f}"),
            html.Td(f"{p['strike_high']:.1f}"),
            html.Td(str(p["expiry_start"])),
        ], style={"borderBottom": f"1px solid {C['grid']}"}))
    return html.Table(rows, style={"width": "100%", "borderCollapse": "collapse"})


# ===========================================================================
# MAIN FACTORY
# ===========================================================================

def create_dash_app(fastapi_app, url_base_pathname: str = "/dashboard/") -> dash.Dash:
    """
    Create and mount a Dash app onto an existing FastAPI instance.

    Parameters
    ----------
    fastapi_app : fastapi.FastAPI
        The FastAPI application to mount onto.
    url_base_pathname : str
        Base URL path for the dashboard (default: "/dashboard/").

    Returns
    -------
    dash.Dash
        The configured Dash application instance.
    """
    # External stylesheets
    external_stylesheets = []
    if HAS_DBC:
        external_stylesheets.append(dbc.themes.DARKLY)

    # Create Dash app
    dash_app = dash.Dash(
        __name__,
        server=fastapi_app,
        url_base_pathname=url_base_pathname,
        external_stylesheets=external_stylesheets,
        suppress_callback_exceptions=True,
        update_title=None,
        meta_tags=[
            {"name": "viewport", "content": "width=device-width, initial-scale=1"},
            {"name": "theme-color", "content": C["bg"]},
        ],
    )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    tabs_component = dbc.Tabs if HAS_DBC else dcc.Tabs

    tab_definitions = [
        {"label": "✦ Heatseeker", "value": "tab-heatseeker", "color": C["neon_cyan"]},
        {"label": "⚡ Flowseeker", "value": "tab-flowseeker", "color": C["neon_orange"]},
        {"label": "☢ Toxicity", "value": "tab-toxicity", "color": C["neon_red"]},
        {"label": "◈ Vol Surface", "value": "tab-vol-surface", "color": C["neon_purple"]},
        {"label": "△ Trinity", "value": "tab-trinity", "color": C["neon_green"]},
    ]

    if HAS_DBC:
        tabs = dbc.Tabs(
            [
                dbc.Tab(
                    _build_heatseeker_tab(),
                    tab_id="tab-heatseeker",
                    label="✦ Heatseeker",
                    label_style={"color": C["neon_cyan"], "fontWeight": "bold"},
                    active_label_style={"color": C["neon_cyan"], "borderBottom": f"2px solid {C['neon_cyan']}"},
                ),
                dbc.Tab(
                    _build_flowseeker_tab(),
                    tab_id="tab-flowseeker",
                    label="⚡ Flowseeker",
                    label_style={"color": C["neon_orange"], "fontWeight": "bold"},
                    active_label_style={"color": C["neon_orange"], "borderBottom": f"2px solid {C['neon_orange']}"},
                ),
                dbc.Tab(
                    _build_toxicity_tab(),
                    tab_id="tab-toxicity",
                    label="☢ Toxicity",
                    label_style={"color": C["neon_red"], "fontWeight": "bold"},
                    active_label_style={"color": C["neon_red"], "borderBottom": f"2px solid {C['neon_red']}"},
                ),
                dbc.Tab(
                    _build_vol_surface_tab(),
                    tab_id="tab-vol-surface",
                    label="◈ Vol Surface",
                    label_style={"color": C["neon_purple"], "fontWeight": "bold"},
                    active_label_style={"color": C["neon_purple"], "borderBottom": f"2px solid {C['neon_purple']}"},
                ),
                dbc.Tab(
                    _build_trinity_tab(),
                    tab_id="tab-trinity",
                    label="△ Trinity",
                    label_style={"color": C["neon_green"], "fontWeight": "bold"},
                    active_label_style={"color": C["neon_green"], "borderBottom": f"2px solid {C['neon_green']}"},
                ),
            ],
            id="dash-tabs",
            active_tab="tab-heatseeker",
            style={"marginBottom": 16},
        )
    else:
        tabs = dcc.Tabs(
            id="dash-tabs",
            value="tab-heatseeker",
            children=[
                dcc.Tab(
                    label="✦ Heatseeker",
                    value="tab-heatseeker",
                    children=[_build_heatseeker_tab()],
                    style={"backgroundColor": C["bg_card"], "color": C["text_muted"],
                           "border": f"1px solid {C['border']}", "padding": "10px 16px"},
                    selected_style={"backgroundColor": C["bg_card"], "color": C["neon_cyan"],
                                    "borderTop": f"2px solid {C['neon_cyan']}",
                                    "borderBottom": "none", "padding": "10px 16px"},
                ),
                dcc.Tab(
                    label="⚡ Flowseeker",
                    value="tab-flowseeker",
                    children=[_build_flowseeker_tab()],
                    style={"backgroundColor": C["bg_card"], "color": C["text_muted"],
                           "border": f"1px solid {C['border']}", "padding": "10px 16px"},
                    selected_style={"backgroundColor": C["bg_card"], "color": C["neon_orange"],
                                    "borderTop": f"2px solid {C['neon_orange']}",
                                    "borderBottom": "none", "padding": "10px 16px"},
                ),
                dcc.Tab(
                    label="☢ Toxicity",
                    value="tab-toxicity",
                    children=[_build_toxicity_tab()],
                    style={"backgroundColor": C["bg_card"], "color": C["text_muted"],
                           "border": f"1px solid {C['border']}", "padding": "10px 16px"},
                    selected_style={"backgroundColor": C["bg_card"], "color": C["neon_red"],
                                    "borderTop": f"2px solid {C['neon_red']}",
                                    "borderBottom": "none", "padding": "10px 16px"},
                ),
                dcc.Tab(
                    label="◈ Vol Surface",
                    value="tab-vol-surface",
                    children=[_build_vol_surface_tab()],
                    style={"backgroundColor": C["bg_card"], "color": C["text_muted"],
                           "border": f"1px solid {C['border']}", "padding": "10px 16px"},
                    selected_style={"backgroundColor": C["bg_card"], "color": C["neon_purple"],
                                    "borderTop": f"2px solid {C['neon_purple']}",
                                    "borderBottom": "none", "padding": "10px 16px"},
                ),
                dcc.Tab(
                    label="△ Trinity",
                    value="tab-trinity",
                    children=[_build_trinity_tab()],
                    style={"backgroundColor": C["bg_card"], "color": C["text_muted"],
                           "border": f"1px solid {C['border']}", "padding": "10px 16px"},
                    selected_style={"backgroundColor": C["bg_card"], "color": C["neon_green"],
                                    "borderTop": f"2px solid {C['neon_green']}",
                                    "borderBottom": "none", "padding": "10px 16px"},
                ),
            ],
            style={"marginBottom": 16},
        )

    dash_app.layout = html.Div(
        style={
            "backgroundColor": C["bg"],
            "minHeight": "100vh",
            "fontFamily": "SF Mono, Fira Code, 'Courier New', monospace",
            "color": C["text"],
            "margin": 0,
            "padding": 0,
        },
        children=[
            # Client-side state store
            dcc.Store(id="dash-store", data={"initialized": True}),

            # Auto-refresh interval (2 seconds)
            dcc.Interval(id="dash-interval", interval=2000, n_intervals=0),

            # Header bar
            html.Div(
                style={
                    "backgroundColor": C["header_bg"],
                    "borderBottom": f"1px solid {C['border']}",
                    "padding": "12px 24px",
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "space-between",
                },
                children=[
                    html.Div(
                        children=[
                            html.Span("◆ CONFLUENCE DECODER", style={
                                "color": C["neon_cyan"], "fontSize": 18,
                                "fontWeight": "bold", "letterSpacing": 3,
                            }),
                            html.Span("  —  Institutional Options Analytics", style={
                                "color": C["text_muted"], "fontSize": 12,
                                "marginLeft": 12,
                            }),
                        ]
                    ),
                    html.Div(
                        children=[
                            html.Span(id="dash-status-indicator", children="● LIVE", style={
                                "color": C["neon_green"], "fontSize": 12,
                                "fontWeight": "bold", "letterSpacing": 1,
                            }),
                            html.Span(id="dash-clock", children="", style={
                                "color": C["text_muted"], "fontSize": 12,
                                "marginLeft": 16,
                            }),
                        ]
                    ),
                ],
            ),

            # Main content
            html.Div(
                style={"padding": "16px 24px"},
                children=[
                    tabs,
                ],
            ),

            # Footer
            html.Div(
                style={
                    "backgroundColor": C["header_bg"],
                    "borderTop": f"1px solid {C['border']}",
                    "padding": "8px 24px",
                    "textAlign": "center",
                },
                children=html.Span(
                    "Confluence Decoder v1.0  ·  DuckDB + FastAPI + Dash  ·  © 2026",
                    style={"color": C["text_muted"], "fontSize": 11},
                ),
            ),
        ],
    )

    # ------------------------------------------------------------------
    # Register all callbacks
    # ------------------------------------------------------------------
    _register_callbacks(dash_app)

    logger.info(
        "Dash app created and mounted at %s (dbc=%s, wsgi=%s)",
        url_base_pathname, HAS_DBC, HAS_WSGI,
    )

    return dash_app
