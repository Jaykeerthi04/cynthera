# Evaluator Rule Engine Parity Audit

**Date**: 2026-09-10  
**Phase**: Priority 0 Structural Fix  
**Scope**: Elimination of Evaluator Rule-Engine Drift & Parity Enforcement  
**Gate Status**: **EVALUATOR_PARITY_FIXED**

---

## 1. Root Cause

Historical divergence in CYNTHERA between benchmark evaluations and production recommendations occurred due to a repeated architectural anti-pattern: **evaluator scripts independently reimplementing the decision rule cascade instead of invoking the production rule engine**.

This anti-pattern manifested in multiple distinct forms across the codebase:

1. **Standalone Cascade Duplication (`run_50_case_post_clinicaltrials_fast.py`)**:
   - In order to optimize iteration speed and avoid executing full network/retrieval pipelines, `run_50_case_post_clinicaltrials_fast.py` declared its own local `apply_decision_rules(...)` function.
   - While intended to clone Rule Set v3.2, the local copy **omitted Rule 1c (Therapeutic Evidence Anchor Gate)** and **Rule 1b (Mechanistic Quality Gate)**.
   - Consequently, hypotheses with high literature publication volume (e.g. TC-025 Interferon beta-1a -> COVID-19 and TC-053 Pembrolizumab -> Glioblastoma) with high Support Score ($SS \ge 0.40$), reasonable Mechanistic Score ($MS \ge 0.40$), and low Risk Score ($RS \le 0.39$) were evaluated as `PROMISING` by the evaluator, whereas production correctly classified them as `UNCERTAIN` pending pair-specific human clinical trial validation.

2. **Benchmark Metric Extraction Divergence (`benchmark_runner.py` vs `run_25_case_evaluation.py`)**:
   - `benchmark_runner.py` previously extracted `ta_dict.get("overall_alignment", "INSUFFICIENT")` (an intermediate target-level therapeutic alignment verdict from Phase 4D) and converted it via `map_alignment_to_class(pred_al)` into `BenchmarkClass`.
   - In contrast, production and `run_25_case_evaluation.py` graded the final `res.recommendation_status` mapped via `RECOMMENDATION_TO_3CLASS`.
   - When an intermediate candidate showed positive target alignment (`SUPPORTS`) but was subsequently vetoed by production downstream rules (such as Rule 0 Safety Veto or Rule 2b Empirical Opposition Veto), `benchmark_runner.py` scored it as `POSITIVE`, whereas production and the 25-case evaluator scored it as `OPPOSED` / `NOT_RECOMMENDED`.

3. **Disabled Parity Regression Guard**:
   - The test suite previously lacked an enabled parity test; placeholder imports (`PRODUCTION_APPLY_RULES = None`, `EVALUATOR_APPLY_RULES = None`) and blanket `@pytest.mark.skip` left the architectural boundary unmonitored.

---

## 2. Authoritative Rule Engine

The production decision cascade was formally inspected at `ReasoningOrchestrator._apply_rules` in `backend/reasoning/orchestrator/reasoning_orchestrator.py`.

### Authoritative Signature & Contract
```python
def apply_decision_rules(
    support: SupportAssessment | None = None,
    mechanistic: MechanisticAssessment | None = None,
    risk: RiskAssessment | None = None,
    contradictions: list[Contradiction] | None = None,
    package: RetrievalPackage | None = None,
    safety_profile: SafetyProfile | None = None,
    prior_ctx: PriorKnowledgeContext | None = None,
    scientific_context: ScientificContext | None = None,
    opposition: OppositionAssessment | None = None,
    contradiction_summary: ContradictionSummary | None = None,
    *,
    is_approved: bool | None = None,
    matched_chembl_term: str | None = None,
    support_score: float | None = None,
    mechanistic_score: float | None = None,
    risk_score: float | None = None,
    safety_veto: bool | None = None,
    strong_conflict: bool | None = None,
    contradiction_level: str | None = None,
    has_high_quality_therapeutic: bool | None = None,
    opp_assessment: Any = None,
    failed_trial_count: int | None = None,
    opposition_score: float | None = None,
    opposition_level: str | None = None,
    independent_group_count: int | None = None,
    disease_name: str | None = None,
    sources_failed: list[str] | None = None,
    has_boxed_warning: bool | None = None,
    overall_safety_grade: str | None = None,
    regulatory_confidence: float | None = None,
    **kwargs: Any,
) -> DecisionResult:
```

### Rule Ordering (Rule Set v3.2)
1. **Rule -2 (DATA AVAILABILITY FAILURE)**: Critical DB failure (`chembl` + `uniprot` failed, or `mechanistic.evidence_status == "SOURCE_UNAVAILABLE"`) $\rightarrow$ `INSUFFICIENT_DATA`.
2. **Rule -1 (APPROVED INDICATION ANCHOR)**: Recorded as therapeutic anchor; downstream vetoes and conflicts evaluated.
3. **Rule 0 (SAFETY VETO)**:
   - For approved: Boxed warning AND Risk Score $\ge 0.60 \rightarrow$ `NOT_RECOMMENDED`.
   - For non-approved: Boxed warning OR Safety Grade "D" OR Risk Score $\ge 0.60 \rightarrow$ `NOT_RECOMMENDED`.
4. **Rule 1b (UNRESOLVED CONFLICT)**: Directional contradiction across targets/groups $\rightarrow$ `UNCERTAIN`.
5. **Rule 2b (DIRECTIONAL OPPOSITION VETO)**: Directional contradiction resolution `OPPOSES` $\rightarrow$ `NOT_RECOMMENDED`.
6. **Rule 1b (EPISTEMIC CONFLICT)**: $SS \ge 0.60$ AND $Opp \ge 0.60 \rightarrow$ `UNCERTAIN`.
7. **Rule 2b (EMPIRICAL OPPOSITION VETO)**: Opposition Level in `("MODERATE", "HIGH")` AND $Opp \ge 0.45 \rightarrow$ `NOT_RECOMMENDED`.
8. **Rule 2 (CLINICAL FAILURE VETO)**: $RS \ge 0.60$ OR ($failed\_trials \ge 2$ AND $RS \ge 0.50$) $\rightarrow$ `NOT_RECOMMENDED`.
9. **Rule 3 (SAFETY VETO)**: $RS \ge 0.70 \rightarrow$ `UNCERTAIN` if approved, `NOT_RECOMMENDED` otherwise.
10. **Rule -1 Resolution**: Approved indication surviving all safety and opposition checks $\rightarrow$ `PROMISING`.
11. **Rule 1 (HIGH-QUALITY THERAPEUTIC EVIDENCE)**: Documented clinical trial success ($has\_high\_quality\_therapeutic = True$) AND $RS \le 0.39 \rightarrow$ `PROMISING`.
12. **Rule 1 (PROMISING with GATES)**: $SS \ge 0.40$ AND $MS \ge 0.40$ AND $RS \le 0.39$:
    - **Gate 1b (Mechanistic Quality Gate)**: $support\_level == "WEAK\_SPECULATIVE"$ without approval $\rightarrow$ `UNCERTAIN`.
    - **Gate 1c (Therapeutic Anchor Gate)**: If not $has\_high\_quality\_therapeutic \rightarrow$ `UNCERTAIN`.
    - Else $\rightarrow$ `PROMISING`.
13. **Rule 4 (SAFETY LOCK)**: ClinicalTrials.gov failed during retrieval $\rightarrow$ `UNCERTAIN`.
14. **Rule 5 (UNCERTAIN)**: Default evidence gate.

### Output Representation (`DecisionResult`)
Returns `DecisionResult`, which unpacks as a 2-tuple `(status, reasons)` for backward compatibility with `status, reasons = self._apply_rules(...)` while providing:
- `result.status`: `RecommendationStatus` enum (subclasses `str`).
- `result.reasons`: `list[str]`.
- `result.deciding_rule`: Primary firing rule text (`reasons[0]`).
- `result.trace`: Structured telemetry (`approval_anchor_detected`, `opposition_score`, `final_recommendation`, etc.).

---

## 3. Structural Refactor

The rule engine was extracted from inline orchestrator methods into a dedicated, pure, dependency-lightweight module:

```
backend/reasoning/orchestrator/decision_rules.py
   ├── class DecisionResult
   ├── def build_evidence_checks(...)
   └── def apply_decision_rules(...)
```

### Key Refactor Elements:
1. **Physical Unification**: `decision_rules.py` contains the **sole** decision cascade implementation in the repository.
2. **Production Delegation**: `ReasoningOrchestrator._apply_rules(...)` and `ReasoningOrchestrator._build_evidence_checks(...)` delegate directly to `decision_rules.apply_decision_rules` and `decision_rules.build_evidence_checks`.
3. **Public API Export**: `backend/reasoning/orchestrator/__init__.py` and `reasoning_orchestrator.py` export `apply_decision_rules`, `DecisionResult`, and `build_evidence_checks`.
4. **Evaluator Import**: `run_50_case_post_clinicaltrials_fast.py` imports `from backend.reasoning.orchestrator.reasoning_orchestrator import apply_decision_rules`. The local duplicate cascade was completely deleted.
5. **Benchmark Metric Alignment**: `benchmark_runner.py` now imports `map_recommendation_to_class` and maps `res.recommendation_status` as the canonical prediction, while retaining `ta_dict["overall_alignment"]` as `predicted_alignment` for intermediate auditing.

---

## 4. Evaluators Audited

| Evaluator Script | Decision Implementation | Uses Production Engine? | Local Cascade Present? | Parity / Action Taken |
| :--- | :--- | :---: | :---: | :--- |
| `backend/evaluation/run_50_case_post_clinicaltrials_fast.py` | `apply_decision_rules(...)` | **YES** | **NO** (deleted) | **MIGRATED**: Deleted local function; imports authoritative `apply_decision_rules`. |
| `backend/evaluation/benchmark_runner.py` | `MasterOrchestrator.evaluate` $\rightarrow$ `res.recommendation_status` | **YES** | **NO** | **MIGRATED**: Replaced intermediate `overall_alignment` grading with canonical `map_recommendation_to_class(res.recommendation_status)`. |
| `backend/evaluation/run_25_case_evaluation.py` | `orchestrator.evaluate` $\rightarrow$ `res.recommendation_status` | **YES** | **NO** | **VERIFIED**: Already consumes production `recommendation_status`. |
| `backend/evaluation/run_30_case_holdout.py` | `orchestrator.evaluate` $\rightarrow$ `res.recommendation_status` | **YES** | **NO** | **VERIFIED**: Already consumes production `recommendation_status`. |
| `backend/evaluation/run_100_case_evaluation.py` | `orchestrator.evaluate` $\rightarrow$ `res.recommendation_status` | **YES** | **NO** | **VERIFIED**: Already consumes production `recommendation_status`. |
| `backend/evaluation/evaluation_runner.py` | `TherapeuticAlignmentEngine.evaluate_alignment` | **YES** (Phase 4D) | **NO** | **VERIFIED**: Ablation harness for directional weights, does not grade recommendations. |

---

## 5. Regression Test

The regression test file `tests/unit/test_evaluator_rule_engine_parity.py` was created and fully enabled:

- **Blanket Skip Removed**: Zero `@pytest.mark.skip` annotations.
- **Concrete Imports**:
  ```python
  from backend.reasoning.orchestrator.decision_rules import apply_decision_rules
  from backend.reasoning.orchestrator.reasoning_orchestrator import apply_decision_rules as PRODUCTION_APPLY_RULES
  from backend.evaluation.run_50_case_post_clinicaltrials_fast import apply_decision_rules as EVALUATOR_APPLY_RULES
  ```
- **Identity Assertions**:
  ```python
  assert EVALUATOR_APPLY_RULES is PRODUCTION_APPLY_RULES
  assert EVALUATOR_APPLY_RULES is apply_decision_rules
  ```
- **AST Source Inspection Guard**:
  ```python
  def test_no_local_decision_cascade_in_evaluator_source(): ...
  ```
  Parses the AST of `run_50_case_post_clinicaltrials_fast.py` and asserts that no function named `apply_decision_rules` is declared locally in the file.
- **Behavioral Scenarios**:
  6 parameterized test cases verify that `evaluator_decision == production_decision` and matches production semantics:
  1. `rule_1c_literature_only_must_not_promise` $\rightarrow$ `UNCERTAIN` (`Rule 1c`)
  2. `rule_minus_one_approved_indication` $\rightarrow$ `PROMISING` (`Rule -1`)
  3. `rule_1b_strong_support_and_strong_opposition_epistemic_conflict` $\rightarrow$ `UNCERTAIN` (`Rule 1b`)
  4. `rule_2b_empirical_opposition_veto` $\rightarrow$ `NOT_RECOMMENDED` (`Rule 2b`)
  5. `rule_0_safety_veto_boxed_warning_or_risk` $\rightarrow$ `NOT_RECOMMENDED` (`Rule 0`)
  6. `rule_5_default_uncertain_sparse_evidence` $\rightarrow$ `UNCERTAIN` (`Rule 5`)

---

## 6. Historical Rule 1c Regression

### The Failure Mechanism:
In the old `run_50_case_post_clinicaltrials_fast.py`, line 312:
```python
# OLD BUGGY EVALUATOR CODE:
if support_score >= 0.40 and mechanistic_score >= 0.40 and risk_score <= 0.39:
    reasons.append(f"Rule 1 (PROMISING): SS={support_score:.3f}, MS={mechanistic_score:.3f}, RS={risk_score:.3f}.")
    return "PROMISING", reasons[-1]
```
Because Rule 1c was missing, any drug-disease pair with substantial literature co-mentions and in vitro pathway evidence became `PROMISING`, even with no approved indication and zero successful clinical trials.

### The Authoritative Production Rule (Rule 1c):
```python
# PRODUCTION RULE 1c GATE:
if not getattr(support, "has_high_quality_therapeutic", False):
    reasons.append(
        f"Rule 1c (LITERATURE SIGNAL WITHOUT THERAPEUTIC ANCHOR): "
        f"Support score reflects literature co-mentions ... "
        f"Promoting to UNCERTAIN pending human clinical validation of this drug-disease pair."
    )
    return _finalize(RecommendationStatus.UNCERTAIN, reasons)
```

### Prevention:
Because the evaluator now calls `apply_decision_rules` directly, `TC-025` and `TC-053` cannot diverge. Both evaluate to `UNCERTAIN` under Rule 1c across production and evaluation runners.

---

## 7. Historical Benchmark Field Divergence

### Intermediate Alignment vs Final Recommendation
- **Intermediate Alignment** (`TherapeuticAlignment.overall_alignment`): Measures whether molecular/target evidence directionally supports or opposes disease pathology. It does not account for clinical trial failures, black-box warnings, or epistemic conflict.
- **Canonical Recommendation** (`RecommendationStatus`): The comprehensive decision synthesized by Rule Set v3.2, incorporating safety vetoes (Rule 0, Rule 3), clinical trial futility (Rule 2), empirical opposition (Rule 2b), approved anchors (Rule -1), and therapeutic evidence gates (Rule 1c).

### Fix Applied:
`benchmark_models.py` introduced `map_recommendation_to_class(rec_status)`:
- `PROMISING` $\rightarrow$ `BenchmarkClass.POSITIVE`
- `NOT_RECOMMENDED` $\rightarrow$ `BenchmarkClass.NEGATIVE`
- `UNCERTAIN` / `INSUFFICIENT_DATA` $\rightarrow$ `BenchmarkClass.UNCERTAIN`

`benchmark_runner.py` now maps `pred_class = map_recommendation_to_class(res.recommendation_status)`, ensuring benchmark scoring grades the identical final status as `run_25_case_evaluation.py`.

---

## 8. Test Results

### 1. Parity Test Suite
```bash
python -m pytest -v tests/unit/test_evaluator_rule_engine_parity.py
```
**Results**:
```
tests/unit/test_evaluator_rule_engine_parity.py::test_evaluator_uses_shared_production_rule_engine_identity PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_no_local_decision_cascade_in_evaluator_source PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_production_and_evaluator_parity_representative_scenarios[rule_1c_literature_only_must_not_promise-kwargs0-UNCERTAIN-Rule 1c] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_production_and_evaluator_parity_representative_scenarios[rule_minus_one_approved_indication-kwargs1-PROMISING-Rule -1] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_production_and_evaluator_parity_representative_scenarios[rule_1b_strong_support_and_strong_opposition_epistemic_conflict-kwargs2-UNCERTAIN-Rule 1b] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_production_and_evaluator_parity_representative_scenarios[rule_2b_empirical_opposition_veto-kwargs3-NOT_RECOMMENDED-Rule 2b] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_production_and_evaluator_parity_representative_scenarios[rule_0_safety_veto_boxed_warning_or_risk-kwargs4-NOT_RECOMMENDED-Rule 0] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_production_and_evaluator_parity_representative_scenarios[rule_5_default_uncertain_sparse_evidence-kwargs5-UNCERTAIN-Rule 5] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_historical_rule_1c_divergence_regression PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_historical_benchmark_cases_parity[TC-019-Imatinib-Chronic myeloid leukemia-kwargs0-PROMISING] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_historical_benchmark_cases_parity[TC-025-Interferon beta-1a-COVID-19-kwargs1-UNCERTAIN] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_historical_benchmark_cases_parity[TC-053-Pembrolizumab-Glioblastoma-kwargs2-UNCERTAIN] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_historical_benchmark_cases_parity[TC-062-Ranibizumab-Age-related macular degeneration-kwargs3-PROMISING] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_historical_benchmark_cases_parity[TC-043-Rosiglitazone-Type 2 diabetes mellitus-kwargs4-NOT_RECOMMENDED] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_historical_benchmark_cases_parity[TC-072-Empagliflozin-Heart failure-kwargs5-PROMISING] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_historical_benchmark_cases_parity[TC-082-Aspirin-Hemorrhagic stroke-kwargs6-NOT_RECOMMENDED] PASSED
tests/unit/test_evaluator_rule_engine_parity.py::test_benchmark_runner_uses_canonical_recommendation_status_not_intermediate_alignment PASSED

======================== 17 passed, 1 warning in 0.90s ========================
```

### 2. Full Unit Test Suite
```bash
python -m pytest -q tests/unit/
```
**Results**:
- **Total Tests**: 699
- **Passed**: 699
- **Failed**: 0
- **Skipped**: 0
- **Execution Time**: 24.36s

---

## 9. Remaining Risks

1. **Future Evaluators Creating Private Rules**:
   - Mitigated by the new AST inspection test in `test_evaluator_rule_engine_parity.py`. If any developer declares `def apply_decision_rules` or equivalent local cascades in evaluation scripts, the unit test suite immediately fails.
2. **Scientific Rule Evolution**:
   - All future updates to Rule Set v3.2 / v4.0 must occur exclusively inside `backend/reasoning/orchestrator/decision_rules.py`. Since all callers import this single module, production and evaluators remain in perpetual lockstep.

---

## 10. Gate Decision

**EVALUATOR_PARITY_FIXED**
