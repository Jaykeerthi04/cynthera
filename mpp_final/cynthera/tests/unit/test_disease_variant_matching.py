"""Tests for disease variant normalization and indication semantic matching.

Validates Fix 3 (ontology-aware disease name normalization) from the final
accuracy repair.  Tests the _normalize_disease_variants() static method
and the _parse_indication_data() behavior with disease subtypes.
"""
import pytest
from backend.engineering.retrieval.pipeline import RetrievalPipeline


# ── _normalize_disease_variants Tests ──


def test_er_positive_breast_cancer_produces_parent():
    """ER-positive breast cancer → ['ER-positive breast cancer', 'breast cancer']"""
    variants = RetrievalPipeline._normalize_disease_variants("ER-positive breast cancer")
    assert "ER-positive breast cancer" in variants
    assert any("breast cancer" == v.lower() for v in variants)


def test_her2_positive_breast_cancer_produces_parent():
    """HER2-positive breast cancer → ['HER2-positive breast cancer', 'breast cancer']"""
    variants = RetrievalPipeline._normalize_disease_variants("HER2-positive breast cancer")
    assert "HER2-positive breast cancer" in variants
    assert any("breast cancer" == v.lower() for v in variants)


def test_secondary_prevention_cardiovascular():
    """Secondary prevention of cardiovascular disease → includes 'cardiovascular disease'"""
    variants = RetrievalPipeline._normalize_disease_variants(
        "Secondary prevention of cardiovascular disease"
    )
    assert "Secondary prevention of cardiovascular disease" in variants
    assert any("cardiovascular disease" == v.lower() for v in variants)


def test_metastatic_colorectal_cancer():
    """metastatic colorectal cancer → includes 'colorectal cancer'"""
    variants = RetrievalPipeline._normalize_disease_variants("metastatic colorectal cancer")
    assert any("colorectal cancer" == v.lower() for v in variants)


def test_plain_disease_no_extra_variants():
    """A plain disease name with no subtype pattern yields only itself."""
    variants = RetrievalPipeline._normalize_disease_variants("Asthma")
    assert variants == ["Asthma"]


def test_kras_mutant_nsclc():
    """KRAS-mutant non-small cell lung cancer → includes parent."""
    variants = RetrievalPipeline._normalize_disease_variants(
        "KRAS-mutant non-small cell lung cancer"
    )
    assert any("non-small cell lung cancer" in v.lower() for v in variants)


def test_advanced_melanoma():
    """advanced melanoma → includes 'melanoma'"""
    variants = RetrievalPipeline._normalize_disease_variants("advanced melanoma")
    assert any("melanoma" == v.lower() for v in variants)


def test_allergic_rhinitis_unchanged():
    """Allergic rhinitis has no subtype prefix and should return only itself."""
    variants = RetrievalPipeline._normalize_disease_variants("Allergic rhinitis")
    assert variants == ["Allergic rhinitis"]


def test_deduplication():
    """Ensure no duplicate variants are returned."""
    variants = RetrievalPipeline._normalize_disease_variants("ER-positive breast cancer")
    assert len(variants) == len(set(v.lower() for v in variants))


# ── _parse_indication_data with Semantic Matching Tests ──


def test_subtype_matches_parent_indication():
    """ER-positive breast cancer should match a 'breast cancer' indication."""
    pipeline = RetrievalPipeline(db_path=":memory:")
    indication_data = {
        "indications": [
            {
                "efo_term": "breast carcinoma",
                "mesh_heading": "breast neoplasms",
                "max_phase_for_ind": 4,
            }
        ]
    }
    molecule_data = {"max_phase": 4}

    # Subtype query should also match via variant normalization
    signal_subtype = pipeline._parse_indication_data(
        indication_data, molecule_data, "ER-positive breast cancer"
    )
    # The parent variant "breast cancer" should match "breast carcinoma"
    assert signal_subtype is not None
    assert signal_subtype.match_confidence > 0.0


def test_cardiovascular_prevention_matches():
    """Secondary prevention of cardiovascular disease should match cardiovascular indications."""
    pipeline = RetrievalPipeline(db_path=":memory:")
    indication_data = {
        "indications": [
            {
                "efo_term": "cardiovascular disease",
                "mesh_heading": "cardiovascular diseases",
                "max_phase_for_ind": 4,
            }
        ]
    }
    molecule_data = {"max_phase": 4}

    signal = pipeline._parse_indication_data(
        indication_data, molecule_data, "Secondary prevention of cardiovascular disease"
    )
    assert signal is not None
    assert signal.match_confidence > 0.30


def test_plain_disease_still_matches():
    """Verify the existing matching logic is not broken for plain disease names."""
    pipeline = RetrievalPipeline(db_path=":memory:")
    indication_data = {
        "indications": [
            {
                "efo_term": "asthma",
                "mesh_heading": "asthma",
                "max_phase_for_ind": 4,
            }
        ]
    }
    molecule_data = {"max_phase": 4}

    signal = pipeline._parse_indication_data(
        indication_data, molecule_data, "Asthma"
    )
    assert signal is not None
    assert signal.is_approved
    assert signal.match_confidence >= 0.6  # Substring match boost
