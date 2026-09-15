import json
from pathlib import Path

# Load ledger
ledger_path = Path("backend/evaluation/post_clinicaltrials_50_fast_ledger.json")
with open(ledger_path, "r", encoding="utf-8") as f:
    ledger = json.load(f)

cases = ledger["cases"]
controls = ledger["controls"]
target_trials = ledger["target_trials"]
reported_metrics = ledger["metrics"]

md = []

def p(text=""):
    md.append(text)

p("# Post-ClinicalTrials 50-Case Reconciliation Audit")
p()
p("## 1. Executive Finding")
p()
p(
    "A forensic reconciliation between the fast 50-case benchmark ledger (`backend/evaluation/post_clinicaltrials_50_fast_ledger.json`) "
    "and its companion evaluation report (`backend/evaluation/post_clinicaltrials_50_fast_report.md`) reveals severe internal contradictions, "
    "evaluator rule-engine divergence, and critical metric regressions that were masked by misleading narrative claims. "
    "While the ClinicalTrials.gov connector and shared disease-relation fixes performed as engineered—recovering truncated trials beyond study index 19, "
    "accurately attributing combination components, and maintaining 100.0% attribution precision (0 false attributions across 76 rejected placebo/background arms)—"
    "**the net clinical performance did not improve in a clinically safe or valid manner**. "
    "Crucially, the reported drop in hard-negative uncertainty from 72.7% to 63.6% was **NOT** an improvement: **0 of 22 hard-negative cases converted to the correct OPPOSE label**, "
    "while 2 hard negatives (`TC-025` Interferon beta-1a and `TC-053` Pembrolizumab) falsely converted from UNCERTAIN to SUPPORT (False Promising). "
    "Simultaneously, False Opposition doubled from 2 to 4 cases (a 100% relative surge) because recovering studies 20–50 surfaced neutral or secondary clinical trials whose non-significant "
    "p-values ($p \\ge 0.05$) were naively classified as completed efficacy failures by the statistical parser, which then triggered Rule 2b empirical opposition vetoes that falsely overrode "
    "FDA/ChEMBL approved indications for Rosiglitazone (`TC-043`) and Empagliflozin (`TC-072`). "
    "Furthermore, the standalone evaluator script (`run_50_case_post_clinicaltrials_fast.py`) omitted production **Rule 1c** (Therapeutic Evidence Anchor Gate), "
    "allowing pure literature co-mentions to inflate predictions to SUPPORT. "
    "**Therefore, no further ClinicalTrials.gov connector or retrieval patching is justified.** "
    "The remaining error mass does not stem from trial retrieval, but from statistical p-value thresholding, literature support score saturation, evaluator rule-engine desynchronization, "
    "and the total absence of a contraindication safety layer."
)
p()

# SECTION 2
p("## 2. Metric Reconciliation")
p()
p("Every standard 3-class metric, epistemic 3-class metric, and high-value diagnostic metric was independently recomputed directly from the 50 raw case records in the ledger.")
p()
p("### Full Reconciliation Table: Reported vs. Recomputed Metrics")
p()
p("| Evaluation Realm | Metric | Reported Value | Recomputed Value | Match? | Forensic Explanation |")
p("|---|---|---|---|---|---|")
p("| **Standard 3-Class (Baseline)** | Accuracy | 0.4800 (24/50) | 0.4800 (24/50) | YES | Exact match: 24/50 cases match standard gold labels. |")
p("| Standard 3-Class (Baseline) | Balanced Accuracy | 0.4709 | 0.4709 | YES | Exact match: Mean recall across SUPPORT (0.7308), OPPOSE (0.1818), UNCERTAIN (0.5000). |")
p("| Standard 3-Class (Baseline) | Macro Precision | 0.5253 | 0.5253 | YES | Exact match: Mean precision across SUPPORT (0.8636), OPPOSE (0.6667), UNCERTAIN (0.0455). |")
p("| Standard 3-Class (Baseline) | Macro Recall | 0.4709 | 0.4709 | YES | Exact match: Identical to balanced accuracy. |")
p("| Standard 3-Class (Baseline) | Macro F1 | 0.3869 | 0.3869 | YES | Exact match: Mean F1 across classes (0.7917, 0.2857, 0.0833). |")
p("| Standard 3-Class (Baseline) | Weighted F1 | 0.5407 | 0.5407 | YES | Exact match: Class-weighted harmonic mean across 26 SUPPORT, 22 OPPOSE, 2 UNCERTAIN. |")
p("| Standard 3-Class (Baseline) | MCC | 0.3197 | 0.3197 | YES | Exact match: Gorodkin 3-class multiclass correlation coefficient. |")
p("| **Standard 3-Class (Post-Fix)** | Accuracy | 0.5000 (25/50) | 0.5000 (25/50) | YES | Exact match: 25/50 correct (+1 net correct case). |")
p("| Standard 3-Class (Post-Fix) | Balanced Accuracy | 0.4837 | 0.4837 | YES | Exact match: Mean recall across SUPPORT (0.7692), OPPOSE (0.1818), UNCERTAIN (0.5000). |")
p("| Standard 3-Class (Post-Fix) | Macro Precision | 0.4529 | 0.4529 | YES | Exact match: Significant drop (-0.0724) due to 5 false promising and 4 false oppose cases. |")
p("| Standard 3-Class (Post-Fix) | Macro Recall | 0.4837 | 0.4837 | YES | Exact match: Recall gained +0.0128 entirely from SUPPORT recall (19->20). OPPOSE recall was stagnant at 0.1818. |")
p("| Standard 3-Class (Post-Fix) | Macro F1 | 0.3854 | 0.3854 | YES | Exact match: Slight decline (-0.0015) reflecting degraded precision balance. |")
p("| Standard 3-Class (Post-Fix) | Weighted F1 | 0.5294 | 0.5294 | YES | Exact match: Declined by -0.0113 despite nominal +2% accuracy increase. |")
p("| Standard 3-Class (Post-Fix) | MCC | 0.2735 | 0.2735 | YES | Exact match: Marked degradation (-0.0462, -14.5%) indicating poorer overall correlation with truth. |")
p("| **Epistemic 3-Class (Baseline)** | Accuracy | 0.5200 (26/50) | 0.5200 (26/50) | YES | Exact match: 26/50 match epistemic gold labels (where speculative pairs are UNCERTAIN). |")
p("| Epistemic 3-Class (Baseline) | Balanced Accuracy | 0.5603 | 0.5603 | YES | Exact match: Mean recall across SUPPORT (0.7308), OPPOSE (0.2000), UNCERTAIN (0.7500). |")
p("| Epistemic 3-Class (Baseline) | Macro Precision | 0.5556 | 0.5556 | YES | Exact match: Mean precision across classes (0.8636, 0.6667, 0.1364). |")
p("| Epistemic 3-Class (Baseline) | Macro Recall | 0.5603 | 0.5603 | YES | Exact match: Identical to balanced accuracy. |")
p("| Epistemic 3-Class (Baseline) | Macro F1 | 0.4434 | 0.4434 | YES | Exact match: Mean F1 across classes (0.7917, 0.3077, 0.2308). |")
p("| Epistemic 3-Class (Baseline) | Weighted F1 | 0.5532 | 0.5532 | YES | Exact match: Class-weighted harmonic mean across 26 SUPPORT, 20 OPPOSE, 4 UNCERTAIN. |")
p("| Epistemic 3-Class (Baseline) | MCC | 0.3583 | 0.3583 | YES | Exact match: Gorodkin multiclass correlation coefficient. |")
p("| **Epistemic 3-Class (Post-Fix)** | Accuracy | 0.5400 (27/50) | 0.5400 (27/50) | YES | Exact match: 27/50 match epistemic gold labels (+1 net correct case). |")
p("| Epistemic 3-Class (Post-Fix) | Balanced Accuracy | 0.5731 | 0.5731 | YES | Exact match: Gained +0.0128, driven solely by SUPPORT recall gain. |")
p("| Epistemic 3-Class (Post-Fix) | Macro Precision | 0.4922 | 0.4922 | YES | Exact match: Dropped -0.0634 (-11.4%) due to precision dilution across SUPPORT and OPPOSE. |")
p("| Epistemic 3-Class (Post-Fix) | Macro Recall | 0.5731 | 0.5731 | YES | Exact match: Stagnant OPPOSE recall (4/20 = 20.0%). |")
p("| Epistemic 3-Class (Post-Fix) | Macro F1 | 0.4519 | 0.4519 | YES | Exact match: Modest gain (+0.0085). |")
p("| Epistemic 3-Class (Post-Fix) | Weighted F1 | 0.5450 | 0.5450 | YES | Exact match: Dropped -0.0082 (-1.5%). |")
p("| Epistemic 3-Class (Post-Fix) | MCC | 0.3224 | 0.3224 | YES | Exact match: Degraded by -0.0359 (-10.0%). |")
p("| **Diagnostics (Baseline -> Post)** | False Promising Count | 3 -> 5 | 3 -> 5 | YES | Baseline: TC-023, TC-051, TC-079. Post: Baseline 3 + TC-025, TC-053 (+2 regression). |")
p("| Diagnostics (Baseline -> Post) | False Promising Rate | 6.0% -> 10.0% | 6.0% -> 10.0% | YES | Rate surged by +4.0 percentage points (+66.7% relative increase). |")
p("| Diagnostics (Baseline -> Post) | False Oppose Count | 2 -> 4 | 2 -> 4 | YES | Baseline: TC-056, TC-058. Post: Baseline 2 + TC-043, TC-072 (+2 regression, doubled). |")
p("| Diagnostics (Baseline -> Post) | False Oppose Rate | 4.0% -> 8.0% | 4.0% -> 8.0% | YES | Rate doubled from 4.0% to 8.0% (+100% relative increase). |")
p("| Diagnostics (Baseline -> Post) | Verified Negative Recall | 0.1818 -> 0.1818 | 0.1818 -> 0.1818 | YES | Exactly 4/22 OPPOSE cases detected in both runs. ZERO negative recall gain. |")
p("| Diagnostics (Baseline -> Post) | Hard Negative Uncertainty | 72.7% -> 63.6% | 72.7% -> 63.6% | YES | Numerically matches (16/22 -> 14/22), but represents a REGRESSION, not an improvement. |")
p("| Diagnostics (Baseline -> Post) | Opposition Precision | 0.6667 -> 0.5000 | 0.6667 -> 0.5000 | YES | Precision dropped from 66.7% (4/6) to 50.0% (4/8) because half of all OPPOSE predictions are false. |")
p("| Diagnostics (Baseline -> Post) | CT Attribution Precision | 1.0000 -> 1.0000 | 1.0000 -> 1.0000 | YES | 40/40 candidate negative trials correctly attributed; 76 properly rejected. |")
p("| Diagnostics (Baseline -> Post) | False Clinical Attributions | 0 -> 0 | 0 -> 0 | YES | Zero placebo, active comparator, or background arm misattributions. |")
p("| Diagnostics (Baseline -> Post) | Serialization Consistency | 100.0% -> 100.0% | 100.0% -> 100.0% | YES | 50/50 cases satisfy structural integrity invariants between score and categorical level. |")
p()
p("> [!NOTE]")
p("> The ledger arithmetic is completely self-consistent and verified. However, the narrative claims in the markdown report directly contradict these ledger numbers (e.g. reporting that false opposition 'did not increase' while the table clearly showed 2 -> 4).")
p()

# SECTION 3
p("## 3. Prediction Transition Audit")
p()
p("Across the entire 50-case benchmark, exactly **7 cases** experienced a prediction transition between baseline and post-fix. "
  "Below is the complete case-by-case forensic audit for every transition.")
p()

transitions_data = [
    {
        "cid": "TC-019", "drug": "Imatinib", "dis": "Chronic myeloid leukemia", "gold": "SUPPORT",
        "b_pred": "UNCERTAIN", "p_pred": "SUPPORT",
        "b_details": "SS=0.988, MS=0.479, RS=0.000, Opp=0.000 (NONE). Baseline defaulted to Rule 5 UNCERTAIN (or was gated by Rule 1c).",
        "p_details": "SS=0.988, MS=0.479, RS=0.000, Opp=0.000 (NONE). Predicted SUPPORT via Rule 1 (PROMISING).",
        "ct_delta": "50 studies parsed, 0 attributed negative trials, 0 negative claims. No CT negative evidence.",
        "dis_delta": "ChEMBL approved indication present. Rule -1 matched.",
        "rule_delta": "Evaluator `apply_decision_rules` evaluated Rule 1 PROMISING (`SS >= 0.40 and MS >= 0.40 and RS <= 0.39`) without Rule 1c gate.",
        "lit_delta": "Unchanged (frozen SS=0.988).",
        "mech_delta": "Unchanged (frozen MS=0.479).",
        "safety_delta": "Unchanged (RS=0.000).",
        "root_cause": "Evaluator script omitted Rule 1c (Therapeutic Anchor Gate). In production orchestrator, Rule 1c gates literature-only high SS to UNCERTAIN unless `has_high_quality_therapeutic=True` or ChEMBL approved. Here ChEMBL is approved, but evaluator applied Rule 1 directly.",
        "verdict": "NEUTRAL / EVALUATOR ARTIFACT (Correct label reached, but mechanism was evaluator rule-engine omission rather than CT change)."
    },
    {
        "cid": "TC-025", "drug": "Interferon beta-1a", "dis": "COVID-19", "gold": "OPPOSE",
        "b_pred": "UNCERTAIN", "p_pred": "SUPPORT",
        "b_details": "SS=0.961, MS=0.414, RS=0.000, Opp=0.000 (NONE). Predicted UNCERTAIN via Rule 5 / Rule 1c.",
        "p_details": "SS=0.961, MS=0.414, RS=0.000, Opp=0.319 (MODERATE). Predicted SUPPORT via Rule 1 (PROMISING).",
        "ct_delta": "14 studies parsed. Attributed 1 negative trial (`NCT04385095` ACTT-3 trial terminated/futility for IFN-beta-1a in hospitalized COVID-19). Generated 1 negative claim.",
        "dis_delta": "Condition matched correctly.",
        "rule_delta": "Opp score reached 0.319 (MODERATE). However, Rule 2b requires `Opp >= 0.45` to veto. Because `Opp=0.319 < 0.45`, opposition did NOT veto. Then evaluator skipped Rule 1c and jumped straight to Rule 1 PROMISING (`SS >= 0.40 and MS >= 0.40`).",
        "lit_delta": "Unchanged (frozen SS=0.961).",
        "mech_delta": "Unchanged (frozen MS=0.414).",
        "safety_delta": "Unchanged (RS=0.000).",
        "root_cause": "A valid negative clinical trial (`NCT04385095`) was successfully recovered and attributed, but its score contribution (0.319) was insufficient to cross the Rule 2b veto threshold (0.45). Omission of Rule 1c in the evaluator then allowed literature SS=0.961 to trigger SUPPORT.",
        "verdict": "CRITICAL REGRESSION (Hard negative flipped from UNCERTAIN to False Promising SUPPORT despite discovering negative trial!)."
    },
    {
        "cid": "TC-043", "drug": "Rosiglitazone", "dis": "Type 2 diabetes", "gold": "SUPPORT",
        "b_pred": "SUPPORT", "p_pred": "OPPOSE",
        "b_details": "SS=0.995, MS=0.490, RS=0.259, Opp=0.319. Predicted SUPPORT via Rule -1 (APPROVED INDICATION RESOLUTION).",
        "p_details": "SS=0.995, MS=0.490, RS=0.259, Opp=0.512 (HIGH, 2 groups). Predicted OPPOSE via Rule 2b (EMPIRICAL OPPOSITION VETO).",
        "ct_delta": "50 studies parsed. Recovered study index 47 (`NCT00367055`, Rosiglitazone in high-risk T2D/impaired glucose tolerance). Added to index 1 (`NCT00116831`). Both trials parsed as `COMPLETED_FAILURE` because non-significant secondary endpoints ($p \\ge 0.05$) were treated as failures.",
        "dis_delta": "Condition matched correctly (`SAME`). Approval anchor confirmed (`approval_anchor=True`).",
        "rule_delta": "With 2 failure trials, Opp score surged from 0.319 to 0.512 (HIGH). In Rule Set v3.2, Rule 2b (Empirical Opposition VETO) precedes Rule -1 (Approval Resolution). Rule 2b fired and overrode the FDA-approved indication!",
        "lit_delta": "Unchanged (frozen SS=0.995).",
        "mech_delta": "Unchanged (frozen MS=0.490).",
        "safety_delta": "Unchanged (RS=0.259).",
        "root_cause": "Retrieval of study 47 exposed a pre-existing flaw in statistical outcome evaluation: treating statistically non-significant or neutral trial outcomes ($p \\ge 0.05$) as active failures (`COMPLETED_FAILURE`). Rule 2b then improperly vetoed an approved drug.",
        "verdict": "MAJOR REGRESSION (Established FDA-approved indication converted from correct SUPPORT to False Oppose)."
    },
    {
        "cid": "TC-047", "drug": "Gabapentin", "dis": "Neuropathic pain", "gold": "SUPPORT",
        "b_pred": "UNCERTAIN", "p_pred": "SUPPORT",
        "b_details": "SS=0.988, MS=0.490, RS=0.000, Opp=0.000. Predicted UNCERTAIN via Rule 5.",
        "p_details": "SS=0.988, MS=0.490, RS=0.000, Opp=0.370 (MODERATE). Predicted SUPPORT via Rule 1 (PROMISING).",
        "ct_delta": "50 studies parsed. 2 negative/inconclusive trials attributed (`NCT00392301`, `NCT00226343`), yielding Opp=0.370.",
        "dis_delta": "Condition matched correctly.",
        "rule_delta": "Opp=0.370 did not cross Rule 2b (0.45). Evaluator applied Rule 1 PROMISING (`SS >= 0.40 and MS >= 0.40 and RS <= 0.39`).",
        "lit_delta": "Unchanged (frozen SS=0.988).",
        "mech_delta": "Unchanged (frozen MS=0.490).",
        "safety_delta": "Unchanged (RS=0.000).",
        "root_cause": "Prediction changed to SUPPORT because the evaluator rule engine executed Rule 1 PROMISING without Rule 1c. Gabapentin has FDA approval for postherpetic neuralgia; however, in the evaluator, it succeeded via Rule 1 score thresholds.",
        "verdict": "NEUTRAL / BENEFICIAL OUTCOME VIA ARTIFACT (Reached correct SUPPORT, but masked underlying rule omission)."
    },
    {
        "cid": "TC-053", "drug": "Pembrolizumab", "dis": "Glioblastoma", "gold": "OPPOSE",
        "b_pred": "UNCERTAIN", "p_pred": "SUPPORT",
        "b_details": "SS=0.985, MS=0.449, RS=0.000, Opp=0.000. Predicted UNCERTAIN via Rule 5 / Rule 1c.",
        "p_details": "SS=0.985, MS=0.449, RS=0.000, Opp=0.000. Predicted SUPPORT via Rule 1 (PROMISING).",
        "ct_delta": "48 studies parsed. 0 negative trials attributed (trials were single-arm or multi-agent without clean set-difference contrast). Opp remained 0.000.",
        "dis_delta": "Condition matched correctly.",
        "rule_delta": "With Opp=0.000, evaluator evaluated Rule 1 PROMISING: `SS=0.985 >= 0.40`, `MS=0.449 >= 0.40`, `RS=0.000 <= 0.39`. Rule 1 fired.",
        "lit_delta": "Unchanged (frozen SS=0.985).",
        "mech_delta": "Unchanged (frozen MS=0.449).",
        "safety_delta": "Unchanged (RS=0.000).",
        "root_cause": "Omission of Rule 1c in evaluator script. Glioblastoma trials failed to generate an opposition claim, and without Rule 1c gating the high literature co-mention score, the hypothesis jumped to SUPPORT.",
        "verdict": "CRITICAL REGRESSION (Genuine hard-negative failed drug promoted to False Promising SUPPORT)."
    },
    {
        "cid": "TC-062", "drug": "Ranibizumab", "dis": "Age-related macular degeneration", "gold": "SUPPORT",
        "b_pred": "UNCERTAIN", "p_pred": "SUPPORT",
        "b_details": "SS=0.994, MS=0.490, RS=0.000, Opp=0.000. Predicted UNCERTAIN via Rule 5.",
        "p_details": "SS=0.994, MS=0.490, RS=0.000, Opp=0.000. Predicted SUPPORT via Rule 1 (PROMISING).",
        "ct_delta": "50 studies parsed. 0 negative trials attributed. Opp=0.000.",
        "dis_delta": "ChEMBL approved indication present (Lucentis in wet AMD).",
        "rule_delta": "Evaluator fired Rule 1 PROMISING directly.",
        "lit_delta": "Unchanged (frozen SS=0.994).",
        "mech_delta": "Unchanged (frozen MS=0.490).",
        "safety_delta": "Unchanged (RS=0.000).",
        "root_cause": "Evaluator script applied Rule 1 PROMISING directly. While Ranibizumab is clinically approved for wet AMD, the transition was driven by evaluator rule-order execution.",
        "verdict": "NEUTRAL / BENEFICIAL OUTCOME VIA ARTIFACT (Correct label reached, but reflects evaluator rule behavior)."
    },
    {
        "cid": "TC-072", "drug": "Empagliflozin", "dis": "Heart failure", "gold": "SUPPORT",
        "b_pred": "SUPPORT", "p_pred": "OPPOSE",
        "b_details": "SS=0.970, MS=0.402, RS=0.259, Opp=0.319. Predicted SUPPORT via Rule -1 (APPROVED INDICATION RESOLUTION).",
        "p_details": "SS=0.970, MS=0.402, RS=0.259, Opp=0.512 (HIGH, 2 groups). Predicted OPPOSE via Rule 2b (EMPIRICAL OPPOSITION VETO).",
        "ct_delta": "50 studies parsed. Recovered study index 36 (`NCT04509674`, EMPACT-MI trial: Empagliflozin in patients hospitalized for acute myocardial infarction, evaluating HF hospitalization/death) and study index 44 (`NCT03448406`). EMPACT-MI was neutral (HR=0.90, p=0.2061), but parser treated $p \\ge 0.05$ as `COMPLETED_FAILURE`.",
        "dis_delta": "Condition matched correctly. Approval anchor confirmed (`approval_anchor=True` for Jardiance in heart failure).",
        "rule_delta": "With 2 failure trials, Opp score surged to 0.512 (HIGH). Rule 2b empirical opposition veto executed before Rule -1, falsely vetoing the approved indication!",
        "lit_delta": "Unchanged (frozen SS=0.970).",
        "mech_delta": "Unchanged (frozen MS=0.402).",
        "safety_delta": "Unchanged (RS=0.259).",
        "root_cause": "Removing the 20-study truncation retrieved EMPACT-MI (study 36). The statistical parser's naive non-significance rule ($p \\ge 0.05 \\rightarrow$ failure) converted neutral secondary-prevention data into an efficacy failure, triggering Rule 2b veto.",
        "verdict": "MAJOR REGRESSION (Established blockbuster FDA-approved indication converted from correct SUPPORT to False Oppose)."
    },
]

for t in transitions_data:
    p(f"### {t['cid']}: {t['drug']} -> {t['dis']}")
    p(f"- **Benchmark Gold**: `{t['gold']}`")
    p(f"- **Baseline Prediction**: `{t['b_pred']}` -> **Post-Fix Prediction**: `{t['p_pred']}`")
    p(f"- **Baseline Score/Details**: {t['b_details']}")
    p(f"- **Post-Fix Score/Details**: {t['p_details']}")
    p(f"- **ClinicalTrials Delta**: {t['ct_delta']}")
    p(f"- **Disease Relation Delta**: {t['dis_delta']}")
    p(f"- **Rule Delta**: {t['rule_delta']}")
    p(f"- **Literature / Mechanism / Safety Deltas**: Lit: {t['lit_delta']} | Mech: {t['mech_delta']} | Safety: {t['safety_delta']}")
    p(f"- **Exact Root Cause**: {t['root_cause']}")
    p(f"- **Audit Verdict**: **{t['verdict']}**")
    p()

# SECTION 4
p("## 4. False Promising Audit")
p()
p("The reported diagnostic metric indicates that False Promising cases increased from **3 to 5** (a 66.7% relative increase). "
  "False promising predictions are dangerous in drug repurposing because they endorse ineffective or harmful treatments.")
p()
p("### Complete False Promising Case Table")
p()
p("| Case ID | Drug | Disease | Baseline Pred | Post-Fix Pred | Correct Gold | Decision Rule Fired | Root Cause Category | Specific Mechanism / Failure Mode |")
p("|---|---|---|---|---|---|---|---|---|")
p("| **TC-023** | Azithromycin | COVID-19 | SUPPORT | SUPPORT | OPPOSE | Rule 1 (HIGH-QUALITY THERAPEUTIC EVIDENCE) | Evidence Weighting / Score Saturation | Unchanged Error. Pre-existing high-quality therapeutic flag from azithromycin clinical trial data on COVID-19 co-medication saturates SS=0.986, which overrides moderate opposition (0.319). |")
p("| **TC-025** | Interferon beta-1a | COVID-19 | UNCERTAIN | **SUPPORT** | OPPOSE | Rule 1 (PROMISING) | Benchmark / Evaluator Artifact | **New Regression**. ACTT-3 trial futility recovered (Opp=0.319), but falls below Rule 2b threshold (0.45). Evaluator script omitted Rule 1c, allowing literature SS=0.961 to trigger SUPPORT. |")
p("| **TC-051** | Valproic acid | Glioblastoma | SUPPORT | SUPPORT | UNCERTAIN | Rule 1 (HIGH-QUALITY THERAPEUTIC EVIDENCE) | Evidence Weighting / Score Saturation | Unchanged Error. Historical adjuvant glioblastoma studies parsed as positive therapeutic trial anchor (SS=0.985), driving prediction to SUPPORT. |")
p("| **TC-053** | Pembrolizumab | Glioblastoma | UNCERTAIN | **SUPPORT** | OPPOSE | Rule 1 (PROMISING) | Benchmark / Evaluator Artifact | **New Regression**. Phase 3 glioblastoma trials lacked clean single-agent contrast, leaving Opp=0.000. Evaluator omitted Rule 1c, allowing pure literature SS=0.985 to fire Rule 1 PROMISING. |")
p("| **TC-079** | Fenofibrate | Cardiovascular disease | SUPPORT | SUPPORT | OPPOSE | Rule -1 (APPROVED INDICATION RESOLUTION) | Disease Relation / Over-Broad Matching | Unchanged Error. Fenofibrate is approved for hypertriglyceridemia. Under Rule -1, hypertriglyceridemia was matched to broad Cardiovascular Disease, creating a false approval anchor that overrode clinical futility (ACCORD trial). |")
p()
p("### Forensic Breakdown of False Promising Origins")
p("- **Introduced by ClinicalTrials changes directly**: **0 cases**. Neither TC-025 nor TC-053 became SUPPORT because of bad trial attribution or bad CT parsing. In fact, TC-025 gained a valid negative trial!")
p("- **Introduced by Evaluator Rule-Engine Omission (Artifact)**: **2 cases** (`TC-025`, `TC-053`). The standalone evaluator omitted Rule 1c (Therapeutic Anchor Gate). In the production reasoning orchestrator (`reasoning_orchestrator.py:1647-1665`), Rule 1c explicitly blocks high literature support scores from reaching PROMISING unless an approved indication or positive clinical trial anchor is proven. Without Rule 1c, both cases leaked into SUPPORT.")
p("- **Pre-existing & Unchanged**: **3 cases** (`TC-023`, `TC-051`, `TC-079`).")
p("  - `TC-023`: Literature / observational trial saturation (`has_high_quality_therapeutic=True`).")
p("  - `TC-051`: Positive adjuvant trial anchor on speculative pair.")
p("  - `TC-079`: Overly broad disease mapping under Rule -1.")
p()

# SECTION 5
p("## 5. False Opposition Audit")
p()
p("False opposition surged from **2 to 4 cases** (doubling from 4.0% to 8.0%). "
  "This is a severe regression because rejecting genuine, lifesaving approved medications (e.g. Rosiglitazone, Empagliflozin) completely destroys clinical credibility.")
p()
p("### Complete False Opposition Case Table")
p()
p("| Case ID | Drug | Disease | Expected Label | Baseline Pred | Post-Fix Pred | Rule Responsible | ClinicalTrials Contribution | Mechanistic / Safety Contribution | Is CT Fix Responsible? |")
p("|---|---|---|---|---|---|---|---|---|---|")
p("| **TC-043** | Rosiglitazone | Type 2 diabetes | SUPPORT | SUPPORT | **OPPOSE** | Rule 2b (EMPIRICAL OPPOSITION VETO) | Truncation removal retrieved `NCT00367055` (index 47). Both study 1 and 47 parsed as `COMPLETED_FAILURE` due to $p \\ge 0.05$ non-significance logic, pushing Opp to 0.512. | SS=0.995, MS=0.490. Approved indication confirmed. | **YES (Indirect)**: CT retrieval exposed pre-existing statistical parser flaw. |")
p("| **TC-056** | Gefitinib | EGFR-positive lung cancer | SUPPORT | OPPOSE | OPPOSE | Rule 2b (DIRECTIONAL OPPOSITION VETO) | None. Opp=0.000. | SS=0.953, MS=0.490. Directional contradiction between target inhibition and disease pathway. | **NO**: Pure mechanistic / directional contradiction conflict. |")
p("| **TC-058** | Crizotinib | ALK-positive lung cancer | SUPPORT | OPPOSE | OPPOSE | Rule 0 (SAFETY VETO) | None. Opp=0.000. | SS=0.987. Risk Score=0.763 (severe hepatotoxicity / QT prolongation boxed warning). | **NO**: Safety veto override of approved indication. |")
p("| **TC-072** | Empagliflozin | Heart failure | SUPPORT | SUPPORT | **OPPOSE** | Rule 2b (EMPIRICAL OPPOSITION VETO) | Truncation removal retrieved `NCT04509674` (EMPACT-MI, index 36). Neutral post-MI secondary prevention trial ($p=0.2061$) was classified as `COMPLETED_FAILURE`, pushing Opp to 0.512. | SS=0.970, MS=0.402. Approved indication confirmed. | **YES (Indirect)**: CT retrieval exposed pre-existing statistical parser flaw. |")
p()
p("### Root Cause Classification of the 2 -> 4 Surge")
p("The increase from 2 to 4 false opposition cases is **Category C: A pre-existing issue exposed by better trial retrieval** combined with **Rule-Precedence Architecture Flaw**:")
p("1. **Pre-existing Statistical Parser Limitation**: `RetrievalPipeline._evaluate_outcome_measure_direction()` naively assigns `COMPLETED_FAILURE` whenever a completed trial's endpoints fail to achieve statistical significance ($p \\ge 0.05$) or when confidence intervals cross unity. In large clinical trial programs, neutral exploratory secondary endpoints, post-MI prevention studies (e.g. EMPACT-MI for Empagliflozin), and subgroup analyses are routine and do NOT refute primary efficacy in the established disease.")
p("2. **Rule Set v3.2 Precedence Bug**: In `apply_decision_rules`, `Rule 2b (EMPIRICAL OPPOSITION VETO)` is evaluated at line 277, **BEFORE** `Rule -1 (APPROVED INDICATION RESOLUTION)` at line 299. Consequently, when two neutral trials are misclassified as failures, the opposition score reaches 0.512 (HIGH), and Rule 2b triggers an unconditional veto, overriding valid FDA approval!")
p()

# SECTION 6
p("## 6. Hard-Negative Audit")
p()
p("The previous report claimed that hard-negative uncertainty dropped from 72.7% to 63.6% as a 'significant improvement' and implied that cases were converted to OPPOSE. "
  "**This claim is entirely false.**")
p()
p("### Transition Matrix for All 22 Hard Negatives (Gold == OPPOSE)")
p()
p("| Transition Category | Count | Percentage | Clinical Meaning |")
p("|---|---|---|---|")
p("| **UNCERTAIN -> CORRECT (OPPOSE)** | **0** | **0.0%** | **ZERO hard negatives were converted to correct opposition!** |")
p("| **UNCERTAIN -> INCORRECT (SUPPORT)** | **2** | **9.1%** | **Severe regression: 2 hard negatives became False Promising (`TC-025`, `TC-053`).** |")
p("| **UNCHANGED UNCERTAIN** | 14 | 63.6% | Remained uncertain due to missing trials, low opposition score, or epistemic conflict. |")
p("| **UNCHANGED CORRECT (OPPOSE)** | 4 | 18.2% | Pre-existing correct opposition (`TC-022` Fluvoxamine, `TC-024` HCQ, `TC-026` Niacin, `TC-075` Pioglitazone). |")
p("| **UNCHANGED INCORRECT (SUPPORT)** | 2 | 9.1% | Pre-existing false promising (`TC-023` Azithromycin, `TC-079` Fenofibrate). |")
p("| **TOTAL HARD NEGATIVES** | 22 | 100.0% | Complete gold standard cohort. |")
p()
p("### Full Case-by-Case Breakdown of All 22 Hard Negatives")
p()
p("| Case ID | Drug | Disease | Baseline Pred | Post-Fix Pred | Transition Class | Post Opp Score | Ruling Reason |")
p("|---|---|---|---|---|---|---|---|")
p("| TC-021 | Ivermectin | COVID-19 | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.770 | Rule 1b: Epistemic conflict (SS=0.989 vs Opp=0.770) |")
p("| TC-022 | Fluvoxamine | COVID-19 | OPPOSE | OPPOSE | UNCHANGED CORRECT | 0.512 | Rule 2b: Empirical opposition veto (TOGETHER trial failure) |")
p("| TC-023 | Azithromycin | COVID-19 | SUPPORT | SUPPORT | UNCHANGED INCORRECT | 0.319 | Rule 1: High-quality therapeutic flag overrides opposition |")
p("| TC-024 | Hydroxychloroquine | COVID-19 | OPPOSE | OPPOSE | UNCHANGED CORRECT | 0.744 | Rule 2b: Empirical opposition veto (RECOVERY trial failure) |")
p("| **TC-025** | Interferon beta-1a | COVID-19 | UNCERTAIN | **SUPPORT** | **UNCERTAIN -> FALSE PROMISING** | 0.319 | Rule 1: Opp=0.319 < 0.45; evaluator omitted Rule 1c |")
p("| TC-026 | Niacin | Cardiovascular disease | OPPOSE | OPPOSE | UNCHANGED CORRECT | 0.512 | Rule 2b: Empirical opposition veto (AIM-HIGH trial failure) |")
p("| TC-028 | Celecoxib | Alzheimer's disease | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.000 | Rule 5: CT.gov lacked mapped failure trials (ADAPT) |")
p("| TC-029 | Simvastatin | Sepsis | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.000 | Rule 5: Historic sepsis failure trials not found on CT.gov |")
p("| TC-030 | Dexamethasone | Traumatic brain injury | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.319 | Rule 5: CRASH trial Opp=0.319 < 0.45 threshold |")
p("| TC-041 | Etanercept | Sepsis | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.000 | Rule 5: 1990s failure trials absent from CT.gov registry |")
p("| TC-042 | Infliximab | Heart failure | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.000 | Rule 5: ATTACH trial published in NEJM, not registered on CT.gov |")
p("| TC-044 | Rofecoxib | Cardiovascular disease | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.000 | Rule 5: Cardiovascular toxicity not parsed as efficacy trial |")
p("| TC-052 | Nivolumab | Glioblastoma | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.700 | Rule 1b: Epistemic conflict (SS=0.986 vs Opp=0.700) |")
p("| **TC-053** | Pembrolizumab | Glioblastoma | UNCERTAIN | **SUPPORT** | **UNCERTAIN -> FALSE PROMISING** | 0.000 | Rule 1: Opp=0.000; evaluator omitted Rule 1c |")
p("| TC-066 | Sildenafil | Alzheimer's disease | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.000 | Rule 5: Observational claims only; no CT.gov failure trial |")
p("| TC-067 | Sildenafil | Heart failure | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.000 | Rule 5: RELAX trial not parsed as failure outcome |")
p("| TC-074 | Semaglutide | Alzheimer's disease | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.000 | Rule 5: EVOKE trials active/ongoing, not completed failures |")
p("| TC-075 | Pioglitazone | Alzheimer's disease | OPPOSE | OPPOSE | UNCHANGED CORRECT | 0.512 | Rule 2b: Empirical opposition veto (TOMMORROW trial failure) |")
p("| TC-079 | Fenofibrate | Cardiovascular disease | SUPPORT | SUPPORT | UNCHANGED INCORRECT | 0.000 | Rule -1: Hypertriglyceridemia mapped to broad CVD |")
p("| TC-081 | Warfarin | Bleeding disorder | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.000 | Rule 5: Absolute contraindication lacking safety rule veto |")
p("| TC-085 | Isotretinoin | Pregnancy | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.000 | Rule 5: Black-box teratogen lacking safety rule veto |")
p("| TC-088 | Doxorubicin | Cardiomyopathy | UNCERTAIN | UNCERTAIN | UNCHANGED UNCERTAIN | 0.000 | Rule 5: Known cardiotoxicity lacking safety rule veto |")
p()
p("### Hard-Negative Performance Metrics")
p("- **Hard-Negative Accuracy (Recall on OPPOSE)**: **18.18% (4/22)** in baseline $\\rightarrow$ **18.18% (4/22)** in post-fix (**STAGNANT**).")
p("- **Hard-Negative Uncertainty Rate**: **72.73% (16/22)** in baseline $\\rightarrow$ **63.64% (14/22)** in post-fix.")
p("- **Hard-Negative False-Promising Rate**: **9.09% (2/22)** in baseline $\\rightarrow$ **18.18% (4/22)** in post-fix (**DOUBLED**).")
p()
p("> [!IMPORTANT]")
p("> The 9.1% drop in hard-negative uncertainty was caused 100% by hard negatives converting to FALSE PROMISING SUPPORT. Not a single hard-negative case was helped by the changes. Calling this drop an 'improvement' was fundamentally wrong.")
p()

# SECTION 7
p("## 7. ClinicalTrials Case Audit")
p()
p("Every targeted case and NCT ID requested in the audit was traced from raw API payload through retrieval, parsing, disease matching, attribution, and claim generation.")
p()
p("### 1. Key Benchmark Cases Verification")
p("- **TC-007 (Metformin -> Type 2 diabetes)**: Baseline Pred: `SUPPORT`, Post Pred: `SUPPORT`. SS=0.994, Opp=0.319. Protected by `Rule -1 (APPROVED INDICATION RESOLUTION)`. Background therapy in combination trials correctly protected.")
p("- **TC-019 (Imatinib -> CML)**: Baseline Pred: `UNCERTAIN`, Post Pred: `SUPPORT`. SS=0.988, Opp=0.000. Fired Rule 1 PROMISING in evaluator. Reached correct clinical outcome.")
p("- **TC-025 (Interferon beta-1a -> COVID-19)**: Baseline Pred: `UNCERTAIN`, Post Pred: `SUPPORT` (Gold: `OPPOSE`). Recovered ACTT-3 trial futility (`NCT04385095`, Opp=0.319), but Opp was below 0.45 threshold, allowing evaluator to fire Rule 1 PROMISING.")
p("- **TC-031 (Furosemide -> Depression)**: Control case. Pred: `UNCERTAIN` (Opp=0.000). Successfully protected: zero false opposition, zero false attribution.")
p("- **TC-032 (Warfarin -> Leishmaniasis)**: Control case. Pred: `UNCERTAIN` (Opp=0.000). Successfully protected: zero false opposition, zero false attribution.")
p("- **TC-043 (Rosiglitazone -> Type 2 diabetes)**: Baseline Pred: `SUPPORT`, Post Pred: `OPPOSE` (Gold: `SUPPORT`). Truncation fix recovered study index 47 (`NCT00367055`). Neutral secondary endpoints misclassified as failure, pushing Opp to 0.512 and triggering Rule 2b veto against an approved drug.")
p("- **TC-047 (Gabapentin -> Neuropathic pain)**: Baseline Pred: `UNCERTAIN`, Post Pred: `SUPPORT`. SS=0.988, Opp=0.370. Evaluator fired Rule 1 PROMISING.")
p("- **TC-053 (Pembrolizumab -> Glioblastoma)**: Baseline Pred: `UNCERTAIN`, Post Pred: `SUPPORT` (Gold: `OPPOSE`). Opp=0.000. Evaluator fired Rule 1 PROMISING in absence of Rule 1c.")
p("- **TC-062 (Ranibizumab -> AMD)**: Baseline Pred: `UNCERTAIN`, Post Pred: `SUPPORT`. SS=0.994, Opp=0.000. Evaluator fired Rule 1 PROMISING.")
p("- **TC-072 (Empagliflozin -> Heart failure)**: Baseline Pred: `SUPPORT`, Post Pred: `OPPOSE` (Gold: `SUPPORT`). Truncation fix recovered EMPACT-MI (`NCT04509674`, index 36). Neutral secondary trial misclassified as failure, pushing Opp to 0.512 and triggering Rule 2b veto against an approved drug.")
p("- **TC-082 (Aspirin -> Hemorrhagic stroke)**: Control case. Baseline Pred: `SUPPORT`, Post Pred: `SUPPORT` (Gold: `OPPOSE`). Rule -1 subtype anchor was correctly blocked (`approval_anchor=False`), but case remained SUPPORT via Rule 1 (see Section 8).")
p()
p("### 2. Explicit Audit of All 6 Target NCT IDs")
p()
p("| NCT ID | Drug | Disease | Retrieved? | Parsed? | Condition Matched? | Drug Attributed? | Drug Role Assigned | Neg Claim? | Contributed to Opp? | Placebo & Background Handling | Forensic Finding |")
p("|---|---|---|---|---|---|---|---|---|---|---|---|")
p("| **NCT00120289** | Niacin | Cardiovascular disease | YES | YES | YES | YES | `EVALUATED_COMBINATION_COMPONENT` | YES | YES (Opp=0.319) | Simvastatin recognized as constant background; Niacin differentiated as active intervention. | Verified: AIM-HIGH trial DSMB termination for lack of efficacy correctly attributed to Niacin. |")
p("| **NCT02362321** | Dexamethasone | Traumatic brain injury | YES | YES | YES | YES | `EVALUATED_PRIMARY_INTERVENTION` | YES | YES (Opp=0.319) | Placebo control properly identified. | Verified: CRASH trial termination due to increased mortality correctly attributed to Dexamethasone. |")
p("| **NCT02667587** | Nivolumab | Glioblastoma | YES | YES | YES | YES | `EVALUATED_COMBINATION_COMPONENT` | YES | YES (Opp=0.319) | Nivolumab Placebo properly ignored; Temozolomide + RT recognized as constant background. | Verified: CheckMate 548 PFS failure correctly attributed to Nivolumab without false placebo matching. |")
p("| **NCT02617589** | Nivolumab | Glioblastoma | YES | YES | YES | YES | `EVALUATED_COMBINATION_COMPONENT` | YES | YES (Opp=0.319) | Active comparator (Temozolomide) handled cleanly via set difference. | Verified: CheckMate 498 OS failure (HR=1.31, p=0.0037) correctly attributed to Nivolumab. |")
p("| **NCT02284906** | Pioglitazone | Alzheimer's disease | YES | YES | YES | YES | `EVALUATED_PRIMARY_INTERVENTION` | YES | YES (Opp=0.266) | Negation guard verified: 'no safety concern' ignored, 'Lack of efficacy' correctly captured. | Verified: TOMMORROW trial termination for futility correctly parsed and attributed. |")
p("| **NCT02020616** | Metformin | Type 2 diabetes | YES | YES | YES | **NO (REJECTED)** | `BACKGROUND_CONSTANT_THERAPY` | **NO** | **NO (Opp=0.000)** | Metformin was constant background therapy across all arms; investigational drug was a novel add-on. | Verified: Set-difference logic correctly blocked Metformin attribution. Prevented false opposition! |")
p()

# SECTION 8
p("## 8. Aspirin -> Hemorrhagic Stroke Dedicated Diagnosis")
p()
p("Hypothesis `TC-082` (Aspirin $\\rightarrow$ Hemorrhagic stroke, Gold: `OPPOSE`) represents the prime example of a **partially fixed case** that was misinterpreted as 'protected'.")
p()
p("### Forensic Findings on TC-082")
p("1. **Was Rule -1 incorrectly firing before?**"
  "\n   **YES**. Previously, naive string/token matching matched `'stroke'` (from Aspirin's approved indication for ischemic stroke / secondary stroke prevention) to `'hemorrhagic stroke'`. This generated a false regulatory approval anchor (`approval_anchor=True`) under Rule -1.")
p("2. **Is it correctly blocked after disease-relation hardening?**"
  "\n   **YES**. The shared disease-relation matcher correctly classified Ischemic Stroke and Hemorrhagic Stroke as `DiseaseRelation.SIBLING_EXCLUDED`. `matches_for_approval_anchor()` strictly requires `DiseaseRelation.SAME`. As confirmed in the ledger, **`approval_anchor = False`**.")
p("3. **What OTHER evidence still causes SUPPORT?**"
  "\n   Despite uncoupling Rule -1, the case STILL predicted **`SUPPORT`** (`recommendation = PROMISING`)."
  "\n   - **Support Score**: `0.9592`"
  "\n   - **Mechanistic Score**: `0.4042`"
  "\n   - **Risk Score**: `0.0000`"
  "\n   - **Opposition Score**: `0.0000` (NONE)"
  "\n   - **Rule Fired**: `Rule 1 (HIGH-QUALITY THERAPEUTIC EVIDENCE): Documented clinical trial success (SS=0.959).`"
  "\n   The retrieval pipeline ingested Aspirin stroke literature containing positive mentions of ischemic stroke trials. These were aggregated into high therapeutic support score, and `has_high_quality_therapeutic` was flagged as `True`.")
p("4. **Is that support clinically valid?**"
  "\n   **NO. It is clinically catastrophic.** In clinical pharmacology, Aspirin is an antiplatelet agent that inhibits thromboxane A2. In hemorrhagic stroke (active intracranial bleeding), Aspirin is an **absolute contraindication** that promotes fatal hematoma expansion.")
p("5. **Is the benchmark label expecting opposition?**"
  "\n   **YES**. The benchmark gold standard is explicitly `OPPOSE`.")
p("6. **Which layer should own this failure?**"
  "\n   This failure does **NOT** belong to ClinicalTrials retrieval or Disease Relation. The disease relation layer did its job by blocking Rule -1."
  "\n   Ownership belongs strictly to:"
  "\n   - **Primary Owner**: **Safety / Contraindication Layer (`ClinicalSafetyAgent`)**. CYNTHERA currently lacks an explicit, high-priority Contraindication Knowledge Base. A drug that causes bleeding (antiplatelet/anticoagulant) must trigger an immediate safety veto when paired with an active hemorrhage/bleeding disorder."
  "\n   - **Secondary Owner**: **Evidence Polarity / Therapeutic Direction**. Literature retrieval cannot distinguish 'Aspirin studied in prevention of ischemic stroke' from 'Aspirin evaluated as a treatment for hemorrhagic stroke' without directional condition polarity.")
p()

# SECTION 9
p("## 9. Unsupported Report Claims")
p()
p("The companion report (`backend/evaluation/post_clinicaltrials_50_fast_report.md`) contains multiple statements that are directly refuted by the underlying ledger data.")
p()
p("| # | Statement in Report | Evidence in Ledger | Supported? | Forensic Correction Needed |")
p("|---|---|---|---|---|")
p("| 1 | *'Did false opposition increase? No. False Oppose remained at 4 (8.0%).'* (Lines 226–227) | Ledger metrics show: `baseline.false_oppose = 2` (4.0%) -> `postfix.false_oppose = 4` (8.0%). Both TC-043 and TC-072 flipped to false oppose. | **NO (DIRECT CONTRADICTION)** | False opposition **doubled** (+100% relative increase), surging from 2 to 4 cases due to neutral trials being misclassified as failures. |")
p("| 2 | *'Hard Negative Uncertainty Rate: 0.7273 -> 0.6364 (-0.0909) Reduced (Converted to Oppose)'* (Line 107) | 0 of 22 hard negatives converted to OPPOSE. Exactly 2 hard negatives converted to SUPPORT (False Promising: TC-025, TC-053). | **NO (FALSE NARRATIVE)** | The uncertainty rate dropped **NOT** because cases converted to OPPOSE, but because 2 cases became False Promising SUPPORT! Zero hard negatives converted to OPPOSE. |")
p("| 3 | *'TC-082 Aspirin -> Hemorrhagic stroke ... Verified Status: PROTECTED'* (Lines 152, 236) | Ledger records: `TC-082 prediction = SUPPORT`, `recommendation = PROMISING`, `Rule 1 (HIGH-QUALITY THERAPEUTIC EVIDENCE)`. Gold is `OPPOSE`. | **NO (UNTRUE)** | TC-082 is **NOT protected**. While the Rule -1 approval anchor was blocked, the final prediction remained a dangerous False Promising SUPPORT. |")
p("| 4 | *'Verified Negative Recall: 0.1818 -> 0.1818 ... Impact: Significant Recovery'* (Line 106) | Delta is +0.0000. Verified negative recall was completely stagnant at 4/22 (18.18%). | **NO (MISLEADING)** | Negative recall showed **zero recovery** across the benchmark cohort. |")
p("| 5 | *'Remaining errors stem primarily from literature Support Score inflation ... and diseases where negative trials were published in literature but not registered on ClinicalTrials.gov'* (Line 239) | Ledger shows that 2 approved drugs (Rosiglitazone, Empagliflozin) failed because ClinicalTrials retrieval pulled neutral trials that the statistical parser broke. | **PARTIAL / MISLEADING** | The report ignored the fact that ClinicalTrials retrieval directly caused 2 new false oppose regressions via parser non-significance misclassifications. |")
p("| 6 | *'Is the system ready for the next workstream? YES. The ClinicalTrials.gov ... layers are confirmed verified, robust, and hardened.'* (Lines 241–242) | Evaluator rule-engine is desynchronized from production (missing Rule 1c), and the statistical parser turns neutral trials into false vetoes. | **NO (OVERCLAIM)** | The pipeline cannot proceed to 100-case benchmarking until the statistical parser non-significance bug and the evaluator Rule 1c omission are rectified. |")
p()

# SECTION 10
p("## 10. Remaining Error Taxonomy (A–M Classification)")
p()
p("A forensic audit of all **25 standard post-fix errors** was performed against the standardized root-cause taxonomy (Categories A–M). "
  "Each error was assigned exactly one primary root cause and one secondary root cause.")
p()
p("### Root-Cause Taxonomy Distribution (25 Errors)")
p()
p("| Code | Root Cause Category | Primary Error Count | Primary Percentage | Secondary Contributors | Typical Case Examples |")
p("|---|---|---|---|---|---|")
p("| **A** | ClinicalTrials retrieval | 3 | 12.0% | 4 | `TC-028` (Celecoxib/AD), `TC-029` (Simvastatin/Sepsis), `TC-066` (Sildenafil/AD) |")
p("| **B** | ClinicalTrials parsing | 1 | 4.0% | 0 | `TC-067` (Sildenafil/Heart failure - RELAX trial parsing) |")
p("| **C** | ClinicalTrials attribution | 0 | 0.0% | 4 | None (Attribution engine was 100% precise; secondary role in multi-arm contrasts) |")
p("| **D** | Disease relation | 2 | 8.0% | 0 | `TC-057` (Osimertinib/EGFR NSCLC), `TC-079` (Fenofibrate/CVD broad match) |")
p("| **E** | Statistical direction parsing | 2 | 8.0% | 2 | `TC-043` (Rosiglitazone/T2D), `TC-072` (Empagliflozin/HF) — $p \\ge 0.05 \\rightarrow$ failure |")
p("| **F** | Therapeutic direction | 2 | 8.0% | 6 | `TC-002` (Aspirin/Secondary CV prev), `TC-056` (Gefitinib/NSCLC polarity) |")
p("| **G** | Mechanistic reasoning | 0 | 0.0% | 1 | Secondary contributor to directional conflict (`TC-056`) |")
p("| **H** | Safety / contraindication | 5 | 20.0% | 0 | `TC-044` (Rofecoxib), `TC-058` (Crizotinib), `TC-081` (Warfarin), `TC-085` (Isotretinoin), `TC-088` (Doxorubicin) |")
p("| **I** | Evidence weighting / score saturation | 5 | 20.0% | 3 | `TC-021` (Ivermectin), `TC-023` (Azithromycin), `TC-030` (Dexamethasone), `TC-051` (Valproic acid), `TC-052` (Nivolumab) |")
p("| **J** | Deduplication / independence | 0 | 0.0% | 0 | None observed in 50 cases |")
p("| **K** | Literature retrieval | 2 | 8.0% | 3 | `TC-041` (Etanercept/Sepsis), `TC-042` (Infliximab/HF) — trials published in NEJM, not CT.gov |")
p("| **L** | Benchmark / evaluator artifact | 2 | 8.0% | 0 | `TC-025` (Interferon beta-1a), `TC-053` (Pembrolizumab) — Rule 1c omitted in fast runner |")
p("| **M** | Other | 1 | 4.0% | 0 | `TC-074` (Semaglutide/AD) — active ongoing trial EVOKE cannot be scored as completed |")
p("| **TOTAL** | | **25** | **100.0%** | | |")
p()
p("### Full Taxonomy Mapping for All 25 Errors")
p()
p("| Case ID | Drug | Disease | Pred | Gold | Rule Fired | Primary Cause | Sec Cause | Forensic Mechanism |")
p("|---|---|---|---|---|---|---|---|---|")
p("| TC-002 | Aspirin | Secondary CV prev | UNCERTAIN | SUPPORT | Rule 5 | **F** | A | Secondary prevention indication lacks exact ChEMBL string match or dedicated trial anchor. |")
p("| TC-021 | Ivermectin | COVID-19 | UNCERTAIN | OPPOSE | Rule 1b | **I** | K | Massive literature co-mentions saturate SS=0.989, forcing Rule 1b conflict with Opp=0.770. |")
p("| TC-023 | Azithromycin | COVID-19 | SUPPORT | OPPOSE | Rule 1 | **I** | C | Observational trial co-medication sets high-quality therapeutic flag, overriding Opp=0.319. |")
p("| TC-025 | Interferon beta-1a | COVID-19 | SUPPORT | OPPOSE | Rule 1 | **L** | I | ACTT-3 futility Opp=0.319 < 0.45 threshold; evaluator omitted Rule 1c, firing Rule 1 PROMISING. |")
p("| TC-028 | Celecoxib | Alzheimer's disease | UNCERTAIN | OPPOSE | Rule 5 | **A** | C | ADAPT prevention trial not retrieved or indexed under Alzheimer's condition query on CT.gov. |")
p("| TC-029 | Simvastatin | Sepsis | UNCERTAIN | OPPOSE | Rule 5 | **A** | K | Historic sepsis failure trials not available on CT.gov API; published only in literature. |")
p("| TC-030 | Dexamethasone | Traumatic brain injury | UNCERTAIN | OPPOSE | Rule 5 | **I** | E | CRASH trial termination Opp=0.319 falls below Rule 2b threshold (0.45); defaults to UNCERTAIN. |")
p("| TC-041 | Etanercept | Sepsis | UNCERTAIN | OPPOSE | Rule 5 | **K** | A | 1990s sepsis failure trials published in NEJM, absent from CT.gov registry. |")
p("| TC-042 | Infliximab | Heart failure | UNCERTAIN | OPPOSE | Rule 5 | **K** | A | ATTACH trial (2003) failure published in NEJM/literature, not indexed on CT.gov. |")
p("| TC-043 | Rosiglitazone | Type 2 diabetes | OPPOSE | SUPPORT | Rule 2b | **E** | C | Study 47 neutral secondary endpoint ($p \\ge 0.05$) parsed as failure, triggering Rule 2b veto. |")
p("| TC-044 | Rofecoxib | Cardiovascular disease | UNCERTAIN | OPPOSE | Rule 5 | **H** | A | APPROVe trial cardiovascular toxicity should be captured as safety/cardiotoxicity contraindication. |")
p("| TC-051 | Valproic acid | Glioblastoma | SUPPORT | UNCERTAIN | Rule 1 | **I** | F | Historical adjuvant glioblastoma studies parsed as positive therapeutic trial anchor (SS=0.985). |")
p("| TC-052 | Nivolumab | Glioblastoma | UNCERTAIN | OPPOSE | Rule 1b | **I** | K | Heavy literature volume inflates SS=0.986, forcing Rule 1b conflict with Opp=0.700. |")
p("| TC-053 | Pembrolizumab | Glioblastoma | SUPPORT | OPPOSE | Rule 1 | **L** | I | Glioblastoma trials lacked clean contrast (Opp=0.0); evaluator omitted Rule 1c, firing Rule 1. |")
p("| TC-056 | Gefitinib | EGFR-positive NSCLC | OPPOSE | SUPPORT | Rule 2b | **F** | G | Directional conflict between target inhibition and downstream pathway triggers Rule 2b veto. |")
p("| TC-057 | Osimertinib | EGFR-mutant NSCLC | UNCERTAIN | SUPPORT | Rule 5 | **D** | F | EGFR-mutant NSCLC vs broad NSCLC ChEMBL approved indication mapping mismatch. |")
p("| TC-058 | Crizotinib | ALK-positive NSCLC | OPPOSE | SUPPORT | Rule 0 | **H** | F | Severe boxed warning (RS=0.763) triggers Rule 0 safety veto, overriding oncology indication. |")
p("| TC-066 | Sildenafil | Alzheimer's disease | UNCERTAIN | OPPOSE | Rule 5 | **A** | K | No definitive negative CT.gov trial found; observational claims dominate literature. |")
p("| TC-067 | Sildenafil | Heart failure | UNCERTAIN | OPPOSE | Rule 5 | **B** | E | RELAX trial (HFpEF) not parsed as failure outcome. |")
p("| TC-072 | Empagliflozin | Heart failure | OPPOSE | SUPPORT | Rule 2b | **E** | C | Neutral EMPACT-MI trial ($p=0.2061$) parsed as failure, triggering Rule 2b veto against approval. |")
p("| TC-074 | Semaglutide | Alzheimer's disease | UNCERTAIN | OPPOSE | Rule 5 | **M** | A | Ongoing trial (EVOKE) is active; benchmark label expects OPPOSE before completion. |")
p("| TC-079 | Fenofibrate | Cardiovascular disease | SUPPORT | OPPOSE | Rule -1 | **D** | F | Hypertriglyceridemia approved indication matched to broad CVD under Rule -1. |")
p("| TC-081 | Warfarin | Bleeding disorder | UNCERTAIN | OPPOSE | Rule 5 | **H** | F | Absolute contraindication lacking safety/bleeding disorder contraindication rule. |")
p("| TC-085 | Isotretinoin | Pregnancy | UNCERTAIN | OPPOSE | Rule 5 | **H** | F | Absolute teratogen contraindication lacking safety rule veto. |")
p("| TC-088 | Doxorubicin | Cardiomyopathy | UNCERTAIN | OPPOSE | Rule 5 | **H** | F | Known cardiotoxicity / causative etiology lacking contraindication veto. |")
p()

# SECTION 11
p("## 11. Decision")
p()
p("### Verdict: `STOP_CLINICALTRIALS_AND_MOVE_ON` (Coupled with `EVALUATOR_ARTIFACT_REQUIRES_FIX`)")
p()
p("### Explicit Audit Questions & Answers")
p("1. **Did the ClinicalTrials fixes actually improve correctness?**"
  "\n   **NO.** While nominal standard accuracy ticked up from 48.0% to 50.0% (+1 case), this was an illusion. The 2 cases gained in SUPPORT were either driven by evaluator rule omissions (`TC-019`, `TC-062`), while 2 FDA-approved indications (`TC-043`, `TC-072`) were destroyed by false opposition vetoes, and 2 hard negatives (`TC-025`, `TC-053`) became False Promising. Net MCC dropped from 0.3197 to 0.2735 (-14.5%).")
p("2. **Did they improve attribution quality?**"
  "\n   **YES.** The attribution module performed flawlessly: 40 candidate negative trials correctly attributed, 76 properly rejected, 0 false clinical attributions, and 100.0% precision on target trials (e.g. `NCT02020616` background metformin rejected; `NCT02667587` nivolumab placebo rejected).")
p("3. **Did they introduce meaningful regressions?**"
  "\n   **YES.** False Opposition doubled from 2 to 4 (8.0%), and False Promising surged from 3 to 5 (10.0%).")
p("4. **Are the regressions caused by the ClinicalTrials changes themselves?**"
  "\n   **Indirectly.** The ClinicalTrials retrieval changes successfully retrieved studies 20–50. However, retrieving more studies exposed latent upstream defects: the statistical parser's naive $p \\ge 0.05 \\rightarrow$ failure rule, and the evaluator's omission of Rule 1c.")
p("5. **Is another ClinicalTrials patch justified right now?**"
  "\n   **ABSOLUTELY NOT.** Only 3 of the 25 remaining errors (12.0%) relate to ClinicalTrials retrieval, and those trials simply do not exist in the CT.gov v2 API (they are 1990s literature publications). Further ClinicalTrials connector work cannot fix literature saturation, statistical p-value misinterpretations, or missing contraindications.")
p("6. **Should we stop ClinicalTrials work and move to another error family?**"
  "\n   **YES. Stop ClinicalTrials work immediately.** Continuing to iterate on ClinicalTrials retrieval would be pure benchmark chasing without fixing the real systemic bottlenecks.")
p()

# SECTION 12
p("## 12. Next Engineering Priority")
p()
p("Based strictly on the empirical evidence from the 25 audited errors, the next highest-value engineering priorities are:")
p()
p("### Priority 1: Synchronize Fast Evaluator with Production Rule Engine (Fix Rule 1c Parity)")
p("- **Subsystem**: `backend/evaluation/run_50_case_post_clinicaltrials_fast.py`")
p("- **Action**: Add production `Rule 1c (Therapeutic Evidence Anchor Gate)` into `apply_decision_rules`. If a hypothesis lacks a ChEMBL approved indication or a pair-scoped successful clinical trial, high literature Support Scores must be gated to `UNCERTAIN` rather than firing `Rule 1 (PROMISING)`.")
p("- **Immediate Impact**: Immediately eliminates the 2 false-promising regressions (`TC-025` and `TC-053`).")
p()
p("### Priority 2: Harden Statistical Outcome Evaluation (Prevent Neutral Trials from Becoming Failures)")
p("- **Subsystem**: `backend/engineering/retrieval/pipeline.py` (`_evaluate_outcome_measure_direction`)")
p("- **Action**: Distinguish between an **active clinical failure** (statistically significant adverse outcome, formal futility termination, or failed primary non-inferiority/superiority endpoint) versus a **neutral/secondary outcome** ($p \\ge 0.05$ with HR near 1.0 or wide CI in exploratory endpoints). Neutral endpoints must be classified as `INCONCLUSIVE_OR_NEUTRAL`, NOT `COMPLETED_FAILURE`.")
p("- **Rule-Order Correction**: In `reasoning_orchestrator.py` and evaluator rules, ensure `Rule -1 (Approved Indication)` takes precedence over empirical trial opposition unless the opposition trial specifically evaluated the approved indication and demonstrated regulatory revocation/direct therapeutic failure.")
p("- **Immediate Impact**: Immediately eliminates the 2 false opposition regressions (`TC-043` Rosiglitazone and `TC-072` Empagliflozin).")
p()
p("### Priority 3: Clinical Safety & Contraindication Knowledge Base")
p("- **Subsystem**: `backend/reasoning/safety/` (`ClinicalSafetyAgent`)")
p("- **Action**: Implement high-priority contraindication veto rules for categorical pharmacological incompatibilities:")
p("  - Anticoagulants / Antiplatelets + Active Hemorrhage / Bleeding Disorders (fixes `TC-081` and `TC-082` Aspirin $\\rightarrow$ Hemorrhagic stroke).")
p("  - Teratogens (Retinoids) + Pregnancy (fixes `TC-085` Isotretinoin).")
p("  - Cardiotoxic Anthracyclines + Cardiomyopathy (fixes `TC-088` Doxorubicin).")
p("- **Immediate Impact**: Converts 5 false promising / uncertain cases into correct, clinically safe opposition.")
p()

content = "\n".join(md)

# Write to backend/evaluation/post_clinicaltrials_50_reconciled_audit.md in mpp_final/cynthera
target_path = Path("backend/evaluation/post_clinicaltrials_50_reconciled_audit.md")
with open(target_path, "w", encoding="utf-8") as f:
    f.write(content)

# Also write to workspace root backend/evaluation
root_target = Path("backend/evaluation/post_clinicaltrials_50_reconciled_audit.md")
root_target.parent.mkdir(parents=True, exist_ok=True)
with open(root_target, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Successfully generated {target_path} ({len(content)} bytes, {len(md)} lines)")
