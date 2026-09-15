# CYNTHERA Final Validation

## 1. Version
- Commit: fcf283d8f58c6b48718ee747bbb7fcd61e10c728
- Branch: main
- Python: 3.12.7 (tags/v3.12.7:0b05ead, Oct 1 2024, 03:06:41) [MSC v.1941 64 bit (AMD64)]
- Dependencies: Pydantic 2.13.4, FastAPI 0.141.1, HTTPX 0.28.1, Streamlit 1.63.0, Plotly 7.0.0
- Benchmark: 100-Case Stratified Benchmark (manifest_100_cases.json / evaluation_outputs/100_case_final/results.jsonl)
- Evaluator: backend/evaluation/run_100_case_evaluation.py
- LLM: Groq llama-3.1-8b-instant (404 model_not_found fallback to deterministic keyword extraction)
- Retrieval policy: RetrievalPolicy.STANDARD
- Cache mode: EvaluationCache + RawResponseCache enabled (SQLite), bypass_cache=False

## 2. Test Suite
- Total: 312
- Passed: 234
- Failed: 78
- Skipped: 0
- Errors: 0
- Test Duration: 9.11s

## 3. Final Benchmark Results

### Standard Ground Truth (Regulatory / Standard Reference)

| Metric | Result |
|---|---:|
| Accuracy | 0.5600 |
| Balanced Accuracy | 0.4764 |
| Macro Precision | 0.5057 |
| Macro Recall | 0.4764 |
| Macro F1 | 0.3911 |
| Weighted F1 | 0.6102 |
| MCC | 0.3328 |

### Epistemic Ground Truth (Directional Evidence-Grounded Reference)

| Metric | Result |
|---|---:|
| Accuracy | 0.6200 |
| Balanced Accuracy | 0.5877 |
| Macro Precision | 0.5597 |
| Macro Recall | 0.5877 |
| Macro F1 | 0.4853 |
| Weighted F1 | 0.6367 |
| MCC | 0.4036 |

## 4. Confusion Matrix

### Standard Ground Truth Confusion Matrix

| Actual \ Predicted | SUPPORT | OPPOSE | UNCERTAIN | Total |
|---|---:|---:|---:|---:|
| **Actual SUPPORT** | 49 | 4 | 10 | 63 |
| **Actual OPPOSE** | 3 | 5 | 25 | 33 |
| **Actual UNCERTAIN** | 2 | 0 | 2 | 4 |
| **Total Predicted** | 54 | 9 | 37 | 100 |

### Epistemic Ground Truth Confusion Matrix

| Actual \ Predicted | SUPPORT | OPPOSE | UNCERTAIN | Total |
|---|---:|---:|---:|---:|
| **Actual SUPPORT** | 49 | 4 | 10 | 63 |
| **Actual OPPOSE** | 3 | 5 | 19 | 27 |
| **Actual UNCERTAIN** | 2 | 0 | 8 | 10 |
| **Total Predicted** | 54 | 9 | 37 | 100 |

## 5. Per-Class Performance

### Standard Ground Truth

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| **SUPPORT** | 0.9074 | 0.7778 | 0.8376 | 63 |
| **OPPOSE** | 0.5556 | 0.1515 | 0.2381 | 33 |
| **UNCERTAIN** | 0.0541 | 0.5000 | 0.0976 | 4 |

### Epistemic Ground Truth

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| **SUPPORT** | 0.9074 | 0.7778 | 0.8376 | 63 |
| **OPPOSE** | 0.5556 | 0.1852 | 0.2778 | 27 |
| **UNCERTAIN** | 0.2162 | 0.8000 | 0.3404 | 10 |

## 6. CYNTHERA-Specific Validation

- Evidence traceability: 100% of generated claims and clinical trials carry explicit provenance records (source name, record_id/NCT, canonical source URL).
- Mechanistic path coverage: 58/100 cases traced multi-hop mechanistic chains connecting Drug -> Target -> [Reaction/Pathway] -> Gene -> Disease.
- Clinical evidence handling: Verified attribution of 20 clinical trials per case where available. Negative efficacy outcomes correctly qualified under Phase 5 semantic rules.
- Contradiction handling: Conflicting signals preserve distinction between supporting and opposing evidence; opposition score explicitly computed without flattening into an average.
- Source provenance: Canonical URLs verified for ChEMBL, UniProt, Reactome, Open Targets, ClinicalTrials.gov, and PubMed.
- Serialization: 100% of completed evaluations serialized consistently to results.jsonl and SQLite database without data corruption.
- API: Endpoints POST /api/analyze, GET /api/analyze/{id}, GET /api/analyze/{id}/evidence, GET /api/analyze/{id}/report, and GET /api/analyze/{id}/report/pdf implemented in backend/api/analyze_routes.py.
- PDF reporting: PDFReporter generates structured 15-section PDF reports via ReportLab.
- Playground: Multi-hop graph layout, dynamic edge disablement without mutating canonical evaluation, and honest Mechanistic-Score-only scenario recomputation verified by automated unit tests (tests/unit/test_subgraph_extractor.py, test_scenario_engine.py: 5/5 passed).

## 7. Representative End-to-End Cases

| Case ID | Drug | Disease | Category | Std Gold | Pred Verdict | Recommendation | SS | MS | RS | Opp | Notes |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---|
| **TC-001** | Lisinopril | Hypertension | Cat A: Clear Positive | SUPPORT | SUPPORT | PROMISING | 0.991 | 0.490 | 0.000 | 0.000 | Primary positive control; ACE inhibition validated. |
| **TC-072** | Empagliflozin | Heart failure | Cat F: Multi-target / CV | SUPPORT | SUPPORT | PROMISING | 0.970 | 0.402 | 0.259 | 0.319 | SGLT2 inhibitor; metabolic/CV multi-target synthesis. |
| **TC-026** | Niacin | Cardiovascular disease | Cat B: Negative / Failed | OPPOSE | OPPOSE | NOT_RECOMMENDED | 0.985 | 0.000 | 0.259 | 0.512 | AIM-HIGH clinical trial failure qualified as genuine opposition. |
| **TC-021** | Ivermectin | COVID-19 | Cat B: Negative / Failed | OPPOSE | UNCERTAIN | UNCERTAIN | 0.989 | 0.000 | 0.451 | 0.629 | Literature present but trials lack efficacy; correctly prevented from False-Promising. |
| **TC-041** | Etanercept | Sepsis | Cat C: Contradiction / Safety | OPPOSE | UNCERTAIN | UNCERTAIN | 0.984 | 0.000 | 0.213 | 0.000 | Conflicting cytokine evidence; trials demonstrate lack of survival benefit. |
| **TC-019** | Imatinib | Chronic myeloid leukemia | Cat A: Clear Positive | SUPPORT | UNCERTAIN | UNCERTAIN | 0.988 | 0.479 | 0.000 | 0.000 | BCR-ABL multi-hop chain present; gate held at uncertain due to strict literature threshold. |

## 8. Reproducibility

### Environment Setup
`ash
git checkout fcf283d8f58c6b48718ee747bbb7fcd61e10c728
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
`

### Execution Commands
1. Run Automated Test Suite:
   `ash
   python -m pytest tests/ -q --tb=no
   `
2. Run Benchmark Evaluation:
   `ash
   python backend/evaluation/run_100_case_evaluation.py
   `
3. Generate Metrics Ledger:
   `ash
   python scratch/generate_validation_artifacts.py
   `

## 9. Final Status

FINAL VALIDATION BLOCKED

### Blocking Issues:
1. **Automated Test Suite Failures (78/312 failed)**:
   - Root cause: Domain model files ackend/core/domain/clinical_trial.py and ackend/core/domain/approval_signal.py in the root repository are missing fields (why_stopped on ClinicalTrial, and kwargs on rom_chembl_indication_match) that were updated in mpp_final/cynthera/ but not synchronized during commit cf283d.
2. **Groq Model Identifier Deprecation**:
   - ClaimExtractionAgent specifies deprecated model llama-3.1-8b-instant, returning HTTP 404 from the Groq API and causing LLM claim extraction to fall back to keyword matching.
3. **Multi-Hop Path Confidence Threshold**:
   - _MIN_CONFIDENCE = 0.01 in multi_hop_reasoner.py filters out valid 4-to-5 hop biological mechanism paths whose decayed confidence falls between 0.001 and 0.006, leaving cases like metformin -> PCOS with MS = 0.000 unless calibrated.
