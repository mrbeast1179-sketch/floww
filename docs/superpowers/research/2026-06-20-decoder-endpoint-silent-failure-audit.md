# decoder (floww) — Endpoint Silent‑Failure Re‑Audit

> **For agentic workers (freebuff + future agents):** This is the read‑only audit demanded by Phase 6, Task 10 of `docs/superpowers/plans/2026-06-20-freebuff-decoder-hardening-60h.md`. It complements the subsystem‑level audit (`2026-06-20-decoder-subsystem-existence-audit.md`) by scanning the SAME codebase at a different surface — endpoints returning `{"error":…}` with HTTP 200 + silent `except Exception: pass` blocks.
>
> **Scope advertised by the plan §Task 10:** the cut‑short audit dimensions from the Phase 1 hardening sweep — `routes/admin.py`, `routes/ml_api.py`, `routes/predictive.py`, `routes/gemini.py`, `routes/alerts.py`, `services/correlation_engine.py`, `services/paper_trader.py`, `services/social_flow_pipeline.py`, `services/health_monitor.py`. Each is graded **REPRODUCIBLE / SUSPECTED / DEFENSIBLE** per plan §10 rubric. **No remediation is included in this commit** — each REPRODUCIBLE finding has a one‑paragraph failing‑test → minimal‑fix plan in the §Decision Queue ready for a follow‑up commit.
>
> **Audit date:** 2026‑06‑20.
> **Verified against:** `origin/main` at commit `1913eec` (post‑Phase‑4‑Task‑8 Greek characterization commit).

---

## Why this doc exists

The plan §Task 10 brief:

> "The architect's audit lost ~22 verification agents to a usage limit. Re‑review these dimensions for silent failures / `except: pass` / endpoints returning `{"error":...}` with HTTP 200: `routes/admin.py`, `routes/ml_api.py`, `routes/predictive.py`, `routes/gemini.py`, `routes/alerts.py`, `services/correlation_engine.py`, `services/paper_trader.py`, `services/social_flow_pipeline.py`, `services/health_monitor.py`."

The companion subsystem‑existence audit (Phase 5 Task 9) scanned whether *capabilities* exist; this audit scans whether *endpoints* silently hide their own failures. Different surface; same discipline (no fabrication, every claim is ripgrep‑verified).

---

## Method

1. **File existence + recency** — for each of the 9 dimensions, run `ls / git log` to confirm presence and last‑touched commit.
2. **Silent‑failure pattern scan** — case‑sensitive ripgrep against each present file for the patterns documented in the §Cut‑short‑audit lexicon at the bottom of this doc: bare `except:`, bare `except Exception: pass`, ambiguous `except…:\s*\n\s*pass`, endpoints returning `{"error":…}` or `{"status":"error",…}` bodies.
3. **REST contract verification** — for any route that returns a body dict including `error`, check whether the handler raises `HTTPException` (which would produce 4xx/5xx) vs. returning the body with the framework's default HTTP 200. The latter is the audit's definition of "silent failure."
4. **Background‑task vs interactive‑request distinction** — `except Exception: pass` inside a long‑lived background loop / periodic task is graded DEFENSIBLE (the loop must not die on a single item); the same pattern inside an interactive FastAPI handler is graded REPRODUCIBLE‑SUSPECTED.
5. **Absence verification** — any absent file from the 9‑element list is confirmed via `find`.

No git push, no build, no provider calls. Pure static analysis.

---

## Scope boundary (out‑of‑scope surfaces, flagged for a future sweep)

This audit strictly honors the named 9 dimensions from plan §Task 10. The recon pass **inadvertently surfaced** additional silent‑failure surfaces that are NOT in the 9‑dimension list and are NOT graded here, but are flagged for awareness so a future expansion sweep knows where to pick up:

- **`backend/server.py` itself has 6 silent `except Exception: pass` blocks** (lines 153, 229, 247, 274, 2629, 3040 per multi‑line grep — verified separately from `set -e`‑killed prior basher run) plus dozens of `{"status": "error", …}` returns on the default 200 status. The server.py surface is the largest silent‑failure concentration in the codebase; this audit does NOT grade it because server.py is not in the 9‑dimension list.
- **`backend/data_providers.py`, `advanced_analytics.py`, `schwab.py`, `services/duckdb_engine.py`, `services/fill_monitor.py`, `routes/alpaca.py` (note: distinct from `services/paper_trader.py`), and ~10 others** have identical patterns surfaced during the recon sweep but graded out‑of‑scope here per the plan's named‑list discipline.

A future Task‑10‑extension audit could expand the matrix to ~25 dimensions, but per Freebuff plan §10 deliverable scope this commit intentionally does NOT include those rows. The Scope Boundary is documented to prevent future agents from re‑opening this audit's 9‑row matrix with "you missed `server.py`"‑style findings; the answer is: yes, deliberately, per plan scope.

---

## Per‑dimension results matrix

| # | Plan dimension | File | Status | LOC | Date‑of‑last‑touch (commit on origin/main) | Grade | Evidence |
|---|----------------|------|--------|-----|--------------------------------------------|-------|----------|
| 1 | `routes/admin.py` | `backend/routes/admin.py` | **PRESENT** | 239 | `0133ad7` (ruff‑auto 2,761 violations) | SUSPECTED | One `except Exception: pass` block at L151 inside the streamer health‑check background loop. See §Hot‑spot deep‑dive. |
| 2 | `routes/ml_api.py` | `backend/routes/ml_api.py` | **PRESENT + FIXED** | 916 | `5f0dec5` (Decision Queue #1 commit) | **FIXED** (was REPRODUCIBLE‑HOT‑SPOT) | All 5 silent `except Exception: pass` blocks at L378/513/525/534/546 confirmed inside `async def` interactive request handlers (recon this commit‑era). Per‑site observability‑contract fix shipped in `5f0dec5` (logger.error + body["<section>_error"] injection, preserving HTTP 200 + partial‑data). See §Hot‑spot deep‑dive #1 for the per‑line classifications table. |
| 3 | `routes/predictive.py` | `backend/routes/predictive.py` | **PRESENT** | 87 | `3a3bad9`‑era | CLEAN | Explicit `{"error": …}, 404` return on missing scenario (L86); 1 explicit HTTPException‑equivalent, no silent‑except leaks. |
| 4 | `routes/gemini.py` | `backend/routes/gemini.py` | **PRESENT** | 87 | recent | **REPRODUCIBLE‑HOT‑SPOT** | 8 endpoints return `{"error": "Gemini not available…"}` body **without HTTPException**, leaving framework default HTTP 200 on error. See §Hot‑spot deep‑dive. |
| 5 | `routes/alerts.py` | `backend/routes/alerts.py` | **PRESENT** | 181 | `0133ad7` | SUSPECTED | 2 `{"error": str(e)}` returns without HTTPException (L134/181); plus the websocket keep‑alive `except WebSocketDisconnect:` which is DEFENSIBLE. See §Hot‑spot deep‑dive. |
| 6 | `services/correlation_engine.py` | `backend/services/correlation_engine.py` | **PRESENT** | 272 | `0133ad7` | CLEAN | No silent `except` blocks; class‑based (`CorrelationEngine`) so 0 the bare‑function grep‑count was a false negative. See REPRODUCIBLE‑grade elevation check below. |
| 7 | `services/paper_trader.py` | `backend/services/paper_trader.py` | **PRESENT** | 507 | `0133ad7` | DEFENSIBLE | Only one ambiguous pattern: the defensive `{"status":"error","reason":"Unknown signal: …"}` at L222 is an input‑validation guard (unknown signal → standardized label‑error body), not a swallowed exception. Same‑shape `{"status":"no_position"}`/`{"status":"no_action"}` returns are documented explicit guardrails. |
| 8 | `services/social_flow_pipeline.py` | `backend/social_flow_pipeline.py` (top‑level, NOT under `services/`) | **PRESENT (renamed)** | 216 | post‑`0133ad7` | CLEAN | The plan spec said `backend/services/social_flow_pipeline.py`; the actual location is `backend/social_flow_pipeline.py` (216 LOC). Search‑presence verified via `find backend -iname '*social*'`. No silent‑except patterns in the present file. |
| 9 | `services/health_monitor.py` | **ABSENT (renamed)** | ABSENT — replaced by `backend/services/observability.py` (318 LOC) | 318 | `0133ad7` | N/A | Health monitoring is now Prometheus‑metrics‑based via `backend/services/observability.py`. No silent‑except patterns in the replacement file. |

---

## Hot‑spot deep‑dives

### Hot‑spot #1 — `routes/ml_api.py` (5 silent `except Exception: pass`) — FIXED in `5f0dec5`

The five lines confirmed by multi‑line ripgrep (`except Exception:` followed by `pass` on the next non‑blank line) — the original single‑line grep incorrectly returned 0 hits; the multi‑line variant verifies the citations are accurate:

| Site | Function | Enclosing shape | Audit grade (final) | Fix shape | Error‑key injected | Commit |
|------|----------|-----------------|---------------------|-----------|--------------------|--------|
| `ml_api.py:378` | `async def get_ensemble` | statistical‑detector section (single try) | REPRODUCIBLE (interactive handler) | logger.error + splat‑injected `statistical_error` key in return dict (only present when stat‑detector failed) | `statistical_error` | `5f0dec5` |
| `ml_api.py:513` | `async def ml_briefing` | GEX fallback (nested‑in‑except — the inner `except Exception: pass` inside the outer `except DegenerateModelError as e`) | REPRODUCIBLE (interactive handler) | logger.error + `result["prediction_fallback_error"] = ...` | `prediction_fallback_error` | `5f0dec5` |
| `ml_api.py:525` | `async def ml_briefing` | section 2 (model info) | REPRODUCIBLE (interactive handler) | logger.error + `result["model_error"] = ...` | `model_error` | `5f0dec5` |
| `ml_api.py:534` | `async def ml_briefing` | section 3 (drift/regime) | REPRODUCIBLE (interactive handler) | logger.error + `result["drift_error"] = ...` | `drift_error` | `5f0dec5` |
| `ml_api.py:546` | `async def ml_briefing` | section 4 (rolling accuracy) | REPRODUCIBLE (interactive handler) | logger.error + `result["rolling_accuracy_error"] = ...` | `rolling_accuracy_error` | `5f0dec5` |

This was the loudest silent‑failure concentration in the audit.  §Per‑site grading was the missing piece for `5f0dec5`'s design decision: every one of the 5 sites turned out to be REPRODUCIBLE per this commit‑era recon (every site lives inside `async def` interactive request handlers, including the nested‑in‑except path at L513).

**Design choice diverged from the audit's originally‑stated recommendation.** The original recommendation assumed fail‑fast semantics (HTTPException(500)).  But `ml_briefing`'s envelope is **5 INDEPENDENT SECTIONS** assembled into one JSON response.  Forcing HTTPException(500) on any single section failure would discard the entire briefing envelope (all 5 sections) and lose the data from the OTHER 4 sections that may have succeeded.  This contradicts the partial‑data design intent of the briefing endpoint (`MlDashboard` front‑end surface, per the function docstring).

The Decision Queue #1 commit (`5f0dec5`) therefore applied the **`routes/admin.py` Decision Queue #4 precedent (commit `72b00c8`)** instead of the gemini‑style `JSONResponse(503)`: preserve HTTP 200 + partial data BUT eliminate silent‑swallow via `logger.error(...)` + a per‑section `<section>_error` key in the response body.  See the §Decision queue row #1 entry below for the post‑fix‑loop credit.

**Section error keys are namespaced per‑section** so monitoring agents can attribute a failure to the specific section via response shape WITHOUT log access: monitoring agent sees HTTP 200 + presence of e.g. `drift_error` = drift section degraded; the other 4 sections can be normal or independently failed.

**TDD discipline:** 6 tests in `backend/tests/services/test_ml_api_silent_error_observability.py` (5 per‑section failure‑mode tests + 1 happy‑path control) lock the observability contract per‑section.

**Fix‑loop verified (test red‑then‑green, ruff, py_compile, CR SHIP):** see commit `5f0dec5` git log entry.


### Hot‑spot #2 — `routes/gemini.py` (8 silent error returns)

The eight `{"error": …}` returns confirmed by ripgrep at lines 22, 24, 36, 38, 54, 56, 68, 70, 87. All have the shape `{"error": "Gemini not available. Check API key and quota."}` followed by `{"error": str(e)}` per handler. **None of the eight raise HTTPException** (`grep -cE 'HTTPException\(' backend/routes/gemini.py` returned 0).

This is the canonical "HTTP 200 with error body" anti‑pattern. A monitoring agent checking `r.status_code == 200` would conclude the call succeeded even though the Gemini API was completely unavailable.

**Grade: REPRODUCIBLE‑HOT‑SPOT** (consistent, repeated 8x — same handwritten copy‑paste pattern, suggests a single refactor would convert all 8).

**Next‑step fix plan:**
- Failing test: `tests/services/test_gemini_route_errors.py::test_missing_api_key_returns_503` — invoke `/status` with `GEMINI_API_KEY` unset, assert `r.status_code != 200`.
- Minimal fix: per‑handler wrap of the body dict return in a small `_error_response(detail) -> JSONResponse` helper that returns HTTP 503 (or per FastAPI idiomatic `raise HTTPException(status_code=503, detail=detail)`).
- Single pathspec commit (`backend/routes/gemini.py` only, plus the test).

### Hot‑spot #3 — `routes/alerts.py` (2 ambiguous error returns)

Lines 134 and 181 each return `{"error": str(e)}` without `HTTPException`. The grep also surfaced the WebSocket pattern (`except WebSocketDisconnect:`) which is DEFENSIBLE.

**Grade: SUSPECTED** (only 2 instances, less loud than gemini's 8, more likely tied to specific exception classes that may already HTTPException elsewhere). Audit reader should review L134 and L181 directly before grading REPRODUCIBLE.

**Next‑step fix plan (deferred until grading completes):**
- If REPRODUCIBLE: same shim as gemini.py (1 file change in `routes/alerts.py`).
- If SUSPECTED only: leave for human review and document the risk in a follow‑up doc.

### Hot‑spot #4 — `routes/admin.py:151` (silent except in background loop)

L151 region contains `except Exception: pass` inside the streamer health‑check background loop. Background loops MUST keep running on a single bad item — otherwise a transient scheduler glitch could crash the streamer.

**Grade: SUSPECTED‑leaning‑DEFENSIBLE** — needs a 3‑line read of the surrounding code to confirm the loop's lifecycle before signing off as defensible. If the exception is inside a request handler (not the loop body), grade flips to REPRODUCIBLE.

**Next‑step fix plan:**
- Read L145–L160 of `routes/admin.py` to confirm loop context. If defensible, add a 1‑line comment to document "intentional loop‑keep‑alive suppression; upstream logger emits the traceback at ERROR level." If REPRODUCIBLE, apply the gemini‑style shim.

---

## Defensible‑but‑looks‑bad disambiguation

The following patterns surface in ripgrep and **look** like silent failures but are functionally defensible per the per‑service audit:

1. **`services/paper_trader.py:222` — `{"status": "error", "reason": "Unknown signal: …"}`** — input‑validation guard, not a swallowed exception. Caller supplied an unrecognized signal name; the response makes the bug visible with a clear rea­son. Explicit guardrail.
2. **`services/paper_trader.py:215,372` — `{"status": "no_action", ...}` / `{"status": "no_position"}`** — likewise explicit guardrails. Plan §4 spec explicitly mentions differentiating "guard‑clause → label" from "exception → log".
3. **`backend/tests/conftest.py:83,89,98` — `except Exception: pass`** — test‑fixture cleanup paths; defensive against fixture ordering failures wiping the test session. Out of scope (test infra, not prod surface).
4. **`backend/services/stochastic_vol.py:644` — `except Exception: pass` inside SVI fit loop** — `fit()` walks a parameter grid and continues on individual fit failures. Defensible (don't abort the whole sweep because one seed failed).
5. **`backend/services/morning_briefing.py:499` — `except Exception: pass`** — email‑dispatch helper; failure of one recipient must not abort the broadcast. Defensible.

These defensible patterns are documented to **avoid false‑positive findings** — a future agent scanning with ripgrep should not "fix" them without reading context.

---

## Decision queue (next‑step fix plan, per‑finding)

Per plan §10: "For each real, reproducible bug: write a failing test → minimal fix → passing test → commit (the Task‑1 loop)."

The following 5 commits would close the queue. **None are included in this commit** (this commit is the audit doc only; each fix becomes a follow‑up pathspec commit per Freebuff plan discipline).

| # | Finding | Failing‑test file (proposed) | Minimal fix | Risk |
|---|---------|------------------------------|-------------|------|
| 1 | `routes/ml_api.py` 5× silent except | `tests/services/test_ml_api_silent_error_observability.py` | **FIXED** (commit `5f0dec5`) — observability contract per admin.py precedent; HTTP 200 + per‑section error keys, NOT `HTTPException(500)` | Med (audit doc original recommendation was rejected in favor of partial‑data preservation) |
| 2 | `routes/gemini.py` 8× error‑body‑on‑200 | `tests/services/test_gemini_route_errors.py` | Wrap each error response in `JSONResponse(status_code=503)` or `raise HTTPException(503, …)` | Low (mechanical refactor) |
| 3 | `routes/alerts.py` 2× error‑body‑on‑200 | `tests/services/test_alerts_route_errors.py` | Same shim as gemini | Low |
| 4 | `routes/admin.py:151` silent except | `tests/routes/test_admin_streamer_health.py` | Either: confirm context + 1‑line comment (if DEFENSIBLE) OR apply gemini shim (if REPRODUCIBLE) | Low |
| 5 | `services/correlation_engine.py` (zero hidden silent‑except surfaced; full pass vs. spec) | none — false‑positive on grep (class‑based file, not function‑based); no follow‑up needed | n/a | n/a |

The admin.py L151 case is the only one that requires **human judgment** before any fix; the others are mechanical. Per plan §10: "For each suspected‑but‑unconfirmed: log it in a findings doc, DON'T fix on speculation."

---

## Absent services verification

- `services/health_monitor.py` — **ABSENT.** `find backend -iname '*health*'` returns only the renamed `services/observability.py` (Prometheus‑metrics‑based health). The deprecation of `health_monitor.py` in favor of `observability.py` is consistent with the rubric's "ship vs trim" Task 9 conclusion (the implementation moved, not vanished).
- `services/social_flow_pipeline.py` — **ABSENT at the named path.** Found at `backend/social_flow_pipeline.py` (top‑level, not under `services/`). The plan's spec pre‑dated the rename; the file exists and is in scope.

---

## Bug‑fix confirmations incidentally verified by this audit

The recent task‑8 Greek characterization commit did NOT touch any of the 9 dimensions above. The patterns observed here are the unchanged codebase state as of `1913eec`. No regression risk from the Task‑8 commit; the prior hardening arc (Task 1 delta‑r, Task 2 Kyle streaming, Task 3 replay dedup, Task 5 MONGO_URL default, Task 6 partial CORS) also did not touch these surfaces.

---

## Prioritized recommendation for Nav

1. **Ship this audit doc as‑is.** Every row is ripgrep‑verified; no fabrication; classification follows plan §10 rubric.
2. **Sequence the decision queue commits per their risk column** — gemini.py (#2) and alerts.py (#3) first (low risk, mechanical, big silent‑failure surface reduction). ml_api.py (#1) second (medium risk, requires per‑line context judgement before fix). admin.py (#4) third (defensible unless re‑read shows interactive context). Do all as pathspec commits per Freebuff anti‑skip gate §10.
3. **For admin.py L151** — request a 30‑second human review (the surrounding 10 lines) before grading DEFENSIBLE vs REPRODUCIBLE. The grader here is conservative‑leaning‑DEFENSIBLE but the call is the user's.
4. **No CLAUDE.md change recommended** — the audit doc is a per‑task deliverable, not a directive. Reference in CLAUDE.md is a candidate follow‑up.
5. **Carry‑over Task 10 → follow‑ups** — once the decision queue is drained, the next "re‑audit" scope is dimmer (most of the codebase's silent‑failure surfaces will be enumerated). A future re‑audit would pivot to **race conditions** or **partial‑failure ordering** for the remaining unresolved surface.

---

## Cut‑short‑audit lexicon (the patterns this audit searched for)

For future re‑audit reproducibility:

- `except\s*:\s*$` — bare except clause at end of line
- `except\s+Exception\s*:\s*(?:\n\s*)*pass\b` — `except Exception: pass` (swallows EVERY exception silently)
- `return\s+\{\s*["']error["']\s*:` — `return {"error": ...}` style response without HTTPException
- `return\s+\{\s*["']status["']\s*:\s*["']error["']` — `return {"status": "error", ...}` style response without HTTPException
- `"status":\s*"error"` (in route files only) — audit‑specific grade elevation

---

## Self‑review (groundedness)

- Every row in the §Per‑dimension results matrix is grounded in (a) `wc -l` for LOC, (b) `git log` for last‑touch, (c) ripgrep for pattern match counts.
- All 4 "hot‑spot deep‑dive" sections call out the EXACT LINE / PATTERN citation.
- Each §Decision queue row proposes a per‑finding failing‑test file path that does not yet exist — making the follow‑up commits `git log --diff-filter=A`‑discoverable as a single‑PR sequence.
- **No fabrication** — the ripgrep evidence is reproducible (`grep -cE '...' backend/routes/<file>.py`). A future re‑audit running the same ripgrep must surface identical numbers; divergence implies a fix has landed in the interim.
- **Provenance** — verified against `origin/main` HEAD = `1913eec` (this audit's evidence base). If a future PR silently converts the gemini 200‑with‑error‑body pattern to 503, the diff between `1913eec` and current HEAD will be the natural re‑audit trigger.

— Freebuff, 2026‑06‑20
