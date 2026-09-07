# Evidence index and preservation receipt

Current preservation boundary: September7, G1 b5f9ae5d99a4d502efdaf1d0c4d8386c2fa9b0d0. Reports explicitly retain their own earlier timestamps and heads.

| Artifact | Meaning |
|---|---|
| [Branch/PR audit](evidence/branch-evidence-20260906.md) | Earlier GitHub/source audit; historical test totals identified; superseded by later snapshots where stated |
| [swarmSPX audit](evidence/swarmspx-audit.md) | Separate-repo code/artifact audit, grouped IDs1–64; proposed research thresholds are not approved requirements |
| [Recent Heat/ticker audit](evidence/recent-heat-audit.md) | REWORK; deterministic analytics/budget/cache/navigation failures and test results; origin-containment note superseded by backup receipt |
| [Scoller WIP patch](evidence/wip-scroller.patch) | Dirty App.js and SkylitTickerBar.jsx changes captured against G1 b5f9ae5; contains the known cap/search defects, not an accepted fix |
| [Serena WIP patch](evidence/wip-serena.patch) | Migration to language_servers including Python; saved as evidence without applying it to product config |
| [F1 WIP patch](evidence/wip-f1.patch) and [test snapshot](evidence/wip-test_honesty_f0.py.txt) | Unfinished work from /private/tmp/w-f0 at5b9d9a9; runtime claim still requires completion |
| legacy-heat-notes/ under evidence | Four untracked notes preserved verbatim; stale “no bug” and “already done” claims are not current verdicts |

The G1 history through b5f9ae5 was saved to `origin/archive/20260907-g1-recovery` and checked with git ls-remote. No G1 working-tree file was staged or overwritten. F1, Serena and scroller originals remain available to their owners; snapshots make recovery independent of /tmp.

Original plan preservation commit: a2c6b08, fifteen documentation paths recovered from84031ea onto origin/main5b9d9a9. The institutional ledger remains identical to main. Current v2 documentation supersedes old role assignments and clocks; original registers remain historical sources.

Recovery of a WIP patch requires a disposable worktree at its recorded base and `git apply --check --unidiff-zero` first. These patches use zero context to preserve exact changes without whitespace-only context lines. Apply only at the recorded base, with `--unidiff-zero`. The F1 test snapshot must be placed at backend/tests/services/test_honesty_f0.py in that worktree. Do not apply a patch to a newer dirty checkout, do not treat a saved patch as green code, and do not copy secrets or private raw datasets into this package.
