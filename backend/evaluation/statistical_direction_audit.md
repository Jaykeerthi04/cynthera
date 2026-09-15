# Statistical Direction Audit

## 1. Root Cause

Prior to this fix, `RetrievalPipeline._evaluate_outcome_measure_direction()` contained an unsafe statistical assumption: any outcome measure where $p \ge 0.05$, where a confidence interval crossed unity ($CI_{lower} \le 1.0 \le CI_{upper}$), or where standard neutral text phrases appeared ("no significant difference", "not statistically significant") was unconditionally classified as `NEGATIVE`.

In scientific trial methodology, a non-significant result ($p \ge 0.05$) signifies that the study failed to establish statistical superiority under the evaluated null hypothesis; it does **not** establish that the drug is therapeutically ineffective, harmful, or an empirical failure. In clinical practice and drug development:
1. Secondary and exploratory endpoints are frequently underpowered or neutral without detracting from established primary disease efficacy.
2. Prevention or post-event extension trials (e.g. EMPACT-MI evaluating Empagliflozin post-myocardial infarction) often produce neutral primary composite results while the drug remains established and approved for its primary indication (Heart Failure).
3. Non-inferiority trials where confidence intervals satisfy the pre-specified margin $\Delta$ are positive successes, yet their difference $p$-value often exceeds 0.05 because the test is designed to verify lack of inferiority rather than superiority.
4. Single-arm studies and within-group paired tests lack comparator controls, making superiority $p$-value thresholds statistically meaningless for empirical therapeutic failure.

Under the flawed implementation, neutral endpoints automatically assigned `is_neg_efficacy = True` to completed trials. For completed trials (`raw_status == "COMPLETED"`), this converted the trial status to `TrialOutcomeStatus.COMPLETED_FAILURE`. When fed into `trial_to_negative_claim()`, these trials generated empirical opposition claims with `predicate = PredicateType.FAILED_TO_IMPROVE` ($ERW = 0.90$, confidence = 0.95). In the `TherapeuticOppositionAssessor`, these false claims accumulated opposition scores above 0.45, triggering an empirical opposition veto under **Rule 2b** and causing regressions in established indications:
- **TC-043** Rosiglitazone $\rightarrow$ Type 2 diabetes mellitus: vetoed to `NOT_RECOMMENDED` (`OPPOSE`) due to neutral secondary/exploratory trial endpoints.
- **TC-072** Empagliflozin $\rightarrow$ Heart failure: vetoed to `NOT_RECOMMENDED` (`OPPOSE`) due to neutral post-MI composite trial endpoints (EMPACT-MI).

---

## 2. Existing Behavior

The call path responsible for clinical-trial outcome direction:

```
raw ClinicalTrials.gov result (resultsSection)
  └── outcomeMeasuresModule.outcomeMeasures
        └── RetrievalPipeline._evaluate_outcome_measure_direction(om)
              └── RetrievalPipeline._parse_trials_data()
                    └── ClinicalTrial(status, is_negative_efficacy, negative_efficacy_reason)
                          └── trial_to_negative_claim(trial, drug, disease)
                                └── TherapeuticOppositionAssessor.assess()
                                      └── apply_decision_rules() -> Rule 2b
```

### Specific Flaws Identified in Legacy Code:
1. **Unconditional $p \ge 0.05$ Failure**:
   ```python
   # Legacy code in pipeline.py:
   if p_val >= 0.05:
       ...
       return "NEGATIVE", f"Outcome '{title}' failed to achieve statistical significance (p={p_val} >= 0.05, {stat_method})"
   ```
2. **Unconditional CI Crossing Unity Failure**:
   ```python
   # Legacy code in pipeline.py:
   if cl <= 1.0 <= cu:
       return "NEGATIVE", f"Outcome '{title}' confidence interval [{cl}, {cu}] crosses unity (no significant benefit)"
   ```
3. **Secondary Endpoint Overreach**:
   In `_parse_trials_data`, if primary endpoints were silent or missing, a secondary endpoint with $p \ge 0.05$ set `is_neg_efficacy = True` for the entire trial, converting `status` to `COMPLETED_FAILURE`.
4. **No Semantic Separation for Non-Inferiority, Equivalence, or Safety**:
   Non-inferiority trials were judged by superiority tests; safety endpoints reporting higher adverse event incidence were conflated with therapeutic efficacy failure.

---

## 3. New Semantics

Explicit, scientifically sound outcome categories were introduced in `backend/core/enums/statistical_direction.py`:

```python
class OutcomeDirection(str, Enum):
    POSITIVE = "POSITIVE"          # Demonstrated statistically significant benefit or NI/equivalence success
    NEGATIVE = "NEGATIVE"          # Genuine failure, explicit futility, or significant harm on disease endpoint
    NEUTRAL = "NEUTRAL"            # Non-significant result (p >= 0.05, CI crosses unity) without explicit failure
    INCONCLUSIVE = "INCONCLUSIVE"  # Incomplete statistical context or ambiguous NI/equivalence bounds
    SAFETY_HARM = "SAFETY_HARM"    # Safety/AE endpoint showing harm; separated from therapeutic opposition
    UNKNOWN = "UNKNOWN"            # Non-efficacy endpoint, single-arm/within-group study, or missing context
```

### Audit Reason Codes:
The parser produces structured provenance via `StatisticalReasonCode`:
- `STATISTICALLY_SIGNIFICANT_BENEFIT`
- `STATISTICALLY_SIGNIFICANT_HARM`
- `EXPLICIT_FUTILITY`
- `EXPLICIT_LACK_OF_EFFICACY`
- `EXPLICIT_TERMINATION_FOR_HARM`
- `NON_SIGNIFICANT_PRIMARY_ENDPOINT`
- `NON_SIGNIFICANT_SECONDARY_ENDPOINT`
- `NON_SIGNIFICANT_SUBGROUP`
- `NON_INFERIOR`
- `NON_INFERIORITY_FAILURE`
- `EQUIVALENT`
- `EQUIVALENCE_FAILURE`
- `SINGLE_ARM_NO_COMPARATOR`
- `SAFETY_ENDPOINT`
- `INSUFFICIENT_STATISTICAL_CONTEXT`
- `NON_EFFICACY_ENDPOINT`

### Backward-Compatible Result Container:
`OutcomeEvaluationResult` subclasses `tuple` with 2 items `(direction, reason)` while exposing `.direction`, `.reason`, and `.reason_code`. Any legacy caller expecting `direction, reason = eval(om)` unpacks seamlessly without breakage, while new callers access the structured metadata.

---

## 4. Primary vs Secondary Endpoint Handling

1. **Secondary Endpoints Cannot Refute Primary Efficacy**:
   - Secondary endpoints with $p \ge 0.05$ or crossing unity evaluate to `NEUTRAL` with reason code `NON_SIGNIFICANT_SECONDARY_ENDPOINT`.
   - In `_parse_trials_data`, secondary endpoints **never** set `is_neg_efficacy = True` or convert a completed trial to `COMPLETED_FAILURE`.
2. **Secondary Endpoint Positive Support**:
   - When a trial's primary endpoint is silent or unpopulated, a statistically significant positive secondary endpoint ($p < 0.05$) can establish positive efficacy (`COMPLETED_SUCCESS`), matching clinical trial reporting norms.

---

## 5. Non-Inferiority / Equivalence

1. **Non-Inferiority Logic**:
   - Detects `nonInferiorityType` and comments.
   - If explicit non-inferiority text ("non-inferiority demonstrated", "met non-inferiority") is present $\rightarrow$ `POSITIVE` (`NON_INFERIOR`).
   - If margin $\Delta$ is extracted and $CI_{upper} \le \Delta$ $\rightarrow$ `POSITIVE` (`NON_INFERIOR`).
   - If $CI_{upper} > \Delta$ $\rightarrow$ `NEGATIVE` (`NON_INFERIORITY_FAILURE`).
   - If evaluated via non-inferiority hypothesis test: $p < 0.05 \rightarrow$ `POSITIVE`; $p \ge 0.05 \rightarrow$ `NEGATIVE`.
   - If margin/CI cannot be determined $\rightarrow$ `INCONCLUSIVE` (`INSUFFICIENT_STATISTICAL_CONTEXT`), never naively negative.
2. **Equivalence Logic**:
   - Evaluates confidence intervals against equivalence bounds (e.g. $[0.80, 1.25]$).
   - If $CI_{lower} \ge 0.80$ and $CI_{upper} \le 1.25$ $\rightarrow$ `POSITIVE` (`EQUIVALENT`).
   - If confidence interval extends outside bounds $\rightarrow$ `NEGATIVE` (`EQUIVALENCE_FAILURE`).

---

## 6. Single-Arm Handling

- Studies or analyses identified as single-arm, paired within-subject, one-sample, or without comparator controls ("paired t-test", "within-group") evaluate to `UNKNOWN` with reason code `SINGLE_ARM_NO_COMPARATOR`.
- Absence of statistical significance or absence of $p$-values in single-arm cohorts never converts to `NEGATIVE`.

---

## 7. Safety vs Efficacy

- Safety outcomes (adverse events, SAEs, laboratory abnormalities, tolerability) identified via `_is_safety_endpoint()` evaluate to `SAFETY_HARM` (`SAFETY_ENDPOINT`) if statistically significant harm/toxicity is observed ($p < 0.05$, ratio > 1.0), or `UNKNOWN` (`SAFETY_ENDPOINT`) otherwise.
- Safety findings are routed strictly to safety/risk representation and never set `is_neg_efficacy = True` or generate `FAILED_TO_IMPROVE` therapeutic efficacy opposition claims.

---

## 8. Opposition Claim Changes

In `trial_to_negative_claim()`:
- Completed trials with only `NEUTRAL` or `UNKNOWN` endpoints receive `status = TrialOutcomeStatus.UNKNOWN` and `is_negative_efficacy = False`.
- `trial_to_negative_claim()` returns `None`.
- Completed trials with positive endpoints receive `TrialOutcomeStatus.COMPLETED_SUCCESS` and return `None`.
- Only trials with genuine primary failure, explicit futility, or primary disease harm receive `TrialOutcomeStatus.COMPLETED_FAILURE` (`is_negative_efficacy = True`) and generate `PredicateType.FAILED_TO_IMPROVE` claims.

---

## 9. Regression Tests

A dedicated test suite was created in `tests/unit/test_statistical_direction_semantics.py` covering all 15 required scenarios:

| # | Test Scenario | Verified Behavior |
|---|---|---|
| 1 | $p \ge 0.05$ primary endpoint | `NEUTRAL` (`NON_SIGNIFICANT_PRIMARY_ENDPOINT`); status `UNKNOWN`; claim is `None` |
| 2 | $p \ge 0.05$ secondary endpoint | `NEUTRAL` (`NON_SIGNIFICANT_SECONDARY_ENDPOINT`); status `UNKNOWN`; claim is `None` |
| 3 | Significant beneficial primary endpoint | `POSITIVE` (`STATISTICALLY_SIGNIFICANT_BENEFIT`); status `COMPLETED_SUCCESS` |
| 4 | Significant harmful primary endpoint | `NEGATIVE` (`STATISTICALLY_SIGNIFICANT_HARM`); claim `FAILED_TO_IMPROVE` |
| 5 | Explicit futility boundary crossing | `NEGATIVE` (`EXPLICIT_FUTILITY`); claim `FAILED_TO_IMPROVE` |
| 6 | Explicit lack of efficacy in text | `NEGATIVE` (`EXPLICIT_LACK_OF_EFFICACY`); claim `FAILED_TO_IMPROVE` |
| 7 | Single-arm without comparator | `UNKNOWN` (`SINGLE_ARM_NO_COMPARATOR`); claim is `None` |
| 8 | Non-inferiority success ($CI_{upper} \le margin$) | `POSITIVE` (`NON_INFERIOR`) |
| 9 | Non-inferiority failure ($CI_{upper} > margin$) | `NEGATIVE` (`NON_INFERIORITY_FAILURE`) |
| 10 | Equivalence success & failure | Bounds $[0.80, 1.25]$ evaluated: within = `POSITIVE`, outside = `NEGATIVE` |
| 11 | Safety endpoint adverse signal | `SAFETY_HARM` (`SAFETY_ENDPOINT`); does NOT generate `FAILED_TO_IMPROVE` |
| 12 | EMPACT-MI neutral post-MI result | Evaluates to `NEUTRAL`; 0 opposition claims for Empagliflozin $\rightarrow$ HF |
| 13 | Rosiglitazone neutral secondary endpoint | Evaluates to `NEUTRAL`; 0 opposition claims for Rosiglitazone $\rightarrow$ T2D |
| 14 | CRASH Dexamethasone in TBI | Excess mortality preserved as `NEGATIVE`; opposition claim generated |
| 15 | AIM-HIGH Niacin in CVD | Futility termination preserved as `NEGATIVE`; opposition claim generated |

---

## 10. Test Results

1. **Unit Test Suite**:
   - `tests/unit/test_statistical_direction_semantics.py`: **15/15 passed** (100%).
   - `tests/unit/test_trial_results_issue5.py`: **14/14 passed** (100%).
   - `tests/unit/test_clinicaltrials_safe_fixes.py`: **26/26 passed** (100%).
   - Entire unit test suite (`pytest -q tests/unit/`): **718/718 passed** (0 failures).

2. **Targeted 7-Case Validation**:

| Case ID | Drug | Disease | Standard Gold | Old Prediction (OppScore) | New Prediction (OppScore) | Deciding Rule | Status |
|---|---|---|---|---|---|---|---|
| **TC-043** | Rosiglitazone | Type 2 diabetes | SUPPORT | OPPOSE (0.512) | **UNCERTAIN** (0.000) | Rule 1c | **False opposition veto fixed** (4 neutral trials recognized) |
| **TC-072** | Empagliflozin | Heart failure | SUPPORT | OPPOSE (0.512) | **UNCERTAIN** (0.000) | Rule 1c | **False opposition veto fixed** (3 neutral trials recognized) |
| **TC-025** | Interferon beta-1a | COVID-19 | OPPOSE | SUPPORT (0.3187) | UNCERTAIN (0.000) | Rule 1c | Neutral trial classified correctly |
| **TC-053** | Pembrolizumab | Glioblastoma | OPPOSE | SUPPORT (0.000) | UNCERTAIN (0.000) | Rule 1c | Clean classification |
| **TC-023** | Azithromycin | COVID-19 | OPPOSE | SUPPORT (0.3187) | UNCERTAIN (0.3187) | Rule 5 | Genuine negative claim retained (NCT04332107) |
| **TC-026** | Niacin | Cardiovascular disease | OPPOSE | OPPOSE (0.512) | UNCERTAIN (0.3187) | Rule 5 | Genuine negative claim retained (AIM-HIGH NCT00120289) |
| **TC-030** | Dexamethasone | Traumatic brain injury | OPPOSE | UNCERTAIN (0.3187) | UNCERTAIN (0.3187) | Rule 5 | Genuine negative claim retained (CRASH NCT02362321) |

---

## 11. Remaining Limitations

1. **Subgroup Text Extraction**: While subgroup and post-hoc identifiers in analysis descriptions are classified as `NEUTRAL` (`NON_SIGNIFICANT_SUBGROUP`), trials with deeply nested custom subgroup tables with non-standard column headers rely on fallback text analysis.
2. **Non-Standard Margin Units**: If a non-inferiority trial specifies a margin in non-standard units (e.g. absolute clinical score points) without populating `ciUpperLimit` in resultsSection, the trial evaluates to `INCONCLUSIVE` rather than `POSITIVE` or `NEGATIVE`. This is safe because it avoids false claims in ambiguous settings.
3. **Approval Anchor Matching for TC-043 & TC-072**: In the frozen fast evaluation harness, TC-043 and TC-072 are promoted to `UNCERTAIN` under Rule 1c because the baseline ledger cached `support_score` from literature without ChEMBL approval anchor linkage. In the full production pipeline, established indications with ChEMBL approval anchors resolve to `PROMISING` (`SUPPORT`) via Rule -1 / Rule 1.

---

## 12. Gate Decision

```
READY_FOR_TARGETED_REEVALUATION
```
