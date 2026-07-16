"""
backend/services/occ_scraper.py — Steal-list #14.

OCC (Options Clearing Corporation) cleared-volume intelligence: a daily
T+1 market-wide CSV that reveals WHO traded each option (Customer / Firm /
Market-Maker). Pulls https://marketdata.theocc.com/volume-query once a day
via ``requests`` + browser User-Agent, caches the raw CSV text in DuckDB
for 24 h, parses into a wide 10-column row per (trade_date, ticker), and
exposes pure-logic summary analytics for ``/api/occ_volume/{ticker}``.

Steal from
----------
``EazyDuz1t_EzOptions/ezoptions.py``
  - ``get_params_for_date``        (L3793): volumeQueryType=O, accountType=A,
    reportType=D, reportDate=YYYY-MM-DD. We use ALL-account-types (A)
    in one fetch then local-aggregate, mirroring the insurance that
    EzOptions' per-account approach provides at lower network cost.
  - ``download_volume_csv``        (L4010): requests.get with browser UA,
    5-business-day rewind fallback. We honor both verbatim.
  - ``process_market_maker_data``  (L3819): pandas column recognition
    (Quantity / Underlying_Symbol / Account_Type / Call_Put_Indicator).
    Replaced with ``csv.DictReader`` so the parser is dependency-light
    and survives column-name drift (Quantity vs Volume, etc.).

Mirrors the canonical pattern of ``backend/services/insider_scraper.py``
(init + accumulate + read_recent + fetch + cache + defensive parser +
zero-state summary), keeping the public surface isomorphic to the
Finviz scraper so the steal-three router can dispatch cleanly.

Steal intent
------------
This is the only genuinely NEW free data-source in the steal-list batch:
yfinance aggregate volume/OI can never reveal dealer vs customer
positioning. Layered onto the Skylit Row 3 alongside max-pain drift,
consensus drift, insider pressure, and strike cone, it gives floww a
"Who traded" lens that no current module provides.
"""

from __future__ import annotations

import logging
from csv import DictReader
from datetime import date, datetime, timedelta
from io import StringIO
from typing import Any

try:
    import requests
    _REQUESTS_IMPORT_ERROR: Exception | None = None
except ImportError as _exc:
    _REQUESTS_IMPORT_ERROR = _exc

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Module-level constants — DO NOT drift.
# CACHE_TTL_SECONDS = 24 h because OCC's volume report is daily T+1.
# FALLBACK_DAYS = 5 mirrors EzOptions' max-age fallback for weekends /
# US market holidays.
# ----------------------------------------------------------------------
TABLE_NAME = "occ_volume_daily"
CACHE_TABLE_NAME = "occ_csv_cache"
CACHE_TTL_SECONDS = 86400
OCC_BASE_URL = "https://marketdata.theocc.com/volume-query"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT_S = 10
FALLBACK_DAYS = 5


# ----------------------------------------------------------------------
# DuckDB ledger helpers (mirrors insider_scraper pattern).
# Wide schema = 8 volume BIGINTs per row so reads don't need GROUP BY.
# ----------------------------------------------------------------------
def init_occ_daily_table(engine) -> None:
    """Idempotent CREATE TABLE IF NOT EXISTS for both the ledger and the
    request-text cache."""
    engine.execute_write(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            trade_date        DATE,
            ticker            VARCHAR,
            customer_call_vol BIGINT,
            customer_put_vol  BIGINT,
            firm_call_vol     BIGINT,
            firm_put_vol      BIGINT,
            mm_call_vol       BIGINT,
            mm_put_vol        BIGINT,
            total_call_vol    BIGINT,
            total_put_vol     BIGINT,
            PRIMARY KEY (trade_date, ticker)
        );
        """
    )
    engine.execute_write(
        f"""
        CREATE TABLE IF NOT EXISTS {CACHE_TABLE_NAME} (
            url        VARCHAR PRIMARY KEY,
            csv_text   VARCHAR,
            fetched_at TIMESTAMP
        );
        """
    )


def accumulate_today(engine, rows: list[dict[str, Any]], snapshot_date: date | None = None) -> int:
    """UPSERT today's wide row(s) into ``occ_volume_daily``."""
    if not rows:
        return 0
    if snapshot_date is None:
        snapshot_date = date.today()
    n = 0
    for row in rows:
        engine.execute_write(
            f"""
            INSERT INTO {TABLE_NAME} (
                trade_date, ticker,
                customer_call_vol, customer_put_vol,
                firm_call_vol, firm_put_vol,
                mm_call_vol, mm_put_vol,
                total_call_vol, total_put_vol
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (trade_date, ticker) DO UPDATE SET
                customer_call_vol = EXCLUDED.customer_call_vol,
                customer_put_vol  = EXCLUDED.customer_put_vol,
                firm_call_vol     = EXCLUDED.firm_call_vol,
                firm_put_vol      = EXCLUDED.firm_put_vol,
                mm_call_vol       = EXCLUDED.mm_call_vol,
                mm_put_vol        = EXCLUDED.mm_put_vol,
                total_call_vol    = EXCLUDED.total_call_vol,
                total_put_vol     = EXCLUDED.total_put_vol;
            """,
            (
                snapshot_date,
                row.get("ticker") or "",
                int(row.get("customer_call_vol") or 0),
                int(row.get("customer_put_vol") or 0),
                int(row.get("firm_call_vol") or 0),
                int(row.get("firm_put_vol") or 0),
                int(row.get("mm_call_vol") or 0),
                int(row.get("mm_put_vol") or 0),
                int(row.get("total_call_vol") or 0),
                int(row.get("total_put_vol") or 0),
            ),
        )
        n += 1
    return n


def read_recent_occ(engine, ticker: str | None = None, n_days: int = 14) -> list[dict[str, Any]]:
    """Read the last ``n_days`` rows (ASC natural drift order).

    When ``ticker`` is provided, filters to that ticker. When None, returns
    market-wide rows (every distinct ticker per trade_date).
    """
    if ticker is not None:
        rows = engine.execute_query(
            f"""
            SELECT * FROM {TABLE_NAME}
            WHERE ticker = ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (ticker, int(n_days)),
        )
        return list(reversed(rows))
    rows = engine.execute_query(
        f"""
        SELECT * FROM {TABLE_NAME}
        ORDER BY trade_date DESC
        LIMIT ?
        """,
        (int(n_days),),
    )
    return list(reversed(rows))


# ----------------------------------------------------------------------
# HTTP + cache helpers.
# ----------------------------------------------------------------------
def _get_cached_csv(engine, url: str) -> str | None:
    """Return the cached CSV text if fresh (< CACHE_TTL_SECONDS old)."""
    try:
        rows = engine.execute_query(
            f"SELECT csv_text, fetched_at FROM {CACHE_TABLE_NAME} WHERE url = ? LIMIT 1",
            (url,),
        )
    except Exception:
        return None
    if not rows:
        return None
    rec = rows[0]
    if isinstance(rec, dict):
        csv_text = rec.get("csv_text")
        fetched_at = rec.get("fetched_at")
    else:
        csv_text, fetched_at = rec[0], rec[1]
    if not csv_text:
        return None
    try:
        if hasattr(fetched_at, "timestamp"):
            age_s = (datetime.now() - fetched_at).total_seconds()
        else:
            age_s = CACHE_TTL_SECONDS + 1
    except Exception:
        age_s = CACHE_TTL_SECONDS + 1
    return csv_text if age_s < CACHE_TTL_SECONDS else None


def _store_cached_csv(engine, url: str, csv_text: str) -> None:
    """Best-effort UPSERT of raw CSV text for DEDUP."""
    try:
        engine.execute_write(
            f"""
            INSERT INTO {CACHE_TABLE_NAME} (url, csv_text, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT (url) DO UPDATE SET
                csv_text   = EXCLUDED.csv_text,
                fetched_at = EXCLUDED.fetched_at;
            """,
            (url, csv_text, datetime.now()),
        )
    except Exception as exc:
        logger.debug("occ: cache store failed for %s: %s", url, exc)


def _get_params_for_date(report_date: date) -> dict[str, str]:
    """OCC volume-query GET params (mirrors EzOptions``ezoptions.py`` L3793)."""
    return {
        "volumeQueryType": "O",   # O = Options (vs F = Futures)
        "accountType":     "A",   # A = All account types
        "reportType":      "D",   # D = Daily granularity
        "reportDate":      report_date.strftime("%Y-%m-%d"),
    }


def _next_business_day(d: date) -> date:
    """OCC's volume is published T+1 weekdays. Rewind past weekends."""
    while d.weekday() >= 5:       # 5=Sat, 6=Sun => Friday
        d -= timedelta(days=1)
    return d


def _fetch_occ_csv(report_date: date, cache_engine=None, warnings: list[str] | None = None) -> str | None:
    """Fetch + cache the OCC daily CSV. Up to FALLBACK_DAYS business days rewind."""
    if warnings is None:
        warnings = []
    if _REQUESTS_IMPORT_ERROR is not None:
        warnings.append(
            f"OCC fetch unavailable: requests not installed ({_REQUESTS_IMPORT_ERROR})"
        )
        return None
    target = _next_business_day(report_date)
    for attempt in range(FALLBACK_DAYS):
        params = _get_params_for_date(target)
        url = OCC_BASE_URL + f"?{target.isoformat()}"
        if cache_engine is not None:
            cached = _get_cached_csv(cache_engine, url)
            if cached is not None:
                return cached
        try:
            resp = requests.get(
                OCC_BASE_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_S,
            )
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            warnings.append(f"OCC fetch error attempt={attempt}: {exc.__class__.__name__}")
            target -= timedelta(days=1)
            continue
        if resp.status_code != 200 or not resp.text or len(resp.text) < 32:
            warnings.append(f"OCC non-200 attempt={attempt}: status={resp.status_code}")
            target -= timedelta(days=1)
            continue
        if cache_engine is not None:
            _store_cached_csv(cache_engine, url, resp.text)
        return resp.text
    warnings.append("OCC empty for date")
    return None


# ----------------------------------------------------------------------
# Pure-logic CSV parser (network/db-free).
# ----------------------------------------------------------------------
def _parse_quantity(raw: Any) -> int:
    """Coerce a quantity cell to a non-negative int. Falls back to 0."""
    if raw is None:
        return 0
    try:
        s = str(raw).strip().replace(",", "").replace('"', "").replace("'", "")
        return max(int(float(s)), 0)
    except (ValueError, TypeError, AttributeError):
        return 0


def _parse_occ_market_csv(csv_text: str, target_ticker: str, warnings: list[str]) -> list[dict[str, Any]]:
    """Parse OCC CSV → list of wide 10-column dicts (one per ticker with data).

    Defensive against column drift — tries multiple header names so the
    parser keeps working if OCC renames a column.
    """
    if not csv_text:
        warnings.append("OCC empty for date")
        return []
    # Strip OCC's preamble: lines before the actual header (header has
    # Underlying/Volume/Quantity substring).
    cleaned: list[str] = []
    header_seen = False
    for raw_line in csv_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not header_seen:
            if any(tok in line for tok in ("Underlying", "Symbol", "Volume", "Quantity")):
                header_seen = True
                cleaned.append(line)
            continue
        cleaned.append(line)
    if not header_seen:
        warnings.append("OCC CSV missing header line")
        return []
    text_clean = "\n".join(cleaned)
    target_upper = (target_ticker or "").upper()
    buckets: dict[str, dict[str, int]] = {}
    try:
        reader = DictReader(StringIO(text_clean))
    except Exception as exc:
        warnings.append(f"OCC CSV parse failed: {exc}")
        return []
    if not reader.fieldnames:
        warnings.append("OCC CSV no fieldnames")
        return []
    fmap = {h.strip(): h for h in reader.fieldnames}
    sym_key  = fmap.get("Underlying_Symbol") or fmap.get("Symbol") or fmap.get("Underlying")
    qty_key  = fmap.get("Quantity")          or fmap.get("Volume")
    cp_key   = fmap.get("Call_Put_Indicator") or fmap.get("Cp") or fmap.get("Call_Put") or fmap.get("P_C")
    acct_key = fmap.get("Account_Type")      or fmap.get("Acct") or fmap.get("Account")
    if not (sym_key and qty_key and cp_key and acct_key):
        warnings.append("OCC CSV missing critical columns")
        return []
    try:
        for r in reader:
            sym = str(r.get(sym_key) or "").strip().upper()
            if target_upper and sym != target_upper:
                continue
            qty = _parse_quantity(r.get(qty_key))
            cp = str(r.get(cp_key) or "").strip().upper()
            acct = str(r.get(acct_key) or "").strip().upper()
            bucket = buckets.setdefault(target_upper, {
                "customer_call_vol": 0, "customer_put_vol": 0,
                "firm_call_vol": 0, "firm_put_vol": 0,
                "mm_call_vol": 0, "mm_put_vol": 0,
            })
            if cp.startswith("C"):
                side = "call"
            elif cp.startswith("P"):
                side = "put"
            else:
                continue
            if acct.startswith("C"):
                bucket["customer_" + side + "_vol"] += qty
            elif acct.startswith("F"):
                bucket["firm_" + side + "_vol"] += qty
            elif acct.startswith("M"):
                bucket["mm_" + side + "_vol"] += qty
            # Account codes outside {C, F, M} silently dropped (no schema bloat).
    except Exception as exc:
        warnings.append(f"OCC CSV row iteration failed: {exc}")
        return []
    out: list[dict[str, Any]] = []
    for sym, b in buckets.items():
        tc = b["customer_call_vol"] + b["firm_call_vol"] + b["mm_call_vol"]
        tp = b["customer_put_vol"]  + b["firm_put_vol"]  + b["mm_put_vol"]
        out.append({
            "ticker":               sym,
            "customer_call_vol":    b["customer_call_vol"],
            "customer_put_vol":     b["customer_put_vol"],
            "firm_call_vol":        b["firm_call_vol"],
            "firm_put_vol":         b["firm_put_vol"],
            "mm_call_vol":          b["mm_call_vol"],
            "mm_put_vol":           b["mm_put_vol"],
            "total_call_vol":       tc,
            "total_put_vol":        tp,
        })
    return out


def fetch_ticker_occ(ticker: str, target_date: date | None = None, cache_engine=None) -> list[dict[str, Any]]:
    """Public fetch helper. Returns wide rows for the ticker across all
    dates parsed (single-date fetch returns 0..1 row)."""
    target = target_date if target_date is not None else (date.today() - timedelta(days=1))
    warnings: list[str] = []
    csv_text = _fetch_occ_csv(target, cache_engine=cache_engine, warnings=warnings)
    if not csv_text:
        return []
    return _parse_occ_market_csv(csv_text, ticker.upper(), warnings)


# ----------------------------------------------------------------------
# Pure-logic summary (DB-free, called from the route handler).
# ----------------------------------------------------------------------
def _safe_ratio(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return num / den


def compute_occ_summary(ticker: str | None, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the most recent row's volumes + lifecycle metrics.

    Returns keys the tile reads: ``customer_pct_of_total``, ``mm_net_bias``,
    ``mm_call_put_ratio``, ``customer_call_put_ratio``. Plus
    ``recent_total_volume``, ``n_days_covered``, ``warnings``.
    """
    if not rows:
        return {
            "ticker": ticker,
            "customer_pct_of_total": 0.0,
            "mm_net_bias": "neutral",
            "mm_call_put_ratio": 0.0,
            "customer_call_put_ratio": 0.0,
            "recent_total_volume": 0,
            "n_days_covered": 0,
            "warnings": [],
        }
    latest = rows[-1]
    cust_c = latest.get("customer_call_vol") or 0
    cust_p = latest.get("customer_put_vol") or 0
    firm_c = latest.get("firm_call_vol") or 0
    firm_p = latest.get("firm_put_vol") or 0
    mm_c = latest.get("mm_call_vol") or 0
    mm_p = latest.get("mm_put_vol") or 0
    total = cust_c + cust_p + firm_c + firm_p + mm_c + mm_p
    customer_total = cust_c + cust_p
    cust_pct = _safe_ratio(customer_total * 100.0, total)
    mm_ratio = _safe_ratio(mm_c, mm_p)
    cust_ratio = _safe_ratio(cust_c, cust_p)
    if total == 0:
        bias = "neutral"
    elif mm_p > mm_c * 1.15:
        bias = "bearish"        # ≥15% put-skew = dealers net short calls
    elif mm_c > mm_p * 1.15:
        bias = "bullish"        # ≥15% call-skew = dealers net long puts
    else:
        bias = "neutral"
    return {
        "ticker": ticker,
        "customer_pct_of_total": round(cust_pct, 1),
        "mm_net_bias": bias,
        "mm_call_put_ratio": round(mm_ratio, 2),
        "customer_call_put_ratio": round(cust_ratio, 2),
        "recent_total_volume": int(total),
        "n_days_covered": len(rows),
        "warnings": [],
    }
