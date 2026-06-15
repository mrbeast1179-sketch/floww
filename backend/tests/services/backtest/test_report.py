"""
backend/tests/services/backtest/test_report.py

Unit tests for backtest/report.py — TradeRecord, BacktestResult, compute_metrics, summary_text.

Coverage:
    - TradeRecord defaults and fields
    - BacktestResult with zero trades
    - BacktestResult with mixed wins/losses
    - Sharpe ratio calculation (golden oracle)
    - Max drawdown calculation (golden oracle)
    - Hit rate, profit factor, win/loss ratio
    - Edge: all wins, all losses, single trade
    - Edge: empty equity curve, empty drawdown curve
    - Edge: zero initial capital
    - summary_text format
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


class TestTradeRecord:
    def test_defaults(self):
        from services.backtest.report import TradeRecord
        tr = TradeRecord()
        assert tr.entry_bar_idx == 0
        assert tr.exit_bar_idx == 0
        assert tr.side == ""
        assert tr.direction == ""
        assert tr.entry_price == 0.0
        assert tr.exit_price == 0.0
        assert tr.quantity == 0
        assert tr.pnl == 0.0
        assert tr.commission == 0.0
        assert tr.slippage == 0.0
        assert tr.net_pnl == 0.0

    def test_net_pnl_independent(self):
        """net_pnl should be set independently (pnl - commission - slippage)."""
        from services.backtest.report import TradeRecord
        tr = TradeRecord(pnl=100.0, commission=2.0, slippage=1.0, net_pnl=97.0)
        assert tr.net_pnl == 97.0


class TestBacktestResultNoTrades:
    """compute_metrics with zero trades returns all zeros."""

    def test_zero_trades_metrics(self):
        from services.backtest.report import BacktestResult
        r = BacktestResult(
            ticker="SPY",
            start_date="2024-01-01",
            end_date="2024-06-01",
            initial_capital=100_000.0,
        )
        m = r.compute_metrics()
        assert m["n_trades"] == 0.0
        assert m["sharpe"] == 0.0
        assert m["max_drawdown"] == 0.0
        assert m["hit_rate"] == 0.0
        assert m["profit_factor"] == 0.0
        assert m["total_pnl"] == 0.0
        assert m["final_equity"] == 100_000.0

    def test_zero_trades_stored_in_metrics(self):
        from services.backtest.report import BacktestResult
        r = BacktestResult(initial_capital=50_000.0)
        r.compute_metrics()
        assert r.metrics["n_trades"] == 0.0


class TestBacktestResultWithTrades:
    """BacktestResult with known trades produces correct computed metrics."""

    @pytest.fixture
    def simple_result(self):
        """A result with 5 trades: 3 wins, 2 losses. Known PnLs."""
        from services.backtest.report import BacktestResult, TradeRecord
        trades = [
            TradeRecord(pnl=100.0, commission=2.0, slippage=1.0, net_pnl=97.0),
            TradeRecord(pnl=150.0, commission=2.0, slippage=1.0, net_pnl=147.0),
            TradeRecord(pnl=-50.0, commission=2.0, slippage=1.0, net_pnl=-53.0),
            TradeRecord(pnl=200.0, commission=2.0, slippage=1.0, net_pnl=197.0),
            TradeRecord(pnl=-30.0, commission=2.0, slippage=1.0, net_pnl=-33.0),
        ]
        r = BacktestResult(
            ticker="SPY",
            start_date="2024-01-01",
            end_date="2024-06-01",
            initial_capital=100_000.0,
            trades=trades,
            equity_curve=[100_000.0, 100_097.0, 100_244.0, 100_191.0, 100_388.0, 100_355.0],
            drawdown_curve=[0.0, 0.0, 0.0, -53.0, 0.0, 0.0],
            bar_returns=[0.001, 0.0015, -0.0005, 0.002, -0.0003],
            total_bars=100,
        )
        return r

    def test_n_trades(self, simple_result):
        m = simple_result.compute_metrics()
        assert m["n_trades"] == 5.0

    def test_total_pnl(self, simple_result):
        m = simple_result.compute_metrics()
        # 97 + 147 - 53 + 197 - 33 = 355
        assert m["total_pnl"] == pytest.approx(355.0)

    def test_avg_trade_pnl(self, simple_result):
        m = simple_result.compute_metrics()
        # 355 / 5 = 71
        assert m["avg_trade_pnl"] == pytest.approx(71.0)

    def test_hit_rate(self, simple_result):
        m = simple_result.compute_metrics()
        # 3 wins / 5 = 0.6
        assert m["hit_rate"] == pytest.approx(0.6)

    def test_avg_win(self, simple_result):
        m = simple_result.compute_metrics()
        # Wins: 97, 147, 197 => avg = 441/3 = 147
        assert m["avg_win"] == pytest.approx(147.0)

    def test_avg_loss(self, simple_result):
        m = simple_result.compute_metrics()
        # Losses: -53, -33 => avg = -86/2 = -43
        assert m["avg_loss"] == pytest.approx(-43.0)

    def test_win_loss_ratio(self, simple_result):
        m = simple_result.compute_metrics()
        # avg_win / |avg_loss| = 147 / 43 ≈ 3.4186
        assert m["win_loss_ratio"] == pytest.approx(147.0 / 43.0, rel=1e-3)

    def test_profit_factor(self, simple_result):
        m = simple_result.compute_metrics()
        # gross_wins = 97 + 147 + 197 = 441
        # gross_losses = 53 + 33 = 86
        # pf = 441 / 86 ≈ 5.1279
        assert m["profit_factor"] == pytest.approx(441.0 / 86.0, rel=1e-3)

    def test_total_commission(self, simple_result):
        m = simple_result.compute_metrics()
        # 5 trades × $2 = $10
        assert m["total_commission"] == pytest.approx(10.0)

    def test_total_slippage(self, simple_result):
        m = simple_result.compute_metrics()
        # 5 trades × $1 = $5
        assert m["total_slippage"] == pytest.approx(5.0)

    def test_final_equity(self, simple_result):
        m = simple_result.compute_metrics()
        assert m["final_equity"] == pytest.approx(100_355.0)

    def test_net_return_pct(self, simple_result):
        m = simple_result.compute_metrics()
        # (100355 / 100000 - 1) * 100 = 0.355%
        assert m["net_return_pct"] == pytest.approx(0.355, rel=1e-3)


class TestBacktestResultSharpe:
    """Verify sharpe ratio independently."""

    def test_sharpe_known_returns(self):
        """Compute sharpe from known bar returns, compare with manual calc."""
        from services.backtest.report import BacktestResult, TradeRecord
        # Create returns with known statistics (avoiding sample noise)
        np.random.seed(42)
        daily_mean = 0.001
        daily_std = 0.02
        returns = np.random.normal(daily_mean, daily_std, size=252).tolist()

        r = BacktestResult(
            ticker="SPY",
            initial_capital=100_000.0,
            trades=[TradeRecord(net_pnl=100.0)],
            bar_returns=returns,
        )
        m = r.compute_metrics()
        # The actual sharpe from the sample should be close to theoretical
        # With 252 samples, the sample std deviates ~3% from population
        expected_sharpe = daily_mean / daily_std * np.sqrt(252)
        assert m["sharpe"] == pytest.approx(expected_sharpe, rel=0.1)
        # More importantly: verify it computes *some* non-trivial sharpe
        assert m["sharpe"] > 0.5

    def test_sharpe_zero_std_returns(self):
        """Sharpe should be 0 when all returns are identical (std=0)."""
        from services.backtest.report import BacktestResult, TradeRecord
        r = BacktestResult(
            ticker="SPY",
            initial_capital=100_000.0,
            trades=[TradeRecord(net_pnl=0.0)],
            bar_returns=[0.001] * 50,
        )
        m = r.compute_metrics()
        assert m["sharpe"] == 0.0

    def test_sharpe_no_bar_returns(self):
        from services.backtest.report import BacktestResult, TradeRecord
        r = BacktestResult(
            initial_capital=100_000.0,
            trades=[TradeRecord(net_pnl=0.0)],
            bar_returns=[],
        )
        m = r.compute_metrics()
        assert m["sharpe"] == 0.0


class TestBacktestResultMaxDrawdown:
    """Verify max drawdown calculation independently."""

    def test_max_drawdown_known(self):
        from services.backtest.report import BacktestResult, TradeRecord
        equity = [100_000.0, 110_000.0, 105_000.0, 115_000.0, 90_000.0, 95_000.0]
        # Drawdown curve: 0, 0, -5000, 0, -25000, -20000
        # Peak = 115000, min drawdown = -25000
        dd = [0.0, 0.0, -5000.0, 0.0, -25_000.0, -20_000.0]
        r = BacktestResult(
            initial_capital=100_000.0,
            trades=[TradeRecord(net_pnl=0.0)],
            equity_curve=equity,
            drawdown_curve=dd,
        )
        m = r.compute_metrics()
        assert m["max_drawdown"] == pytest.approx(-25_000.0)
        assert m["max_drawdown_pct"] == pytest.approx(-25_000.0 / 115_000.0 * 100.0, rel=1e-6)

    def test_max_drawdown_empty(self):
        from services.backtest.report import BacktestResult, TradeRecord
        r = BacktestResult(
            initial_capital=100_000.0,
            trades=[TradeRecord(net_pnl=0.0)],
            drawdown_curve=[],
        )
        m = r.compute_metrics()
        assert m["max_drawdown"] == 0.0
        assert m["max_drawdown_pct"] == 0.0


class TestBacktestResultEdgeCases:
    def test_all_wins_infinite_wl_ratio(self):
        """When all trades are wins, win_loss_ratio = inf (no losses)."""
        from services.backtest.report import BacktestResult, TradeRecord
        trades = [
            TradeRecord(net_pnl=100.0),
            TradeRecord(net_pnl=200.0),
            TradeRecord(net_pnl=50.0),
        ]
        r = BacktestResult(initial_capital=100_000.0, trades=trades)
        m = r.compute_metrics()
        assert m["win_loss_ratio"] == float("inf")
        assert m["profit_factor"] == float("inf")
        assert m["hit_rate"] == 1.0
        assert m["avg_loss"] == 0.0

    def test_all_losses_zero_wl_and_pf(self):
        """When all trades are losses with no wins."""
        from services.backtest.report import BacktestResult, TradeRecord
        trades = [
            TradeRecord(net_pnl=-100.0),
            TradeRecord(net_pnl=-50.0),
        ]
        r = BacktestResult(initial_capital=100_000.0, trades=trades)
        m = r.compute_metrics()
        assert m["hit_rate"] == 0.0
        assert m["win_loss_ratio"] == 0.0
        assert m["profit_factor"] == 0.0
        assert m["avg_win"] == 0.0
        assert m["avg_loss"] == pytest.approx(-75.0)

    def test_single_trade(self):
        """One trade should compute all metrics without error."""
        from services.backtest.report import BacktestResult, TradeRecord
        r = BacktestResult(
            initial_capital=100_000.0,
            trades=[TradeRecord(net_pnl=500.0, commission=2.0, slippage=1.0, pnl=503.0)],
            equity_curve=[100_000.0, 100_500.0],
            drawdown_curve=[0.0, 0.0],
        )
        m = r.compute_metrics()
        assert m["n_trades"] == 1.0
        assert m["hit_rate"] == 1.0
        assert m["total_pnl"] == pytest.approx(500.0)

    def test_zero_initial_capital(self):
        """Zero initial capital shouldn't crash net_return_pct."""
        from services.backtest.report import BacktestResult, TradeRecord
        r = BacktestResult(
            initial_capital=0.0,
            trades=[TradeRecord(net_pnl=100.0)],
            equity_curve=[0.0, 100.0],
        )
        m = r.compute_metrics()
        assert m["net_return_pct"] == 0.0


class TestBacktestResultSummaryText:
    def test_summary_text_format(self):
        from services.backtest.report import BacktestResult, TradeRecord
        trades = [
            TradeRecord(net_pnl=100.0),
            TradeRecord(net_pnl=-50.0),
        ]
        r = BacktestResult(
            ticker="SPY",
            start_date="2024-01-01",
            end_date="2024-06-01",
            initial_capital=100_000.0,
            trades=trades,
            equity_curve=[100_000.0, 100_100.0, 100_050.0],
            drawdown_curve=[0.0, 0.0, -50.0],
            total_bars=100,
        )
        text = r.summary_text()
        assert "=== Backtest Report: SPY ===" in text
        assert "Period: 2024-01-01 -> 2024-06-01" in text
        assert "Bars: 100" in text
        assert "Initial Capital:" in text
        assert "Hit Rate:" in text
        assert "Sharpe" in text

    def test_summary_text_without_compute(self):
        """summary_text auto-computes metrics if not done."""
        from services.backtest.report import BacktestResult, TradeRecord
        r = BacktestResult(
            ticker="QQQ",
            initial_capital=100_000.0,
            trades=[TradeRecord(net_pnl=200.0)],
        )
        # Don't call compute_metrics first
        text = r.summary_text()
        assert "QQQ" in text
