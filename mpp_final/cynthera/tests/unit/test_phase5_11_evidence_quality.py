"""Unit tests for Phase 5.11 — Mechanistic Evidence Quality Calibration.

Verifies:
1. Structural-only candidate -> STRUCTURAL quality tier
2. Curated candidate -> CURATED quality tier
3. Causal candidate -> CAUSAL quality tier
4. Literature-grounded candidate -> LITERATURE_GROUNDED quality tier
5. Independently validated candidate -> INDEPENDENTLY_VALIDATED quality tier
6. Structural Reactome edge remains non-directional (STRUCTURAL invariant)
7. Quality components serialize correctly in to_dict()
8. Quality classification is deterministic
9. Current numeric MS values remain unchanged (MS preservation invariant)
10. Existing Rule 1 quality gate remains functional
"""
from __future__ import annotations

import uuid
import pytest

from backend.core.domain.candidate_mechanism import CandidateMechanism, MechanismHop
from backend.core.domain.disease import Disease
from backend.core.domain.drug import Drug
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.reasoning.mechanistic.mechanism_validation import MechanismValidator
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner


def _make_pkg(drug_name: str = "DrugA", disease_name: str = "DiseaseB") -> RetrievalPackage:
    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=Drug(name=drug_name, chembl_id="CHEMBL1", identifiers={"chembl": "CHEMBL1"}),
        disease=Disease(name=disease_name, mesh_id="D1", identifiers={"mesh": "D1"}),
    )


# ── 1. Structural-only candidate ──────────────────────────────────────────────
def test_1_structural_only_candidate():
    validator = MechanismValidator()
    hops = [
        MechanismHop(
            from_node="Drug: DrugA",
            to_node="Target: T1",
            predicate="BINDS",
            status="CANDIDATE_STRUCTURAL",
            source_database="ChEMBL",
            evidence_type="STRUCTURAL",
            polarity="UNKNOWN",
            causal_grounding="STRUCTURAL",
        ),
        MechanismHop(
            from_node="Target: T1",
            to_node="Pathway: PW1",
            predicate="PARTICIPANT",
            status="STRUCTURAL_EVIDENCE",
            source_database="Reactome",
            evidence_type="STRUCTURAL",
            polarity="UNKNOWN",
            causal_grounding="STRUCTURAL",
        ),
        MechanismHop(
            from_node="Pathway: PW1",
            to_node="Disease: DiseaseB",
            predicate="ASSOCIATED_WITH",
            status="CANDIDATE_STRUCTURAL",
            source_database="Open Targets",
            evidence_type="STRUCTURAL",
            polarity="UNKNOWN",
            causal_grounding="STRUCTURAL",
        ),
    ]
    cand = CandidateMechanism(
        name="Structural Route",
        support_level="WEAK_SPECULATIVE",
        confidence_score=0.40,
        summary_chain=["DrugA", "T1", "PW1", "DiseaseB"],
        hops=hops,
    )
    validated = validator.validate(_make_pkg(), [cand], claims=[])[0]

    assert validated.quality_tier == "STRUCTURAL"
    assert validated.quality_components["structural_edges"] == 3
    assert validated.quality_components["causal_edges"] == 0
    assert validated.quality_components["grounded_edges"] == 0
    assert validated.quality_components["literature_claims"] == 0
    assert validated.support_level == "WEAK_SPECULATIVE"


# ── 2. Curated candidate ──────────────────────────────────────────────────────
def test_2_curated_candidate():
    validator = MechanismValidator()
    hops = [
        MechanismHop(
            from_node="Drug: DrugA",
            to_node="Target: T1",
            predicate="ASSOCIATED_WITH",
            status="DATABASE_SUPPORTED",
            source_database="ChEMBL",
            evidence_type="CURATED",
            polarity="UNKNOWN",
            causal_grounding="CURATED",
        ),
        MechanismHop(
            from_node="Target: T1",
            to_node="Disease: DiseaseB",
            predicate="ASSOCIATED_WITH",
            status="DATABASE_SUPPORTED",
            source_database="DrugMechDB",
            evidence_type="CURATED",
            polarity="UNKNOWN",
            causal_grounding="CURATED",
        ),
    ]
    cand = CandidateMechanism(
        name="Curated Route",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.55,
        summary_chain=["DrugA", "T1", "DiseaseB"],
        hops=hops,
    )
    validated = validator.validate(_make_pkg(), [cand], claims=[])[0]

    assert validated.quality_tier == "CURATED"
    assert validated.quality_components["grounded_edges"] == 2
    assert validated.quality_components["curated_database_support"] is True
    assert validated.quality_components["causal_edges"] == 0


# ── 3. Causal candidate ───────────────────────────────────────────────────────
def test_3_causal_candidate():
    validator = MechanismValidator()
    hops = [
        MechanismHop(
            from_node="Drug: DrugA",
            to_node="Target: T1",
            predicate="INHIBITOR",
            status="DATABASE_SUPPORTED",
            source_database="ChEMBL",
            evidence_type="DIRECT",
            polarity="NEGATIVE",
            causal_grounding="DIRECT",
        ),
        MechanismHop(
            from_node="Target: T1",
            to_node="Disease: DiseaseB",
            predicate="DOWNREGULATES",
            status="DATABASE_SUPPORTED",
            source_database="Open Targets",
            evidence_type="CURATED",
            polarity="NEGATIVE",
            causal_grounding="CURATED",
        ),
    ]
    cand = CandidateMechanism(
        name="Causal Route",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.60,
        summary_chain=["DrugA", "T1", "DiseaseB"],
        hops=hops,
    )
    validated = validator.validate(_make_pkg(), [cand], claims=[])[0]

    assert validated.quality_tier == "CAUSAL"
    assert validated.quality_components["causal_edges"] >= 1
    assert validated.quality_components["directionally_supported"] is True


# ── 4. Literature-grounded candidate ──────────────────────────────────────────
def test_4_literature_grounded_candidate():
    validator = MechanismValidator()
    hops = [
        MechanismHop(
            from_node="Drug: DrugA",
            to_node="Target: T1",
            predicate="INHIBITOR",
            status="LITERATURE_SUPPORTED",
            source_database="ChEMBL",
            evidence_type="LITERATURE",
            polarity="NEGATIVE",
            causal_grounding="DIRECT",
            supporting_claims=[{"pmid": "12345678", "claim": "DrugA inhibits T1 in vitro", "source": "PubMed"}],
        ),
        MechanismHop(
            from_node="Target: T1",
            to_node="Disease: DiseaseB",
            predicate="ASSOCIATED_WITH",
            status="DATABASE_SUPPORTED",
            source_database="Open Targets",
            evidence_type="CURATED",
            polarity="UNKNOWN",
            causal_grounding="CURATED",
        ),
    ]
    cand = CandidateMechanism(
        name="Literature-Grounded Route",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.58,
        summary_chain=["DrugA", "T1", "DiseaseB"],
        hops=hops,
    )
    validated = validator.validate(_make_pkg(), [cand], claims=[])[0]

    assert validated.quality_tier == "LITERATURE_GROUNDED"
    assert validated.quality_components["literature_claims"] >= 1
    assert validated.quality_components["independent_evidence_groups"] == 1


# ── 5. Independently validated candidate ──────────────────────────────────────
def test_5_independently_validated_candidate():
    validator = MechanismValidator()
    hops = [
        MechanismHop(
            from_node="Drug: DrugA",
            to_node="Target: T1",
            predicate="INHIBITOR",
            status="LITERATURE_SUPPORTED",
            source_database="ChEMBL",
            evidence_type="LITERATURE",
            polarity="NEGATIVE",
            causal_grounding="DIRECT",
            supporting_claims=[{"pmid": "11111111", "claim": "In vitro study", "source": "Study1_PMID_11111111"}],
        ),
        MechanismHop(
            from_node="Target: T1",
            to_node="Disease: DiseaseB",
            predicate="ASSOCIATED_WITH",
            status="LITERATURE_SUPPORTED",
            source_database="PubMed",
            evidence_type="LITERATURE",
            polarity="NEGATIVE",
            causal_grounding="CURATED",
            supporting_claims=[{"pmid": "22222222", "claim": "Independent clinical cohort", "source": "Study2_PMID_22222222"}],
        ),
    ]
    cand = CandidateMechanism(
        name="Independently Validated Route",
        support_level="STRONGLY_SUPPORTED",
        confidence_score=0.72,
        summary_chain=["DrugA", "T1", "DiseaseB"],
        hops=hops,
    )
    validated = validator.validate(_make_pkg(), [cand], claims=[])[0]

    assert validated.quality_tier == "INDEPENDENTLY_VALIDATED"
    assert validated.quality_components["independent_evidence_groups"] >= 2
    assert validated.quality_components["causal_edges"] >= 1


# ── 6. Structural Reactome edge remains non-directional ───────────────────────
def test_6_structural_reactome_edge_remains_nondirectional():
    validator = MechanismValidator()
    # CATALYST / INPUT / OUTPUT / PARTICIPANT must be counted as structural, NOT causal
    for role in ["CATALYST", "INPUT", "OUTPUT", "PARTICIPANT"]:
        hops = [
            MechanismHop(
                from_node="Target: T1",
                to_node="Pathway: PW1",
                predicate=f"REACTOME_{role}",
                status="STRUCTURAL_EVIDENCE",
                source_database="Reactome",
                evidence_type="STRUCTURAL",
                polarity="UNKNOWN",
                causal_grounding="STRUCTURAL",
            )
        ]
        cand = CandidateMechanism(
            name=f"Reactome {role} Hop",
            support_level="WEAK_SPECULATIVE",
            confidence_score=0.40,
            summary_chain=["T1", "PW1"],
            hops=hops,
        )
        validated = validator.validate(_make_pkg(), [cand], claims=[])[0]
        assert validated.quality_components["structural_edges"] >= 1
        assert validated.quality_components["causal_edges"] == 0
        assert validated.quality_tier == "STRUCTURAL"


# ── 7. Quality components serialize correctly ─────────────────────────────────
def test_7_quality_components_serialize_correctly():
    cand = CandidateMechanism(
        name="Serialization Check",
        support_level="WEAK_SPECULATIVE",
        confidence_score=0.45,
        summary_chain=["Drug", "Target"],
        quality_tier="STRUCTURAL",
        quality_components={
            "structural_edges": 2,
            "causal_edges": 0,
            "grounded_edges": 0,
            "reaction_evidence": 1,
            "literature_claims": 0,
            "independent_evidence_groups": 0,
            "curated_database_support": True,
            "directionally_supported": False,
        },
    )
    d = cand.to_dict()
    assert "quality_tier" in d
    assert d["quality_tier"] == "STRUCTURAL"
    assert "quality_components" in d
    assert d["quality_components"]["structural_edges"] == 2
    assert d["quality_components"]["curated_database_support"] is True


# ── 8. Quality classification is deterministic ────────────────────────────────
def test_8_quality_classification_deterministic():
    validator = MechanismValidator()
    hops = [
        MechanismHop(
            from_node="Drug: D",
            to_node="Target: T",
            predicate="INHIBITOR",
            status="DATABASE_SUPPORTED",
            source_database="ChEMBL",
            evidence_type="DIRECT",
            polarity="NEGATIVE",
            causal_grounding="DIRECT",
        ),
        MechanismHop(
            from_node="Target: T",
            to_node="Disease: Dis",
            predicate="ASSOCIATED_WITH",
            status="DATABASE_SUPPORTED",
            source_database="Open Targets",
            evidence_type="CURATED",
            polarity="UNKNOWN",
            causal_grounding="CURATED",
        ),
    ]
    cand = CandidateMechanism(
        name="Deterministic Check",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.55,
        summary_chain=["D", "T", "Dis"],
        hops=hops,
    )
    # Run twice
    v1 = validator.validate(_make_pkg(), [cand], claims=[])[0]
    v2 = validator.validate(_make_pkg(), [cand], claims=[])[0]

    assert v1.quality_tier == v2.quality_tier
    assert v1.quality_components == v2.quality_components
    assert v1.confidence_score == v2.confidence_score


# ── 9. Current numeric MS values remain unchanged ─────────────────────────────
def test_9_numeric_ms_values_remain_unchanged():
    reasoner = MultiHopReasoner()
    cand1 = CandidateMechanism(
        name="Candidate 1",
        support_level="MODERATELY_SUPPORTED",
        confidence_score=0.60,
        summary_chain=["D", "T1", "Dis"],
        quality_tier="CAUSAL",
    )
    cand2 = CandidateMechanism(
        name="Candidate 2",
        support_level="WEAK_SPECULATIVE",
        confidence_score=0.40,
        summary_chain=["D", "T2", "Dis"],
        quality_tier="STRUCTURAL",
    )
    # compute_mechanistic_score_from_candidates formula must remain frozen
    ms, level = reasoner.compute_mechanistic_score_from_candidates([cand1, cand2])
    # Frozen contract: best usable candidate score = 0.60, level = "MEDIUM"
    assert ms == 0.60
    assert level == "MEDIUM"


# ── 10. Existing Rule 1 quality gate remains functional ────────────────────────
def test_10_rule_1_quality_gate_remains_functional():
    reasoner = MultiHopReasoner()
    # A candidate with WEAK_SPECULATIVE confidence_score >= 0.40
    cand_speculative = CandidateMechanism(
        name="Speculative Candidate",
        support_level="WEAK_SPECULATIVE",
        confidence_score=0.45,
        summary_chain=["D", "PW", "Dis"],
        quality_tier="STRUCTURAL",
    )
    ms, level = reasoner.compute_mechanistic_score_from_candidates([cand_speculative])
    assert ms == 0.45
    assert level == "LOW"

    # Multiple candidates where all are WEAK_SPECULATIVE
    cand_spec2 = CandidateMechanism(
        name="Speculative Candidate 2",
        support_level="WEAK_SPECULATIVE",
        confidence_score=0.35,
        summary_chain=["D", "PW2", "Dis"],
        quality_tier="STRUCTURAL",
    )
    ms2, level2 = reasoner.compute_mechanistic_score_from_candidates([cand_speculative, cand_spec2])
    assert ms2 == 0.45
    assert level2 == "LOW"
