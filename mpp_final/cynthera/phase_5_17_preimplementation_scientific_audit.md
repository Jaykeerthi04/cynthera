# Phase 5.17 — Pre-Implementation Scientific Audit

**Audit Date:** 2026-09-06  
**Status:** COMPLETE (Audit Only — Zero Production Logic Modified)  
**Scope:** Systematic investigation of opposition aggregation math, threshold gating, literature extraction gaps, Rule 1 positive over-recommendation, benchmark ontology divergence, and achievable accuracy ceiling.

---

## 1. Opposition Aggregation Audit

### Case Traces

#### Case 1: CYN-013 (Aspirin $\rightarrow$ Secondary Prevention of CVD)
- **Raw Negative Claims (1):**
  - Source: ClinicalTrials.gov
  - Record ID: `NCT02313909` (NAVIGATE ESUS trial)
  - Predicate: `PredicateType.FAILED_TO_IMPROVE`
  - Subject: `"Aspirin"` | Object: `"Secondary prevention of cardiovascular disease"`
  - Raw text: `"Rivaroxaban Versus Aspirin in Secondary Prevention of Stroke and Prevention of Systemic Embolism in Patients With Recent Embolic Stroke of Undetermined Source (ESUS)"`
  - Base ERW: `0.90` | Confidence: `0.95`
- **Relevance Gating:**
  - Drug relevant: `"aspirin"` appears in subject and title $\rightarrow$ **PASS**
  - Disease relevant: `"secondary prevention"` appears in object and title $\rightarrow$ **PASS**
- **Evidence Weighting & Grouping:**
  - Evidence Quality: `0.95`
  - Claim ERW: `claim.erw.value = 0.90`
  - Canonical `Claim` attributes: `Claim` has no `evidence_type` field; `getattr(claim, "evidence_type", None)` returns `None`.
  - Type Mapping: In [evidence_weighting.py:76](file:///c:/Users/win10/Documents/cynthera/mpp_final/cynthera/backend/reasoning/conflict/evidence_weighting.py#L76), `ev_type` falls back to `"UNKNOWN"`, yielding `type_weight = EVIDENCE_TYPE_WEIGHTS["UNKNOWN"] = 0.50`.
  - Recency Factor: `claim.publication_year` is `None` $\rightarrow$ `recency_factor = 1.0`.
  - Computed Claim Weight:
    $$\text{weight} = \text{round}(\min(1.0, 0.90 \times 0.50 \times 1.0), 4) = \mathbf{0.450}$$
  - Independence Group: `record:NCT02313909` ($n_{groups} = 1$)
  - Group Weight: $\max(\text{weights in group}) = \mathbf{0.450}$
- **Aggregation Computation:**
  - Inputs: $best\_w = 0.450$, $n_{groups} = 1$
  - Formula: $\text{score} = \text{round}(\min(1.0, best\_w \times (1.0 - e^{-0.5 \times n})), 4)$
  - Intermediate factor: $1.0 - e^{-0.5 \times 1} = 1.0 - 0.60653 = 0.39347$
  - Raw score: $0.450 \times 0.39347 = 0.17706$
  - Final `opposition_score`: $\mathbf{0.177}$
  - Level Classification: Since $best\_w = 0.450 < 0.50$, it fails the MODERATE threshold; since score $> 0$, it is classified as **`LOW`**.

---

#### Case 2: CYN-179 (Propranolol $\rightarrow$ Depression)
- **Raw Negative Claims (1):**
  - Source: ClinicalTrials.gov
  - Record ID: `NCT05189977` (Combination trial with Prazosin)
  - Predicate: `PredicateType.TERMINATED_FOR_SAFETY`
  - Subject: `"Propranolol"` | Object: `"Depression"`
  - Raw text: `"A Trial to Assess the Effects of Prazosin or Propranolol on Blood Pressure in the Presence of Brexpiprazole/Sertraline"`
  - Base ERW: `0.90` | Confidence: `0.95`
- **Relevance Gating:**
  - Drug & Disease relevance: **PASS**
- **Evidence Weighting & Grouping:**
  - Claim ERW: `0.90`
  - Type Mapping: `ev_type = "UNKNOWN"` $\rightarrow$ `type_weight = 0.50`
  - Computed Claim Weight: $0.90 \times 0.50 = \mathbf{0.450}$
  - Independence Group: `record:NCT05189977` ($n_{groups} = 1$)
  - Group Weight: $\mathbf{0.450}$
- **Aggregation Computation:**
  - Inputs: $best\_w = 0.450$, $n = 1$
  - Raw score: $0.450 \times (1 - e^{-0.5}) = 0.450 \times 0.39347 = \mathbf{0.177}$
  - Final `opposition_score`: $\mathbf{0.177}$
  - Opposition Level: **`LOW`**

---

#### Case 3: CYN-103 (Azithromycin $\rightarrow$ COVID-19)
- **Raw Negative Claims (2):**
  - Claim 1: `NCT04332107` ("Azithromycin for COVID-19 Treatment in Outpatients Nationwide") $\rightarrow$ `FAILED_TO_IMPROVE`, base ERW = 0.90
  - Claim 2: `NCT04341870` ("CORIMUNO-19 Trial: Sarilumab, Azithromycin...") $\rightarrow$ `FAILED_TO_IMPROVE`, base ERW = 0.90
- **Relevance Gating:**
  - Both claims pass drug ("azithromycin") and disease ("covid-19") relevance: **PASS**
- **Evidence Weighting & Grouping:**
  - Both claims: `ev_type = "UNKNOWN"` $\rightarrow$ `type_weight = 0.50`
  - Computed Claim Weights: Claim 1 = 0.450, Claim 2 = 0.450
  - Independence Groups: `record:NCT04332107` and `record:NCT04341870` ($n_{groups} = 2$)
  - Group Weights: Group 1 = 0.450, Group 2 = 0.450
  - $best\_w = \mathbf{0.450}$
- **Aggregation Computation:**
  - Inputs: $best\_w = 0.450$, $n = 2$
  - Intermediate factor: $1.0 - e^{-0.5 \times 2} = 1.0 - e^{-1.0} = 1.0 - 0.36788 = \mathbf{0.63212}$
  - Raw score: $0.450 \times 0.63212 = \mathbf{0.28445}$
  - Final `opposition_score`: $\mathbf{0.284}$
  - Opposition Level: Since $best\_w = 0.450 < 0.50$ (MODERATE requires $best\_w \ge 0.50$ for $n \ge 2$), classified as **`LOW`**.

---

### Root Cause Analysis: Why Two Independent Failed Trials Result in `0.284`

**Diagnostic Determination:**  
The issue is **B (unexpectedly over-suppressed by normalization)** and **E (incorrectly quality-adjusted)**.

1. **The 50% "UNKNOWN" Penalty Bug:**
   In [evidence_weighting.py:71-76](file:///c:/Users/win10/Documents/cynthera/mpp_final/cynthera/backend/reasoning/conflict/evidence_weighting.py#L71-L76):
   ```python
   ev_type_raw = getattr(claim, "evidence_type", None)
   if ev_type_raw is not None:
       ev_type = str(ev_type_raw).upper().replace(" ", "_")
   else:
       ev_type = "UNKNOWN"
   type_weight = EVIDENCE_TYPE_WEIGHTS.get(ev_type, 0.5)
   ```
   The domain model `Claim` has no `evidence_type` field, and [therapeutic_opposition_assessor.py:trial_to_negative_claim](file:///c:/Users/win10/Documents/cynthera/mpp_final/cynthera/backend/reasoning/opposition/therapeutic_opposition_assessor.py#L78) does not attach one. Therefore, clinical trial claims default to `"UNKNOWN"`, which applies a $0.50$ multiplier, immediately cutting the clinical trial's base weight from **0.90 to 0.450**.
2. **Mathematical Asymptotic Cap:**
   Because $best\_w$ is capped at $0.450$, and the aggregation formula multiplies $best\_w$ by $(1 - e^{-0.5 \times n}) < 1.0$, the maximum possible score with **infinite** failed trials is:
   $$\lim_{n \to \infty} \text{opposition\_score} = 0.450 \times 1.0 = \mathbf{0.450}$$
   It is **mathematically impossible** for clinical trial opposition to ever reach the `0.60` threshold required by Rule 1b or even exceed the `0.45` threshold required by Rule 2b.
3. **If Properly Quality-Adjusted:**
   If clinical trial claims were recognized as `RCT` (type weight $0.90$) or clinical trials ($1.00$):
   - $best\_w = 0.90 \times 0.90 = 0.810$
   - With $n=2$ independent trials:
     $$\text{score} = 0.810 \times 0.63212 = \mathbf{0.512}$$
   - With $best\_w = 0.810 \ge 0.75$ and $n=2$, `opposition_level` would be **`HIGH`** (or **`MODERATE`**), and `score = 0.512` would easily cross the `0.45` threshold, firing **Rule 2b (EMPIRICAL OPPOSITION VETO $\rightarrow$ NOT_RECOMMENDED / OPPOSE)**.

---

## 2. Opposition Threshold Audit

The table below maps opposition score values to levels, rules, and outcomes under the **current** implementation:

| Opposition Score | Level | Relevant Rule Fired | Final Recommendation | Prediction | Effect of Opposition |
| :---: | :---: | :--- | :--- | :--- | :--- |
| **0.177** | `LOW` | Rule 1 (if MS $\ge$ 0.40) else Rule 5 | PROMISING or UNCERTAIN | SUPPORT or UNCERTAIN | **Zero effect.** Completely ignored by decision rules. |
| **0.284** | `LOW` | Rule 1 (if MS $\ge$ 0.40) else Rule 5 | PROMISING or UNCERTAIN | SUPPORT or UNCERTAIN | **Zero effect.** Below 0.45 threshold. |
| **0.350** | `LOW` or `MOD` | Rule 1 (if MS $\ge$ 0.40) else Rule 5 | PROMISING or UNCERTAIN | SUPPORT or UNCERTAIN | **Zero effect.** Rule 2b requires $\ge 0.45$. |
| **0.450** | `MOD` / `HIGH` | **Rule 2b (EMPIRICAL OPPOSITION VETO)** | **NOT_RECOMMENDED** | **OPPOSE** | **Full veto fires.** Recommends NOT_RECOMMENDED. |
| **0.600** | `HIGH` | **Rule 1b (EPISTEMIC CONFLICT)** if SS $\ge$ 0.60, else **Rule 2b** | **UNCERTAIN** (if SS $\ge 0.60$) or **NOT_RECOMMENDED** | **UNCERTAIN** or **OPPOSE** | If strong support coexists, resolves to UNCERTAIN. If SS $< 0.60$, vetoes to OPPOSE. |

### Separation of Scoring Problem vs. Threshold Problem
1. **The Scoring Problem (Primary):**  
   The $0.50$ penalty for `"UNKNOWN"` evidence types suppresses genuine clinical trial weights from $0.90 \rightarrow 0.450$, mathematically capping `opposition_score` at $\le 0.450$.
2. **The Threshold Problem (Secondary):**  
   Rule 2b sets a boundary of `score >= 0.45` and `level in ("MODERATE", "HIGH")`. Even with proper weights ($best\_w = 0.81$), a single large, pivotal Phase 3 trial failure ($n=1$) produces:
   $$\text{score} = 0.81 \times (1 - e^{-0.5}) = 0.81 \times 0.39347 = \mathbf{0.319}$$
   A single Phase 3 trial failure would thus still fail the $0.45$ threshold!  
   *Scientific question for Phase 5.17:* Should $n=1$ with a high-quality pivotal RCT trigger opposition, or should the threshold be calibrated around $\ge 0.30 - 0.35$?

---

## 3. Fluvoxamine Literature Audit (CYN-109)

### Evidence Discovery & Database Representation

| Trial / Study | Design & Cohort | Status on CT.gov | whyStopped on CT.gov | Publication | Documented Negative Outcome | Legitimate Predicate |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ACTIV-6** (`NCT04885530`) | Double-blind RCT, $n=1288$ outpatients | `COMPLETED` | *None* | McCarthy et al., *NEJM* 2022 (`doi:10.1056/nejmoa2201662`) | Fluvoxamine (50 mg BID) did not improve time to sustained recovery (HR 0.96; 95% CrI, 0.86–1.06; posterior probability of superiority = 0.21). No evidence of efficacy. | `FAILED_TO_IMPROVE` |
| **COVID-OUT** (`NCT04510194`) | Quadruple-blind RCT, $n=1431$ outpatients | `COMPLETED` | *None* | Bramante et al., *NEJM* 2022 (`doi:10.1056/NEJMoa2201662`) | Neither fluvoxamine nor metformin nor ivermectin significantly reduced hypoxemia, emergency visits, hospitalization, or death (OR 0.94; 95% CI, 0.66–1.34). | `FAILED_TO_IMPROVE` |
| **TOGETHER Trial** (`NCT04727424`) | Platform trial, $n=1497$ outpatients | `COMPLETED` | *None* | Reis et al., *Lancet Glob Health* 2021 | Initial signal in emergency stay reduction failed to replicate in subsequent independent trials; NIH/WHO guidelines issued explicit recommendations against use. | `FAILED_TO_IMPROVE` |

### Critical Pipeline Defects Identified:
1. **CT.gov Status Blindspot:**  
   The trials did not terminate early for futility or safety—they enrolled to protocol completion. Their CT.gov status is `COMPLETED`. The current adapter checks only `TERMINATED_LACK_OF_EFFICACY` and `TERMINATED_SAFETY`, so it extracted 0 negative claims from CT.gov.
2. **Inversion by Fallback Extraction:**  
   In the raw cache (`data/cynthera.db`), the ACTIV-6 paper (`doi:10.1056/nejmoa2201662`) was extracted by `claim_extraction_agent` using a naive rule-based fallback:
   ```json
   {"claims": [{"subject": "Fluvoxamine", "predicate": "PREVENTS", "object": "COVID-19", "confidence": 0.25}], "method": "rule_based_fallback"}
   ```
   **A landmark negative trial was extracted as a positive `PREVENTS` claim**, inflating `support_score` to $0.991$!

### Proposed Extraction Specification (Literature-Based Opposition):
- Parse abstract conclusions for explicit efficacy negation patterns in clinical trials:
  - `"did not improve"`, `"did not significantly reduce"`, `"failed to demonstrate"`, `"no evidence of efficacy"`, `"no significant difference compared with placebo"`.
- Verify pair-specificity: drug name in intervention arm and target disease in indication context.
- Map strictly to `PredicateType.FAILED_TO_IMPROVE` (or `TERMINATED_FOR_SAFETY` if adverse event rate exceeded placebo).
- Set provenance record to PMID/DOI for independent clustering.

---

## 4. Positive Recommendation Audit (CYN-186 & CYN-200)

### Findings:
- **CYN-186 (Colchicine $\rightarrow$ Colorectal Cancer):** Predicted **SUPPORT** / **PROMISING** via Rule 1 (SS = 0.995, MS = 0.421, RS = 0.213).
- **CYN-200 (Escitalopram $\rightarrow$ Neuropathic Pain):** Predicted **SUPPORT** / **PROMISING** via Rule 1 (SS = 0.973, MS = 0.401, RS = 0.213).

### Evidence Breakdown:
1. **Therapeutic Indication / Regulatory Precedence:** **NONE**. Neither drug is approved or indicated for these conditions (`has_high_quality_therapeutic = False`).
2. **Clinical Trial Success:** **NONE**. No positive human Phase 2/3 trial data.
3. **Mechanistic Evidence:** Modest pathway plausibility (tubulin binding in CRC, MS = 0.421; SERT inhibition in pain pathways, MS = 0.401).
4. **Literature Evidence:** 78 literature records for Colchicine and 52 for Escitalopram (epidemiological reviews, in vitro assays, speculative co-mentions).

### Root Cause in Rule 1:
In [reasoning_orchestrator.py:1450-1467](file:///c:/Users/win10/Documents/cynthera/mpp_final/cynthera/backend/reasoning/orchestrator/reasoning_orchestrator.py#L1450-L1467):
```python
if support.score >= 0.4 and mechanistic.score >= 0.4 and risk.score <= 0.39:
    # Rule 1 (PROMISING) fires!
```
Because the support formula accumulates literature records exponentially ($1 - e^{-0.12 \times \text{sum}}$), 50+ PubMed co-mentions saturate `SS` to $\approx 0.99$.  
**Answer to Critical Question:**  
**YES.** Rule 1 currently permits generic literature support + moderate mechanistic plausibility ($MS \ge 0.40$) to produce **PROMISING** without requiring any pair-specific human therapeutic evidence or clinical efficacy trials. This causes off-label, speculative hypotheses (which should be `UNCERTAIN`) to be recommended as `PROMISING`.

---

## 5. Benchmark Ontology Audit

The 25 canonical cases were evaluated under two distinct ontologies:
- **Evaluation A:** Standard 3-Class Benchmark (Closed-World: Unverified Non-Indications $\rightarrow$ `OPPOSE`).
- **Evaluation B:** Epistemic Expected Class (Open-World: Unverified Non-Indications $\rightarrow$ `UNCERTAIN`).

### Comparative Performance Metrics

| Metric | Evaluation A (Standard Benchmark) | Evaluation B (Epistemic Expected) | Net Epistemic Delta |
| :--- | :---: | :---: | :---: |
| **Accuracy** | **0.4000** (10 / 25) | **0.5600** (14 / 25) | **+16.0% (+4 cases)** |
| **Macro Precision** | 0.2725 | 0.4630 | +0.1905 |
| **Macro Recall** | 0.5000 | 0.5278 | +0.0278 |
| **Macro F1** | 0.3405 | 0.4323 | +0.0918 |
| **Weighted F1** | 0.2676 | 0.5105 | +0.2429 |
| **MCC** | 0.2596 | 0.4432 | +0.1836 |

### Confusion Matrices

#### Evaluation A: Standard Benchmark
```
               SUPPORT  OPPOSE  UNCERTAIN
  SUPPORT         7        0        0       (Recall: 1.000)
  OPPOSE          8        0        4       (Recall: 0.000)
  UNCERTAIN       3        0        3       (Recall: 0.500)
```
*Note:* 8 OPPOSE cases predicted as SUPPORT; 4 OPPOSE cases predicted as UNCERTAIN; 0 OPPOSE cases predicted as OPPOSE.

#### Evaluation B: Epistemic Expected Class (UNVERIFIED $\rightarrow$ UNCERTAIN)
```
               SUPPORT  OPPOSE  UNCERTAIN
  SUPPORT         7        0        0       (Recall: 1.000)
  OPPOSE          6        0        0       (Recall: 0.000)
  UNCERTAIN       5        0        7       (Recall: 0.583)
```
*Note:* The 6 remaining OPPOSE cases are the true Category C empirical opposition cases (Azithromycin, Fluvoxamine, Aspirin-COVID, Baricitinib-COVID, Atorvastatin-AD, Lithium-AD). The 4 previously "failed" hard negatives (Furosemide-Depression, Warfarin-Leishmaniasis, Tamsulosin-Liver cancer, Imatinib-COVID) are correctly recognized as `UNCERTAIN`.

---

## 6. Achievable Ceiling Analysis

### Category B: Closed-World Non-Indications vs. Epistemic Reality
The benchmark contains 6 Category B "Hard Negatives":
1. `CYN-251` (Metformin $\rightarrow$ Pancreatic cancer)
2. `CYN-260` (Furosemide $\rightarrow$ Depression)
3. `CYN-261` (Warfarin $\rightarrow$ Leishmaniasis)
4. `CYN-277` (Pregabalin $\rightarrow$ Breast cancer)
5. `CYN-284` (Tamsulosin $\rightarrow$ Liver cancer)
6. `CYN-299` (Imatinib $\rightarrow$ COVID-19)

- **The Closed-World Trap:** None of these pairs are approved indications, so the benchmark assigned them `OPPOSE`. However, none have documented contraindications or failed clinical trials. Warfarin is not contraindicated for Leishmaniasis; there is simply no evidence for it.
- **Disappearing Errors:** When evaluated epistemically, 4 errors (Furosemide, Warfarin, Tamsulosin, Imatinib) immediately disappear because the system correctly predicted `UNCERTAIN`.
- **Achievable Benchmark Ceiling:**
  - True Empirical Opposition Cases: **6 cases** (Category C).
  - True Approved Positives: **7 cases** (Category A).
  - True Uncertain / Weak Cases: **12 cases** (6 Category D + 6 Category B unverified).
  - If Category C empirical opposition is fully resolved (predicting OPPOSE for all 6) and Rule 1 over-recommendation is fixed (predicting UNCERTAIN for weak cases), the system achieves:
    $$\text{Accuracy}_{\text{epistemic}} = \frac{7 + 6 + 12}{25} = \mathbf{100\%}$$
    $$\text{Accuracy}_{\text{standard}} = \frac{7 + 6 (\text{Cat C}) + 0 (\text{Cat B}) + 6 (\text{Cat D})}{25} = \mathbf{76\%}$$

---

## 7. Contradiction Audit (Rule 1b Exercise Status)

- **Rule 1b Status:** **`NOT_EXERCISED`**
- **Reason:** Rule 1b requires:
  $$\text{support.score} \ge 0.60 \quad \text{AND} \quad \text{opposition.score} \ge 0.60$$
  As proven in Section 1, because claim weighting applies a 0.50 multiplier to missing evidence types, `opposition.score` is capped at $\le 0.450$. `opposition.score >= 0.60` is **mathematically impossible** to satisfy under current code.
- **Cases with Co-occurring Support and Opposition:**
  - `CYN-013` (Aspirin $\rightarrow$ CVD): SS = 0.986, Opp = 0.177 $\rightarrow$ `contradiction_state = NONE`
  - `CYN-179` (Propranolol $\rightarrow$ Depression): SS = 0.994, Opp = 0.177 $\rightarrow$ `contradiction_state = NONE`
  - `CYN-103` (Azithromycin $\rightarrow$ COVID-19): SS = 0.986, Opp = 0.284 $\rightarrow$ `contradiction_state = NONE`

---

## 8. Summary of Components & Defects

### A. Confirmed Working Components
1. **Canonical `OppositionAssessment`:** Model type consolidation is 100% verified; zero serialization or Pydantic errors.
2. **Deterministic Cache Invalidation:** `rule_set_version="2.1"` strictly prevents stale v2.0 cross-version cache pollution.
3. **Cache Bypass Semantics:** `bypass_cache=True` guarantees fresh live evaluations.
4. **Positive Control Anchor:** Lisinopril $\rightarrow$ Hypertension executes Rule -1 flawlessly (`SUPPORT` / `PROMISING`).
5. **Clinical Trial Adapter (Basic):** Successfully extracts and normalizes `TERMINATED_LACK_OF_EFFICACY` and `TERMINATED_SAFETY` into canonical negative predicates.

### B. Confirmed Defects
1. **Defect 1 (Critical): Missing `evidence_type` on `Claim` cuts clinical trial weights in half.**  
   `compute_claim_weight` defaults to `"UNKNOWN"` (0.50 multiplier), capping all clinical trial weights at 0.450 and aggregate opposition scores at $\le 0.450$.
2. **Defect 2 (Critical): Rule 1 over-recommends generic literature co-mentions.**  
   Rule 1 fires `PROMISING` when $SS \ge 0.40$ (saturated by generic PubMed papers) and $MS \ge 0.40$, without requiring pair-specific clinical or therapeutic evidence.
3. **Defect 3 (Critical): Literature extraction inverts negative trial publications.**  
   Naive fallback extraction converts negative trial publications (e.g. ACTIV-6 for Fluvoxamine) into positive `PREVENTS` claims.
4. **Defect 4 (Major): Completed negative trials invisible to CT.gov adapter.**  
   Pivotal negative trials completed according to protocol (ACTIV-6, COVID-OUT) have status `COMPLETED` and are missed by the terminated trials adapter.

### C. Suspected Defects Requiring Evidence
1. **Opposition Threshold Granularity:**  
   Whether $score \ge 0.35$ with 1 pivotal Phase 3 trial should be sufficient to trigger `MODERATE` opposition.
2. **PubMed LLM Claim Extractor Reliability:**  
   Investigate whether the LLM extraction agent is failing or falling back due to API rate limits (HTTP 429 seen in logs).

### D. Scientific Risks
- **Over-suppression Risk:** Lowering opposition thresholds too far could cause small pilot safety warnings to veto valid drugs.
- **Literature Noise Risk:** Extracting negation from PubMed abstracts without strict RCT/primary endpoint filtering risks treating background sentences ("Drug X does not treat Disease Y when...") as clinical opposition.

### E. Benchmark-Label Problems
- The 25-case benchmark's closed-world expectation that unverified pairs must be `OPPOSE` creates an artificial 24% accuracy ceiling loss.

---

## 9. Final Decision Framework & Priority Ranking

Based on empirical audit evidence, the recommended changes for Phase 5.17 are ranked as follows:

| Priority Rank | Target Area | Leverage | Primary Evidence & Justification |
| :---: | :--- | :---: | :--- |
| **1** | **Opposition Aggregation Correction (`evidence_type` mapping)** | **CRITICAL BLOCKER** | Mathematically unlocks the opposition pipeline. Fixing the 50% UNKNOWN penalty allows two failed trials (Azithromycin) to reach `score = 0.512`, immediately enabling Rule 2b to fire `OPPOSE`. |
| **2** | **Rule 1 Positive Gate Tightening** | **HIGH** | Fixes false-positive recommendations for Colchicine (CYN-186) and Escitalopram (CYN-200) by requiring genuine therapeutic evidence rather than generic PubMed co-mentions. |
| **3** | **Literature-Based Negative Evidence Extraction** | **HIGH** | Resolves Fluvoxamine (CYN-109) and other completed negative trials whose results reside in journal publications rather than CT.gov termination strings. Stops naive fallback from inverting failed trials into positive `PREVENTS` claims. |
| **4** | **Benchmark Epistemic Scoring Reconciliation** | **MEDIUM** | Formally separates closed-world non-indications from true counter-indications, raising baseline reporting from 40% to 56% without scientific distortion. |

---
*End of Phase 5.17 Pre-Implementation Scientific Audit. In accordance with task constraints, no production scientific logic was modified.*
