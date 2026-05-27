# A9 Deletion Verification (DS Pro post-mortem)

Per-name audit of A9's mass deletion at commit 7ec433f.

## Summary

- Total unique names deleted: 159 (classes, async defs, defs across backend/)
- Names with surviving references: 6
- Classification:
  - Already restored by A10 (8ac1f0e): 2 (AlertRule, AzureKeyVaultClient)
  - Restored by DS Pro (T2): 3 (AlertDispatcher, RateLimiter, FreeDataProvider, PolygonProvider)
  - STALE_IMPORT / lazy type hint (safe): 2 (AcknowledgeRequest, AnomalyExplanation)
  - Deferred to R10: 1 (AlphaVantageProvider — needs circuit breaker import reconciliation)

## ACTIVE_CALL — Restored in DS Pro session

| Name | Referenced in | A9-deleted-from | Action |
|------|---------------|-----------------|--------|
| AlertDispatcher | backend/services/alert_dispatcher.py:57 (`dispatcher = AlertDispatcher()`) | backend/services/alert_dispatcher.py | restored by DS Pro at b594b34 |
| RateLimiter | backend/data_providers.py:49 (`class RateLimiter`) | backend/data_providers.py | restored by DS Pro at 5b22845 |
| FreeDataProvider | backend/data_providers.py:65 (`class FinnhubProvider(FreeDataProvider)`) | backend/data_providers.py | restored by DS Pro at 5b22845 |
| PolygonProvider | backend/data_providers.py:213 (`self.polygon = PolygonProvider()`) | backend/data_providers.py | restored by DS Pro at 5b22845 |

## Already restored by A10 (8ac1f0e)

| Name | Referenced in | Verified |
|------|---------------|----------|
| AlertRule | backend/server.py:1758 | Present + importable |
| AzureKeyVaultClient | backend/config/secrets.py:52 | Present + importable |
| LocalEnvClient | backend/config/secrets.py | Present + importable |
| SecretResolver | backend/config/secrets.py | Present + importable |
| ConnectionManager | backend/services/websocket_streamer.py | Present + importable |
| StructuredFormatter | backend/services/logging_config.py | Present + importable |

## STALE_IMPORT / TYPE_HINT — Cleanup tickets for R10

| Name | Referenced in | Classification |
|------|---------------|----------------|
| AcknowledgeRequest | backend/routes/alerts_api.py:53 (`req: AcknowledgeRequest`) | TYPE_HINT — class missing but route lazy-loads, module imports OK |
| AnomalyExplanation | backend/services/anomaly_explainer.py:96 (`-> AnomalyExplanation`) | TYPE_HINT — module imports OK, return type only |

## Deferred to R10

| Name | Referenced in | Reason |
|------|---------------|--------|
| AlphaVantageProvider | backend/data_providers.py:214 (`self.alphavantage = AlphaVantageProvider()`) | Needs `circuit` breaker module import reconciliation (circuit var undefined in current file) |

## A10 recovery audit

A10 restored at 8ac1f0e: AlertRule, AzureKeyVaultClient, LocalEnvClient, SecretResolver, ConnectionManager, StructuredFormatter. Verified each still present + importable in current codebase.

## Hard precondition lesson for R10 READ-ONLY missions

A9's mass deletion incident demonstrates that READ-ONLY agents must be constrained by a hard precondition: grep for modifications to source files during the agent's lifetime; if any appear, the agent must halt. The current "scope section" in mission files is advisory, not enforcement.
