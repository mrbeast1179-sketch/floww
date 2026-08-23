"""
backend/services/insider_scraper.py

Finviz insider-trading scraper (steal-list #20)
================================================

Wraps the three Buzzfund scrape patterns
(``https://finviz.com/insidertrading.ashx`` latest, ``?or=-10&tv=100000&tc=7``
top, ``/quote.ashx?t={ticker}`` per-ticker) into floww's service layer
and adds three things the upstream lacks:

  1. A robust header-based table-lookup that doesn't break when Finviz
     reorders their HTML tables (the upstream source's ``table[5]`` /
     ``table[9]`` magic constants are fragile).
  2. A DuckDB-backed daily-snapshot accumulator + 4-hour HTML-content
     cache so the dev server can be restarted without re-scraping.
  3. A pure-logic ``compute_insider_summary(ticker, rows)`` 7-key badge
     the Flowseeker scanner can read as a Flowseeker-Insider-BUY badge
     (cross-reference lens for flow-buyer + insider-buyer corroboration).

Steal intent: ``Buzzfund_UnusualOptions/insider.py`` (latest, top, per-
ticker). Lands in floww: `GET /api/insider/{ticker}?limit=50`,
`GET /api/insider/top?min_value=100000&tc=7&limit=20`, and the
accumulate cron `GET /api/insider/snapshot?accumulate=true`.

Audit: ``docs/reports/2026-07-11-steal-list-integration-roadmap.md`` #20
       ``backend/tests/services/test_insider_scraper.py`` (~16 cases
       pure-logic + DuckDB I/O + parser robustness + cache TTL).

This module is split:
- Fetch-side (``fetch_*``, ``_fetch_finviz_html``, ``_find_insider_table``,
  ``_parse_money``, ``_parse_date``, ``_classify_insider_title``): I/O OK.
- Pure-logic (``compute_insider_summary``): no network, no DB I/O.
- DuckDB I/O (``init_insider_daily_table``, ``accumulate_today``,
  ``read_recent_insider``): operate on an engine instance, fully testable
  in-memory with :memory: DuckDBEngine.
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup, Tag

from services.max_pain_drift import (
    _coerce_to_date,
    _safe_float,
    _to_date,
)

logger = logging.getLogger(__name__)


# Re-export the imported helpers so test consumers can hit them via the
# insider_scraper module namespace.
__all__ = [
    "compute_insider_summary",
    "accumulate_today",
    "read_recent_insider",
    "init_insider_daily_table",
    "fetch_ticker_insider",
    "fetch_top_insider",
    "fetch_latest_insider",
    "TABLE_NAME",
    "CACHE_TABLE_NAME",
    "CREATE_TABLE_SQL",
    "CREATE_INDEX_SQL_LIST",
    "UPSERT_SQL",
    "CACHE_TABLE_SQL",
    "CACHE_TTL_SECONDS",
]


# ─────────────────────────────────────────────────────────────────────
# Constants — table-naming + Finviz URL/header conventions. TTL is a
# generous 4 hours so dev-restart churn doesn't trigger Finviz IP-bans.
# ─────────────────────────────────────────────────────────────────────

TABLE_NAME = "insider_daily"
CACHE_TABLE_NAME = "insider_html_cache"
CACHE_TTL_SECONDS = 4 * 60 * 60    # 4 hours

FINVIZ_BASE = "https://finviz.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.6 Safari/605.1.15"
)
REQUEST_TIMEOUT_S = 15  # short: never hang the FastAPI route

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS insider_daily (
    snapshot_date      DATE,
    ticker             VARCHAR,
    insider_name       VARCHAR,
    title              VARCHAR,
    transaction_date   DATE,
    transaction_type   VARCHAR,
    cost               DOUBLE,
    shares             BIGINT,
    value              DOUBLE,
    shares_total       BIGINT,
    PRIMARY KEY (snapshot_date, ticker, transaction_date, insider_name)
)
"""

CREATE_INDEX_SQL_LIST = (
    "CREATE INDEX IF NOT EXISTS idx_insider_daily_ticker "
    "ON insider_daily(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_insider_daily_date "
    "ON insider_daily(snapshot_date)",
    "CREATE INDEX IF NOT EXISTS idx_insider_daily_value "
    "ON insider_daily(value)",
)

UPSERT_SQL = """
INSERT INTO insider_daily
    (snapshot_date, ticker, insider_name, title,
     transaction_date, transaction_type, cost, shares,
     value, shares_total)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (snapshot_date, ticker, transaction_date, insider_name)
DO UPDATE SET
    title = excluded.title,
    transaction_type = excluded.transaction_type,
    cost = excluded.cost,
    shares = excluded.shares,
    value = excluded.value,
    shares_total = excluded.shares_total
"""

CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS insider_html_cache (
    url_key      VARCHAR PRIMARY KEY,
    html_content VARCHAR,
    fetched_at   TIMESTAMP
)
"""


# ─────────────────────────────────────────────────────────────────────
# Defensive parsers — money/date/title are the three fragile
# Finviz HTML columns and need explicit handling before they reach
# DuckDB or the pure-logic compute.
# ─────────────────────────────────────────────────────────────────────


def _parse_money(raw: Any) -> float | None:
    """Coerce a Finviz money cell like ``"$1,234,500"`` → ``1234500.0``.

    Strips ``$``, ``,``, whitespace. Negative values (sells) handled by
    a leading minus sign. ``+`` and ``++`` for buy/buy-continued are
    treated as their plain-text description column, NOT as money — they
    never reach this function from the parser.

    Returns None for empty / non-numeric / NaN strings.
    """
    if raw is None:
        return None
    s = str(raw).strip().replace("$", "").replace(",", "").strip()
    if not s or s in {"-", "—", "N/A"}:
        return None
    # Buy/Buy Continued markers (Finviz's + / ++) → semantic info, not
    # money. Don't double-count as transactions; transaction_type column
    # captures that.
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _parse_date(raw: Any, anchor_date: date) -> date | None:
    """Coerce a Finviz date cell into a real ``datetime.date``.

    Finviz uses qualitative / shorthand dates:
      - ``"Today"``         → anchor_date
      - ``"Yesterday"``    → anchor_date - 1 day
      - ``"Jul 14"``       → current year (Jul 14, anchor_date.year)
      - ``"2024-07-14"``   → ISO date (already qualified)
      - ``"07/14/2024"``   → US-format MM/DD/YYYY (Finviz fallback)

    Returns None for unrecognised formats.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.lower() == "today":
        return anchor_date
    if s.lower() == "yesterday":
        return anchor_date - timedelta(days=1)
    # ISO YYYY-MM-DD
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        pass
    # US M/D/YYYY
    try:
        return datetime.strptime(s, "%m/%d/%Y").date()
    except ValueError:
        pass
    # Short "Jul 14" with year from anchor
    try:
        parsed = datetime.strptime(s, "%b %d").date()
        return parsed.replace(year=anchor_date.year)
    except ValueError:
        pass
    return None


_CEO_TOKENS = (
    "CEO", "Chief Executive", "Chief Executive Officer",
    "Pres", "President", "Chmn", "Chairman",
)


def _is_officer_title(title: str | None) -> bool:
    """Officer detector — powers the ``ceo_bought_recent`` summary key."""
    if not title:
        return False
    t = str(title).upper().strip()
    return any(tok.upper() in t for tok in _CEO_TOKENS)


def _classify_transaction_type(raw: str | None) -> str | None:
    """Lowercase + canonicalize Finviz transaction-type cell.

    Returns one of: ``"buy"``, ``"sell"``, ``"option_exercise"``,
    ``"gift"``, ``"other"`` — or None if unrecognised. Used by
    ``compute_insider_summary`` for the BUY-vs-SELL signal.
    """
    if not raw:
        return None
    s = str(raw).strip().lower()
    if s.startswith("buy") or s in {"p", "purchase"}:
        return "buy"
    if s.startswith("sale") or s in {"s", "sell", "s -o"}:
        return "sell"
    if s in {"option exercise", "exercise", "m"}:
        return "option_exercise"
    if s in {"gift", "g"}:
        return "gift"
    return "other"


def _find_insider_table(soup: BeautifulSoup) -> Tag | None:
    """Position+content hybrid table finder.

    Iterates ALL <table> elements, returns the first whose first <tr>
    contains the expected insider-trading column keywords. This is
    robust to Finviz reordering their HTML layout (which has changed at
    least 4 times in 2024-2025 alone). The upstream source's hardcoded
    ``table[5]`` and ``table[9]`` are fragile to this churn.
    """
    required_keywords = ("ticker", "insider trading", "date", "value")
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if first_row is None:
            continue
        cells = first_row.find_all(["td", "th"])
        headers = [c.get_text(strip=True).lower() for c in cells]
        if all(any(k in h for h in headers) for k in required_keywords):
            return table
    return None


# ─────────────────────────────────────────────────────────────────────
# Fetch-side — DuckDB-backed HTML cache + urllib I/O + parser.
# ─────────────────────────────────────────────────────────────────────


def evict_cache_if_over_limit(engine: Any, max_rows: int = 5000) -> None:
    """Evict oldest cache entries if we exceed ``max_rows``.

    Keeps the Finviz HTML cache from growing unbounded across long
    sessions. Called after every successful cache-write in
    ``_fetch_finviz_html``; best-effort (defensive degrade on errors).
    """
    try:
        engine.execute_write(
            "DELETE FROM insider_html_cache WHERE url_key IN ("
            "    SELECT url_key FROM insider_html_cache "
            "    ORDER BY fetched_at DESC OFFSET ?"
            ")",
            [int(max_rows)],
        )
    except Exception as exc:    # pragma: no cover
        logger.warning("insider cache eviction failed: %s", exc)


def _fetch_finviz_html(
    url: str,
    cache_engine: Any | None = None,
    warnings: list[str] | None = None,
) -> str | None:
    """GET Finviz with browser headers, returning HTML body as a string.

    If ``cache_engine`` is supplied, checks/leaves the 4h-HTML cache:
      - cache hit: returns cached HTML if younger than CACHE_TTL_SECONDS.
      - cache miss OR stale: fetches, then writes the fresh HTML back.

    Returns None if the network call fails entirely (defensive-degrade
    path; the caller logs the warning and yields []).
    """
    if warnings is None:
        warnings = []
    if cache_engine is not None:
        try:
            cached = cache_engine.query(
                "SELECT html_content, fetched_at FROM insider_html_cache "
                "WHERE url_key = ?",
                [url],
            )
            if cached:
                row = cached[0]
                fetched = row.get("fetched_at")
                html = row.get("html_content")
                if html and fetched:
                    if isinstance(fetched, datetime):
                        age_s = (datetime.now() - fetched).total_seconds()
                    else:
                        age_s = CACHE_TTL_SECONDS + 1   # force-refetch
                    if age_s < CACHE_TTL_SECONDS:
                        return html
        except Exception as exc:    # pragma: no cover
            warnings.append(f"cache read failed: {type(exc).__name__}: {exc}")

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            html_raw = resp.read()
        html = (
            html_raw.decode("utf-8", errors="replace")
            if isinstance(html_raw, bytes) else html_raw
        )
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        ConnectionError,
        OSError,
    ) as exc:
        warnings.append(
            f"finviz fetch failed for {url}: {type(exc).__name__}: {exc}"
        )
        return None
    if cache_engine is not None:
            try:
                cache_engine.execute_write(
                    "INSERT INTO insider_html_cache (url_key, html_content, fetched_at) "
                    "VALUES (?, ?, ?) ON CONFLICT (url_key) DO UPDATE SET "
                    "html_content = excluded.html_content, "
                    "fetched_at = excluded.fetched_at",
                    [(url, html, datetime.now())],
                )
                evict_cache_if_over_limit(cache_engine, 5000)
            except Exception as exc:    # pragma: no cover
                warnings.append(f"cache write failed: {type(exc).__name__}: {exc}")

    return html


def _parse_insider_table(
    table: Tag,
    anchor_date: date | None = None,
) -> list[dict[str, Any]]:
    """Parse a Finviz insider-trading HTML table into a list[dict].

    Each dict has: ticker, insider_name, title, transaction_date,
    transaction_type, cost, shares, value, shares_total. Defensive on
    every column. Drops rows missing ticker OR insider_name (mandatory
    keys). All monetary columns passed through ``_parse_money``.

    The header row itself is consumed for column-name lookup.
    """
    if anchor_date is None:
        anchor_date = date.today()
    rows = []
    all_tr = table.find_all("tr")
    if not all_tr:
        return rows
    headers = [
        c.get_text(strip=True).lower() for c in all_tr[0].find_all(["td", "th"])
    ]
    # Map header-name → column-index.
    col_idx: dict[str, int] = {h: i for i, h in enumerate(headers)}

    def _col(name_options: tuple, tr: Tag) -> str | None:
        for n in name_options:
            if n in col_idx:
                cells = tr.find_all(["td", "th"])
                if col_idx[n] < len(cells):
                    return cells[col_idx[n]].get_text(strip=True)
        return None

    for tr in all_tr[1:]:
        cells = tr.find_all(["td", "th"])
        if len(cells) < 4:
            continue  # malformed row, skip

        ticker = _col(("ticker",), tr)
        insider_name = _col(("insider trading", "insider"), tr)
        if not ticker or not insider_name:
            continue
        title = _col(("title",), tr)
        date_cell = _col(("date",), tr)
        transaction_date = _parse_date(date_cell, anchor_date) if date_cell else None
        type_cell = _col(("type", "transaction"), tr)
        transaction_type = _classify_transaction_type(type_cell)
        cost_cell = _col(("cost",), tr)
        cost = _parse_money(cost_cell)
        shares_cell = _col(("shares", "#shares"), tr)
        shares = _safe_float(
            "shares", {}, _parse_money(shares_cell),
            warnings=[],
        )
        value_cell = _col(("value",), tr)
        value = _parse_money(value_cell)
        shares_total_cell = _col(("shares total", "total"), tr)
        shares_total = _safe_float(
            "shares_total", {}, _parse_money(shares_total_cell),
            warnings=[],
        )

        rows.append({
            "ticker": ticker.strip().upper(),
            "insider_name": " ".join(insider_name.split()),  # collapse whitespace
            "title": re.sub(r"\s*\([^(]*\)\s*$", "", title or "").strip(),
            "transaction_date": transaction_date,
            "transaction_type": transaction_type,
            "cost": cost,
            "shares": int(shares) if shares is not None else None,
            "value": value,
            "shares_total": int(shares_total) if shares_total is not None else None,
        })
    return rows


def fetch_ticker_insider(
    ticker: str,
    cache_engine: Any | None = None,
    anchor_date: date | None = None,
) -> list[dict[str, Any]]:
    """Fetch the recent insider trades for ``ticker`` from Finviz.

    Pure network I/O + table parsing — no DB writes here (the caller
    decides whether to ``accumulate_today`` what comes back).

    Returns ``[]`` if the network call fails, the table isn't found, or
    the table is empty.
    """
    warnings: list[str] = []
    url = f"{FINVIZ_BASE}/quote.ashx?t={urllib.parse.quote(ticker.upper())}"
    html = _fetch_finviz_html(url, cache_engine, warnings)
    if not html:
        for w in warnings:
            logger.warning(f"fetch_ticker_insider({ticker}): {w}")
        return []
    soup = BeautifulSoup(html, "html.parser")
    table = _find_insider_table(soup)
    if table is None:
        logger.warning(
            f"fetch_ticker_insider({ticker}): insider table not found in HTML"
        )
        return []
    return _parse_insider_table(table, anchor_date)


def fetch_top_insider(
    min_value: int = 100_000,
    days: int = 7,
    cache_engine: Any | None = None,
    limit: int = 50,
    anchor_date: date | None = None,
) -> list[dict[str, Any]]:
    """Fetch the top insider buys for the last ``days`` days above ``min_value``.

    Defaults mirror the upstream Buzzfund function's hardcoded filter
    (or=-10, tv=100000, tc=7, o=-transactionValue). Returns at most
    ``limit`` rows.
    """
    warnings: list[str] = []
    qs = urllib.parse.urlencode({
        "or": "-10",
        "tv": str(min_value),
        "tc": str(days),
        "o": "-transactionValue",
    })
    url = f"{FINVIZ_BASE}/insidertrading.ashx?{qs}"
    html = _fetch_finviz_html(url, cache_engine, warnings)
    if not html:
        for w in warnings:
            logger.warning(f"fetch_top_insider: {w}")
        return []
    soup = BeautifulSoup(html, "html.parser")
    table = _find_insider_table(soup)
    if table is None:
        logger.warning(
            "fetch_top_insider: insider table not found in HTML"
        )
        return []
    rows = _parse_insider_table(table, anchor_date)
    return rows[:max(0, int(limit))]


def fetch_latest_insider(
    cache_engine: Any | None = None,
    limit: int = 50,
    anchor_date: date | None = None,
) -> list[dict[str, Any]]:
    """Fetch the latest insider trades market-wide (Finviz default feed)."""
    warnings: list[str] = []
    url = f"{FINVIZ_BASE}/insidertrading.ashx"
    html = _fetch_finviz_html(url, cache_engine, warnings)
    if not html:
        for w in warnings:
            logger.warning(f"fetch_latest_insider: {w}")
        return []
    soup = BeautifulSoup(html, "html.parser")
    table = _find_insider_table(soup)
    if table is None:
        logger.warning(
            "fetch_latest_insider: insider table not found in HTML"
        )
        return []
    rows = _parse_insider_table(table, anchor_date)
    return rows[:max(0, int(limit))]


# ─────────────────────────────────────────────────────────────────────
# DuckDB I/O — table init + daily-snapshot accumulator + read API.
# Mirrors the max_pain_daily / consensus_daily accumulation pattern.
# ─────────────────────────────────────────────────────────────────────


def init_insider_daily_table(engine) -> None:
    """Create the daily + cache tables + indexes. Idempotent."""
    engine.execute_write(CREATE_TABLE_SQL)
    for stmt in CREATE_INDEX_SQL_LIST:
        engine.execute_write(stmt)
    engine.execute_write(CACHE_TABLE_SQL)


def _build_row_for_upsert(
    snapshot_date: date,
    row: dict[str, Any],
) -> tuple | None:
    """Build the 10-tuple row for UPSERT. Drops rows missing the
    mandatory keys (ticker/insider_name) or with NaN transaction_date.
    """
    warnings: list[str] = []
    ticker = row.get("ticker")
    insider_name = row.get("insider_name")
    transaction_date = _to_date(
        row.get("transaction_date"), "transaction_date", warnings,
    )
    if not ticker or not insider_name or transaction_date is None:
        return None
    cost = _safe_float("cost", row, row.get("cost"), warnings)
    shares = _safe_float("shares", row, row.get("shares"), warnings)
    value = _safe_float("value", row, row.get("value"), warnings)
    shares_total = _safe_float(
        "shares_total", row, row.get("shares_total"), warnings,
    )
    if warnings:
        for w in warnings:
            logger.warning(
                f"_build_row_for_upsert({ticker}, {insider_name}): {w}"
            )
    return (
        snapshot_date,
        ticker,
        insider_name,
        row.get("title") or "",
        transaction_date,
        row.get("transaction_type") or "",
        cost,
        int(shares) if shares is not None else None,
        value,
        int(shares_total) if shares_total is not None else None,
    )


def accumulate_today(
    engine,
    rows: list[dict[str, Any]],
    snapshot_date: date | None = None,
) -> int:
    """UPSERT ``rows`` into ``insider_daily``. Returns the COUNT OF ROWS THAT
    *PASSED* THE PRE-WRITE FILTER (``ticker``/``insider_name``/valid
    ``transaction_date`` present), as a tuple-pre-write number.

    On DuckDB failure (``engine.execute_write`` raises) the exception
    propagates; callers should wrap in try/except. The return value is
    NOT a confirmed-persisted count — a successful return of N means N
    rows were submitted to the upsert statement, not that the upsert
    itself succeeded.
    """
    if snapshot_date is None:
        snapshot_date = date.today()
    if not rows:
        return 0
    tuples: list[tuple] = []
    for r in rows:
        built = _build_row_for_upsert(snapshot_date, r)
        if built is not None:
            tuples.append(built)
    if not tuples:
        return 0
    engine.execute_write(UPSERT_SQL, tuples)
    return len(tuples)


def read_recent_insider(
    engine,
    ticker: str | None,
    n_days: int = 14,
    min_value: float | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Return insider rows from the last ``n_days`` for ``ticker`` (or all).

    Forward-chronological (oldest first). Optional ``min_value`` filter
    trims to buys/aboves the threshold. Returns ``[]`` on DB error.
    """
    if n_days <= 0:
        return []
    if today is None:
        today = date.today()
    cutoff = today - timedelta(days=n_days)
    params: list[Any] = []
    if ticker:
        sql = (
            f"SELECT snapshot_date, ticker, insider_name, title, "
            f"transaction_date, transaction_type, cost, shares, "
            f"value, shares_total "
            f"FROM {TABLE_NAME} "
            f"WHERE snapshot_date > ? "
            f"AND ticker = ? "
        )
        params = [cutoff, ticker.upper()]
    else:
        sql = (
            f"SELECT snapshot_date, ticker, insider_name, title, "
            f"transaction_date, transaction_type, cost, shares, "
            f"value, shares_total "
            f"FROM {TABLE_NAME} "
            f"WHERE snapshot_date > ? "
        )
        params = [cutoff]
    if min_value is not None:
        sql += " AND value >= ? "
        params.append(float(min_value))
    sql += (
        " ORDER BY snapshot_date ASC, transaction_date ASC "
        " LIMIT ?"
    )
    params.append(n_days * 64)
    try:
        rows = engine.query(sql, params)
        # Normalize dates — DuckDB returns ``pd.Timestamp`` for DATE cols.
        rows = [
            {**r,
             "snapshot_date": _coerce_to_date(r.get("snapshot_date")),
             "transaction_date": _coerce_to_date(r.get("transaction_date"))}
            for r in rows
        ]
        return rows
    except Exception as exc:    # pragma: no cover
        logger.warning(
            f"read_recent_insider({ticker}): {type(exc).__name__}: {exc}"
        )
        return []


# ─────────────────────────────────────────────────────────────────────
# Pure-logic compute — distills row arrays into a 7-key Flowseeker
# badge summary. No I/O.
# ─────────────────────────────────────────────────────────────────────


def compute_insider_summary(
    ticker: str | None,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Produce a 7-key summary suitable for the Flowseeker insider badge.

    Output keys:
        ticker :            ticker filter (passed-through; None = market)
        n_buys_30d :        count of BUY transactions in the row window
        n_sells_30d :       count of SELL transactions in the row window
        total_buy_value :   sum of BUY rows' ``value`` column
        total_sell_value :  sum of SELL rows' ``value`` column
        net_buy_pressure :   total_buy_value - total_sell_value
        largest_buy_value : max single BUY row's ``value`` (None if no buys)
        ceo_bought_recent : True iff any BUY row in window has officer
                            title (CEO / President / Chairman / etc.)
        n_rows_considered : count of rows fed in (post-filter diagnostic)
        warnings :          list of parser-level warnings (NaN strings)
    """
    warnings: list[str] = []
    n_buys = 0
    n_sells = 0
    total_buy_value = 0.0
    total_sell_value = 0.0
    largest_buy_value = 0.0
    largest_buy_seen = False
    ceo_bought_recent = False

    for r in rows:
        if not isinstance(r, dict):
            warnings.append("non-dict row skipped")
            continue
        # Skip rows that don't match the ticker filter (for per-ticker calls).
        if ticker is not None:
            row_ticker = str(r.get("ticker") or "").upper()
            if row_ticker != ticker.upper():
                continue
        tx_type = (r.get("transaction_type") or "").lower()
        value = _safe_float(
            "value", r, r.get("value"), warnings,
        )
        if value is None:
            continue  # NaN row contributes nothing to summary math
        if tx_type == "buy":
            n_buys += 1
            total_buy_value += value
            if not largest_buy_seen or value > largest_buy_value:
                largest_buy_value = value
                largest_buy_seen = True
            if _is_officer_title(r.get("title")):
                ceo_bought_recent = True
        elif tx_type == "sell":
            n_sells += 1
            total_sell_value += abs(value)
        # Other (option_exercise / gift / other / None) is recorded but
        # doesn't affect the buy/sell summary stats.

    return {
        "ticker": ticker,
        "n_buys_30d": n_buys,
        "n_sells_30d": n_sells,
        "total_buy_value": round(total_buy_value, 4),
        "total_sell_value": round(total_sell_value, 4),
        "net_buy_pressure": round(total_buy_value - total_sell_value, 4),
        "largest_buy_value": (
            round(largest_buy_value, 4) if largest_buy_seen else None
        ),
        "ceo_bought_recent": ceo_bought_recent,
        "n_rows_considered": len(rows),
        "warnings": warnings,
    }
