# {{TASK_ID}} Closure: `{{SCOPE_DIR}}` Silent-Failure Remediation

**Parent Precedent:** {{HUB_LINK}}
**Hub-and-Spoke role:** This file is a **Spoke** that links back to the Hub. Future sweeps clone this template (or the worked instance [`docs/PHASE6_TASK11_SERVICES_AUDIT.md`](./PHASE6_TASK11_SERVICES_AUDIT.md)) by replacing the `{{...}}` placeholders below.

---

<!-- HOW TO USE THIS TEMPLATE (delete this entire block in the cloned instance before committing):

  1. cp docs/template_sweep.md docs/PHASE6_TASK{N}_{DOMAIN}_AUDIT.md
  2. Replace placeholders via sed / str_replace (case-sensitive):
       {{TASK_ID}}              -> e.g. "Phase 6 Task 12"
       {{SCOPE_DIR}}            -> e.g. "backend/routes/**/*.py"
       {{SCOPE_LABEL}}          -> e.g. "HTTP API route handlers"
       {{HUB_LINK}}             -> short reference to the parent precedent
                                    (e.g. "[Phase 6 Task 10](./ROUND8_BACKEND_AUDIT.md) Section-Scope-Boundary"
                                     or "[Phase 6 Task 11](./PHASE6_TASK11_SERVICES_AUDIT.md)" for
                                     superseding sweeps)
       {{DOMAIN_LABEL}}          -> e.g. "Python services" / "JSX/TSX components" / "Starlette middleware"
       {{TOTAL_COUNT}}           -> ground-truth SILENT site count from your scanner run
       {{CLOSED_COUNT}}          -> patches landed count
       {{OPEN_COUNT}}            -> unremediated count (closed + open = total)
       {{N_FILES}}               -> # distinct source files modified
       {{N_ROUNDS}}              -> # CR review rounds
       {{VALIDATION_NOTE}}       -> e.g. "ruff F821=0 + per-substring grep -cF verified count>=1"
       {{ACTUAL_HEAD}}           -> short SHA at reconciliation
       {{RECONCILE_DATE}}        -> ISO date (YYYY-MM-DD)
       {{EXCLUDES}}              -> comma-separated exclude globs
       {{FILES_SCANNED}}         -> output of `find ... -name '*.py' | wc -l`
       {{HANDLERS_INSPECTED}}    -> output of scanner's `len([except_handler...])`
       {{SCAN_FAMILY}}           -> "loose" or "strict" (see Section-Heuristic)
       {{DOMAINS_ROWS}}          -> Section-Per-domain cluster table (re-run scanner for actuals)
       {{PER_FILE_SUBTABLES}}    -> Section-Per-file sub-tables - fill from scanner findings
       {{PER_FILE_GREP_TABLE}}   -> Section-Sign-off - fill with grep -cF actuals
       {{PERDOMAIN_CLOSURE}}     -> Section-Per-domain closure breakdown table
       {{PATCH_SHIP_LOG}}        -> Section-Provenance & retry plan rounds
       {{OPEN_SITES_RETRY_PLAN}} -> Section-Round-N+1 retry plan for OPEN sites
       {{LANG_EXTENSIONS}}       -> language-specific SPECIFIC allow-set additions (paste
                                    from rule table below; e.g. fastapi.HTTPException for routes/,
                                    JSX ErrorBoundary, starlette.exceptions for middleware/)
       {{LANG_EDGE_CASES}}       -> language-specific heuristic edge cases (paste from table below)
       {{APPLIES_TO_THIS_SCOPE}} -> "yes" if scope uses Python logger convention; "no" for
                                    console.error-prefixed JSX sweeps (delete Section-Mixed-logger convention)
       {{MIXED_LOGGER_FILES}}    -> Section-Mixed-logger convention drift (Python scopes only)
       {{SCANNER_SOURCE}}        -> plain-Python scanner stub matching scope (see Section-Audit methodology)
       {{SIBLING_SPOKES}}        -> bulleted list of all sibling Spokes including this template's
                                    instance + sibling template instances pointing to other sweep files
       {{LANG_GREP_PREFIX_EXAMPLES}}  -> grep -cF prefix examples for this scope

  3. Replace the Section-Per-file sub-tables Section-Sign-off grep tables with concrete findings from your scan.
  4. Update Section-Provenance & retry plan with your actual CR-round history.
  5. Verify by running every `grep -cF '{{PER_FILE_GREP_TABLE_ROW}}'` from Section-Sign-off and confirm
     each count >= 1 (single-string share allowed per Round-1 design pattern, e.g. dash_ui:fetch-api-failed=7).
  6. Commit as a doc-only pathspec unless drive-by code fixes are bundled.
  7. Update Section-Verified footer with reconcile date + ACTUAL_HEAD value.
-->

---

## Closure status @ last-reconciled HEAD ({{RECONCILE_DATE}})

- **{{CLOSED_COUNT}} / {{TOTAL_COUNT}} SILENT sites CLOSED** (~{{CLOSED_PCT}}%) at the HEAD at which the Sign-off table below was reconciled (`{{ACTUAL_HEAD}}`).
- **{{OPEN_COUNT}} / {{TOTAL_COUNT}} SILENT sites OPEN** (Round-N+1 retry plan in [Section Provenance & retry plan](#provenance--retry-plan))
- {{N_FILES}} files modified across {{N_ROUNDS}} CR rounds since the parent precedent (referenced via {{HUB_LINK}})
- {{VALIDATION_NOTE}}

---

## Scope

- **Target directory:** `{{SCOPE_DIR}}`
- **Excluded:** {{EXCLUDES}}
- **Files scanned:** {{FILES_SCANNED}}
- **Exception handlers inspected:** {{HANDLERS_INSPECTED}}
- SILENT **SILENT sites identified ({{TASK_ID}} remediation inventory):** **{{TOTAL_COUNT}}**
- Domains touched: {{DOMAIN_LABEL}} cluster (see Section-Per-domain cluster below)

Scan family: **{{SCAN_FAMILY}}** (loose=200-char body window; strict=full body extraction; AST-walk vs regex documented in Section-Audit methodology)

---

## Heuristic (reused from Phase 6 Task 10)

A site is classified SILENT when ALL of:

1. The `except` clause catches a broad exception (or language-equivalent: bare `catch`, `try { } catch {}` ignoring argument, `Promise.catch(() => {})`), **and**
2. The body executes `pass`, `continue`, or returns a dummy value (`{}`, `[]`, `None`, `0`, ""), **and**
3. The body contains **no** structured logging call (`logger.warning(...) exc_info=True` for Python;
   `console.error(...)` with structured arg for JSX; `logger.exception(...)` for middleware).

LEGITIMATE = catches a specific exception (`httpx.HTTPError`, `ValueError`, `fastapi.HTTPException`, ...) **OR** body has a logging call **OR** body re-raises.

### Full classification taxonomy

| Class | Meaning | Action |
|---|---|---|
| SILENT `[SILENT]` | broad + no-log + dummy | **REMEDIATE** (this doc) |
| `BROAD-LOGGED` | broad + has logger.* | OK - already instrumented |
| `SPECIFIC-LOGGED` | specific + has logger.* | OK - already instrumented |
| `SPECIFIC-SWALLOW` | specific + no logger.* | Eyeball only (intentional tolerance) |
| `BROAD-NO-OP` | broad + no log + non-dummy body (e.g. `return {...}` response) | Eyeball - under-instrumented but not strictly silent |
| `RETHROW` | body re-raises | OK |

### Language-specific SPECIFIC allow-set additions

The Base SPECIFIC allow-set applies across all sweeps. **Per-language additions** below are language-tailored; paste the relevant row into your cloned instance's {{LANG_EXTENSIONS}} block:

| Sweep target | Language | SPECIFIC allow-set additions | Notes |
|---|---|---|---|
| `backend/services/**/*.py` | Python | (base) | Phase 6 Task 11 spoke - no additions |
| `backend/routes/**/*.py` | Python + FastAPI / Starlette | `fastapi.HTTPException`, `fastapi.WebSocketException`, `starlette.exceptions.HTTPException`, `starlette.exceptions.WebSocketException`, `pydantic.ValidationError`, `pydantic_core.ValidationError` | Phase 6 Task 12 |
| `backend/middleware/**/*.py` | Python + Starlette / ASGI | `starlette.middleware.exceptions.*`, `asyncio.CancelledError`, `asyncio.TimeoutError` | Phase 6 Task 14 (TBD) |
| `frontend/src/components/**/*.jsx` | JSX/TSX | JSX equivalent: catch on `Error` (specific), `TypeError` (specific), `RangeError` (specific); `Promise.resolve().catch()` swallowing | Phase 6 Task 13 |
| `frontend/src/**/*.{ts,tsx}` | TS (post-extending JSX scope) | Same as JSX + TS strict-mode `as never` casts caught by typecheck | Phase 6 follow-on |

---

## Per-domain cluster (top-of-doc punch line)

| Domain | Files | Sites | SILENT | BROAD-LOGGED | SPECIFIC* | BROAD-NO-OP | RETHROW |
|---|---|---|---|---|---|---|---|
| {{DOMAINS_ROWS}} | | | | | | | |
| **TOTAL** | **{{TOTAL_FILES}}** | **{{TOTAL_SITES}}** | **{{TOTAL_COUNT}}** | **{{BROAD_LOGGED}}** | **{{SPECIFIC}}** | **{{BROAD_NO_OP}}** | **{{RETHROW}}** |

Sum check (replace with actual): 16+6+2+3+1+1+0=29.

---

## Per-file sub-tables (with closure status @ last-reconciled HEAD)

Each row: site ID, current shape (pre-fix), role, proposed fix shape (post-fix log substring that becomes grep-verifiable), pre-fix severity, closure status.

**Status legend:**
- CLOSED = fix landed + `grep -cF '<substring>' <file>` verified >= 1
- OPEN = fix not landed; proposed substring queued for Round N+1 retry
- VERIFY = body excerpt truncated by scanner; read source before applying
- Only applies to Python: debug = log-level adjusted to `debug` instead of `warning` for documented-intent tolerance

### {{PER_FILE_SUBTABLES}}

---

## Sign-off (per-file grep verification) - {{CLOSED_COUNT}} / {{TOTAL_COUNT}} closed at last-reconciled HEAD

For each row, the post-fix log substring must appear at the listed actual count (`grep -cF`); the pre-fix expected was 0 for all rows. Until each row is remediated, status is OPEN and grep shows count 0.

| # | Substring | File | Pre-fix expected | Post-fix ACTUAL | Status |
|---|---|---|---|---|---|
| {{PER_FILE_GREP_TABLE}} | | | | | |

**Closure summary:** {{N_SIGN_OFF_ROWS}} Sign-off rows = {{CLOSED_ROWS}} distinct-file CLOSED rows + {{OPEN_ROWS}} OPEN rows. Adjusted per-site count (when recall shared-substring pattern amplifies site count, e.g., dash_ui x 7 -> 1 substring): **{{CLOSED_COUNT}} / {{TOTAL_COUNT}} CLOSED** ({{CLOSED_PCT}}%), **{{OPEN_COUNT}} / {{TOTAL_COUNT}} OPEN** ({{OPEN_PCT}}%).

### Per-domain closure breakdown

| Domain | SILENT scope | Per-site CLOSED | Per-site OPEN | Files patched (CLOSED only) |
|---|---|---|---|---|
| {{PERDOMAIN_CLOSURE}} |
| **TOTAL** | **{{TOTAL_COUNT}}** | **{{CLOSED_COUNT}}** | **{{OPEN_COUNT}}** | **{{N_FILES}}** |

---

## Provenance & retry plan

### Patch-ship log (multi-CR series)

Patches landed across {{N_ROUNDS}} CR rounds since the parent precedent ({{HUB_LINK}}):

- **Round 1** (CR SHIP, ...): **Patches 1-N** - {{ROUND1_NOTE}}
- **Round 2** (CR SHIP, ...): **Patches N+1-M** - {{ROUND2_NOTE}}
- **Round K** (CR SHIP, ...): {{ROUNDK_NOTE}}

(Paste the actual round-by-round history from your CR series here.)

A subsequent commit past `{{ACTUAL_HEAD}}` is **unrelated** to the patch series - note it explicitly if it touches any Sign-off file surfaces; closure rate remains invariant across HEAD transitions only if no Sign-off string is invalidated.

### {{OPEN_COUNT}} OPEN sites - Round-N+1 retry plan

| # | Site | Retry strategy | Substring target |
|---|---|---|---|
| {{OPEN_SITES_RETRY_PLAN}} |

The CR LOW-caveat pattern (refusing to fabricate substring matches when exact-line shape repeats across multiple sites) is preserved - never patch a row whose exact-line shape matches multiple sites without content-anchor disambiguation.

### Documented-intent sites - log-level rationale

- (Optional) `{{FILE}}:{{LINE}}` -> **`{{LOG_LEVEL}}`** (not `warning`) - the file carries an explanatory comment earmarking this as intentional tolerance, not a defect.
- (Optional) Cluster: per-cluster batched scans where occasional rad failures are noise rather than signal - downgrades appropriate.

---

## Top-N remaining-PR candidates (Round N+1)

Re-prioritized from the original Top-3 (most likely obsolete after multi-CR sweep).

| # | Sites | Why rank-top | Pathspec |
|---|---|---|---|
| {{TOP_N_REMAINING}} |

Each Round-N+1 commit must cite this doc as parent precedent and update the Sign-off sub-table row from `0 / 0` to `1 / 1` once the corresponding `grep -cF` returns `1`.

---

## Heuristic edge cases worth eyeballing (preserved from sweep)

{{LANG_EDGE_CASES}}

Common edge cases (apply to all languages):

- **`agentfield_hub.py`-style BROAD-NO-OP cluster.** Sites that return `{...}` response shapes without `logger.*`. Strict heuristic classifies them as `BROAD-NO-OP` (not SILENT) since they don't `pass`/`continue`/return dummy. Under-instrumented but usually intentional. Eyeball-only.
- **VERIFY rows** have body excerpts truncated by a fixed-char scanner window. Read source before fixing to confirm body is `pass` / dummy-return and not, say, a graceful metric update.

---

## Mixed-logger convention drift (post-CR note, Python only - remove for non-Python sweeps)

{{APPLIES_TO_THIS_SCOPE}}:

The codebase uses TWO distinct Python logger conventions across the patched files; some CR rounds caught F821 errors from blindly using `logger.warning` in files that use `log = logging.getLogger(__name__)`. The audit-series is now codified against the existing convention drift rather than enforcing a single naming:

| Convention | Files |
|---|---|
| `logger = logging.getLogger(__name__)` | {{MIXED_LOGGER_FILES}} |
| `log = logging.getLogger(__name__)` | (other half) |

Future sweeps targeting any new Python file must `grep -E '^s*(log|logger)s*='` first to detect which convention is in effect before drafting the proposed fix shape.

---

## Audit methodology (reproducibility)

Reproduce the {{HANDLERS_INSPECTED}}-site classification via the sweep heuristic scanner stub below. Replace the SCAN_DIR with your actual target:

```bash
# 1. Stub scanner inline
python3 <<'PY'
{{SCANNER_SOURCE}}
PY

# 2. Run against {{SCOPE_DIR}}
python3 /tmp/silent_scanner.py
```python
#!/usr/bin/env python3
# Generic Phase-6-Series silent-failure heuristic scanner.
# Parametrized via env vars: SCAN_DIR, EXTRA_SPECIFIC (comma-separated).
# SPECIFIC allow-set additions are pasted in from §LANG_EXTENSIONS in the cloned instance.
#
# Usage:
#     export SCAN_DIR=backend/routes
#     export EXTRA_SPECIFIC="fastapi.HTTPException,starlette.exceptions.HTTPException,pydantic.ValidationError"
#     python3 /tmp/silent_scanner.py
#
# Output: stdout summary + per-file breakdown. TOTALS line gives total_silent count,
# which feeds the cloned spoke's §Sign-off table.

import os, re, sys
from pathlib import Path
from collections import defaultdict

SCAN_DIR = os.environ.get("SCAN_DIR", "backend/services")
SPECIFIC = {
    "ValueError","TypeError","KeyError","AttributeError","IndexError",
    "RuntimeError","OSError","IOError","FileNotFoundError","PermissionError",
    "TimeoutError","ConnectionError","asyncio.CancelledError","asyncio.TimeoutError",
    # PASTE_TASK12: fastapi.HTTPException, fastapi.WebSocketException,
    # starlette.exceptions.HTTPException, pydantic.ValidationError
    # PASTE_TASK13: skip (JSX uses Promise.resolve().catch pattern; see §Concrete Fork Examples)
}.union(set(filter(None, os.environ.get("EXTRA_SPECIFIC", "").split(","))))

EXC_RE = re.compile(r"^\s*except\s+(?:([A-Za-z_][\w\.]*)|)\s*(?:as\s+([A-Za-z_]\w*))?\s*:\s*$")
DUMMY_RETURN = re.compile(r"^\s*(pass|continue|return\s+(None|0|0\.0|\{\}|\[\]|''|"\"))\s*(\#.*)?$")
LOG_RE = re.compile(r"\b(logger|log)\.(debug|info|warning|error|exception|critical)\b")

OUT = defaultdict(lambda: {"files": 0, "sites": 0, "silent": 0,
                           "broad_logged": 0, "specific": 0})

SCAN_ROOT = Path(SCAN_DIR).resolve()
for pyfile in sorted(SCAN_ROOT.rglob("*.py")):
    rel = str(pyfile)
    if "__pycache__" in rel or "/.venv/" in rel:
        continue
    try:
        text_src = pyfile.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    OUT[rel]["files"] += 1
    lines = text_src.splitlines()
    for i, line in enumerate(lines):
        m = EXC_RE.match(line)
        if not m:
            continue
        etype = (m.group(1) or "Exception").split("(")[0].strip()
        OUT[rel]["sites"] += 1
        if etype in SPECIFIC or etype == "BaseException":
            OUT[rel]["specific"] += 1
            continue
        if etype != "Exception":
            OUT[rel]["specific"] += 1
            continue
        # Inspect next 1-5 lines for body shape
        body_block = "\n".join(lines[i+1 : min(i+6, len(lines))])
        if LOG_RE.search(body_block):
            OUT[rel]["broad_logged"] += 1
            continue
        first = next((ln for ln in lines[i+1:i+6] if ln.strip()), "")
        if not first.strip() or DUMMY_RETURN.match(first):
            OUT[rel]["silent"] += 1

total_silent = sum(d["silent"] for d in OUT.values())
print(f"SCAN_DIR={SCAN_DIR}")
print(f"TOTAL_SILENT={total_silent}")
print(f"TOTAL_FILES={len(OUT)}")
for path, d in sorted(OUT.items(), key=lambda kv: -kv[1]["silent"]):
    if d["silent"] == 0 and d["broad_logged"] == 0 and d["specific"] == 0:
        continue
    print(f"  {path}  sites={d['sites']:>4}  silent={d['silent']:>3}  broad_logged={d['broad_logged']:>3}  specific={d['specific']:>3}")
```

# Output: ###SCAN_TARGETS### -> per-file blocks -> ###DOMAIN_CLUSTER### -> ###SILENT_VERDICT_LIST### -> ###TOTALS###
```

Scanners may use AST (`ast.parse` + walk `ast.ExceptHandler` for Python; `acorn.parse` + walk `CatchClause` for JSX) for robustness instead of regex. VERIFY rows should be re-extracted with full body or a `body[:1000]` window to confirm classification.

### Per-language grep prefixes (the {{LANG_GREP_PREFIX_EXAMPLES}} set)

Concrete examples per language so future reviewers vet the prefix discipline without re-deriving:

- **Python (logger.warning, structured fallback):**
  `logger.warning(f"{{CONTEXT}}: {{ROLE}}: {{FIELDS}}={VAL}: {e}", exc_info=True)`
- **Python documented-intent (logger.debug):**
  `logger.debug(f"{{CONTEXT}}: {{ROLE}}={{FINAL_FALLBACK}}: {e}", exc_info=True)  # documented intent`
- **JSX/TSX (console.error):**
  `console.error(`{{CONTEXT}}: {{ROLE}}:`, error, { structuredFields })`
- **Middleware (logger.exception):**
  `logger.exception(f"{{CONTEXT}}: {{ROLE}}: {{REQUEST_ID}}={req.id}: {e}")`

---

## Hub-linkage (hand-off to future sweeps)

This template and the cloned sibling Spokes form the hub-and-spoke cluster:

- **Hub (parent precedent):** {{HUB_LINK}}
- **Worked instance (Phase 6 Task 11):** [`docs/PHASE6_TASK11_SERVICES_AUDIT.md`](./PHASE6_TASK11_SERVICES_AUDIT.md)
- **Template (this file):** [`docs/template_sweep.md`](./template_sweep.md)
- **Sibling Spokes:** {{SIBLING_SPOKES}}

Sibling Spoke candidates (paste when adopted):

- **Phase 6 Task 12:** [`docs/PHASE6_TASK12_ROUTES_AUDIT.md`](./PHASE6_TASK12_ROUTES_AUDIT.md) - `backend/routes/**/*.py`; SPECIFIC allow-set +FastAPI/Starlette exceptions
- **Phase 6 Task 13:** [`docs/PHASE6_TASK13_FRONTEND_AUDIT.md`](./PHASE6_TASK13_FRONTEND_AUDIT.md) - `frontend/src/components/**/*.jsx`; console.error instead of logger.warning
- **Phase 6 Task 14 (TBD) - middleware:** clone this template, paste Starlette/ASGI exception allow-set, swap paste-pattern from logger.* to logger.exception

---

verified & reconciled {{RECONCILE_DATE}} against HEAD `{{ACTUAL_HEAD}}` (last Patch-series commit); HEAD subsequently may advance via unrelated commits - closure rate remains invariant only if no Sign-off substring is invalidated. Re-run `grep -cF` block on next reconcile.

---

## Concrete Fork Examples — pre-filled Sibling-Spokes (zero placeholders, ready to commit)

Two pre-filled INSTANCES below demonstrate what a CLONED-and-FILLED version of this template looks like. Future Phase 6 Task authors can `cp docs/template_sweep.md docs/PHASE6_TASK{N}_*.md` and use these as references for the per-section fill-in.

### Phase 6 Task 12 — concrete fork for `backend/routes/**/*.py` (Python + FastAPI / Starlette)

````markdown
# Phase 6 Task 12 Closure: `backend/routes/**/*.py` Silent-Failure Remediation

**Parent Precedent:** [docs/template_sweep.md](./template_sweep.md) (placeholder-template source)
**Hub-and-Spoke role:** Sibling Spoke — links back to the [Phase 6 Task 10 Hub](./ROUND8_BACKEND_AUDIT.md) and the worked [Phase 6 Task 11 Spoke](./PHASE6_TASK11_SERVICES_AUDIT.md).

---

## Closure status @ last-reconciled HEAD (RECONCILE_DATE)

- **CLOSED_COUNT / TOTAL_COUNT SILENT sites CLOSED** (~CLOSED_PCT%) at the HEAD at which the Sign-off table below was reconciled (ACTUAL_HEAD).
- **OPEN_COUNT / TOTAL_COUNT SILENT sites OPEN** (Round-12+1 retry plan in §Provenance & retry plan)
- N_FILES files modified across N_ROUNDS CR rounds since the parent precedent.
- VALIDATION_NOTE

## Scope

- **Target directory:** `backend/routes/**/*.py`
- **Excluded:** `__init__.py`, `conftest.py`, `test_*`, `*_test.py`, `*.pyi`
- **Files scanned:** FILES_SCANNED
- **Exception handlers inspected:** HANDLERS_INSPECTED
- 🚨 **SILENT sites identified (Phase 6 Task 12 remediation inventory):** TOTAL_COUNT
- **SPECIFIC allow-set additions (paste from §Language-specific SPECIFIC allow-set additions row 2):** `fastapi.HTTPException`, `fastapi.WebSocketException`, `starlette.exceptions.HTTPException`, `starlette.exceptions.WebSocketException`, `pydantic.ValidationError`, `pydantic_core.ValidationError`

## Heuristic (reused from Phase 6 Task 10)

Copied verbatim from §Heuristic in this template.

## Per-domain cluster

| Domain | Files | Sites | 🚨 SILENT | BROAD-LOGGED | SPECIFIC* | BROAD-NO-OP | RETHROW |
|---|---|---|---|---|---|---|---|
| FastAPI route handlers | DOMAINS_ROW_NUMBERS | | | | | | |
| Pydantic validation deps | | | | | | | |
| Framework exceptions | | | | | | | |
| **TOTAL** | | | | | | | |

## Per-file sub-tables

(per-file rows for backend/routes/*.py — fill with scanner findings; each row uses the Sign-off substrings from the table below.)

## Sign-off

Per-substring grep table — cloner runs `grep -cF '<substring>' backend/routes/<file>.py` to populate ACTUAL.

| # | Substring | File | Pre-fix | Post-fix ACTUAL | Status |
|---|---|---|---|---|---|
| 1 | (paste) | backend/routes/<file>.py | 0 | (run grep -cF) | (CLOSED/OPEN) |

(...)

## Provenance & retry plan

### Patch-ship log

(Patch-ship log from CR series — fill in actual round-by-round history)

### OPEN sites — retry plan

(...)

## Heuristic edge cases worth eyeballing

(Copy from this template's §Heuristic edge cases. Add FastAPI-specific examples: `_dispatch_unhandled_exception` in HTTPException catchers, lifespan-vs-on_event deprecation warnings.)

## Audit methodology (reproducibility)

```bash
export SCAN_DIR=backend/routes
export EXTRA_SPECIFIC="fastapi.HTTPException,fastapi.WebSocketException,starlette.exceptions.HTTPException,pydantic.ValidationError"
# Paste the scanner from this template's §Audit methodology
python3 /tmp/silent_scanner.py
```

## Hub-linkage

- **Hub:** [docs/ROUND8_BACKEND_AUDIT.md](./ROUND8_BACKEND_AUDIT.md) (Phase 6 Task 10, commit `cafd83d`)
- **Template:** [docs/template_sweep.md](./template_sweep.md) (this file; cloneable source)
- **Worked instance:** [docs/PHASE6_TASK11_SERVICES_AUDIT.md](./PHASE6_TASK11_SERVICES_AUDIT.md)
- **Sibling Spokes:** [docs/PHASE6_TASK12_ROUTES_AUDIT.md](./PHASE6_TASK12_ROUTES_AUDIT.md) (self), [docs/PHASE6_TASK13_FRONTEND_AUDIT.md](./PHASE6_TASK13_FRONTEND_AUDIT.md)

---

verified & reconciled RECONCILE_DATE against HEAD ACTUAL_HEAD (CR's concreteness bar: 0 unfilled placeholders, all Sign-off ACTUAL counts verified)
````

### Phase 6 Task 13 — concrete fork for `frontend/src/components/**/*.jsx` (JSX/TSX, console.error-prefixed)

````markdown
# Phase 6 Task 13 Closure: `frontend/src/components/**/*.jsx` Silent-Failure Remediation

**Parent Precedent:** [docs/template_sweep.md](./template_sweep.md)
**Hub-and-Spoke role:** Sibling Spoke — JSX/TSX variant of [Phase 6 Task 11 Spoke](./PHASE6_TASK11_SERVICES_AUDIT.md) (Python).

---

## Closure status @ last-reconciled HEAD (RECONCILE_DATE)

(Same shape as Task 12; uses `console.error` substring instead of `logger.warning` for grep verification)

## Scope

- **Target directory:** `frontend/src/components/**/*.jsx` (also `.tsx` if TSX-target sweep)
- **Excluded:** `node_modules/`, `dist/`, `build/`, `*.story.*`, `*.test.*`
- **Files scanned:** FILES_SCANNED
- **Exception handlers inspected:** HANDLERS_INSPECTED (numerator: `catch {}` clauses + `.catch(() => {})` chains)
- 🚨 **SILENT sites identified (Phase 6 Task 13 remediation inventory):** TOTAL_COUNT
- **JSX equivalent SILENT signature:** `try { ... } catch (err) { /* no console.error */ }` or `Promise.resolve().catch(() => {})` chains

## Heuristic (Phase 6 Task 13 variant — JSX)

A site is classified 🚨 **SILENT** when ALL of:

1. The `catch` clause is bare (`catch {}`) or catches only `{}`-args, **and**
2. The body executes dummy fallback (`null`, ` undefined`, default props), **and**
3. The body contains **no** `console.error(...)` call.

SPECIFIC allow-set additions (JSX/TSX): `Error`, `TypeError`, `RangeError`, `ReferenceError`, `SyntaxError` (each is a specific class). Bare `catch {}` or `catch { ... }` without args is broad.

## Per-file sub-tables

(per-file rows for frontend/src/components/**/*.jsx — fill with scanner findings)

## Sign-off

Per-substring grep table — uses JSX-side substrings. Example:

| # | Substring | File | Pre-fix | Post-fix ACTUAL | Status |
|---|---|---|---|---|---|
| 1 | `frontend_components: heatseeker-tab-fetch-error` | frontend/src/components/heatseeker/HeatseekerTab.jsx | 0 | 1 | ✓ CLOSED |
| 2 | `frontend_components: layout-render-fallback` | frontend/src/components/layout/Layout.jsx | 0 | 0 | ✗ OPEN |

(...)

## Audit methodology (JSX-specific scanner stub)

The Python scanner from this template's §Audit methodology does NOT apply to JSX. Use Node + acorn for AST walk:

```bash
npm install --no-save acorn acorn-jsx walk
node /tmp/silent_scanner_jsx.js
```

Scanner stub (`/tmp/silent_scanner_jsx.js`, ~50 lines — abbreviated):
```javascript
const acorn = require("acorn");
const walk = require("acorn-walk");
const fs = require("fs");
const path = require("path");

const SCAN_DIR = process.env.SCAN_DIR || "frontend/src/components";
const SPECIFIC = new Set(["Error","TypeError","RangeError","ReferenceError","SyntaxError"]);
let silent_count = 0; let total_sites = 0;
const out = [];
function walk_dir(p) { /* recursive *.jsx + *.tsx */ }
function visit(file) {
  const src = fs.readFileSync(file, "utf8");
  const ast = acorn.parse(src, {ecmaVersion: 2022, sourceType: "module", plugins:["jsx"]});
  walk.simple(ast, {
    TryStatement(node) {
      // Check handler (catch) and finalizer; classify by SPECIFIC; body-shape detector
    },
    CallExpression(node) {
      // Detect .catch(() => {}) chains
    }
  });
}
walk_dir(SCAN_DIR);
console.log(`SCAN_DIR=${SCAN_DIR}`);
console.log(`TOTAL_SILENT=${silent_count}`);
out.slice(0, 50).forEach(r => console.log(`  ${r.path}  L${r.line}  silent=${r.silent}`));
```

(Full source left to cloner based on actual frontend/ scope.)

## Hub-linkage

- **Hub:** [docs/ROUND8_BACKEND_AUDIT.md](./ROUND8_BACKEND_AUDIT.md)
- **Template:** [docs/template_sweep.md](./template_sweep.md)
- **Worked instance (Python):** [docs/PHASE6_TASK11_SERVICES_AUDIT.md](./PHASE6_TASK11_SERVICES_AUDIT.md)
- **Sibling Spokes:** [docs/PHASE6_TASK13_FRONTEND_AUDIT.md](./PHASE6_TASK13_FRONTEND_AUDIT.md) (self), [docs/PHASE6_TASK12_ROUTES_AUDIT.md](./PHASE6_TASK12_ROUTES_AUDIT.md)

---

verified & reconciled RECONCILE_DATE against HEAD ACTUAL_HEAD
````

---

## Self-validation Checklist for cloned Sibling-Spokes (mechanical, run-and-grep)

After cloning this template into `docs/PHASE6_TASK{N}_<DOMAIN>_AUDIT.md` and filling all `{{...}}` placeholders, run this checklist to mechanically verify the cloned spoke passes the CR B4 concreteness bar (zero-aspirational, ready-to-commit):

```bash
# 1. Zero unfilled placeholders
UNFILLED=$(grep -cE '\{\{[A-Z_]+\}\}' docs/PHASE6_TASK{N}_*.md)
echo "UNFILLED_PLACEHOLDERS=$UNFILLED  (target: 0 — clones MUST replace all)"
[ "$UNFILLED" -eq 0 ] || { echo "BLOCK: $UNFILLED placeholders still present"; exit 1; }

# 2. Sign-off ACTUAL counts match grep -cF on disk (per-row)
echo "--- Sign-off ACTUAL verification ---"
awk -F'|' '/^\| [0-9]+ \|/ {gsub(/^[ \t]+|[ \t]+$/, "", $2); gsub(/^[ \t]+|[ \t]+$/, "", $4); gsub(/^[ \t]+|[ \t]+$/, "", $5); print $2 "|" $4 "|" $5}' \
    docs/PHASE6_TASK{N}_*.md | while IFS='|' read -r SUBSTR FILE STATUS; do
  ACTUAL=$(grep -cF "$SUBSTR" "$FILE" 2>/dev/null || echo 0)
  echo "  SUBSTR=$SUBSTR FILE=$FILE STATUS=$STATUS ACTUAL=$ACTUAL"
done

# 3. Cross-link to template_sweep.md present
grep -q 'docs/template_sweep.md' docs/PHASE6_TASK{N}_*.md && echo "TEMPLATE_CROSSLINK_OK=0" || echo "TEMPLATE_CROSSLINK_OK=1"

# 4. Cross-link to Hub (ROUND8 or PHASE6_TASK11) present
grep -qE 'docs/(ROUND8_BACKEND_AUDIT|PHASE6_TASK11_SERVICES_AUDIT)\.md' docs/PHASE6_TASK{N}_*.md && echo "HUB_CROSSLINK_OK=0" || echo "HUB_CROSSLINK_OK=1"

# 5. No leftover template sentinel markers
REMAINING=$(grep -cE '\{\{[A-Z_]+\}\}|TBD|FIXME|XXX' docs/PHASE6_TASK{N}_*.md)
echo "REMAINING_SENTINELS=$REMAINING  (target: 0)"
[ "$REMAINING" -eq 0 ] || echo "BLOCK: $REMAINING sentinel markers remaining"
```

Output target for the cloned spoke (all checks must pass):
- `UNFILLED_PLACEHOLDERS=0`
- Sum of `actual=N` rows matches §Closure status `CLOSED_COUNT`
- `TEMPLATE_CROSSLINK_OK=0`
- `HUB_CROSSLINK_OK=0`
- `REMAINING_SENTINELS=0`

If any check fails, the spoke is **not ready to commit** — fix the placeholder row and re-run.

---

## End-of-Spoke cloning contract

When you clone this template into `docs/PHASE6_TASK{N}_<DOMAIN>_AUDIT.md`, you commit to the following 5-step contract:

1. **Replace all `{{...}}` placeholders.** Run `grep -cE '\{\{[A-Z_]+\}\}' docs/PHASE6_TASK{N}_*.md` → must be 0 before commit.
2. **Update §Verified footer** with reconcile date + ACTUAL_HEAD value + cross-link to `docs/template_sweep.md`.
3. **Add yourself to Hub-linkage §Sibling Spokes** (insert as a new bullet pointing back to the cloned filename).
4. **Link back to `docs/template_sweep.md` directly** — the cloned instance links to the template (NOT to the prior parent — all cloned instances are siblings of each other).
5. **Commit as `docs/<name>.md` doc-only pathspec** unless bundling drive-by code fixes (in which case the companion code commits must cite this doc by filename in their commit messages).

A cloned spoke is **concrete** (CR B4 bar) when:
- All 5 self-validation checklist items pass (`UNFILLED_PLACEHOLDERS=0`, Sign-off counts match, cross-links OK, no sentinel markers)
- §Hub-linkage lists both the Hub and at least one sibling Spoke
- §Verified footer has a real `RECONCILE_DATE` and `ACTUAL_HEAD` value
