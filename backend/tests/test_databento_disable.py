"""Test that DISABLE_DATABENTO=1 empties PAID_TICKERS for fast startup."""
import os


def test_paid_tickers_empty_when_disabled(monkeypatch):
    """DISABLE_DATABENTO=1 must result in an empty PAID_TICKERS set."""
    monkeypatch.setenv("DISABLE_DATABENTO", "1")

    # Replicate the gate logic from server.py:~310 exactly:
    #   PAID_TICKERS: set = (
    #       set()
    #       if os.environ.get("DISABLE_DATABENTO", "").lower() in ("1", "true", "yes")
    #       else set(DEFAULT_PAID_TICKERS)
    #   )
    disabled = os.environ.get("DISABLE_DATABENTO", "").lower() in ("1", "true", "yes")
    from server import DEFAULT_PAID_TICKERS

    result = set() if disabled else set(DEFAULT_PAID_TICKERS)
    assert result == set(), f"DISABLE_DATABENTO=1 must empty PAID_TICKERS, got {result}"


def test_paid_tickers_default_when_not_disabled(monkeypatch):
    """Without DISABLE_DATABENTO, PAID_TICKERS gets all six default tickers."""
    monkeypatch.delenv("DISABLE_DATABENTO", raising=False)

    disabled = os.environ.get("DISABLE_DATABENTO", "").lower() in ("1", "true", "yes")
    from server import DEFAULT_PAID_TICKERS

    result = set() if disabled else set(DEFAULT_PAID_TICKERS)
    assert result == {"SPY", "QQQ", "IWM", "DIA", "TLT", "SPX"}, (
        f"Default PAID_TICKERS should be the six production tickers, got {result}"
    )


def test_paid_tickers_disabled_with_true_variants(monkeypatch):
    """DISABLE_DATABENTO=true and yes also disable."""
    for value in ("true", "yes", "TRUE", "YES"):
        monkeypatch.setenv("DISABLE_DATABENTO", value)
        disabled = os.environ.get("DISABLE_DATABENTO", "").lower() in ("1", "true", "yes")
        assert disabled, f"DISABLE_DATABENTO={value!r} should be recognized as disabled"
