# /Users/nav/Documents/GitHub/floww/Makefile
#
# Exposes one canonical regen target pulled in by the pre-commit hook
# (`make consolidate-diff` -> scripts/consolidate_diff.py). Idempotent;
# rerunning against unchanged source git data produces a byte-identical
# report file. Corrective: if a numeric cell has drifted, the script
# restores the correct value from `git show --numstat/--shortstat`.
#
# `make test` runs `scripts/consolidate_diff.py --validate`, an in-memory
# probe suite that injects stale numeric values and asserts each cell
# reverts to its git ground truth. Byte-equality alone could not catch
# the previous lambda group-indexing bug (the old regex silently no-op'd
# on the Deletions cell, so the script was accidentally-idempotent while
# the bug lurked). The probe suite calls the regen code path with a stale
# input, so it ALSO covers the chained pass order (TL;DR then per-file).

.PHONY: consolidate-diff test

consolidate-diff:
	@python3 scripts/consolidate_diff.py

# In-memory probe suite — exits 0 on full PASS, 1 otherwise.
# Does not touch disk; safe to run before/after regen without side effects.
test:
	@python3 scripts/consolidate_diff.py --validate
