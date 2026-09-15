"""Tests verifying approval-anchor indication candidate selection in RetrievalPipeline._parse_indication_data.

Requirements:
- Candidates must pass matches_for_approval_anchor() (DiseaseRelation.SAME) to be eligible.
- Among eligible candidates, Phase 4 (approved) indications are prioritized over lower-phase candidates.
- Unrelated Phase 4 indications are strictly ignored.
- Only Phase 3 candidates retain Phase 3 (is_approved=False).
- Multiple Phase 4 valid candidates break ties deterministically on similarity.
"""
import pytest
from backend.engineering.retrieval.pipeline import RetrievalPipeline


@pytest.fixture
def pipeline():
    return RetrievalPipeline()


def test_candidate_selection_case_a_phase4_beats_exact_phase3(pipeline):
    """Case A: Same disease - Phase 3 exact lexical match vs Phase 4 lower-similarity match.

    Phase 4 must be selected to establish regulatory approval anchor.
    """
    indications = [
        {
            "efo_term": "age-related macular degeneration",
            "mesh_heading": "Macular Degeneration",
            "max_phase_for_ind": 3,
        },
        {
            "efo_term": "wet macular degeneration",
            "mesh_heading": "Wet Macular Degeneration",
            "max_phase_for_ind": 4,
        },
    ]
    sig = pipeline._parse_indication_data(
        indication_data={"indications": indications},
        molecule_data={},
        disease_name="Age-related macular degeneration",
    )
    assert sig is not None
    assert sig.is_approved is True
    assert sig.max_phase == 4
    assert sig.matched_indication_term == "wet macular degeneration"


def test_candidate_selection_case_b_unrelated_phase4_ignored(pipeline):
    """Case B: Unrelated Phase 4 candidate is ignored; valid Phase 3 candidate retained."""
    indications = [
        {
            "efo_term": "prostate cancer",
            "mesh_heading": "Prostatic Neoplasms",
            "max_phase_for_ind": 4,
        },
        {
            "efo_term": "age-related macular degeneration",
            "mesh_heading": "Macular Degeneration",
            "max_phase_for_ind": 3,
        },
    ]
    sig = pipeline._parse_indication_data(
        indication_data={"indications": indications},
        molecule_data={},
        disease_name="Age-related macular degeneration",
    )
    assert sig is not None
    assert sig.is_approved is False
    assert sig.max_phase == 3
    assert sig.matched_indication_term == "age-related macular degeneration"


def test_candidate_selection_case_c_only_phase3_retained(pipeline):
    """Case C: Only valid Phase 3 candidate exists.

    Phase 3 is retained; approval detection does not depend on Phase 4 existing.
    """
    indications = [
        {
            "efo_term": "age-related macular degeneration",
            "mesh_heading": "Macular Degeneration",
            "max_phase_for_ind": 3,
        },
    ]
    sig = pipeline._parse_indication_data(
        indication_data={"indications": indications},
        molecule_data={},
        disease_name="Age-related macular degeneration",
    )
    assert sig is not None
    assert sig.is_approved is False
    assert sig.max_phase == 3
    assert sig.matched_indication_term == "age-related macular degeneration"


def test_candidate_selection_case_d_multiple_phase4_deterministic_tiebreak(pipeline):
    """Case D: Multiple Phase 4 valid candidates.

    Deterministic selection uses existing similarity/tie-break logic.
    """
    indications = [
        {
            "efo_term": "wet macular degeneration",
            "mesh_heading": "Wet Macular Degeneration",
            "max_phase_for_ind": 4,
        },
        {
            "efo_term": "neovascular age-related macular degeneration",
            "mesh_heading": "Neovascular Age-Related Macular Degeneration",
            "max_phase_for_ind": 4,
        },
    ]
    sig = pipeline._parse_indication_data(
        indication_data={"indications": indications},
        molecule_data={},
        disease_name="Age-related macular degeneration",
    )
    assert sig is not None
    assert sig.is_approved is True
    assert sig.max_phase == 4
    # "neovascular age-related macular degeneration" has higher token overlap with "Age-related macular degeneration"
    assert sig.matched_indication_term == "neovascular age-related macular degeneration"
