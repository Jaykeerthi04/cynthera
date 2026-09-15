"""CYNTHERA — Phase 5.11.5 Mechanistic Evidence Quality Audit.

Audits discovered candidate mechanisms across diverse biological cases,
printing candidate ID, summary path, public support level, internal quality tier,
the 8-dimensional quality components breakdown, and scientific explanation.
"""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
from backend.core.domain.candidate_mechanism import CandidateMechanism, MechanismHop
from backend.core.domain.disease import Disease
from backend.core.domain.drug import Drug
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.reasoning.mechanistic.mechanism_validation import MechanismValidator


def make_test_hops(case_type: str) -> list[MechanismHop]:
    if case_type == "STRUCTURAL":
        return [
            MechanismHop(
                from_node="Drug: TestDrug",
                to_node="Target: TGT1",
                predicate="BINDS",
                status="CANDIDATE_STRUCTURAL",
                evidence_strength=0.5,
                source_database="ChEMBL",
                evidence_type="STRUCTURAL",
                polarity="UNKNOWN",
                causal_grounding="STRUCTURAL",
            ),
            MechanismHop(
                from_node="Target: TGT1",
                to_node="Pathway: PW1",
                predicate="PARTICIPANT",
                status="STRUCTURAL_EVIDENCE",
                evidence_strength=0.5,
                source_database="Reactome",
                evidence_type="STRUCTURAL",
                polarity="UNKNOWN",
                causal_grounding="STRUCTURAL",
            ),
            MechanismHop(
                from_node="Pathway: PW1",
                to_node="Disease: Dis1",
                predicate="ASSOCIATED_WITH",
                status="CANDIDATE_STRUCTURAL",
                evidence_strength=0.5,
                source_database="Open Targets",
                evidence_type="STRUCTURAL",
                polarity="UNKNOWN",
                causal_grounding="STRUCTURAL",
            ),
        ]
    elif case_type == "CURATED":
        return [
            MechanismHop(
                from_node="Drug: TestDrug",
                to_node="Target: TGT1",
                predicate="INHIBITOR",
                status="DATABASE_SUPPORTED",
                evidence_strength=0.85,
                source_database="ChEMBL",
                evidence_type="CURATED",
                polarity="NEGATIVE",
                causal_grounding="CURATED",
            ),
            MechanismHop(
                from_node="Target: TGT1",
                to_node="Disease: Dis1",
                predicate="ASSOCIATED_WITH",
                status="DATABASE_SUPPORTED",
                evidence_strength=0.80,
                source_database="DrugMechDB",
                evidence_type="CURATED",
                polarity="UNKNOWN",
                causal_grounding="CURATED",
            ),
        ]
    elif case_type == "CAUSAL":
        return [
            MechanismHop(
                from_node="Drug: TestDrug",
                to_node="Target: TGT1",
                predicate="INHIBITOR",
                status="DATABASE_SUPPORTED",
                evidence_strength=0.90,
                source_database="ChEMBL",
                evidence_type="DIRECT",
                polarity="NEGATIVE",
                causal_grounding="DIRECT",
            ),
            MechanismHop(
                from_node="Target: TGT1",
                to_node="Disease: Dis1",
                predicate="DOWNREGULATES",
                status="DATABASE_SUPPORTED",
                evidence_strength=0.80,
                source_database="Open Targets",
                evidence_type="CURATED",
                polarity="NEGATIVE",
                causal_grounding="CURATED",
            ),
        ]
    elif case_type == "LITERATURE_GROUNDED":
        return [
            MechanismHop(
                from_node="Drug: TestDrug",
                to_node="Target: TGT1",
                predicate="INHIBITOR",
                status="LITERATURE_SUPPORTED",
                evidence_strength=0.88,
                source_database="ChEMBL",
                evidence_type="LITERATURE",
                polarity="NEGATIVE",
                causal_grounding="DIRECT",
                supporting_claims=[{"pmid": "12345678", "claim": "TestDrug inhibits TGT1"}],
            ),
            MechanismHop(
                from_node="Target: TGT1",
                to_node="Disease: Dis1",
                predicate="ASSOCIATED_WITH",
                status="LITERATURE_SUPPORTED",
                evidence_strength=0.75,
                source_database="PubMed",
                evidence_type="LITERATURE",
                polarity="NEGATIVE",
                causal_grounding="CURATED",
                supporting_claims=[{"pmid": "12345678", "claim": "TGT1 reduction ameliorates Dis1"}],
            ),
        ]
    elif case_type == "INDEPENDENTLY_VALIDATED":
        return [
            MechanismHop(
                from_node="Drug: TestDrug",
                to_node="Target: TGT1",
                predicate="INHIBITOR",
                status="LITERATURE_SUPPORTED",
                evidence_strength=0.92,
                source_database="ChEMBL",
                evidence_type="LITERATURE",
                polarity="NEGATIVE",
                causal_grounding="DIRECT",
                supporting_claims=[{"pmid": "11111111", "claim": "RCT confirms TGT1 inhibition"}],
            ),
            MechanismHop(
                from_node="Target: TGT1",
                to_node="Disease: Dis1",
                predicate="ASSOCIATED_WITH",
                status="LITERATURE_SUPPORTED",
                evidence_strength=0.85,
                source_database="EuropePMC",
                evidence_type="LITERATURE",
                polarity="NEGATIVE",
                causal_grounding="CURATED",
                supporting_claims=[{"pmid": "22222222", "claim": "Multicenter study confirms therapeutic rescue"}],
            ),
        ]
    return []


def audit_cases():
    cases = ["STRUCTURAL", "CURATED", "CAUSAL", "LITERATURE_GROUNDED", "INDEPENDENTLY_VALIDATED"]
    validator = MechanismValidator()

    print("=" * 90)
    print("CYNTHERA — PHASE 5.11 MECHANISTIC EVIDENCE QUALITY AUDIT")
    print("=" * 90)

    for case_type in cases:
        hops = make_test_hops(case_type)
        cand = CandidateMechanism(
            name=f"Candidate Mechanism ({case_type})",
            support_level="WEAK_SPECULATIVE",
            confidence_score=0.50,
            summary_chain=["Drug", "Target", "Disease"],
            hops=hops,
        )
        pkg = RetrievalPackage(
            hypothesis_id="00000000-0000-0000-0000-000000000000",
            drug=Drug(name="TestDrug", chembl_id="CHEMBL1", identifiers={"chembl": "CHEMBL1"}),
            disease=Disease(name="TestDisease", mesh_id="D1", identifiers={"mesh": "D1"}),
        )

        val_cands = validator.validate(pkg, [cand], claims=[])
        val_cand = val_cands[0]

        print(f"\nCandidate ID:    {val_cand.id}")
        print(f"Name:            {val_cand.name}")
        print(f"Summary Path:    {' -> '.join(val_cand.summary_chain)}")
        print(f"Support Level:   {val_cand.support_level} (Confidence Score: {val_cand.confidence_score:.4f})")
        print(f"Quality Tier:    {val_cand.quality_tier}")
        print("Quality Components Breakdown:")
        for k, v in val_cand.quality_components.items():
            print(f"  - {k:<28}: {v}")
        print(f"Explanation:     {val_cand.rationale}")
        print("-" * 90)


if __name__ == "__main__":
    audit_cases()
