# Agent A5 — CharmChart + VannaChart Fix + Test Coverage (target: 2.5 hours)

**You are Agent A5.** Read `_PREAMBLE.md`. Scope: investigate user-reported broken `CharmChart.jsx` + `VannaChart.jsx`, fix the actual symptoms, lock in regression tests. Also extend `useGreeks.js` + `useWebSocketGex.jsx` hooks (these power the charts).

Your file ownership: `frontend/src/components/CharmChart.jsx`, `frontend/src/components/VannaChart.jsx`, `frontend/src/hooks/useGreeks.js`, `frontend/src/hooks/useWebSocketGex.jsx`, matching test files, new test files.

---

## Mission

| # | Task | Min |
|---|------|-----|
| 1 | Pre-flight + reproduce the symptom | 20 |
| 2 | Read CharmChart + identify failure mode | 20 |
| 3 | Read VannaChart + identify failure mode | 20 |
| 4 | Read useGreeks + useWebSocketGex hooks | 20 |
| 5 | Write failing test reproducing the broken state | 25 |
| 6 | Fix CharmChart (TDD) | 25 |
| 7 | Fix VannaChart (TDD) | 25 |
| 8 | Verify chain endpoint vanna/charm now populated | 15 |
| 9 | Memory snapshot + unmount cleanup test | 15 |
| 10 | Close-out doc | 10 |

Total ~195 min.

---

## Task 1 — Pre-flight + reproduce (20 min)

- [ ] **1.1** `pwd` → canonical.
- [ ] **1.2** Confirm recent vanna/charm work landed (commit `d8af12c` added vanna/charm to `/chain` endpoint):
  ```bash
  git log origin/main --oneline | grep -E 'chain greeks|vanna|charm' | head -3
  ```
- [ ] **1.3** Start the backend (background):
  ```bash
  lsof -ti :8000 | xargs kill -9 2>/dev/null
  cd backend && nohup .venv/bin/python3 -m uvicorn server:app --port 8000 > /tmp/uvicorn_a5.log 2>&1 &
  sleep 4
  ```
- [ ] **1.4** Hit the chain endpoint to see what data CharmChart/VannaChart actually receive:
  ```bash
  curl -s 'http://localhost:8000/chain?ticker=SPY' | python3 -c "
  import sys, json
  data = json.load(sys.stdin)
  print('top-level keys:', list(data.keys()))
  rows = data.get('rows', data.get('contracts', []))
  print('rows len:', len(rows))
  if rows:
      print('first row keys:', list(rows[0].keys()))
      print('first row vanna:', rows[0].get('vanna'))
      print('first row charm:', rows[0].get('charm'))
      # check if any row has non-zero vanna/charm
      nonzero_vanna = sum(1 for r in rows if r.get('vanna', 0) != 0)
      nonzero_charm = sum(1 for r in rows if r.get('charm', 0) != 0)
      print(f'non-zero vanna: {nonzero_vanna}/{len(rows)}')
      print(f'non-zero charm: {nonzero_charm}/{len(rows)}')
  "
  ```
  This tells you if the BACKEND is delivering the data. If non-zero counts are 0, that's a backend issue (but you can't touch market_data.py — A6 owns that). If non-zero counts are >0 but charts still don't render, it's a FRONTEND issue (your scope).
- [ ] **1.5** Capture the response shape to `/tmp/a5_chain_sample.json` for later test fixtures.
- [ ] **1.6** First pulse.

---

## Task 2 — Read CharmChart, identify failure (20 min)

- [ ] **2.1** Open `frontend/src/components/CharmChart.jsx` with `Read`. Read the WHOLE file.
- [ ] **2.2** Identify:
  - Where does it get data? (props? hook? fetch?)
  - What charting library is used (Recharts, Chart.js, D3, Plotly)?
  - What field does it read from the data? (likely `row.charm` per d8af12c)
  - Does it handle empty data / null data?
  - Does it handle data shape changes?
- [ ] **2.3** Trace the import chain. If CharmChart uses `useGreeks` or `useWebSocketGex`, you need to understand THOSE hooks too.
- [ ] **2.4** Write a brief "failure mode hypothesis" comment for yourself — what's likely broken? Examples:
  - Field name mismatch (chart reads `row.charmValue` but backend returns `row.charm`)
  - Data shape: chart expects flat array, backend returns nested
  - Missing null safety: chart crashes when `row.charm === null`
  - Wrong axis scaling
  - State not updating when WebSocket delivers new data
- [ ] **2.5** Pulse with hypothesis.

---

## Task 3 — Read VannaChart, identify failure (20 min)

Same drill as Task 2, for `frontend/src/components/VannaChart.jsx`. The two charts may share the same failure mode or differ.

- [ ] **3.1-3.5** Same steps as 2.

---

## Task 4 — Read the hooks (20 min)

- [ ] **4.1** Open `frontend/src/hooks/useGreeks.js` with `Read`.
- [ ] **4.2** Open `frontend/src/hooks/useWebSocketGex.jsx` with `Read`.
- [ ] **4.3** Identify:
  - What URL does `useGreeks` hit? Does it match the backend route?
  - Does it use `AbortController` for cleanup? (already H6 fixed `useMarketData.js`; verify if same fix needed here)
  - Does `useWebSocketGex` properly close the WebSocket on unmount? (audit the cleanup function in the useEffect — must call `ws.close()`)
  - Does the WebSocket parse a message format that matches what the backend sends?
- [ ] **4.4** Pulse with hook findings.

---

## Task 5 — Write failing test reproducing the broken state (25 min)

Goal: a Jest test that fails with the CURRENT broken code. This locks the behavior so your fix in Tasks 6-7 has a clear pass criterion.

- [ ] **5.1** Look at how existing charts are tested for examples:
  ```bash
  ls frontend/src/components/*.test.jsx | head -5
  cat frontend/src/components/heatseeker/FlipZonesPanel.test.jsx | head -40
  ```
- [ ] **5.2** Create or extend `frontend/src/components/CharmChart.test.jsx`:
  ```javascript
  import { render } from '@testing-library/react';
  import CharmChart from './CharmChart';
  
  describe('CharmChart', () => {
    const sampleRow = (overrides = {}) => ({
      type: 'call',
      strike: 450,
      iv: 0.18,
      delta: 0.5,
      gamma: 0.01,
      vega: 0.5,
      theta: -0.05,
      vanna: 0.002,
      charm: -0.001,
      moneyness_pct: 0.5,
      dte: 7,
      oi: 1000,
      volume: 500,
      ...overrides,
    });
  
    test('renders without crash when given a populated chain', () => {
      const rows = [sampleRow({ strike: 440 }), sampleRow({ strike: 450 }), sampleRow({ strike: 460 })];
      const { container } = render(<CharmChart rows={rows} spot={450} />);
      expect(container).toBeTruthy();
    });
  
    test('renders empty state when rows is empty', () => {
      const { container } = render(<CharmChart rows={[]} spot={450} />);
      // Should render SOMETHING (placeholder, "no data") — not crash
      expect(container.firstChild).not.toBeNull();
    });
  
    test('handles rows with null charm gracefully', () => {
      const rows = [sampleRow({ charm: null }), sampleRow({ charm: undefined })];
      const { container } = render(<CharmChart rows={rows} spot={450} />);
      expect(container.firstChild).not.toBeNull();  // no crash
    });
  
    test('reads the "charm" field (matches backend d8af12c contract)', () => {
      // If the chart uses a different field name like charmValue, this catches it
      const rows = [sampleRow({ charm: -0.002 })];
      // Render and check that the SVG path data isn't NaN
      const { container } = render(<CharmChart rows={rows} spot={450} />);
      const svg = container.querySelector('svg');
      if (svg) {
        const html = svg.outerHTML;
        expect(html).not.toContain('NaN');
        expect(html).not.toMatch(/[Mm]\s*NaN/);  // no NaN in path commands
      }
    });
  });
  ```
- [ ] **5.3** Same kind of test for VannaChart: `frontend/src/components/VannaChart.test.jsx`.
- [ ] **5.4** Run both:
  ```bash
  cd frontend && npx jest src/components/CharmChart.test.jsx src/components/VannaChart.test.jsx 2>&1 | tail -15
  ```
  Expected: some tests FAIL (those are the bugs you'll fix in 6-7).
- [ ] **5.5** Document which tests fail and why. Pulse.

---

## Task 6 — Fix CharmChart (TDD, 25 min)

- [ ] **6.1** Based on failure mode (Task 2) + failing tests (Task 5), apply the fix with `Edit`.
- [ ] **6.2** Common fixes:
  - Field name: `row.charmValue` → `row.charm` (or vice versa)
  - Null safety: `const charm = row.charm ?? 0;` before plotting
  - Empty state: `if (!rows || rows.length === 0) return <div className="empty-state">No data</div>;`
  - WebSocket data shape: parse the right field from the message
- [ ] **6.3** Re-run the test until all 4 cases pass.
- [ ] **6.4** Run eslint:
  ```bash
  cd frontend && npx eslint src/components/CharmChart.jsx --max-warnings=0
  ```
- [ ] **6.5** Commit:
  ```bash
  git add frontend/src/components/CharmChart.jsx frontend/src/components/CharmChart.test.jsx
  git commit -m "$(cat <<'EOF'
  fix(round-9-a5): CharmChart renders correctly with d8af12c chain contract
  
  <One-line failure mode> — <one-line fix>.
  
  Verification:
  \$ cd frontend && npx jest src/components/CharmChart.test.jsx
  4 passed
  EOF
  )"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'CharmChart'
  ```
- [ ] **6.6** Pulse.

---

## Task 7 — Fix VannaChart (25 min)

Same pattern as Task 6 for VannaChart. Likely shares the failure mode but verify independently.

---

## Task 8 — Backend-to-frontend round-trip verification (15 min)

- [ ] **8.1** Ensure backend still running on :8000. Open the React app via the PWA:
  ```bash
  open -a "$HOME/Applications/Chrome Apps.localized/Confluence Decoder.app"
  ```
- [ ] **8.2** Navigate to a view containing Charm/Vanna charts. If you can't visually inspect (Hermes Owl Alpha may not have screenshot capability), at minimum verify the underlying fetch:
  ```bash
  curl -s 'http://localhost:8000/chain?ticker=SPY' | python3 -c "
  import sys, json
  rows = json.load(sys.stdin).get('rows', [])
  nz_vanna = sum(1 for r in rows if r.get('vanna', 0) not in (0, None))
  nz_charm = sum(1 for r in rows if r.get('charm', 0) not in (0, None))
  print(f'non-zero vanna: {nz_vanna}/{len(rows)}')
  print(f'non-zero charm: {nz_charm}/{len(rows)}')
  assert nz_vanna > 0 or len(rows) == 0, 'all vanna are zero — backend bug, escalate to A6'
  assert nz_charm > 0 or len(rows) == 0, 'all charm are zero — backend bug, escalate to A6'
  "
  ```
- [ ] **8.3** Pulse.

---

## Task 9 — Memory snapshot + unmount cleanup test (15 min)

- [ ] **9.1** Extend `useWebSocketGex.test.jsx` (or create it) to verify unmount closes the WebSocket:
  ```javascript
  import { renderHook } from '@testing-library/react';
  import { useWebSocketGex } from './useWebSocketGex';
  
  describe('useWebSocketGex', () => {
    let mockClose;
    
    beforeEach(() => {
      mockClose = jest.fn();
      global.WebSocket = jest.fn(() => ({
        close: mockClose,
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        readyState: 1,
      }));
    });
    
    test('closes WebSocket on unmount', () => {
      const { unmount } = renderHook(() => useWebSocketGex('SPY'));
      unmount();
      expect(mockClose).toHaveBeenCalled();
    });
  });
  ```
- [ ] **9.2** Run: `cd frontend && npx jest src/hooks/useWebSocketGex.test 2>&1 | tail -10`. If the test fails, the hook is leaking — fix the cleanup return in the useEffect.
- [ ] **9.3** Commit + push + gate.
- [ ] **9.4** Pulse.

---

## Task 10 — Close-out (10 min)

- [ ] **10.1** Write `docs/ROUND9_A5_CLOSEOUT.md`:
  ```markdown
  # Agent A5 Close-out — Charm/Vanna Chart Fix
  
  ## Symptom (user report)
  - <briefly describe original failure mode you found>
  
  ## Root cause
  - <one paragraph>
  
  ## Commits
  | Task | SHA | Subject |
  
  ## Round 10 candidates
  - <any backend issues you couldn't fix (A6's scope)>
  ```
- [ ] **10.2** Commit + push + gate.
- [ ] **10.3** Final pulse.

---

## Halt conditions

1. Pre-flight backend curl shows non-zero vanna/charm counts of 0 across ALL rows → backend bug, A6's scope. Document and STOP fixing frontend (you can still write the failing tests; they'll pass once A6 fixes backend).
2. The "fix" requires editing `market_data.py` or `bs_greeks.py` → A6/A10's scope, STOP.
3. A fix introduces eslint errors.
4. Origin gate fails.
5. 15-min pulse gap.
