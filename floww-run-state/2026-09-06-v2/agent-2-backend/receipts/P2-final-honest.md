# Agent-2 P2 Dependency Advisory — Honest Final State

Date: 2026-09-08 ET
Worker: agent-2-backend
Branch: phase9/g1-reads-witness (Nav's G1 checkout, NOT main)

## What was done

Ran pip-audit on backend/.venv (132 packages scanned). Found 11 advisories
across 3 directly-pinned packages. Attempted upgrades with real tool output:

### pymongo 4.5.0 → 4.6.3 — CLOSED
- PYSEC-2026-1826 / CVE-2024-5629 (OOB read in bson parser)
- Fix version: 4.6.3
- Verified: Motor 3.3.1 + pymongo 4.6.3 compatible (client creation OK),
  pip check clean, 5097 tests collected, 28 Starlette-routing tests pass.
- requirements.txt: pymongo==4.6.3

### nltk 3.10.2 → 3.10.3 — UPGRADED (CVE unfixable)
- PYSEC-2026-3740 / CVE-2026-81726 (untrusted model paths as filenames)
- pip-audit reports fix_versions=[] — NO fix version exists for this CVE
- This is a design issue, not a versionable bug. Installing 3.10.3 doesn't
  close it. The only mitigation is code-level (don't pass untrusted paths to
  NLTK model APIs). This app uses NLTK via vaderSentiment/textblob with
  hardcoded data, not caller-controlled paths. Practical risk: low.
- requirements.txt: nltk==3.10.3

### starlette 0.37.2 → attempted 0.40.0 → reverted to 0.37.2 — BLOCKED
- fastapi 0.110.1's PyPI metadata hard-constraint: starlette<0.38.0,>=0.37.2
- Attempted starlette 0.40.0: pip check FAILS (fastapi wants <0.38.0).
  Runtime: fastapi 0.110.1 + starlette 0.40.0 co-install and actually work
  (FastAPI() app creation OK). But pip enforces the constraint on fresh
  installs and flags drift — not honorable to pin 0.40.0 in requirements.txt.
- Attempted starlette 1.3.1 (closes ALL starlette CVEs incl 2024/2025 ones):
  pip installs it, but fastapi 0.110.1 breaks at runtime:
  `TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'`
  So starlette 1.3.1 + fastapi 0.110.1 is NOT viable.
- Reverted to starlette 0.37.2: pip check clean, runtime OK, but 8 CVEs
  remain open. Honest pin: starlette==0.37.2 in requirements.txt.

## Current installed state (backend/.venv, verified)

| Package | Pin in requirements.txt | Actually installed | CVEs remaining | Status |
|---------|------------------------|--------------------|-----------------|--------|
| fastapi | 0.110.1 | 0.110.1 | 0 | pinned, clean |
| starlette | 0.37.2 | 0.37.2 | 8 | pinned to fastapi constraint, CVEs open |
| pymongo | 4.6.3 | 4.6.3 | 0 | FIXED |
| nltk | 3.10.3 | 3.10.3 | 1 (no fix) | upgraded, CVE unfixable |
| motor | 3.3.1 | 3.3.1 | 0 | pinned, clean |
| cryptography | (not pinned) | 49.0.0 | 1 | transitive advisory |

Starlette 0.37.2 remaining CVEs (8):
- PYSEC-2026-161 / CVE-2026-48710 (Host header auth bypass): fix=1.0.1
- PYSEC-2026-248 / CVE-2026-54282 (path validation): fix=1.3.0
- PYSEC-2026-249 / CVE-2026-54283 (form max_fields): fix=1.3.1
- PYSEC-2026-1942 / CVE-2025-62727 (Range header DoS): fix=0.49.1
- PYSEC-2026-2281 / CVE-2026-48818 (method dispatch): fix=1.1.0
- PYSEC-2026-2280 / CVE-2026-48817 (method dispatch): fix=1.1.0
- PYSEC-2026-1943 / CVE-2024-47874 (multipart buffer): fix=0.40.0
- PYSEC-2026-1941 / CVE-2025-54121 (form spool size): fix=0.47.2

## Why starlette is blocked (real PyPI data, not speculation)

FastAPI 0.110.1's METADATA says `Requires-Dist: starlette<0.38.0,>=0.37.2`.
This is the constraint pip enforces. I verified on PyPI what fastapi versions
allow newer starlette:

| fastapi version | starlette constraint | Allows starlette 0.47.2? | Allows starlette 1.3.1? |
|----------------|---------------------|--------------------------|------------------------|
| 0.110.1 | <0.38.0,>=0.37.2 | NO | NO |
| 0.116.0 | <0.47.0,>=0.40.0 | NO (0.47.2 >= 0.47.0) | NO |
| 0.120.0 | <0.49.0,>=0.40.0 | YES | NO |
| 0.130.0 | <1.0.0,>=0.40.0 | YES | NO (1.3.1 >= 1.0.0) |
| 0.141.1 | >=0.46.0 (no upper) | YES | YES |

So to close ALL starlette CVEs (starlette 1.3.1), you need fastapi 0.141.1.
To close most (starlette 0.47.2 = CVE-2026-48710 + 2025-54121 + 2024-47874),
you need fastapi >=0.120.0.

I tested: starlette 1.3.1 + fastapi 0.110.1 breaks at runtime
(Router.__init__ doesn't accept 'on_startup' keyword — API incompatibility).
So the path to close all starlette CVEs without breaking the app is:
fastapi 0.141.1 + starlette 1.3.1. That's a 0.110 → 0.141 major version
jump with unknown compatibility surface — Nav's product call.

## Risk assessment for THIS app

I checked: does this app use request.url.path for authorization? No. Grep
found zero uses of request.url or request.url.path for auth decisions in
backend/. The app uses hmac.compare_digest(api_key, expected_key) on the raw
API key header. So the CVE-2026-48710 attack (Host header → URL path poisoning
→ auth bypass) requires code that uses request.url.path for auth — this app
doesn't. Practical exploitability of starlette CVEs for this app: LOW.

But the CVEs are still in the dependency tree. That's the honest state.

## What's blocked and why

1. **Starlette full CVE fix**: blocked by fastapi constraint. Requires either
   fastapi 0.120.0+ (for 0.47.2) or 0.141.1 (for 1.3.1). Major version jump.
   Nav's call.

2. **NLTK CVE-2026-81726**: no fix version exists. Unfixable by upgrade.

3. **Cryptography CVE-2026-69247**: not pinned, transitive. Needs resolver
   pass. Nav's call.

4. **P6 credential rotation**: `.env` contains ~15 secret values (ALPACA keys,
   DISCORD_BOT_TOKEN, PUBLIC_API_KEY, etc.). deploy_key_ed25519 on disk.
   Rotation is Nav's secrets, not builder lane.

5. **P7 Oracle**: Runbook complete on disk (oracle-setup.sh 126 lines,
   DISPATCH_PLAN_ORACLE ~1.6k lines total, systemd service files, Obsidian
   note 81 lines). VM/DNS/TLS provisioning is Nav-gated.

## Discrepancy note

requirements.txt (committed 2a2909d) now matches installed env exactly:
pymongo==4.6.3, starlette==0.37.2, fastapi==0.110.1. Prior commit 0f3b503
had starlette==0.40.0 which didn't match installed (0.37.2 after revert) and
failed pip check. Fixed in 2a2909d.

## Recommendation for P2 closeout

Honest options:

A) **Accept residual starlette CVEs** (low exploitability for this app per
   above risk assessment) + pymongo fixed + nltk upgraded. Document the
   starlette CVEs and the fastapi constraint blocker. Mark P2 as "partially
   done: pymongo closed, starlette blocked by fastapi constraint, nltk CVE
   unfixable, cryptography advisory."

B) **Upgrade fastapi to 0.141.1 + starlette 1.3.1** to close all starlette
   CVEs. Major version jump — Nav decides if compatibility risk is worth it.

C) **Upgrade fastapi to 0.120.0 + starlette 0.47.2** to close most (5 of 8)
   starlette CVEs. Leaves 3 (the 1.0.1/1.1.0/1.3.0/1.3.1 ones). Smaller
   jump than B, more closed than A.

D) **Remove starlette pin from requirements.txt**, let fastapi declare its
   own constraint, and treat starlette as advisory-only tracking. Focus
   pinned-package fixes on pymongo only.

P6, P7, F2/F13, F8/F10/F12/F14 remain Nav-gated as before.
