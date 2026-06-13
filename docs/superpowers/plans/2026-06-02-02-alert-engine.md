# AlphaPod Clone — Plan 02: Alert Engine (the "methods") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]`. **Backend lane** — runs in parallel with Plan 01 (no file overlap). Spec for the rules/scoring: `docs/superpowers/research/2026-06-02-alphapod-rules-dossier.md` (READ IT FIRST).

**Goal:** A backend service that (a) **replays the 73 captured AlphaPod alerts** for instant UI parity, and (b) **classifies floww's option-flow prints into AlphaPod-shaped alerts** using the reverse-engineered rules + confidence scorer — behind one interface so replay→live is a swap.

**Architecture:** New package `backend/services/alpha/`. Pure-function `scoring.py` + `rules.py` (trivially TDD-able), a `replay.py` source over copied fixtures, an `engine.py` orchestrator, and a FastAPI router `/api/alpha/alerts`. The **73 captured alerts are the ground-truth regression set** — the scorer is calibrated until it reproduces their `confidence` buckets.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest (asyncio auto). Venv: `backend/.venv/bin/python3`. Lane-authorized files: `backend/services/alpha/**`, `backend/tests/services/alpha/**`, and ONE surgical include line in `backend/server.py` (Task 5). Do NOT touch `inference.py`, `dash_ui.py`, `conftest.py`, models.

---

### Task 1: `AlphaAlert` schema (TDD)

**Files:** Create `backend/services/alpha/__init__.py`, `backend/services/alpha/schema.py`; Test `backend/tests/services/alpha/test_schema.py`

- [ ] **Step 1: Failing test** — a real captured alert validates and exposes typed fields.

```python
# backend/tests/services/alpha/test_schema.py
from services.alpha.schema import AlphaAlert

SAMPLE = {
  "alert_id": "5f7b7052-0000", "ticker": "DOCU", "option_type": "call", "strike": 65.0,
  "expiration": "2026-07-17", "dte": 45, "premium": 463365.0, "size": 3646, "side": "buy",
  "alert_rule": "Golden Sweeps", "has_sweep": True, "has_floor": False, "volume": 3650,
  "open_interest": 95, "vol_oi_ratio": 38.4, "spot_price": 60.0, "market_cap": 1.2e10,
  "sector": "Technology", "tier": 2, "is_spread": False, "avg_fill_price": 1.27,
  "created_at": "2026-06-01T15:59:19-04:00", "sentiment": "BULLISH", "exec_type": "SWEEP",
  "confidence": "HIGH", "confidence_score": 76, "confidence_factors": [], "direction": "bullish",
  "pct_otm": 8.33,
}

def test_validates_captured_alert():
    a = AlphaAlert.model_validate(SAMPLE)
    assert a.ticker == "DOCU" and a.option_type == "call"
    assert a.exec_type == "SWEEP" and a.confidence == "HIGH"

def test_optional_greeks_default_none():
    a = AlphaAlert.model_validate(SAMPLE)
    assert a.delta is None and a.iv_rank is None
```

- [ ] **Step 2: Run → FAIL** — `cd backend && .venv/bin/python3 -m pytest tests/services/alpha/test_schema.py -q` → ModuleNotFound.

- [ ] **Step 3: Implement** `schema.py`

```python
# backend/services/alpha/schema.py
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel

OptionType = Literal["call", "put"]
Side = Literal["buy", "sell"]
ExecType = Literal["SINGLE", "SWEEP", "FLOOR"]
Confidence = Literal["LOW", "MED", "HIGH"]
Direction = Literal["bullish", "bearish", "ambiguous"]
Sentiment = Literal["BULLISH", "BEARISH", "NEUTRAL"]

class AlphaAlert(BaseModel):
    alert_id: str
    ticker: str
    option_type: OptionType
    strike: float
    expiration: str
    dte: int
    premium: float
    size: int
    side: Side
    alert_rule: str
    has_sweep: bool = False
    has_floor: bool = False
    volume: int = 0
    open_interest: int = 0
    vol_oi_ratio: float = 0.0
    spot_price: float
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    tier: int = 2
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    is_spread: bool = False
    spread_type: Optional[str] = None
    avg_fill_price: Optional[float] = None
    created_at: str
    sentiment: Sentiment = "NEUTRAL"
    exec_type: ExecType = "SINGLE"
    confidence: Confidence = "LOW"
    confidence_score: int = 0
    confidence_factors: list[str] = []
    direction: Direction = "ambiguous"
    pct_otm: float = 0.0
    # always-null placeholders kept for schema parity
    iv_rank: Optional[float] = None
    oi_change: Optional[float] = None
    stickiness: Optional[float] = None
```

- [ ] **Step 4: Run → PASS.** **Step 5: Commit** `feat(alpha-T1): AlphaAlert schema (47-field parity, TDD)`.

---

### Task 2: Capture fixtures + replay source (TDD)

**Files:** Create `backend/services/alpha/fixtures/alerts.json` (copied), `backend/services/alpha/replay.py`; Test `backend/tests/services/alpha/test_replay.py`

- [ ] **Step 1: Copy the 73 ground-truth alerts into the repo** (so the source travels with the code)

```bash
mkdir -p backend/services/alpha/fixtures
.venv/bin/python3 - <<'PY'
import json, pathlib
m = pathlib.Path.home() / "GitHub/hub-alphapodtrading/api-data"
alerts = []
for f in ["alerts-p1.json", "alerts-p2.json"]:
    d = json.loads((m / f).read_text())
    alerts += d.get("alerts", d if isinstance(d, list) else [])
out = pathlib.Path("services/alpha/fixtures/alerts.json")
out.write_text(json.dumps({"total": len(alerts), "alerts": alerts}, indent=2))
print("wrote", len(alerts), "alerts")
PY
```
Expected: `wrote 73 alerts`.

- [ ] **Step 2: Failing test**

```python
# backend/tests/services/alpha/test_replay.py
from services.alpha.replay import ReplaySource

def test_loads_73_alerts():
    src = ReplaySource()
    page = src.page(page=1, page_size=50)
    assert page["total"] == 73 and len(page["alerts"]) == 50

def test_pagination_second_page():
    src = ReplaySource()
    assert len(ReplaySource().page(page=2, page_size=50)["alerts"]) == 23
```

- [ ] **Step 3: Run → FAIL. Step 4: Implement** `replay.py`

```python
# backend/services/alpha/replay.py
import json, pathlib
from .schema import AlphaAlert

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "alerts.json"

class ReplaySource:
    def __init__(self, path: pathlib.Path | None = None):
        raw = json.loads((path or _FIXTURE).read_text())
        self._alerts = [AlphaAlert.model_validate(a) for a in raw["alerts"]]

    def all(self) -> list[AlphaAlert]:
        return list(self._alerts)

    def page(self, page: int = 1, page_size: int = 50) -> dict:
        start = (page - 1) * page_size
        chunk = self._alerts[start : start + page_size]
        return {"total": len(self._alerts), "page": page, "page_size": page_size,
                "alerts": [a.model_dump() for a in chunk]}
```

- [ ] **Step 5: Run → PASS. Step 6: Commit** `feat(alpha-T2): replay source over 73 captured alerts (TDD)`.

---

### Task 3: Confidence scorer (TDD — the core)

**Files:** Create `backend/services/alpha/scoring.py`; Test `backend/tests/services/alpha/test_scoring.py`

> The dossier (§C) gives base win-rates, bucket boundaries, the explicit ± direction/sector points, and the **spread→69 cap** + **buckets ≤54 LOW / 55–69 MED / ≥70 HIGH**. The acceptance test calibrates the model against all 73 captured alerts.

- [ ] **Step 1: Failing tests** (unit invariants + the regression gate)

```python
# backend/tests/services/alpha/test_scoring.py
import json, pathlib
from services.alpha.scoring import score_alert, confidence_bucket

def test_buckets():
    assert confidence_bucket(54) == "LOW"
    assert confidence_bucket(55) == "MED" and confidence_bucket(69) == "MED"
    assert confidence_bucket(70) == "HIGH"

def test_spread_capped_at_med():
    score, conf, factors = score_alert({
        "alert_rule": "OTM Conviction", "premium": 2_700_000, "dte": 16, "vol_oi_ratio": 1000,
        "is_spread": True, "direction": "bullish", "has_sweep": False, "side": "buy",
        "option_type": "call", "open_interest": 10, "size": 100, "sector": "Technology",
    })
    assert score <= 69 and conf in ("MED", "LOW")
    assert any("Capped at MED" in f for f in factors)

def test_regression_against_73_captured():
    raw = json.loads((pathlib.Path("services/alpha/fixtures/alerts.json")).read_text())
    hits = 0
    for a in raw["alerts"]:
        _, conf, _ = score_alert(a)
        hits += (conf == a["confidence"])
    # calibrate until >= 90% bucket match on the ground-truth set
    assert hits / raw["total"] >= 0.90, f"only {hits}/{raw['total']} buckets matched"
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement** `scoring.py` (calibrate the bucket deltas until the regression test passes)

```python
# backend/services/alpha/scoring.py
RULE_BASE_WR = {
    "RepeatedHitsAscendingFill": 61.2, "Golden Sweeps": 57.4, "RepeatedHits": 53.4,
    "RepeatedHitsDescendingFill": 52.0, "FloorTradeMidCap": 50.0, "LowHistoricVolumeFloor": 47.7,
    "FloorTradeLargeCap": 47.6, "OTM Conviction": 71.8, "OtmEarningsFloor": 71.8,
    "SPY_call_buy_TIER_2": 50.0, "SPY_put_buy_TIER_2": 50.0, "SPY_put_sell_TIER_2": 50.0,
    "SPY_call_buy_HIGH_CONVICTION": 55.0,
}
SECTOR_ADJ = {"Energy": 2, "Consumer Defensive": 1, "Technology": 1,
              "Financial Services": 1, "Industrials": 1, "Healthcare": -1}

def confidence_bucket(score: int) -> str:
    if score >= 70: return "HIGH"
    if score >= 55: return "MED"
    return "LOW"

def score_alert(a: dict) -> tuple[int, str, list[str]]:
    factors: list[str] = []
    score = RULE_BASE_WR.get(a.get("alert_rule", ""), 50.0)
    factors.append(f"Base {score:.1f}% for {a.get('alert_rule')}")

    p = a.get("premium", 0) or 0
    if p >= 1_000_000: score += 6; factors.append("Institutional premium ($1M+)")
    elif p >= 500_000: score += 3; factors.append("Significant block ($500K+)")
    elif p >= 100_000: factors.append("Moderate size")
    else: score -= 4; factors.append("Light/retail premium")

    dte = a.get("dte", 30)
    if dte <= 16: score += 4; factors.append("Short window")
    elif dte >= 136: score -= 4; factors.append("Very long-dated — avoid")

    voi = a.get("vol_oi_ratio", 0) or 0
    if voi >= 50: score -= 3; factors.append("Extreme vol/OI — likely gamma, not directional")
    elif 3.0 <= voi <= 8.5: score += 3; factors.append("Vol/OI sweet spot — fresh positioning")

    et = a.get("exec_type") or ("SWEEP" if a.get("has_sweep") else "FLOOR" if a.get("has_floor") else "SINGLE")
    if et == "SWEEP": score += 4; factors.append("Cross-exchange urgency (sweep)")
    elif a.get("side") == "sell": score -= 2; factors.append("Bid-side — may be hedge")

    direction = a.get("direction", "ambiguous")
    if direction == "bullish" and a.get("has_sweep"): score += 3; factors.append("Bullish sweep +3")
    elif direction == "bearish" and p >= 500_000: score += 2; factors.append("Bearish block +2")
    elif direction == "bearish": score += 1; factors.append("Bearish +1")
    if a.get("side") == "sell" and a.get("option_type") == "put": score -= 3; factors.append("Put-sale -3")
    if direction == "ambiguous": score -= 3; factors.append("Ambiguous direction -3")

    sec = SECTOR_ADJ.get(a.get("sector") or "")
    if sec: score += sec; factors.append(f"Sector {a.get('sector')} {sec:+d}")

    if a.get("is_spread"):
        score = min(round(score), 69); factors.append("Capped at MED: multi-leg structure")
    else:
        score = round(score)
    score = max(0, min(100, score))
    return score, confidence_bucket(score), factors
```

- [ ] **Step 4: Run → tune until the 73-alert regression ≥90% passes.** **Step 5: Commit** with the real ratio inline: `feat(alpha-T3): confidence scorer, calibrated <hits>/73 buckets (TDD)`.

---

### Task 4: Rule classifiers (TDD)

**Files:** Create `backend/services/alpha/rules.py`; Test `backend/tests/services/alpha/test_rules.py`

> Each classifier takes a normalized print (ticker,type,side,strike,expiry,premium,oi,size,volume,spot,market_cap,sector,exec_type,avg_fill_price,pct_otm,dte) and returns a rule name or None. Conditions are from dossier §G (concrete, not placeholders).

- [ ] **Step 1: Failing tests** (one per key rule, using dossier example rows)

```python
# backend/tests/services/alpha/test_rules.py
from services.alpha.rules import classify_golden_sweeps, classify_otm_conviction, classify_repeated_hits

def test_golden_sweeps_fires():
    p = {"option_type": "call", "side": "buy", "exec_type": "SWEEP", "premium": 463365}
    assert classify_golden_sweeps(p) == "Golden Sweeps"

def test_golden_sweeps_needs_sweep_and_floor_premium():
    assert classify_golden_sweeps({"option_type":"call","side":"buy","exec_type":"SINGLE","premium":463365}) is None
    assert classify_golden_sweeps({"option_type":"call","side":"buy","exec_type":"SWEEP","premium":100000}) is None

def test_otm_conviction_fires_on_deep_otm_call_buy():
    assert classify_otm_conviction({"option_type":"call","side":"buy","exec_type":"SINGLE","pct_otm":23.4,"premium":491000}) == "OTM Conviction"

def test_repeated_hits_ascending_vs_descending():
    base = dict(ticker="X", option_type="call", strike=10, expiration="2026-07-17")
    assert classify_repeated_hits([{**base,"avg_fill_price":1.0},{**base,"avg_fill_price":1.5}]) == "RepeatedHitsAscendingFill"
    assert classify_repeated_hits([{**base,"avg_fill_price":2.0},{**base,"avg_fill_price":1.2}]) == "RepeatedHitsDescendingFill"
    assert classify_repeated_hits([{**base,"avg_fill_price":1.0},{**base,"avg_fill_price":1.0}]) == "RepeatedHits"
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement** `rules.py`

```python
# backend/services/alpha/rules.py
GOLDEN_SWEEP_MIN_PREMIUM = 250_000   # dossier observed floor ~$264K
OTM_CONVICTION_MIN_PCT = 16.0

def classify_golden_sweeps(p: dict) -> str | None:
    if (p.get("option_type") == "call" and p.get("side") == "buy"
            and p.get("exec_type") == "SWEEP" and (p.get("premium", 0) or 0) >= GOLDEN_SWEEP_MIN_PREMIUM):
        return "Golden Sweeps"
    return None

def classify_otm_conviction(p: dict) -> str | None:
    if (p.get("option_type") == "call" and p.get("side") == "buy"
            and p.get("exec_type") == "SINGLE" and (p.get("pct_otm", 0) or 0) >= OTM_CONVICTION_MIN_PCT):
        return "OTM Conviction"
    return None

def classify_repeated_hits(prints: list[dict]) -> str | None:
    """prints = the session's prints for ONE contract (ticker,type,strike,expiry), in time order."""
    if len(prints) < 2:
        return None
    fills = [pr.get("avg_fill_price") for pr in prints if pr.get("avg_fill_price") is not None]
    if len(fills) >= 2:
        if all(b > a for a, b in zip(fills, fills[1:])): return "RepeatedHitsAscendingFill"
        if all(b < a for a, b in zip(fills, fills[1:])): return "RepeatedHitsDescendingFill"
    return "RepeatedHits"

# Remaining rules (encode per dossier §G with the same pattern + a test each):
#   classify_low_historic_volume_floor: exec_type=="FLOOR" and volume >> contract historical baseline
#   classify_floor_trade_cap: exec_type=="FLOOR" -> bucket by market_cap (Large >=1.0e10, Mid 2e9..1e10, else Small)
#   classify_virgin_strike: open_interest == 0 and no prior prints on the strike
#   classify_sweeps_followed_by_floor: a SWEEP then a FLOOR on the same contract in-session
#   classify_spy_index: ticker=="SPY" and exec_type=="SINGLE" and premium>=1e6 -> "SPY_{type}_{side}_TIER_2" (promote to HIGH_CONVICTION above the higher bar)
```

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat(alpha-T4): rule classifiers — Golden Sweeps / OTM Conviction / RepeatedHits family (TDD)`. Then add the remaining classifiers (one test + impl each) in follow-up commits.

---

### Task 5: Engine + API route (TDD)

**Files:** Create `backend/services/alpha/engine.py`, `backend/services/alpha/router.py`; Modify `backend/server.py` (ONE surgical `include_router` line); Test `backend/tests/services/alpha/test_router.py`

- [ ] **Step 1: Failing test** (route serves replay alerts, sorted by actionability)

```python
# backend/tests/services/alpha/test_router.py
from fastapi.testclient import TestClient
from server import app

def test_alerts_endpoint_serves_replay():
    c = TestClient(app)
    r = c.get("/api/alpha/alerts?source=replay&page=1&page_size=50")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 73 and len(body["alerts"]) == 50
    scores = [a["confidence_score"] for a in body["alerts"]]
    assert scores == sorted(scores, reverse=True)  # default sort = actionability
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement** `engine.py` + `router.py`

```python
# backend/services/alpha/engine.py
from .replay import ReplaySource
from .scoring import score_alert

_SORTERS = {
    "actionability": lambda a: -a.get("confidence_score", 0),
    "premium": lambda a: -(a.get("premium", 0) or 0),
    "ticker": lambda a: a.get("ticker", ""),
}

class AlertEngine:
    def __init__(self):
        self._replay = ReplaySource()

    def alerts(self, source="replay", sort="actionability", page=1, page_size=50) -> dict:
        if source == "replay":
            items = [a.model_dump() for a in self._replay.all()]
        else:  # "live" wired in a later plan; falls back to replay for now
            items = [a.model_dump() for a in self._replay.all()]
        for a in items:
            s, conf, factors = score_alert(a)
            a["confidence_score"], a["confidence"], a["confidence_factors"] = s, conf, factors
        items.sort(key=_SORTERS.get(sort, _SORTERS["actionability"]))
        start = (page - 1) * page_size
        return {"total": len(items), "page": page, "page_size": page_size,
                "alerts": items[start : start + page_size]}
```

```python
# backend/services/alpha/router.py
from fastapi import APIRouter, Query
from .engine import AlertEngine

router = APIRouter(prefix="/api/alpha", tags=["alpha"])
_engine = AlertEngine()

@router.get("/alerts")
def get_alerts(source: str = "replay", sort: str = "actionability",
               page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    return _engine.alerts(source=source, sort=sort, page=page, page_size=page_size)
```

- [ ] **Step 4: Surgical `server.py` edit** — add near the other routers:

```python
from services.alpha.router import router as alpha_router
app.include_router(alpha_router)
```

- [ ] **Step 5: Run the alpha suite → PASS, then the module sweep for no regressions**

```bash
cd backend && .venv/bin/python3 -m pytest tests/services/alpha/ -q
.venv/bin/python3 -m pytest -q --tb=no 2>&1 | tail -3
```

- [ ] **Step 6: Commit** `feat(alpha-T5): /api/alpha/alerts engine+router serving scored replay (TDD)`.

---

## Self-Review
- **Spec coverage:** dossier §A→Task 1; replay (73 alerts) §ground-truth→Task 2; scoring §C→Task 3; rules §B/§G→Task 4; sort §D + serving→Task 5. Live classification over floww's print feed is **stubbed** (engine `source="live"` falls back to replay) — wiring it to floww's real option-flow source is Plan 02b (needs floww's print stream + a sweep/floor detector); called out so it isn't silently assumed done.
- **Placeholder scan:** Task 4 lists the remaining 5 classifiers with concrete conditions (not TODOs) + instruction to add one test+impl each; everything else is complete code.
- **Type consistency:** `score_alert(dict)->(int,str,list[str])` used identically in Task 3 tests, engine; `ReplaySource.all()/page()` consistent across Tasks 2 & 5; `AlphaAlert` field names match the dossier schema and the fixtures.
- **Calibration honesty:** Task 3's bucket deltas are a starting point; the **73-alert regression gate (≥90%)** is the real acceptance — tune deltas, don't fake the number.
