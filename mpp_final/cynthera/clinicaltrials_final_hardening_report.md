# CYNTHERA — FINAL PRE-BENCHMARK HARDENING REPORT
**Date:** September 9, 2026  
**Status:** COMPLETE & VERIFIED  
**Benchmark Execution Status:** HELD (DO NOT RUN 100-CASE BENCHMARK YET)

---

## 1. Executive Summary

Following the adversarial audit of the ClinicalTrials.gov and disease-relation pipeline, three primary vulnerabilities and potential bypasses were identified and addressed:
1. **Empty-condition bypass in `matches_disease_condition()`:** Trials with `condition_names = []` formerly bypassed relation classification and defaulted to `True`.
2. **Unresolved combination contrast attribution bypass:** Multi-agent contrasts ($A+B$ vs $C+D$) could erroneously become attributable if the termination rationale (`whyStopped`) explicitly mentioned the candidate drug, despite the trial design lacking a valid differentiating contrast (`is_diff=False`).
3. **Ontological sibling / subtype leakage:** Stroke vs Hemorrhagic Stroke and TBI vs Chronic Subdural Hematoma required unified, strict enforcement across both approval anchors (Rule -1) and trial attribution.

All corrections have been implemented under a strict **freeze** on scores, weights, thresholds, formulas, and benchmark labels. All 682 production unit tests and 44 targeted hardening tests pass with 100% success. Live checks across the 6 specified target drug-disease pairs confirm that the system is safe, stable, and ready for benchmarking.

---

## 2. Files Changed & Exact Implementation Details

### A. Production Code

1. [therapeutic_opposition_assessor.py](file:///c:/Users/win10/Documents/cynthera/mpp_final/cynthera/backend/reasoning/opposition/therapeutic_opposition_assessor.py)
   - **Eliminated Empty-Condition Bypass (§1):**
     - Removed `if not conditions: return True` at lines 686–689.
     - Enforced that when `condition_names` is empty or does not match, execution falls back strictly to the trial `title`.
     - In title fallback:
       - Sibling exclusions (`_SIBLING_EXCLUSIONS`) are evaluated first and bidirectionally; any match immediately returns `False`.
       - `classify_disease_relation(queried_disease, title)` and `matches_for_trial_attribution(queried_disease, title)` are executed.
       - Entity-level parent-child (`_PARENT_CHILD`), canonical synonym (`_CANONICAL_SYNONYMS`), and word-bounded exact query terms are evaluated.
       - Any unrelated title returns `False`.
   - **Hardened Unresolved Combination Attribution (§3):**
     - In `analyze_trial_drug_role()`: Expanded multi-arm comparison to detect when active comparator agents exist that do not match the experimental arm (`diff_ctl_agents`). When present, marked as an `"unresolved multi-agent contrast"` with `is_diff = False`.
     - In `evaluate_trial_attribution()`:
       - If `role == TrialDrugRole.EVALUATED_COMBINATION_COMPONENT` and `not is_diff`:
         - If the contrast is an `"unresolved multi-agent contrast"` (e.g. $A+B$ vs $C+D$), `final_decision` is **strictly `False`**, even if `whyStopped` explicitly names the drug (`EXPLICIT_DRUG_ATTRIBUTION`).
         - If the contrast is against `Placebo` ($A+B$ vs Placebo) and termination text explicitly names the drug, attribution is permitted; generic failure without drug attribution is strictly rejected.
   - **Import Integration:** Imported `_PARENT_CHILD` directly from `backend.engineering.retrieval.disease_relation`.

2. [disease_relation.py](file:///c:/Users/win10/Documents/cynthera/mpp_final/cynthera/backend/engineering/retrieval/disease_relation.py)
   - **Curated Ontology Enhancement (§2):**
     - Added `"stroke"` to `_PARENT_CHILD["cardiovascular disease"]` so vascular stroke trials correctly map to the broader cardiovascular disease hypothesis in clinical trial attribution, while preserving strict sibling exclusion (`"stroke": {"hemorrhagic stroke"}`).
     - Added canonical synonyms:
       - `"secondary prevention of cardiovascular disease": "cardiovascular disease"`
       - `"secondary prevention of stroke": "stroke"`

### B. Test Suites Updated

1. [test_clinicaltrials_safe_fixes.py](file:///c:/Users/win10/Documents/cynthera/mpp_final/cynthera/tests/unit/test_clinicaltrials_safe_fixes.py)
   - Added all 7 required adversarial tests (A through G):
     - `test_hardening_a_empty_conditions_sibling_title_rejected`
     - `test_hardening_b_empty_conditions_parent_child_title_matched`
     - `test_hardening_c_unresolved_combination_is_diff_false`
     - `test_hardening_d_unresolved_combination_whystopped_not_attributable`
     - `test_hardening_e_stroke_vs_hemorrhagic_stroke_strict_veto`
     - `test_hardening_f_metformin_background_protection_preserved`
     - `test_hardening_g_nivolumab_placebo_remains_non_match`
2. [test_trial_attribution.py](file:///c:/Users/win10/Documents/cynthera/mpp_final/cynthera/tests/unit/test_trial_attribution.py)
   - Updated test helper `_build_trial()` to accept `condition_names` parameter to eliminate reliance on the former empty-conditions bypass.
   - Updated `test_a`, `test_e`, and `test_niacin_aim_high_trial_attributed` to pass explicit condition metadata.
3. [test_therapeutic_opposition.py](file:///c:/Users/win10/Documents/cynthera/mpp_final/cynthera/tests/unit/test_therapeutic_opposition.py)
   - Updated `_make_trial()` to support `condition_names` and parameterized dummy disease/condition terms in `test_20`, `test_21`, `test_24`.

---

## 3. Test Suite Verification

### A. Targeted Suites
```
pytest tests/unit/test_disease_relation.py -v
--> 9 passed in 0.12s (100%)

pytest tests/unit/test_clinicaltrials_safe_fixes.py -v
--> 25 passed in 0.87s (100%)

pytest tests/unit/test_trial_attribution.py -v
--> 10 passed in 0.51s (100%)
```

### B. Full Unit Test Suite
```
pytest tests/unit/ -q
--> 682 passed, 0 failed, 496 warnings in 24.88s (100%)
```

---

## 4. Adversarial Test Verification (§5)

| Test Identifier | Description | Setup | Expected Verdict | Verified Result |
|---|---|---|---|---|
| **Test A** | Empty condition, sibling title | `conditions=[]`, `title="Acute Hemorrhagic Stroke"`, `query="Stroke"` | Trial match = `False` | **PASSED** (`matches_disease_condition() == False`) |
| **Test B** | Empty condition, parent-child title | `conditions=[]`, `title="Dexamethasone for Chronic Subdural Hematoma"`, `query="Traumatic brain injury"` | Trial match = `True` | **PASSED** (Validated via PARENT_CHILD) |
| **Test C** | Unresolved combination contrast | Experimental: $A+B$, Comparator: $C+D$, Candidate: $A$ | `is_diff = False` | **PASSED** (`is_differentiating_intervention == False`) |
| **Test D** | Unresolved combination with explicit text | Experimental: $A+B$, Comparator: $C+D$, `whyStopped="A was ineffective"` | `final_attribution_decision = False` | **PASSED** (Contrast design protects against attribution escape) |
| **Test E** | Stroke vs Hemorrhagic stroke strict veto | `query="stroke"`, `cand="hemorrhagic stroke"` | Approval = `False`, Trial = `False` | **PASSED** (Rule -1 anchor blocked; trial attribution blocked) |
| **Test F** | Metformin background protection | NCT02020616 ($LY3053102+Metformin$ vs $Placebo+Metformin$) | `attr = False`, claim = `None` | **PASSED** (Identical co-medication subtracted) |
| **Test G** | Nivolumab Placebo non-match | Comparator: `"Nivolumab Placebo"` | Candidate match = `False` | **PASSED** (Placebo component excluded from candidate drug role) |

---

## 5. Live Targeted Pre-Benchmark Verification (§7)

A dedicated script (`scratch/live_pre_benchmark_verification.py`) executed the 6 specified target pairs against the live pipeline:

1. **Aspirin $\rightarrow$ Hemorrhagic stroke:**
   - Relation: `SIBLING_EXCLUDED`
   - Approval Anchor Match: `False` (Blocked)
   - Trial Attribution Match: `False` (Blocked)
   - ChEMBL Approval Signal: `is_approved=False`, pathway=`NOVEL_HYPOTHESIS`
   - **Status: PASS**
2. **Dexamethasone $\rightarrow$ Traumatic brain injury:**
   - Relation TBI $\rightarrow$ Subdural hematoma: `PARENT_CHILD`
   - Trial Attribution Match: `True`
   - Parsed trials: 7, Negative claims extracted: 1
   - Opposition Score: `0.319` (MODERATE)
   - **Status: PASS**
3. **Niacin $\rightarrow$ Cardiovascular disease:**
   - Parsed trials: 50
   - AIM-HIGH (NCT00120289) retrieved: `True`, status: `TERMINATED_LACK_OF_EFFICACY`
   - AIM-HIGH attribution: `True`, negative claim generated: `True`
   - Opposition Score: `0.512` (HIGH)
   - **Status: PASS**
4. **Nivolumab $\rightarrow$ Glioblastoma:**
   - Parsed trials: 42
   - CheckMate 498 (NCT02667587) retrieved: `True`
   - CheckMate 498 attribution: `True`, negative claim generated: `True`
   - Total negative claims: 4, Opposition Score: `0.700` (HIGH)
   - **Status: PASS**
5. **Metformin $\rightarrow$ Type 2 diabetes:**
   - Parsed trials: 50
   - NCT02020616 ($LY3053102 + Metformin$ vs $Placebo + Metformin$): `attr=False`, `claim=None` (Background protected)
   - Approval Match (`"type 2 diabetes"`, `"diabetes mellitus, type 2"`): `True`
   - ChEMBL Approval: `is_approved=True`, `max_phase=4`
   - **Status: PASS**
6. **Furosemide $\rightarrow$ Depression:**
   - ChEMBL Approval Anchor: `is_approved=False`
   - Parsed trials: 0, Negative claims: 0
   - Opposition Score: `0.000` (NONE)
   - **Status: PASS**

---

## 6. Documented System Limitations (As Instructed)

### A. Remaining Statistical Interpretation Limitations
- **Superiority Assumption:** The structured results parser (`_detect_negative_outcome_from_results`) interprets $p \ge 0.05$ on the primary endpoint as an empirical lack of efficacy (superiority trial design).
- **Non-Inferiority & Equivalence Trials:** The parser does not currently inspect non-inferiority margins ($\delta$) or equivalence bounds. A non-inferiority trial where the experimental agent successfully demonstrates non-inferiority with $p < 0.05$ against the non-inferiority margin is not distinguished from superiority failure if formatted with standard two-sided superiority testing.
- **Single-Arm Historical Comparators:** Single-arm trials lacking explicit comparative arms rely on structured completion counts or termination reasons. Historical comparator statistical testing is unresolved.
- **Endpoint Polarity Ambiguity:** While standard endpoints (OS, PFS, HbA1c, blood pressure) are parsed for directionality, novel or bespoke composite score directions remain ambiguous.

### B. Remaining Ontology Limitations
- **Curated Coverage Scope:** `_PARENT_CHILD` and `_SIBLING_EXCLUSIONS` use curated deterministic mappings for key disease families (Cardiovascular, Stroke, TBI, Glioblastoma, Alzheimer's, Diabetes). Indications outside these curated mappings rely on canonical synonym normalization (`_CANONICAL_SYNONYMS`) and exact word-bounded matching.
- **Complex Syndromic Subtypes:** Broad multisystem disease queries (e.g. "Autoimmune disease", "Neurodegenerative disorder") require explicit child declarations to avoid either over-broad trial aggregation or false negative omissions.

### C. Remaining Attribution Limitations
- **Factorial Designs ($2 \times 2$):** Trials with complex multi-arm factorial combinations ($A+B$ vs $A$ vs $B$ vs Placebo) are parsed pairwise by arm component extraction. Complex interaction terms are not parsed from unstructured registry narratives.
- **Unreported Formulation Changes:** If trial records omit formulation or delivery device keywords from intervention names, delivery contrast versus drug contrast differentiation relies on textual comparative patterns in the title.

---

## 7. Explicit Verdict

```
================================================================================
SAFE TO RUN 100-CASE BENCHMARK = YES
================================================================================
```

**Justification:**
1. All identified bypasses (empty condition, unisolated combination escape, sibling approval leakage) have been eliminated and verified.
2. 100% of unit tests pass (682 / 682).
3. 100% of targeted adversarial tests pass (44 / 44).
4. All 6 live verification cases passed without false opposition, false anchors, or lost valid trials.
5. Strict freeze on all decision thresholds, scores, and weights was maintained throughout.
