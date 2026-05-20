---
id: O-RESEARCH-LOOP
title: Continuous autonomous research loop
assignee: Agent 6
skill: research:arxiv + research:duckduckgo-search + gbrain:academic-verify + hermeshub:arxiv-watcher
estimate_hours: 6
dependencies: []
status: ready
last_update: 2026-05-19T20:30:00Z
commits: []
blockers: []
---

## Deliverable
Continuous research pipeline: arxiv discovery -> code-link extraction -> GitHub clone/dedupe -> pattern extraction -> HF Hub search -> 4-hour digests

## Files
- `data/external_research/*.json` + `*.md`
- `data/github-repos/cloned/*` (new clones)
- `memory/research_digest_<date>.md` (new daily)

## Loop
1. Discover arxiv papers
2. Extract code URLs
3. Clone repos, deduplicate
4. Extract patterns
5. HuggingFace Hub search every 2h
6. Daily digest every 4h

## Rate Limits
- <= 30 arxiv/hour
- <= 60 GH API/hour

## Acceptance Criteria
- [ ] Pipeline running continuously
- [ ] Rate-limit conscious
- [ ] Daily digest produced
- [ ] All commits conventional: `feat(research): ...`
