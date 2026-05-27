# Agent A4 — Heatseeker Panel Test Coverage + Hardening (target: 2.5 hours)

**You are Agent A4.** Read `_PREAMBLE.md`. Scope: extend test coverage of the 5 React Heatseeker panels, audit the backend `heatseeker.py` + `heatseeker_snapshots.py` for edge cases, and write regression tests for the Round-9 H4 degraded-response hardening.

Your file ownership: `backend/services/heatseeker.py`, `backend/services/heatseeker_snapshots.py`, `frontend/src/components/heatseeker/*` (AirPocketsPanel, BeachBallIndicator, FlipZonesPanel, HeatseekerDashboard, NodeClassificationPanel), matching `*.test.jsx` files, new test files.

**DO NOT TOUCH** `backend/routes/heatseeker.py` (already hardened in commit bc5e942 by architect — your tests will validate that hardening).

---

## Mission

| # | Task | Min |
|---|------|-----|
| 1 | Pre-flight + read existing tests | 15 |
| 2 | Read H4 degraded-response commit + write contract regression | 25 |
| 3 | Inspect each panel + identify missing test cases | 25 |
| 4 | Extend AirPocketsPanel test (loading + error + degraded) | 20 |
| 5 | Extend FlipZonesPanel test (same patterns) | 20 |
| 6 | Extend NodeClassificationPanel test | 20 |
| 7 | Extend BeachBallIndicator test (visual gauge edge cases) | 15 |
| 8 | Extend HeatseekerDashboard test (panel composition) | 20 |
| 9 | Backend `heatseeker.py` edge-case test (empty chain, missing IV) | 20 |
| 10 | Close-out doc | 10 |

Total ~190 min.

---

## Task 1 — Pre-flight (15 min)

- [ ] **1.1** `pwd` → `…/Documents/GitHub/floww`.
- [ ] **1.2** Confirm H4 already landed:
  ```bash
  git log origin/main --oneline | grep -i 'heatseeker' | head -3
  ```
- [ ] **1.3** List existing tests:
  ```bash
  ls frontend/src/components/heatseeker/*.test.jsx
  ```
  Note: 5 test files exist (AirPocketsPanel, BeachBallIndicator, FlipZonesPanel, HeatseekerDashboard, NodeClassificationPanel).
- [ ] **1.4** Run them as-is to baseline:
  ```bash
  cd frontend && npx jest src/components/heatseeker/ --no-coverage 2>&1 | tail -10
  ```
  Capture pass count.
- [ ] **1.5** Backend tests for heatseeker:
  ```bash
  ls backend/tests/services/test_heatseeker* 2>&1 | head -5
  ```
- [ ] **1.6** Run backend heatseeker tests:
  ```bash
  cd backend && .venv/bin/python3 -m pytest tests/ -k heatseeker -v 2>&1 | tail -10
  ```
- [ ] **1.7** First pulse.

---

## Task 2 — H4 contract regression test (25 min)

H4 hardened `flip_zones`, `node_lifecycle`, `air_pockets` routes to return `{"status": "degraded", ...}` instead of HTTP 500 on chain/history fetch failures. Your test asserts this contract holds.

- [ ] **2.1** Read the commit:
  ```bash
  git show bc5e942 -- backend/routes/heatseeker.py | head -60
  ```
- [ ] **2.2** Create `backend/tests/routes/test_heatseeker_degraded.py`:
  ```python
  """Regression: H4 hardening — heatseeker routes degrade gracefully."""
  import pytest
  from unittest.mock import patch, AsyncMock
  from fastapi.testclient import TestClient
  
  
  @pytest.fixture
  def client():
      from server import app
      return TestClient(app)
  
  
  def _broken_fetch(*a, **kw):
      raise RuntimeError("simulated chain fetch failure")
  
  
  def test_flip_zones_returns_degraded_on_chain_failure(client):
      with patch("routes.heatseeker._fetch_chain", new=AsyncMock(side_effect=_broken_fetch)):
          r = client.get("/heatseeker/flip-zones?ticker=SPY")
          # H4: returns 200 with status=degraded, NOT HTTP 500
          assert r.status_code == 200, f"expected 200 degraded, got {r.status_code}"
          body = r.json()
          assert body.get("status") == "degraded", body
          assert body.get("zones") == [], body
  
  
  def test_node_lifecycle_returns_degraded_on_failure(client):
      with patch("routes.heatseeker._fetch_chain", new=AsyncMock(side_effect=_broken_fetch)):
          r = client.get("/heatseeker/node-lifecycle?ticker=SPY")
          assert r.status_code == 200
          body = r.json()
          assert body.get("status") == "degraded", body
          assert body.get("nodes") == [], body
  
  
  def test_air_pockets_returns_degraded_on_failure(client):
      with patch("routes.heatseeker._fetch_chain", new=AsyncMock(side_effect=_broken_fetch)):
          r = client.get("/heatseeker/air-pockets?ticker=SPY")
          assert r.status_code == 200
          body = r.json()
          assert body.get("status") == "degraded", body
  
  
  def test_routes_still_propagate_404_for_missing_data(client):
      """HTTPException 404 must still propagate (not get swallowed by the catch-all)."""
      # Simulate empty chain — HTTPException(404, "No options data") should fire
      with patch("routes.heatseeker._fetch_chain", new=AsyncMock(return_value={"spot": None, "contracts": []})):
          r = client.get("/heatseeker/flip-zones?ticker=ZZZ")
          assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text}"
  ```
- [ ] **2.3** Run:
  ```bash
  cd backend && .venv/bin/python3 -m pytest tests/routes/test_heatseeker_degraded.py -v 2>&1 | tail -10
  ```
  Expected: 4 PASSED. If any fail, that means H4's hardening doesn't quite match the contract — note in close-out, do NOT modify routes/heatseeker.py to "fix" it (forbidden file).
- [ ] **2.4** Commit:
  ```bash
  git add backend/tests/routes/test_heatseeker_degraded.py
  git commit -m "test(round-9-a4): regression for H4 heatseeker degraded-response contract"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'a4.*heatseeker'
  ```
- [ ] **2.5** Pulse.

---

## Task 3 — Inspect each panel + identify gaps (25 min)

For EACH of the 5 panels, open the `.jsx` AND its `.test.jsx` with `Read`. For each component check:
- Does it handle `status === "degraded"` from the API?
- Does it handle empty data (`zones: []`, `nodes: []`)?
- Does it handle `loading` state?
- Does it handle `error` state?
- Does it cleanup intervals/subscriptions on unmount? (Tasks 4-8 will add tests for this if not covered.)

Document gaps in a scratch file `/tmp/a4_gaps.txt` — Tasks 4-8 will close them one by one.

- [ ] **3.1** Read `AirPocketsPanel.jsx` + `AirPocketsPanel.test.jsx`. Note 3-5 missing test cases.
- [ ] **3.2** Same for FlipZonesPanel, NodeClassificationPanel, BeachBallIndicator, HeatseekerDashboard.
- [ ] **3.3** Pulse: `T3 done :: <N> gaps identified`.

---

## Tasks 4-8 — Per-panel test extension (~20 min each)

**Template for each panel:**

- [ ] **X.1** Open the `.test.jsx` file. Identify existing test structure (Jest? React Testing Library? Vitest?).
- [ ] **X.2** Add 3-5 new tests for missing coverage. Use the same imports/utilities as existing tests in the file. Examples of useful new tests:
  ```javascript
  // Degraded API response handling
  test('renders fallback when API returns status:degraded', () => {
    const props = { data: { status: 'degraded', zones: [], error: 'simulated' } };
    const { getByText } = render(<FlipZonesPanel {...props} />);
    expect(getByText(/unavailable|degraded|not available/i)).toBeInTheDocument();
  });
  
  // Empty data
  test('renders empty state when zones is []', () => {
    const props = { data: { zones: [], spot: 100 } };
    const { container } = render(<FlipZonesPanel {...props} />);
    // assert no zone rows rendered
    expect(container.querySelectorAll('.zone-row').length).toBe(0);
  });
  
  // Loading
  test('renders skeleton when isLoading', () => {
    const { getByTestId } = render(<FlipZonesPanel isLoading={true} />);
    expect(getByTestId('flipzones-skeleton')).toBeInTheDocument();
  });
  
  // Unmount cleanup
  test('unmount clears polling intervals', () => {
    jest.useFakeTimers();
    const before = jest.getTimerCount();
    const { unmount } = render(<FlipZonesPanel />);
    const during = jest.getTimerCount();
    unmount();
    expect(jest.getTimerCount()).toBeLessThan(during);
    jest.useRealTimers();
  });
  ```
  **IMPORTANT:** if a test you write requires the component to handle a state it currently does NOT handle (e.g., it doesn't show a "degraded" message), that's a real gap — either:
  - (a) Extend the component to handle that state (allowed under your scope), OR
  - (b) If the gap is large (>20 lines of component change), document it and skip that specific test for Round 10.
- [ ] **X.3** Run JUST the panel's tests:
  ```bash
  cd frontend && npx jest src/components/heatseeker/<Panel>.test.jsx 2>&1 | tail -15
  ```
  Must all pass.
- [ ] **X.4** Commit:
  ```bash
  git add frontend/src/components/heatseeker/<Panel>.test.jsx frontend/src/components/heatseeker/<Panel>.jsx
  git commit -m "test(round-9-a4): extend <Panel> coverage (degraded + empty + loading + cleanup)"
  git pull --rebase origin main && git push origin main
  ```
- [ ] **X.5** Pulse.

(Repeat for all 5 panels: Tasks 4, 5, 6, 7, 8.)

---

## Task 9 — Backend `heatseeker.py` edge cases (20 min)

`backend/services/heatseeker.py` and `heatseeker_snapshots.py` contain the calc functions (`calc_flip_zones`, `calc_node_lifecycle`, etc.). Add edge-case tests.

- [ ] **9.1** Read `services/heatseeker.py` to find the public calc functions:
  ```bash
  grep -nE '^def calc_|^def compute_' backend/services/heatseeker.py
  ```
- [ ] **9.2** Create `backend/tests/services/test_heatseeker_edge_cases.py`:
  ```python
  """Edge cases for heatseeker calc functions."""
  import pytest
  from services.heatseeker import calc_flip_zones, calc_node_lifecycle
  
  
  def test_flip_zones_empty_chain_returns_empty_zones():
      result = calc_flip_zones(spot=100, contracts=[], window_pct=0.05)
      assert isinstance(result, dict)
      assert result.get("zones") == [] or result.get("zones") is None
  
  
  def test_flip_zones_zero_spot_does_not_crash():
      # Spot of 0 is a real edge case (preflight failure, market closed weird state)
      contracts = [{"strike": 100, "type": "call", "gamma": 0.01, "oi": 1000}]
      try:
          result = calc_flip_zones(spot=0, contracts=contracts, window_pct=0.05)
          # Either returns empty zones or raises a controlled exception
          assert isinstance(result, dict)
      except (ValueError, ZeroDivisionError):
          pass  # Acceptable: controlled exception, not silent corruption
  
  
  def test_node_lifecycle_with_no_history_uses_chain_only():
      contracts = [
          {"strike": 100, "type": "call", "gamma": 0.01, "oi": 5000},
          {"strike": 105, "type": "put", "gamma": 0.008, "oi": 4000},
      ]
      result = calc_node_lifecycle(spot=102, contracts=contracts, history=[])
      assert isinstance(result, dict)
      # When history is empty, all nodes should be classified as Fresh (no prior tests)
      nodes = result.get("nodes", [])
      for n in nodes:
          assert n.get("classification") in {"Fresh", "Tested", "Delivered", "Decaying"}
  ```
- [ ] **9.3** Run: `cd backend && .venv/bin/python3 -m pytest tests/services/test_heatseeker_edge_cases.py -v 2>&1 | tail -10`.
  If a test fails because the function genuinely crashes on edge case → that's a real bug. Note in close-out, do NOT modify the function silently. Instead, file as Round 10 ticket.
- [ ] **9.4** Commit + push + gate.
- [ ] **9.5** Pulse.

---

## Task 10 — Close-out (10 min)

- [ ] **10.1** Write `docs/ROUND9_A4_CLOSEOUT.md`:
  ```markdown
  # Agent A4 Close-out — Heatseeker Test Coverage
  
  ## Commits
  | Task | SHA | Subject |
  
  ## Test counts
  - BEFORE: <T1.4>
  - AFTER: <re-run from T10>
  - Net: +<N> heatseeker tests
  
  ## Component handling gaps closed
  - <list each panel + new test types added>
  
  ## Round 10 candidates
  - <any edge cases that revealed real bugs in services/heatseeker.py>
  ```
- [ ] **10.2** Commit + push + gate.
- [ ] **10.3** Final pulse.

---

## Halt conditions

1. H4 hardening contract test (T2) fails — that means routes/heatseeker.py has a real bug; document, don't touch (forbidden).
2. A new test requires modifying a panel in a way >20 lines — defer to R10.
3. Edge-case test reveals real backend bug — document, don't silently fix.
4. Origin gate fails.
5. 15-min pulse gap.
