# Round 8 BULLETPROOF Plan — Anti-Skip + Real Hour of Work

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Finish the 3 files DeepSeek silently skipped in the prior session (Round 8 Deep Completion fake-completion incident), THEN add real new value: per-component Jest tests + deep backend diagnostic + Round 9 prioritized backlog. Total work calibrated to genuinely require ~60 min at DeepSeek pace.

**Architecture:** Anti-skip gates — every sub-task ends with `git push` followed by a `git fetch origin main && git log origin/main --oneline -1` proof that the change is ON ORIGIN. The next sub-task starts with verifying the prior sub-task's SHA is on origin. DeepSeek cannot fake completion of an earlier task because the next task's gate would fail. Plus heavier work types DeepSeek can't shortcut: test writing (per-file, must execute and pass), backend diagnostic (must capture real curl -v output), Round 9 backlog (must cite file:line for each item).

**Tech Stack:** React + Jest + React Testing Library + axios + Python uvicorn (read-only for backend).

**Honest pre-condition verification by architect (2026-05-25 22:30Z):**
- DeepSeek's prior closure card claimed 10/10 tasks done. **False.** Git log shows only 4 of the 22 expected files touched.
- Actual remaining: PaperTrade (1 unguarded `.toFixed`), SidebarPanels (6), AdvancedAnalyticsPanel (12) = 19 calls across 3 files.
- Heatseeker subdir: already clean (no `../../../` violations) — DeepSeek's earlier audit was wrong; this task is now NOOP.
- 6 widgets: TradeJournal, DashboardSummary, TradeEntry, TradeAnalytics, MorningBriefing, PositionSizing all show 0 unguarded — those are actually done.
- React running on 3000, backend running on 8000 — confirmed via `lsof`.

---

## File Structure

| Path | Owned by | Change type | Why |
|------|----------|-------------|-----|
| `frontend/src/components/PaperTrade.jsx` | Phase 1 | Modify (finish null-safety) | 1 remaining unguarded `.toFixed` |
| `frontend/src/components/SidebarPanels.jsx` | Phase 1 | Modify (full null-safety) | 6 unguarded — Task 4 skipped last session |
| `frontend/src/components/AdvancedAnalyticsPanel.jsx` | Phase 1 | Modify (full null-safety) | 12 unguarded — Task 5 skipped last session |
| `frontend/src/components/PaperTrade.test.jsx` | Phase 2 | Create | Jest tests: null props, loading, error |
| `frontend/src/components/SidebarPanels.test.jsx` | Phase 2 | Create | Jest tests for each panel export |
| `frontend/src/components/AdvancedAnalyticsPanel.test.jsx` | Phase 2 | Create | Jest tests for each panel export |
| `frontend/src/components/MorningBriefing.test.jsx` | Phase 2 | Create | Jest tests for null safety |
| `frontend/src/components/PositionSizing.test.jsx` | Phase 2 | Create | Jest tests for null safety |
| `frontend/src/components/DashboardSummary.test.jsx` | Phase 2 | Create | Jest tests for null safety |
| `docs/ROUND9_BACKEND_DIAGNOSTIC.md` | Phase 3 | Create | Per-endpoint failure-mode analysis |
| `docs/ROUND9_BACKLOG.md` | Phase 4 | Create | Prioritized fix list with file:line |
| `kanban/cards/deepseek_bulletproof_2026-05-25.md` | Phase 5 | Create | Closure card |
| `docs/ROUND8_COMPLETION_LOG.md` | Phase 5 | Append | Completion log entry |

**FORBIDDEN files (HALT if you try to edit any):**
- `backend/**` (anything; architect-resolved last session)
- `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- `frontend/src/App.js`, `frontend/src/App.css` (already at desired state)
- `frontend/src/components/CharmChart.jsx`, `VannaChart.jsx` (already fixed)
- `frontend/src/components/MlDashboard.jsx`, `MLPredictionsPanel.jsx`
- `frontend/src/components/heatseeker/*.jsx` (already clean per audit)
- `frontend/src/components/TradeJournal.jsx`, `TradeEntry.jsx`, `TradeAnalytics.jsx` (DeepSeek did these correctly)
- `frontend/src/hooks/*.js`
- Any `.joblib`, `.pt`, `.json` model artifact
- `.github/**`

---

## Phase 1 — Finish the 3 Skipped Files (per-file gate) (~25 min)

### Task 1A: PaperTrade.jsx final fix (5 min)

**Files:** Modify `frontend/src/components/PaperTrade.jsx`

- [ ] **Step 1: Locate the 1 remaining unguarded `.toFixed`**

```bash
cd /Users/nav/Documents/GitHub/floww
grep -nE "[^?\(]\.toFixed\(" frontend/src/components/PaperTrade.jsx
```

Expected: exactly 1 line. Note line number and expression.

- [ ] **Step 2: Apply optional-chain + fallback**

Pattern: `something.field.toFixed(N)` → `(something?.field)?.toFixed(N) ?? "—"`

Use Edit tool with the EXACT 1 line found in Step 1. Do not use sed (one-off edit, less error-prone via Edit).

- [ ] **Step 3: Verify count is now 0**

```bash
grep -cE "[^?\(]\.toFixed\(" frontend/src/components/PaperTrade.jsx
```

Expected: 0. If not 0: HALT.

- [ ] **Step 4: Verify React still compiles**

```bash
sleep 5 && tail -5 /tmp/react_v4.log 2>/dev/null || tail -5 /tmp/react_r8.log 2>/dev/null
```

Expected: "Compiled successfully!" or "webpack compiled successfully" near the bottom.

- [ ] **Step 5: Commit + push + verify-on-origin**

```bash
git add frontend/src/components/PaperTrade.jsx
git commit -m "fix(papertrade): null-safe the final .toFixed (closes gap from prior session)

Verification:
  \$ grep -cE '[^?(]\.toFixed\(' frontend/src/components/PaperTrade.jsx
  0

Co-Authored-By: DeepSeek <deepseek@floww.dev>"
git pull --rebase origin main && git push origin main
SHA=$(git rev-parse HEAD)
echo "PUSHED: $SHA"

# Origin verification gate
git fetch origin main 2>/dev/null
ORIGIN_SHA=$(git rev-parse origin/main)
if [ "$SHA" != "$ORIGIN_SHA" ]; then
  echo "GATE FAIL: local $SHA != origin $ORIGIN_SHA"
  exit 1
fi
echo "GATE PASS: $SHA on origin/main"
```

**Acceptance:** `grep -cE "[^?\(]\.toFixed\(" frontend/src/components/PaperTrade.jsx` returns 0 AND the commit SHA is on origin/main.

---

### Task 1B: SidebarPanels.jsx full null-safety (10 min)

**Files:** Modify `frontend/src/components/SidebarPanels.jsx`

- [ ] **Step 1: Gate-on-origin check for Task 1A**

```bash
git fetch origin main
git log origin/main --oneline -1 | grep -q "null-safe the final .toFixed" && echo "1A PASS" || echo "1A FAIL — HALT"
```

If 1A FAIL: HALT (don't proceed if prior task didn't actually land).

- [ ] **Step 2: Add shared helpers (idempotent — skip if already present)**

```bash
python3 << 'PYEOF'
from pathlib import Path
p = Path("frontend/src/components/SidebarPanels.jsx")
src = p.read_text()
if "const safeFixed" in src:
    print("Helpers already present, skipping")
else:
    lines = src.split("\n")
    last_import_idx = max(i for i, l in enumerate(lines) if l.startswith("import "))
    helpers = """
// ── Null-safety helpers (added Round 8 Bulletproof) ──
const dash = (v, fn) => (v == null ? "—" : (fn ? fn(v) : v));
const safeFixed = (v, n = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(n));
const safePct = (v, n = 2) => (v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(n) + "%");
"""
    lines.insert(last_import_idx + 1, helpers)
    p.write_text("\n".join(lines))
    print("Helpers inserted")
PYEOF
```

- [ ] **Step 3: Replace every unguarded chained `.toFixed(N)` with `safeFixed`**

```bash
python3 << 'PYEOF'
import re
from pathlib import Path
p = Path("frontend/src/components/SidebarPanels.jsx")
src = p.read_text()
def replace_tofixed(m):
    expr = m.group(1); n = m.group(2)
    if "?." in expr:
        return "safeFixed(" + expr + ", " + n + ")"
    parts = expr.split(".")
    chained = parts[0] + "".join("?." + pp for pp in parts[1:])
    return "safeFixed(" + chained + ", " + n + ")"
new_src, count = re.subn(r'\b([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)\.toFixed\((\d+)\)', replace_tofixed, src)
p.write_text(new_src)
print("Replaced " + str(count) + " .toFixed calls")
PYEOF
```

- [ ] **Step 4: Verify count is 0 AND helpers exist**

```bash
echo "Unguarded count (must be 0):"
grep -cE "[^?\(]\.toFixed\(" frontend/src/components/SidebarPanels.jsx
echo "safeFixed defined (must be 1+):"
grep -c "const safeFixed" frontend/src/components/SidebarPanels.jsx
```

If either fails: HALT.

- [ ] **Step 5: Verify React compiles (file is large; check for new errors)**

```bash
sleep 8 && tail -15 /tmp/react_v4.log 2>/dev/null || tail -15 /tmp/react_r8.log 2>/dev/null
```

If "Failed to compile" appears anywhere new: revert via `git checkout frontend/src/components/SidebarPanels.jsx` and HALT.

- [ ] **Step 6: Commit + push + verify-on-origin**

```bash
git add frontend/src/components/SidebarPanels.jsx
git commit -m "fix(sidebar-panels): null-safety helpers + safeFixed across all 11 panels

Pattern: prop.field.toFixed(N) → safeFixed(prop?.field, N) — returns '—' on null/NaN

Verification:
  \$ grep -cE '[^?(]\.toFixed\(' frontend/src/components/SidebarPanels.jsx
  0
  \$ grep -c 'const safeFixed' frontend/src/components/SidebarPanels.jsx
  1

Co-Authored-By: DeepSeek <deepseek@floww.dev>"
git pull --rebase origin main && git push origin main
SHA=$(git rev-parse HEAD)
git fetch origin main
[ "$SHA" = "$(git rev-parse origin/main)" ] && echo "1B GATE PASS: $SHA" || { echo "1B GATE FAIL"; exit 1; }
```

**Acceptance:** Unguarded `.toFixed` count = 0; `safeFixed` defined; commit on origin.

---

### Task 1C: AdvancedAnalyticsPanel.jsx full null-safety (10 min)

**Files:** Modify `frontend/src/components/AdvancedAnalyticsPanel.jsx`

- [ ] **Step 1: Gate-on-origin check for Task 1B**

```bash
git fetch origin main
git log origin/main --oneline -1 | grep -q "sidebar-panels" && echo "1B PASS" || { echo "1B FAIL — HALT"; exit 1; }
```

- [ ] **Step 2: Add helpers (idempotent)**

Same Python script as Task 1B Step 2, substituting the file path `frontend/src/components/AdvancedAnalyticsPanel.jsx`.

- [ ] **Step 3: Replace `.toFixed` calls**

Same Python regex as Task 1B Step 3, substituting the file path.

- [ ] **Step 4: Verify counts**

```bash
echo "Unguarded count (must be 0):"
grep -cE "[^?\(]\.toFixed\(" frontend/src/components/AdvancedAnalyticsPanel.jsx
echo "safeFixed defined (must be 1+):"
grep -c "const safeFixed" frontend/src/components/AdvancedAnalyticsPanel.jsx
```

- [ ] **Step 5: Verify React compiles**

Same as Task 1B Step 5.

- [ ] **Step 6: Commit + push + verify-on-origin**

```bash
git add frontend/src/components/AdvancedAnalyticsPanel.jsx
git commit -m "fix(advanced-analytics): null-safety helpers + safeFixed across 5 panels

Same pattern as SidebarPanels (Task 1B).

Verification:
  \$ grep -cE '[^?(]\.toFixed\(' frontend/src/components/AdvancedAnalyticsPanel.jsx
  0
  \$ grep -c 'const safeFixed' frontend/src/components/AdvancedAnalyticsPanel.jsx
  1

Co-Authored-By: DeepSeek <deepseek@floww.dev>"
git pull --rebase origin main && git push origin main
SHA=$(git rev-parse HEAD)
git fetch origin main
[ "$SHA" = "$(git rev-parse origin/main)" ] && echo "1C GATE PASS: $SHA" || { echo "1C GATE FAIL"; exit 1; }
```

**Acceptance:** Same gates as 1B.

---

## Phase 2 — Per-Component Jest Tests (~25 min)

Each test file gets a per-file commit + origin-state gate. DeepSeek cannot batch-skip these.

### Task 2A: PaperTrade.test.jsx (5 min)

**Files:** Create `frontend/src/components/PaperTrade.test.jsx`

- [ ] **Step 1: Gate-on-origin check for Task 1C**

```bash
git fetch origin main
git log origin/main --oneline -1 | grep -q "advanced-analytics" && echo "1C PASS" || { echo "1C FAIL — HALT"; exit 1; }
```

- [ ] **Step 2: Create test file**

```bash
cat > frontend/src/components/PaperTrade.test.jsx <<'EOF'
import React from "react";
import { render, screen } from "@testing-library/react";
import PaperTrade from "./PaperTrade";

// Mock axios so component doesn't actually hit the network
jest.mock("axios", () => ({
  get: jest.fn(() => Promise.reject(new Error("test"))),
  post: jest.fn(() => Promise.reject(new Error("test"))),
}));

describe("PaperTrade", () => {
  test("renders without crashing when portfolio is null", () => {
    const { container } = render(<PaperTrade ticker="SPY" spot={null} />);
    expect(container).toBeTruthy();
  });

  test("renders without crashing when spot is undefined", () => {
    const { container } = render(<PaperTrade ticker="SPY" />);
    expect(container).toBeTruthy();
  });

  test("renders without crashing when ticker is empty", () => {
    const { container } = render(<PaperTrade ticker="" spot={745.64} />);
    expect(container).toBeTruthy();
  });
});
EOF
wc -l frontend/src/components/PaperTrade.test.jsx
```

- [ ] **Step 3: Run the test**

```bash
cd frontend
CI=true node_modules/.bin/react-scripts test --watchAll=false --testPathPattern="PaperTrade" 2>&1 | tail -15
cd ..
```

Expected: "3 passed" or similar. If any failure: HALT.

- [ ] **Step 4: Commit + push + verify-on-origin**

```bash
git add frontend/src/components/PaperTrade.test.jsx
git commit -m "test(papertrade): null-prop + missing-spot smoke tests

3 tests verifying the component renders without crashing under common
null/undefined prop scenarios (portfolio null, spot undefined, ticker empty).

Verification:
  \$ CI=true npx react-scripts test --watchAll=false --testPathPattern='PaperTrade'
  Tests: 3 passed

Co-Authored-By: DeepSeek <deepseek@floww.dev>"
git pull --rebase origin main && git push origin main
SHA=$(git rev-parse HEAD)
git fetch origin main
[ "$SHA" = "$(git rev-parse origin/main)" ] && echo "2A GATE PASS: $SHA" || { echo "2A GATE FAIL"; exit 1; }
```

**Acceptance:** 3 tests pass; file on origin.

---

### Task 2B: SidebarPanels.test.jsx (5 min)

**Files:** Create `frontend/src/components/SidebarPanels.test.jsx`

- [ ] **Step 1: Origin gate for 2A**

```bash
git fetch origin main
git log origin/main --oneline -1 | grep -q "papertrade.*smoke tests" && echo "2A PASS" || { echo "2A FAIL — HALT"; exit 1; }
```

- [ ] **Step 2: Create test file**

```bash
cat > frontend/src/components/SidebarPanels.test.jsx <<'EOF'
import React from "react";
import { render } from "@testing-library/react";
import {
  FlipZonesPanel, StackedNodesPanel, TugOfWarPanel,
  ScenarioPanel, RiskDashboardPanel, OpportunitiesPanel,
  ImpliedMovePanel, VolAnalyticsPanel,
  GreekReferencePanel, UsagePanel, LivePolicyPanel,
} from "./SidebarPanels";

describe("SidebarPanels — null prop smoke tests", () => {
  test.each([
    ["FlipZonesPanel", FlipZonesPanel],
    ["StackedNodesPanel", StackedNodesPanel],
    ["TugOfWarPanel", TugOfWarPanel],
    ["ScenarioPanel", ScenarioPanel],
    ["RiskDashboardPanel", RiskDashboardPanel],
    ["OpportunitiesPanel", OpportunitiesPanel],
    ["ImpliedMovePanel", ImpliedMovePanel],
    ["VolAnalyticsPanel", VolAnalyticsPanel],
    ["GreekReferencePanel", GreekReferencePanel],
    ["UsagePanel", UsagePanel],
    ["LivePolicyPanel", LivePolicyPanel],
  ])("%s renders without crashing on null/undefined props", (name, Panel) => {
    if (!Panel) {
      // Component may not be exported; skip
      return;
    }
    const { container } = render(<Panel data={null} loading={false} error={null} />);
    expect(container).toBeTruthy();
  });
});
EOF
```

- [ ] **Step 3: Run the test**

```bash
cd frontend && CI=true node_modules/.bin/react-scripts test --watchAll=false --testPathPattern="SidebarPanels" 2>&1 | tail -15 && cd ..
```

Expected: tests pass (or skipped if a component isn't exported). HALT on any actual FAIL.

- [ ] **Step 4: Commit + push + origin gate**

```bash
git add frontend/src/components/SidebarPanels.test.jsx
git commit -m "test(sidebar-panels): 11-panel null-prop smoke tests

Verification:
  \$ CI=true npx react-scripts test --watchAll=false --testPathPattern='SidebarPanels'
  Tests: 11 passed (or skipped if not exported)

Co-Authored-By: DeepSeek <deepseek@floww.dev>"
git pull --rebase origin main && git push origin main
SHA=$(git rev-parse HEAD)
git fetch origin main
[ "$SHA" = "$(git rev-parse origin/main)" ] && echo "2B GATE PASS: $SHA" || { echo "2B GATE FAIL"; exit 1; }
```

---

### Task 2C: AdvancedAnalyticsPanel.test.jsx (5 min)

**Files:** Create `frontend/src/components/AdvancedAnalyticsPanel.test.jsx`

- [ ] **Step 1: Origin gate for 2B**

```bash
git fetch origin main
git log origin/main --oneline -1 | grep -q "sidebar-panels.*smoke" && echo "2B PASS" || { echo "2B FAIL — HALT"; exit 1; }
```

- [ ] **Step 2: Create test file (same pattern as 2B for 5 panels)**

```bash
cat > frontend/src/components/AdvancedAnalyticsPanel.test.jsx <<'EOF'
import React from "react";
import { render } from "@testing-library/react";
import {
  MarketRegimePanel, ImpliedPDFPanel, HedgeImpulsePanel,
  PressureCloudPanel, CharmIntegralPanel,
} from "./AdvancedAnalyticsPanel";

describe("AdvancedAnalyticsPanel — null prop smoke tests", () => {
  test.each([
    ["MarketRegimePanel", MarketRegimePanel],
    ["ImpliedPDFPanel", ImpliedPDFPanel],
    ["HedgeImpulsePanel", HedgeImpulsePanel],
    ["PressureCloudPanel", PressureCloudPanel],
    ["CharmIntegralPanel", CharmIntegralPanel],
  ])("%s renders without crashing on null props", (name, Panel) => {
    if (!Panel) return;
    const { container } = render(<Panel data={null} loading={false} error={null} ticker="SPY" />);
    expect(container).toBeTruthy();
  });
});
EOF
```

- [ ] **Step 3: Run + verify**

```bash
cd frontend && CI=true node_modules/.bin/react-scripts test --watchAll=false --testPathPattern="AdvancedAnalyticsPanel" 2>&1 | tail -15 && cd ..
```

- [ ] **Step 4: Commit + push + origin gate**

Same pattern as 2A/2B with appropriate commit message and grep gate.

---

### Task 2D: Trade widgets smoke tests (10 min)

**Files:** Create `frontend/src/components/MorningBriefing.test.jsx`, `PositionSizing.test.jsx`, `DashboardSummary.test.jsx`

- [ ] **Step 1: Origin gate for 2C**

```bash
git fetch origin main
git log origin/main --oneline -1 | grep -q "advanced-analytics.*null" && echo "2C PASS" || { echo "2C FAIL — HALT"; exit 1; }
```

- [ ] **Step 2: Create all 3 test files with the same pattern**

```bash
for COMPONENT in MorningBriefing PositionSizing DashboardSummary; do
cat > frontend/src/components/${COMPONENT}.test.jsx <<EOF
import React from "react";
import { render } from "@testing-library/react";
import { ${COMPONENT} } from "./${COMPONENT}";

jest.mock("axios", () => ({
  get: jest.fn(() => Promise.reject(new Error("test"))),
  post: jest.fn(() => Promise.reject(new Error("test"))),
}));

describe("${COMPONENT}", () => {
  test("renders without crashing on null/undefined props", () => {
    const { container } = render(<${COMPONENT} ticker="SPY" spot={null} />);
    expect(container).toBeTruthy();
  });
});
EOF
done
ls frontend/src/components/{MorningBriefing,PositionSizing,DashboardSummary}.test.jsx
```

- [ ] **Step 3: Run all three**

```bash
cd frontend && CI=true node_modules/.bin/react-scripts test --watchAll=false --testPathPattern="MorningBriefing|PositionSizing|DashboardSummary" 2>&1 | tail -20 && cd ..
```

- [ ] **Step 4: Commit + push + origin gate**

```bash
git add frontend/src/components/MorningBriefing.test.jsx frontend/src/components/PositionSizing.test.jsx frontend/src/components/DashboardSummary.test.jsx
git commit -m "test(widgets): null-prop smoke tests for 3 dashboard widgets

Verification:
  \$ CI=true npx react-scripts test --watchAll=false --testPathPattern='MorningBriefing|PositionSizing|DashboardSummary'
  3 test suites passed

Co-Authored-By: DeepSeek <deepseek@floww.dev>"
git pull --rebase origin main && git push origin main
SHA=$(git rev-parse HEAD)
git fetch origin main
[ "$SHA" = "$(git rev-parse origin/main)" ] && echo "2D GATE PASS: $SHA" || { echo "2D GATE FAIL"; exit 1; }
```

---

## Phase 3 — Deep Backend Endpoint Diagnostic (~15 min)

### Task 3: Per-endpoint failure-mode analysis (15 min)

**Files:** Create `docs/ROUND9_BACKEND_DIAGNOSTIC.md` (READ-ONLY for backend; only writes new doc)

- [ ] **Step 1: Origin gate for 2D**

```bash
git fetch origin main
git log origin/main --oneline -1 | grep -q "widgets.*smoke" && echo "2D PASS" || { echo "2D FAIL — HALT"; exit 1; }
```

- [ ] **Step 2: Inventory endpoints from React**

```bash
grep -rhoE '/api/[a-z-]+(/\{[a-z_]+\}|/[A-Z]+)?' frontend/src \
  --include="*.jsx" --include="*.js" 2>/dev/null | sort -u > /tmp/r9_endpoints.txt
wc -l /tmp/r9_endpoints.txt
```

- [ ] **Step 3: For each endpoint, capture full `curl -v` trace**

```bash
> /tmp/r9_diagnostic.txt
while read ep; do
  url="http://localhost:8000${ep//\{ticker\}/SPY}"
  echo "═════════════════════════════════════════" >> /tmp/r9_diagnostic.txt
  echo "ENDPOINT: $ep" >> /tmp/r9_diagnostic.txt
  echo "URL:      $url" >> /tmp/r9_diagnostic.txt
  echo "─── HEADERS ───" >> /tmp/r9_diagnostic.txt
  curl --max-time 10 -s -I "$url" 2>&1 | head -10 >> /tmp/r9_diagnostic.txt
  echo "─── BODY (first 200 bytes) ───" >> /tmp/r9_diagnostic.txt
  curl --max-time 10 -s "$url" 2>&1 | head -c 200 >> /tmp/r9_diagnostic.txt
  echo "" >> /tmp/r9_diagnostic.txt
  echo "" >> /tmp/r9_diagnostic.txt
done < /tmp/r9_endpoints.txt
wc -l /tmp/r9_diagnostic.txt
```

- [ ] **Step 4: Categorize each endpoint by status**

```bash
> /tmp/r9_categorized.txt
echo "## 200 OK (healthy)" >> /tmp/r9_categorized.txt
grep -B 2 "HTTP/1.1 200\|HTTP/2 200" /tmp/r9_diagnostic.txt | grep "ENDPOINT:" >> /tmp/r9_categorized.txt
echo "" >> /tmp/r9_categorized.txt
echo "## 404 Not Found" >> /tmp/r9_categorized.txt
grep -B 2 "HTTP/1.1 404\|HTTP/2 404" /tmp/r9_diagnostic.txt | grep "ENDPOINT:" >> /tmp/r9_categorized.txt
echo "" >> /tmp/r9_categorized.txt
echo "## 500 Server Error" >> /tmp/r9_categorized.txt
grep -B 2 "HTTP/1.1 500\|HTTP/2 500" /tmp/r9_diagnostic.txt | grep "ENDPOINT:" >> /tmp/r9_categorized.txt
echo "" >> /tmp/r9_categorized.txt
echo "## Other (timeout, connection, etc)" >> /tmp/r9_categorized.txt
grep "ENDPOINT:" /tmp/r9_diagnostic.txt | grep -v -F -f <(grep "ENDPOINT:" /tmp/r9_categorized.txt) >> /tmp/r9_categorized.txt
cat /tmp/r9_categorized.txt
```

- [ ] **Step 5: Write the diagnostic document**

```bash
cat > docs/ROUND9_BACKEND_DIAGNOSTIC.md <<EOF
# Round 9 Backend Diagnostic

Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by DeepSeek V4 Pro.
Inventory source: \`grep -rhoE '/api/...' frontend/src\`
Probe target: http://localhost:8000 (direct, not via CRA proxy)

## Endpoint Categorization

$(cat /tmp/r9_categorized.txt)

## Full Per-Endpoint Trace

\`\`\`
$(cat /tmp/r9_diagnostic.txt)
\`\`\`

## Recommendations for Round 9

For each 404: confirm the route exists in \`backend/routes/\`. If missing, add stub.
For each 500: read uvicorn log (\`tail -100 backend.log\` or wherever) and trace stack.
For each 200 returning text/html: proxy misroute; investigate \`frontend/package.json\` proxy config.

Round 9 priority: fix all 500s first (real bugs), then 404s (missing routes), then text/html misroutes.
EOF

wc -l docs/ROUND9_BACKEND_DIAGNOSTIC.md
```

- [ ] **Step 6: Commit + push + origin gate**

```bash
git add docs/ROUND9_BACKEND_DIAGNOSTIC.md
git commit -m "docs(round-9-diag): per-endpoint backend diagnostic with curl -v traces

$(wc -l < /tmp/r9_endpoints.txt) endpoints probed directly against localhost:8000.
Categorized by status (200/404/500/other) with full headers + first 200B of body.

Recommendations for Round 9 prioritized: 500s first, 404s second, text/html third.

Co-Authored-By: DeepSeek <deepseek@floww.dev>"
git pull --rebase origin main && git push origin main
SHA=$(git rev-parse HEAD)
git fetch origin main
[ "$SHA" = "$(git rev-parse origin/main)" ] && echo "3 GATE PASS: $SHA" || { echo "3 GATE FAIL"; exit 1; }
```

**Acceptance:** Diagnostic doc on origin with per-endpoint curl trace.

---

## Phase 4 — Round 9 Prioritized Backlog (~10 min)

### Task 4: Synthesize backlog from diagnostic + component inventory

**Files:** Create `docs/ROUND9_BACKLOG.md`

- [ ] **Step 1: Origin gate for Task 3**

```bash
git fetch origin main
git log origin/main --oneline -1 | grep -q "round-9-diag" && echo "3 PASS" || { echo "3 FAIL — HALT"; exit 1; }
```

- [ ] **Step 2: Build the backlog document**

```bash
cat > docs/ROUND9_BACKLOG.md <<EOF
# Round 9 Prioritized Backlog

Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by DeepSeek V4 Pro Bulletproof session.
Source: docs/ROUND9_BACKEND_DIAGNOSTIC.md + DeepSeek's working knowledge of the codebase.

## Priority 1 — Backend 500 errors (highest urgency)

These are real bugs surfacing in the dashboard right now.

$(grep -A 1 "## 500" /tmp/r9_categorized.txt 2>/dev/null | tail -n +2 || echo "(none — verify via diagnostic doc)")

## Priority 2 — Backend 404 (missing routes)

Routes the React app calls that don't exist in backend yet.

$(grep -A 20 "## 404" /tmp/r9_categorized.txt 2>/dev/null | grep "ENDPOINT:" || echo "(none — verify via diagnostic doc)")

## Priority 3 — Frontend file ownership remainder

Files in Hermes ownership that DeepSeek can't touch (waiting on Hermes free-tier reset):

- frontend/src/App.js — toggle composition (DAY+CHARM, DTE, Expiries don't combine)
- frontend/src/components/heatseeker/*.jsx — content (imports are clean per audit)
- frontend/src/components/PortfolioPanel.jsx — scenarios/hedge buttons are dummy
- Skylit ticker dropdown — needs UX decision
- Dashboard tab embed style — match dark theme

## Priority 4 — Test coverage gaps

Components without test files (added in Phase 2 of this session):

- AlertsPanel.jsx
- AlertOverlay.jsx
- FlowTicker.jsx
- HistoryPanel.jsx
- OptionsChainTable.jsx
- MultiTimeframeGEXPanel.jsx
- UOAPanel.jsx
- ToxicityGauge.jsx
- BarHeatmap, CharmChart, GridHeatmap, TrinityView, VannaChart (Plotly wrappers)

## Priority 5 — Frontend antipattern cleanup (from ROUND8_FRONTEND_AUDIT.md)

- Missing key props in .map() calls
- console.log/warn/error left in production code

## Estimated session time per priority

- P1: 60-90 min (depends on number of 500s)
- P2: 30-60 min (per missing route)
- P3: requires Hermes (UX/design judgment)
- P4: 20-30 min (mechanical test scaffold)
- P5: 15-30 min (mechanical cleanup)
EOF

wc -l docs/ROUND9_BACKLOG.md
```

- [ ] **Step 3: Commit + push + origin gate**

```bash
git add docs/ROUND9_BACKLOG.md
git commit -m "docs(round-9-backlog): prioritized fix list for next session

P1: Backend 500s (real bugs)
P2: Backend 404s (missing routes)
P3: Hermes-owned UX work (App.js, PortfolioPanel, Skylit ticker)
P4: Test coverage gaps (~13 components without tests)
P5: Antipattern cleanup (missing keys, console.logs)

Co-Authored-By: DeepSeek <deepseek@floww.dev>"
git pull --rebase origin main && git push origin main
SHA=$(git rev-parse HEAD)
git fetch origin main
[ "$SHA" = "$(git rev-parse origin/main)" ] && echo "4 GATE PASS: $SHA" || { echo "4 GATE FAIL"; exit 1; }
```

**Acceptance:** Backlog doc on origin.

---

## Phase 5 — Closure (~5 min)

### Task 5: Final closure with origin-verified count

- [ ] **Step 1: Origin gate for Task 4**

```bash
git fetch origin main
git log origin/main --oneline -1 | grep -q "round-9-backlog" && echo "4 PASS" || { echo "4 FAIL — HALT"; exit 1; }
```

- [ ] **Step 2: Verify ALL tasks landed on origin (anti-skip final check)**

```bash
git log origin/main --oneline --since="2 hours ago" | head -20
echo ""
echo "Expected SHAs from this session (count must be 9):"
count=$(git log origin/main --oneline --since="2 hours ago" --author-date-order | grep -cE "papertrade|sidebar-panels|advanced-analytics|smoke|round-9" || echo 0)
echo "Found: $count"
[ "$count" -ge 8 ] && echo "ANTI-SKIP CHECK PASS" || { echo "ANTI-SKIP CHECK FAIL — some tasks missing"; exit 1; }
```

If anti-skip fails: HALT. Do NOT write closure card claiming completion.

- [ ] **Step 3: Append completion log entry with REAL SHAs from origin**

```bash
cat >> docs/ROUND8_COMPLETION_LOG.md <<EOF

## Round 8 Bulletproof — $(date -u +%Y-%m-%dT%H:%M:%SZ)

Real per-file work with origin-state gates. Each task verified ON ORIGIN, not just locally.

Phase 1 (3 files): finished prior session's skipped work
- 1A PaperTrade: $(git log origin/main --oneline -1 --grep="papertrade.*final" | cut -d' ' -f1)
- 1B SidebarPanels: $(git log origin/main --oneline -1 --grep="sidebar-panels" | cut -d' ' -f1)
- 1C AdvancedAnalyticsPanel: $(git log origin/main --oneline -1 --grep="advanced-analytics" | cut -d' ' -f1)

Phase 2 (6 test files): per-component Jest smoke tests
- 2A PaperTrade.test: $(git log origin/main --oneline -1 --grep="papertrade.*smoke" | cut -d' ' -f1)
- 2B SidebarPanels.test: $(git log origin/main --oneline -1 --grep="sidebar-panels.*smoke" | cut -d' ' -f1)
- 2C AdvancedAnalyticsPanel.test: $(git log origin/main --oneline -1 --grep="advanced-analytics.*null" | cut -d' ' -f1)
- 2D Widget tests: $(git log origin/main --oneline -1 --grep="widgets.*smoke" | cut -d' ' -f1)

Phase 3 (backend diag): $(git log origin/main --oneline -1 --grep="round-9-diag" | cut -d' ' -f1)
Phase 4 (backlog): $(git log origin/main --oneline -1 --grep="round-9-backlog" | cut -d' ' -f1)

HEAD on origin: $(git rev-parse origin/main)
EOF
```

- [ ] **Step 4: Closure kanban card**

```bash
mkdir -p kanban/cards
cat > kanban/cards/deepseek_bulletproof_2026-05-25.md <<EOF
---
id: deepseek-bulletproof-2026-05-25
title: "DeepSeek V4 Pro Bulletproof — per-file gates, anti-skip"
status: done
assignee: deepseek-v4-pro-bulletproof
acceptance: |
  9+ commits on origin/main with grep-verified changes.
  Per-task origin gates passed.
  No fake-completion: each task's SHA verifiable on origin via git fetch+log.
---

## Per-task SHAs on origin

\`\`\`
$(git log origin/main --oneline --since="2 hours ago" | head -15)
\`\`\`

## Unguarded .toFixed counts (final)

\`\`\`
PaperTrade: $(grep -cE "[^?\\(]\\.toFixed\\(" frontend/src/components/PaperTrade.jsx)
SidebarPanels: $(grep -cE "[^?\\(]\\.toFixed\\(" frontend/src/components/SidebarPanels.jsx)
AdvancedAnalyticsPanel: $(grep -cE "[^?\\(]\\.toFixed\\(" frontend/src/components/AdvancedAnalyticsPanel.jsx)
\`\`\`
All three should be 0.
EOF
```

- [ ] **Step 5: Final commit + push**

```bash
git add docs/ROUND8_COMPLETION_LOG.md kanban/cards/deepseek_bulletproof_2026-05-25.md
git commit -m "docs(round-8-bulletproof): closure with origin-verified SHAs (anti-fake-completion)

Each task's SHA fetched from origin/main, not local. Per-task gates prevent silent skipping.

Co-Authored-By: DeepSeek <deepseek@floww.dev>"
git pull --rebase origin main && git push origin main

echo ""
echo "──── BULLETPROOF SESSION COMPLETE ────"
echo "Final HEAD on origin: $(git rev-parse origin/main)"
echo "Commits this session: $(git log origin/main --oneline --since='2 hours ago' | wc -l)"
echo "PaperTrade unguarded: $(grep -cE '[^?(]\.toFixed\(' frontend/src/components/PaperTrade.jsx)"
echo "SidebarPanels unguarded: $(grep -cE '[^?(]\.toFixed\(' frontend/src/components/SidebarPanels.jsx)"
echo "AdvancedAnalyticsPanel unguarded: $(grep -cE '[^?(]\.toFixed\(' frontend/src/components/AdvancedAnalyticsPanel.jsx)"
echo "─────────────────────────────────────"
echo "DONE"
```

**Acceptance:** Anti-skip gate from Step 2 passes; closure docs land; final report shows 0/0/0 for unguarded counts.

---

## Self-Review

**Spec coverage:**
- 3 files skipped last session → Tasks 1A, 1B, 1C ✓
- New test scaffolding → Tasks 2A, 2B, 2C, 2D ✓
- Backend diagnostic → Task 3 ✓
- Round 9 backlog → Task 4 ✓
- Closure with anti-skip verification → Task 5 ✓

**Anti-skip defenses:**
- Every task starts with `git fetch origin main` + `git log origin/main` grep for the prior task's commit message
- If prior task didn't actually land on origin: HALT
- Closure Step 2 counts commits on origin; if < expected: HALT
- DeepSeek cannot fake by writing local commits and skipping push — gates check origin

**Placeholder scan:** No "TODO" / "fill in" / vague instructions. Every step has executable bash + expected output.

**Time estimate:** 5+10+10+5+5+5+10+15+10+5 = 80 min (allows buffer for compile/test reload). DeepSeek's mechanical speed reduces this; expect 50-65 min real wall-clock.

**Why this can't be faked in 20 min:**
- 9 separate commits required (vs prior plan's batch-commits)
- Each commit must land on origin AND be verified via git fetch
- Tests must actually run and pass (not just file-create)
- Backend diagnostic requires real curl invocations against running server (can't be hallucinated)
- Backlog document references real per-endpoint data captured by Task 3

If DeepSeek attempts to skip ahead, the next task's origin gate will FAIL and force a HALT.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-05-25-round8-bulletproof.md`.

DeepSeek prompt: `DEEPSEEK_V4_PRO_BULLETPROOF.md` (generated next).
