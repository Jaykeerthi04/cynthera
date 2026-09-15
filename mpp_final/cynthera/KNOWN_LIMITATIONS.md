# CYNTHERA — Known Limitations (Stable Release Candidate)

**Document Version:** 1.0  
**Backend Version:** Rule Set v3.2 (Phase 5.17 corrections applied)  
**Date:** 2026-09-06  

---

## Summary

This document records confirmed scientific or architectural limitations of the current CYNTHERA backend that were identified during the Phase 5.17 pre-implementation audit but are **not resolved in the stable release candidate** due to architectural complexity. Each limitation is described alongside its known impact and the condition under which it manifests.

---

## Limitation 1: Completed Negative Trials Invisible to CT.gov Adapter

**Severity:** Major  
**Affected module:** `backend/reasoning/opposition/therapeutic_opposition_assessor.py` → `trial_to_negative_claim()`  

### Description

The `trial_to_negative_claim()` function converts clinical trial records from ClinicalTrials.gov into negative opposition claims. It currently converts only trials with status:
- `TERMINATED_LACK_OF_EFFICACY` → `PredicateType.FAILED_TO_IMPROVE`
- `TERMINATED_SAFETY` → `PredicateType.TERMINATED_FOR_SAFETY`

**Pivotal negative trials that completed according to protocol** (not terminated early) are **invisible** to this adapter. Their CT.gov status is `COMPLETED`, not `TERMINATED_*`, so they produce zero opposition claims regardless of their primary endpoint results.

### Known Affected Cases

| Trial | CT.gov NCT | Drug | Disease | Outcome |
|-------|-----------|------|---------|---------|
| ACTIV-6 | NCT04885530 | Fluvoxamine | COVID-19 | No improvement in sustained recovery (NEJM 2022) |
| COVID-OUT | NCT04510194 | Fluvoxamine | COVID-19 | No significant benefit (NEJM 2022) |
| TOGETHER | NCT04727424 | Fluvoxamine | COVID-19 | Failed to replicate initial signal (Lancet 2021) |

### Impact

For Fluvoxamine → COVID-19 (CYN-109):
- CT.gov adapter contributes **0** negative claims (all trials `COMPLETED`)
- Opposition pipeline receives 0 trial-derived claims
- If literature extraction is also impaired (see Limitation 2), prediction defaults to `PROMISING` or `UNCERTAIN` instead of the scientifically correct `NOT_RECOMMENDED`

### Planned Resolution

Requires a new pipeline component that:
1. Fetches published primary endpoint results for `COMPLETED` trials
2. Classifies them as success/failure using LLM-assisted outcome classification
3. Converts confirmed failures to `FAILED_TO_IMPROVE` claims

This is architecturally complex and requires rate-limited LLM inference per trial. Targeted for a future integration phase.

### Workaround

The literature extraction pipeline (PubMed/Semantic Scholar) retrieves the published trial papers. If the LLM is available and extracts claims correctly, it will produce `FAILED_TO_IMPROVE` claims from the ACTIV-6 / COVID-OUT abstracts. The Phase 5.17 fix to the rule-based fallback negation guard reduces the probability of inversion (Limitation 2), but LLM extraction remains the primary path for detecting these cases.

---

## Limitation 2: LLM Claim Extraction Reliability Under Rate Limits

**Severity:** Moderate  
**Affected module:** `backend/reasoning/extraction/claim_extraction_agent.py`  

### Description

When all configured LLM providers (Groq, Gemini, OpenRouter, EdenAI) are unavailable or quota-exhausted, the `ClaimExtractionAgent` falls back to `_rule_based_fallback()` — keyword-based pattern matching. Claims produced by this fallback are:
- Low confidence (0.25)
- Explicitly marked `[keyword-extracted — LLM unavailable]` in `raw_text`
- Disclosed in `claim_extraction_method` field of `ReasoningResult`

**The Phase 5.17 fix** (negation guard + additional negative patterns) significantly reduces false-positive inversions. However, the rule-based fallback remains a best-effort heuristic that cannot replace LLM-verified claim extraction.

### Impact

When LLM providers are rate-limited or unavailable:
- Complex negation patterns not in the keyword list may still be incorrectly classified
- Support scores may be inflated by incorrect positive claims from keyword matching
- The system discloses the degraded extraction quality in `data_source_failures` and the audit report

### Mitigation

Configure at least one LLM provider in `.env`. The system supports a 4-tier cascade:
1. `GROQ_API_KEY` — primary (fastest, best rate limits)
2. `GEMINI_API_KEY` — secondary fallback
3. `OPENROUTER_API_KEY` — third fallback  
4. `EDENAI_API_KEY` — fourth fallback

---

## Limitation 3: 25-Case Benchmark Closed-World Assumption

**Severity:** Informational  
**Affected module:** `backend/evaluation/run_25_case_evaluation.py`  

### Description

The 25-case benchmark assigns `OPPOSE` to all unverified non-indications (6 Category B cases) using a closed-world assumption. This artificially suppresses the reported accuracy:

- **Closed-world accuracy:** 40% (standard benchmark evaluation)
- **Epistemic accuracy:** 56% (when Category B unverified pairs are reclassified as `UNCERTAIN`)

The 6 Category B cases (Metformin→Pancreatic Cancer, Furosemide→Depression, Warfarin→Leishmaniasis, Pregabalin→Breast Cancer, Tamsulosin→Liver Cancer, Imatinib→COVID-19) are not approved indications, but they also have **no documented contraindications or failed clinical trials**. The system correctly predicts `UNCERTAIN` for these cases, which is the epistemically correct outcome.

### Impact on Reported Metrics

Benchmark accuracy numbers should be interpreted with this context. The pipeline does not confuse "drug not indicated for disease" with "drug is harmful for disease."

---

## Limitation 4: Benchmark Runner vs. Evaluation Script Verdict Derivation

**Severity:** Minor (transparency only)  
**Affected module:** `backend/evaluation/benchmark_runner.py` vs. `backend/evaluation/run_25_case_evaluation.py`  

### Description

Two evaluation harnesses exist:
- `benchmark_runner.py`: derives prediction from `ta_dict['overall_alignment']` (directional therapeutic alignment)
- `run_25_case_evaluation.py`: derives prediction from `recommendation_status` (final rule-engine verdict)

These may produce slightly different confusion matrices because directional alignment and the recommendation rule engine are not always consistent.

### Planned Resolution

Reconcile both harnesses to a single canonical verdict source (`recommendation_status`) in a future phase.

---

*End of Known Limitations document. This document should be updated whenever new limitations are discovered or existing ones are resolved.*
