# Harness v2 — multi-day execution protocol

## Control rule

The coordinator may have many candidate tasks but admits exactly one task per builder
at a time. Workers do not select from GitHub, rewrite central state, or expand their
own file scope. A chat is a replaceable process; Git, checkpoints, task cards, and
evidence receipts are the durable system.

## Launch handshake

Before dispatch, Agent 1 writes a task card containing task ID, O/X contract, base SHA,
branch, worktree, allowed files, proof commands, dependencies, external gates, and the
first command. A worker's first action is to write `boot.json` in its external lane
directory with:

The coordinator owns `/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/task-cards/<task-id>.md` and the central runtime state. Future cards live there, so creating a card never requires silently widening a repository-file lease. The committed TASK-CARDS.md contains initial templates only. The JSON below is a schema example with September 6 values — always use current `origin/main` (run-state-v2.json `acceptance_base`) in a real boot.json.

```json
{
  "schema": "floww-worker-boot/v2",
  "agent": "agent-2-backend",
  "session": "provider-session-id-or-unknown",
  "task_id": "F0-F1",
  "worktree": "/private/tmp/w-f0",
  "base_sha": "5b9d9a96a29951e548e883d108a806b93c2d11a9",
  "head_sha": "5b9d9a96a29951e548e883d108a806b93c2d11a9",
  "allowed_files": ["backend/services/gex_paper_accurate.py", "backend/tests/services/test_honesty_f0.py"],
  "next_command": "run the focused F1 regression",
  "written_at_utc": "worker-supplied ISO-8601 timestamp"
}
```

Agent 1 re-reads Git state and this receipt before marking the lane `ACTIVE`. A
delegation UI saying “background” is only `DISPATCHED`.

## Task lifecycle

```text
DISCOVERY -> READY -> ACTIVE -> REVIEW -> ACCEPTED -> MERGED -> DEPLOYED -> WITNESSED
                 \-> BLOCKED
                 \-> REWORK -> ACTIVE
                 \-> HARNESS_FAILED -> READY
                 \-> VERIFIED_EXISTING
                 \-> DEFERRED
```

`ACCEPTED` means a reviewed candidate. It does not mean main, deployment, or external
witness. Every transition records its actor, exact head, evidence path, and timestamp.

## Checkpoints

Each lane owns only:

```text
/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/<lane>/
  boot.json
  checkpoint.json
  events.jsonl
  receipts/<task-id>.md
```

Checkpoint after every red test, green test, commit, push, review verdict, blocker,
and at least every 15 minutes of meaningful work. The checkpoint includes dirty owned
paths, last command and exit, exact failure, next command, lease, branch/local/remote
SHAs, and attempt count. It never contains credentials or raw private market data.

## Concurrency

- Agent 1: central state and integration only.
- Agent 2 and Agent 3: parallel only with disjoint whole-file leases.
- Agent 4: read/review only while builders edit; independent new test paths need a
  lease and cannot modify a builder's test.
- One full backend suite, frontend full suite, build, or Docker build at a time.
- One runtime owner and one live provider-probe owner at a time.
- Only one repository-wide `$gsd-loop-build` worker. Managed task-card builders do not
  invoke that picker.

## Evidence levels

| Level | Minimum evidence |
|---|---|
| SOURCE | path/symbol and exact head read |
| REPRODUCED | deterministic input demonstrates claimed behavior |
| TARGETED | focused test/lint command, exit, count |
| REGRESSION | relevant broader suite at exact candidate head |
| CI | GitHub job URL and exact head |
| REVIEWED | independent O/X and quality verdict |
| MERGED | PR merged plus fetched main ancestry/content receipt |
| DEPLOYED | PID/cwd/revision or immutable image plus endpoint response |
| WITNESSED | named human/external action and observed result |

No higher level is inferred from a lower one.

## Failure classes

| Class | Required reaction |
|---|---|
| `NO_BYTES` / provider 5xx | Preserve checkpoint, rotate session once, then pause repeated failure |
| `RATE_LIMIT` | Stagger calls, reduce agent concurrency, resume from checkpoint after provider permits |
| `APPROVAL_DENIED` | Record exact command; continue independent read-only work |
| `ENVIRONMENT` | Record runtime/dependency mismatch; do not patch product to hide it |
| `BASELINE` | Reproduce at base; keep separate from task regression |
| `REGRESSION` | Repair within lease with red/green evidence |
| `CONTRACT_AMBIGUITY` | Stop dependent code; send one decision to Agent 1/Nav |
| `EXTERNAL_GATE` | Name owner and exact missing artifact; take an independent eligible task |

## Integration gate

Before a PR:

1. Fetch origin and record base/head.
2. Confirm changed paths are a subset of the lease.
3. Inspect full diff and generated/binary/secret detector results.
4. Run targeted and relevant broader checks.
5. Obtain Agent 4's two-stage review.
6. Push to an explicit task branch and verify remote SHA equals local SHA.
7. Open/update one PR whose body contains O/X results and actual evidence.

Before merge, Nav verifies required checks and the exact reviewed head. After merge,
Agent 1 fetches main and records the actual merge SHA.

## Multi-day continuation

A worker handles one coherent unit, then requests another admission. When context is
low, it stops after a checkpoint and commit/push if the unit is green; unfinished
changes remain on their isolated branch with a precise next command. The replacement
worker reads `checkpoint.json`, `git status`, `git log`, and the task card before any
new investigation.

The coordinator watches progress artifacts rather than chat activity. Fifteen minutes
without a new artifact triggers one status request. A missing response becomes
`HARNESS_FAILED`; it does not release a dirty worktree or silently reassign its files.

## Scheduling limit in this session

The installed `gsd-loop-schedule` workflow requires a native recurring-task tool. This
host does not expose one, so no recurring builder/reviewer was created. The four prompt
files support user-launched persistent sessions now. When a native scheduler is
available, schedule the build lane and review lane in separate chats after running the
GSD doctor; never emulate it with a shell loop.
