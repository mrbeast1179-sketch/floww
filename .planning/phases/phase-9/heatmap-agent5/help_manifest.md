---
lane: phase9/heatmap-agent5
kind: help-rag-manifest
updated: 2026-09-04
purpose: source of truth for help-layer RAG on the Heatseeker surfaces.
---

# Help RAG manifest — Heatseeker agent 5

This manifest is the boundary between the help layer and the live product. It is where this
agent records what it actually read and what it is willing to assert from that reading.

## Reading inventory (read in this session)

These URLs were retrieved and read:

1. https://www.skylit.ai/learn/category/heatseeker
2. https://www.skylit.ai/learn/reading-heatseeker
3. https://www.skylit.ai/learn/gamma-exposure
4. https://www.skylit.ai/learn/vanna-exposure
5. https://www.skylit.ai/learn/gex-vex-alignment
6. https://www.skylit.ai/learn/negative-gex
7. https://www.skylit.ai/learn/support-resistance-gex
8. https://www.skylit.ai/learn/gex-trading
9. https://www.skylit.ai/learn/vex-trading
10. https://www.skylit.ai/learn/options-flow
11. https://www.skylit.ai/learn/dealer-positioning
12. https://www.skylit.ai/learn/node-lifecycle

Catalog root: https://www.skylit.ai/sitemap.xml
Category root for Heatseeker: https://www.skylit.ai/learn/category/heatseeker

## Help-layer manifest meaning

For each row, the manifest records:
- what the subject is
- which top-level section of the catalog it belongs to
- what the page claims
- what the page is useful for in this implementation
- what the page is not a substitute for on this repo

## Operational rule

If a help topic later needs a fresh basis, re-read the source URL and either update the row or
remove it. A help file must never assert something from a URL the manifest does not reference.
