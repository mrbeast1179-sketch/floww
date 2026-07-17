"""
backend/tests/services/test_news_feed.py

Pure-Python unit tests for ``services.news_feed``. All HTTP is mocked via
``unittest.mock.patch`` — no network. Mirrors the canonical insider
scraper test pattern (defensive, mocked, no shared state).
"""

from __future__ import annotations

import urllib.error
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup

from services.news_feed import (
    _fetch_html,
    _parse_headlines,
    _parse_paragraphs,
    accumulate_today,
    compute_news_summary,
    fetch_article_text,
    fetch_ticker_news,
    init_news_daily_table,
    read_recent_news,
)

# ─────────────────────────────────────────────────────────────────────
# Helpers — keep mocks terse.
# ─────────────────────────────────────────────────────────────────────


def _mocked_urlopen(html: str = "<html></html>"):
    """Return a context-manager mock whose .read() returns ``html``."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = html.encode("utf-8")
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_resp
    return mock_cm


# ─────────────────────────────────────────────────────────────────────
# fetch_ticker_news — happy paths.
# ─────────────────────────────────────────────────────────────────────


def test_fetch_ticker_news_extracts_yahoo_native_layout():
    """Yahoo wraps headlines in <a><h3>...</h3></a>; capture both titles."""
    html = """
    <html><body>
        <a href="/news/test-article-1.html"><h3>Apple announces new iPhone</h3></a>
        <div>Bloomberg • 2 hours ago</div>
        <a href="https://external.com/article"><h3>External article about AAPL</h3></a>
        <div>Reuters</div>
    </body></html>
    """
    with patch("urllib.request.urlopen", return_value=_mocked_urlopen(html)):
        rows = fetch_ticker_news("AAPL", limit=10)

    assert len(rows) == 2
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["title"] == "Apple announces new iPhone"
    assert rows[0]["url"].startswith("http")
    assert "Bloomberg" in rows[0]["publisher"]
    assert rows[1]["title"] == "External article about AAPL"
    assert rows[1]["url"] == "https://external.com/article"


def test_fetch_ticker_news_dedupes_by_url():
    """Same URL appearing twice should appear only once in output."""
    html = """
    <html><body>
        <a href="/news/same.html"><h3>Title A</h3></a>
        <a href="/news/same.html"><h3>Title A duplicate</h3></a>
        <a href="/news/different.html"><h3>Title B</h3></a>
    </body></html>
    """
    with patch("urllib.request.urlopen", return_value=_mocked_urlopen(html)):
        rows = fetch_ticker_news("TSLA", limit=10)

    assert len(rows) == 2
    urls = [r["url"] for r in rows]
    assert urls[0] == "https://finance.yahoo.com/news/same.html"
    assert urls[1] == "https://finance.yahoo.com/news/different.html"


def test_fetch_ticker_news_respects_limit():
    """`limit` should cap the result list to the requested count."""
    html = """
    <html><body>
        <a href="/news/a.html"><h3>Headline 1</h3></a>
        <a href="/news/b.html"><h3>Headline 2</h3></a>
        <a href="/news/c.html"><h3>Headline 3</h3></a>
    </body></html>
    """
    with patch("urllib.request.urlopen", return_value=_mocked_urlopen(html)):
        rows = fetch_ticker_news("NVDA", limit=2)

    assert len(rows) == 2


def test_fetch_ticker_news_uppercases_ticker_in_output():
    """Lowercase ticker in should uppercase in output ticker field."""
    html = '<html><body><a href="/news/x.html"><h3>Some headline</h3></a></body></html>'
    with patch("urllib.request.urlopen", return_value=_mocked_urlopen(html)):
        rows = fetch_ticker_news("msft", limit=5)

    assert len(rows) == 1
    assert rows[0]["ticker"] == "MSFT"


# ─────────────────────────────────────────────────────────────────────
# fetch_ticker_news — defensive / failure paths.
# ─────────────────────────────────────────────────────────────────────


def test_fetch_ticker_news_http_429_graceful_degrade():
    """Yahoo rate-limiting (429) should return [] not raise."""
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            "url", 429, "Too Many Requests", {}, None,
        ),
    ):
        rows = fetch_ticker_news("NVDA", limit=5)
    assert rows == []


def test_fetch_ticker_news_http_403_graceful_degrade():
    """Yahoo blocking (403) should return [] not raise."""
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            "url", 403, "Forbidden", {}, None,
        ),
    ):
        rows = fetch_ticker_news("AAPL", limit=5)
    assert rows == []


def test_fetch_ticker_news_empty_html_returns_empty():
    """Empty Yahoo page should yield [] without crashing."""
    with patch("urllib.request.urlopen", return_value=_mocked_urlopen("<html></html>")):
        rows = fetch_ticker_news("MSFT", limit=10)
    assert rows == []


def test_fetch_ticker_news_malformed_html_graceful():
    """Heavily malformed HTML (no <a>, no <h3>) should return []."""
    html = "<html><body>random junk no headlines here</body></html>"
    with patch("urllib.request.urlopen", return_value=_mocked_urlopen(html)):
        rows = fetch_ticker_news("XYZ", limit=10)
    assert rows == []


def test_fetch_ticker_news_handles_h2_in_addition_to_h3():
    """Yahoo occasionally uses <h2> instead of <h3>; capture both."""
    html = """
    <html><body>
        <a href="/news/h3.html"><h3>From h3</h3></a>
        <a href="/news/h2.html"><h2>From h2</h2></a>
    </body></html>
    """
    with patch("urllib.request.urlopen", return_value=_mocked_urlopen(html)):
        rows = fetch_ticker_news("META", limit=10)
    assert len(rows) == 2
    titles = {r["title"] for r in rows}
    assert titles == {"From h3", "From h2"}


# ─────────────────────────────────────────────────────────────────────
# fetch_article_text — happy + edge paths.
# ─────────────────────────────────────────────────────────────────────


def test_fetch_article_text_yahoo_native_caas_body():
    """Yahoo's <div class='caas-body'> should be extracted preferentially."""
    html = """
    <html><body>
        <div class="caas-body">
            <p>First paragraph here.</p>
            <p>Second paragraph here.</p>
            <p>Third paragraph here.</p>
        </div>
    </body></html>
    """
    with patch("urllib.request.urlopen", return_value=_mocked_urlopen(html)):
        res = fetch_article_text(
            "http://finance.yahoo.com/news/123", max_paragraphs=2,
        )

    assert res["url"] == "http://finance.yahoo.com/news/123"
    assert len(res["paragraphs"]) == 2
    assert res["paragraphs"][0] == "First paragraph here."
    assert res["warnings"] == []


def test_fetch_article_text_generic_external_fallback():
    """Non-Yahoo pages fall back to <p> walks with a length floor."""
    html = """
    <html><body>
        <p>Short UI</p>
        <p>
            This is a much longer paragraph that represents generic
            content on an external site that we are scraping.
        </p>
    </body></html>
    """
    with patch("urllib.request.urlopen", return_value=_mocked_urlopen(html)):
        res = fetch_article_text("http://external.com", max_paragraphs=5)

    # Short UI paragraph must be filtered (>40 char floor).
    assert len(res["paragraphs"]) == 1
    assert res["paragraphs"][0].startswith(
        "This is a much longer paragraph"
    )


def test_fetch_article_text_paywall_yields_warning():
    """Paywalled page with no extractable paragraphs yields a warning."""
    html = """
    <html><body>
        <p>Subscribe to read this article.</p>
    </body></html>
    """
    with patch("urllib.request.urlopen", return_value=_mocked_urlopen(html)):
        res = fetch_article_text("http://paywalled.com", max_paragraphs=5)

    assert res["paragraphs"] == []
    assert any(
        "paywall" in w.lower() or "no article paragraphs" in w.lower()
        for w in res["warnings"]
    )


def test_fetch_article_text_http_404_graceful():
    """Article URL returning 404 should yield empty paragraphs + warning."""
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            "url", 404, "Not Found", {}, None,
        ),
    ):
        res = fetch_article_text("http://finance.yahoo.com/news/missing")

    assert res["paragraphs"] == []
    assert len(res["warnings"]) >= 1


# ─────────────────────────────────────────────────────────────────────
# Internal parser helpers (pure-logic, no mocking needed).
# ─────────────────────────────────────────────────────────────────────


def test_parse_headlines_skips_orphan_h3_without_link():
    """An <h3> without an <a> ancestor should not be captured."""
    html = (
        '<html><body>'
        '<h3>Orphan headline</h3>'
        '<a href="/news/x.html"><h3>Linked headline</h3></a>'
        '</body></html>'
    )
    soup = BeautifulSoup(html, "html.parser")
    rows = _parse_headlines(soup, ticker="SPY")
    assert len(rows) == 1
    assert rows[0]["title"] == "Linked headline"


def test_parse_paragraphs_filters_short_p_when_no_caas_body():
    """Generic <p> walk applies the 40-char length floor."""
    html = (
        "<html><body>"
        "<p>too short</p>"
        "<p>" + ("a" * 50) + "</p>"
        "</body></html>"
    )
    soup = BeautifulSoup(html, "html.parser")
    paras = _parse_paragraphs(soup)
    assert len(paras) == 1
    assert paras[0] == "a" * 50


# ─────────────────────────────────────────────────────────────────────
# DuckDB I/O — init / accumulate / read.
# ─────────────────────────────────────────────────────────────────────


def test_init_news_daily_table_creates_tables_and_indexes():
    """init_news_daily_table issues CREATE TABLE for both tables + 2 indexes."""
    engine = MagicMock()
    init_news_daily_table(engine)
    sqls = [c.args[0] for c in engine.execute_write.call_args_list]
    assert len(sqls) == 4
    assert any(
        "CREATE TABLE IF NOT EXISTS news_daily" in s for s in sqls
    )
    assert any(
        "CREATE TABLE IF NOT EXISTS news_html_cache" in s for s in sqls
    )
    assert any("idx_news_ticker" in s for s in sqls)
    assert any("idx_news_date" in s for s in sqls)


def test_accumulate_today_upserts_with_proper_params():
    """accumulate_today issues UPSERT with snapshot_date + uppercased ticker."""
    engine = MagicMock()
    rows = [{
        "ticker": "spy", "title": "Headline 1",
        "url": "https://example.com/1", "publisher": "Reuters",
        "scraped_at": "2026-07-15T10:00:00+00:00",
    }]
    n = accumulate_today(
        engine, rows, snapshot_date=date(2026, 7, 15),
    )
    assert n == 1
    call = engine.execute_write.call_args
    sql = call.args[0]
    params = call.args[1]
    assert "INSERT INTO news_daily" in sql
    assert "ON CONFLICT" in sql
    assert params[0][0] == date(2026, 7, 15)
    assert params[0][1] == "SPY"          # uppercased
    assert params[0][2] == "Headline 1"
    assert params[0][3] == "https://example.com/1"
    assert params[0][4] == "Reuters"


def test_accumulate_today_drops_rows_missing_ticker_or_url():
    """Rows missing ticker or url are silently dropped (return 0)."""
    engine = MagicMock()
    rows = [
        {"ticker": "", "url": "https://example.com/1"},  # no ticker
        {"ticker": "SPY", "url": ""},                    # no url
        {"ticker": "AAPL", "url": "https://example.com/2"},  # valid
    ]
    n = accumulate_today(engine, rows, snapshot_date=date(2026, 7, 15))
    assert n == 1   # only the AAPL row qualifies
    params = engine.execute_write.call_args.args[1]
    assert len(params) == 1
    assert params[0][1] == "AAPL"


def test_accumulate_today_empty_rows_no_op():
    """accumulate_today([]) returns 0 and does NOT call execute_write."""
    engine = MagicMock()
    n = accumulate_today(engine, [], snapshot_date=date(2026, 7, 15))
    assert n == 0
    engine.execute_write.assert_not_called()


def test_accumulate_today_idempotent_same_day():
    """Two accumulates on the same snapshot_date + URL UPSERT (no duplicates)."""
    engine = MagicMock()
    rows = [{
        "ticker": "SPY", "title": "Original",
        "url": "https://example.com/x", "publisher": "Reuters",
        "scraped_at": "2026-07-15T10:00:00+00:00",
    }]
    accumulate_today(engine, rows, snapshot_date=date(2026, 7, 15))
    rows[0]["title"] = "Updated"
    accumulate_today(engine, rows, snapshot_date=date(2026, 7, 15))
    # Both calls should issue UPSERT_SQL (the idempotency is DB-side).
    assert engine.execute_write.call_count == 2
    for c in engine.execute_write.call_args_list:
        assert "ON CONFLICT" in c.args[0]


def test_read_recent_news_passes_correct_sql():
    """read_recent_news issues SELECT with ticker param + LIMIT."""
    engine = MagicMock()
    engine.query.return_value = []
    rows = read_recent_news(engine, "SPY", n_days=14)
    assert rows == []
    call = engine.query.call_args
    sql = call.args[0]
    params = call.args[1]
    assert "FROM news_daily" in sql
    assert "WHERE ticker = ?" in sql
    assert "ORDER BY snapshot_date ASC" in sql
    assert params[0] == "SPY"
    assert params[1] == 14 * 30   # n_days * 30 cap


def test_read_recent_news_returns_rows_asc_chronological():
    """read_recent_news returns engine.query result as-is (DB-side ASC)."""
    engine = MagicMock()
    engine.query.return_value = [
        {"snapshot_date": date(2026, 7, 14), "ticker": "SPY",
         "headline": "Old", "url": "u1", "publisher": "Reuters",
         "scraped_at": datetime(2026, 7, 14, 10, 0)},
        {"snapshot_date": date(2026, 7, 15), "ticker": "SPY",
         "headline": "New", "url": "u2", "publisher": "Reuters",
         "scraped_at": datetime(2026, 7, 15, 10, 0)},
    ]
    rows = read_recent_news(engine, "SPY", n_days=14)
    assert len(rows) == 2
    assert rows[0]["headline"] == "Old"
    assert rows[1]["headline"] == "New"


def test_read_recent_news_db_exception_yields_empty():
    """If engine.query raises, read_recent_news returns [] not propagate."""
    engine = MagicMock()
    engine.query.side_effect = Exception("DuckDB connection lost")
    rows = read_recent_news(engine, "SPY", n_days=14)
    assert rows == []


# ─────────────────────────────────────────────────────────────────────
# HTML cache — 24h TTL + LRU eviction.
# ─────────────────────────────────────────────────────────────────────


def test_cache_within_TTL_returns_cached_html():
    """Within TTL, _fetch_html returns cached HTML without hitting network."""
    engine = MagicMock()
    engine.query.return_value = [{
        "html_content": "<html>CACHED</html>",
        "fetched_at": datetime.now(),   # fresh — age < 24h
    }]
    with patch("urllib.request.urlopen") as mock_open:
        result = _fetch_html(
            "https://test.com", "UA", [], cache_engine=engine,
        )
    assert result == "<html>CACHED</html>"
    mock_open.assert_not_called()


def test_cache_stale_refetches_html_and_updates_cache():
    """After TTL expires, _fetch_html refetches + writes fresh HTML to cache."""
    engine = MagicMock()
    engine.query.return_value = [{
        "html_content": "<html>OLD</html>",
        "fetched_at": datetime.now() - timedelta(days=2),  # stale
    }]
    with patch(
        "urllib.request.urlopen",
        return_value=_mocked_urlopen("<html>NEW</html>"),
    ):
        result = _fetch_html(
            "https://test.com", "UA", [], cache_engine=engine,
        )
    assert result == "<html>NEW</html>"
    # Both the SELECT (cache lookup) AND the INSERT (cache write) should fire.
    sqls = [
        c.args[0] for c in engine.execute_write.call_args_list
    ]
    assert any("INSERT INTO news_html_cache" in s for s in sqls)


def test_cache_read_exception_falls_through_to_fetch():
    """If cache read raises, _fetch_html still proceeds to network fetch."""
    engine = MagicMock()
    engine.query.side_effect = Exception("Cache read error")
    with patch(
        "urllib.request.urlopen",
        return_value=_mocked_urlopen("<html>FRESH</html>"),
    ):
        result = _fetch_html(
            "https://test.com", "UA", [], cache_engine=engine,
        )
    assert result == "<html>FRESH</html>"


# ─────────────────────────────────────────────────────────────────────
# Pure-logic compute_news_summary.
# ─────────────────────────────────────────────────────────────────────


def test_compute_news_summary_empty():
    """Empty rows yields all-zero summary."""
    out = compute_news_summary("SPY", [])
    assert out["n_headlines"] == 0
    assert out["n_unique_domains"] == 0
    assert out["top_publishers"] == []
    assert out["has_catalyst_news"] is False


def test_compute_news_summary_groups_by_publisher_top_3():
    """Distinct publishers counted; top-3 returned in DESC order."""
    rows = [
        {"publisher": "Reuters", "title": "A"},
        {"publisher": "Reuters", "title": "B"},
        {"publisher": "Bloomberg", "title": "C"},
        {"publisher": "Yahoo", "title": "D"},
        {"publisher": "Yahoo", "title": "E"},
        {"publisher": "Yahoo", "title": "F"},
    ]
    out = compute_news_summary("SPY", rows)
    assert out["n_headlines"] == 6
    assert out["n_unique_domains"] == 3
    assert out["top_publishers"] == ["Yahoo", "Reuters", "Bloomberg"]


def test_compute_news_summary_catalyst_keyword_detected():
    """Earnings / FDA / merger / upgrade keywords trigger catalyst flag."""
    rows = [
        {"publisher": "Reuters", "title": "Apple reports record earnings"},
    ]
    out = compute_news_summary("AAPL", rows)
    assert out["has_catalyst_news"] is True


def test_compute_news_summary_no_catalyst_generic_headline():
    """Generic market chatter yields has_catalyst_news=False."""
    rows = [
        {"publisher": "Reuters", "title": "Stocks trade sideways on low volume"},
    ]
    out = compute_news_summary("SPY", rows)
    assert out["has_catalyst_news"] is False


def test_compute_news_summary_skips_non_dict_rows():
    """Non-dict entries are skipped with a warning rather than crashing."""
    rows = [
        {"publisher": "Reuters", "title": "Valid"},
        "not a dict",
        None,
    ]
    out = compute_news_summary("SPY", rows)
    assert out["n_headlines"] == 1
    assert any("non-dict row skipped" in w for w in out["warnings"])
