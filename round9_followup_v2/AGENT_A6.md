# Agent A6 — OptionsChainTable + Expiry Filter + DTE Filter (target: 2.5 hours)

**You are Agent A6.** Read `_PREAMBLE.md`. Scope: investigate + fix `OptionsChainTable.jsx` (rendering the chain), add or fix expiry filter, add or fix DTE filter. Extend backend `/chain` endpoint if needed (your scope includes `routes/market_data.py` chain endpoint additions only — not the whole file).

Your file ownership: `frontend/src/components/OptionsChainTable.jsx`, `frontend/src/components/ExpiryFilter*.jsx` (if exists or new), `frontend/src/components/DTEFilter*.jsx` (if exists or new), `backend/routes/market_data.py` (ONLY the chain endpoint section), matching test files.

---

## Mission

| # | Task | Min |
|---|------|-----|
| 1 | Pre-flight + reproduce symptoms | 20 |
| 2 | Read OptionsChainTable, find render bugs | 25 |
| 3 | Audit existing expiry/DTE filtering | 20 |
| 4 | Backend: verify chain endpoint supports filter params | 15 |
| 5 | Write failing tests for all symptoms | 25 |
| 6 | Fix OptionsChainTable | 30 |
| 7 | Add/fix ExpiryFilter component | 25 |
| 8 | Add/fix DTEFilter component | 20 |
| 9 | Smoke test full chain UI workflow | 10 |
| 10 | Close-out doc | 10 |

Total ~200 min.

---

## Task 1 — Pre-flight + reproduce (20 min)

- [ ] **1.1** `pwd` canonical.
- [ ] **1.2** Confirm vanna/charm/dte/moneyness landed in chain endpoint (commit `d8af12c`):
  ```bash
  git show d8af12c -- backend/routes/market_data.py | head -40
  ```
- [ ] **1.3** Start backend + verify chain endpoint:
  ```bash
  lsof -ti :8000 | xargs kill -9 2>/dev/null
  cd backend && nohup .venv/bin/python3 -m uvicorn server:app --port 8000 > /tmp/uvicorn_a6.log 2>&1 &
  sleep 4
  curl -s 'http://localhost:8000/chain?ticker=SPY' | python3 -c "
  import sys, json
  data = json.load(sys.stdin)
  rows = data.get('rows', data.get('contracts', []))
  print('rows:', len(rows))
  if rows:
      r = rows[0]
      print('fields:', sorted(r.keys()))
      print('sample:', {k: r.get(k) for k in ['type','strike','dte','expiry','vanna','charm','moneyness_pct']})
      # check expiry diversity
      exps = set(r.get('expiry') for r in rows)
      dtes = set(r.get('dte') for r in rows)
      print('unique expiries:', len(exps), 'sample:', list(exps)[:5])
      print('unique dtes:', sorted(dtes)[:10])
  "
  ```
  Save the row keys + counts.
- [ ] **1.4** Save sample response to `/tmp/a6_chain_sample.json` for test fixtures.
- [ ] **1.5** First pulse.

---

## Task 2 — Read OptionsChainTable + find render bugs (25 min)

- [ ] **2.1** Open `frontend/src/components/OptionsChainTable.jsx` with `Read`. Full file.
- [ ] **2.2** Check for:
  - What data prop shape does it expect? (Should be `rows: [{...}]` matching backend)
  - Which columns are rendered? (strike, bid/ask, IV, delta, gamma, vega, theta, vanna, charm, OI, volume, dte, moneyness_pct, ...)
  - Are vanna/charm/dte/moneyness_pct columns shown? (They were added by d8af12c — likely table is missing them)
  - Is there null safety on cell values? (e.g., `row.charm?.toFixed(4)` not `row.charm.toFixed(4)`)
  - Is there a sort feature? Does it handle missing values gracefully?
  - Is the table virtualized for large chains?
- [ ] **2.3** Note all real bugs in /tmp/a6_table_bugs.txt.
- [ ] **2.4** Pulse.

---

## Task 3 — Audit existing expiry/DTE filtering (20 min)

- [ ] **3.1** Search for any existing filter components:
  ```bash
  ls frontend/src/components/ | grep -iE 'expir|dte|filter' 2>&1 | head -10
  grep -rn 'ExpiryFilter\|DTEFilter\|expiryFilter\|dteFilter' frontend/src/ --include='*.jsx' --include='*.js' | head -10
  ```
- [ ] **3.2** If components exist, open them. Note what they currently do and what's broken.
- [ ] **3.3** If they DON'T exist, you'll create them in Tasks 7-8. Sketch the API:
  - `<ExpiryFilter expiries={['2026-05-30', '2026-06-06', ...]} value={selectedExpiry} onChange={fn} />`
  - `<DTEFilter min={0} max={365} value={[0, 30]} onChange={fn} />`
- [ ] **3.4** Pulse.

---

## Task 4 — Backend chain endpoint: verify filter params (15 min)

`backend/routes/market_data.py` `/chain` endpoint already accepts `expiry: Optional[str]` (see d8af12c diff line ~183). Verify and add DTE filter if missing.

- [ ] **4.1** Read the chain function signature:
  ```bash
  grep -A5 'async def chain' backend/routes/market_data.py | head -10
  ```
- [ ] **4.2** Check for DTE filter param (likely missing). If missing, add a `dte_max: Optional[int] = None` query param. After the row construction (around line 230), add a filter:
  ```python
  # Apply DTE filter if present
  if dte_max is not None:
      rows = [r for r in rows if r.get("dte", 0) <= dte_max]
  ```
- [ ] **4.3** Test:
  ```bash
  curl -s 'http://localhost:8000/chain?ticker=SPY&dte_max=7' | python3 -c "
  import sys, json
  rows = json.load(sys.stdin).get('rows', [])
  print(f'filtered rows: {len(rows)}')
  print(f'max dte in result: {max((r.get(\"dte\", 0) for r in rows), default=0)}')
  "
  ```
- [ ] **4.4** Commit (only the chain endpoint, not whole file):
  ```bash
  git add backend/routes/market_data.py
  git commit -m "feat(round-9-a6): chain endpoint accepts dte_max filter param"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'a6.*dte_max'
  ```
- [ ] **4.5** Pulse.

---

## Task 5 — Write failing tests for all symptoms (25 min)

- [ ] **5.1** Create `frontend/src/components/OptionsChainTable.test.jsx`:
  ```javascript
  import { render } from '@testing-library/react';
  import OptionsChainTable from './OptionsChainTable';
  
  describe('OptionsChainTable', () => {
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
      bid: 5.2,
      ask: 5.3,
      expiry: '2026-05-30',
      ...overrides,
    });
  
    test('renders without crash on populated rows', () => {
      const rows = [sampleRow(), sampleRow({ strike: 460 })];
      const { container } = render(<OptionsChainTable rows={rows} spot={450} />);
      expect(container).toBeTruthy();
    });
  
    test('renders new vanna column (d8af12c contract)', () => {
      const rows = [sampleRow({ vanna: 0.0042 })];
      const { container } = render(<OptionsChainTable rows={rows} spot={450} />);
      // Should display vanna somewhere
      expect(container.textContent).toMatch(/vanna|Vanna|VANNA|0\.004/i);
    });
  
    test('renders new charm column', () => {
      const rows = [sampleRow({ charm: -0.0021 })];
      const { container } = render(<OptionsChainTable rows={rows} spot={450} />);
      expect(container.textContent).toMatch(/charm|Charm|CHARM|-0\.002/i);
    });
  
    test('renders dte column', () => {
      const rows = [sampleRow({ dte: 14 })];
      const { container } = render(<OptionsChainTable rows={rows} spot={450} />);
      expect(container.textContent).toMatch(/14|DTE|dte/);
    });
  
    test('handles rows with null greeks gracefully', () => {
      const rows = [sampleRow({ vanna: null, charm: undefined, moneyness_pct: null })];
      const { container } = render(<OptionsChainTable rows={rows} spot={450} />);
      // Must not throw, must not display literal "null"
      expect(container.textContent).not.toContain('null');
      expect(container.textContent).not.toContain('undefined');
    });
  });
  ```
- [ ] **5.2** Run: `cd frontend && npx jest src/components/OptionsChainTable.test.jsx 2>&1 | tail -15`. Expect some FAILS (you'll fix in Task 6).
- [ ] **5.3** Pulse.

---

## Task 6 — Fix OptionsChainTable (30 min)

Apply fixes based on Task 2 findings + Task 5 failing tests. Common needs:
- Add vanna/charm/dte/moneyness_pct columns to the table header + body
- Add null-safe rendering: `{row.vanna != null ? row.vanna.toFixed(4) : '—'}`
- Add column sorting that handles nulls (sort to bottom)
- Add empty state when `rows.length === 0`

- [ ] **6.1** Apply fixes with `Edit`.
- [ ] **6.2** Re-run tests until all 5 pass.
- [ ] **6.3** eslint clean.
- [ ] **6.4** Commit (subject `OptionsChainTable`).
- [ ] **6.5** Pulse.

---

## Task 7 — ExpiryFilter component (25 min)

- [ ] **7.1** If component exists, fix bugs found in Task 3. If not, create `frontend/src/components/ExpiryFilter.jsx`:
  ```jsx
  import React from 'react';
  
  /**
   * Drop-down for selecting an option expiry from the available chain.
   *
   * Props:
   *   expiries: string[]   — list of YYYY-MM-DD strings
   *   value: string | null  — currently selected expiry
   *   onChange: (string|null) => void
   */
  export default function ExpiryFilter({ expiries = [], value, onChange }) {
    if (!Array.isArray(expiries) || expiries.length === 0) {
      return <span className="expiry-filter expiry-filter--empty">No expiries</span>;
    }
  
    const handleChange = (e) => {
      const v = e.target.value;
      onChange(v === '__all__' ? null : v);
    };
  
    return (
      <select
        className="expiry-filter"
        value={value || '__all__'}
        onChange={handleChange}
        aria-label="Filter by expiry"
      >
        <option value="__all__">All expiries</option>
        {expiries.map((exp) => (
          <option key={exp} value={exp}>
            {exp}
          </option>
        ))}
      </select>
    );
  }
  ```
- [ ] **7.2** Create test `frontend/src/components/ExpiryFilter.test.jsx`:
  ```jsx
  import { render, fireEvent } from '@testing-library/react';
  import ExpiryFilter from './ExpiryFilter';
  
  describe('ExpiryFilter', () => {
    test('renders all expiries as options', () => {
      const { getAllByRole } = render(
        <ExpiryFilter expiries={['2026-05-30', '2026-06-06']} value={null} onChange={() => {}} />
      );
      const opts = getAllByRole('option');
      expect(opts.length).toBe(3); // 2 + "All"
    });
  
    test('shows empty state when no expiries', () => {
      const { getByText } = render(<ExpiryFilter expiries={[]} value={null} onChange={() => {}} />);
      expect(getByText(/no expiries/i)).toBeInTheDocument();
    });
  
    test('emits null when "All" selected', () => {
      const fn = jest.fn();
      const { getByLabelText } = render(
        <ExpiryFilter expiries={['2026-05-30']} value="2026-05-30" onChange={fn} />
      );
      fireEvent.change(getByLabelText(/filter by expiry/i), { target: { value: '__all__' } });
      expect(fn).toHaveBeenCalledWith(null);
    });
  
    test('emits selected expiry on change', () => {
      const fn = jest.fn();
      const { getByLabelText } = render(
        <ExpiryFilter expiries={['2026-05-30', '2026-06-06']} value={null} onChange={fn} />
      );
      fireEvent.change(getByLabelText(/filter by expiry/i), { target: { value: '2026-06-06' } });
      expect(fn).toHaveBeenCalledWith('2026-06-06');
    });
  });
  ```
- [ ] **7.3** Run: `cd frontend && npx jest src/components/ExpiryFilter 2>&1 | tail -10` → 4 PASSED.
- [ ] **7.4** Commit + push + gate.
- [ ] **7.5** Pulse.

---

## Task 8 — DTEFilter component (20 min)

- [ ] **8.1** Create `frontend/src/components/DTEFilter.jsx`:
  ```jsx
  import React from 'react';
  
  /**
   * Numeric input for max days-to-expiry filter.
   *
   * Props:
   *   value: number | null   — current max DTE (null = no limit)
   *   onChange: (number|null) => void
   *   min: number  — default 0
   *   max: number  — default 365
   */
  export default function DTEFilter({ value, onChange, min = 0, max = 365 }) {
    const display = value == null ? '' : String(value);
  
    const handleChange = (e) => {
      const raw = e.target.value.trim();
      if (raw === '') {
        onChange(null);
        return;
      }
      const n = parseInt(raw, 10);
      if (Number.isFinite(n) && n >= min && n <= max) {
        onChange(n);
      }
    };
  
    return (
      <label className="dte-filter">
        Max DTE:
        <input
          type="number"
          min={min}
          max={max}
          value={display}
          onChange={handleChange}
          placeholder="any"
          aria-label="Maximum days to expiry"
        />
      </label>
    );
  }
  ```
- [ ] **8.2** Test `frontend/src/components/DTEFilter.test.jsx`:
  ```jsx
  import { render, fireEvent } from '@testing-library/react';
  import DTEFilter from './DTEFilter';
  
  test('emits null when input cleared', () => {
    const fn = jest.fn();
    const { getByLabelText } = render(<DTEFilter value={7} onChange={fn} />);
    fireEvent.change(getByLabelText(/maximum days to expiry/i), { target: { value: '' } });
    expect(fn).toHaveBeenCalledWith(null);
  });
  
  test('emits parsed number when valid input', () => {
    const fn = jest.fn();
    const { getByLabelText } = render(<DTEFilter value={null} onChange={fn} />);
    fireEvent.change(getByLabelText(/maximum days to expiry/i), { target: { value: '30' } });
    expect(fn).toHaveBeenCalledWith(30);
  });
  
  test('rejects out-of-range values', () => {
    const fn = jest.fn();
    const { getByLabelText } = render(<DTEFilter value={null} onChange={fn} max={365} />);
    fireEvent.change(getByLabelText(/maximum days to expiry/i), { target: { value: '99999' } });
    expect(fn).not.toHaveBeenCalled();
  });
  ```
- [ ] **8.3** Run → 3 PASSED.
- [ ] **8.4** Commit + push + gate.
- [ ] **8.5** Pulse.

---

## Task 9 — Smoke test full chain UI workflow (10 min)

- [ ] **9.1** With backend running, hit chain with expiry+dte filters:
  ```bash
  curl -s 'http://localhost:8000/chain?ticker=SPY&dte_max=14' | python3 -c "
  import sys, json
  rows = json.load(sys.stdin).get('rows', [])
  max_dte = max((r.get('dte', 0) for r in rows), default=0)
  print(f'rows: {len(rows)}, max dte: {max_dte}')
  assert max_dte <= 14, f'filter not applied — max dte is {max_dte}'
  print('OK')
  "
  ```
- [ ] **9.2** Pulse.

---

## Task 10 — Close-out (10 min)

- [ ] **10.1** `docs/ROUND9_A6_CLOSEOUT.md` with table of commits, symptoms fixed, new components added.
- [ ] **10.2** Commit + push + gate.
- [ ] **10.3** Final pulse.

---

## Halt conditions

1. Pre-flight chain endpoint returns 0 rows for SPY → backend setup issue, document + stop.
2. d8af12c fields (vanna/charm/dte/moneyness_pct) missing from chain response → backend regression, escalate.
3. A new filter component conflicts with existing one of the same name → audit first, don't overwrite.
4. Origin gate fails.
5. 15-min pulse gap.
