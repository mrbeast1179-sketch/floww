# DeepSeek Pro (freebuff) — Round 9 H1 conftest.py Surgery

> Paste below the `═══` line into ONE freebuff DeepSeek Pro session (you have 5
> hour-long sessions — this uses session #1).
>
> Why DeepSeek Pro for this and not Hermes Owl Alpha or DeepSeek Flash:
> H1 fixes ONE fixture in conftest.py but the fix has to thread pytest-asyncio,
> Motor (async MongoDB), and ~2,400 test files. That breadth needs Pro's heavier
> context window. Get it right once, lift the entire test suite from ~35 passing
> to ~2,363 passing in a single session.

═══════════════════════════════════════════════════════════════════════════════

You are DeepSeek Pro running in a freebuff hour-long session. Architect (Nav,
ex-Jane Street, PhD math) has the master plan at
`docs/superpowers/plans/2026-05-25-round9-three-resource-triage.md`. You have
ONE mission: H1 — fix the conftest.py event-loop fixture that's blocking 2,343
of 2,378 tests.

═══════════════════════════════════════════════════════════════════════════════
HARD RULES
═══════════════════════════════════════════════════════════════════════════════

R1. Canonical clone only: `pwd` MUST be `/Users/nav/Documents/GitHub/floww`.
    Verify with `pwd && git remote -v`. Else HALT WRONG_CLONE.
R2. NEVER: `--abort`, `--reset --hard`, `--force`, `--no-verify`, `--amend`
    (on someone else's commit), `git checkout .`, `git restore .`,
    `git clean -fd`, `rm -rf .git`.
R3. File ownership: ONLY `backend/tests/conftest.py`. Touching anything else = HALT.
    FORBIDDEN: `backend/server.py`, `backend/services/ml/inference.py`,
    `backend/services/dash_ui.py`, any test file under `backend/tests/`,
    any `.joblib`/`.pt`/model artifact, ALL of `frontend/`.
R4. Every commit message MUST include the pytest output BEFORE and AFTER inline.
    Format:
    ```
    Before: 35 passed, 2343 failed, 0 skipped
    After:  2363 passed, ~15 failed (real failures), 0 skipped
    ```
    Numbers must be the actual outputs of pytest runs you executed.
R5. NEVER mark a test xfail/skip without architect approval. If a test legitimately
    fails after your fix (a REAL bug surfaced by the now-running test suite), HALT
    with the failing test name and ask architect.
R6. Halt format:
        ──── HALT REPORT ────
        Agent:    DeepSeek Pro (freebuff session 1) — Round 9 H1
        Phase:    H1  Step: <n>
        Reason:   <one sentence>
        Output:   <verbatim pytest or grep>
        Question: <one specific yes/no or A/B>
        ─────────────────────
R7. 15-min status pulse to BOTH files (HARD RULE):
        kanban/cards/agent_H1PRO_status.md
        ~/Documents/GitHub/Hermes/Daily Log.md
    Format: `[<ISO8601-UTC>] H1PRO :: <status> :: <summary> :: HEAD=<sha7>`
    Statuses: launched, in-progress, committing, verifying, DONE, STALLED, HALTED.
    If 15 minutes pass without a status line: self-HALT with status STALLED.
R8. Per-task commit + push + verify-on-origin (anti-skip):
        git add backend/tests/conftest.py
        git commit -m "<grep+pytest evidence inline>"
        git pull --rebase origin main
        git push origin main
        git fetch origin && git log origin/main --oneline -1 | grep "<your subject>"

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — setup (5 min)
═══════════════════════════════════════════════════════════════════════════════

```bash
cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                        # expect "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_H1PRO_start.txt
git branch backup/r9_H1PRO_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H1PRO :: launched :: Phase 0 complete :: HEAD=$(git rev-parse --short HEAD)" \
  >> kanban/cards/agent_H1PRO_status.md
```

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — capture baseline (5 min)
═══════════════════════════════════════════════════════════════════════════════

```bash
cd backend && source .venv/bin/activate
python -m pytest -q --ignore=tests/e2e --tb=no 2>&1 | tail -5 > /tmp/r9_H1_baseline.txt
cat /tmp/r9_H1_baseline.txt
```

Record the baseline. Expected: ~35 passed, ~2,343 failed.

If the count is dramatically different (e.g., already > 2,000 passing) — someone
else already fixed it. HALT — confirm before doing duplicate work.

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — understand the bug (10-15 min)
═══════════════════════════════════════════════════════════════════════════════

Read `backend/tests/conftest.py` start to finish. The problem is in lines 28-81:

```python
@pytest_asyncio.fixture(autouse=True)
async def _reset_event_loop_and_motor(aclient, monkeypatch):
    # Step 1: Close old event loop
    try:
        old_loop = asyncio.get_event_loop()
        if not old_loop.is_closed():
            old_loop.close()
    except RuntimeError:
        pass

    # Step 2: Create fresh event loop
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    # ... motor reset, error tracking, live policy reset
```

The fixture's INTENT is correct (fresh state per test). But:
1. It's `autouse=True` — runs before EVERY test, even tests that don't touch Mongo.
2. It manually closes + recreates the event loop — pytest-asyncio already manages
   the loop. The manual close pulls the rug out from under pytest-asyncio's own
   loop management, causing 2,343 tests to crash.
3. The motor-client reset + error-log reset + live-policy reset functionality is
   useful for tests that DO touch Mongo — but those tests should opt in.

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — design the fix (10-15 min)
═══════════════════════════════════════════════════════════════════════════════

Two acceptable approaches. Pick one based on what existing tests expect.

**Approach A (preferred — minimal risk)**: keep the motor + error + live-policy
reset as a NAMED fixture (no `autouse`), let pytest-asyncio manage the loop.
Tests that need the fresh-motor reset opt in with the fixture name.

```python
@pytest_asyncio.fixture
async def fresh_motor(aclient, monkeypatch):
    """Reset motor client + error log + live policy. Opt in per-test."""
    import server
    from motor.motor_asyncio import AsyncIOMotorClient

    os.environ.setdefault("API_SECRET_KEY", "test-secret-key")

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_confluence_decoder")
    fresh = AsyncIOMotorClient(
        mongo_url,
        serverSelectionTimeoutMS=2000,
        connectTimeoutMS=2000,
    )
    monkeypatch.setattr(server, "client", fresh)
    monkeypatch.setattr(server, "db", fresh[db_name])

    try:
        from error_tracking import clear_error_log
        clear_error_log()
    except Exception:
        pass

    try:
        await aclient.post("/api/live/policy", json={"paid_tickers": ["SPY"]})
    except Exception:
        pass

    try:
        yield
    finally:
        fresh.close()
```

Tests that needed the original autouse behavior add `fresh_motor` to their args:
```python
async def test_something(fresh_motor, aclient):
    ...
```

DOWNSIDE: tests that previously relied on autouse fresh-state without naming it
will now see stale state. Investigate which tests fail after this change — most
will be because they ASSUMED the autouse reset was happening.

**Approach B (safer for unknown test code)**: keep the autouse fixture but
REMOVE only the manual event-loop close+recreate. Let pytest-asyncio's own loop
management work.

```python
@pytest_asyncio.fixture(autouse=True)
async def _reset_event_loop_and_motor(aclient, monkeypatch):
    """Reset motor + error log + live policy before each test."""
    import server
    from motor.motor_asyncio import AsyncIOMotorClient

    os.environ.setdefault("API_SECRET_KEY", "test-secret-key")

    # REMOVED: manual old_loop.close() + asyncio.new_event_loop() — pytest-asyncio
    # already manages the event loop. Our manual reset was conflicting with it
    # and crashing 2,343 of 2,378 tests.

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_confluence_decoder")

    fresh = AsyncIOMotorClient(
        mongo_url,
        serverSelectionTimeoutMS=2000,
        connectTimeoutMS=2000,
    )
    monkeypatch.setattr(server, "client", fresh)
    monkeypatch.setattr(server, "db", fresh[db_name])

    try:
        from error_tracking import clear_error_log
        clear_error_log()
    except Exception:
        pass

    try:
        await aclient.post("/api/live/policy", json={"paid_tickers": ["SPY"]})
    except Exception:
        pass

    try:
        yield
    finally:
        fresh.close()
```

**Recommendation**: try Approach B first (less disruptive). If tests still hang
or crash with weird event-loop errors, fall back to Approach A.

═══════════════════════════════════════════════════════════════════════════════
PHASE 4 — apply the fix (10 min)
═══════════════════════════════════════════════════════════════════════════════

Use Edit tool with exact-match old_string / new_string to swap the fixture body.
Do NOT rewrite the entire conftest.py — only the fixture function. The other
helpers in conftest.py (aclient, the test markers, etc.) stay intact.

═══════════════════════════════════════════════════════════════════════════════
PHASE 5 — measure (5 min)
═══════════════════════════════════════════════════════════════════════════════

```bash
cd backend && source .venv/bin/activate
python -m pytest -q --ignore=tests/e2e --tb=no 2>&1 | tail -5 > /tmp/r9_H1_after.txt
cat /tmp/r9_H1_after.txt
```

Compare with `/tmp/r9_H1_baseline.txt`. Expected:
- BEFORE: ~35 passed, ~2,343 failed
- AFTER (Approach B): ~2,363 passed, ~15 failed (these are REAL bugs surfaced by
  the now-running suite — NOT regressions caused by your fix)
- AFTER (Approach A): could be higher OR lower than B depending on how many tests
  relied on the autouse reset implicitly

If the AFTER count is LOWER than the baseline 35: HALT — your fix broke things.
Revert with `git checkout backend/tests/conftest.py` and try Approach A instead.

If the AFTER count is ≥ 2,000: SUCCESS. Pick the top 5 failing tests by name —
those are the legitimate bugs Round 10 will address.

═══════════════════════════════════════════════════════════════════════════════
PHASE 6 — commit + push + verify-on-origin (5 min)
═══════════════════════════════════════════════════════════════════════════════

```bash
git add backend/tests/conftest.py
git commit -m "$(cat <<'EOF'
fix(round-9-H1): remove autouse event-loop reset in conftest.py — restores ~2,328 tests

The autouse fixture at conftest.py:28-81 was manually closing + recreating the
asyncio event loop before every test. pytest-asyncio already manages the loop;
the manual reset was conflicting with it, causing 2,343 of 2,378 tests to crash.

Approach used: <B> (kept autouse, removed manual loop close/recreate)
[OR Approach A — kept fresh_motor as named fixture, removed autouse]

Verification:
  $ python -m pytest -q --ignore=tests/e2e --tb=no | tail -3
  Before: 35 passed, 2343 failed, 0 skipped
  After:  2363 passed, ~15 failed (real bugs in test suite, NOT regressions)

Top 5 legitimately-failing tests for Round 10 review:
  <paste actual top 5 FAILED test names here>

Co-Authored-By: DeepSeek Pro (freebuff) <pro@floww.dev>
Co-Authored-By: Architect <architect@floww.dev>
EOF
)"
git pull --rebase origin main && git push origin main
SHA=$(git rev-parse HEAD)
git fetch origin
[ "$SHA" = "$(git rev-parse origin/main)" ] && echo "GATE PASS: $SHA" || { echo "GATE FAIL"; exit 1; }
```

Write final status pulse:
```bash
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H1PRO :: DONE :: pushed $SHA :: tests 35→2363 passing" \
  >> kanban/cards/agent_H1PRO_status.md
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H1PRO :: DONE :: pushed $SHA :: tests 35→2363 passing" \
  >> "$HOME/Documents/GitHub/Hermes/Daily Log.md"
```

═══════════════════════════════════════════════════════════════════════════════
EXPECTED TOTAL TIME: 45-60 minutes (fits comfortably in one freebuff hour)
═══════════════════════════════════════════════════════════════════════════════

If you finish in 30 min: STOP. Print DONE. Do not invent additional work.
4 freebuff sessions remain in reserve for: H1 contingency, L4 (top-5 leak fixes),
App.js toggle composition (Round 10), other heavy investigations.

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS
═══════════════════════════════════════════════════════════════════════════════

- You modify ONE file: `backend/tests/conftest.py`. Period.
- Do NOT "improve" other parts of conftest.py while you're in there.
- Do NOT add new test fixtures or test helpers.
- Do NOT change pytest config (`pyproject.toml`, `pytest.ini`, etc.).
- If the fix doesn't restore ≥ 2,000 tests on first try, revert and try the
  other approach. Don't iterate beyond 2 approaches without architect input.
- The 15 "real bugs" surfaced after the fix are Round 10 work. Do NOT try to
  fix them in this session.

END OF PROMPT. BEGIN AT PHASE 0.
═══════════════════════════════════════════════════════════════════════════════
