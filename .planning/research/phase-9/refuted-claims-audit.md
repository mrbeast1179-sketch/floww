# Refuted-Claims Audit — Agent 4 (2026-09-03)

**Scope searched (rg, case-insensitive, fixed strings):** frontend/src, backend/services,
backend/routes, backend/tests, docs, .planning. Excludes node_modules/.git.
**I do NOT edit copy — violations are reported with file:line for the owning lane.**

## 1. Checklist verdicts

| Claim | Verdict | Found in repo? |
|---|---|---|
| P&P 7–90 DTE band | REFUTED as attribution | No occurrence in product code (only correctly in planning docs as refuted) |
| Ni GX formula `gamma×DDOI×100×S²×0.01` as paper claim | REFUTED | See §2 — practitioner formula presented as paper methodology |
| Ni calls(+)/puts(−) sign rule | REFUTED as paper claim | See §2 (OI-signed gamma wrapped as "paper-accurate") |
| ΓIB-as-Barbon (`ΓIB = GEX/(S×ADSV)×100` as "Barbon-Buraschi Eq. 2") | UNVERIFIED/REFUTED as citation | backend/services/gex_paper_accurate.py:40 "1. Gamma Imbalance (% of ADV) — Barbon-Buraschi Eq. (2)" + formula derivation lines 40–50 |
| flip-as-academic (zero-gamma flip detection as Barbon–Buraschi) | REFUTED as paper claim | gex_paper_accurate.py:19 "2. Zero-Gamma Flip Distance — Barbon-Buraschi Section II.B" |
| Crash probabilities | REFUTED (association only, never calibrated) | gex_paper_accurate.py:24,428,447: `flash_crash_risk()` returns `crash_probability_estimate` with hardcoded 1%/3%/8%/18% bands; line ~1111 comment "flash crash probability ≈ 2-5x" |
| Phantom papers ("Ni et al. Option Market Maker Hedging and Stock Market Liquidity"; "Charming!/retail follow-up") | REFUTED (not found in indexes) | Not found in repo — clean |
| -$200mm folklore (GEX rarely < −$200mm as SqueezeMetrics claim) | REFUTED | No "-200mm"/"200mm" string in backend/services, docs, .planning (only correctly as folklore in planning docs) — clean |
| VPIN-from-snapshots | PROHIBITED as "VPIN" label | backend/routes/vpin.py (full VPIN API), backend/services/vpin_toxicity.py (bulk-volume VPIN over call/put volume buckets — NOT signed trade flow), backend/routes/microstructure.py:124, backend/routes/quant.py:124-136 ("VPIN-based market toxicity"), backend/routes/ensemble.py (VPIN+QI ensemble). FRONTEND COPY IS HONEST: FlowseekerProBlademap.jsx:1353,1948 correctly state VPIN/Kyle-λ need a trade-level feed (n/a on snapshot chains); ToxicityGauge.jsx:136 honest empty state |
| Dark pool buy/sell claims | PROHIBITED | None found in frontend/src, backend, docs — clean |
| Confirmed buyer/seller claims | PROHIBITED | None in product code (only in planning docs as prohibited-example text + CONTRACTS.md:48 "No confirmed buyer/seller identity. Ever.") — clean |
| True sweep claims without venue data | PROHIBITED | No "true sweep / confirmed sweep / sweep detected" in product code; only docs/superpowers spec line 94 correctly states true sweep needs OPRA-grade data — clean |
| "guaranteed" / "will move" / "institutional buying detected" | PROHIBITED | Zero hits in frontend/src — clean |

## 2. File:line violations requiring owner action

All in backend lane (Agent 3 / backend owner). Agent 4 proposes relabeling only:

1. backend/services/gex_paper_accurate.py:6 — "Ni, Pearson, Poteshman & White (2020)" — wrong year;
   journal version is RFS 34(4), April 2021. Fix: correct citation + note working-paper 2006 draft.
2. backend/services/gex_paper_accurate.py:11-19 — module docstring presents practitioner GEX wrapper as
   "the paper-prescribed normalizations and decompositions" and "academic risk metrics proven in the
   literature". Fix: relabel as practitioner constructions "in the spirit of" the papers; cite Ni §1
   mechanism only for sign-of-gamma zones.
3. backend/services/gex_paper_accurate.py:40-50 — "Barbon-Buraschi Eq. (2)" with ×100 scaling the
   docstring itself admits differs ~13× from paper scale. Fix: drop "Eq. (2)" attribution or verify
   against full text; label ours.
4. backend/services/gex_paper_accurate.py:19 (:19 in docstring list) + flip function — "Barbon-Buraschi
   Section II.B" zero-gamma flip. Section refs unverified (full text not opened — abstract-only).
   Fix: remove section numbers until verified; label flip a practitioner level.
5. backend/services/gex_paper_accurate.py:24,428-470 — `flash_crash_risk()` / "Flash Crash Probability
   Proxy — Barbon-Buraschi Sec. III.C" returning `crash_probability_estimate` (1/3/8/18% bands).
   REFUTED: paper shows association only. Fix: replace numeric probability with fragile/stable tag;
   keep "Table V ~16bp High-Low" as context only if verified. Highest severity.
6. backend/routes/vpin.py, backend/services/vpin_toxicity.py:55 (`push_bucket(call_vol, put_vol, ...)`),
   backend/routes/quant.py:124-136, backend/routes/ensemble.py — snapshot/bucket volume imbalance
   served under the name "VPIN". Per Easley-Lopez de Prado-O'Hara 2012 §§2–3, VPIN requires signed
   volume-time buckets. Fix: rename served metric "toxicity proxy (not VPIN)" everywhere user-visible;
   keep engine internals but quarantine the label. Note: frontend already does this correctly.

## 3. Clean areas (explicitly verified, no action)

- frontend/src: no "guaranteed", no "will move", no "institutional buying detected", no dark-pool
  directional language, no confirmed-buyer language. VPIN mentions are honest n/a-on-snapshot disclaimers.
- No P&P band / $25k / 3×OI citations in product code.
- No phantom-paper citations anywhere.

## 4. Recommended product changes (for CONTRACT_REQUESTS / backend owner)

- R1 (P0): kill numeric `crash_probability_estimate` from API responses; serve fragility tag.
- R2 (P0): rename all user-facing "VPIN" to "toxicity proxy"; add "requires signed flow for true VPIN" footnote.
- R3 (P1): fix Ni year (2020→2021 RFS) and strip unverified "Eq./Sec./Table" numbers from gex_paper_accurate.py
  docstrings; file exact replacement patch via Agent 3 workstream (B8).
- R4 (P2): add copy-checklist CI grep (terms in §1) to block regressions.
