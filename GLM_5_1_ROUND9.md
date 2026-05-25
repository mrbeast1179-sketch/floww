# OpenCode GLM 5.1 — Round 9 Research Integration

> Self-contained. Paste below the `═══` into a single GLM 5.1 session.
> Two ports of MIT-licensed research code. Estimated 4-6 hours sequential.

═══════════════════════════════════════════════════════════════════════════════

You are OpenCode GLM 5.1. Architect (Nav, ex-Jane Street, PhD math) has bound
your scope to math-heavy ports from public MIT-licensed repos. You don't modify
existing code — you add NEW services that future agents will integrate.

═══════════════════════════════════════════════════════════════════════════════
HARD RULES
═══════════════════════════════════════════════════════════════════════════════

R1. Canonical clone: `/Users/nav/Documents/GitHub/floww`.
R2. NEVER: `--abort`, `--reset --hard`, `--force`, `--no-verify`, `--amend`,
    `git checkout .`, `git clean -fd`, `rm -rf .git`.
R3. You create NEW files only. NEVER modify:
    - `backend/services/regime_detector.py` (Round 10 integration target)
    - `backend/services/heatseeker_snapshots.py` (Round 10 integration target)
    - ANY existing file under `backend/services/` other than the ones you create
    - All other Forbidden List items (inference.py, dash_ui.py, server.py, frontend/**)
R4. Every commit message must include test-pass output inline.
R5. NEVER xfail/skip. HALT instead.
R6. Halt format:
        ──── HALT REPORT ────
        Agent:    GLM 5.1 Round 9
        Phase:    <G-N>  Step: <n>
        Reason:   <one sentence>
        Output:   <verbatim>
        Question: <one specific question>
        ─────────────────────
R7. 15-min status pulse to:
        kanban/cards/agent_GLM_status.md
        ~/Documents/GitHub/Hermes/Daily Log.md
    Format: `[<ISO8601-UTC>] GLM :: <status> :: <summary> :: HEAD=<sha7>`
R8. Per-task commit + push + verify-on-origin.

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — common setup
═══════════════════════════════════════════════════════════════════════════════

```bash
cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                        # expect "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_GLM_start.txt
git branch backup/r9_GLM_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards backend/services backend/tests/services
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] GLM :: launched :: Phase 0 complete :: HEAD=$(git rev-parse --short HEAD)" \
  >> kanban/cards/agent_GLM_status.md
```

═══════════════════════════════════════════════════════════════════════════════
G1 — Port pin-risk calculator from FlashAlpha-lab/0dte-options-analytics
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** `backend/services/pin_risk.py` (NEW), `backend/tests/services/test_pin_risk.py` (NEW)

**Upstream:** https://github.com/FlashAlpha-lab/0dte-options-analytics (MIT license)
Specifically: their pin-risk calculator. Math is portable; ignore any API client code.

**Function signature:**
```python
from typing import Dict, List, Any

def compute_pin_risk(
    chain_payload: Dict[str, Any],   # backend's /api/chain/{ticker} response shape
    spot: float,                      # current underlying price
) -> Dict[str, Any]:
    """
    Compute pin-risk metrics from an options chain payload.
    
    Returns:
        {
            "pin_strike": float,         # the strike with highest pin probability
            "pin_strength": float,       # 0..1 score of how strong the pin is
            "dealer_hedge_dollars": float,  # estimated dealer hedging $ per 1% move
            "expected_move": float,      # implied 1-day expected move based on ATM straddle
            "asof": str,                 # ISO timestamp
        }
    """
    ...
```

**Steps:**

1. Look up the pin-risk math in the FlashAlpha repo (or replicate from theory):
   - Pin strike: the strike with the highest combined call+put OI near spot
   - Pin strength: ratio of pin-strike OI to total OI within ±1 ATM std
   - Dealer hedge dollars: ≈ Σ (OI × contract_multiplier × |gamma|) × spot²
   - Expected move: ATM straddle price × 0.85 (heuristic) or use IV * spot * sqrt(T/365)
2. Implement `compute_pin_risk` in `backend/services/pin_risk.py`.
3. Use ONLY numpy + the standard library + math/typing. Do NOT pull in scipy.
4. Module docstring must credit upstream:
   ```python
   """
   Pin-risk calculator. Ported from FlashAlpha-lab/0dte-options-analytics (MIT license).
   See https://github.com/FlashAlpha-lab/0dte-options-analytics for upstream source.
   Adapted to consume our /api/chain/{ticker} response shape directly.
   """
   ```
5. Write `backend/tests/services/test_pin_risk.py` with ≥ 5 tests:
   - test with synthetic chain (3 strikes, varying OI) — verify pin_strike picks max OI strike
   - test with empty contracts — returns sensible defaults / NaN-safe
   - test with all puts (no calls) — function doesn't crash
   - test pin_strength is in [0,1]
   - test dealer_hedge_dollars is non-negative
6. Run: `cd backend && source .venv/bin/activate && python -m pytest tests/services/test_pin_risk.py -v`
7. Commit:
   ```
   feat(round-9-GLM): port pin-risk calculator from FlashAlpha-lab (MIT)
   
   New service backend/services/pin_risk.py + 5 tests.
   No existing code modified — drop-in addition.
   Round 10 integration target: heatseeker_snapshots.py.
   
   $ pytest backend/tests/services/test_pin_risk.py -v | tail -3
   5 passed in 0.Ns
   
   Upstream: https://github.com/FlashAlpha-lab/0dte-options-analytics (MIT)
   
   Co-Authored-By: OpenCode GLM 5.1 <glm@floww.dev>
   ```
8. Push + verify-on-origin.

═══════════════════════════════════════════════════════════════════════════════
G2 — Port HMM emission features from CameronScarpati/lob-regime-scanner
═══════════════════════════════════════════════════════════════════════════════

**ORIGIN GATE:** G1 must be on origin first.

**OWNS:** `backend/services/regime_emissions.py` (NEW), `backend/tests/services/test_regime_emissions.py` (NEW)

**Upstream:** https://github.com/CameronScarpati/lob-regime-scanner (MIT license)
Specifically: their Gaussian HMM emission distribution choices.

**Function signature:**
```python
from typing import Dict
import numpy as np

def compute_emissions(
    returns: np.ndarray,       # 1-D array of log returns
    volumes: np.ndarray,       # 1-D array of volumes (same length as returns)
    window: int = 20,          # rolling window for vol estimates
) -> Dict[str, np.ndarray]:
    """
    Compute the 3 emission features used by Gaussian HMM regime detection.
    
    Returns:
        {
            "realized_vol": np.ndarray,   # rolling std of returns × sqrt(252) (annualized)
            "abs_return": np.ndarray,     # |returns| (absolute return magnitude)
            "volume_ratio": np.ndarray,   # volumes / rolling_mean(volumes, window)
        }
    
    Output arrays have len == len(returns); first `window-1` values are NaN.
    """
    ...
```

**Steps:**

1. Implement using numpy only. Use `np.lib.stride_tricks` or simple loops for rolling stats.
2. NaN-safe: any NaN in input → NaN in output for that index (don't propagate to later indices).
3. Module docstring credits upstream.
4. Write `backend/tests/services/test_regime_emissions.py` with ≥ 5 tests:
   - test output keys match {realized_vol, abs_return, volume_ratio}
   - test output array lengths match input
   - test first `window-1` values are NaN (warm-up period)
   - test volume_ratio is ≈ 1.0 when volumes are constant
   - test realized_vol is non-negative
5. Run: `pytest backend/tests/services/test_regime_emissions.py -v`
6. Commit:
   ```
   feat(round-9-GLM): port HMM emission features from lob-regime-scanner (MIT)
   
   New service backend/services/regime_emissions.py + 5 tests.
   No existing code modified — drop-in addition.
   Round 10 integration target: regime_detector.py (replace its emission logic).
   
   $ pytest backend/tests/services/test_regime_emissions.py -v | tail -3
   5 passed in 0.Ns
   
   Upstream: https://github.com/CameronScarpati/lob-regime-scanner (MIT)
   
   Co-Authored-By: OpenCode GLM 5.1 <glm@floww.dev>
   ```
7. Push + verify-on-origin.

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS
═══════════════════════════════════════════════════════════════════════════════

- You ONLY add NEW files. Cannot modify regime_detector.py, heatseeker_snapshots.py,
  inference.py, dash_ui.py, server.py, or anything in frontend/.
- Round 10 will integrate your work — don't pre-integrate.
- Math must be correct. If unit test fails, HALT and re-check the math; don't
  loosen the assertion.
- MIT license attribution in module docstring is non-negotiable.
- If you find yourself wanting to "improve" upstream code beyond porting:
  HALT. That's Round 10's job. Port faithfully.

END OF PROMPT. BEGIN AT PHASE 0.
═══════════════════════════════════════════════════════════════════════════════
