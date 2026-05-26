# DeepSeek Pro (freebuff session #2) — UI Symptom Investigation + Bounded Fixes

> **WHERE TO PASTE**: freebuff terminal → new DeepSeek Pro session → paste everything below the first `═══` line. ONE 60-minute session. This is freebuff session #2 of your remaining 2.5.
>
> **WHY DeepSeek Pro for this and not Owl Alpha**: this mission requires reading App.js (800+ lines), tracing toggle wiring through multiple useEffects, probing backend response shapes, and re-checking `/api/heatseeker/flip-zones` behavior. The architect-forbidden files for Owl Alpha include `App.js` — but a focused Pro session with deep-context can SAFELY surgical-edit it for this single bounded mission. Pro's heavier context window can hold App.js + backend route code + audit data simultaneously while reasoning about toggle composition.

═══════════════════════════════════════════════════════════════════════════════

You are DeepSeek Pro running in a freebuff hour-long session. Architect: Nav (PhD math/physics, Stanford, ex-Jane Street HFT). Repo: `/Users/nav/Documents/GitHub/floww`. Master plan: `docs/superpowers/plans/2026-05-25-round9-three-resource-triage.md`.

Your mission: **investigate and fix the 5 visible UI bugs the user has been reporting**:
1. **CHARM** toggle doesn't render data in BarHeatmap view
2. **Chain** button doesn't render OptionsChainTable
3. **DTE filter** (0DTE/1DTE/Week/All) doesn't filter results
4. **Expiries** selector (2/4/6/8/12) doesn't change number of expiries shown
5. **Skylit tab** loads forever (some `/api/heatseeker/*` panel returns 500 → blocks all sibling panels)

Each is a real user-facing problem. Each may have multiple root-cause layers (React state, useEffect deps, URL construction, backend cache key, backend route bug). Your job: investigate each, fix what's bounded (≤30-min change), document what isn't with file:line evidence for Round 10.

═══════════════════════════════════════════════════════════════════════════════
HARD RULES (violating any = P0 — STOP and HALT instead)
═══════════════════════════════════════════════════════════════════════════════

R1. **Canonical clone only.** `pwd` MUST equal `/Users/nav/Documents/GitHub/floww`. NOT `/Users/nav/GitHub/floww`. Verify with `pwd && git remote -v`. If wrong: HALT WRONG_CLONE.

R2. **Forbidden git commands.** NEVER: `--abort`, `--reset --hard`, `--force`, `--no-verify`, `--amend` (others' commits), `git checkout .`, `git restore .`, `git clean -fd`, `rm -rf .git`. The repo has recently-resolved rebase state.

R3. **File ownership (this mission's writable set):**
   - `frontend/src/App.js` (surgical edits ONLY for toggle composition wiring — DO NOT refactor)
   - `frontend/src/components/BarHeatmap.jsx` (charm/vex field handling)
   - `frontend/src/components/OptionsChainTable.jsx` (if Chain button issue is here)
   - `backend/server.py` `build_heatmap()` function ONLY (around line 1444) — cache key fix
   - `backend/routes/heatseeker.py` (flip-zones handler IF it's the 500 source)
   - `docs/ROUND10_UI_BACKLOG.md` (NEW — for what you don't fix)
   - `kanban/cards/agent_PRO2_status.md` (NEW — 15-min status pulse)

   ALWAYS FORBIDDEN: `backend/services/ml/inference.py`, `backend/services/dash_ui.py`, `backend/tests/conftest.py`, `backend/server.py` anywhere outside `build_heatmap()`, any model artifact, `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`.

R4. **Grep/curl evidence in every commit message.** Every commit MUST include the literal output of a probe (curl, grep, or pytest) that proves the claim. No fabricated success.

R5. **NEVER xfail/skip a test** without architect approval. HALT instead.

R6. **15-minute status pulse — HARD RULE.** Append to BOTH:
   ```
   kanban/cards/agent_PRO2_status.md
   /Users/nav/Documents/GitHub/Hermes/Daily Log.md
   ```
   Format: `[<ISO8601-UTC>] PRO2 :: <status> :: <one-line summary> :: HEAD=<sha7>`
   Statuses: `launched`, `investigating-N`, `fixing-N`, `verifying`, `DONE-INVESTIGATION-N`, `DONE-ALL`, `STALLED`, `HALTED`.

R7. **Halt format:**
   ```
   ──── HALT REPORT ────
   Agent:    DeepSeek Pro (freebuff session 2) — UI Investigation
   Phase:    Investigation <N>  Step: <n>
   Reason:   <one sentence>
   Output:   <verbatim diagnostic>
   Question: <one specific yes/no or A/B>
   ─────────────────────
   ```

R8. **Per-investigation commit + push + verify-on-origin.** After each of 5 investigations completes (either fix shipped OR documented as Round 10):
   ```bash
   git add <relevant files>
   git commit -m "<inline grep/curl/test evidence>"
   git pull --rebase origin main && git push origin main
   git fetch origin && git log origin/main --oneline -1 | grep "<your subject>"
   ```

R9. **30-minute fix budget per investigation.** If you can't fix an issue in ≤30 minutes of work, document the root cause in `docs/ROUND10_UI_BACKLOG.md` with file:line precision and move to the next investigation. Better to document 5 clear root causes than fix 1 and leave 4 mysterious.

R10. **The Confluence Decoder PWA.** For visual verification: `open -a "$HOME/Applications/Chrome Apps.localized/Confluence Decoder.app"` (NEVER `open <URL>` — that spawns a Chrome tab instead of the PWA).

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY + SETUP (5 min)
═══════════════════════════════════════════════════════════════════════════════

```bash
cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ .git/rebase-apply/ 2>&1   # MUST be "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_PRO2_start.txt
git branch backup/r9_PRO2_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards docs
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] PRO2 :: launched :: Phase 0 complete :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_PRO2_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

# Initialize the Round 10 backlog file
cat > docs/ROUND10_UI_BACKLOG.md <<'EOF'
# Round 10 UI Backlog — items DeepSeek Pro Round 9 didn't fix

Each entry below is a root cause traced by DeepSeek Pro during Round 9 UI
investigation, with file:line evidence, that exceeded the 30-min per-issue
fix budget OR requires architectural decision the architect needs to make.

Generated: 
Source session: freebuff Pro #2

EOF
date -u +%Y-%m-%dT%H:%M:%SZ | xargs -I{} sed -i '' "s/^Generated: $/Generated: {}/" docs/ROUND10_UI_BACKLOG.md
```

Confirm backend + React are running:
```bash
lsof -i :8000 -P -n 2>/dev/null | grep LISTEN | head -1   # backend
lsof -i :3000 -P -n 2>/dev/null | grep LISTEN | head -1   # frontend
```
If either is down, start them via the launcher: `bash scripts/launch_decoder.sh`.

═══════════════════════════════════════════════════════════════════════════════
INVESTIGATION 1 — CHARM toggle (Bars view)  (~15 min budget)
═══════════════════════════════════════════════════════════════════════════════

**Context:** the architect already fixed CHARM rendering in GridHeatmap.jsx (commit `533cf5e`). Verify the fix is on origin AND check whether BarHeatmap.jsx has the same destructure bug (it uses a different code path — `s[key]` lookup expecting per-strike `s.charm` field).

**Steps:**

1. Verify GridHeatmap fix is on origin:
   ```bash
   grep -n 'charm_grid' frontend/src/components/GridHeatmap.jsx
   ```
   Expected: `const charm_grid = grid.charm_grid;` (NOT `const { ..., charm_grid, ... } = data;`)

2. Probe backend to see what charm data shape it returns:
   ```bash
   curl --max-time 15 -s "http://localhost:8000/api/heatmap/SPY?expiries=2&mode=day" \
     | python3 -c "import sys, json; d=json.load(sys.stdin); s0=(d.get('strikes') or [{}])[0]; print('Per-strike keys:', sorted(s0.keys())[:25]); print('has charm field?', 'charm' in s0)"
   ```

3. If `'charm' in s0` is **True**: BarHeatmap will work as-is when CHARM is selected (its `s[key]` lookup finds `s.charm`). No fix needed. Document this finding.

4. If `'charm' in s0` is **False**: backend response doesn't include per-strike charm field. Two options:
   - **(a)** BarHeatmap falls back to a friendly placeholder when key is missing. Edit `frontend/src/components/BarHeatmap.jsx` line ~7-12 (where `key` is set and `s[key] || s.gex` defaults to gex):
     ```jsx
     const filtered = strikes.filter((s) => {
       const val = s[key];
       if (val === undefined && key !== 'gex') return false;  // hide strikes when charm/vex data absent
       // ... rest unchanged
     });
     ```
     Add a banner above the bars: `{key !== 'gex' && filtered.length === 0 && <div className="text-slate-500 text-xs p-4">No {key.toUpperCase()} data available from backend</div>}`
   - **(b)** Leave BarHeatmap silently falling back to GEX (current behavior) and add a banner explaining: `{key === 'charm' && <div className="text-amber-400 text-xs p-2">Bars + CHARM not yet supported by backend; showing GEX</div>}`

   Pick (a) — better UX. The user notices "nothing happens" silently with current behavior.

5. Commit + push per R8.

**If you cannot fix in 15 minutes**: document the root cause in `docs/ROUND10_UI_BACKLOG.md` with file:line and move on.

═══════════════════════════════════════════════════════════════════════════════
INVESTIGATION 2 — Chain button doesn't work  (~15 min budget)
═══════════════════════════════════════════════════════════════════════════════

**Context:** App.js line 678-680 renders `<OptionsChainTable ticker={ticker} spot={...} />` when `view === "chain"`. The component exists. User says "doesn't work" — need to determine the actual symptom.

**Steps:**

1. Read `frontend/src/components/OptionsChainTable.jsx` first 50 lines. Identify the fetch URL.

2. Probe that URL directly:
   ```bash
   # Look at what URL the component constructs:
   grep -n 'axios.get\|fetch(' frontend/src/components/OptionsChainTable.jsx | head -5
   # Then curl whatever it hits, e.g.:
   curl --max-time 15 -s -o /tmp/chain_probe.json -w "STATUS=%{http_code} CT=%{content_type}\n" "http://localhost:8000/api/chain/SPY"
   head -c 200 /tmp/chain_probe.json
   ```

3. Three likely outcomes:
   - **(a)** API returns 200 with JSON → component bug. Read render logic; look for empty-state guards. Likely: `if (!chain) return ...` missing OR sort/filter returns empty array.
   - **(b)** API 404 → backend route mismatch. Likely the component calls `/api/chain/...` but backend serves `/api/analytics/chain/...` (same prefix-bug class we've seen). Update the URL.
   - **(c)** API 500 → backend bug. Out of scope for this session — document in Round 10 backlog.

4. Apply the bounded fix. Commit + push.

═══════════════════════════════════════════════════════════════════════════════
INVESTIGATION 3 — DTE filter doesn't filter  (~10 min budget)
═══════════════════════════════════════════════════════════════════════════════

**Context:** Architect already verified DTE param flows correctly:
- DTE=0 → empty (no same-day expiries)
- DTE=1 → 110 strikes (works)
- DTE=7 → 158 strikes (works)
- DTE=All (null) → 158 strikes (works)

User's complaint "only Week works" is **mostly perception** — 0DTE legitimately has no data on most days. But verify the URL construction is still correct:

```bash
grep -n 'dte=\|debouncedDte\|setDte' frontend/src/App.js | head -10
```

Expected pattern:
```js
const dteParam = debouncedDte != null ? `&dte=${debouncedDte}` : "";
... axios.get(`${API}/heatmap/${ticker}?expiries=...&mode=...${dteParam}`)
```

If that pattern is intact: this is NOT a bug. Document in Round 10 backlog as "0DTE returns empty correctly when no 0DTE expiries exist; consider adding UI message 'No 0DTE expiries today' when the filter returns empty results." Then move on.

If the pattern is broken (the dteParam isn't being appended, or 1DTE/Week/All look identical in network tab): apply the fix. Commit + push.

═══════════════════════════════════════════════════════════════════════════════
INVESTIGATION 4 — Expiries selector doesn't change data  (~30 min budget)
═══════════════════════════════════════════════════════════════════════════════

**Context:** Architect suspects backend caching strips the `expiries` param from the cache key. From `backend/server.py:1444`:
```python
async def build_heatmap(ticker, max_expiries=4, with_taps=True, mode="day", dte=None, scalp=False):
    if mode == "swing":
        max_expiries = max(max_expiries, 8)
    raw = await fetch_spot_and_chains_merged(ticker, max_expiries)
    # ... downstream computation
```

`fetch_spot_and_chains_merged()` has its own cache. If that cache keys ONLY on ticker (not on max_expiries), then expiries=2 and expiries=12 return the SAME cached chain.

**Steps:**

1. Read `fetch_spot_and_chains_merged()`:
   ```bash
   grep -n 'def fetch_spot_and_chains_merged\|_chain_cache\|@.*cache' backend/server.py | head -10
   ```

2. Inspect the cache key construction. If it's `(ticker,)` instead of `(ticker, max_expiries)`: that's the bug.

3. Probe to confirm symptom:
   ```bash
   curl --max-time 20 -s "http://localhost:8000/api/heatmap/SPY?expiries=2" \
     | python3 -c "import sys, json; d=json.load(sys.stdin); print('expiries=2 returns:', len((d.get('grid') or {}).get('expiries', [])), 'expiries')"
   curl --max-time 20 -s "http://localhost:8000/api/heatmap/SPY?expiries=12" \
     | python3 -c "import sys, json; d=json.load(sys.stdin); print('expiries=12 returns:', len((d.get('grid') or {}).get('expiries', [])), 'expiries')"
   ```

   If both return the same count: caching bug confirmed. If they differ: not a caching bug; investigate downstream.

4. **Fix** (only if confirmed): inside `build_heatmap()` at server.py:~1444, add a per-(ticker, max_expiries) wrapper cache OR fix the underlying `fetch_spot_and_chains_merged` cache key. The bounded fix is to memoize `build_heatmap` results directly with a tuple key:
   ```python
   from functools import lru_cache
   
   _build_heatmap_cache_keys = {}  # {(ticker, max_expiries, mode, dte, scalp): (timestamp, payload)}
   _CACHE_TTL_SEC = 60
   
   async def build_heatmap(ticker, max_expiries=4, ..., mode="day", dte=None, scalp=False):
       import time
       key = (ticker.upper(), max_expiries, mode, dte, scalp)
       now = time.time()
       cached = _build_heatmap_cache_keys.get(key)
       if cached and (now - cached[0]) < _CACHE_TTL_SEC:
           return cached[1]
       # ... existing computation
       result = ...  # whatever it currently returns
       _build_heatmap_cache_keys[key] = (now, result)
       return result
   ```
   This bypasses any downstream cache-key bug.

5. After fix, restart backend + re-probe + verify expiries=2 vs expiries=12 return different counts. Commit + push.

**If exceeding 30 min**: document in Round 10 backlog and move on.

═══════════════════════════════════════════════════════════════════════════════
INVESTIGATION 5 — Skylit loads forever (/api/heatseeker/flip-zones 500)  (~25 min budget)
═══════════════════════════════════════════════════════════════════════════════

**Context:** Architect's previous audit showed `/api/heatseeker/flip-zones?ticker=SPY` returns 500. The Skylit tab uses `HeatseekerDashboard` which renders ~13 sub-panels; if any of them hangs (waiting for a never-arriving 500 to time out), the whole tab spins forever.

**Steps:**

1. Re-probe each Skylit panel endpoint (backend restart from architect's b9d182f should be live):
   ```bash
   for ep in flip-zones node-lifecycle reverse-rug rainbow-road beach-ball velocity-mode rolling-floors-ceilings node-classification tug-of-war air-pockets; do
     code=$(curl --max-time 8 -s -o /dev/null -w "%{http_code}" "http://localhost:8000/api/heatseeker/$ep?ticker=SPY")
     echo "$ep → $code"
   done
   ```

2. For each endpoint returning 500: capture the traceback from uvicorn log:
   ```bash
   tail -100 /tmp/uvicorn*.log 2>/dev/null | grep -B 2 -A 20 'flip-zones\|node-lifecycle' | head -40
   ```

3. If the 500 source is identifiable (e.g., NaN in a math function, missing field in a dict, divide-by-zero):
   - Apply the surgical fix in `backend/routes/heatseeker.py` to the affected handler.
   - Wrap in try/except that returns a structured 200 response with `{"status": "degraded", "reason": "..."}` instead of 500 so the frontend doesn't hang.
4. If the 500 source needs investigation > 25 min: document in Round 10 backlog with the full traceback.

5. Restart backend after the fix. Re-probe. Verify no more 500s. Commit + push.

═══════════════════════════════════════════════════════════════════════════════
PHASE 6 — CLOSURE (5 min)
═══════════════════════════════════════════════════════════════════════════════

After all 5 investigations:

```bash
# Append findings summary to ROUND10_UI_BACKLOG.md if not already done
# Then commit:
git add docs/ROUND10_UI_BACKLOG.md
git commit -m "docs(round-9-PRO2): Round 10 UI backlog with investigation findings

Co-Authored-By: DeepSeek Pro (freebuff session 2) <pro@floww.dev>"
git pull --rebase origin main && git push origin main

# Final status pulse
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] PRO2 :: DONE-ALL :: 5 investigations complete :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_PRO2_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

# Final report:
echo ""
echo "──── DEEPSEEK PRO ROUND 9 INVESTIGATION COMPLETE ────"
echo "Start HEAD:       $(cat /tmp/r9_PRO2_start.txt)"
echo "Final HEAD:       $(git rev-parse HEAD)"
echo "Commits added:    $(git log $(cat /tmp/r9_PRO2_start.txt)..HEAD --oneline | wc -l | tr -d ' ')"
echo "Investigations:   5/5 (each either fixed or documented for Round 10)"
echo "Backlog doc:      docs/ROUND10_UI_BACKLOG.md"
echo "─────────────────────────────────────────────────────"
echo "DONE"
```

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS
═══════════════════════════════════════════════════════════════════════════════

- This is freebuff Pro session **#2 of remaining 2.5**. Do not exceed 60 minutes.
- 30-minute fix budget per investigation. Better 5 documented root causes than 1 fix + 4 mysteries.
- App.js is normally FORBIDDEN — you have a NARROW exception for toggle composition wiring ONLY. Do NOT refactor App.js; only adjust the specific lines related to URL construction or component selection. If you find yourself wanting to refactor App.js: STOP, document the refactor as a Round 10 item.
- `server.py` similarly: ONLY touch `build_heatmap()` if Investigation 4 requires it. Nothing else.
- Every commit message must include grep/curl/test evidence INLINE. No fabricated success claims.

END OF PROMPT. BEGIN AT PHASE 0.
═══════════════════════════════════════════════════════════════════════════════
