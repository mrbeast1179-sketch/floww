# Agent A7 — ToxicityGauge UI + Backend Ensemble Validation (target: 2.5 hours)

**You are Agent A7.** Read `_PREAMBLE.md`. Scope: investigate + fix `ToxicityGauge.jsx`, validate backend `ml_ensemble.py` (toxicity-related sections), add regression tests for the Platt-scaled toxicity output, document the toxicity contract for Round 10.

Your file ownership: `frontend/src/components/ToxicityGauge.jsx`, `backend/services/ml_ensemble.py` (toxicity sections only — preserve any non-toxicity code), any new test files. **Do not touch** `services/ml/inference.py` (forbidden) — but you can read it.

---

## Mission

| # | Task | Min |
|---|------|-----|
| 1 | Pre-flight + locate toxicity backend code | 15 |
| 2 | Read `ml_ensemble.py` toxicity section | 20 |
| 3 | Read `ToxicityGauge.jsx` + identify symptoms | 20 |
| 4 | Determine the API endpoint the gauge consumes | 15 |
| 5 | Write failing test: backend Platt scaler shape | 20 |
| 6 | Write failing test: gauge component contract | 20 |
| 7 | Fix backend (if Platt output shape is wrong) | 25 |
| 8 | Fix ToxicityGauge (null safety + thresholds + colors) | 25 |
| 9 | Document toxicity contract for Round 10 | 15 |
| 10 | Close-out | 10 |

Total ~185 min.

---

## Task 1 — Pre-flight + locate (15 min)

- [ ] **1.1** `pwd` canonical.
- [ ] **1.2** Find toxicity-related backend files:
  ```bash
  grep -rln 'toxicity\|Toxicity\|PlattScaler\|ToxicityEnsemble' backend/services/ --include='*.py' | head -10
  ls backend/services/ml_ensemble.py 2>&1
  ```
- [ ] **1.3** Find the API endpoint:
  ```bash
  grep -rn 'toxicity\|@router.get.*toxic' backend/routes/ --include='*.py' | head -10
  ```
- [ ] **1.4** Read existing test coverage:
  ```bash
  ls backend/tests/services/test_ml_ensemble* backend/tests/routes/test_toxicity* 2>&1 | head -5
  ```
- [ ] **1.5** First pulse.

---

## Task 2 — Read `ml_ensemble.py` toxicity (20 min)

- [ ] **2.1** Use `Read` on `backend/services/ml_ensemble.py`.
- [ ] **2.2** Identify:
  - `PlattScaler` class — what does fit/transform return? Single scalar 0-1 or distribution?
  - `ToxicityEnsemble` class — how many sub-models? What's the aggregation (mean/median/weighted)?
  - What features go into the ensemble (VPIN, OFI, queue imbalance, etc.)?
  - What's the API contract — `predict(features: dict) → float in [0,1]` ?
  - Are there documented thresholds (e.g., >0.7 = "toxic flow")?
- [ ] **2.3** Note any obvious bugs (divide-by-zero, missing null safety, wrong distribution assumption).
- [ ] **2.4** Pulse.

---

## Task 3 — Read `ToxicityGauge.jsx` + symptoms (20 min)

- [ ] **3.1** `Read` the component.
- [ ] **3.2** Identify:
  - Where does it get data — props? hook? polling?
  - What's the input shape? (single value or {value, history})
  - How is the gauge visualized (SVG arc, progress bar, colored circle)?
  - What thresholds drive color changes? (green/yellow/red)
  - Null/undefined handling?
  - Animation jitter on rapid updates?
- [ ] **3.3** Note rendering bugs.
- [ ] **3.4** Pulse.

---

## Task 4 — Determine the consumed API (15 min)

- [ ] **4.1** Search frontend for the fetch:
  ```bash
  grep -rn 'toxicity' frontend/src/ --include='*.js' --include='*.jsx' | head -10
  ```
- [ ] **4.2** Trace the URL. Common pattern is `useToxicity` hook calling `/api/toxicity/<ticker>` or via WebSocket message type.
- [ ] **4.3** Start backend, hit the endpoint:
  ```bash
  lsof -ti :8000 | xargs kill -9 2>/dev/null
  cd backend && nohup .venv/bin/python3 -m uvicorn server:app --port 8000 > /tmp/uvicorn_a7.log 2>&1 &
  sleep 4
  curl -s 'http://localhost:8000/api/toxicity/SPY' 2>&1 | head -30
  ```
  If 404, the URL is different — find it via the grep in 4.1.
- [ ] **4.4** Save sample response shape.
- [ ] **4.5** Pulse.

---

## Task 5 — Failing test: backend Platt scaler shape (20 min)

- [ ] **5.1** Create `backend/tests/services/test_toxicity_ensemble_contract.py`:
  ```python
  """Contract: ToxicityEnsemble.predict returns float in [0,1]; PlattScaler is monotonic."""
  import pytest
  import numpy as np
  from services.ml_ensemble import PlattScaler, ToxicityEnsemble
  
  
  def test_platt_scaler_output_in_unit_interval():
      """Calibrated probabilities must be in [0, 1]."""
      ps = PlattScaler()
      # Fit on a simple dataset
      scores = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
      labels = np.array([0, 0, 0, 1, 1])
      ps.fit(scores, labels)
      out = ps.transform(scores)
      assert np.all((out >= 0.0) & (out <= 1.0)), \
          f"Platt output out of range: {out}"
  
  
  def test_platt_scaler_monotonic():
      """Higher scores should yield higher calibrated probabilities."""
      ps = PlattScaler()
      scores = np.linspace(-3, 3, 21)
      labels = (scores > 0).astype(int)
      ps.fit(scores, labels)
      out = ps.transform(scores)
      diffs = np.diff(out)
      # Allow tiny numerical wobble
      assert np.all(diffs >= -1e-6), f"Platt not monotonic; diffs: {diffs[diffs < 0]}"
  
  
  def test_toxicity_ensemble_predict_returns_unit_float():
      """Aggregated toxicity score is a single float in [0, 1]."""
      ens = ToxicityEnsemble()
      # Use a feature dict matching the ensemble's expected schema.
      # If the schema is different, this test will reveal it.
      features = {
          "vpin": 0.5,
          "ofi": 0.3,
          "queue_imbalance": 0.1,
          "spread_bps": 5.0,
          "volume_imbalance": 0.2,
      }
      try:
          out = ens.predict(features)
      except KeyError as e:
          pytest.fail(f"ToxicityEnsemble requires feature {e} — adjust the test fixture")
      assert isinstance(out, (float, int, np.floating))
      assert 0.0 <= float(out) <= 1.0, f"out of range: {out}"
  ```
- [ ] **5.2** Run: `cd backend && .venv/bin/python3 -m pytest tests/services/test_toxicity_ensemble_contract.py -v 2>&1 | tail -10`.
  - If tests pass → contract is sound, no backend fix needed.
  - If tests fail → real backend bug, you'll fix in Task 7.
- [ ] **5.3** Pulse.

---

## Task 6 — Failing test: gauge component contract (20 min)

- [ ] **6.1** Create `frontend/src/components/ToxicityGauge.test.jsx`:
  ```jsx
  import { render } from '@testing-library/react';
  import ToxicityGauge from './ToxicityGauge';
  
  describe('ToxicityGauge', () => {
    test('renders without crash for value=0.5', () => {
      const { container } = render(<ToxicityGauge value={0.5} />);
      expect(container.firstChild).not.toBeNull();
    });
  
    test('renders empty state for null', () => {
      const { container } = render(<ToxicityGauge value={null} />);
      // Must render SOMETHING, not crash
      expect(container.firstChild).not.toBeNull();
    });
  
    test('clamps display to [0,1] for out-of-range values', () => {
      const { container: c1 } = render(<ToxicityGauge value={-0.5} />);
      const { container: c2 } = render(<ToxicityGauge value={1.5} />);
      // No NaN in SVG
      [c1, c2].forEach((c) => {
        const svg = c.querySelector('svg');
        if (svg) {
          expect(svg.outerHTML).not.toContain('NaN');
        }
      });
    });
  
    test('changes color class with severity', () => {
      // Low (green): value < 0.4
      // Medium (yellow): 0.4-0.7
      // High (red): > 0.7
      const { container: low } = render(<ToxicityGauge value={0.2} />);
      const { container: med } = render(<ToxicityGauge value={0.55} />);
      const { container: high } = render(<ToxicityGauge value={0.85} />);
      // Just verify they render different content (could be className, fill color, etc.)
      expect(low.innerHTML).not.toEqual(high.innerHTML);
    });
  });
  ```
- [ ] **6.2** Run: `cd frontend && npx jest src/components/ToxicityGauge.test.jsx 2>&1 | tail -15`.
- [ ] **6.3** Document which tests fail — those drive Task 8 fixes.
- [ ] **6.4** Pulse.

---

## Task 7 — Backend fix if Platt contract is broken (25 min)

ONLY do this task if Task 5 tests failed.

- [ ] **7.1** Inspect the failure. Common backend bugs:
  - PlattScaler returns logits (un-sigmoidified) instead of probabilities — wrap in `1 / (1 + exp(-x))`
  - Non-monotonic when training data is small — handle the edge case with a clamp
  - ToxicityEnsemble divides by zero when all sub-model scores are equal — guard
- [ ] **7.2** Apply minimal fix with `Edit`.
- [ ] **7.3** Re-run Task 5 tests until pass.
- [ ] **7.4** Run all ml_ensemble tests to confirm no regression:
  ```bash
  cd backend && .venv/bin/python3 -m pytest tests/services/test_ml_ensemble* -v 2>&1 | tail -10
  ```
- [ ] **7.5** Commit + push + gate (subject `fix(a7-backend): <one-line>`).
- [ ] **7.6** Pulse.

---

## Task 8 — Fix ToxicityGauge (25 min)

- [ ] **8.1** Apply fixes for failing tests in Task 6. Common:
  - Null safety: `const v = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : null;`
  - Empty state: `if (v === null) return <div className="gauge gauge--no-data">—</div>;`
  - Color logic via className (testable) or via the fill prop on an SVG element
- [ ] **8.2** Re-run tests until all 4 pass.
- [ ] **8.3** eslint clean.
- [ ] **8.4** Commit + push + gate (subject `fix(a7-frontend): ToxicityGauge ...`).
- [ ] **8.5** Pulse.

---

## Task 9 — Document toxicity contract (15 min)

- [ ] **9.1** Write `docs/ROUND9_A7_TOXICITY_CONTRACT.md`:
  ```markdown
  # Toxicity Detection Contract
  
  ## Backend
  
  **Module:** `backend/services/ml_ensemble.py`
  
  **Function:** `ToxicityEnsemble.predict(features: dict) -> float`
  
  **Input features (required keys):**
  - `vpin`: float — Volume-Synchronized PIN, [0,1]
  - `ofi`: float — Order Flow Imbalance, signed
  - `queue_imbalance`: float — top-of-book imbalance, [-1, 1]
  - `spread_bps`: float — bid-ask spread in basis points
  - `volume_imbalance`: float — bid vs ask volume ratio
  
  **Output:** Single float in [0, 1] representing calibrated toxicity probability.
  
  **Calibration:** Platt scaling (`PlattScaler.transform`).
  
  **Thresholds (recommended for UI):**
  - [0.0, 0.4) — low (green)
  - [0.4, 0.7) — medium (yellow)
  - [0.7, 1.0] — high (red)
  
  ## Frontend
  
  **Component:** `frontend/src/components/ToxicityGauge.jsx`
  
  **Props:**
  - `value: number | null` — toxicity score, [0, 1] (null = no data, render empty state)
  
  **Behavior:**
  - Out-of-range values are clamped to [0, 1] for display
  - `null` / `undefined` renders empty state (no crash)
  - Color updates based on the thresholds above
  
  ## Round 10 candidates
  - <list any non-blocking issues you found>
  ```
- [ ] **9.2** Commit + push.
- [ ] **9.3** Pulse.

---

## Task 10 — Close-out (10 min)

- [ ] **10.1** `docs/ROUND9_A7_CLOSEOUT.md`.
- [ ] **10.2** Commit + push + gate.
- [ ] **10.3** Final pulse.

---

## Halt conditions

1. ml_ensemble.py imports modules that aren't installed → HALT, don't `pip install`.
2. Test reveals a model file dependency you can't resolve → HALT.
3. Frontend hook for toxicity is owned by another agent (collision) → STOP and coordinate.
4. Origin gate fails.
5. 15-min pulse gap.
