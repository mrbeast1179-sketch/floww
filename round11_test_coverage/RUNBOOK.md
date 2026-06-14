# RUNBOOK — what YOU (Nav) actually do. Almost nothing.

Everything is pre-written. You just copy a file to your clipboard and paste it into an agent. macOS `pbcopy` puts a file on your clipboard so you can ⌘V it.

## ⚠️ Do this FIRST (before launching any new agents)
You already have **5 open PRs** from another session waiting. New agents on top of an unreviewed pile = chaos. Tell me **"review the 5 PRs"** and I'll go through them, or merge the ones you trust. Clear the queue, THEN fan out.

## A) Launch Hermes agents (start with 4, not 10)
For EACH agent, run ONE line, then paste (⌘V) into a fresh Hermes agent and send. Start with the 4 trading-critical ones:

```bash
pbcopy < "/Users/nav/Documents/GitHub/floww/round11_test_coverage/rendered/agent_01.md"   # → paste into Hermes agent 1
pbcopy < "/Users/nav/Documents/GitHub/floww/round11_test_coverage/rendered/agent_02.md"   # → Hermes agent 2
pbcopy < "/Users/nav/Documents/GitHub/floww/round11_test_coverage/rendered/agent_03.md"   # → Hermes agent 3
pbcopy < "/Users/nav/Documents/GitHub/floww/round11_test_coverage/rendered/agent_04.md"   # → Hermes agent 4
```
Watch agents 1–4 actually push a branch and report green tests. **If they do, add the rest** (agent_05 … agent_10, same pattern). If they thrash/collide, stop and tell me — don't push through.

## B) Launch DeepSeek Pro (when freebuff is back up)
```bash
pbcopy < "/Users/nav/Documents/GitHub/floww/round11_test_coverage/DEEPSEEK_PRO_mypy_strict.md"   # → paste into DeepSeek Pro / freebuff
```
This is a 30-hour standing task (type-safety). It self-paces module by module. It can't break the backend (annotations only) and the gate is unfakeable.

## C) When agents report back
Just tell me **"agents pushed, review them"** (or paste their branch names). I'll: verify their tests actually pass (not just claimed), check they stayed in their lane, and merge the clean ones / kick back the bad ones. **Verifying their claims is my job, not yours.**

## That's the whole job for you
Copy a file → paste into an agent → tell me when they report. I do the review, merging, and coordination. You don't need to read the prompts or know the code.

---
### To view a prompt yourself (optional)
```bash
open -a TextEdit "/Users/nav/Documents/GitHub/floww/round11_test_coverage/rendered/agent_01.md"
# or open the whole folder in your editor:
open "/Users/nav/Documents/GitHub/floww/round11_test_coverage/rendered/"
```
