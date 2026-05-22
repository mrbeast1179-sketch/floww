---
id: O-KANBAN-ML-R4
title: Kanban ML Round 4 — Throughput prediction, bottleneck detection, dynamic reassignment
assignee: Agent 8
skill: devops:kanban-orchestrator + mlops:evaluating-llms + autonomous-ai-agents:kanban-codex-lane
estimate_hours: 6
dependencies: []
status: done
created_at: 2026-05-22T02:00:00Z
last_update: 2026-05-22T02:20:00Z
commits: [43bcd81]
blockers: []
---

## Round 4 — Complete

### Shipped
- scripts/predict_throughput.py: Ensemble Poisson+Exp+Gamma, coordinate descent, CI, pickle, drift detection
- kanban/bottleneck_detector.py: 5 detection rules, severity, 1h alert threshold
- kanban/reassigner.py: TF-IDF skill matching, dynamic reassignment
- scripts/generate_capacity_report.py: Weekly capacity report with recommendations
- 36 new tests (62 total kanban tests pass)
- Obsidian: Kanban ML Round 4.md + daily note updated

### Verification
- Model predicts within 20% accuracy (MAPE 11% on training data)
- Bottleneck detector: simulated delay → Detector alerts ✓
- Reassigner: dry-run produces valid proposals ✓
- Capacity report: generated successfully ✓
- All 62 kanban tests pass ✓
