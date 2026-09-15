# CYNTHERA — TC-062 ROOT-CAUSE FIX AUDIT REPORT
## Fix Approval Anchor Selection + Remove Targeted Override + Verify Evaluator Parity

**Audit Date**: September 11, 2026  
**Target Case**: TC-062 (`Ranibizumab` $\rightarrow$ `Age-related macular degeneration`)  
**Status**: COMPLETE — ALL GATES PASS  

---

## 1. Confirmed Root Cause

Forensic tracing of TC-062 confirmed that the failure of Ranibizumab to reach `SUPPORT` was **NOT** an opposition assessor issue. 

NCT02611778 is correctly classified as:
- `qualification_category`: `BIOSIMILAR_EQUIVALENCE_FAILURE`
- `qualified`: `False`
- `opposition_score`: `0.0`
- `independent_groups`: `0`

The root cause was located in approval-anchor selection in:
```
backend/engineering/retrieval/pipeline.py :: RetrievalPipeline._parse_indication_data()
```

### Mechanism of Failure:
For Ranibizumab (`CHEMBL1201825`), ChEMBL contains multiple indication records:
1. `"age-related macular degeneration"`: `max_phase_for_ind = 3`, `sim = 1.0`
2. `"wet macular degeneration"`: `max_phase_for_ind = 4`, `sim = 0.40`

The previous implementation ranked candidates primarily by lexical token similarity (`candidate_rank = sim`). Consequently, the exact Phase-3 lexical match shadowed the Phase-4 approved indication. Because the selected indication had `max_phase = 3`, `is_approved` evaluated to `False`. As a result:
- `Rule -1 (APPROVED INDICATION RESOLUTION)` could not fire.
- Evaluation fell through to `Rule 1c (LITERATURE SIGNAL WITHOUT THERAPEUTIC ANCHOR)`.
- The final classification became `UNCERTAIN`.

The targeted evaluator previously achieved `SUPPORT` solely because of an ad-hoc override that injected `"wet macular degeneration"` when `cid == "TC-062"` or `drug.lower() == "ranibizumab"`.

---

## 2. Exact Function Modified

- **File**: `backend/engineering/retrieval/pipeline.py` (synced in both workspace root and `mpp_final/cynthera/`)
- **Function**: `RetrievalPipeline._parse_indication_data(self, indication_data, molecule_data, disease_name, source="chembl") -> ApprovalSignal | None`

---

## 3. Old vs. New Candidate Selection Behavior

### Old Behavior:
```python
sim = len(intersection) / len(union)
if q_clean in t_clean or t_clean in q_clean:
    sim = max(sim, 0.6)
if variant != disease_name:
    sim *= 0.95

if sim > best_match_confidence:
    best_match_confidence = sim
    best_match_term = term
    best_match_phase = max_phase
    best_match_variant = variant
```
*Effect*: Pure similarity ranking allowed investigational records (Phase 3) with exact lexical matches to shadow lower-similarity FDA-approved records (Phase 4).

### New Behavior:
```python
# Disease Relation Gate (§8 & §24):
# Sibling exclusions strictly reject approval anchor candidates
orig_rel = classify_disease_relation(disease_name, term)
variant_rel = classify_disease_relation(variant, term)
if orig_rel == DiseaseRelation.SIBLING_EXCLUDED or variant_rel == DiseaseRelation.SIBLING_EXCLUDED:
    continue

# Rule -1 requires DiseaseRelation.SAME (Section 6 & 8)
is_anchor = matches_for_approval_anchor(disease_name, term) or (
    variant != disease_name and matches_for_approval_anchor(variant, term)
)
if not is_anchor:
    continue

sim = len(intersection) / len(union)
if q_clean in t_clean or t_clean in q_clean:
    sim = max(sim, 0.6)
if variant != disease_name:
    sim *= 0.95

# Deterministic ranking among eligible candidates (DiseaseRelation.SAME):
# Prioritize confirmed approved indications (Phase 4) over lower phases.
# When phase status is equal, break ties using similarity.
candidate_rank = (max_phase == 4, max_phase, sim)
best_rank = (best_match_phase == 4, best_match_phase, best_match_confidence)
if candidate_rank > best_rank:
    best_match_confidence = sim
    best_match_term = term
    best_match_phase = max_phase
    best_match_variant = variant
```

*Guardrail*: Unrelated Phase 4 indications are excluded prior to ranking via `matches_for_approval_anchor()`. The Phase 4 preference operates exclusively inside the eligible approval-anchor set.

---

## 4. Exact Selected Phase-4 Indication for TC-062

- **Queried Disease**: `Age-related macular degeneration`
- **Selected ChEMBL Indication Term**: `wet macular degeneration`
- **Selected Indication Phase**: `4` (FDA Approved)
- **Approval Confidence**: `0.40`
- **Approval Anchor Detected**: `True` (`DiseaseRelation.SAME`)

---

## 5. Removal of All TC-062 Workarounds

All ad-hoc conditionals matching `TC-062`, `ranibizumab`, or hardcoded `"wet macular degeneration"` in evaluation and validation code were identified and permanently eliminated:

1. `backend/evaluation/run_50_case_post_clinicaltrials_fast.py`:
   - Removed ad-hoc fallback branches; approval anchor resolution now uniformly uses:
     ```python
     m_term = re.search(r"Matched ChEMBL term: '([^']+)'", baseline_rule)
     matched_term = m_term.group(1) if m_term else (b.get("matched_indication_term") or None)
     is_anchor = matches_for_approval_anchor(disease, matched_term) if matched_term else False
     ```
2. `scratch/audit_p0b2_1_targeted.py`:
   - Removed `or (cid == "TC-062")` and `if drug.lower() == "ranibizumab"`.

All evaluators now derive approval status canonically from the pipeline.

---

## 6. Canonical Regeneration of `results.jsonl`

In accordance with requirement 1 & 6:
- **No manual text edit** of `evaluation_outputs/100_case_final/results.jsonl` was performed.
- TC-062 was executed through the canonical `MasterOrchestrator.evaluate()` / `evaluate_case()` execution path.
- The resulting structured record was verified and written to `results.jsonl` (both workspace root and `mpp_final/`).

---

## 7. TC-062 End-to-End Production Trace

```text
case_id:                     TC-062
drug:                        Ranibizumab
disease:                     Age-related macular degeneration

selected_indication_term:    wet macular degeneration
selected_indication_phase:   4
approval_anchor_detected:    True
approval_confidence:         0.40

opposition_score:            0.000
opposition_level:            NONE
independent_groups:          0
qualified_negative_claims:   0

rule_0:                      bypassed (RS = 0.000 <= 0.6)
rule_1b:                     bypassed (no conflict)
rule_1c:                     bypassed (is_approved = True)
rule_2b:                     bypassed (opp_score = 0.000 < 0.45)
rule_minus_1:                FIRED (APPROVED INDICATION RESOLUTION)

recommendation_status:       PROMISING
prediction:                  SUPPORT
decision_rule:               Rule -1 (APPROVED INDICATION RESOLUTION): Approved therapeutic anchor confirmed. All safety, empirical opposition, and conflict evaluations passed. Confirmed PROMISING under approved indication pathway.
```

---

## 8. Evaluator Parity Results (Section 9)

| Evaluation Path | Prediction | Recommendation Status | Opposition Score | Approved Anchor | Deciding Rule |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Production Orchestrator** | `SUPPORT` | `PROMISING` | `0.000` | `True` | `Rule -1 (APPROVED INDICATION RESOLUTION)` |
| **Fast Evaluator** | `SUPPORT` | `PROMISING` | `0.000` | `True` | `Rule -1 (APPROVED INDICATION RESOLUTION)` |
| **Benchmark Runner** | `SUPPORT` | `PROMISING` | `0.000` | `True` | `Rule -1 (APPROVED INDICATION RESOLUTION)` |
| **Targeted Evaluator** | `SUPPORT` | `PROMISING` | `0.000` | `True` | `Rule -1 (APPROVED INDICATION RESOLUTION)` |

**Parity Result**: 4/4 paths exhibit identical semantic state, score, and deciding rule.  
**Deciding Rules Unique Count**: `1` (`Rule -1 (APPROVED INDICATION RESOLUTION)`).

---

## 9. Required Before/After Table (Section 16)

| Case ID | Before Pred | After Pred | Opp Score Before | Opp Score After | Approval Before | Approval After | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **TC-062** (Ranibizumab $\rightarrow$ AMD) | `UNCERTAIN` | `SUPPORT` | 0.000 | 0.000 | `False` | `True` | **RECOVERED TO SUPPORT** |
| **TC-001** (Lisinopril $\rightarrow$ HTN) | `SUPPORT` | `SUPPORT` | 0.000 | 0.000 | `True` | `True` | **PRESERVED** |
| **TC-003** (Budesonide $\rightarrow$ Asthma) | `SUPPORT` | `SUPPORT` | 0.000 | 0.000 | `True` | `True` | **PRESERVED** |
| **TC-026** (Niacin $\rightarrow$ CVD) | `UNCERTAIN` | `UNCERTAIN` | 0.567 | 0.567 | `True` | `True` | **PRESERVED (Rule 1b)** |
| **TC-030** (Dexamethasone $\rightarrow$ TBI) | `OPPOSE` | `OPPOSE` | 0.567 | 0.567 | `False` | `False` | **PRESERVED (Rule 2b)** |
| **TC-052** (Nivolumab $\rightarrow$ GBM) | `OPPOSE` | `OPPOSE` | 0.567 | 0.567 | `False` | `False` | **PRESERVED (Rule 2b)** |
| **TC-024** (Aspirin $\rightarrow$ Hemorrhagic Stroke) | `OPPOSE` | `OPPOSE` | 0.000 | 0.000 | `False` | `False` | **PRESERVED (Rule 0)** |
| **TC-022** (HCQ $\rightarrow$ COVID-19) | `UNCERTAIN` | `UNCERTAIN` | 0.749 | 0.749 | `False` | `False` | **PRESERVED (Rule 1b)** |

---

## 10. Regression Checks: TC-026 and TC-030

- **TC-026 (Niacin $\rightarrow$ CVD)**:
  - Qualification: `DIRECT_THERAPEUTIC_FAILURE`
  - Opposition Score: `0.567` (1 independent group)
  - Approved Anchor: `True`
  - Decision: `Rule 1b (APPROVED INDICATION vs ISOLATED EMPIRICAL OPPOSITION CONFLICT)`
  - Final State: `UNCERTAIN` (**PASS** — isolated-conflict policy preserved)

- **TC-030 (Dexamethasone $\rightarrow$ TBI)**:
  - Qualification: `DIRECT_THERAPEUTIC_FAILURE`
  - Opposition Score: `0.567` (1 independent group)
  - Approved Anchor: `False`
  - Decision: `Rule 2b (EMPIRICAL OPPOSITION VETO)`
  - Final State: `OPPOSE` (**PASS**)

---

## 11. Unit Test Results

Executed in strict order as specified in Section 15:

1. `pytest tests/unit/test_evaluator_rule_engine_parity.py`: **18 passed** (including `test_tc062_all_evaluators_have_identical_final_state`).
2. `pytest tests/unit/test_semantic_opposition_qualification.py`: **19 passed** (including biosimilar equivalence audit and Section 9 parity test).
3. `pytest tests/unit/test_approval_candidate_selection.py`: **4 passed** (covering Cases A, B, C, and D).
4. `pytest tests/unit/`: **752 passed, 0 failed**.

---

## 12. Safety Invariants Confirmed

- **Opposition Mathematics**: Unchanged ($\text{best\_w} \times (1 - 0.30/n)$).
- **Decision Thresholds**: Unchanged (Rule 2b threshold remains 0.45; Rule 1b conflict bounds unchanged).
- **Benchmark Labels**: Unchanged.
- **Results.jsonl**: Canonical pipeline regeneration used; zero manual text manipulation.
- **Generic Applicability**: Zero drug-specific or case-specific overrides remain.

---

## 13. Success Gate Evaluation

| Gate | Status | Evidence |
| :--- | :---: | :--- |
| `TC062_ROOT_CAUSE_CONFIRMED` | **PASS** | Phase 3 exact match confirmed shadowing Phase 4 approval record |
| `APPROVAL_ANCHOR_SELECTION_FIXED` | **PASS** | Gated by `matches_for_approval_anchor()`, Phase 4 prioritized |
| `TC062_PARITY` | **PASS** | 4-path evaluator test passes with identical decision rule |
| `TC062_FINAL_SUPPORT` | **PASS** | `prediction = SUPPORT`, `recommendation = PROMISING` across all paths |
| `TC026_REGRESSION` | **PASS** | Niacin $\rightarrow$ CVD remains `UNCERTAIN` via Rule 1b |
| `TC030_REGRESSION` | **PASS** | Dexamethasone $\rightarrow$ TBI remains `OPPOSE` via Rule 2b |
| `P0B2_SENTINELS` | **PASS** | TC-001, TC-003, TC-024, TC-052, TC-022 all unchanged |
| `UNIT_SUITE` | **PASS** | 752/752 tests passing |
| `NO_CASE_SPECIFIC_OVERRIDE` | **PASS** | Zero ad-hoc case/drug branches |

**Overall Result**:
```
TC062_GATE = READY_FOR_IMATINIB_DIAGNOSTIC
```
