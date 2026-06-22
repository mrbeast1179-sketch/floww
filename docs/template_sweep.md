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
