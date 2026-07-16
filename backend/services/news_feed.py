"""
Free financial-news headline ingestion (steal-list #4)
======================================================

Scrapes Yahoo Finance for zero-cost per-ticker news headlines and
article body text. Replaces paid-X / xurl dependencies with a
pure-Python BeautifulSoup alternative.

Mirrors the ``insider_scraper.py`` fetch/parse pattern exactly:
- ``urllib.request`` only (no extra dependencies)
- Multi-fallback defensive parsing (handles YF layout churn)
- Empty lists returned on failure (graceful degrade)

Now ships with DuckDB persistence (``news_daily`` + ``news_html_cache``)
mirroring backend/services/occ_scraper.py + insider_scraper.py
conventions (PRIMARY KEY + UPSERT + snapshot_date + 24h HTML cache).
The periodic-poll wiring lives in backend/services/scheduler.py.

Steal from: ``shirosaidev_stocksight`` — NewsHeadlineListener class
            (L265-337), get_news_headlines() (L339-382),
            get_page_text() (L385-409)
Lands in:    ``backend/services/news_feed.py`` (this file)
             exposed via ``routes/steal_three.py`` on :8000
             (canonical FastAPI app via server.py line 2994).

Audit: ``docs/reports/2026-07-11-steal-list-integration-roadmap.md``
       ``backend/tests/services/test_news_feed.py``
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

__all__ = [
    "fetch_ticker_news",
    "fetch_article_text",
    "init_news_daily_table",
    "accumulate_today",
    "read_recent_news",
    "compute_news_summary",
]


# ─────────────────────────────────────────────────────────────────────
# Constants — table-naming + Yahoo URL/header conventions. Mirrors the
# occ_scraper.py / insider_scraper.py style for consistency.
# ─────────────────────────────────────────────────────────────────────

TABLE_NAME = "news_daily"
CACHE_TABLE_NAME = "news_html_cache"
CACHE_TTL_SECONDS = 24 * 60 * 60    # 24 hours — daily-cadence accumulator

YAHOO_BASE = "https://finance.yahoo.com"
USER_AGENTS: tuple = (
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 "
        "Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    ),
)
REQUEST_TIMEOUT_S = 15  # short: never hang the FastAPI route


# Generic paragraph length floor — filters UI chrome (<40 chars) from
# genuine article body on non-Yahoo pages.
_MIN_PARAGRAPH_LEN = 40

# Max cached HTML pages kept in news_html_cache (LRU by fetched_at).
_CACHE_MAX_ROWS = 5000


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS news_daily (
    snapshot_date      DATE,
    ticker             VARCHAR,
    headline           VARCHAR,
    url                VARCHAR,
    publisher          VARCHAR,
    scraped_at         TIMESTAMP,
    PRIMARY KEY (snapshot_date, ticker, url)
)
"""

CREATE_INDEX_SQL_LIST = (
    "CREATE INDEX IF NOT EXISTS idx_news_ticker "
    "ON news_daily(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_news_date "
    "ON news_daily(snapshot_date)",
)

UPSERT_SQL = """
INSERT INTO news_daily
    (snapshot_date, ticker, headline, url, publisher, scraped_at)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (snapshot_date, ticker, url) DO UPDATE SET
    headline   = excluded.headline,
    publisher  = excluded.publisher,
    scraped_at = excluded.scraped_at
"""

CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS news_html_cache (
    url_key      VARCHAR PRIMARY KEY,
    html_content VARCHAR,
    fetched_at   TIMESTAMP
)
"""


# ─────────────────────────────────────────────────────────────────────
# Helpers — deterministic UA rotation + defensive HTTP fetch.
# ─────────────────────────────────────────────────────────────────────


def _get_user_agent(ticker: str) -> str:
    """Deterministic rotation based on ticker hash to spread fingerprints.

    Python's built-in ``hash()`` is randomised per process for security,
    so different runs use different UAs across the same ticker — exactly
    the anti-fingerprint behaviour we want for a free, public endpoint.
    """
    return USER_AGENTS[hash(ticker) % len(USER_AGENTS)]


def _fetch_html(
    url: str,
    user_agent: str,
    warnings: list[str],
    cache_engine: Any | None = None,
) -> str | None:
    """GET HTML using urllib with defensive degrade + optional 24h cache.

    If ``cache_engine`` is supplied, checks/leaves the 24h-HTML cache:
      - cache hit: returns cached HTML if younger than CACHE_TTL_SECONDS.
      - cache miss OR stale: fetches, then writes the fresh HTML back.

    Returns ``None`` for any HTTP/network error; caller logs the
    warning and yields ``[]``. Mirrors ``_fetch_finviz_html`` in
    ``insider_scraper.py`` for consistency.
    """
    if cache_engine is not None:
        try:
            cached = cache_engine.query(
                "SELECT html_content, fetched_at FROM "
                f"{CACHE_TABLE_NAME} WHERE url_key = ?",
                [url],
            )
            if cached:
                row = cached[0]
                fetched = row.get("fetched_at")
                html = row.get("html_content")
                if html and fetched:
                    if isinstance(fetched, datetime):
                        age_s = (
                            datetime.now() - fetched
                        ).total_seconds()
                    else:
                        age_s = CACHE_TTL_SECONDS + 1   # force-refetch
                    if age_s < CACHE_TTL_SECONDS:
                        return html
        except Exception as exc:    # pragma: no cover
            warnings.append(
                f"cache read failed: {type(exc).__name__}: {exc}"
            )

    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(
            req, timeout=REQUEST_TIMEOUT_S
        ) as resp:
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
            f"network error for {url}: {type(exc).__name__}: {exc}"
        )
        return None

    if cache_engine is not None:
        try:
            cache_engine.execute_write(
                f"INSERT INTO {CACHE_TABLE_NAME} "
                "(url_key, html_content, fetched_at) "
                "VALUES (?, ?, ?) ON CONFLICT (url_key) DO "
                "UPDATE SET html_content = excluded.html_content, "
                "fetched_at = excluded.fetched_at",
                [(url, html, datetime.now())],
            )
            # LRU eviction: keep top _CACHE_MAX_ROWS by fetched_at DESC.
            cache_engine.execute_write(
                f"DELETE FROM {CACHE_TABLE_NAME} WHERE url_key IN ("
                f"    SELECT url_key FROM {CACHE_TABLE_NAME} "
                f"    ORDER BY fetched_at DESC OFFSET ?"
                f")",
                [int(_CACHE_MAX_ROWS)],
            )
        except Exception as exc:    # pragma: no cover
            warnings.append(
                f"cache write failed: {type(exc).__name__}: {exc}"
            )

    return html


# ─────────────────────────────────────────────────────────────────────
# Parsers — defensive headline + article-body extraction.
# ─────────────────────────────────────────────────────────────────────


def _parse_headlines(
    soup: BeautifulSoup, ticker: str,
) -> list[dict[str, Any]]:
    """Defensive headline extraction.

    Strategy: walk every ``<h3>`` and ``<h2>`` tag; if its parent is an
    ``<a>`` (Yahoo's canonical wrapping), or an ``<a>`` is its closest
    ancestor, capture the title + URL + adjacent publisher. Dedupe by URL.
    """
    headlines: list[dict[str, Any]] = []
    seen_urls: set = set()

    for h_tag in soup.find_all(["h3", "h2"]):
        a_tag: Any | None = None
        if h_tag.parent is not None and getattr(h_tag.parent, "name", None) == "a":
            a_tag = h_tag.parent
        else:
            a_tag = h_tag.find_parent("a")
        if a_tag is None:
            continue

        url = a_tag.get("href")
        if not url:
            continue

        # Normalize relative Yahoo URLs.
        if isinstance(url, str) and url.startswith("/"):
            url = f"{YAHOO_BASE}{url}"
        if url in seen_urls:
            continue

        title = h_tag.get_text(strip=True)
        if not title:
            continue

        # Sub-text (publisher / timestamp) is often in adjacent <div>.
        publisher = ""
        pub_div = a_tag.find_next_sibling("div")
        if pub_div is not None:
            publisher = pub_div.get_text(strip=True)[:80]

        headlines.append({
            "ticker": ticker.upper(),
            "title": title,
            "url": url,
            "publisher": publisher,
            "scraped_at": datetime.now(UTC).isoformat(),
        })
        seen_urls.add(url)

    return headlines


def _parse_paragraphs(soup: BeautifulSoup) -> list[str]:
    """Extract article-body paragraphs with a Yahoo-native preference.

    Yahoo Finance wraps article bodies in ``<div class="caas-body">``;
    external links fall back to a generic ``<p>`` walk with a length
    floor to filter UI chrome.
    """
    paragraphs: list[str] = []
    caas_body = soup.find("div", class_="caas-body")
    if caas_body is not None:
        for p in caas_body.find_all("p"):
            text = p.get_text(strip=True)
            if text:
                paragraphs.append(text)
    else:
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            # Generic fallback: filter UI chrome by length floor.
            if len(text) > _MIN_PARAGRAPH_LEN:
                paragraphs.append(text)
    return paragraphs


# ─────────────────────────────────────────────────────────────────────
# Public API — used by the steal-three router.
# ─────────────────────────────────────────────────────────────────────


def fetch_ticker_news(ticker: str, limit: int = 15, cache_engine: Any | None = None) -> list[dict[str, Any]]:
    """Fetch recent Yahoo Finance news headlines for ``ticker``.

    Returns a list of ``{ticker, title, url, publisher, scraped_at}``
    dicts (newest first per Yahoo's natural ordering). Returns ``[]``
    on any HTTP/network/parse failure (graceful degrade).

    If ``cache_engine`` is supplied, the fetched HTML is cached for
    24 hours in news_html_cache (LRU-evicted at 5000 rows) — mirrors
    the insider_scraper.py fetch-caching pattern.
    """
    warnings: list[str] = []
    url = (
        f"{YAHOO_BASE}/quote/{urllib.parse.quote(ticker.upper())}/news"
    )

    html = _fetch_html(url, _get_user_agent(ticker), warnings, cache_engine)
    if not html:
        # Fallback to the bare quote page — Yahoo sometimes 404s on /news.
        url = (
            f"{YAHOO_BASE}/quote/{urllib.parse.quote(ticker.upper())}"
        )
        html = _fetch_html(url, _get_user_agent(ticker), warnings, cache_engine)

    if not html:
        for w in warnings:
            logger.warning(f"fetch_ticker_news({ticker}): {w}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    rows = _parse_headlines(soup, ticker)
    return rows[: max(0, int(limit))]


def fetch_article_text(
    url: str, max_paragraphs: int = 10,
) -> dict[str, Any]:
    """Follow a news article URL and extract its body paragraphs.

    Returns ``{url, paragraphs, warnings}``. Empty ``paragraphs`` list
    + warning indicates a paywall / malformed page / network failure.
    """
    warnings: list[str] = []

    html = _fetch_html(url, _get_user_agent(url), warnings)
    if not html:
        return {
            "url": url,
            "paragraphs": [],
            "warnings": warnings,
        }

    soup = BeautifulSoup(html, "html.parser")
    paragraphs = _parse_paragraphs(soup)
    if not paragraphs:
        warnings.append(
            "No article paragraphs found (possible paywall or "
            "non-article URL)."
        )

    return {
        "url": url,
        "paragraphs": paragraphs[: max(0, int(max_paragraphs))],
        "warnings": warnings,
    }


# ─────────────────────────────────────────────────────────────────────
# DuckDB I/O — daily accumulator + read API.
# Mirrors backend/services/occ_scraper.py / insider_scraper.py conventions
# (PRIMARY KEY + UPSERT + snapshot_date).
# ─────────────────────────────────────────────────────────────────────


def init_news_daily_table(engine) -> None:
    """Create news_daily + news_html_cache + indexes. Idempotent."""
    engine.execute_write(CREATE_TABLE_SQL)
    for stmt in CREATE_INDEX_SQL_LIST:
        engine.execute_write(stmt)
    engine.execute_write(CACHE_TABLE_SQL)


def _build_row_for_accumulate(
    snapshot_date: date,
    row: dict[str, Any],
) -> tuple | None:
    """Build the 6-tuple UPSERT row. Drops rows missing ticker or url."""
    ticker = str(row.get("ticker") or "").strip().upper()
    url = str(row.get("url") or "").strip()
    if not ticker or not url:
        return None
    title = str(row.get("title") or "")
    publisher = str(row.get("publisher") or "")
    scraped_at_raw = row.get("scraped_at")
    if isinstance(scraped_at_raw, str):
        try:
            scraped_at = datetime.fromisoformat(
                scraped_at_raw.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except ValueError:
            scraped_at = datetime.now()
    elif isinstance(scraped_at_raw, datetime):
        scraped_at = scraped_at_raw.replace(tzinfo=None)
    else:
        scraped_at = datetime.now()
    return (snapshot_date, ticker, title, url, publisher, scraped_at)


def accumulate_today(
    engine,
    rows: list[dict[str, Any]],
    snapshot_date: date | None = None,
) -> int:
    """UPSERT ``rows`` into ``news_daily``. Returns count actually written.

    Idempotent on same-day re-runs (PRIMARY KEY (snapshot_date, ticker, url)
    ON CONFLICT DO UPDATE).
    """
    if snapshot_date is None:
        snapshot_date = date.today()
    if not rows:
        return 0
    tuples: list[tuple] = []
    for r in rows:
        built = _build_row_for_accumulate(snapshot_date, r)
        if built is not None:
            tuples.append(built)
    if not tuples:
        return 0
    engine.execute_write(UPSERT_SQL, tuples)
    return len(tuples)


def read_recent_news(
    engine,
    ticker: str,
    n_days: int = 14,
) -> list[dict[str, Any]]:
    """Return news rows from the last ``n_days`` for ``ticker``.

    Forward-chronological (oldest first). Returns ``[]`` on DB error.
    """
    if n_days <= 0:
        return []
    sql = (
        f"SELECT snapshot_date, ticker, headline, url, publisher, scraped_at "
        f"FROM {TABLE_NAME} "
        f"WHERE ticker = ? "
        f"ORDER BY snapshot_date ASC, scraped_at ASC "
        f"LIMIT ?"
    )
    try:
        rows = engine.query(sql, [ticker.upper(), int(n_days * 30)])
        return rows
    except Exception as exc:    # pragma: no cover
        logger.warning(
            f"read_recent_news({ticker}): {type(exc).__name__}: {exc}"
        )
        return []


# ─────────────────────────────────────────────────────────────────────
# Pure-logic compute — distills headline arrays into a 6-key summary.
# No I/O.
# ─────────────────────────────────────────────────────────────────────


_CATALYST_KEYWORDS = frozenset({
    "earnings", "fda", "merger", "acquisition", "spinoff",
    "upgrade", "downgrade", "buyout", "phase 3", "phase 2",
    "approval", "guidance", "restructuring", "layoff",
})


def compute_news_summary(
    ticker: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Produce a 6-key summary for the Flowseeker news badge.

    Output keys:
        ticker             : ticker filter (passed-through)
        n_headlines        : count of headlines in the window
        n_unique_domains   : distinct publisher count
        top_publishers     : top-3 publishers by headline count
        has_catalyst_news  : True iff any headline mentions a
                              catalyst keyword (earnings/fda/merger/etc.)
        warnings           : parser-level warnings
    """
    warnings: list[str] = []
    n_headlines = 0
    publisher_counts: dict[str, int] = {}
    has_catalyst = False

    for r in rows:
        if not isinstance(r, dict):
            warnings.append("non-dict row skipped")
            continue
        n_headlines += 1
        pub = str(r.get("publisher") or "Unknown")
        publisher_counts[pub] = publisher_counts.get(pub, 0) + 1
        title = str(r.get("title") or r.get("headline") or "")
        if any(kw in title.lower() for kw in _CATALYST_KEYWORDS):
            has_catalyst = True

    sorted_pubs = sorted(
        publisher_counts.items(), key=lambda kv: kv[1], reverse=True,
    )[:3]
    return {
        "ticker": ticker,
        "n_headlines": n_headlines,
        "n_unique_domains": len(publisher_counts),
        "top_publishers": [p[0] for p in sorted_pubs],
        "has_catalyst_news": has_catalyst,
        "warnings": warnings,
    }
