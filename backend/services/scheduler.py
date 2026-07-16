"""
backend/services/scheduler.py

Rate Limiter & Scheduler.
Runs yoptions_fetcher and yfinance_fetcher every 60 seconds.
Ensures no overlapping executions with asyncio lock.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from datetime import UTC, datetime

from services.yfinance_fetcher import fetch_and_store, get_duckdb_conn

logger = logging.getLogger(__name__)

try:
    from services.yoptions_fetcher import fetch_all_chains
except ImportError as _yopt_err:
    # tenacity (or yoptions) not installed — disable options polling gracefully
    logger.warning(
        "yoptions_fetcher import failed (%s); options fetch will be skipped.", _yopt_err
    )
    import pandas as _pd
    def fetch_all_chains(*_args, **_kwargs):  # type: ignore[misc]
        return _pd.DataFrame()

DEFAULT_INTERVAL = 60  # seconds


class PollingScheduler:
    """Async scheduler that runs fetchers at a fixed interval.

    Features:
    - No overlapping executions (asyncio lock).
    - Graceful shutdown on SIGINT/SIGTERM.
    - Logs start/end times for monitoring.
    """

    def __init__(self, interval: int = DEFAULT_INTERVAL):
        self._interval = interval
        self._lock = asyncio.Lock()
        self._running = False
        self._task: asyncio.Task | None = None
        self._execution_count = 0
        self._conn = get_duckdb_conn()

    async def start(self):
        """Start the scheduler loop."""
        self._running = True
        logger.info(f"Scheduler started (interval={self._interval}s)")
        try:
            while self._running:
                start_time = datetime.now(UTC)
                logger.info(
                    f"Execution #{self._execution_count + 1} started at "
                    f"{start_time.isoformat()}"
                )

                # Use lock to prevent overlapping executions
                if self._lock.locked():
                    logger.warning("Previous execution still running, skipping this cycle")
                else:
                    async with self._lock:
                        await self._run_fetchers()

                end_time = datetime.now(UTC)
                duration = (end_time - start_time).total_seconds()
                self._execution_count += 1
                logger.info(
                    f"Execution #{self._execution_count} completed in {duration:.2f}s"
                )

                # Sleep for remaining interval
                sleep_time = max(0, self._interval - duration)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
        finally:
            logger.info(
                f"Scheduler stopped. Total executions: {self._execution_count}"
            )

    async def _run_fetchers(self):
        """Run all fetchers concurrently, including periodic news polling.

        News polling fires every 1440 ticks (24h at default 60s interval)
        via ``_poll_news_for_universe``. The cadence check uses
        ``_execution_count`` which is incremented by ``start()`` AFTER
        each cycle — so count==0 on first tick (news fires immediately),
        count==1440 on the 1441st tick (news fires again), etc.
        """
        try:
            options_task = asyncio.create_task(self._fetch_options())
            underlying_task = asyncio.create_task(self._fetch_underlying())

            # 1440 ticks * 60s interval = 86400s = 24h. Adjust if
            # ``_interval`` is non-default.
            ticks_per_day = max(1, int(24 * 3600 / max(1, self._interval)))
            news_task = None
            if self._execution_count % ticks_per_day == 0:
                news_task = asyncio.create_task(
                    self._poll_news_for_universe()
                )

            # Max-pain daily poll: staggered by 5 ticks from news-feed so
            # the two daily polls don't both fire on the same tick.
            max_pain_task = None
            if (self._execution_count + 5) % ticks_per_day == 0:
                max_pain_task = asyncio.create_task(
                    self._poll_max_pain_for_universe()
                )

            tasks = [options_task, underlying_task]
            if news_task is not None:
                tasks.append(news_task)
            if max_pain_task is not None:
                tasks.append(max_pain_task)

            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Fetcher error: {e}")

    async def _poll_news_for_universe(self):
        """Daily news poll: iterate top-10 universe + accumulate into DuckDB.

        Wrapped in ``run_in_executor`` to keep the event loop responsive
        during the blocking urllib fetches + DuckDB writes. Best-effort:
        any per-ticker failure is logged + skipped (does NOT fail the
        whole poll). Mirrors the try/except pattern of ``_fetch_options``.
        """
        try:
            loop = asyncio.get_running_loop()

            def sync_poll() -> None:
                from services.duckdb_engine import db as duckdb_engine
                from services.news_feed import (
                    accumulate_today,
                    fetch_ticker_news,
                    init_news_daily_table,
                )

                try:
                    init_news_daily_table(duckdb_engine)
                except Exception as exc:
                    logger.debug(f"news poll: init_table: {exc}")

                universe = (
                    "SPY", "QQQ", "AAPL", "TSLA", "NVDA",
                    "AMZN", "MSFT", "META", "GOOGL", "AMD",
                )
                for t in universe:
                    try:
                        rows = fetch_ticker_news(
                            t, cache_engine=duckdb_engine,
                        )
                        if rows:
                            accumulate_today(duckdb_engine, rows)
                    except Exception as exc:
                        logger.debug(
                            f"news poll: ticker {t} failed: {exc}"
                        )

            await loop.run_in_executor(None, sync_poll)
            logger.info("News polling for top-10 universe triggered.")
        except Exception as e:
            logger.error(f"News poll failed: {e}")

    async def _poll_max_pain_for_universe(self):
        """Daily max-pain poll: iterate top-10 universe + accumulate per-expiry.

        Mirrors ``_poll_news_for_universe`` — wrapped in
        ``run_in_executor`` to keep the event loop responsive during
        blocking yfinance fetches + DuckDB writes. Best-effort:
        any per-ticker failure is logged + skipped (does NOT fail the
        whole poll).
        """
        try:
            loop = asyncio.get_running_loop()

            def sync_poll() -> None:
                from services.duckdb_engine import db as duckdb_engine
                from services.max_pain_drift import (
                    accumulate_today,
                    accumulate_today_per_expiry,
                    init_max_pain_daily_table,
                )

                try:
                    init_max_pain_daily_table(duckdb_engine)
                except Exception as exc:
                    logger.debug(f"max_pain poll: init_table: {exc}")

                # Hoisted out of the per-ticker for-loop — runs once
                # per daily poll instead of 10x.
                from server import (
                    compute_max_pain_per_expiry,
                    compute_overall_max_pain,
                    fetch_spot_and_chains,
                )

                universe = (
                    "SPY", "QQQ", "AAPL", "TSLA", "NVDA",
                    "AMZN", "MSFT", "META", "GOOGL", "AMD",
                )
                for t in universe:
                    try:
                        raw = fetch_spot_and_chains(t, max_expiries=4)
                        contracts = raw.get("contracts") or []
                        spot_val = raw.get("spot") or 0.0
                        if not contracts:
                            continue
                        # Write one overall row + per-expiry rows.
                        # accumulate_today_per_expiry filters the
                        # "_unknown" sentinel + empty expiries itself.
                        accumulate_today(
                            duckdb_engine, t, spot_val,
                            compute_overall_max_pain(contracts),
                            expiry="",
                        )
                        accumulate_today_per_expiry(
                            duckdb_engine, t, spot_val,
                            compute_max_pain_per_expiry(contracts),
                        )
                    except Exception as exc:
                        logger.debug(
                            f"max_pain poll: ticker {t} failed: {exc}"
                        )

            await loop.run_in_executor(None, sync_poll)
            logger.info("Max-pain polling for top-10 universe triggered.")
        except Exception as e:
            logger.error(f"Max-pain poll failed: {e}")

    async def _fetch_options(self):
        """Fetch options chains in thread pool."""
        try:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, fetch_all_chains)
            if not df.empty:
                logger.info(f"Options fetch: {len(df)} rows")
            else:
                logger.warning("Options fetch returned empty")
        except Exception as e:
            logger.error(f"Options fetch failed: {e}")

    async def _fetch_underlying(self):
        """Fetch underlying data in thread pool."""
        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None, fetch_and_store, None, self._conn
            )
            total = sum(results.values())
            logger.info(f"Underlying fetch: {total} rows across {len(results)} tickers")
        except Exception as e:
            logger.error(f"Underlying fetch failed: {e}")

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        logger.info("Scheduler stop requested")

    @property
    def execution_count(self) -> int:
        return self._execution_count

    @property
    def is_running(self) -> bool:
        return self._running


async def run_scheduler(interval: int = DEFAULT_INTERVAL):
    """Convenience function to run the scheduler."""
    scheduler = PollingScheduler(interval=interval)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows doesn't support add_signal_handler
            loop.add_signal_handler(sig, scheduler.stop)

    await scheduler.start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(run_scheduler())
