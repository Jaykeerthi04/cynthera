"""CYNTHERA — 30-Case Hold-Out Evaluation Dataset.

This module defines the 30-case hold-out benchmark that is COMPLETELY SEPARATE
from the existing 25-case regression benchmark.

IMPORTANT DESIGN CONSTRAINTS:
- These labels are evaluation-only ground truth.
- Labels must NEVER enter the reasoning engine.
- No expected_class or expected_category may be passed to any
  production reasoning, retrieval, or orchestration function.
- This file is imported ONLY by evaluation runners and evaluation tests.
- The reasoning engine must remain benchmark-agnostic.

Category Structure:
- Category E: Established Positive (8 cases) — FDA/EMA-approved indications
- Category F: Verified Negative (7 cases) — Documented clinical trial failure
- Category G: Unverified / No Established Indication (8 cases) — Hallucination traps
- Category H: Weak / Indirect Evidence (7 cases) — Preclinical or epidemiological only

Ground Truth Labelling Philosophy:
- "established/approved": Drug is approved for this specific indication (Phase 4)
- "negative/contradictory": Phase II/III clinical trial(s) showed futility, harm, or no benefit
- "unverified": No approved indication AND no conclusive clinical trial evidence
- "insufficient/weak": Preclinical, epidemiological, or very early-stage evidence only

Epistemic Mapping (protects UNKNOWN ≠ NEGATIVE principle):
  Standard 3-class:   established→SUPPORT, negative→OPPOSE, unverified→OPPOSE, weak→UNCERTAIN
  Epistemic 3-class:  established→SUPPORT, negative→OPPOSE, unverified→UNCERTAIN, weak→UNCERTAIN

The epistemic mapping correctly distinguishes verified therapeutic failure from
absence of evidence. This is the fundamental epistemic principle CYNTHERA is designed around.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(frozen=True)
class HoldoutCase:
    """A single hold-out evaluation case.

    Attributes:
        case_id: Unique identifier for this case (H-xxx format).
        category: Human-readable category label.
        drug: Drug name (as it would be entered by a researcher).
        disease: Disease name (as it would be entered by a researcher).
        expected_label: Ground truth label for evaluation.
        rationale: Brief scientific rationale for the expected label.
    """

    case_id: str
    category: str
    drug: str
    disease: str
    expected_label: str
    rationale: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# 30 HOLD-OUT BENCHMARK CASES
# ─────────────────────────────────────────────────────────────────────────────
# These 30 cases are completely disjoint from the 25-case regression set.
# No drug-disease pair from the 25-case set appears here.

HOLDOUT_CASES: list[HoldoutCase] = [
    # ── CATEGORY E: ESTABLISHED POSITIVE (8) ──
    # Drug-disease pairs with confirmed Phase 4 / approved indication
    HoldoutCase(
        case_id="H-001",
        category="Established positive",
        drug="Metformin",
        disease="Type 2 diabetes mellitus",
        expected_label="established/approved",
        rationale="First-line oral antidiabetic agent. FDA-approved for T2DM.",
    ),
    HoldoutCase(
        case_id="H-002",
        category="Established positive",
        drug="Omeprazole",
        disease="Gastroesophageal reflux disease",
        expected_label="established/approved",
        rationale="Proton pump inhibitor. FDA-approved for GERD.",
    ),
    HoldoutCase(
        case_id="H-003",
        category="Established positive",
        drug="Adalimumab",
        disease="Crohn disease",
        expected_label="established/approved",
        rationale="Anti-TNF monoclonal antibody. FDA-approved for Crohn disease.",
    ),
    HoldoutCase(
        case_id="H-004",
        category="Established positive",
        drug="Rituximab",
        disease="Non-Hodgkin lymphoma",
        expected_label="established/approved",
        rationale="Anti-CD20 monoclonal antibody. FDA-approved for NHL.",
    ),
    HoldoutCase(
        case_id="H-005",
        category="Established positive",
        drug="Insulin glargine",
        disease="Type 1 diabetes mellitus",
        expected_label="established/approved",
        rationale="Long-acting insulin analogue. FDA-approved for T1DM.",
    ),
    HoldoutCase(
        case_id="H-006",
        category="Established positive",
        drug="Sertraline",
        disease="Major depressive disorder",
        expected_label="established/approved",
        rationale="SSRI antidepressant. FDA-approved for MDD.",
    ),
    HoldoutCase(
        case_id="H-007",
        category="Established positive",
        drug="Methotrexate",
        disease="Rheumatoid arthritis",
        expected_label="established/approved",
        rationale="DMARD. FDA-approved for RA.",
    ),
    HoldoutCase(
        case_id="H-008",
        category="Established positive",
        drug="Doxorubicin",
        disease="Breast cancer",
        expected_label="established/approved",
        rationale="Anthracycline chemotherapy. FDA-approved for breast cancer.",
    ),

    # ── CATEGORY F: VERIFIED NEGATIVE / CLINICAL FAILURE (7) ──
    # Drug-disease pairs with documented Phase II/III clinical trial failure
    HoldoutCase(
        case_id="H-009",
        category="Verified negative",
        drug="Hydroxychloroquine",
        disease="COVID-19",
        expected_label="negative/contradictory",
        rationale="RECOVERY trial (n=4716): no clinical benefit. WHO SOLIDARITY confirmed.",
    ),
    HoldoutCase(
        case_id="H-010",
        category="Verified negative",
        drug="Ivermectin",
        disease="COVID-19",
        expected_label="negative/contradictory",
        rationale="TOGETHER trial (n=1358), ACTIV-6: no clinical benefit over placebo.",
    ),
    HoldoutCase(
        case_id="H-011",
        category="Verified negative",
        drug="Celecoxib",
        disease="Alzheimer disease",
        expected_label="negative/contradictory",
        rationale="ADAPT trial: no cognitive benefit, cardiovascular safety concerns led to termination.",
    ),
    HoldoutCase(
        case_id="H-012",
        category="Verified negative",
        drug="Simvastatin",
        disease="Sepsis",
        expected_label="negative/contradictory",
        rationale="Multiple Phase III RCTs (e.g., ASEPSIS, SAILS): no mortality benefit.",
    ),
    HoldoutCase(
        case_id="H-013",
        category="Verified negative",
        drug="Niacin",
        disease="Cardiovascular disease",
        expected_label="negative/contradictory",
        rationale="AIM-HIGH (n=3414), HPS2-THRIVE (n=25,673): no additional benefit + adverse events.",
    ),
    HoldoutCase(
        case_id="H-014",
        category="Verified negative",
        drug="Dexamethasone",
        disease="Traumatic brain injury",
        expected_label="negative/contradictory",
        rationale="CRASH trial (n=10,008): 14-day mortality significantly HIGHER with dexamethasone.",
    ),
    HoldoutCase(
        case_id="H-015",
        category="Verified negative",
        drug="Interferon beta-1a",
        disease="COVID-19",
        expected_label="negative/contradictory",
        rationale="WHO SOLIDARITY trial: no reduction in mortality, ventilation, or hospitalization.",
    ),

    # ── CATEGORY G: UNVERIFIED / NO ESTABLISHED INDICATION (8) ──
    # Drug-disease pairs with no approved indication and no conclusive trial evidence
    HoldoutCase(
        case_id="H-016",
        category="Unverified",
        drug="Omeprazole",
        disease="Parkinson disease",
        expected_label="unverified",
        rationale="No indication data, no clinical trials, no mechanistic basis.",
    ),
    HoldoutCase(
        case_id="H-017",
        category="Unverified",
        drug="Amlodipine",
        disease="Lung cancer",
        expected_label="unverified",
        rationale="Calcium channel blocker. No oncological indication or evidence.",
    ),
    HoldoutCase(
        case_id="H-018",
        category="Unverified",
        drug="Metoprolol",
        disease="Autism spectrum disorder",
        expected_label="unverified",
        rationale="Beta-blocker for cardiovascular conditions. No autism indication.",
    ),
    HoldoutCase(
        case_id="H-019",
        category="Unverified",
        drug="Gabapentin",
        disease="Pancreatic cancer",
        expected_label="unverified",
        rationale="Anticonvulsant/neuropathic pain agent. No oncological indication.",
    ),
    HoldoutCase(
        case_id="H-020",
        category="Unverified",
        drug="Cetirizine",
        disease="Multiple sclerosis",
        expected_label="unverified",
        rationale="H1 antihistamine. No neurological/autoimmune disease indication.",
    ),
    HoldoutCase(
        case_id="H-021",
        category="Unverified",
        drug="Montelukast",
        disease="Prostate cancer",
        expected_label="unverified",
        rationale="Leukotriene receptor antagonist for asthma. No oncological indication.",
    ),
    HoldoutCase(
        case_id="H-022",
        category="Unverified",
        drug="Sildenafil",
        disease="Amyotrophic lateral sclerosis",
        expected_label="unverified",
        rationale="PDE5 inhibitor for ED/PAH. No ALS indication or evidence.",
    ),
    HoldoutCase(
        case_id="H-023",
        category="Unverified",
        drug="Ranitidine",
        disease="Tuberculosis",
        expected_label="unverified",
        rationale="H2 receptor antagonist (withdrawn). No anti-infective indication.",
    ),

    # ── CATEGORY H: WEAK / INDIRECT EVIDENCE (7) ──
    # Drug-disease pairs with preclinical, epidemiological, or early-stage evidence only
    HoldoutCase(
        case_id="H-024",
        category="Weak/indirect",
        drug="Metformin",
        disease="Colorectal cancer",
        expected_label="insufficient/weak",
        rationale="Epidemiological associations (observational studies). No Phase III RCT treatment evidence.",
    ),
    HoldoutCase(
        case_id="H-025",
        category="Weak/indirect",
        drug="Rapamycin",
        disease="Aging",
        expected_label="insufficient/weak",
        rationale="Strong preclinical evidence (mTOR pathway). No Phase III human anti-aging trial.",
    ),
    HoldoutCase(
        case_id="H-026",
        category="Weak/indirect",
        drug="Valproic acid",
        disease="Glioblastoma",
        expected_label="insufficient/weak",
        rationale="HDAC inhibitor with preclinical anticancer activity. Small Phase II trials only.",
    ),
    HoldoutCase(
        case_id="H-027",
        category="Weak/indirect",
        drug="Doxycycline",
        disease="Parkinson disease",
        expected_label="insufficient/weak",
        rationale="Preclinical MMP inhibition and anti-inflammatory neuroprotection. No clinical RCT.",
    ),
    HoldoutCase(
        case_id="H-028",
        category="Weak/indirect",
        drug="Thalidomide",
        disease="Crohn disease",
        expected_label="insufficient/weak",
        rationale="Small open-label studies showing response. No Phase III RCT. Teratogenicity concerns.",
    ),
    HoldoutCase(
        case_id="H-029",
        category="Weak/indirect",
        drug="Niclosamide",
        disease="Colorectal cancer",
        expected_label="insufficient/weak",
        rationale="Anthelmintic with preclinical Wnt pathway inhibition. No human oncology trial.",
    ),
    HoldoutCase(
        case_id="H-030",
        category="Weak/indirect",
        drug="Disulfiram",
        disease="Glioblastoma",
        expected_label="insufficient/weak",
        rationale="ALDH inhibitor with preclinical anticancer activity. Case reports only, no Phase III.",
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# 3-CLASS MAPPING
# ─────────────────────────────────────────────────────────────────────────────

STANDARD_LABEL_TO_3CLASS: dict[str, str] = {
    "established/approved": "SUPPORT",
    "negative/contradictory": "OPPOSE",
    "unverified": "OPPOSE",
    "insufficient/weak": "UNCERTAIN",
}

EPISTEMIC_LABEL_TO_3CLASS: dict[str, str] = {
    "established/approved": "SUPPORT",
    "negative/contradictory": "OPPOSE",
    "unverified": "UNCERTAIN",   # ← Key difference: UNKNOWN ≠ NEGATIVE
    "insufficient/weak": "UNCERTAIN",
}

RECOMMENDATION_TO_3CLASS: dict[str, str] = {
    "PROMISING": "SUPPORT",
    "NOT_RECOMMENDED": "OPPOSE",
    "UNCERTAIN": "UNCERTAIN",
    "INSUFFICIENT_DATA": "UNCERTAIN",
}


def validate_dataset_integrity() -> None:
    """Validate dataset invariants. Raises AssertionError on violation."""
    assert len(HOLDOUT_CASES) == 30, f"Expected 30 cases, got {len(HOLDOUT_CASES)}"

    # Unique case IDs
    ids = [c.case_id for c in HOLDOUT_CASES]
    assert len(set(ids)) == len(ids), f"Duplicate case IDs: {[x for x in ids if ids.count(x) > 1]}"

    # Unique drug-disease pairs
    pairs = [(c.drug.lower(), c.disease.lower()) for c in HOLDOUT_CASES]
    assert len(set(pairs)) == len(pairs), "Duplicate drug-disease pairs"

    # Category distribution
    from collections import Counter

    cats = Counter(c.category for c in HOLDOUT_CASES)
    assert cats["Established positive"] == 8
    assert cats["Verified negative"] == 7
    assert cats["Unverified"] == 8
    assert cats["Weak/indirect"] == 7

    # All labels are mapped
    for c in HOLDOUT_CASES:
        assert c.expected_label in STANDARD_LABEL_TO_3CLASS, f"Unmapped label: {c.expected_label}"
        assert c.expected_label in EPISTEMIC_LABEL_TO_3CLASS, f"Unmapped label: {c.expected_label}"

    # No overlap with existing 25-case pairs
    existing_25_pairs = {
        ("lisinopril", "hypertension"),
        ("aspirin", "secondary prevention of cardiovascular disease"),
        ("budesonide", "asthma"),
        ("fluticasone", "allergic rhinitis"),
        ("etanercept", "rheumatoid arthritis"),
        ("tamoxifen", "er-positive breast cancer"),
        ("trastuzumab", "her2-positive breast cancer"),
        ("metformin", "pancreatic cancer"),
        ("furosemide", "depression"),
        ("warfarin", "leishmaniasis"),
        ("pregabalin", "breast cancer"),
        ("tamsulosin", "liver cancer"),
        ("imatinib", "covid-19"),
        ("azithromycin", "covid-19"),
        ("fluvoxamine", "covid-19"),
        ("aspirin", "covid-19"),
        ("baricitinib", "covid-19"),
        ("atorvastatin", "alzheimer disease"),
        ("lithium", "alzheimer disease"),
        ("propranolol", "depression"),
        ("colchicine", "colorectal cancer"),
        ("escitalopram", "neuropathic pain"),
        ("furosemide", "copd"),
        ("baricitinib", "influenza"),
        ("losartan", "breast cancer"),
    }
    for c in HOLDOUT_CASES:
        pair = (c.drug.lower(), c.disease.lower())
        assert pair not in existing_25_pairs, (
            f"OVERLAP with 25-case set: {c.drug} → {c.disease}"
        )
