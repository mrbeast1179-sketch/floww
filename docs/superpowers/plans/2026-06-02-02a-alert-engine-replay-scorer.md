# AlphaPod Clone — Plan 02a: Alert Engine — Replay + Solved Scorer + Classifiers

> **SUPERSEDES** the monolithic `2026-06-02-02-alert-engine.md`. The live pipeline is split into 02b (ingestion), 02c (enrichment), 02d (rule engine + publish) — all gated on a real print feed. **This plan (02a) is fully unblocked and ships working software.**
>
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. `- [ ]` steps. Spec: `docs/superpowers/research/2026-06-02-alphapod-rules-dossier.md` (READ FIRST). Backend lane — no overlap with the frontend foundation.

**Goal:** Serve the 73 captured AlphaPod alerts through floww's API, scored by a confidence model whose weights are **recovered by least-squares from the alerts' own `confidence_factors`** (so the scorer reproduces AlphaPod's scores, not an approximation), with the rule classifiers as pure, golden-tested functions.

**Architecture:** New package `backend/services/alpha/`. The scorer is data-driven: a **factor parser** turns each alert's `confidence_factors[]` into feature indicators + a base win-rate; a **weight solver** fits `score = base + X·w` over the 73 non-spread alerts via `numpy.linalg.lstsq`, emitting a static `weights.json`; the **scorer** applies those weights + the observed `is_spread → cap 69` rule. The 73 alerts are the golden regression set — acceptance is exact-bucket reproduction.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, numpy (already a backend dep), pytest. Venv: `backend/.venv/bin/python3`. Lane-authorized files: `backend/services/alpha/**`, `backend/tests/services/alpha/**`, one surgical `include_router` line in `backend/server.py` (Task 7). Commit format: HEREDOC + inline `pytest` evidence (CLAUDE.md). TDD: red→green→commit per task.

---

### Task 1: `AlphaAlert` schema (TDD)

**Files:** Create `backend/services/alpha/__init__.py`, `backend/services/alpha/schema.py`; Test `backend/tests/services/alpha/__init__.py`, `backend/tests/services/alpha/test_schema.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/services/alpha/test_schema.py
from services.alpha.schema import AlphaAlert
GOLDEN = {
  "alert_id": "doc-1", "ticker": "DOCU", "option_type": "call", "strike": 65.0,
  "expiration": "2026-07-17", "dte": 45, "premium": 463365.0, "size": 3646, "side": "buy",
  "alert_rule": "Golden Sweeps", "has_sweep": True, "has_floor": False, "volume": 3650,
  "open_interest": 95, "vol_oi_ratio": 38.4, "spot_price": 60.0, "market_cap": 1.2e10,
  "sector": "Technology", "tier": 2, "is_spread": False, "avg_fill_price": 1.27,
  "created_at": "2026-06-01T15:59:19-04:00", "sentiment": "BULLISH", "exec_type": "SWEEP",
  "confidence": "HIGH", "confidence_score": 76,
  "confidence_factors": ["Base 57.4% for Golden Sweeps", "Bullish sweep +3"],
  "direction": "bullish", "pct_otm": 8.33,
}
def test_validates_and_defaults():
    a = AlphaAlert.model_validate(GOLDEN)
    assert a.exec_type == "SWEEP" and a.confidence == "HIGH" and a.delta is None
```

- [ ] **Step 2: Run → FAIL.** `cd backend && .venv/bin/python3 -m pytest tests/services/alpha/test_schema.py -q`
- [ ] **Step 3: Implement** `schema.py` (47-field parity)

```python
# backend/services/alpha/schema.py
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel

class AlphaAlert(BaseModel):
    alert_id: str; ticker: str
    option_type: Literal["call", "put"]; strike: float; expiration: str; dte: int
    premium: float; size: int; side: Literal["buy", "sell"]
    alert_rule: str; has_sweep: bool = False; has_floor: bool = False
    volume: int = 0; open_interest: int = 0; vol_oi_ratio: float = 0.0
    spot_price: float; market_cap: Optional[float] = None; sector: Optional[str] = None
    tier: int = 2; iv: Optional[float] = None; delta: Optional[float] = None; gamma: Optional[float] = None
    is_spread: bool = False; spread_type: Optional[str] = None; avg_fill_price: Optional[float] = None
    created_at: str; sentiment: Literal["BULLISH","BEARISH","NEUTRAL"] = "NEUTRAL"
    exec_type: Literal["SINGLE","SWEEP","FLOOR"] = "SINGLE"
    confidence: Literal["LOW","MED","HIGH"] = "LOW"; confidence_score: int = 0
    confidence_factors: list[str] = []
    direction: Literal["bullish","bearish","ambiguous"] = "ambiguous"; pct_otm: float = 0.0
    iv_rank: Optional[float] = None; oi_change: Optional[float] = None; stickiness: Optional[float] = None
```

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat(alpha-T1): AlphaAlert schema (TDD)`.

---

### Task 2: Copy the 73 alerts + replay source (TDD)

**Files:** Create `backend/services/alpha/fixtures/alerts.json`, `backend/services/alpha/replay.py`; Test `backend/tests/services/alpha/test_replay.py`

- [ ] **Step 1: Copy ground truth into the repo**

```bash
cd backend && mkdir -p services/alpha/fixtures
.venv/bin/python3 - <<'PY'
import json, pathlib
m = pathlib.Path.home()/"GitHub/hub-alphapodtrading/api-data"
alerts=[]
for f in ["alerts-p1.json","alerts-p2.json"]:
    d=json.loads((m/f).read_text()); alerts+=d.get("alerts", d if isinstance(d,list) else [])
pathlib.Path("services/alpha/fixtures/alerts.json").write_text(json.dumps({"total":len(alerts),"alerts":alerts},indent=2))
print("wrote",len(alerts))
PY
```
Expected: `wrote 73`.

- [ ] **Step 2: Failing test**

```python
# backend/tests/services/alpha/test_replay.py
from services.alpha.replay import ReplaySource
def test_loads_73(): assert ReplaySource().count() == 73
def test_pages(): assert len(ReplaySource().page(2,50)["alerts"]) == 23
```

- [ ] **Step 3: Run → FAIL. Step 4: Implement**

```python
# backend/services/alpha/replay.py
import json, pathlib
from .schema import AlphaAlert
_FIX = pathlib.Path(__file__).parent/"fixtures"/"alerts.json"
class ReplaySource:
    def __init__(self, path=None):
        self._raw = json.loads((path or _FIX).read_text())["alerts"]
        self._alerts = [AlphaAlert.model_validate(a) for a in self._raw]
    def count(self): return len(self._alerts)
    def raw(self): return list(self._raw)               # dicts incl. confidence_factors (for the solver)
    def all(self): return list(self._alerts)
    def page(self, page=1, page_size=50):
        s=(page-1)*page_size
        return {"total": len(self._alerts), "page": page, "page_size": page_size,
                "alerts": [a.model_dump() for a in self._alerts[s:s+page_size]]}
```

- [ ] **Step 5: Run → PASS. Step 6: Commit** `feat(alpha-T2): replay over 73 captured alerts (TDD)`.

---

### Task 3: Factor parser (TDD)

**Files:** Create `backend/services/alpha/factors.py`; Test `backend/tests/services/alpha/test_factors.py`

> Each `confidence_factors` string is either the base (`"Base 57.4% for Golden Sweeps"`), an explicit ± point (`"Bullish sweep +3"`, `"Put-sale -3"`), the spread cap (`"Capped at MED: ..."`), or a labeled bucket with no number (`"Institutional premium ($1M+)"`). The parser splits these into: base win-rate, a normalized **feature label** (number stripped) per non-base factor, and the explicit point if present.

- [ ] **Step 1: Failing test**

```python
# backend/tests/services/alpha/test_factors.py
from services.alpha.factors import parse_factors, feature_label

def test_parses_base_and_points():
    p = parse_factors(["Base 57.4% for Golden Sweeps", "Bullish sweep +3", "Institutional premium ($1M+)"])
    assert abs(p.base - 57.4) < 1e-6
    assert p.is_spread_capped is False
    assert ("bullish sweep", 3) in p.features         # explicit point captured
    assert ("institutional premium ($1m+)", None) in p.features  # bucket, point unknown

def test_detects_spread_cap():
    assert parse_factors(["Base 53.4% for RepeatedHits", "Capped at MED: multi-leg structure"]).is_spread_capped

def test_feature_label_strips_sign():
    assert feature_label("Bearish block +2") == "bearish block"
    assert feature_label("Put-sale -3") == "put-sale"
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**

```python
# backend/services/alpha/factors.py
import re
from dataclasses import dataclass

_BASE_RE = re.compile(r"base\s+([\d.]+)%", re.I)
_POINT_RE = re.compile(r"([+-]\d+)\s*$")

def feature_label(s: str) -> str:
    return _POINT_RE.sub("", s).strip().lower().rstrip(":").strip()

@dataclass
class ParsedFactors:
    base: float
    is_spread_capped: bool
    features: list[tuple[str, int | None]]   # (normalized label, explicit point or None)

def parse_factors(factors: list[str]) -> ParsedFactors:
    base, capped, feats = 50.0, False, []
    for raw in factors or []:
        m = _BASE_RE.search(raw)
        if m:
            base = float(m.group(1)); continue
        if "capped at med" in raw.lower():
            capped = True; continue
        pm = _POINT_RE.search(raw)
        feats.append((feature_label(raw), int(pm.group(1)) if pm else None))
    return ParsedFactors(base=base, is_spread_capped=capped, features=feats)
```

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat(alpha-T3): confidence_factors parser (TDD)`.

---

### Task 4: Weight solver — recover the model from the 73 (TDD)

**Files:** Create `backend/services/alpha/solve_weights.py`, output `backend/services/alpha/weights.json`; Test `backend/tests/services/alpha/test_solver.py`

> Fit `confidence_score - base = X · w` over the **non-spread** alerts (spreads are score-censored at 69), where `X[i][f] = 1` if feature `f` is present on alert `i`. `numpy.linalg.lstsq` recovers each feature's point weight. Explicitly-pointed features (e.g. "bullish sweep" → +3) should solve to ≈ their stated value, validating the recovery.

- [ ] **Step 1: Failing test**

```python
# backend/tests/services/alpha/test_solver.py
import json, pathlib, subprocess, sys
from services.alpha.factors import parse_factors

def test_solver_emits_weights_and_reproduces_scores():
    # (re)generate weights.json from the fixtures
    subprocess.run([sys.executable, "-m", "services.alpha.solve_weights"], check=True, cwd="backend")
    weights = json.loads(pathlib.Path("backend/services/alpha/weights.json").read_text())
    assert "features" in weights and len(weights["features"]) >= 8
    # explicit points must be recovered within tolerance
    assert abs(weights["features"].get("bullish sweep", 0) - 3) <= 1.5

def test_reconstruction_error_small():
    from services.alpha.solve_weights import reconstruct
    raw = json.loads(pathlib.Path("backend/services/alpha/fixtures/alerts.json").read_text())["alerts"]
    errs = [abs(reconstruct(a) - a["confidence_score"]) for a in raw if not a["is_spread"]]
    assert max(errs) <= 3 and (sum(e <= 1 for e in errs) / len(errs)) >= 0.85
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**

```python
# backend/services/alpha/solve_weights.py
import json, pathlib
import numpy as np
from .factors import parse_factors

_DIR = pathlib.Path(__file__).parent
_FIX = _DIR/"fixtures"/"alerts.json"
_OUT = _DIR/"weights.json"

def _design(alerts):
    parsed = [parse_factors(a.get("confidence_factors", [])) for a in alerts]
    labels = sorted({f for p in parsed for (f, _) in p.features})
    idx = {f: i for i, f in enumerate(labels)}
    X = np.zeros((len(alerts), len(labels)))
    y = np.zeros(len(alerts))
    for i, (a, p) in enumerate(zip(alerts, parsed)):
        y[i] = a["confidence_score"] - p.base
        for (f, _pt) in p.features:
            X[i, idx[f]] = 1.0
    return labels, X, y, parsed

def solve():
    alerts = json.loads(_FIX.read_text())["alerts"]
    fit = [a for a in alerts if not a["is_spread"]]      # spreads are censored at 69
    labels, X, y, _ = _design(fit)
    w, *_ = np.linalg.lstsq(X, y, rcond=None)
    weights = {f: round(float(wi), 3) for f, wi in zip(labels, w)}
    _OUT.write_text(json.dumps({"features": weights}, indent=2))
    return weights

def reconstruct(alert: dict) -> float:
    weights = json.loads(_OUT.read_text())["features"]
    p = parse_factors(alert.get("confidence_factors", []))
    score = p.base + sum(weights.get(f, 0.0) for (f, _) in p.features)
    if alert.get("is_spread"):
        score = min(score, 69)
    return round(score)

if __name__ == "__main__":
    print("solved", len(solve()), "feature weights")
```

- [ ] **Step 4: Run → PASS (tune nothing — the fit is exact-ish by construction; if `max err > 3`, a feature label is mis-normalized — fix `feature_label`).** **Step 5: Commit** `feat(alpha-T4): least-squares recovery of the confidence model from 73 alerts (TDD)` with the reconstruction stats inline.

---

### Task 5: Scorer (TDD — golden reproduction)

**Files:** Create `backend/services/alpha/scoring.py`; Test `backend/tests/services/alpha/test_scoring.py`

> The runtime scorer mirrors `reconstruct` but works from a *live* alert dict's own factors (replay) — and for live alerts (02d) the factors are emitted by the rule pipeline. Acceptance: it reproduces the captured `confidence` bucket for **all 73**.

- [ ] **Step 1: Failing test**

```python
# backend/tests/services/alpha/test_scoring.py
import json, pathlib
from services.alpha.scoring import score_from_factors, confidence_bucket

def test_buckets():
    assert confidence_bucket(54)=="LOW" and confidence_bucket(55)=="MED"
    assert confidence_bucket(69)=="MED" and confidence_bucket(70)=="HIGH"

def test_reproduces_all_73_buckets():
    raw = json.loads(pathlib.Path("backend/services/alpha/fixtures/alerts.json").read_text())["alerts"]
    miss = [a["alert_id"] for a in raw
            if score_from_factors(a["confidence_factors"], a["is_spread"])[1] != a["confidence"]]
    assert miss == [], f"bucket mismatch on {miss}"
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**

```python
# backend/services/alpha/scoring.py
import json, pathlib
from .factors import parse_factors
_WEIGHTS = json.loads((pathlib.Path(__file__).parent/"weights.json").read_text())["features"]

def confidence_bucket(score: int) -> str:
    return "HIGH" if score >= 70 else "MED" if score >= 55 else "LOW"

def score_from_factors(factors: list[str], is_spread: bool) -> tuple[int, str]:
    p = parse_factors(factors)
    score = p.base + sum(_WEIGHTS.get(f, 0.0) for (f, _) in p.features)
    if is_spread or p.is_spread_capped:
        score = min(score, 69)
    score = max(0, min(100, round(score)))
    return score, confidence_bucket(score)
```

- [ ] **Step 4: Run → PASS (all 73 buckets reproduced). Step 5: Commit** `feat(alpha-T5): factor-driven scorer, reproduces 73/73 buckets (TDD)`.

---

### Task 6: Rule classifiers (TDD)

**Files:** Create `backend/services/alpha/rules.py`; Test `backend/tests/services/alpha/test_rules.py`

> Pure functions over a normalized print/contract. Conditions verbatim from dossier §G. (These feed the *live* engine in 02d; here they're unit-locked against the dossier's example rows.)

- [ ] **Step 1: Failing tests**

```python
# backend/tests/services/alpha/test_rules.py
from services.alpha.rules import (classify_golden_sweeps, classify_otm_conviction,
                                   classify_repeated_hits, classify_floor_cap)
def test_golden_sweeps():
    assert classify_golden_sweeps({"option_type":"call","side":"buy","exec_type":"SWEEP","premium":463365})=="Golden Sweeps"
    assert classify_golden_sweeps({"option_type":"call","side":"buy","exec_type":"SINGLE","premium":463365}) is None
def test_otm_conviction():
    assert classify_otm_conviction({"option_type":"call","side":"buy","exec_type":"SINGLE","pct_otm":23.4}) =="OTM Conviction"
    assert classify_otm_conviction({"option_type":"call","side":"buy","exec_type":"SINGLE","pct_otm":5}) is None
def test_repeated_hits_fill_trend():
    b=dict(ticker="X",option_type="call",strike=10,expiration="2026-07-17")
    asc=[{**b,"avg_fill_price":1.0},{**b,"avg_fill_price":1.5}]
    desc=[{**b,"avg_fill_price":2.0},{**b,"avg_fill_price":1.2}]
    flat=[{**b,"avg_fill_price":1.0},{**b,"avg_fill_price":1.0}]
    assert classify_repeated_hits(asc)=="RepeatedHitsAscendingFill"
    assert classify_repeated_hits(desc)=="RepeatedHitsDescendingFill"
    assert classify_repeated_hits(flat)=="RepeatedHits"
def test_floor_cap_buckets():
    assert classify_floor_cap({"exec_type":"FLOOR","market_cap":2.0e10})=="FloorTradeLargeCap"
    assert classify_floor_cap({"exec_type":"FLOOR","market_cap":2.9e9})=="FloorTradeMidCap"
    assert classify_floor_cap({"exec_type":"SINGLE","market_cap":2.0e10}) is None
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**

```python
# backend/services/alpha/rules.py
GOLDEN_SWEEP_MIN_PREMIUM = 250_000
OTM_CONVICTION_MIN_PCT = 16.0
LARGE_CAP_MIN = 1.0e10
MID_CAP_MIN = 2.0e9

def classify_golden_sweeps(p):
    return "Golden Sweeps" if (p.get("option_type")=="call" and p.get("side")=="buy"
        and p.get("exec_type")=="SWEEP" and (p.get("premium",0) or 0) >= GOLDEN_SWEEP_MIN_PREMIUM) else None

def classify_otm_conviction(p):
    return "OTM Conviction" if (p.get("option_type")=="call" and p.get("side")=="buy"
        and p.get("exec_type")=="SINGLE" and (p.get("pct_otm",0) or 0) >= OTM_CONVICTION_MIN_PCT) else None

def classify_repeated_hits(prints):
    if len(prints) < 2: return None
    fills = [pr["avg_fill_price"] for pr in prints if pr.get("avg_fill_price") is not None]
    if len(fills) >= 2:
        if all(b>a for a,b in zip(fills,fills[1:])): return "RepeatedHitsAscendingFill"
        if all(b<a for a,b in zip(fills,fills[1:])): return "RepeatedHitsDescendingFill"
    return "RepeatedHits"

def classify_floor_cap(p):
    if p.get("exec_type") != "FLOOR": return None
    mc = p.get("market_cap") or 0
    return "FloorTradeLargeCap" if mc >= LARGE_CAP_MIN else "FloorTradeMidCap" if mc >= MID_CAP_MIN else "FloorTradeSmallCap"
```

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat(alpha-T6): rule classifiers vs dossier examples (TDD)`. Remaining rules (Virgin Strike, LowHistoricVolumeFloor, SweepsFollowedByFloor, SPY index, OtmEarningsFloor) are 02d (need live state/enrichment) — do NOT stub them here.

---

### Task 7: Engine + API route (TDD)

**Files:** Create `backend/services/alpha/engine.py`, `backend/services/alpha/router.py`; Modify `backend/server.py` (one `include_router`); Test `backend/tests/services/alpha/test_router.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/services/alpha/test_router.py
from fastapi.testclient import TestClient
from server import app
def test_alerts_served_scored_and_sorted():
    r = TestClient(app).get("/api/alpha/alerts?source=replay&sort=actionability&page=1&page_size=50")
    assert r.status_code == 200
    b = r.json(); assert b["total"] == 73 and len(b["alerts"]) == 50
    sc = [a["confidence_score"] for a in b["alerts"]]
    assert sc == sorted(sc, reverse=True)
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**

```python
# backend/services/alpha/engine.py
from .replay import ReplaySource
from .scoring import score_from_factors
_SORT = {"actionability": lambda a: -a["confidence_score"],
         "premium": lambda a: -(a.get("premium",0) or 0),
         "ticker": lambda a: a.get("ticker","")}
class AlertEngine:
    def __init__(self): self._replay = ReplaySource()
    def alerts(self, source="replay", sort="actionability", page=1, page_size=50):
        items = self._replay.raw()                       # live source arrives in 02d
        for a in items:
            a["confidence_score"], a["confidence"] = score_from_factors(a.get("confidence_factors",[]), a["is_spread"])
        items = sorted(items, key=_SORT.get(sort, _SORT["actionability"]))
        s=(page-1)*page_size
        return {"total": len(items), "page": page, "page_size": page_size, "alerts": items[s:s+page_size]}
```

```python
# backend/services/alpha/router.py
from fastapi import APIRouter, Query
from .engine import AlertEngine
router = APIRouter(prefix="/api/alpha", tags=["alpha"])
_engine = AlertEngine()
@router.get("/alerts")
def get_alerts(source: str="replay", sort: str="actionability",
               page: int=Query(1,ge=1), page_size: int=Query(50,ge=1,le=200)):
    return _engine.alerts(source, sort, page, page_size)
```

- [ ] **Step 4: Surgical `server.py`** — in the router-include block (~`server.py:2627-2815`):

```python
from services.alpha.router import router as alpha_router
app.include_router(alpha_router)
```

- [ ] **Step 5: Run alpha suite + module sweep**

```bash
cd backend && .venv/bin/python3 -m pytest tests/services/alpha/ -q
.venv/bin/python3 -m pytest -q --tb=no 2>&1 | tail -3   # no regressions
```

- [ ] **Step 6: Commit** `feat(alpha-T7): /api/alpha/alerts serving solved-scored replay (TDD)`.

---

## Self-Review
- **Spec coverage:** dossier §A→T1; ground-truth replay→T2; §C scoring (now *solved*, not guessed)→T3–T5; §B/§G rules→T6; §D sort + serving→T7. **Live classification, enrichment, persistence, publish, and the remaining 5 rules are explicitly out of scope → 02b/02c/02d** (gated on a real print feed + mcap/sector providers). Stated, not stubbed.
- **Placeholder scan:** every code step complete; the only deferrals are whole tasks moved to named downstream plans with their blockers.
- **Type consistency:** `parse_factors→ParsedFactors(base,is_spread_capped,features)` used identically in solver, scorer; `score_from_factors(list,bool)->(int,str)` consistent T5/T7; `ReplaySource.raw()/count()/page()` consistent T2/T7; weights keyed by `feature_label` output across T3/T4/T5.
- **Rigor note (for the math):** the solver fits on non-spread alerts only (spreads are censored at the 69 cap); acceptance is `max|err|≤3` and `≥85%` within ±1, plus **73/73 bucket reproduction** in T5. If a recovered explicit weight (e.g. "bullish sweep") deviates >1.5 from its stated ±value, a label normalization bug is the cause — fix `feature_label`, don't fudge tolerances.
