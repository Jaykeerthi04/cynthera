"""Tests for Phase 5.4: Reactome reaction evidence aggregation and deduplication."""
from __future__ import annotations

import pytest

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.pathway import Pathway
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.reactome_reaction_evidence import ReactomeReactionEvidence
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.reasoning.mechanistic.reaction_aggregator import (
    AggregatedReactionEvidence,
    aggregate_reaction_evidence,
)
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder


def _make_rev(
    target_canonical_id: str = "MMP1",
    target_original_id: str = "P03956",
    reaction_id: str = "R-HSA-12345",
    reaction_name: str = "Cleavage of collagen",
    target_role: str = "CATALYST",
    pathway_id: str = "R-HSA-99999",
    species: str = "Homo sapiens",
    source_id: str = "rec_001",
) -> ReactomeReactionEvidence:
    return ReactomeReactionEvidence(
        target_canonical_id=target_canonical_id,
        target_original_id=target_original_id,
        reaction_id=reaction_id,
        reaction_name=reaction_name,
        target_role=target_role,
        pathway_id=pathway_id,
        pathway_name="Collagen degradation",
        species=species,
        source_id=source_id,
    )


class TestReactionAggregation:
    def test_duplicate_raw_rows_collapsed(self):
        """Duplicate raw records with same entity key and role are collapsed into one aggregate."""
        r1 = _make_rev(target_role="CATALYST", source_id="rec_1")
        r2 = _make_rev(target_role="CATALYST", source_id="rec_2")
        r3 = _make_rev(target_role="CATALYST", source_id="rec_3")

        aggregated = aggregate_reaction_evidence([r1, r2, r3])
        assert len(aggregated) == 1
        agg = aggregated[0]
        assert agg.target_canonical_id == "MMP1"
        assert agg.reaction_id == "R-HSA-12345"
        assert agg.roles == ("CATALYST",)
        assert agg.evidence_count == 3
        assert agg.has_structural_role is True
        assert agg.has_positive_regulation is False
        assert agg.polarity == MolecularPolarity.UNKNOWN
        assert agg.causal_grounding == CausalGrounding.STRUCTURAL
        assert sorted(agg.provenance_sources) == ["rec_1", "rec_2", "rec_3"]

    def test_multi_role_preserved_in_single_entity(self):
        """Different biological roles in the same reaction are preserved in a single reaction aggregate."""
        r_cat = _make_rev(target_role="CATALYST", source_id="rec_cat")
        r_reg = _make_rev(target_role="POSITIVE_REGULATOR", source_id="rec_reg")

        aggregated = aggregate_reaction_evidence([r_cat, r_reg])
        assert len(aggregated) == 1
        agg = aggregated[0]
        assert set(agg.roles) == {"CATALYST", "POSITIVE_REGULATOR"}
        assert agg.has_structural_role is True
        assert agg.has_positive_regulation is True
        assert agg.has_negative_regulation is False
        assert agg.polarity == MolecularPolarity.POSITIVE
        assert agg.causal_grounding == CausalGrounding.CURATED
        assert agg.evidence_count == 2

    def test_structural_role_has_unknown_polarity(self):
        """Structural roles (INPUT, OUTPUT, CATALYST, PARTICIPANT) yield UNKNOWN polarity."""
        for role in ["INPUT", "OUTPUT", "CATALYST", "PARTICIPANT", "COMPLEX_COMPONENT", "ENTITY_SET_MEMBER"]:
            rec = _make_rev(target_role=role)
            agg = aggregate_reaction_evidence([rec])[0]
            assert agg.has_structural_role is True
            assert agg.polarity == MolecularPolarity.UNKNOWN
            assert agg.causal_grounding == CausalGrounding.STRUCTURAL

    def test_positive_regulator_yields_positive_polarity(self):
        """POSITIVE_REGULATOR role yields POSITIVE polarity and CURATED grounding."""
        rec = _make_rev(target_role="POSITIVE_REGULATOR")
        agg = aggregate_reaction_evidence([rec])[0]
        assert agg.has_positive_regulation is True
        assert agg.polarity == MolecularPolarity.POSITIVE
        assert agg.causal_grounding == CausalGrounding.CURATED

    def test_negative_regulator_yields_negative_polarity(self):
        """NEGATIVE_REGULATOR role yields NEGATIVE polarity and CURATED grounding."""
        rec = _make_rev(target_role="NEGATIVE_REGULATOR")
        agg = aggregate_reaction_evidence([rec])[0]
        assert agg.has_negative_regulation is True
        assert agg.polarity == MolecularPolarity.NEGATIVE
        assert agg.causal_grounding == CausalGrounding.CURATED

    def test_conflicting_regulatory_roles_yield_unknown_polarity(self):
        """If a target is annotated with both positive and negative regulation in one reaction, polarity is UNKNOWN."""
        r_pos = _make_rev(target_role="POSITIVE_REGULATOR")
        r_neg = _make_rev(target_role="NEGATIVE_REGULATOR")
        agg = aggregate_reaction_evidence([r_pos, r_neg])[0]
        assert agg.has_positive_regulation is True
        assert agg.has_negative_regulation is True
        assert agg.polarity == MolecularPolarity.UNKNOWN

    def test_distinct_reactions_remain_separate(self):
        """Different reactions for the same target produce distinct AggregatedReactionEvidence items."""
        r1 = _make_rev(reaction_id="R-HSA-101")
        r2 = _make_rev(reaction_id="R-HSA-102")
        aggregated = aggregate_reaction_evidence([r1, r2])
        assert len(aggregated) == 2
        rxn_ids = {a.reaction_id for a in aggregated}
        assert rxn_ids == {"R-HSA-101", "R-HSA-102"}

    def test_distinct_pathways_remain_separate(self):
        """Same reaction occurring in distinct pathways produces separate pathway-context entities."""
        r1 = _make_rev(pathway_id="R-HSA-901")
        r2 = _make_rev(pathway_id="R-HSA-902")
        aggregated = aggregate_reaction_evidence([r1, r2])
        assert len(aggregated) == 2

    def test_empty_input_returns_empty_list(self):
        """Empty input yields empty list."""
        assert aggregate_reaction_evidence([]) == []

    def test_graph_builder_deduplicates_reaction_nodes(self):
        """EvidenceGraphBuilder creates a single REACTION node even when provided 10 duplicate rows."""
        import uuid
        from backend.core.value_objects.erw import ERW
        from backend.core.value_objects.provenance import ProvenanceReference

        drug = Drug(id=uuid.uuid4(), name="Doxycycline", chembl_id="CHEMBL1433", identifiers={"chembl": "CHEMBL1433"})
        disease = Disease(id=uuid.uuid4(), name="Heart failure", mesh_id="D006333", identifiers={"mesh": "D006333"})
        target = Target(
            drug_chembl_id="CHEMBL1433",
            protein_uniprot="P03956",
            affinity_nm=15.0,
            affinity_type="IC50",
            mechanism="INHIBITOR",
            erw=ERW.from_base(0.9),
            provenance=ProvenanceReference(
                source_name="ChEMBL",
                source_version="33",
                record_id="act_1",
                url="https://chembl.org",
            ),
        )
        protein = Protein(name="Interstitial collagenase", uniprot_accession="P03956", gene_symbol="MMP1", is_reviewed=True)
        pathway = Pathway(reactome_id="R-HSA-99999", name="Collagen degradation", participant_uniprot_ids=["P03956"])

        # 5 identical raw reaction records
        rxn_rows = [_make_rev(target_role="CATALYST", source_id=f"row_{i}") for i in range(5)]

        pkg = RetrievalPackage(
            hypothesis_id=uuid.uuid4(),
            drug=drug,
            disease=disease,
            targets=[target],
            proteins=[protein],
            pathways=[pathway],
            reactome_reaction_evidence=rxn_rows,
        )

        builder = EvidenceGraphBuilder()
        graph, _ = builder.build(pkg)

        rxn_nodes = [n for n in graph.nodes.values() if n.label == "REACTION"]
        assert len(rxn_nodes) == 1
        assert rxn_nodes[0].meta["reaction_id"] == "R-HSA-12345"
        assert rxn_nodes[0].meta["evidence_count"] == 5
