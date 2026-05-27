# Agent A3 — Frontend Memory-Leak Audit + 5 High-Severity Fixes (target: 3 hours)

**You are Agent A3.** Read `_PREAMBLE.md`. Scope: comprehensive audit of frontend memory leaks (setInterval/setTimeout/useEffect/AbortController/addEventListener/WebSocket) across `frontend/src/hooks/` and `frontend/src/components/`, then fix the 5 highest-severity findings.

Excluded files (owned by A4/A5/A6/A7): `components/heatseeker/*`, `CharmChart.jsx`, `VannaChart.jsx`, `OptionsChainTable.jsx`, `ToxicityGauge.jsx`, `hooks/useGreeks.js`, `hooks/useWebSocketGex.jsx`. ALSO forbidden: `App.js`.

---

## Mission

| # | Task | Min |
|---|------|-----|
| 1 | Pre-flight + scope estimation | 10 |
| 2 | Enumerate every leaky pattern (grep) | 20 |
| 3 | Manual confirm per candidate file | 30 |
| 4 | Write `ROUND9_FRONTEND_LEAK_AUDIT.md` | 20 |
| 5 | Fix #1 (highest-severity) — TDD cycle | 20 |
| 6 | Fix #2 — TDD cycle | 20 |
| 7 | Fix #3 — TDD cycle | 20 |
| 8 | Fix #4 — TDD cycle | 20 |
| 9 | Fix #5 — TDD cycle | 20 |
| 10 | eslint + manual mount/unmount + close-out | 10 |

Total ~190 min.

---

## Reference patterns (memorize before starting)

### Leak A — interval without cleanup
```js
// BAD
useEffect(() => {
  const id = setInterval(() => poll(), 5000);
}, []);

// GOOD
useEffect(() => {
  const id = setInterval(() => poll(), 5000);
  return () => clearInterval(id);
}, []);
```

### Leak B — fetch without abort
```js
// BAD
useEffect(() => { fetch(url).then(setData); }, [url]);

// GOOD
useEffect(() => {
  const ctrl = new AbortController();
  fetch(url, { signal: ctrl.signal })
    .then(setData)
    .catch((e) => { if (e.name !== 'AbortError') throw e; });
  return () => ctrl.abort();
}, [url]);
```

### Leak C — addEventListener without remove
```js
// BAD
useEffect(() => {
  window.addEventListener('resize', handler);
}, []);

// GOOD
useEffect(() => {
  window.addEventListener('resize', handler);
  return () => window.removeEventListener('resize', handler);
}, []);
```

### Leak D — WebSocket without close / EventSource
```js
// BAD
useEffect(() => {
  const ws = new WebSocket(url);
  ws.onmessage = handler;
}, [url]);

// GOOD
useEffect(() => {
  const ws = new WebSocket(url);
  ws.onmessage = handler;
  return () => ws.close();
}, [url]);
```

---

## Task 1 — Pre-flight (10 min)

- [ ] **1.1** `pwd` → `…/Documents/GitHub/floww`.
- [ ] **1.2** Confirm Round-9 H6 already on origin (it fixed `fetch({timeout})` — confirms your scope assumption):
  ```bash
  git log origin/main --oneline | grep -E 'H6\b' | head -2
  ```
- [ ] **1.3** Scope estimation:
  ```bash
  echo "=== setInterval/setTimeout ===" && grep -rEn 'setInterval\(|setTimeout\(' frontend/src/ --include='*.js' --include='*.jsx' | wc -l
  echo "=== useEffect ===" && grep -rn 'useEffect(' frontend/src/ --include='*.js' --include='*.jsx' | wc -l
  echo "=== addEventListener ===" && grep -rn 'addEventListener(' frontend/src/ --include='*.js' --include='*.jsx' | wc -l
  echo "=== AbortController ===" && grep -rn 'new AbortController' frontend/src/ --include='*.js' --include='*.jsx' | wc -l
  echo "=== WebSocket ===" && grep -rn 'new WebSocket' frontend/src/ --include='*.js' --include='*.jsx' | wc -l
  echo "=== EventSource ===" && grep -rn 'new EventSource' frontend/src/ --include='*.js' --include='*.jsx' | wc -l
  ```
  Save the 6 numbers.
- [ ] **1.4** Pulse.

---

## Task 2 — Enumerate leaky patterns (20 min)

Goal: produce a per-file list of POTENTIAL leaks. False positives are OK at this stage — you'll confirm in Task 3.

**Important:** skip files owned by other agents (heatseeker/, CharmChart, VannaChart, OptionsChainTable, ToxicityGauge, useGreeks, useWebSocketGex, App.js). Pipe through:
```
grep -v -e 'heatseeker/' -e 'CharmChart' -e 'VannaChart' -e 'OptionsChainTable' -e 'ToxicityGauge' -e 'useGreeks' -e 'useWebSocketGex' -e '/App.js'
```

- [ ] **2.1** Intervals without paired clear:
  ```bash
  for file in $(grep -rEln 'setInterval\(' frontend/src/ --include='*.js' --include='*.jsx' \
                | grep -v -e 'heatseeker/' -e 'CharmChart' -e 'VannaChart' -e 'OptionsChainTable' -e 'ToxicityGauge' -e 'useGreeks' -e 'useWebSocketGex' -e '/App.js'); do
    s=$(grep -c 'setInterval(' "$file")
    c=$(grep -c 'clearInterval(' "$file")
    [ "$s" -gt "$c" ] && echo "MAYBE: $file ($s setInterval / $c clearInterval)"
  done | tee /tmp/a3_interval_leaks.txt
  ```
- [ ] **2.2** Same pattern for setTimeout/clearTimeout (lower severity but document):
  ```bash
  for file in $(grep -rEln 'setTimeout\(' frontend/src/ --include='*.js' --include='*.jsx' \
                | grep -v -e 'heatseeker/' -e 'CharmChart' -e 'VannaChart' -e 'OptionsChainTable' -e 'ToxicityGauge' -e 'useGreeks' -e 'useWebSocketGex' -e '/App.js'); do
    s=$(grep -c 'setTimeout(' "$file")
    c=$(grep -c 'clearTimeout(' "$file")
    [ "$s" -gt "$c" ] && echo "MAYBE: $file ($s setTimeout / $c clearTimeout)"
  done | tee /tmp/a3_timeout_leaks.txt
  ```
- [ ] **2.3** addEventListener without remove:
  ```bash
  for file in $(grep -rEln 'addEventListener\(' frontend/src/ --include='*.js' --include='*.jsx' \
                | grep -v -e 'heatseeker/' -e 'CharmChart' -e 'VannaChart' -e 'OptionsChainTable' -e 'ToxicityGauge' -e 'useGreeks' -e 'useWebSocketGex' -e '/App.js'); do
    a=$(grep -c 'addEventListener(' "$file")
    r=$(grep -c 'removeEventListener(' "$file")
    [ "$a" -gt "$r" ] && echo "MAYBE: $file ($a add / $r remove)"
  done | tee /tmp/a3_evt_leaks.txt
  ```
- [ ] **2.4** WebSocket without close:
  ```bash
  for file in $(grep -rEln 'new WebSocket\(' frontend/src/ --include='*.js' --include='*.jsx' \
                | grep -v -e 'heatseeker/' -e 'CharmChart' -e 'VannaChart' -e 'OptionsChainTable' -e 'ToxicityGauge' -e 'useGreeks' -e 'useWebSocketGex' -e '/App.js'); do
    o=$(grep -c 'new WebSocket(' "$file")
    c=$(grep -c '\.close()' "$file")
    [ "$o" -gt "$c" ] && echo "MAYBE: $file ($o new / $c close)"
  done | tee /tmp/a3_ws_leaks.txt
  ```
- [ ] **2.5** fetch without abort (very common): grep for `useEffect` containing `fetch(` but no `AbortController`:
  ```bash
  grep -rEnA 15 'useEffect\(' frontend/src/ --include='*.js' --include='*.jsx' \
    | grep -v -e 'heatseeker/' -e 'CharmChart' -e 'VannaChart' -e 'OptionsChainTable' -e 'ToxicityGauge' -e 'useGreeks' -e 'useWebSocketGex' -e '/App.js' \
    | grep -B2 'fetch(' \
    | tee /tmp/a3_fetch_candidates.txt
  ```
  Each candidate must be opened individually — easy to misjudge from grep alone.
- [ ] **2.6** Pulse — paste sizes of the 5 scratch files.

---

## Task 3 — Manual confirm per candidate (30 min)

For each MAYBE file in /tmp/a3_*.txt, open with `Read`. Confirm each potential site is REAL by:
1. Locating the `setInterval`/`addEventListener`/etc.
2. Walking up to its enclosing `useEffect` block.
3. Checking whether the block returns a cleanup function that pairs with the resource.

Classify each REAL leak as:
- **High**: mounts often (e.g., panel inside a tab), leak fires every mount, resource is unbounded (interval polling, WebSocket)
- **Med**: mounts occasionally, leak window noticeable but bounded
- **Low**: edge-case only (e.g., 100ms setTimeout)

- [ ] **3.1** Open EACH file in /tmp/a3_interval_leaks.txt. Note the line+severity.
- [ ] **3.2** Same for /tmp/a3_evt_leaks.txt, ws_leaks.txt, fetch_candidates.txt.
- [ ] **3.3** setTimeout list — most are Low; only flag if the timeout is >5s.
- [ ] **3.4** Pulse — `T3 done :: <N> high :: <M> med :: <K> low`.

---

## Task 4 — Write `docs/ROUND9_FRONTEND_LEAK_AUDIT.md` (20 min)

- [ ] **4.1** Write the doc with this structure:
  ```markdown
  # Round 9 Frontend Memory-Leak Audit
  
  **Auditor:** Agent A3
  **Date:** <YYYY-MM-DD>
  **Scope:** frontend/src/hooks/ + frontend/src/components/
    (excluding /heatseeker/, CharmChart, VannaChart, OptionsChainTable, ToxicityGauge — owned by A4-A7)
  
  ## Summary
  
  | Pattern | Total grep hits | Confirmed real leaks (High/Med/Low) |
  |---------|----------------|--------------------------------------|
  | setInterval w/o clearInterval | <N> | <H/M/L> |
  | setTimeout w/o clearTimeout | <N> | <H/M/L> |
  | addEventListener w/o removeEventListener | <N> | <H/M/L> |
  | WebSocket w/o close | <N> | <H/M/L> |
  | fetch w/o AbortController | <N> | <H/M/L> |
  
  ## Findings
  
  | # | File:Line | Pattern | Severity | Recommended fix |
  |---|-----------|---------|----------|-----------------|
  | 1 | <file>:<ln> | setInterval w/o cleanup | High | Add `return () => clearInterval(id);` in useEffect |
  | ... | | | | |
  
  ## Top 5 (this session — agent A3 fixes)
  1. <file>:<ln> — <reason>
  2. ...
  
  ## Round 10 candidates (Med/Low)
  - <list rest>
  ```
- [ ] **4.2** Commit:
  ```bash
  git add docs/ROUND9_FRONTEND_LEAK_AUDIT.md
  git commit -m "docs(round-9-a3): frontend leak audit — <N> total findings, <H> high"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'frontend leak audit'
  ```
- [ ] **4.3** Pulse.

---

## Tasks 5-9 — Fix top-5 (TDD cycle each, ~20 min per)

**For EACH of your 5 highest-severity findings**, repeat this cycle:

### Cycle template

- [ ] **X.1** Open the file (full Read).
- [ ] **X.2** Determine cleanup type from the pattern table at the top of this doc.
- [ ] **X.3** Apply the fix with `Edit`. **Preserve exact indentation.**
- [ ] **X.4** Write or extend a Jest test if a test file already exists for the component. Template:
  ```javascript
  import { render } from '@testing-library/react';
  import TheComponent from '../TheComponent';
  
  test('component unmount clears intervals', () => {
    jest.useFakeTimers();
    const before = jest.getTimerCount();
    const { unmount } = render(<TheComponent />);
    const during = jest.getTimerCount();
    unmount();
    const after = jest.getTimerCount();
    expect(after).toBeLessThan(during);
    jest.useRealTimers();
  });
  ```
  If no test file exists, **skip writing a new one** — note "verified by grep + manual mount/unmount cycle" in commit.
- [ ] **X.5** Verify with grep that counts now match:
  ```bash
  grep -cE '<add-pattern>|<remove-pattern>' frontend/src/<the-file>
  ```
- [ ] **X.6** Run eslint on the touched file:
  ```bash
  cd frontend && npx eslint src/<path> --max-warnings=0 2>&1 | tail -10
  ```
  Must be clean.
- [ ] **X.7** Commit:
  ```bash
  git add frontend/src/<file>
  git commit -m "fix(L2-frontend-leak-#<N>): <component> — clear <resource> on unmount"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'L2-frontend-leak'
  ```
- [ ] **X.8** Pulse.

After all 5 fixes:

- [ ] **C.1** Update audit doc — mark all 5 fixed findings with ✅ + SHA.
- [ ] **C.2** Run full frontend eslint:
  ```bash
  cd frontend && npx eslint src/hooks/ src/components/ --max-warnings=0 2>&1 | tail -10
  ```
- [ ] **C.3** Commit audit update.

---

## Task 10 — Close-out + final pulse (10 min)

- [ ] **10.1** Write `docs/ROUND9_A3_CLOSEOUT.md` with commit table, leak counts, eslint status.
- [ ] **10.2** Commit + push + gate.
- [ ] **10.3** Final pulse: `A3 :: DONE :: 7 commits :: 5 high-severity leaks fixed`.

---

## Halt conditions

1. H6 commit missing from origin.
2. Audit reveals 0 high-severity findings → STOP, skip Phase 2, just commit the audit.
3. A fix introduces eslint errors that aren't yours.
4. You realize a fix requires App.js or another agent's file → STOP.
5. 15-min pulse gap.
