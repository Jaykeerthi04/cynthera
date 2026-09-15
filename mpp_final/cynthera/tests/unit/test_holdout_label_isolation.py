"""Tests for 30-case hold-out benchmark label isolation and dataset integrity.

These tests verify that:
1. The holdout dataset is internally consistent (30 cases, correct categories, no overlaps).
2. No production reasoning module references holdout labels.
3. The label-to-3class mappings are complete and consistent.
4. The standard vs epistemic scoring difference is correctly implemented.
"""
import importlib
import pytest
from pathlib import Path

from backend.evaluation.holdout_30_case_dataset import (
    HOLDOUT_CASES,
    HoldoutCase,
    STANDARD_LABEL_TO_3CLASS,
    EPISTEMIC_LABEL_TO_3CLASS,
    RECOMMENDATION_TO_3CLASS,
    validate_dataset_integrity,
)


def test_dataset_has_exactly_30_cases():
    """The hold-out benchmark must contain exactly 30 cases."""
    assert len(HOLDOUT_CASES) == 30


def test_all_case_ids_are_unique():
    """Every case must have a unique ID."""
    ids = [c.case_id for c in HOLDOUT_CASES]
    assert len(set(ids)) == len(ids), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"


def test_all_drug_disease_pairs_are_unique():
    """No drug-disease pair may appear twice in the hold-out set."""
    pairs = [(c.drug.lower(), c.disease.lower()) for c in HOLDOUT_CASES]
    assert len(set(pairs)) == len(pairs)


def test_category_distribution():
    """Verify category distribution: E=8, F=7, G=8, H=7."""
    from collections import Counter
    cats = Counter(c.category for c in HOLDOUT_CASES)
    assert cats["Established positive"] == 8
    assert cats["Verified negative"] == 7
    assert cats["Unverified"] == 8
    assert cats["Weak/indirect"] == 7


def test_no_overlap_with_25_case_set():
    """No drug-disease pair from the 25-case set may appear in the 30-case set."""
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
        assert pair not in existing_25_pairs, f"OVERLAP: {c.drug} → {c.disease}"


def test_all_labels_are_mapped():
    """Every expected_label must be mapped in both scoring systems."""
    for c in HOLDOUT_CASES:
        assert c.expected_label in STANDARD_LABEL_TO_3CLASS, f"Unmapped label: {c.expected_label}"
        assert c.expected_label in EPISTEMIC_LABEL_TO_3CLASS, f"Unmapped label: {c.expected_label}"


def test_epistemic_vs_standard_difference():
    """The key difference: 'unverified' maps to OPPOSE in standard, UNCERTAIN in epistemic."""
    assert STANDARD_LABEL_TO_3CLASS["unverified"] == "OPPOSE"
    assert EPISTEMIC_LABEL_TO_3CLASS["unverified"] == "UNCERTAIN"

    # All other labels should map the same way
    for label in STANDARD_LABEL_TO_3CLASS:
        if label != "unverified":
            assert STANDARD_LABEL_TO_3CLASS[label] == EPISTEMIC_LABEL_TO_3CLASS[label], (
                f"Unexpected difference for label '{label}'"
            )


def test_recommendation_mapping_is_complete():
    """All recommendation statuses must be mapped to 3-class."""
    expected_recs = {"PROMISING", "NOT_RECOMMENDED", "UNCERTAIN", "INSUFFICIENT_DATA"}
    assert set(RECOMMENDATION_TO_3CLASS.keys()) == expected_recs


def test_validate_dataset_integrity():
    """The validate_dataset_integrity() function must pass without error."""
    validate_dataset_integrity()


def test_label_isolation_from_production_modules():
    """No production reasoning module may reference holdout labels or dataset.

    This is the critical anti-leakage test. If any production module
    (reasoning orchestrator, retrieval pipeline, master orchestrator,
    scientific context builder) contains a reference to the holdout dataset,
    benchmark labels could influence the reasoning engine's output.
    """
    production_modules = [
        "backend.reasoning.orchestrator.reasoning_orchestrator",
        "backend.engineering.retrieval.pipeline",
        "backend.engineering.orchestrator.master_orchestrator",
        "backend.reasoning.context.scientific_context_builder",
        "backend.core.domain.approval_signal",
        "backend.core.domain.reasoning_result",
    ]

    for mod_name in production_modules:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue

        source_file = getattr(mod, "__file__", None)
        if not source_file or not Path(source_file).exists():
            continue

        with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
            source = f.read()

        assert "holdout_30_case_dataset" not in source, (
            f"LABEL LEAKAGE: {mod_name} references holdout_30_case_dataset"
        )
        assert "HOLDOUT_CASES" not in source, (
            f"LABEL LEAKAGE: {mod_name} references HOLDOUT_CASES"
        )
        assert "HoldoutCase" not in source, (
            f"LABEL LEAKAGE: {mod_name} references HoldoutCase"
        )


def test_established_positive_labels_are_consistent():
    """All Category E cases must have expected_label 'established/approved'."""
    for c in HOLDOUT_CASES:
        if c.category == "Established positive":
            assert c.expected_label == "established/approved", (
                f"{c.case_id}: Category E case has wrong label: {c.expected_label}"
            )


def test_verified_negative_labels_are_consistent():
    """All Category F cases must have expected_label 'negative/contradictory'."""
    for c in HOLDOUT_CASES:
        if c.category == "Verified negative":
            assert c.expected_label == "negative/contradictory", (
                f"{c.case_id}: Category F case has wrong label: {c.expected_label}"
            )


def test_unverified_labels_are_consistent():
    """All Category G cases must have expected_label 'unverified'."""
    for c in HOLDOUT_CASES:
        if c.category == "Unverified":
            assert c.expected_label == "unverified", (
                f"{c.case_id}: Category G case has wrong label: {c.expected_label}"
            )


def test_weak_indirect_labels_are_consistent():
    """All Category H cases must have expected_label 'insufficient/weak'."""
    for c in HOLDOUT_CASES:
        if c.category == "Weak/indirect":
            assert c.expected_label == "insufficient/weak", (
                f"{c.case_id}: Category H case has wrong label: {c.expected_label}"
            )


def test_each_case_has_rationale():
    """Every case should have a non-empty scientific rationale."""
    for c in HOLDOUT_CASES:
        assert c.rationale.strip(), f"{c.case_id}: Missing rationale"


def test_case_id_format():
    """All case IDs must follow H-xxx format."""
    import re
    for c in HOLDOUT_CASES:
        assert re.match(r"^H-\d{3}$", c.case_id), f"Invalid case ID format: {c.case_id}"
