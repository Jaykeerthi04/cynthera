"""Benchmark dataset collection for Phase 4E evaluation.

Dataset Construction Principles
--------------------------------
1. POSITIVE cases: Approved repurposing indications with documented molecular mechanism
   mapped to canonical targets with Open Targets / DATTs directional annotations.
2. NEGATIVE / CONTRADICTION cases: Pharmacological counterfactuals where the drug's action
   on the target is directionally OPPOSITE to what disease-direction evidence requires.
   A genuine negative is not simply "no evidence" — it is evidence that the direction is wrong.
3. UNCERTAIN cases: Cases with genuine directional ambiguity — where either the drug action
   or the target-disease direction is uncharacterized, or conflicting signals exist.

Label Provenance
----------------
Every case carries:
  label_source: Primary authority for the expected class assignment.
  label_reference: Specific citation, ID, or URL.
  label_rationale: Scientific explanation of the directional reasoning.

Quality Flags
-------------
  unsuitable_for_directional_negative: If True, this case cannot produce OPPOSES from
    the live pipeline because directional annotations for the target-disease pair are
    absent in configured data sources (Open Targets DoE / DATTs) or uncharacterized in ChEMBL.
    The case is kept for documentation completeness but excluded from directional specificity metrics.

Dataset Splits
--------------
  split = TEST  : Cases used for final evaluation (do not tune weights against TEST).
  split = DEV   : Cases intended for development-time inspection of system behavior.
"""
from __future__ import annotations

from backend.evaluation.benchmark_models import BenchmarkCase, BenchmarkClass, BenchmarkSplit


# ══════════════════════════════════════════════════════════════════════════════
# BENCHMARK_DATASET_V1  —  Full dataset (all splits combined)
# ══════════════════════════════════════════════════════════════════════════════
BENCHMARK_DATASET_V1: list[BenchmarkCase] = [

    # ── Canonical Positives (ground-truth POSITIVE) ───────────────────────────

    BenchmarkCase(
        case_id="BENCH-POS-01",
        drug="Furosemide",
        disease="Edema",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="SLC12A1",
        rationale="Loop diuretic inhibiting NKCC2 (SLC12A1) to reduce volume overload in edema.",
        evidence_reference="FDA Approved Indication; Open Targets LoF-protect; DATTs Curated Inhibition",
        source="ChEMBL / Open Targets / DATTs",
        notes="Primary benchmark positive control.",
        label_source="FDA Approved Drug Label",
        label_reference="FDA NDA 016273",
        label_rationale=(
            "Furosemide is an FDA-approved loop diuretic. Its mechanism of action is inhibition of "
            "NKCC2 (SLC12A1), which reduces renal sodium reabsorption and fluid retention. "
            "Open Targets records LoF-protect direction for SLC12A1 in edematous conditions, "
            "confirming that inhibiting this transporter is the desired therapeutic direction."
        ),
        split=BenchmarkSplit.TEST,
    ),

    BenchmarkCase(
        case_id="BENCH-POS-02",
        drug="Propranolol",
        disease="Infantile Hemangioma",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="ADRB1",
        rationale=(
            "Non-selective beta-blocker inhibiting ADRB1/ADRB2 causing vasoconstriction "
            "and apoptosis in proliferating hemangiomas."
        ),
        evidence_reference="FDA/EMA Approved Repurposing Indication; DrugMechDB DB00571",
        source="ChEMBL / DrugMechDB / Open Targets",
        notes="Established pediatric drug repurposing breakthrough.",
        label_source="FDA Approval (Hemangeol)",
        label_reference="FDA NDA 205410",
        label_rationale=(
            "Propranolol received FDA approval for infantile hemangioma in 2014. "
            "Its therapeutic effect requires beta-antagonism (INHIBITION) of ADRB1/ADRB2, "
            "which reduces cAMP-driven vasodilation and induces apoptosis in proliferating "
            "endothelial cells. DrugMechDB records the full curated mechanistic path."
        ),
        split=BenchmarkSplit.TEST,
    ),

    BenchmarkCase(
        case_id="BENCH-POS-03",
        drug="Dapagliflozin",
        disease="Heart Failure",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="SLC5A2",
        rationale="SGLT2 inhibitor (SLC5A2) reducing cardiovascular death and hospitalizations in HFrEF/HFpEF.",
        evidence_reference="DAPA-HF Clinical Trial (NEJM 2019); Open Targets Clinical Precedence",
        source="ChEMBL / Open Targets / DATTs",
        notes="Landmark metabolic to cardiovascular repurposing indication.",
        label_source="Pivotal Clinical Trial",
        label_reference="PMID:31535829",
        label_rationale=(
            "The DAPA-HF trial (McMurray et al., NEJM 2019) demonstrated that dapagliflozin, "
            "an SGLT2 (SLC5A2) inhibitor, significantly reduced the composite of worsening "
            "heart failure or cardiovascular death in patients with HFrEF. "
            "Subsequent EMPEROR-Reduced and EMPEROR-Preserved trials extended this to HFpEF. "
            "FDA approved the HF indication in 2020."
        ),
        split=BenchmarkSplit.TEST,
    ),

    BenchmarkCase(
        case_id="BENCH-POS-04",
        drug="Thalidomide",
        disease="Multiple Myeloma",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="CRBN",
        rationale=(
            "Immunomodulatory drug binding cereblon (CRBN) to recruit and degrade "
            "transcription factors IKZF1/3 in myeloma."
        ),
        evidence_reference="FDA Approved; DATTs CRBN targeting; DrugMechDB DB01041",
        source="ChEMBL / DATTs / Open Targets / DrugMechDB",
        notes="Classic phenotypic to targeted molecular mechanism repurposing case.",
        label_source="FDA Approval + DrugMechDB Curated Path",
        label_reference="FDA NDA 021430; DrugMechDB DB01041",
        label_rationale=(
            "Thalidomide received FDA approval for multiple myeloma in 2006. "
            "Its primary mechanism involves binding cereblon (CRBN), the substrate receptor "
            "of a CRL4 ubiquitin ligase complex, redirecting it to degrade IKZF1 and IKZF3 "
            "transcription factors critical for myeloma cell survival. "
            "DrugMechDB records the full curated mechanistic path."
        ),
        split=BenchmarkSplit.TEST,
    ),

    BenchmarkCase(
        case_id="BENCH-POS-05",
        drug="Aspirin",
        disease="Colorectal Cancer",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="PTGS2",
        rationale="COX-2 (PTGS2) inhibitor reducing prostaglandin synthesis, inflammation, and adenoma recurrence in CRC.",
        evidence_reference="USPSTF Chemoprevention Guideline; Open Targets Clinical Precedence",
        source="ChEMBL / Open Targets",
        notes="Chemoprevention repurposing paradigm.",
        label_source="USPSTF Clinical Guideline + Meta-analysis",
        label_reference="PMID:25834009",
        label_rationale=(
            "The USPSTF (2016) issued a B-grade recommendation for aspirin use for primary "
            "prevention including colorectal cancer in adults aged 50-59. "
            "Meta-analyses demonstrate that aspirin's inhibition of COX-2 (PTGS2) reduces "
            "prostaglandin E2 production, suppressing tumor-promoting inflammation and "
            "adenoma recurrence. Open Targets records clinical evidence for PTGS2 in CRC."
        ),
        split=BenchmarkSplit.TEST,
    ),

    # ── Directional Negative & Contradiction Controls (ground-truth NEGATIVE) ──

    BenchmarkCase(
        case_id="BENCH-NEG-01",
        drug="Isoproterenol",
        disease="Infantile Hemangioma",
        expected_class=BenchmarkClass.NEGATIVE,
        expected_target="ADRB1",
        rationale=(
            "Beta-adrenergic agonist (ACTIVATION) on ADRB1/ADRB2. "
            "Propranolol's therapeutic efficacy requires beta-antagonism (INHIBITION); "
            "beta-receptor agonism causes vasodilation and opposes therapeutic requirements."
        ),
        evidence_reference="ChEMBL Mechanism AGONIST vs ADRB1 LoF-protect requirement",
        source="Pharmacological Counterfactual Control",
        notes=(
            "Directional antagonist control paired with Propranolol (BENCH-POS-02). "
            "IMPORTANT: Flagged unsuitable_for_directional_negative=True because "
            "Open Targets DoE and DATTs currently carry no directional annotations for ADRB1 "
            "in Infantile Hemangioma specifically. Retained for documentation completeness."
        ),
        label_source="Pharmacological First Principles + ChEMBL Mechanism",
        label_reference="ChEMBL CHEMBL1431 (Isoproterenol); PMID:9488601",
        label_rationale=(
            "Isoproterenol is a non-selective beta-adrenergic full agonist. "
            "Propranolol's efficacy in infantile hemangioma requires ADRB1/ADRB2 antagonism. "
            "Therefore, an agonist on the same target opposes the therapeutic direction."
        ),
        split=BenchmarkSplit.TEST,
        unsuitable_for_directional_negative=True,
    ),

    BenchmarkCase(
        case_id="BENCH-NEG-02",
        drug="Norepinephrine",
        disease="Heart Failure",
        expected_class=BenchmarkClass.NEGATIVE,
        expected_target="ADRB1",
        rationale=(
            "Norepinephrine is a catecholamine that activates ADRB1, causing increased "
            "chronotropy, inotropy and cardiac stress. In chronic heart failure, sustained "
            "ADRB1 activation is pathological — the established therapeutic strategy is "
            "ADRB1 INHIBITION (beta-blockers), not activation."
        ),
        evidence_reference="MERIT-HF, CIBIS-II trials; Open Targets ADRB1 LoF-protect in HF",
        source="ChEMBL / Open Targets",
        notes=(
            "Flagged unsuitable_for_directional_negative=True due to INSUFFICIENT_SOURCE_SIGNAL: "
            "ChEMBL lacks a curated mechanism entry for endogenous norepinephrine in mechanism.json, "
            "so the pipeline correctly assigns drug_action=UNKNOWN and withholds positive/negative prediction."
        ),
        label_source="Clinical Guidelines + Landmark Clinical Trials",
        label_reference="PMID:10764374; PMID:10376614",
        label_rationale=(
            "Multiple landmark RCTs establish that beta-blockade reduces mortality in chronic HF. "
            "Sustained norepinephrine activation is a core pathophysiological driver of HF progression. "
            "However, ChEMBL's mechanism endpoint lacks curated records for norepinephrine, "
            "making this an uncharacterized machine-readable signal in ChEMBL."
        ),
        split=BenchmarkSplit.TEST,
        unsuitable_for_directional_negative=True,
    ),

    BenchmarkCase(
        case_id="BENCH-NEG-03",
        drug="Testosterone",
        disease="Prostate Cancer",
        expected_class=BenchmarkClass.NEGATIVE,
        expected_target="AR",
        rationale=(
            "Testosterone is an androgen receptor (AR) AGONIST/ACTIVATOR. "
            "Prostate cancer is AR-driven; established therapy requires AR antagonism "
            "(antiandrogens: enzalutamide, abiraterone) or androgen deprivation. "
            "Testosterone directly activates the target whose inhibition is required."
        ),
        evidence_reference="Huggins & Hodges 1941 Nobel-cited work; EAU Guidelines; Open Targets AR GoF-risk / LoF-protect in PCa",
        source="ChEMBL / Open Targets / DATTs",
        notes="Verified working contradiction control: Drug ACTIVATION opposes disease INHIBITION requirement.",
        label_source="Nobel Prize Work + Established Clinical Guidelines",
        label_reference="PMID:14350438; PMID:2082610",
        label_rationale=(
            "Huggins and Hodges (1941) established that androgen deprivation causes regression of "
            "prostate cancer metastases (Nobel Prize 1966). "
            "Required therapeutic action = AR INHIBITION. "
            "Testosterone is an AR AGONIST (ACTIVATION) in ChEMBL. "
            "Open Targets clinical precedence and DATTs require AR INHIBITION. "
            "Alignment correctly outputs OPPOSES."
        ),
        split=BenchmarkSplit.TEST,
        unsuitable_for_directional_negative=False,
    ),

    BenchmarkCase(
        case_id="BENCH-NEG-04",
        drug="Pilocarpine",
        disease="Asthma",
        expected_class=BenchmarkClass.NEGATIVE,
        expected_target="CHRM3",
        rationale=(
            "Pilocarpine is a muscarinic acetylcholine receptor agonist (ACTIVATION on CHRM1/CHRM3). "
            "In asthma, bronchial smooth muscle constriction is mediated by muscarinic receptor activation; "
            "established asthma therapy requires muscarinic ANTAGONISM (INHIBITION, e.g. ipratropium, tiotropium). "
            "Pilocarpine agonism directly causes severe bronchoconstriction and is strictly contra-indicated in asthma."
        ),
        evidence_reference="GINA Asthma Guidelines; ChEMBL AGONIST on CHRM1/CHRM3; Open Targets CHRM1/CHRM3 LoF-protect",
        source="ChEMBL / Open Targets / DATTs",
        notes="Verified machine-readable contradiction: Muscarinic AGONIST vs Anticholinergic INHIBITION requirement.",
        label_source="Global Initiative for Asthma (GINA) Guidelines + FDA Drug Label",
        label_reference="PMID:30138982; FDA Salagen Label NDA 020237",
        label_rationale=(
            "Muscarinic agonists such as pilocarpine stimulate CHRM1 and CHRM3 receptors in bronchial "
            "smooth muscle, inducing severe bronchospasm, mucus hypersecretion, and airway narrowing. "
            "Standard asthma pharmacotherapy utilizes muscarinic antagonists (tiotropium, ipratropium) "
            "to achieve bronchodilation (required action = INHIBITION). "
            "ChEMBL annotates pilocarpine as AGONIST (ACTIVATION), while Open Targets and DATTs record "
            "required INHIBITION across 11 independent clinical trial groups. "
            "Alignment correctly computes OPPOSES."
        ),
        split=BenchmarkSplit.TEST,
        unsuitable_for_directional_negative=False,
    ),

    BenchmarkCase(
        case_id="BENCH-NEG-05",
        drug="Albuterol",
        disease="Hypertension",
        expected_class=BenchmarkClass.NEGATIVE,
        expected_target="ADRB2",
        rationale=(
            "Albuterol is a beta-2 adrenergic agonist (ACTIVATION on ADRB2). "
            "In systemic hypertension, beta-adrenergic activation increases heart rate, cardiac output, "
            "and renin release; established antihypertensive therapy utilizes beta-blockers (ADRB1/ADRB2 INHIBITION). "
            "Beta-agonist activation opposes the established therapeutic requirement for blood pressure reduction."
        ),
        evidence_reference="AHA/ACC Hypertension Guidelines; ChEMBL AGONIST on ADRB2; Open Targets ADRB2 LoF-protect in HTN",
        source="ChEMBL / Open Targets / DATTs",
        notes="Verified machine-readable contradiction: Beta-2 AGONIST vs Antihypertensive Beta-Blocker INHIBITION requirement.",
        label_source="AHA/ACC Hypertension Clinical Practice Guidelines",
        label_reference="PMID:29146100; FDA Ventolin Label NDA 020983",
        label_rationale=(
            "Albuterol is a selective beta-2 adrenergic receptor agonist (ACTIVATION in ChEMBL). "
            "In hypertension management, beta-adrenergic blockade (INHIBITION) reduces blood pressure "
            "and cardiovascular mortality. "
            "Open Targets records 10 independent clinical trial precedence groups requiring ADRB2 INHIBITION "
            "in essential hypertension. "
            "Albuterol's agonist action directly opposes this requirement, producing OPPOSES."
        ),
        split=BenchmarkSplit.TEST,
        unsuitable_for_directional_negative=False,
    ),

    # ── Mechanistically Uncertain & Balanced Conflict Controls (ground-truth UNCERTAIN) ──

    BenchmarkCase(
        case_id="BENCH-UNC-01",
        drug="Thalidomide",
        disease="Hypertension",
        expected_class=BenchmarkClass.UNCERTAIN,
        expected_target="TNF",
        rationale=(
            "Thalidomide exhibits binding to TNF/PTGS1 with uncharacterized functional polarity "
            "and no established directional disease-target effect in essential hypertension."
        ),
        evidence_reference="ChEMBL Binding Data lacking functional polarity",
        source="Directional Ambiguity Control",
        notes="Tests system ability to withhold premature positive classification when directional evidence is insufficient.",
        label_source="Absence of directional annotations in configured sources",
        label_reference="ChEMBL CHEMBL267 (Thalidomide); Open Targets TNF-Hypertension associations",
        label_rationale=(
            "Thalidomide has binding activity against TNF/TNFA but its functional relationship "
            "to essential hypertension is not directionally characterized in any configured source. "
            "There is no established mechanistic pathway connecting thalidomide CRBN/TNF activity "
            "to blood pressure regulation with sufficient directional specificity. "
            "This case tests that the system correctly emits INSUFFICIENT when evidence is absent."
        ),
        split=BenchmarkSplit.TEST,
    ),

    BenchmarkCase(
        case_id="BENCH-UNC-02",
        drug="Atorvastatin",
        disease="Major Depressive Disorder",
        expected_class=BenchmarkClass.UNCERTAIN,
        expected_target="HMGCR",
        rationale=(
            "Atorvastatin is an HMG-CoA reductase (HMGCR) inhibitor. While observational and exploratory "
            "studies have investigated anti-inflammatory statin effects in psychiatric disorders, there is "
            "no established causal directional relationship connecting HMGCR inhibition to depressive symptom reduction "
            "in structured genetic, clinical trial, or pharmacological databases."
        ),
        evidence_reference="Cochrane Systematic Review on Statins for Depression; Open Targets HMGCR MDD associations",
        source="Directional Absence / Exploratory Repurposing Control",
        notes=(
            "Replacement for invalid Methotrexate-RA case. Demonstrates genuine lack of machine-readable "
            "directional evidence: 22 Open Targets records without directional consensus, 0 DATTs records, "
            "0 DrugMechDB paths, producing 0 supporting and 0 opposing groups (INSUFFICIENT)."
        ),
        label_source="Cochrane Systematic Review & Meta-Analysis",
        label_reference="PMID:24647326; Cochrane CD010483",
        label_rationale=(
            "Systematic reviews conclude that evidence supporting statin use as an antidepressant treatment "
            "is low-quality and inconclusive, with uncharacterized neurobiological causal directionality. "
            "In Cynthera's pipeline, HMGCR has no curated therapeutic action in DATTs for depression, "
            "no DrugMechDB pathway, and no directional LoF/GoF consensus in Open Targets. "
            "The system correctly emits INSUFFICIENT."
        ),
        split=BenchmarkSplit.TEST,
    ),

    BenchmarkCase(
        case_id="BENCH-UNC-03",
        drug="Nicotine",
        disease="Hypertension",
        expected_class=BenchmarkClass.UNCERTAIN,
        expected_target="CHRNB2",
        rationale=(
            "Nicotine is a nicotinic acetylcholine receptor agonist (ACTIVATION on CHRNB2/CHRNA3). "
            "In vascular and autonomic hypertension biology, nicotinic receptor modulation exhibits "
            "genuinely contradictory clinical and genetic directional evidence: sympathetic ganglionic "
            "stimulation increases blood pressure, while peripheral endothelial vasodilatory pathways "
            "and specific channel variants show opposing effects."
        ),
        evidence_reference="Open Targets multi-directional CHRNB2 hypertension annotations; DATTs nicotinic annotations",
        source="Balanced Multi-Direction Contradiction Control",
        notes=(
            "Tests that balanced multi-direction conflicting evidence (Support: 1 vs Oppose: 1) "
            "is resolved to INSUFFICIENT rather than arbitrarily picking a winner."
        ),
        label_source="Pharmacological & Epidemiological Cardiovascular Literature",
        label_reference="PMID:10498744; Open Targets CHRNB2 Hypertension Records",
        label_rationale=(
            "Nicotinic cholinergic signaling in essential hypertension has both pressor (sympathetic "
            "vasoconstriction) and depressor (nitric-oxide mediated vasodilation) mechanisms. "
            "In Open Targets and DATTs, CHRNB2 has both supporting and opposing directional groups. "
            "Because supporting weight equals opposing weight, the alignment engine correctly "
            "withholds a directional verdict and outputs INSUFFICIENT."
        ),
        split=BenchmarkSplit.TEST,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # DEVELOPMENT SPLIT — Cases for weight calibration only.
    # DO NOT use these cases to evaluate final TEST-split performance.
    # DO NOT tune weights against TEST labels.
    # ══════════════════════════════════════════════════════════════════════════

    # ── DEVELOPMENT Positives ─────────────────────────────────────────────────

    BenchmarkCase(
        case_id="BENCH-DEV-POS-01",
        drug="Imatinib",
        disease="Chronic Myeloid Leukemia",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="ABL1",
        rationale=(
            "Imatinib is a BCR-ABL tyrosine kinase inhibitor (INHIBITION of ABL1). "
            "CML is driven by constitutively active BCR-ABL fusion kinase; "
            "ABL1 INHIBITION is the required and established therapeutic action."
        ),
        evidence_reference="FDA Approval NDA 021588; DrugMechDB DB00619; Open Targets Clinical Precedence ABL1-CML",
        source="ChEMBL / DrugMechDB / Open Targets",
        notes="Landmark precision oncology case. ABL1 is a primary ChEMBL-curated target for imatinib.",
        label_source="FDA Drug Approval + DrugMechDB Curated Path",
        label_reference="FDA NDA 021588; DrugMechDB DB00619; PMID:11423472",
        label_rationale=(
            "Imatinib (Gleevec) received FDA approval for CML in 2001. It competitively inhibits ABL1 "
            "kinase activity, blocking proliferation of BCR-ABL-expressing cells. "
            "DrugMechDB records the complete curated mechanistic path. "
            "Open Targets records clinical precedence for ABL1 in CML with loss-of-function protective direction."
        ),
        split=BenchmarkSplit.DEVELOPMENT,
    ),

    BenchmarkCase(
        case_id="BENCH-DEV-POS-02",
        drug="Trastuzumab",
        disease="Breast Cancer",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="ERBB2",
        rationale=(
            "Trastuzumab is a monoclonal antibody that binds and inhibits HER2/ERBB2. "
            "HER2-positive breast cancer is driven by ERBB2 overexpression/amplification; "
            "ERBB2 INHIBITION is the required therapeutic action."
        ),
        evidence_reference="FDA Approval BLA 103792; Open Targets ERBB2 GoF-risk in BC; DATTs ERBB2 INHIBITION",
        source="ChEMBL / Open Targets / DATTs",
        notes="Paradigmatic targeted therapy case. HER2-overexpression is a canonical GoF-risk oncogene.",
        label_source="FDA Biologic License Approval",
        label_reference="FDA BLA 103792; PMID:9815071",
        label_rationale=(
            "Trastuzumab (Herceptin) received FDA approval for HER2-positive breast cancer in 1998. "
            "It binds domain IV of ERBB2 extracellular domain, blocking downstream proliferative signaling. "
            "Open Targets records ERBB2 as a GoF-risk gene in breast cancer, "
            "requiring INHIBITION — concordant with trastuzumab's mechanism."
        ),
        split=BenchmarkSplit.DEVELOPMENT,
    ),

    BenchmarkCase(
        case_id="BENCH-DEV-POS-03",
        drug="Sildenafil",
        disease="Pulmonary Arterial Hypertension",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="PDE5A",
        rationale=(
            "Sildenafil is a phosphodiesterase-5 (PDE5A) inhibitor. "
            "In pulmonary arterial hypertension, increased cGMP via PDE5 INHIBITION causes "
            "pulmonary vasodilation and reduces vascular resistance."
        ),
        evidence_reference="FDA Approval NDA 022473 (Revatio); Open Targets PDE5A PAH; PMID:15858186",
        source="ChEMBL / Open Targets / DrugMechDB",
        notes="Established repurposing from erectile dysfunction to PAH. PDE5A INHIBITION required.",
        label_source="FDA Drug Approval + Pivotal RCT",
        label_reference="FDA NDA 022473; PMID:15858186 (SUPER-1 Trial)",
        label_rationale=(
            "Sildenafil (Revatio) received FDA approval for PAH in 2005. "
            "The SUPER-1 trial demonstrated significant improvement in exercise capacity. "
            "Mechanism: PDE5A INHIBITION increases cGMP, relaxing pulmonary vascular smooth muscle. "
            "ChEMBL records sildenafil as a PDE5A INHIBITOR; Open Targets records PDE5A LoF-protect in PAH."
        ),
        split=BenchmarkSplit.DEVELOPMENT,
    ),

    BenchmarkCase(
        case_id="BENCH-DEV-POS-04",
        drug="Atorvastatin",
        disease="Hyperlipidemia",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="HMGCR",
        rationale=(
            "Atorvastatin is an HMG-CoA reductase (HMGCR) inhibitor. "
            "In hyperlipidemia, excessive hepatic cholesterol synthesis requires HMGCR INHIBITION "
            "to reduce LDL and total cholesterol levels."
        ),
        evidence_reference="FDA Approval NDA 020702; HMGCR LoF-protect in hypercholesterolemia; PMID:11450675",
        source="ChEMBL / Open Targets / DATTs",
        notes=(
            "Primary indication (not repurposing). HMGCR INHIBITION is the established, well-characterized mechanism. "
            "Note: BENCH-UNC-02 (Atorvastatin → MDD) is the UNCERTAIN version testing directional absence."
        ),
        label_source="FDA Drug Approval + Extensive Clinical Evidence",
        label_reference="FDA NDA 020702; PMID:11450675 (Heart Protection Study)",
        label_rationale=(
            "Atorvastatin (Lipitor) has been FDA approved for hyperlipidemia since 1996. "
            "It competitively inhibits HMGCR, the rate-limiting enzyme in the cholesterol biosynthesis pathway. "
            "Genetic studies (Mendelian randomization) confirm HMGCR loss-of-function variants protect against "
            "hypercholesterolemia, concordant with INHIBITION being the required therapeutic direction."
        ),
        split=BenchmarkSplit.DEVELOPMENT,
    ),

    BenchmarkCase(
        case_id="BENCH-DEV-POS-05",
        drug="Erlotinib",
        disease="Non-Small Cell Lung Cancer",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="EGFR",
        rationale=(
            "Erlotinib is an EGFR tyrosine kinase inhibitor (INHIBITION of EGFR). "
            "NSCLC with EGFR-activating mutations requires EGFR INHIBITION for tumor suppression."
        ),
        evidence_reference="FDA Approval NDA 021743; Open Targets EGFR GoF-risk in NSCLC; DrugMechDB DB00530",
        source="ChEMBL / Open Targets / DrugMechDB",
        notes="Landmark EGFR-targeted therapy. EGFR activating mutations (exon 19 del, L858R) = GoF-risk.",
        label_source="FDA Drug Approval + DrugMechDB Curated Path",
        label_reference="FDA NDA 021743; DrugMechDB DB00530; PMID:15118073",
        label_rationale=(
            "Erlotinib (Tarceva) received FDA approval for NSCLC in 2004. "
            "It inhibits EGFR kinase, blocking proliferative signaling in EGFR-mutant tumors. "
            "DrugMechDB records the curated path. EGFR is a GoF-risk oncogene in NSCLC, requiring INHIBITION."
        ),
        split=BenchmarkSplit.DEVELOPMENT,
    ),

    # ── DEVELOPMENT Negatives (machine-readable contradiction controls) ───────

    BenchmarkCase(
        case_id="BENCH-DEV-NEG-01",
        drug="Phenylephrine",
        disease="Hypertension",
        expected_class=BenchmarkClass.NEGATIVE,
        expected_target="ADRA1A",
        rationale=(
            "Phenylephrine is a selective alpha-1 adrenergic receptor agonist (ACTIVATION of ADRA1A). "
            "In hypertension, vasoconstriction caused by alpha-1 agonism increases peripheral resistance "
            "and raises blood pressure. Established antihypertensive therapy requires alpha-1 ANTAGONISM "
            "(doxazosin, prazosin) or ADRA1A INHIBITION, not activation."
        ),
        evidence_reference="AHA/ACC Hypertension Guidelines; ChEMBL AGONIST on ADRA1A; Open Targets ADRA1A LoF-protect in HTN",
        source="ChEMBL / Open Targets / DATTs",
        notes=(
            "Directional counterfactual: ADRA1A ACTIVATION (phenylephrine) opposes the INHIBITION "
            "required for hypertension treatment. Verified machine-readable contradiction."
        ),
        label_source="AHA/ACC Clinical Practice Guidelines + FDA Drug Label",
        label_reference="PMID:29146100; FDA Phenylephrine Label NDA 009045",
        label_rationale=(
            "Phenylephrine is a pure alpha-1 adrenergic agonist used clinically to RAISE blood pressure "
            "(e.g., in septic shock). In systemic hypertension, blood pressure reduction requires "
            "vasodilation via alpha-1 ANTAGONISM. ChEMBL records phenylephrine as AGONIST on ADRA1A; "
            "Open Targets records ADRA1A LoF-protect in essential hypertension, requiring INHIBITION. "
            "Alignment correctly computes OPPOSES."
        ),
        split=BenchmarkSplit.DEVELOPMENT,
        unsuitable_for_directional_negative=False,
    ),

    BenchmarkCase(
        case_id="BENCH-DEV-NEG-02",
        drug="Dopamine",
        disease="Dilated Cardiomyopathy",
        expected_class=BenchmarkClass.NEGATIVE,
        expected_target="ADRB1",
        rationale=(
            "Dopamine at high doses is a beta-1 adrenergic agonist (ACTIVATION of ADRB1), "
            "causing increased heart rate, contractility, and cardiac stress. "
            "In dilated cardiomyopathy and chronic heart failure, sustained ADRB1 activation "
            "is pathological — the established therapy requires ADRB1 INHIBITION via beta-blockers "
            "(carvedilol, metoprolol). Dopamine's agonist action opposes this requirement."
        ),
        evidence_reference="ESC Heart Failure Guidelines; ChEMBL AGONIST on ADRB1; Open Targets ADRB1 LoF-protect in DCM/HF",
        source="ChEMBL / Open Targets",
        notes=(
            "Endogenous catecholamine used acutely for hemodynamic support but contraindicated "
            "for chronic cardiomyopathy management. ADRB1 AGONIST vs therapeutic INHIBITION requirement."
        ),
        label_source="ESC Heart Failure Clinical Guidelines",
        label_reference="PMID:27206819; PMID:10764374 (MERIT-HF)",
        label_rationale=(
            "Sustained catecholamine-mediated ADRB1 activation is a core pathophysiological driver "
            "of dilated cardiomyopathy progression. Multiple RCTs (MERIT-HF, CIBIS-II) demonstrate "
            "beta-1 blockade reduces mortality. ChEMBL records dopamine as ADRB1 AGONIST; "
            "Open Targets records ADRB1 LoF-protect in DCM requiring INHIBITION. OPPOSES verdict expected."
        ),
        split=BenchmarkSplit.DEVELOPMENT,
        unsuitable_for_directional_negative=False,
    ),

    BenchmarkCase(
        case_id="BENCH-DEV-NEG-03",
        drug="Diazoxide",
        disease="Type 2 Diabetes",
        expected_class=BenchmarkClass.NEGATIVE,
        expected_target="KCNJ11",
        rationale=(
            "Diazoxide is a KATP channel opener (ACTIVATION of KCNJ11/SUR1 complex), "
            "which hyperpolarizes pancreatic beta cells and INHIBITS insulin secretion. "
            "Type 2 diabetes therapy requires KCNJ11 INHIBITION (sulfonylureas like glibenclamide) "
            "to promote insulin secretion and lower blood glucose. "
            "Diazoxide's channel-opening ACTIVATION directly opposes this requirement."
        ),
        evidence_reference="ADA Standards of Care; ChEMBL KCNJ11 ACTIVATOR/OPENER; Open Targets KCNJ11 LoF-protect in T2D",
        source="ChEMBL / Open Targets / DATTs",
        notes=(
            "Diazoxide is used clinically to RAISE blood glucose (treat hypoglycemia/insulinoma), "
            "making it a pharmacological counterpart to sulfonylureas. "
            "Verified machine-readable contradiction: KATP OPENER vs antidiabetic INHIBITION requirement."
        ),
        label_source="ADA Standards of Medical Care in Diabetes + Clinical Pharmacology",
        label_reference="PMID:33298415; FDA Proglycem Label NDA 016366",
        label_rationale=(
            "Diazoxide activates KCNJ11 (Kir6.2 subunit of KATP channel), suppressing insulin secretion. "
            "This is the opposite of antidiabetic sulfonylurea action (KCNJ11 INHIBITION → insulin release). "
            "Open Targets records KCNJ11 LoF-protect in T2D, meaning INHIBITION is required. "
            "Diazoxide ACTIVATION directly opposes this, so alignment should output OPPOSES."
        ),
        split=BenchmarkSplit.DEVELOPMENT,
        unsuitable_for_directional_negative=False,
    ),

    # ── DEVELOPMENT Uncertain (directional ambiguity controls) ───────────────

    BenchmarkCase(
        case_id="BENCH-DEV-UNC-01",
        drug="Lithium",
        disease="Alzheimer's Disease",
        expected_class=BenchmarkClass.UNCERTAIN,
        expected_target="GSK3B",
        rationale=(
            "Lithium inhibits glycogen synthase kinase-3 beta (GSK3B). "
            "While GSK3B hyperactivation is implicated in tau phosphorylation in AD, "
            "the directional consensus for GSK3B INHIBITION as a therapeutic strategy in AD "
            "is not established in structured genetic, clinical trial, or pharmacological databases."
        ),
        evidence_reference="Open Targets GSK3B-AD associations without directional consensus; Cochrane AD Review",
        source="Directional Ambiguity / Exploratory Repurposing Control",
        notes=(
            "Tests system ability to withhold classification when directional evidence is absent or low-confidence. "
            "Multiple small trials of lithium in MCI/AD are ongoing but lack DoE consensus."
        ),
        label_source="Cochrane Systematic Review + Absence of Curated Directional Evidence",
        label_reference="PMID:20238362; Open Targets GSK3B Alzheimer records",
        label_rationale=(
            "While lithium's GSK3B inhibitory mechanism is established, the therapeutic benefit "
            "in established Alzheimer's disease is uncharacterized in directional databases. "
            "Open Targets GSK3B AD associations lack a clear LoF-protect or GoF-risk directional consensus, "
            "and no DATTs curated entry exists for this indication. INSUFFICIENT is expected."
        ),
        split=BenchmarkSplit.DEVELOPMENT,
    ),

    BenchmarkCase(
        case_id="BENCH-DEV-UNC-02",
        drug="Sirolimus",
        disease="Autism Spectrum Disorder",
        expected_class=BenchmarkClass.UNCERTAIN,
        expected_target="MTOR",
        rationale=(
            "Sirolimus (rapamycin) inhibits mTOR complex 1 (MTORC1). "
            "mTOR pathway hyperactivation occurs in some genetic subtypes of ASD (TSC1/TSC2 mutations) "
            "but the directional evidence for MTOR INHIBITION as a general ASD treatment is absent "
            "from structured databases — benefit is subset-specific and not annotated directionally."
        ),
        evidence_reference="Open Targets MTOR-ASD associations; TSC clinical trials; Cochrane ASD interventions",
        source="Subset-Specific / Exploratory Repurposing Control",
        notes=(
            "mTOR inhibition has evidence in TSC-related ASD but not general ASD population. "
            "No directional DoE consensus in Open Targets for MTOR in ASD broadly."
        ),
        label_source="Clinical Trial Evidence (Subset-Specific) + Absence of Broad Directional Evidence",
        label_reference="PMID:27617384; Open Targets MTOR-ASD records",
        label_rationale=(
            "Sirolimus has shown benefit in TSC-related ASD (MTOR pathway hyperactivation). "
            "However, for general ASD as a disease category, no curated directional MTOR "
            "LoF-protect or GoF-risk entry exists in Open Targets or DATTs. "
            "The pipeline correctly emits INSUFFICIENT for the general case."
        ),
        split=BenchmarkSplit.DEVELOPMENT,
    ),

    BenchmarkCase(
        case_id="BENCH-DEV-UNC-03",
        drug="Simvastatin",
        disease="Amyotrophic Lateral Sclerosis",
        expected_class=BenchmarkClass.UNCERTAIN,
        expected_target="HMGCR",
        rationale=(
            "Simvastatin is an HMGCR inhibitor. In ALS, there is no established directional "
            "relationship between HMGCR inhibition and motor neuron disease progression. "
            "Epidemiological studies show mixed and inconclusive results; "
            "no mechanistic directional annotation exists in curated databases."
        ),
        evidence_reference="Cochrane ALS Motor Neuron Disease Reviews; Open Targets HMGCR-ALS associations",
        source="Directional Absence / Negative Exploratory Control",
        notes=(
            "Tests INSUFFICIENT when HMGCR inhibition has no directional consensus in a neurological indication. "
            "Paired with BENCH-DEV-POS-04 (simvastatin in hyperlipidemia) to test indication-specificity."
        ),
        label_source="Cochrane Systematic Review + Absence of Directional Evidence",
        label_reference="PMID:23670155; Open Targets HMGCR ALS records",
        label_rationale=(
            "Multiple clinical trials of statins in ALS have shown no significant benefit. "
            "Cochrane reviews conclude evidence is insufficient and quality is low. "
            "Open Targets contains no directional DoE entries linking HMGCR to ALS with GoF/LoF annotation. "
            "DATTs has no curated HMGCR-ALS pathway. INSUFFICIENT is expected."
        ),
        split=BenchmarkSplit.DEVELOPMENT,
    ),
]



# ── Convenience accessors by split ──────────────────────────────────────────

def get_cases_by_split(split: BenchmarkSplit) -> list[BenchmarkCase]:
    """Return benchmark cases belonging to a specific split."""
    return [c for c in BENCHMARK_DATASET_V1 if c.split == split]


def get_directionally_suitable_negatives() -> list[BenchmarkCase]:
    """Return NEGATIVE benchmark cases that are expected to produce OPPOSES from live pipeline.

    Excludes cases flagged unsuitable_for_directional_negative=True.
    """
    return [
        c for c in BENCHMARK_DATASET_V1
        if c.expected_class == BenchmarkClass.NEGATIVE
        and not c.unsuitable_for_directional_negative
    ]


def get_unsuitable_negatives() -> list[BenchmarkCase]:
    """Return NEGATIVE cases flagged as unsuitable for directional pipeline evaluation."""
    return [
        c for c in BENCHMARK_DATASET_V1
        if c.expected_class == BenchmarkClass.NEGATIVE
        and c.unsuitable_for_directional_negative
    ]


def get_contradiction_cases() -> list[BenchmarkCase]:
    """Return benchmark cases designed to evaluate contradiction handling."""
    return [
        c for c in BENCHMARK_DATASET_V1
        if (c.expected_class == BenchmarkClass.NEGATIVE and not c.unsuitable_for_directional_negative)
        or c.case_id == "BENCH-UNC-03"
    ]


# ── Named split constants ────────────────────────────────────────────────────
BENCHMARK_TEST_SET: list[BenchmarkCase] = get_cases_by_split(BenchmarkSplit.TEST)
BENCHMARK_DEV_SET: list[BenchmarkCase] = get_cases_by_split(BenchmarkSplit.DEVELOPMENT)
BENCHMARK_VAL_SET: list[BenchmarkCase] = get_cases_by_split(BenchmarkSplit.VALIDATION)
