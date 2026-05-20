# Morning Checklist — 60-Second Swarm Status

When you wake up, run through this in order. Top to bottom. Stop at the first red flag.

## 1. Single-glance dashboard (5s)
```bash
cd /Users/nav/Documents/GitHub/floww
cat kanban/SWARM_STATUS.md
```
That's Agent 8's auto-generated board. If it doesn't exist, Agent 8 died — restart it.

## 2. Truth audit (5s)
```bash
bash qc/audit/truth_audit.sh
```
Must say `TRUTH AUDIT PASSED`. If red → remediation-only mode until green. No new feature work.

## 3. Git position (5s)
```bash
git log --oneline -10
git status --short | head -20
git rev-list --left-right --count origin/main...main
```
- `--count` should be `0	0` (synced)
- If working tree has 20+ M/?? files → agents are mid-flight, leave them alone
- If working tree is clean → agents finished or stalled (check kanban)

## 4. Architect brief (10s)
```bash
cat kanban/ARCHITECT_BRIEF.md
```
Sections:
- **Red lights** → triage first
- **Decisions needed** → these are queued for you specifically
- **In-flight summary** → who's working on what
- **Green lights** → celebrate before the coffee kicks in

## 5. New blockers (5s)
```bash
ls memory/agent*_blocker_*.md 2>/dev/null
ls kanban/cards/*.md | xargs grep -l "status: blocked" 2>/dev/null
```
Any output → that agent is stuck, needs your call.

## 6. New CRITICAL security findings (5s)
```bash
grep -A2 "Severity: CRITICAL" SECURITY_AUDIT.md | head -30
```
If new CRITICALs surfaced overnight, the live-trading gate stays closed.

## 7. Round 1 completion gate (5s)
```bash
ls memory/agent*_round1_complete.md 2>/dev/null
```
Each completion file = one agent done with Round 1 and auto-loaded Round 2. 10 files = full swarm migrated.

## 8. Live-trading gate (5s)
```bash
# CRITICAL count from latest pentest
grep -c "Severity: CRITICAL" reports/pentest_*.md 2>/dev/null | tail -1
# Must be 0 before flipping the live switch
```

## 9. Cost burn (5s)
Open Grafana → Cost dashboard (Agent 10's deliverable). Or:
```bash
cat ./project_oracle/MANIFEST.json | python3 -c "import json,sys; m=json.load(sys.stdin); print(f'HF assets: {len(m.get(\"assets\", []))}')"
# Databento credit burn lives in qc/data/*_manifest.json files
```

## 10. New research / auto-port proposals (5s)
```bash
ls memory/auto_port_proposal_*.md 2>/dev/null
ls memory/author_alert_*.md 2>/dev/null
ls memory/weekly_digest_*.md 2>/dev/null
```
Agent 6's findings — review the proposals before merging.

---

## If you have 5 minutes

```bash
# Test count delta
backend/.venv/bin/python -m pytest backend/tests/ --tb=no -q 2>&1 | tail -3

# What committed overnight
git log --oneline --since="8 hours ago"

# Which agents pushed
git log --since="8 hours ago" --pretty=format:'%an %s' | sort | uniq -c
```

## If a CRITICAL or RED appears

1. **Truth audit red:** `cat qc/audit/truth_audit.sh` shows which rule. Find the offending commit. Either fix or revert. Block all other work.
2. **Agent blocked > 1h:** open its `kanban/cards/<id>.md`, read the blocker. If you can unblock, do it. Else mark the card BLOCKED and reassign work.
3. **Security CRITICAL:** Agent 7 finds something → live-trading gate stays closed. Don't flip the switch.
4. **Cost > 80% budget:** stop Agent 2 retraining loops and Agent 6 cloning loops first (they're the heavy spenders).

## When everything is green

```bash
# Pull latest, push your morning thoughts
git pull --rebase
# Decide which agent to dispatch into Round 3 (after Round 2 completes)
```

---

**Memory recovery path** (if your terminal is fresh):
1. `cat ~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md`
2. `cat DISPATCH_PLAN_ORACLE.md` (Round 1) + `DISPATCH_PLAN_ORACLE_ROUND2.md`
3. `cat kanban/SWARM_STATUS.md`

That's the full state restore in 3 commands.
