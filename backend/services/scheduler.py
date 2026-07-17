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

# ─────────────────────────────────────────────────────────────────────
# Universe constant — hoisted to module level so the scheduler tests
# can ``from services.scheduler import RV_UNIVERSE`` and pin the
# universe end-to-end (mirrors the convention in tests that hit
# ``services.max_pain_drift.TABLE_NAME`` as a canonical reference).
# Single source of truth — also referenced by both
# ``_poll_rv_for_universe`` (RV/VRP cron) and any other future
# universe-driven cron that wants the same top-10 set.
# ─────────────────────────────────────────────────────────────────────

RV_UNIVERSE: tuple[str, ...] = (
    "SPY", "QQQ", "AAPL", "TSLA", "NVDA",
    "AMZN", "MSFT", "META", "GOOGL", "AMD",
)


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

            # RV/VRP daily poll: staggered by 10 ticks from news-feed so
            # the three daily polls (news + max_pain + RV) never share
            # the same tick — keep each fetch+write burst isolated.
            rv_task = None
            if (self._execution_count + 10) % ticks_per_day == 0:
                rv_task = asyncio.create_task(
                    self._poll_rv_for_universe()
                )

            tasks = [options_task, underlying_task]
            if news_task is not None:
                tasks.append(news_task)
            if max_pain_task is not None:
                tasks.append(max_pain_task)
            if rv_task is not None:
                tasks.append(rv_task)

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

    async def _poll_rv_for_universe(self):
        """Daily RV/VRP poll for the top-10 universe (steal-list #7).

        Each tick fires the cron at 1440-tick / 24h cadence (60s
        interval) staggered by 10 ticks from the news-feed poll so
        the three daily polls (news + max_pain + RV) never share a
        tick. Per ticker we write 5 estimator rows (rv_daily) + 3
        cone rows (rv_cones_daily) + 2 band rows (rv_bands_daily) +
        1 VRP row (rv_vrp_daily) = 11 persisted rows.

        Each per-ticker fetch+compute+write sequence is wrapped in
        try/except so a single bad ticker cannot fail the whole
        poll; the loop is best-effort.

        Mirrors ``_poll_max_pain_for_universe``: ``run_in_executor``
        keeps the event loop responsive during Mongo + yfinance
        fetches + DuckDB writes. Per the cron spec the bars source
        is Mongo ``underlying_bars`` (~60 daily bars); front-month
        ATM IV comes from the established yfinance path mirroring
        ``routes/steal_three.py:2070-2080``.
        """
        try:
            loop = asyncio.get_running_loop()

            def sync_poll() -> None:
                from services.duckdb_engine import db as duckdb_engine
                from services.realized_volatility import (
                    accumulate_bands_today,
                    accumulate_cones_today,
                    accumulate_today,
                    accumulate_vrp_today,
                    compute_realized_volatility,
                    compute_typical_range_bands,
                    compute_vol_cone,
                    fetch_front_atm_iv_sync,
                    fetch_underlying_bars_sync,
                    init_rv_bands_table,
                    init_rv_cones_table,
                    init_rv_daily_table,
                    init_rv_vrp_table,
                )
                # Defensive: ``server.db`` is a Mongo handle populated at
                # app-startup; if the cron fires in a non-server context
                # (tests / standalone scheduler / CI without the FastAPI
                # app bootstrapped), ``server.db`` may be ``None`` or the
                # import may fail entirely. Set ``mongo_db = None`` so
                # the sync fetchers gracefully fall back to yfinance
                # instead of letting one ticker's poll blow up.
                mongo_db = None
                try:
                    from server import db as _server_db
                    if _server_db is not None:
                        mongo_db = _server_db
                except Exception as _import_exc:
                    logger.debug(
                        f"rv poll: server.db import deferred: "
                        f"{type(_import_exc).__name__}: {_import_exc}"
                    )

                # Idempotent inits (4 DuckDB tables, all in parallel
                # with init pattern from news_feed._poll_news_for_universe).
                for init_fn in (
                    init_rv_daily_table,
                    init_rv_cones_table,
                    init_rv_bands_table,
                    init_rv_vrp_table,
                ):
                    try:
                        init_fn(duckdb_engine)
                    except Exception as exc:
                        logger.debug(
                            f"rv poll: {init_fn.__name__}: {exc}"
                        )

                ESTIMATORS = (
                    "close_to_close",
                    "parkinson",
                    "garman_klass",
                    "rogers_satchell",
                    "yang_zhang",
                )
                # Universe hoisted to module-level RV_UNIVERSE (see
                # ``test_rv_poll_iterates_top_10_universe``).
                for t in RV_UNIVERSE:
                    try:
                        # 1. Pull ~60 daily bars from Mongo underlying_bars.
                        bars = fetch_underlying_bars_sync(
                            t, days=60, mongo_db=mongo_db,
                        )
                        if not bars:
                            continue

                        # 2. 5 estimator rows per ticker.
                        rv_dict: dict[str, float] = {}
                        for est in ESTIMATORS:
                            res = compute_realized_volatility(
                                bars, estimator=est,
                            )
                            v = res.get("volatility")
                            if (
                                v is not None
                                and isinstance(v, (int, float))
                                and v > 0
                            ):
                                rv_dict[est] = float(v)
                        if rv_dict:
                            accumulate_today(duckdb_engine, t, rv_dict)

                        # 3. 3 cone rows (20d / 30d / 60d).
                        cone = compute_vol_cone(
                            bars, lookbacks_days=(20, 30, 60),
                        )
                        cone_clean = {
                            k: v for k, v in cone.items()
                            if k != "warnings"
                        }
                        if cone_clean:
                            accumulate_cones_today(
                                duckdb_engine, t, cone_clean,
                            )

                        # 4. 2 band rows (daily + weekly).
                        bands = compute_typical_range_bands(
                            bars, windows=(1, 5),
                        )
                        bands_clean = {
                            k: v for k, v in bands.items()
                            if k != "warnings"
                        }
                        if bands_clean:
                            accumulate_bands_today(
                                duckdb_engine, t, bands_clean,
                            )

                        # 5. 1 VRP row using the front-month ATM IV.
                        front_atm_iv = fetch_front_atm_iv_sync(
                            t, mongo_db=mongo_db,
                        )
                        yz_rv = rv_dict.get("yang_zhang")
                        if (
                            front_atm_iv is not None
                            and yz_rv is not None
                        ):
                            accumulate_vrp_today(
                                duckdb_engine, t, front_atm_iv, yz_rv,
                            )
                    except Exception as exc:
                        logger.debug(
                            f"rv poll: ticker {t} failed: {exc}"
                        )

            await loop.run_in_executor(None, sync_poll)
            logger.info("RV/VRP polling for top-10 universe triggered.")
        except Exception as e:
            logger.error(f"RV/VRP poll failed: {e}")

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
