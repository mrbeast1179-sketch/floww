# Hermes Owl Alpha — Agent H28 · Frontend Memory-Leak Audit + Top-3 Fixes (~90 min)

You are Agent H28. You execute L2+L3 from the original Round 9 plan: a comprehensive audit of frontend memory leaks (setInterval/setTimeout cleanup + useEffect cleanup + AbortController abort-on-unmount + addEventListener teardown), then fix the 3 highest-severity findings you discover.

This is the BACKEND L1 leak audit's mirror for the frontend. L1 found 14 backend leaks (4 fixed by Pro, 4 by H26). Frontend likely has 10-20 similar findings — React's `useEffect` makes it easy to leak intervals and subscriptions on unmount.

---

## Mission scope

1. **Audit phase** (~45 min): Read every file under `frontend/src/hooks/` and `frontend/src/components/` that uses `setInterval`, `setTimeout`, `useEffect`, `addEventListener`, `new AbortController()`, or `new EventSource()`. Write findings to `docs/ROUND9_FRONTEND_LEAK_AUDIT.md` with `file:line` + severity + recommended fix.
2. **Fix phase** (~45 min): Apply 3 fixes — the High-severity ones you found, with grep proof before/after in each commit message.

---

## Hard constraints

- **Canonical clone**: `/Users/nav/Documents/GitHub/floww`. **Never** the stale one.
- **Forbidden files**: `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`, `frontend/src/App.js` (heavy WIP — don't touch), any `.css` file (cosmetic, not your scope).
- **No `--force`, `--no-verify`, `--amend` others' commits, `--hard`, `clean -fd`.**
- **NEVER** mark a Jest test `.skip()` or `it.skip(...)`. If a test fails, fix it.
- **No npm install / no package.json edits.** If a fix needs a new dependency, HALT and ask the architect — don't add it yourself.
- **Origin gate after every commit.**
- **15-min pulse** to `kanban/cards/agent_H28_status.md`.

---

## Reference: what a leak looks like in React

### Leak pattern A — interval without cleanup
```javascript
useEffect(() => {
  const id = setInterval(() => fetchData(), 5000);
  // NO return — interval leaks every time component unmounts
}, []);
```
Fix:
```javascript
useEffect(() => {
  const id = setInterval(() => fetchData(), 5000);
  return () => clearInterval(id);
}, []);
```

### Leak pattern B — fetch without abort on unmount
```javascript
useEffect(() => {
  fetch(url).then(setData);  // if component unmounts mid-fetch, setData fires on dead component
}, [url]);
```
Fix:
```javascript
useEffect(() => {
  const ctrl = new AbortController();
  fetch(url, { signal: ctrl.signal })
    .then(setData)
    .catch((e) => { if (e.name !== 'AbortError') throw e; });
  return () => ctrl.abort();
}, [url]);
```

### Leak pattern C — addEventListener without remove
```javascript
useEffect(() => {
  window.addEventListener('resize', handler);
}, []);
```
Fix:
```javascript
useEffect(() => {
  window.addEventListener('resize', handler);
  return () => window.removeEventListener('resize', handler);
}, []);
```

### Leak pattern D — WebSocket without close
```javascript
useEffect(() => {
  const ws = new WebSocket(url);
  ws.onmessage = ...;
}, [url]);
```
Fix:
```javascript
useEffect(() => {
  const ws = new WebSocket(url);
  ws.onmessage = ...;
  return () => ws.close();
}, [url]);
```

---

## Pre-flight

- [ ] **PF1.** `pwd` ends in `/Users/nav/Documents/GitHub/floww`.

- [ ] **PF2.** Confirm working tree clean except for the known untracked file:
  ```
  git status --short
  ```
  Expected: only `?? backend/tests/services/ml/test_ml_integration.py`.

- [ ] **PF3.** Confirm Round-9 H6 already landed (it fixed `fetch({timeout: 30000})` in useMarketData.js — your audit should already see the corrected pattern there):
  ```
  git log origin/main --oneline | grep 'H6' | head -2
  ```
  Expected: at least one match.

- [ ] **PF4.** Estimate scope:
  ```
  echo "setInterval/setTimeout sites:"
  grep -rEn 'setInterval\(|setTimeout\(' frontend/src/ --include='*.js' --include='*.jsx' | wc -l
  echo "useEffect sites:"
  grep -rn 'useEffect(' frontend/src/ --include='*.js' --include='*.jsx' | wc -l
  echo "addEventListener sites:"
  grep -rn 'addEventListener(' frontend/src/ --include='*.js' --include='*.jsx' | wc -l
  echo "AbortController sites:"
  grep -rn 'new AbortController' frontend/src/ --include='*.js' --include='*.jsx' | wc -l
  echo "WebSocket sites:"
  grep -rn 'new WebSocket' frontend/src/ --include='*.js' --include='*.jsx' | wc -l
  ```
  Save the numbers — you'll cite them in the audit doc summary.

- [ ] **PF5.** Pulse:
  ```
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H28 :: started :: pre-flight done :: HEAD=$(git rev-parse --short HEAD)" \
    >> kanban/cards/agent_H28_status.md
  ```

---

## Phase 1: Audit (45 min)

### Task A1: Enumerate every leaky pattern (15 min)

For each pattern below, run the grep and CAPTURE the output. Save to a scratch file (you'll consolidate in A2).

- [ ] **A1.1** Intervals without paired cleanup:
  ```
  for file in $(grep -rEln 'setInterval\(' frontend/src/ --include='*.js' --include='*.jsx'); do
    intervals=$(grep -c 'setInterval(' "$file")
    clears=$(grep -c 'clearInterval(' "$file")
    if [ "$intervals" -gt "$clears" ]; then
      echo "POTENTIAL_LEAK: $file ($intervals setInterval, $clears clearInterval)"
    fi
  done
  ```

- [ ] **A1.2** Timeouts without paired cleanup (often OK if short-lived — note severity Med/Low):
  ```
  for file in $(grep -rEln 'setTimeout\(' frontend/src/ --include='*.js' --include='*.jsx'); do
    sets=$(grep -c 'setTimeout(' "$file")
    clears=$(grep -c 'clearTimeout(' "$file")
    if [ "$sets" -gt "$clears" ]; then
      echo "POTENTIAL_LEAK: $file ($sets setTimeout, $clears clearTimeout)"
    fi
  done
  ```

- [ ] **A1.3** addEventListener without removeEventListener:
  ```
  for file in $(grep -rEln 'addEventListener\(' frontend/src/ --include='*.js' --include='*.jsx'); do
    adds=$(grep -c 'addEventListener(' "$file")
    removes=$(grep -c 'removeEventListener(' "$file")
    if [ "$adds" -gt "$removes" ]; then
      echo "POTENTIAL_LEAK: $file ($adds addEventListener, $removes removeEventListener)"
    fi
  done
  ```

- [ ] **A1.4** WebSocket without close:
  ```
  for file in $(grep -rEln 'new WebSocket\(' frontend/src/ --include='*.js' --include='*.jsx'); do
    opens=$(grep -c 'new WebSocket(' "$file")
    closes=$(grep -c '\.close()' "$file")
    if [ "$opens" -gt "$closes" ]; then
      echo "POTENTIAL_LEAK: $file ($opens new WebSocket, $closes .close())"
    fi
  done
  ```

- [ ] **A1.5** useEffect without return cleanup, where the effect body has any of `setInterval|setTimeout|addEventListener|fetch|subscribe|new WebSocket|new EventSource`:
  ```
  # This requires manual inspection per file — grep gives candidates
  grep -rEnA 10 'useEffect\(\(\) => \{' frontend/src/ --include='*.js' --include='*.jsx' \
    | grep -E 'setInterval|setTimeout|addEventListener|fetch\(|subscribe|new WebSocket|new EventSource' \
    | head -30
  ```
  For each candidate, open the file and check whether the useEffect block ends with `return () => {...cleanup...}`. List files MISSING the return.

### Task A2: Open the actual files and confirm each potential leak (20 min)

False positives are common — grep counts can match unrelated `setInterval` (e.g., in a comment or in a different function in the same file). For each PII file from A1.1-A1.5, **open it with `Read`** and confirm by eye.

For each REAL leak, note:
- File path + line number of the leaking call
- Component name (or hook name)
- Severity:
  - **High**: leak fires on every component remount, dataset/subscription continues growing in size (e.g., `setInterval` polling every 1-5s, WebSocket that's never closed). Mount/unmount in a navigation-heavy view leaks rapidly.
  - **Med**: leak fires occasionally, smaller scope (e.g., `addEventListener` on a one-shot component)
  - **Low**: edge-case only (e.g., a `setTimeout` that's < 1s — leak window is tiny)

### Task A3: Write `docs/ROUND9_FRONTEND_LEAK_AUDIT.md` (10 min)

Use this exact structure:

```markdown
# Round 9 Frontend Memory-Leak Audit

**Auditor:** Agent H28
**Date:** <YYYY-MM-DD>
**Scope:** `frontend/src/hooks/`, `frontend/src/components/`

## Summary

| Pattern | Files scanned | Potential leaks | Confirmed real leaks |
|---------|---------------|------------------|----------------------|
| setInterval w/o clearInterval | <N> | <N> | <N> |
| setTimeout w/o clearTimeout | <N> | <N> | <N> |
| addEventListener w/o removeEventListener | <N> | <N> | <N> |
| WebSocket w/o close | <N> | <N> | <N> |
| useEffect w/o cleanup return | <N> | <N> | <N> |

(Numbers from your PF4 + A1 + A2.)

## Findings

| # | File:Line | Pattern | Severity | Fix recommendation |
|---|-----------|---------|----------|--------------------|
| 1 | `frontend/src/hooks/X.js:42` | setInterval w/o cleanup | High | Add `return () => clearInterval(id);` to useEffect cleanup |
| 2 | ... | ... | ... | ... |
| ... | | | | |

## Top 3 to Fix Now (severity High)

1. `<file>:<line>` — <one-sentence why this is highest impact>
2. ...
3. ...

## Recommended for Round 10 (Med/Low)

- Findings #4–#N — list each one-liner
```

### Task A4: Commit the audit report (5 min)

```bash
git add docs/ROUND9_FRONTEND_LEAK_AUDIT.md
git commit -m "$(cat <<'EOF'
docs(round-9-h28): frontend memory-leak audit — L2+L3 findings

Mirror of the L1 backend leak audit for frontend code. Enumerates
setInterval/setTimeout/addEventListener/WebSocket/useEffect-cleanup
leaks across frontend/src/hooks and frontend/src/components.

Summary in the report; top-3 high-severity items will be fixed in
follow-up commits in this session (Tasks B1-B3).
EOF
)"
git push origin main
git fetch origin && git log origin/main --oneline -1 | grep 'h28.*audit'
```

Pulse: `audit phase done, N high-severity findings`.

---

## Phase 2: Fix the top 3 (45 min)

For EACH of your top-3 findings, do a 4-step TDD cycle. Below is the GENERIC template — apply it 3 times.

### Template (repeat 3 times — one fix per top finding)

- [ ] **B-X.1** Open the file. Read the entire `useEffect` / hook / component block, not just the line.

- [ ] **B-X.2** Determine the cleanup type:
  - **setInterval** → `return () => clearInterval(id);`
  - **setTimeout** → `return () => clearTimeout(id);`
  - **addEventListener** → `return () => element.removeEventListener(event, handler);`
  - **fetch without abort** → wrap in `new AbortController()` + `return () => ctrl.abort();`
  - **WebSocket** → `return () => ws.close();`
  - **EventSource** → `return () => es.close();`
  - **External subscription** → call the unsubscribe fn the library returns

- [ ] **B-X.3** Apply the fix with `Edit`. **Preserve the exact existing indentation** — React components are usually 2-space indented; hooks may be 4-space inside arrow functions.

- [ ] **B-X.4** Write a Jest test if a test file already exists for the component. The simplest test:
  ```javascript
  import { render, unmount } from '@testing-library/react';
  // ... import the component
  
  test('component unmount clears its interval', () => {
    jest.useFakeTimers();
    const { unmount } = render(<TheComponent />);
    const intervalsBefore = jest.getTimerCount();
    unmount();
    const intervalsAfter = jest.getTimerCount();
    expect(intervalsAfter).toBeLessThan(intervalsBefore);
  });
  ```
  Adjust the import path + component name to match. If the component has no existing test file, **skip writing a new one** for time — note in your commit message "no existing test file, fix verified by grep + manual mount/unmount cycle".

- [ ] **B-X.5** Verify the fix with grep — the BEFORE pattern must be gone, the AFTER pattern present:
  ```
  grep -n 'setInterval\|clearInterval' frontend/src/<the-file>
  ```
  Both counts should now match.

- [ ] **B-X.6** Commit, push, gate:
  ```bash
  git add frontend/src/<the-file>
  # (and the test file if you wrote one)
  git commit -m "fix(L2-frontend-leak-#<N>): <one-line what + why>"
  git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'L2-frontend-leak'
  ```

- [ ] **B-X.7** Pulse.

### After all 3 fixes land

- [ ] **C.1** Smoke-build the frontend to confirm no syntax errors introduced:
  ```
  cd frontend && npx eslint src/hooks/ src/components/ --max-warnings=0 2>&1 | tail -20
  ```
  If eslint warns on YOUR changes, fix immediately. If it warns on others' code, document in close-out but don't touch.

- [ ] **C.2** Update your audit report — mark the 3 fixed findings as DONE with SHAs:
  ```
  # In docs/ROUND9_FRONTEND_LEAK_AUDIT.md, prefix each fixed row with ✅ and append "DONE <sha>" to the Fix column.
  ```

- [ ] **C.3** Final commit + push:
  ```
  git add docs/ROUND9_FRONTEND_LEAK_AUDIT.md
  git commit -m "docs(round-9-h28): mark top-3 frontend leaks DONE"
  git push origin main
  ```

- [ ] **C.4** Final pulse: `DONE :: 4 commits :: <N> total findings :: 3 high-severity fixed`.

---

## Halt conditions

1. Pre-flight in wrong dir or H6 commit missing.
2. Audit reveals 0 High-severity findings (means everything's already clean — STOP and report; skip Phase 2).
3. A fix breaks `npm start` or eslint introduces new errors.
4. You realize a fix requires App.js or another forbidden file — STOP and ask architect.
5. Origin gate fails.
6. 15-min pulse gap.

---

## What success looks like

- 1 commit for the audit report (Task A4)
- 3 commits for top-3 fixes (one each)
- 1 commit marking the report findings as DONE
- 5 total commits on origin/main
- `docs/ROUND9_FRONTEND_LEAK_AUDIT.md` exists with full table + summary + Round-10 backlog
- Frontend npm/eslint still clean
- React app at port 3000 still mounts cleanly (eyeball test: `decoder` alias should still open the PWA without errors)
