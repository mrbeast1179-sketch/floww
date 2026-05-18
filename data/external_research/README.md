# External research discovery

This folder is the staging area for research artifacts (papers, datasets,
code repositories) discovered from public sources before any are ingested
into the project's training pipeline.

## Why this exists

The current training data for our models is thin:

- Academic GEX dataset (`iAmGiG_gex-llm-patterns`): 167 labeled rows
- yfinance OHLCV per-ticker: ~2,800 rows × 6 tickers
- FlashAlpha sample chain: 26 rows (test fixture)

That's not enough to train production-quality models. More data → better
models. Rather than only generating data ourselves, we systematically find
what already exists on:

- **arxiv** — peer-reviewed quant research, especially recent papers on
  gamma exposure, options flow, market making, dealer positioning
- **Hugging Face Hub** — public datasets (financial sentiment, market
  data, news) and models pre-trained on financial text
- **GitHub topics** — open-source repos tagged `gamma-exposure`,
  `options-trading`, `quantitative-finance`, etc.
- **Federal Reserve / NBER / SSRN** — economic research, often with
  downloadable data appendices

## Workflow

```
sources.yaml  ──▶  discover_research.py  ──▶  discoveries_<date>.json
                                               (human/LLM review)
                                                       │
                                                       ▼
                                         data/github-repos/cloned/*
                                         or  Mongo collections
                                         (vetted, ingested)
```

1. **Curate sources** in `sources.yaml` — what to search for, where.
2. **Run discovery** (script lives at `scripts/discover_research.py` once
   wired — see TODO in `backend/services/research/discovery.py`).
   Produces a JSON manifest with normalized `Discovery` records.
3. **Vet** — humans (or a future LLM-based filter) score each discovery
   for: relevance, license compatibility, data quality.
4. **Ingest** the vetted subset — `git clone` for repos, append to Mongo
   for datasets, save PDFs to `data/papers/` for papers.

Discoveries are **never auto-ingested**. The `relevance_score` field on
every `Discovery` defaults to `None` until manually filled. This prevents
the "synthetic data" repeat: see `models/_quarantine/README.md` for what
happens when un-vetted data feeds a training pipeline.

## Currently implemented sources

| Source | Status | Notes |
|---|---|---|
| arxiv | ✅ wired (`ArxivSource`) | No auth, public API, 3s rate limit |
| HuggingFace Hub | ⏳ stub | Public search at `huggingface.co/api/datasets?search=...` |
| GitHub topics | ⏳ stub | Via `gh search repos --topic <topic>` |
| Semantic Scholar | not yet | API requires auth for high-rate use |
| SSRN | not yet | No public API; would need RSS scraping |
| Federal Reserve | not yet | Bulk download of FRED has Mongo-grade data |

## License hygiene

Every `Discovery` has a `license` field (often `None` — discovery is best-effort).
Before ingesting anything from this folder into the project:

- **arxiv preprints**: typically the author retains copyright, but most allow
  research use. Cite the arxiv id in any derived work.
- **Hugging Face datasets**: each has a stated license on its hub page —
  check before download.
- **GitHub repos**: respect the repo's LICENSE file. Some `quantitative-finance`
  repos are GPL — that constrains how we can use them.
- **When in doubt**: don't ingest. File a question in `BLOCKERS.md` instead.

## Manual additions

Some sources don't have APIs (SSRN, certain Fed releases). For those, add
entries directly to `discoveries_manual_<date>.json` in this folder, using
the same `Discovery` schema. The vetting pipeline treats manual and
auto-discovered entries identically.
