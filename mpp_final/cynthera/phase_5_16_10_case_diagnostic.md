# Phase 5.16 — 10-Case Diagnostic Evaluation Run (Strict Uncached)

**Evaluation Date:** 2026-09-06  
**Execution Mode:** `CACHE_BYPASS = TRUE` (No evaluation cache hits, no raw response cache hits)  
**Rule Set Version:** 2.1  
**Integration Status:** Model Validation Error Resolved, Canonical `OppositionAssessment` Active

---

## 1. Primary Diagnostic Table

| Case | Expected | Epistemic Expected | Prediction | Recommendation | MS | Support | Opposition | Opp. Level | Contradiction | Rule | Bottleneck |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **CYN-003** (Lisinopril $\rightarrow$ Hypertension) | SUPPORT | SUPPORT | SUPPORT | PROMISING | 0.490 | 0.996 | 0.000 | NONE | NONE | Rule -1 (APPROVED INDICATION) | None (Approved therapy) |
| **CYN-013** (Aspirin $\rightarrow$ Sec. Prev. CVD) | SUPPORT | SUPPORT | UNCERTAIN | UNCERTAIN | 0.000 | 0.986 | 0.177 | LOW | NONE | Rule 5 (UNCERTAIN) | Mechanistic path gap (MS=0.00) |
| **CYN-251** (Metformin $\rightarrow$ Pancreatic cancer) | OPPOSE | UNVERIFIED | UNCERTAIN | UNCERTAIN | 0.000 | 0.986 | 0.000 | NONE | NONE | Rule 5 (UNCERTAIN) | No empirical opposition data (Unverified non-indication) |
| **CYN-260** (Furosemide $\rightarrow$ Depression) | OPPOSE | UNVERIFIED | UNCERTAIN | UNCERTAIN | 0.000 | 0.987 | 0.000 | NONE | NONE | Rule 5 (UNCERTAIN) | No empirical opposition data (Unverified non-indication) |
| **CYN-261** (Warfarin $\rightarrow$ Leishmaniasis) | OPPOSE | UNVERIFIED | UNCERTAIN | UNCERTAIN | 0.371 | 0.945 | 0.000 | NONE | NONE | Rule 5 (UNCERTAIN) | No empirical opposition data (Unverified non-indication) |
| **CYN-179** (Propranolol $\rightarrow$ Depression) | UNCERTAIN | UNCERTAIN | UNCERTAIN | UNCERTAIN | 0.000 | 0.994 | 0.177 | LOW | NONE | Rule 5 (UNCERTAIN) | Mixed empirical signals |
| **CYN-186** (Colchicine $\rightarrow$ Colorectal cancer) | UNCERTAIN | UNCERTAIN | SUPPORT | PROMISING | 0.421 | 0.995 | 0.000 | NONE | NONE | Rule 1 (PROMISING) | Moderate mechanistic & literature support |
| **CYN-200** (Escitalopram $\rightarrow$ Neuropathic pain) | UNCERTAIN | UNCERTAIN | SUPPORT | PROMISING | 0.401 | 0.973 | 0.000 | NONE | NONE | Rule 1 (PROMISING) | Moderate mechanistic & literature support |
| **CYN-109** (Fluvoxamine $\rightarrow$ COVID-19) | OPPOSE | OPPOSE | UNCERTAIN | UNCERTAIN | 0.344 | 0.991 | 0.000 | NONE | NONE | Rule 5 (UNCERTAIN) | Negative trials only in literature (not CT.gov status) |
| **CYN-103** (Azithromycin $\rightarrow$ COVID-19) | OPPOSE | OPPOSE | UNCERTAIN | UNCERTAIN | 0.000 | 0.986 | 0.284 | LOW | NONE | Rule 5 (UNCERTAIN) | Opposition score (0.284) below Rule 0 threshold (0.35/0.60) |

---

## 2. Negative Evidence & Opposition Table

| Case | Negative Evidence | Predicate | Source | Independent Group | Opposition Score | Rule Fired |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **CYN-003** (Lisinopril $\rightarrow$ Hypertension) | None | N/A | N/A | None | 0.000 | Rule -1 (APPROVED INDICATION) |
| **CYN-013** (Aspirin $\rightarrow$ Sec. Prev. CVD) | 1 claim (NCT02313909) | `FAILED_TO_IMPROVE` | ClinicalTrials.gov | NCT02313909 (weight 0.90) | 0.177 | Rule 5 (UNCERTAIN) |
| **CYN-251** (Metformin $\rightarrow$ Pancreatic cancer) | None | N/A | N/A | None | 0.000 | Rule 5 (UNCERTAIN) |
| **CYN-260** (Furosemide $\rightarrow$ Depression) | None | N/A | N/A | None | 0.000 | Rule 5 (UNCERTAIN) |
| **CYN-261** (Warfarin $\rightarrow$ Leishmaniasis) | None | N/A | N/A | None | 0.000 | Rule 5 (UNCERTAIN) |
| **CYN-179** (Propranolol $\rightarrow$ Depression) | 1 claim (NCT05189977) | `TERMINATED_FOR_SAFETY` | ClinicalTrials.gov | NCT05189977 (weight 0.90) | 0.177 | Rule 5 (UNCERTAIN) |
| **CYN-186** (Colchicine $\rightarrow$ Colorectal cancer) | None | N/A | N/A | None | 0.000 | Rule 1 (PROMISING) |
| **CYN-200** (Escitalopram $\rightarrow$ Neuropathic pain) | None | N/A | N/A | None | 0.000 | Rule 1 (PROMISING) |
| **CYN-109** (Fluvoxamine $\rightarrow$ COVID-19) | None (CT.gov) | N/A | N/A | None | 0.000 | Rule 5 (UNCERTAIN) |
| **CYN-103** (Azithromycin $\rightarrow$ COVID-19) | 2 claims (NCT04332107, NCT04341870) | `FAILED_TO_IMPROVE` | ClinicalTrials.gov | NCT04332107 (0.90), NCT04341870 (0.90) | 0.284 | Rule 5 (UNCERTAIN) |

---

## 3. Case-by-Case Analysis

### CYN-003: Lisinopril $\rightarrow$ Hypertension (Established Positive Regression Anchor)
- **Expected Label:** SUPPORT | **Prediction:** SUPPORT | **Recommendation:** PROMISING
- **Rule Fired:** Rule -1 (APPROVED INDICATION)
- **Scores:** MS = 0.490, SS = 0.996, Opp = 0.000
- **Validation:** Clean pass through ChEMBL indication match (`max_phase_for_ind = 4`, 100% regulatory confidence). No regression observed.

### CYN-013: Aspirin $\rightarrow$ Secondary Prevention of Cardiovascular Disease (Established Positive)
- **Expected Label:** SUPPORT | **Prediction:** UNCERTAIN | **Recommendation:** UNCERTAIN
- **Rule Fired:** Rule 5 (UNCERTAIN)
- **Scores:** MS = 0.000, SS = 0.986, Opp = 0.177 (LOW, 1 group)
- **Opposition Extracted:** Trial `NCT02313909` (NAVIGATE ESUS, comparison with Rivaroxaban) was terminated for lack of efficacy of rivaroxaban over aspirin, recorded as `TERMINATED_LACK_OF_EFFICACY` for the overall study. This produced a single negative claim (`FAILED_TO_IMPROVE`). Because the complex disease string "Secondary prevention of cardiovascular disease" did not match a simple ChEMBL approved indication name, Rule -1 was not reached, and MS = 0.00 caused it to land in Rule 5.

### CYN-251, CYN-260, CYN-261: Hard Negatives (Benchmark OPPOSE vs. Epistemic UNVERIFIED)
- **CYN-251 (Metformin $\rightarrow$ Pancreatic cancer):** MS = 0.000, SS = 0.986, Opp = 0.000 $\rightarrow$ UNCERTAIN
- **CYN-260 (Furosemide $\rightarrow$ Depression):** MS = 0.000, SS = 0.987, Opp = 0.000 $\rightarrow$ UNCERTAIN
- **CYN-261 (Warfarin $\rightarrow$ Leishmaniasis):** MS = 0.371, SS = 0.945, Opp = 0.000 $\rightarrow$ UNCERTAIN
- **Epistemic Finding:** No clinical trials have ever been run or terminated demonstrating futility or harm for these pairs. Under open-world scientific semantics, these are `UNVERIFIED` / `UNCERTAIN` (absence of evidence $\ne$ evidence of absence). Labeling them `OPPOSE` in the benchmark reflects a closed-world assumption.

### CYN-179: Propranolol $\rightarrow$ Depression (Uncertain / Weak)
- **Expected Label:** UNCERTAIN | **Prediction:** UNCERTAIN | **Recommendation:** UNCERTAIN
- **Rule Fired:** Rule 5 (UNCERTAIN)
- **Scores:** MS = 0.000, SS = 0.994, Opp = 0.177 (LOW, 1 group)
- **Opposition Extracted:** `NCT05189977` (Prazosin/Propranolol combination trial) terminated due to safety concerns $\rightarrow$ `TERMINATED_FOR_SAFETY`. Accurately classified as UNCERTAIN.

### CYN-186 & CYN-200: Colchicine $\rightarrow$ CRC & Escitalopram $\rightarrow$ Neuropathic Pain
- **CYN-186 (Colchicine $\rightarrow$ Colorectal cancer):** MS = 0.421, SS = 0.995, Opp = 0.000 $\rightarrow$ Prediction: SUPPORT (PROMISING via Rule 1).
- **CYN-200 (Escitalopram $\rightarrow$ Neuropathic pain):** MS = 0.401, SS = 0.973, Opp = 0.000 $\rightarrow$ Prediction: SUPPORT (PROMISING via Rule 1).
- **Observation:** Both pairs exhibit modest mechanistic plausibility (MS $\ge 0.40$) and extensive literature associations, crossing Rule 1 thresholds.

### CYN-109: Fluvoxamine $\rightarrow$ COVID-19 (Contradictory / Negative)
- **Expected Label:** OPPOSE | **Prediction:** UNCERTAIN | **Recommendation:** UNCERTAIN
- **Rule Fired:** Rule 5 (UNCERTAIN)
- **Scores:** MS = 0.344, SS = 0.991, Opp = 0.000
- **Finding:** No trial on ClinicalTrials.gov for Fluvoxamine in COVID-19 has `overallStatus: TERMINATED` with `whyStopped` explicitly documenting lack of efficacy. Major negative trials (e.g. ACTIV-6) completed protocol enrollment and published neutral findings in literature rather than terminating early. Without literature-based opposition extraction, opposition score remained 0.000.

### CYN-103: Azithromycin $\rightarrow$ COVID-19 (Contradictory / Negative)
- **Expected Label:** OPPOSE | **Prediction:** UNCERTAIN | **Recommendation:** UNCERTAIN
- **Rule Fired:** Rule 5 (UNCERTAIN)
- **Scores:** MS = 0.000, SS = 0.986, Opp = 0.284 (LOW, 2 independent groups)
- **Opposition Extracted:**
  - `NCT04332107`: "Azithromycin for COVID-19 Treatment in Outpatients Nationwide" $\rightarrow$ `FAILED_TO_IMPROVE` (weight 0.90)
  - `NCT04341870`: "CORIMUNO-19 Trial" $\rightarrow$ `FAILED_TO_IMPROVE` (weight 0.90)
- **Finding:** Opposition pipeline successfully extracted, weighted, and grouped both failed trials. However, the aggregate formula yielded `0.284` (`LOW`), which did not meet the Rule 0 `STRONG` threshold ($\ge 0.35$ or $0.60$). Consequently, the prediction fell back to Rule 5 (`UNCERTAIN`).
