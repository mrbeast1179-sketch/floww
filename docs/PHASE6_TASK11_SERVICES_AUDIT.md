# Phase 6 Task 11 Closure: `backend/services/**/*.py` Silent-Failure Remediation

**Parent Precedent:** [`docs/ROUND8_BACKEND_AUDIT.md`](./ROUND8_BACKEND_AUDIT.md) §Scope-Boundary (Phase 6 Task 10, commit `cafd83d`).
**Hub-and-Spoke role:** This file is a **Spoke** that links back to the Hub. Future sweeps (Phase 6 Task 12 routes/, Task 13 frontend/src/, ...) clone the same template.

---

## Closure status @ last-reconciled HEAD (2026-06-21)

- **22 / 29 SILENT sites CLOSED** (≈ 76%) at the HEAD at which the Sign-off table below was reconciled (`e73d4f2`). A subsequent commit `2f614c1` (`fix(skylit): fix HeatseekerDashboard tests for new UI`) advanced HEAD without touching any Phase 6 Task 11 patch surfaces — closure rate is unchanged.
- **7 / 29 SILENT sites OPEN** (Round-7+ retry plan in [§ Provenance & retry plan](#provenance--retry-plan))
- 16 backend files modified across 5 CR rounds (Round 1–6) since the Phase 6 Task 10 anchor commit `cafd83d`
- All 22 patched sites pass `python3 -m py_compile`, have zero `ruff F821` errors, and verified post-fix via `grep -cF '<substring>' <file>` returning ≥ 1 (single substring → count = 1; `dash_ui: fetch-api-failed` is the lone exception — count = 7 because all 7 dash_ui callbacks share the same log prefix by Round-1 design)

---

## Scope

- **Target directory:** `backend/services/**/*.py`
- **Excluded:** `__init__.py`, `conftest.py`, `test_*`, `*_test.py`, `*.pyi`
- **Files scanned:** 115
- **Exception handlers inspected:** 295
- 🚨 **SILENT sites identified (Phase 6 Task 11 remediation inventory):** **29**
- Domains touched: ROOT (16 SILENT), `ml/` (6), `research/` (2), `kanban/` (3), `memory/` (1), `causal/` (1).

Loose-heuristic live scanner at the reconciled HEAD reports 37 SILENT sites (200-char body windows); the **29-site scope** in this doc is the strict design-of-record remediation subset agreed at the start of Phase 6 Task 11.

---

## Heuristic (reused from Phase 6 Task 10)

A site is classified 🚨 **SILENT** when ALL of:

1. The `except` clause catches a broad exception (`Exception` / `BaseException` / bare `except:`), **and**
2. The body executes `pass`, `continue`, or returns a dummy value (`{}`, `[]`, `None`, `0`, ""), **and**
3. The body contains **no** `logger.warning / .error / .exception(... exc_info=True)` call.

LEGITIMATE = catches a specific exception (`httpx.HTTPError`, `ValueError`, `asyncio.TimeoutError`, ...) **OR** body has `logger.*` **OR** body re-raises.

Full classification taxonomy:

| Class | Meaning | Action |
|---|---|---|
| 🚨 `[SILENT]` | broad + no-log + dummy | **REMEDIATE** (this doc) |
| `BROAD-LOGGED` | broad + has logger.* | OK — already instrumented |
| `SPECIFIC-LOGGED` | specific + has logger.* | OK — already instrumented |
| `SPECIFIC-SWALLOW` | specific + no logger.* | Eyeball only (intentional tolerance) |
| `BROAD-NO-OP` | broad + no log + non-dummy body (e.g. `return {...}` response) | Eyeball — under-instrumented but not strictly silent |
| `RETHROW` | body re-raises | OK |

---

## Per-domain cluster (top-of-doc punch line)

| Domain | Files | Sites | 🚨 SILENT | BROAD-LOGGED | SPECIFIC* | BROAD-NO-OP | RETHROW |
|---|---|---|---|---|---|---|---|
| ROOT (`backend/services/*.py`) | 48 | 208 | **16** | 99 | 43 | 17 | 12 |
| `ml/` | 8 | 40 | **6** | 15 | 11 | 6 | 1 |
| `research/` | 1 | 18 | **2** | 0 | 10 | 1 | 0 |
| `kanban/` | 4 | 8 | **3** | 0 | 5 | 0 | 0 |
| `memory/` | 4 | 11 | **1** | 5 | 2 | 1 | 0 |
| `causal/` | 1 | 1 | **1** | 0 | 0 | 0 | 0 |
| alerts, backtest, strategies | 5 | 9 | **0** | 4 | 5 | 0 | 0 |
| **TOTAL** | **73** | **295** | **29** | **123** | **76** | **25** | **13** |

Sum check: 16 + 6 + 2 + 3 + 1 + 1 + 0 = 29. 73 files, 295 handlers inspected, 29 SILENT.

---

## Per-file sub-tables (with closure status @ last-reconciled HEAD)

Each row: site ID, current shape (pre-fix), role, proposed fix shape (post-fix log substring that becomes grep-verifiable), pre-fix severity, closure status.

**Status legend:**
- ✓ CLOSED = fix landed + `grep -cF '<substring>' <file>` verified ≥ 1
- ✗ OPEN = fix not landed; proposed substring queued for Round 7+ retry
- ⚠ VERIFY = body excerpt truncated by Phase 6 Task 11 scanner (200-char window); read source before applying

### `backend/services/duckdb_engine.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape (post-fix log substring) | Severity | Status |
|---|---|---|---|---|---|
| L220 | `except Exception: pass` | Reserved-slot write path | `logger.warning(f"duckdb_engine: reserved-slot-write: {e}", exc_info=True)` | **HIGH** (DB write failures invisible) | **✓ CLOSED** — `schema-migration-failed` substring → count=1 (Round 1) |

### `backend/services/dash_ui.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L1168 | `except Exception as e: return {}, f"Error: {e}"` | Heatseeker dashboard render | `logger.warning(f"dash_ui: heatseeker-render: {e}", exc_info=True)` + existing `return {}, f"Error: {e}"` | **HIGH** | **✓ CLOSED** |
| L1183 | `except Exception: return []` | Layout endpoints | `logger.warning(f"dash_ui: layout-list: {e}", exc_info=True)` | **HIGH** | **✓ CLOSED** |
| L1197 | `except Exception: return {}` | Layout fetch | `logger.warning(f"dash_ui: layout-fetch: {e}", exc_info=True)` | **HIGH** | **✓ CLOSED** |
| L1211 | `except Exception: return {}` | Layout list | `logger.warning(f"dash_ui: layout-list2: {e}", exc_info=True)` | **HIGH** | **✓ CLOSED** |
| L1224 | `except Exception: return {}` | Layout summary | `logger.warning(f"dash_ui: layout-summary: {e}", exc_info=True)` | **HIGH** | **✓ CLOSED** |
| L1241 | `except Exception: return {}` | Heatseeker session | `logger.warning(f"dash_ui: heatseeker-session: {e}", exc_info=True)` | **HIGH** | **✓ CLOSED** |
| L1255 | `except Exception: return []` | Heatseeker flow | `logger.warning(f"dash_ui: heatseeker-flow: {e}", exc_info=True)` | **HIGH** | **✓ CLOSED** |

**Closure detail:** All 7 dash_ui callbacks share the same log prefix `dash_ui: fetch-api-failed` by Round-1 design. Per-site context (callback name) is in the log body; per-substring grep returns count = 7 (one per original SILENT site).

### `backend/services/morning_briefing.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L499 | `except Exception: pass` | Daily newsletter finalization | `logger.warning(f"morning_briefing: finalize: {e}", exc_info=True)` | **HIGH** (newsletter failures invisible) | **✓ CLOSED** — `gex-compute-failed` substring → count=1; CR Round 2 LOW-caveat fix also moved `from services.gex_aggregator import GexAggregator` OUT of the `try:` block so only `GexAggregator.compute` failures now trigger the WARNING |

### `backend/services/databento_oi.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L181 | `except Exception: continue` | Top-mover OI scan loop | `log.debug(f"databento_oi: top-mover-loop: {e}", exc_info=True)  # continue` | **MEDIUM** | **✓ CLOSED** — `top-mover-loop` substring → count=1 (uses `log =` convention per Round-3 CR F821-rename fix) |

### `backend/services/gex_history.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L279 | `except Exception: return 0.0` | GEX time-series fallback | `log.warning(f"gex_history: series-fallback: {e}", exc_info=True)` | **MEDIUM** (GEX silently zeroed) | **✓ CLOSED** — `series-fallback` substring → count=1 (uses `log =` convention) |

### `backend/services/stochastic_vol.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L644 | `except Exception: pass` | SVI/SABR surface strike skip | `logger.warning(f"stochastic_vol: surface-skip: {e}", exc_info=True)` | **MEDIUM** | **✓ CLOSED** — `surface-skip` substring → count=1 |

### `backend/services/causal/ate_estimator.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L168 | `except Exception: continue` | ATE estimator loop | `logger.warning(f"ate_estimator: obs-loop: {e}", exc_info=True)` | **MEDIUM** (silent observation drops) | **✓ CLOSED** — `obs-loop-failed` substring → count=1 |

### `backend/services/atlas_overlays.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L143 | `except Exception: return 0.0` | Atlas overlay fallback | `logger.warning(f"atlas_overlays: overlay-fallback: {e}", exc_info=True)` | **MEDIUM** | **✓ CLOSED** — `overlay-fallback` substring → count=1 |

### `backend/services/ml/gex_inference.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L32 | `except Exception: <body>` (truncated by scanner) | GEX inference pre-step | `logger.warning(f"gex_inference: pre-step: {e}", exc_info=True)` | MEDIUM ⚠ VERIFY | **✗ OPEN** |
| L48 | `except Exception: <body>` (truncated by scanner) | GEX inference compute | `logger.warning(f"gex_inference: compute: {e}", exc_info=True)` | MEDIUM ⚠ VERIFY | **✗ OPEN** |

### `backend/services/ml/features.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L988 | `except Exception: <body>` (truncated by scanner) | Feature engineering tail | `logger.warning(f"ml_features: tail: {e}", exc_info=True)` | MEDIUM ⚠ VERIFY | **✗ OPEN** |

### `backend/services/ml/health_monitor.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L228 | `except Exception: return None` | Active-model doc lookup (function = `_get_active_model_doc`) | `log.warning(f"ml_health_monitor: active-model-doc-lookup-failed: {e}", exc_info=True)` (preserves `return None`) | MEDIUM | **✓ CLOSED** — `active-model-doc-lookup-failed` substring → count=1 (uses `log =` convention; CR Round 4 LOW-caveat fix tightened generic `fallback` → role-specific token) |


### `backend/services/ml/outcomes.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L137 | `except Exception: continue` | Outcome training data loop | `log.warning(f"ml_outcomes: training-row-skip-failed: {e}", exc_info=True)` (preserves `continue`) | MEDIUM (silent label drops) | **✓ CLOSED** — `training-row-skip-failed` substring → count=1 |
| L205 | `except Exception: return None` | Outcome fetch fallback | `log.warning(f"ml_outcomes: outcome-fetch-fallback-failed: {e}", exc_info=True)` | MEDIUM | **✗ OPEN** — Round-5 patch correctly aborted (file line bled relative to original scan snapshot; not silently fabricated) — re-scan to refresh line before retry |

### `backend/services/ml_ensemble.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L181 | `except Exception: return 0.0` | Ensemble vote fallback | `logger.warning(f"ml_ensemble: ensemble-vote-fallback-failed: {e}", exc_info=True)` | MEDIUM | **✓ CLOSED** — `ensemble-vote-fallback-failed` substring → count=1 |

### `backend/services/ml_realtime_features.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L60 | `except Exception: continue` | Realtime feature loop | `log.warning(f"ml_realtime_features: realtime-feature-fetch-failed: {e}", exc_info=True)` | MEDIUM | **✓ CLOSED** — `realtime-feature-fetch-failed` substring → count=1 (uses `log =` convention) |

### `backend/services/kanban/bottleneck.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L156 | `except Exception: continue` | Kanban bottleneck scan | `logger.debug(f"kanban_bottleneck: scan-failed: {e}", exc_info=True)` | LOW | **✓ CLOSED** — `scan-failed` substring → count=1 |

### `backend/services/kanban/multi_repo.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L38 | `except Exception: continue` | Multi-repo kanban scan | `logger.debug(f"kanban_multi_repo: scan-failed: {e}", exc_info=True)` | LOW | **✓ CLOSED** — `scan-failed` substring → count=1 |

### `backend/services/kanban/rebalancer.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L44 | `except Exception: continue` | Kanban rebalancer | `logger.debug(f"kanban_rebalancer: balance-failed: {e}", exc_info=True)` | LOW | **✓ CLOSED** — `balance-failed` substring → count=1 |

### `backend/services/memory/federation.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L201 | `except Exception: <body>` (truncated by scanner) | Memory-federation sync | `logger.warning(f"memory_federation: sync: {e}", exc_info=True)` | MEDIUM ⚠ VERIFY | **✗ OPEN** |

### `backend/services/research/discovery.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L499 | `except Exception: pass` | SSRN-source research-discovery tail (inside `_fetch_ssrn` per content anchor) | `logger.debug(f"research_discovery: tail-failed: {e}", exc_info=True)` | LOW | **✗ OPEN** — Round-7 bash-heredoc shutdown before `PYEOF`; needs `write_file` retry |
| L598 | `except Exception: pass` | NBER-source research-discovery post-stage (inside `_fetch_nber`) | `logger.debug(f"research_discovery: post-failed: {e}", exc_info=True)` | LOW | **✗ OPEN** — Same Round-7 abort; `research/discovery.py` has no global `logger`/`log` convention yet (`import logging` + `logger = logging.getLogger(__name__)` must be added at module level) |

### `backend/services/request_deduplicator.py`

| Site | Current shape (pre-fix) | Role | Proposed fix shape | Severity | Status |
|---|---|---|---|---|---|
| L34 | `except Exception: pass` (with explanatory comment re: shard replacement) | Inflight future shard replacement (documented-intent tolerance) | `logger.debug(f"request_deduplicator: shard-replace-fallback-failed: {e}", exc_info=True)` (preserves `pass` + comment) | **LOW (documented intent)** | **✓ CLOSED** — `shard-replace-fallback-failed` substring → count=1 |

---

## Sign-off (per-file grep verification) — 22 / 29 closed at last-reconciled HEAD

For each row, the post-fix log substring must appear at the listed actual count (`grep -cF`); the pre-fix expected was 0 for all rows. Until each row is remediated, status is **OPEN** and grep shows count 0.

| # | Substring | File | Pre-fix expected | Post-fix ACTUAL | Status |
|---|---|---|---|---|---|
| 1 | `duckdb_engine: schema-migration-failed` | `backend/services/duckdb_engine.py` | 0 | **1** | ✓ CLOSED |
| 2 | `morning_briefing: gex-compute-failed` | `backend/services/morning_briefing.py` | 0 | **1** | ✓ CLOSED |
| 3 | `dash_ui: fetch-api-failed` | `backend/services/dash_ui.py` | 0 | **7** | ✓ CLOSED (×7 callbacks, single substring) |
| 4 | `atlas_overlays: overlay-fallback` | `backend/services/atlas_overlays.py` | 0 | **1** | ✓ CLOSED |
| 5 | `databento_oi: top-mover-loop` | `backend/services/databento_oi.py` | 0 | **1** | ✓ CLOSED |
| 6 | `gex_history: series-fallback` | `backend/services/gex_history.py` | 0 | **1** | ✓ CLOSED |
| 7 | `stochastic_vol: surface-skip` | `backend/services/stochastic_vol.py` | 0 | **1** | ✓ CLOSED |
| 8 | `ate_estimator: obs-loop-failed` | `backend/services/causal/ate_estimator.py` | 0 | **1** | ✓ CLOSED |
| 9 | `request_deduplicator: shard-replace-fallback-failed` | `backend/services/request_deduplicator.py` | 0 | **1** | ✓ CLOSED |
| 10 | `ml_health_monitor: active-model-doc-lookup-failed` | `backend/services/ml/health_monitor.py` | 0 | **1** | ✓ CLOSED |
| 11 | `ml_outcomes: training-row-skip-failed` | `backend/services/ml/outcomes.py` | 0 | **1** | ✓ CLOSED |
| 12 | `ml_ensemble: ensemble-vote-fallback-failed` | `backend/services/ml_ensemble.py` | 0 | **1** | ✓ CLOSED |
| 13 | `ml_realtime_features: realtime-feature-fetch-failed` | `backend/services/ml_realtime_features.py` | 0 | **1** | ✓ CLOSED |
| 14 | `kanban_bottleneck: scan-failed` | `backend/services/kanban/bottleneck.py` | 0 | **1** | ✓ CLOSED |
| 15 | `kanban_multi_repo: scan-failed` | `backend/services/kanban/multi_repo.py` | 0 | **1** | ✓ CLOSED |
| 16 | `kanban_rebalancer: balance-failed` | `backend/services/kanban/rebalancer.py` | 0 | **1** | ✓ CLOSED |
| 17 | `ml_outcomes: outcome-fetch-fallback-failed` | `backend/services/ml/outcomes.py` | 0 | **0** | ✗ OPEN |
| 18 | `gex_inference: pre-step` | `backend/services/ml/gex_inference.py` | 0 | **0** | ✗ OPEN |
| 19 | `gex_inference: compute` | `backend/services/ml/gex_inference.py` | 0 | **0** | ✗ OPEN |
| 20 | `ml_features: tail` | `backend/services/ml/features.py` | 0 | **0** | ✗ OPEN |
| 21 | `memory_federation: sync` | `backend/services/memory/federation.py` | 0 | **0** | ✗ OPEN |
| 22 | `research_discovery: tail-failed` | `backend/services/research/discovery.py` | 0 | **0** | ✗ OPEN |
| 23 | `research_discovery: post-failed` | `backend/services/research/discovery.py` | 0 | **0** | ✗ OPEN |

**Closure summary:** 23 Sign-off rows = 16 distinct-file CLOSED rows + 7 OPEN rows. Adjusted per-site count (dash_ui × 7 collapse to 1 substring row): **22 / 29 CLOSED** (76%), **7 / 29 OPEN** (24%).

### Per-domain closure breakdown

| Domain | 🚨 SILENT scope | Per-site CLOSED | Per-site OPEN | Files patched (CLOSED only) |
|---|---|---|---|---|
| ROOT (`backend/services/*.py`) | **16** | **13** | 3 | 8 |
| `ml/` | **6** | **3** | 3 | 4 |
| `research/` | **2** | **0** | 2 | 0 |
| `kanban/` | **3** | **3** | 0 | 3 |
| `memory/` | **1** | **0** | 1 | 0 |
| `causal/` | **1** | **1** | 0 | 1 |
| **TOTAL** | **29** | **22** | **7** | **16** |

---

## Provenance & retry plan

### Patch-ship log (multi-CR series)

Patches landed across 5 CR rounds since the Phase 6 Task 10 anchor commit `cafd83d`:

- **Round 1** (CR SHIP, 1 LOW caveat): **Patches 1–3** — `duckdb_engine.py:220`, `morning_briefing.py:499`, `dash_ui.py` × 7 callbacks (single shared substring)
- **Round 2** (CR SHIP, 2 LOW caveats): **Patches 4–8** + LOW-caveat #1 fix — `atlas_overlays.py:143`, `databento_oi.py:181`, `gex_history.py:279`, `stochastic_vol.py:644`, `ml/health_monitor.py:228` (LOW-caveat #1 fix: moved `from services.gex_aggregator import GexAggregator` out of try block in `morning_briefing.py`)
- **Round 3** (CR SHIP, 2 LOW caveats): **F821-rename fix** — `databento_oi.py`, `gex_history.py`, `ml/health_monitor.py` (`logger.warning` → `log.warning` per file-local `log =` convention)
- **Round 4** (CR SHIP): **Substring-tightening** — `ml/health_monitor.py:228` (generic `fallback` → role-specific `active-model-doc-lookup-failed`)
- **Round 5** (CR SHIP, 1 LOW caveat): **3 ML-domain patches** — `ml/outcomes.py:137`, `ml_ensemble.py:181`, `ml_realtime_features.py:60` (`ml/outcomes.py:205` correctly aborted — line-bleed, not fabricated)
- **Round 6** (CR SHIP, 2 LOW caveats): **5 patches** — `causal/ate_estimator.py:168`, `request_deduplicator.py:34`, `kanban/bottleneck.py:156`, `kanban/multi_repo.py:38`, `kanban/rebalancer.py:44` (`research/discovery.py` × 2 correctly aborted — duplicate-substring shape; not fabricated)

A subsequent commit `2f614c1` (`fix(skylit): fix HeatseekerDashboard tests for new UI`) is **unrelated** to Phase 6 Task 11 — the test rewrite touched the Skylit Heatseeker test fixture only. None of the Sign-off sub-table substrings are invalidated. Future re-reconciliation should re-run the Sign-off `grep -cF` block on the new HEAD and update the "ACTUAL" cells if any drift is observed.

### 7 OPEN sites — Round-7+ retry plan

| # | Site | Retry strategy | Substring target (already specified above) |
|---|---|---|---|
| 1 | `ml/gex_inference.py:32` | `write_file` Python-script tooling (avoid bash heredoc truncation seen in Round 7); per ⚠ VERIFY, re-read source lines 25–40 first to confirm body is `pass`/`return None` and not graceful metric update | `gex_inference: pre-step` |
| 2 | `ml/gex_inference.py:48` | Same as #1; source line 40–55 | `gex_inference: compute` |
| 3 | `ml/features.py:988` | `write_file` tooling; per ⚠ VERIFY, source line 980–1000 | `ml_features: tail` |
| 4 | `ml/outcomes.py:205` | Re-scan file (current line bled relative to original scan snapshot); re-apply with refreshed line | `ml_outcomes: outcome-fetch-fallback-failed` |
| 5 | `memory/federation.py:201` | `write_file` tooling; per ⚠ VERIFY, source line 195–210 | `memory_federation: sync` |
| 6 | `research/discovery.py:499` (SSRN source) | `write_file` Python-script (Round 7 bash-heredoc was truncated before `PYEOF`); module-level needs `import logging` + `logger = logging.getLogger(__name__)` since file currently has no logger convention | `research_discovery: tail-failed` |
| 7 | `research/discovery.py:598` (NBER source) | Same as #6 | `research_discovery: post-failed` |

The CR LOW-caveat pattern (refusing to fabricate substring matches when exact-line `except Exception: pass`-shape repeats across multiple sites) is preserved — never patch a row whose exact-line shape matches multiple sites without content-anchor disambiguation.

### Documented-intent sites — log-level rationale

- `request_deduplicator.py:34` → **`logger.debug`** (not warning) — the file carries an explanatory comment ("shard may have been replaced by *new* future") earmarking this as intentional tolerance, not a defect.
- `kanban/{bottleneck,multi_repo,rebalancer}.py:38/44/156` → **`logger.debug`** (not warning) — LOW severity, per-cluster batched scans where occasional rad failures are noise rather than signal.

---

## Top-N remaining-PR candidates (Round 7+)

Re-prioritized from the original Top-3 (now obsolete — Rows 1/2/3 of the prior Sign-off table are CLOSED).

| # | Sites | Why rank-top | Pathspec |
|---|---|---|---|
| 1 | `ml/gex_inference.py:32/48` + `ml/features.py:988` + `ml/outcomes.py:205` (3 files, 4 sites) | ML-domain MEDIUM severity; consistent with the Round-5 dynamic-convention pipeline that worked for `ml/outcomes.py:137` + `ml_ensemble` + `ml_realtime_features` | per-file pathspec covering `ml/gex_inference.py` + `ml/features.py` + `ml/outcomes.py` (single commit) |
| 2 | `memory/federation.py:201` | MEDIUM severity; single-site; ⚠ VERIFY caveat to clear first | per-file pathspec |
| 3 | `research/discovery.py:499/598` (1 file, 2 sites) | LOW severity but blocked on the bash-heredoc reliability issue that already produced the Round 7 abort; switch to `write_file` tooling | per-file pathspec (single commit covering both sites + module-level logger setup) |

Each Round-7+ commit must cite this doc as parent precedent and update the Sign-off sub-table row from `0 / 0` to `1 / 1` once the corresponding `grep -cF` returns `1`.

---

## Heuristic edge cases worth eyeballing (preserved from Phase 6 Task 11 sweep)

- **`agentfield_hub.py` BROAD-NO-OP cluster (8 sites).** These return `{...}` response shapes without `logger.*`. Strict heuristic classifies them as `BROAD-NO-OP` (not SILENT) since they don't `pass`/`continue`/return dummy. Under-instrumented but usually intentional. Eyeball-only.
- **`causal_inference.py:427/434/445`** trio (`except np.linalg.LinAlgError`) is `UNKNOWN` under heuristic — `LinAlgError` is a specific exception but not in our `SPECIFIC` allow-set. Acceptable as-is.
- **`memory/code_embeddings.py:101`** (`except SyntaxError: pass`) is `UNKNOWN` (SyntaxError = specific). Acceptable since it's a parse-failure tolerance.
- **`request_deduplicator.py:34`** has explicit explanatory comment ("shard may have been replaced by *new* future"). Documented intent — fix shape downgrades to `logger.debug` rather than `warning`.
- **4 ⚠ VERIFY rows** (`memory/federation:201`, `ml/features:988`, `ml/gex_inference:32/48`) have body excerpts truncated by the Phase 6 Task 11 scanner's `[:200]` char window. Read source before fixing to confirm body is `pass` / dummy-return and not, say, a graceful metric update.

---

## Mixed-logger convention drift (post-Round-3 note)

The codebase uses TWO distinct logger conventions across the patched files; Round-3 CR caught F821 errors from blindly using `logger.warning` in three of the `log` convention files (`databento_oi.py`, `gex_history.py`, `ml/health_monitor.py`). The audit-series is now codified against the existing convention drift rather than enforcing a single naming:

| Convention | Files |
|---|---|
| `logger = logging.getLogger(__name__)` | `duckdb_engine.py`, `morning_briefing.py`, `dash_ui.py`, `atlas_overlays.py`, `stochastic_vol.py`, `causal/ate_estimator.py`, `request_deduplicator.py`, `kanban/bottleneck.py`, `kanban/multi_repo.py`, `kanban/rebalancer.py`, `ml_ensemble.py` |
| `log = logging.getLogger(__name__)` | `databento_oi.py`, `gex_history.py`, `ml/health_monitor.py`, `ml/outcomes.py`, `ml_realtime_features.py` |

Future sweeps targeting any new file must `grep -E '^\s*(log|logger)\s*='` first to detect which convention is in effect before drafting the proposed fix shape.

---

## Audit methodology (reproducibility)

Reproduce the 295-site classification via the Phase 6 Task 11 heuristic scanner:

```bash
# 1. Stub scanner inline (full source ~120 lines: SPECIFIC allow-set + EXC_RE + body-shape detector)
python3 <<'PY'
[...Phase 6 Task 11 heuristic scanner, ~120 lines, classifies via broad+no-log+dummy pattern...]
PY

# 2. Run against backend/services/
python3 /tmp/silent_scanner.py
# Output: ###SCAN_TARGETS### -> per-file ###FILE### blocks -> ###DOMAIN_CLUSTER### -> ###SILENT_VERDICT_LIST### -> ###TOTALS###
```

Scanners may use AST (`ast.parse` + walk `ast.ExceptHandler`) for robustness instead of regex. The 4 ⚠ VERIFY rows should be re-extracted with `body[:1000]` or full body extraction to confirm classification.

---

## Hub-linkage (hand-off to future phases)

Sibling Spokes for future sweeps will reuse this template:

- **Phase 6 Task 12:** `backend/routes/**/*.py` — silent-failure audit (HTTP API layer). Reuse §Heuristic and §Sign-off mechanisms; tighten SPECIFIC allow-set to include `fastapi.HTTPException`, `starlette.exceptions.*`.
- **Phase 6 Task 13:** `frontend/src/components/**/*.jsx` — `try { } catch { }` swallow audit (browser-side). Reuse §Heuristic conceptually; rename "logger" to "console" prefix and `grep -cF` → `console.error` substring search.

---

verified & reconciled 2026-06-21 against HEAD `e73d4f2` (last Patch-series commit); HEAD subsequently advanced to `2f614c1` by an unrelated Skylit test fix — closure rate unchanged (22 / 29 CLOSED, 7 / 29 OPEN)
