"""
backend/tests/services/risk/test_sizer.py — Tests for Kelly sizer.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from backend.services.risk.sizer import KellySizer, SizerConfig, TradeRecord


def make_trade(pnl=100.0, ticker="SPY", entry=400.0, exit_price=401.0, qty=10):
    return TradeRecord(ticker=ticker, pnl=pnl, entry_price=entry, exit_price=exit_price, qty=qty)


class TestKellySizerInit:
    def test_default_config(self):
        sizer = KellySizer()
        assert sizer.config.kelly_fraction == 0.5

    def test_custom_config(self):
        sizer = KellySizer(config=SizerConfig(kelly_fraction=0.25))
        assert sizer.config.kelly_fraction == 0.25


class TestComputeSize:
    def test_returns_positive_shares(self):
        sizer = KellySizer()
        shares = sizer.compute_size("SPY", 400.0, 10000.0)
        assert shares > 0

    def test_zero_when_daily_loss_lock(self):
        sizer = KellySizer()
        shares = sizer.compute_size("SPY", 400.0, 10000.0, daily_pnl_pct=-0.02)
        assert shares == 0

    def test_zero_when_price_zero(self):
        sizer = KellySizer()
        shares = sizer.compute_size("SPY", 0.0, 10000.0)
        assert shares == 0

    def test_respects_max_position_value(self):
        sizer = KellySizer(config=SizerConfig(max_position_value=1000.0))
        shares = sizer.compute_size("SPY", 400.0, 100000.0)
        assert shares * 400.0 <= 1000.0 * 1.01  # small tolerance for int rounding

    def test_respects_max_position_pct(self):
        sizer = KellySizer(config=SizerConfig(max_position_pct=0.05))
        shares = sizer.compute_size("SPY", 400.0, 10000.0)
        assert shares * 400.0 <= 10000.0 * 0.05 * 1.01


class TestKellyFraction:
    def test_default_kelly_with_no_history(self):
        sizer = KellySizer()
        kelly = sizer._compute_kelly_fraction([])
        assert kelly > 0

    def test_kelly_with_history(self):
        sizer = KellySizer()
        history = [
            make_trade(pnl=150.0),
            make_trade(pnl=200.0),
            make_trade(pnl=-100.0),
            make_trade(pnl=100.0),
            make_trade(pnl=-50.0),
        ] * 5  # 25 trades
        kelly = sizer._compute_kelly_fraction(history)
        assert kelly > 0
        assert kelly < 1.0

    def test_kelly_all_wins(self):
        sizer = KellySizer()
        history = [make_trade(pnl=100.0)] * 25
        kelly = sizer._compute_kelly_fraction(history)
        assert kelly == 0.05  # conservative default when no losses

    def test_kelly_all_losses(self):
        sizer = KellySizer()
        history = [make_trade(pnl=-100.0)] * 25
        kelly = sizer._compute_kelly_fraction(history)
        assert kelly == 0.0  # never negative


class TestAddTrade:
    def test_adds_to_history(self):
        sizer = KellySizer()
        sizer.add_trade(make_trade())
        stats = sizer.get_stats()
        assert stats["total_trades"] == 1

    def test_multiple_trades(self):
        sizer = KellySizer()
        for _ in range(10):
            sizer.add_trade(make_trade(pnl=100.0))
        for _ in range(5):
            sizer.add_trade(make_trade(pnl=-50.0))
        stats = sizer.get_stats()
        assert stats["total_trades"] == 15
        assert stats["win_count"] == 10
        assert stats["loss_count"] == 5


class TestGetStats:
    def test_empty_stats(self):
        sizer = KellySizer()
        stats = sizer.get_stats()
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0

    def test_stats_with_trades(self):
        sizer = KellySizer()
        sizer.add_trade(make_trade(pnl=200.0))
        sizer.add_trade(make_trade(pnl=-100.0))
        stats = sizer.get_stats()
        assert stats["total_trades"] == 2
        assert stats["win_count"] == 1
        assert stats["total_pnl"] == 100.0
