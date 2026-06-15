# Round 11 — Lane Assignments (10 agents, 20 untested services)

Each agent owns a disjoint set of NEW test files → zero file collisions. Branches isolate commits.
Priority P1 = trading-critical (do these first if running fewer than 10).

| Agent | Branch | Services (create `tests/.../test_<name>.py`) | ~src lines | Pri |
|---|---|---|---|---|
| 01 | `round11/agent-01-paper` | `services/paper_trading.py`, `services/position_reconciler.py` | 298 | **P1** |
| 02 | `round11/agent-02-alerts` | `services/alert_dispatcher.py`, `services/audit_trail.py` | 219 | **P1** |
| 03 | `round11/agent-03-mlfeat` | `services/ml_realtime_features.py` | 421 | **P1** |
| 04 | `round11/agent-04-mlinfra` | `services/ml/health_monitor.py`, `services/ml/gex_inference.py` | 465 | **P1** |
| 05 | `round11/agent-05-stream` | `services/websocket_streamer.py`, `services/logging_config.py`, `services/graph_updater.py` | 176 | P2 |
| 06 | `round11/agent-06-kgraph` | `services/research/knowledge_graph.py` | 440 | P2 |
| 07 | `round11/agent-07-kanban` | `services/kanban/throughput_model.py`, `services/kanban/multi_repo.py` | 419 | P3 |
| 08 | `round11/agent-08-hub` | `services/agentfield_hub.py` | 293 | P3 |
| 09 | `round11/agent-09-memory` | `services/memory/code_embeddings.py`, `services/memory/chart_embeddings.py`, `services/memory/voice_embeddings.py` | 418 | P3 |
| 10 | `round11/agent-10-causal` | `services/causal/ate_estimator.py`, `services/backtest/report.py`, `services/backtest/retail_flow_signal.py` | 552 | P2 |

Test file location: mirror the source path under `tests/`. E.g. `services/ml/gex_inference.py` → `tests/services/ml/test_gex_inference.py`; `services/paper_trading.py` → `tests/services/test_paper_trading.py`. Match the `sys.path.insert` depth of the nearest existing sibling test.

## Launcher (Nav runs)
Each agent's full prompt = `PREAMBLE.md` + its row above + `TEMPLATE.md`. Concretely, for agent NN:
```bash
cd /Users/nav/Documents/GitHub/floww/round11_test_coverage
{ cat PREAMBLE.md; echo; echo "## YOUR LANE: agent-NN"; echo "<paste the table row>"; echo; cat TEMPLATE.md; } | pbcopy
# → paste into Hermes agent NN
```
Run P1 lanes (01–04) first to validate the protocol on one or two agents before fanning out all 10. After they push, the owner (me) reviews each branch, triages FINDINGS, and merges green ones.
