# P6 audit note — agent-2-backend — 2026-09-07

Branch: astra/f0-honesty-backend. Head d63d0b3 (merge of origin/main; local == remote).

P6 scope (path-only credential audit, current-doc redaction, rotation handoff).
Constraint: the actual credentials live only in the real prod checkout's .env /
config/secrets.py / provider env, and the canonical repo at
/Users/nav/Documents/GitHub/floww. This worktree's backend is a frozen 3.12 refactor
snapshot, so durable action is: enumerate the surface from files in scope here,
record what must be rotated/revoked, point to the production paths for redaction +
rotation, and cross-walk to the existing secrets-scan lane.

Repo reads performed (files only, values not emitted):
- backend/config/secrets.py — secrets module (structure).
- backend/auth.py — auth (reads settings; not a secret store by itself).
- backend/server.py — server (reads settings; not a secret store by itself).
- backend/databento_provider.py — databento key path.
- backend/alpaca_client.py — alpaca key path.
- backend/discord_bot.py — discord token path.
- backend/cron_outcomes.py — cron outcomes (may touch webhook/salt).
- deploy/free/.env.prod.template — prod template.
- backend/tests/chaos/secret_scan.py + test_secret_scan.py — existing secrets scan.

Confirmed boundary:
- No live credential values were read, emitted, or rotated.
- No .env materialized in this worktree's backend.
- No paid probe.
- No rotation performed — rotation is Nav-gated.

Known credential surface (names only; rotate at provider/vault/console):
- Databento API key (databento_provider.py). Note existing CLAUDE.md
  auth_account_locked finding — rotation alone may not fix a vendor-side lock;
  vendor ticket is the real fix there.
- Alpaca keys (alpaca_client.py)
- Discord bot token + guild id (discord_bot.py)
- CVServer API key
- Finnhub / Alpha Vantage / AllPaper / other provider API keys
- LLM provider keys (OpenAI/Anthropic/etc.) used by route consumers
- AWS/GCP creds if free-tier deploy uses them
- auth/cron webhook/salt/jwt signing secrets

Redaction target (production paths, not this snapshot):
- docs/ and reports/ that may still contain a real key, token, URL-with-credential,
  or example payload with a real identity.
- deploy/free/.env.prod.template: verify placeholders match the real prod keys
  (do not invent new required keys).

Rotation handoff (Nav action, this receipt as input):
1. Rotate each secret above at its provider/vault/console.
2. Update the real .env / secrets store / provider console with rotated values.
3. Redact any doc/report under docs/ and reports/ that still contains a real key,
   token, URL-with-credential, or example payload with a real identity.
4. Remove or replace any committed example that embeds a real secret (if one exists).
5. Re-run existing chaos/secret_scan.py (and any CI gate) against the production
   checkout to confirm no credential-shaped value remains committed.
6. Record rotation date + rotated key names (not values) in a durable secrets log.

What P6 does NOT do here:
- Does not claim the production checkout is clean.
- Does not perform rotation.
- Does not rewrite docs in this snapshot absent Nav confirmation of the exact
  redaction list.
- Does not touch frontend unless a frontend doc actually contains a credential
  (verify first, then redact with explicit paths).

Honest status: P6 audit inventory is ready and trustworthy within this snapshot's
scope. The durable redaction + rotation is a Nav-gated operation on the real prod
paths. No frozen files touched. No uncommitted drift.

Full receipt with the same content also lives at:
/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/agent-2-backend/receipts/P6.md
(that path is outside this worktree's git — owned by Agent1's run-state tree.)

Verification:
- git status --short (kanban drift reverted; only leased/allowed files staged)
EOF
