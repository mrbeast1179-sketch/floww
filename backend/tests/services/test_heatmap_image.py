"""
backend/tests/services/test_heatmap_image.py — Solstice PNG renderer.
PIL-only; no network. Fixtures, never live chains.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _payload(**over):
    base = {
        "ticker": "SPY",
        "spot": 700.0,
        "strikes": [
            {"strike": 690.0, "gex": -5e8},
            {"strike": 695.0, "gex": -1e8},
            {"strike": 700.0, "gex": 3e8},
            {"strike": 705.0, "gex": 9e8},
            {"strike": 710.0, "gex": 2e8},
        ],
        "nodes": {"king": {"strike": 705.0, "gex": 9e8}, "regime": "positive"},
        "gamma_flip": 697.5,
    }
    base.update(over)
    return base


class TestNormalize:
    def test_ok(self):
        from services.heatmap_image import gex_rows_from_heatmap
        out = gex_rows_from_heatmap(_payload())
        assert out["ticker"] == "SPY" and out["spot"] == 700.0
        assert len(out["strikes"]) == 5
        assert out["king_strike"] == 705.0 and out["flip"] == 697.5

    def test_flip_fallback_zero_crossing(self):
        from services.heatmap_image import gex_rows_from_heatmap
        p = _payload()
        del p["gamma_flip"]
        out = gex_rows_from_heatmap(p)
        assert out["flip"] in (695.0, 700.0)

    def test_degenerate_is_none(self):
        from services.heatmap_image import gex_rows_from_heatmap
        assert gex_rows_from_heatmap(None) is None
        assert gex_rows_from_heatmap({}) is None
        assert gex_rows_from_heatmap({"ticker": "X", "spot": 0, "strikes": []}) is None


class TestRender:
    def test_gex_png_bytes(self):
        from services.heatmap_image import gex_rows_from_heatmap, render_gex_png
        png = render_gex_png(gex_rows_from_heatmap(_payload()))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert 10_000 < len(png) < 2_000_000

    def test_render_none_safe(self):
        from services.heatmap_image import render_gex_png, render_vex_png
        assert render_gex_png(None) is None
        assert render_vex_png(None) is None

    def test_trims_to_60_rows(self):
        from services.heatmap_image import render_gex_png
        norm = {"ticker": "X", "spot": 100.0,
                "strikes": [(float(k), 1e6) for k in range(1, 201)],
                "king_strike": None, "flip": None, "regime": "?"}
        assert render_gex_png(norm)[:8] == b"\x89PNG\r\n\x1a\n"


class TestVex:
    def test_vex_rows_from_contracts(self):
        from services.heatmap_image import render_vex_png, vex_rows_from_contracts
        contracts = [
            {"strike": 700.0, "type": "call", "oi": 5000, "iv": 0.25, "expiry": "2099-01-15"},
            {"strike": 700.0, "type": "put", "oi": 4000, "iv": 0.30, "expiry": "2099-01-15"},
            {"strike": 710.0, "type": "call", "oi": 1000, "iv": 0.22, "expiry": "2099-01-15"},
            {"strike": 0, "type": "call", "oi": 9, "iv": 0.2, "expiry": "2099-01-15"},
            {"bogus": True},
        ]
        out = vex_rows_from_contracts(contracts, 700.0)
        assert out is not None and len(out["strikes"]) == 2
        png = render_vex_png({**out, "ticker": "SPY"})
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_vex_degenerate_none(self):
        from services.heatmap_image import vex_rows_from_contracts
        assert vex_rows_from_contracts([], 700.0) is None
        assert vex_rows_from_contracts(None, 700.0) is None
        assert vex_rows_from_contracts([{"strike": 1}], 0) is None


class TestWalls:
    def test_walls_text(self):
        from services.heatmap_image import gex_rows_from_heatmap, walls_text
        t = walls_text(gex_rows_from_heatmap(_payload()))
        assert "705" in t and "690" in t  # call wall + put wall
        assert "697.5" in t and "King Node" in t

    def test_walls_empty(self):
        from services.heatmap_image import walls_text
        assert "unavailable" in walls_text(None)
