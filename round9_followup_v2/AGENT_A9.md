# Agent A9 — Backend Dead-Code Audit (READ-ONLY, target: 2.5 hours)

**You are Agent A9.** Read `_PREAMBLE.md`. Scope: AUDIT-ONLY across `backend/` to identify functions, classes, and modules with zero callers (dead code candidates). You write ONE deliverable: `docs/ROUND10_DEAD_CODE_AUDIT.md`. **You do not modify any source file.** Deletions are explicitly Round 10's job; your role is to produce the verified list.

This is a high-leverage role: Round 9 found 932 potentially-dead functions (per backlog). Verifying each by hand is the prerequisite to a safe Round-10 deletion sweep.

---

## Mission

| # | Task | Min |
|---|------|-----|
| 1 | Pre-flight + tools setup | 15 |
| 2 | Enumerate every `def`/`class` in backend | 20 |
| 3 | For each, count callers (grep + AST) | 40 |
| 4 | Triage by confidence (definitely-dead vs needs-eyeball) | 25 |
| 5 | Manual eyeball pass on top 50 candidates | 30 |
| 6 | Cross-reference with frontend fetch URLs | 15 |
| 7 | Cross-reference with scripts/ and cron jobs | 15 |
| 8 | Write the audit report | 20 |
| 9 | Close-out | 10 |

Total ~190 min.

---

## Reference: Why this matters

- Dead code = maintenance debt (developers read it, get confused)
- Dead code = security debt (vulnerable code paths the linter checks but no one tests)
- Dead code = test debt (broken tests for functions no one calls hide real failures)
- BUT: false-positive deletion = production breakage. Hence: AUDIT, NEVER DELETE.

False-positive sources you MUST account for:
- **Reflection / dynamic dispatch**: `getattr(obj, name)`, `globals()[name]`
- **Decorators**: A function decorated as `@router.get("/foo")` has its name never called, but Starlette still routes to it
- **FastAPI dependencies**: `Depends(some_function)` — grep for `Depends(<name>)`
- **Background tasks / cron**: invoked via APScheduler, cron, etc.
- **External imports**: another agent's branch or external script imports it

---

## Task 1 — Pre-flight + tools (15 min)

- [ ] **1.1** `pwd` canonical.
- [ ] **1.2** Confirm you write ONLY to `docs/ROUND10_DEAD_CODE_AUDIT.md` — no source files. If you find yourself opening Edit/Write on a `.py` file, STOP.
- [ ] **1.3** Check available tools:
  ```bash
  backend/.venv/bin/python3 -c "import ast; print('AST OK')"
  which rg 2>&1 || echo "ripgrep not installed — will use grep -rn"
  ```
- [ ] **1.4** First pulse.

---

## Task 2 — Enumerate every def/class (20 min)

- [ ] **2.1** Write a Python AST scanner script `scripts/audit_dead_code.py` (TEMP — you may add this to scripts/ as it's a one-off, not a source-code modification; commit it with your audit doc at the end):
  ```python
  #!/usr/bin/env python3
  """One-off AST scan of backend/ — lists every top-level def/class with its file:line."""
  import ast
  from pathlib import Path
  
  ROOT = Path("backend")
  EXCLUDES = {".venv", "__pycache__", "tests"}
  
  results = []
  for p in ROOT.rglob("*.py"):
      if any(part in EXCLUDES for part in p.parts):
          continue
      try:
          tree = ast.parse(p.read_text())
      except SyntaxError:
          continue
      for node in ast.walk(tree):
          if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
              # Skip dunder methods (mostly safe, often legitimately uncalled)
              if node.name.startswith("__") and node.name.endswith("__"):
                  continue
              # Skip clearly-private one-line helpers (less interesting)
              if node.name.startswith("_") and not isinstance(node, ast.ClassDef):
                  kind = "private_fn"
              elif isinstance(node, ast.ClassDef):
                  kind = "class"
              else:
                  kind = "public_fn"
              results.append({
                  "kind": kind,
                  "name": node.name,
                  "file": str(p.relative_to(".")),
                  "line": node.lineno,
              })
  
  print(f"# Total: {len(results)}")
  for r in sorted(results, key=lambda r: (r["file"], r["line"])):
      print(f"{r['kind']}\t{r['name']}\t{r['file']}:{r['line']}")
  ```
- [ ] **2.2** Run: `backend/.venv/bin/python3 scripts/audit_dead_code.py > /tmp/a9_all_defs.tsv` and capture line count.
- [ ] **2.3** Pulse.

---

## Task 3 — Count callers (40 min)

- [ ] **3.1** For EACH entry in /tmp/a9_all_defs.tsv, count how many places call/reference it. Write `scripts/count_callers.py`:
  ```python
  #!/usr/bin/env python3
  """For each (name, file) in /tmp/a9_all_defs.tsv, count caller hits in backend/ + frontend/ + scripts/."""
  import subprocess
  from pathlib import Path
  
  defs = []
  with open("/tmp/a9_all_defs.tsv") as f:
      for line in f:
          line = line.strip()
          if not line or line.startswith("#"):
              continue
          parts = line.split("\t")
          if len(parts) != 3:
              continue
          kind, name, fileln = parts
          file, lineno = fileln.rsplit(":", 1)
          defs.append((kind, name, file, int(lineno)))
  
  for kind, name, file, lineno in defs:
      # Count uses across the codebase (excluding the definition line itself)
      # \b<name>\b matches as identifier
      cmd = [
          "grep", "-rn",
          f"\\b{name}\\b",
          "backend/", "frontend/src/", "scripts/",
          "--include=*.py", "--include=*.js", "--include=*.jsx", "--include=*.ts", "--include=*.tsx",
      ]
      try:
          out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
      except subprocess.TimeoutExpired:
          print(f"TIMEOUT\t{name}\t{file}:{lineno}")
          continue
      lines = out.stdout.strip().split("\n") if out.stdout.strip() else []
      # Exclude the definition itself
      def_line_marker = f"{file}:{lineno}:"
      callers = [ln for ln in lines if not ln.startswith(def_line_marker) and ln]
      n_callers = len(callers)
      print(f"{n_callers}\t{kind}\t{name}\t{file}:{lineno}")
  ```
- [ ] **3.2** Run: `backend/.venv/bin/python3 scripts/count_callers.py > /tmp/a9_callers.tsv 2>&1`. This may take a few minutes — that's fine.
- [ ] **3.3** Sort by caller count ascending — 0-caller entries surface to the top:
  ```bash
  sort -n /tmp/a9_callers.tsv | head -100 > /tmp/a9_zero_caller.txt
  wc -l /tmp/a9_zero_caller.txt
  ```
- [ ] **3.4** Pulse.

---

## Task 4 — Triage by confidence (25 min)

For each zero-caller entry, classify:
- **A — Definitely dead (high confidence)**: regular function, no decorators, not in `__all__`, name doesn't suggest dynamic dispatch
- **B — Probably dead (needs eyeball)**: private helper that may be called via getattr; or function in a route file (could be a FastAPI route — needs decorator check)
- **C — False positive**: has `@router.get/@router.post` decorator; or is a CLI entry point; or is decorated with `@app.on_event(...)`

- [ ] **4.1** For each entry in /tmp/a9_zero_caller.txt, run a small grep to see surrounding lines (the line BEFORE the def is typically the decorator):
  ```bash
  while read line; do
    count=$(echo "$line" | cut -f1)
    name=$(echo "$line" | cut -f3)
    fileln=$(echo "$line" | cut -f4)
    file=$(echo "$fileln" | cut -d: -f1)
    ln=$(echo "$fileln" | cut -d: -f2)
    # Look at the 2 lines before the def
    decorator=$(sed -n "$((ln-2)),$((ln-1))p" "$file" | tr '\n' ' ')
    if echo "$decorator" | grep -qE '@router|@app|@scheduler|@cron|@click'; then
      verdict="C_FP_decorator"
    elif echo "$name" | grep -qE '^_'; then
      verdict="B_private"
    else
      verdict="A_dead"
    fi
    echo -e "$verdict\t$count\t$name\t$fileln"
  done < /tmp/a9_zero_caller.txt > /tmp/a9_triaged.tsv
  
  # Quick stats
  awk '{print $1}' /tmp/a9_triaged.tsv | sort | uniq -c
  ```
- [ ] **4.2** Pulse with the count breakdown.

---

## Task 5 — Manual eyeball pass on top 50 (30 min)

For each entry classified `A_dead`, open the file and verify:
- Is the function called from a Jinja template / docstring (unusual but possible)?
- Is it referenced in a config string (e.g., `"backend.services.foo:run"`)?
- Is it a public API that an external consumer might call (check git log for who added it)?

- [ ] **5.1** Open each of the top 50 A_dead entries. For each, append to the audit report (Task 8) one of:
  - **Confirmed dead** (safe to delete in R10)
  - **Likely dead, needs further investigation** (don't delete without owner sign-off)
  - **Reclassify** (false positive after eyeball)
- [ ] **5.2** Pulse.

---

## Task 6 — Cross-reference with frontend (15 min)

For functions in `backend/routes/*.py` that look unused, verify the corresponding URL isn't called from frontend:

- [ ] **6.1** Extract route URL patterns:
  ```bash
  grep -rEn '@router\.(get|post|delete|put|patch)\("[^"]+"\)' backend/routes/ \
    | grep -oE '"[^"]+"' \
    | sort -u > /tmp/a9_backend_urls.txt
  wc -l /tmp/a9_backend_urls.txt
  ```
- [ ] **6.2** Check each route URL appears in frontend:
  ```bash
  while read url; do
    cleaned=$(echo "$url" | tr -d '"')
    hits=$(grep -rE "['\"]$cleaned['\"]" frontend/src/ 2>/dev/null | wc -l)
    if [ "$hits" -eq 0 ]; then
      echo "UNUSED_ROUTE: $cleaned"
    fi
  done < /tmp/a9_backend_urls.txt > /tmp/a9_unused_routes.txt
  ```
- [ ] **6.3** Note: routes can be called by external tools (curl, scripts/, monitoring) — these aren't necessarily dead. Mark "Frontend doesn't call this; check scripts/external".

---

## Task 7 — Cross-reference scripts/ + cron (15 min)

- [ ] **7.1** Find anything in `scripts/` or `backend/cron_*.py` that imports from `backend/services/`:
  ```bash
  grep -rEn 'from services\.|from backend\.services' scripts/ backend/cron* 2>&1 | head -30
  ```
- [ ] **7.2** For each import, mark the imported names as ALIVE in your audit (overrides A_dead classification).
- [ ] **7.3** Pulse.

---

## Task 8 — Write the audit report (20 min)

- [ ] **8.1** Write `docs/ROUND10_DEAD_CODE_AUDIT.md`:
  ```markdown
  # Round 10 Backend Dead-Code Audit
  
  **Auditor:** Agent A9
  **Date:** <YYYY-MM-DD>
  **Method:** AST scan of all top-level def/class in backend/ (excl. tests, .venv), cross-referenced with grep across backend/ + frontend/src/ + scripts/. Per-entry decorator check to filter false-positive routes. Manual eyeball of top-50 candidates.
  
  ## Summary
  
  - Total definitions scanned: <N>
  - Zero-caller entries: <N>
  - Triage breakdown:
    - A_dead (no decorator, public-name): <count>
    - B_private (underscore-prefixed): <count>
    - C_FP_decorator (false positive — FastAPI/cron/etc.): <count>
  - Manual-eyeball confirmed dead (safe to delete): <count>
  - Frontend-unused route URLs: <count>
  
  ## Confirmed dead (safe to delete in Round 10)
  
  | File:Line | Name | Kind | Notes |
  |-----------|------|------|-------|
  | services/foo.py:42 | bar | function | added in Round 5, never wired up |
  | ... | | | |
  
  ## Likely dead (needs owner sign-off before deletion)
  
  | File:Line | Name | Kind | Reason for caution |
  |-----------|------|------|---------------------|
  | services/baz.py:88 | _quux | private fn | might be called via getattr in dispatch |
  
  ## False positives (DO NOT DELETE — auditor confirmed alive)
  
  | File:Line | Name | Why it looked dead |
  |-----------|------|--------------------|
  | routes/foo.py:50 | get_foo | @router.get("/foo") — invoked by FastAPI |
  
  ## Unused frontend route URLs (deletion candidates)
  
  | URL | Backend file | Used in scripts/cron? |
  |-----|--------------|------------------------|
  | /api/x | routes/x.py | no — safe to deprecate |
  
  ## Methodology + reproduction
  
  All scan scripts are committed at:
  - scripts/audit_dead_code.py
  - scripts/count_callers.py
  
  To re-run from scratch:
  ```bash
  backend/.venv/bin/python3 scripts/audit_dead_code.py > /tmp/all_defs.tsv
  backend/.venv/bin/python3 scripts/count_callers.py > /tmp/callers.tsv
  sort -n /tmp/callers.tsv | head -100  # top dead candidates
  ```
  
  ## Round 10 plan (recommended)
  
  - Phase 1: delete the N "confirmed dead" entries, one per PR
  - Phase 2: ping owners for "likely dead" — get sign-off OR add a use case
  - Phase 3: deprecate the unused frontend routes (HTTP 410 Gone for 30d, then remove)
  ```
- [ ] **8.2** Commit:
  ```bash
  git add docs/ROUND10_DEAD_CODE_AUDIT.md scripts/audit_dead_code.py scripts/count_callers.py
  git commit -m "$(cat <<'EOF'
  docs(round-10): dead-code audit — <N> definitions scanned, <K> confirmed dead
  
  AST scan + grep cross-reference + manual eyeball top-50. Audit report
  at docs/ROUND10_DEAD_CODE_AUDIT.md.
  
  Includes reproducible scan scripts:
  - scripts/audit_dead_code.py (AST extraction)
  - scripts/count_callers.py (grep cross-ref)
  
  Round 10 should:
  1. Delete confirmed-dead entries one-per-PR
  2. Get owner sign-off on likely-dead entries
  3. Deprecate unused frontend route URLs
  EOF
  )"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'dead-code'
  ```
- [ ] **8.3** Pulse.

---

## Task 9 — Close-out (10 min)

- [ ] **9.1** `docs/ROUND9_A9_CLOSEOUT.md`.
- [ ] **9.2** Commit + push + gate.
- [ ] **9.3** Final pulse.

---

## Halt conditions

1. You modify a `.py` source file — STOP, your scope is READ-ONLY.
2. The AST scanner crashes on a malformed file — note the file, skip it, continue.
3. The grep cross-reference takes >10 min total — too slow; reduce scope to public functions only.
4. Your audit reveals >10 unused public route URLs — that's important; flag as urgent in close-out.
5. 15-min pulse gap.
