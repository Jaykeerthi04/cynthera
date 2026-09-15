"""CYNTHERA — Phase 5.13.1 Multi-Target Evidence Audit.

Audits how multiple targets are currently handled across representative benchmark cases:
- Primary vs secondary target selection
- Where secondary targets are discarded
- Target-level mechanism quality and directional evidence
- Support / opposition / unresolved target-level breakdown
"""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import uuid
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.value_objects.therapeutic_direction_evidence import (
    TherapeuticDirectionEvidence,
    TherapeuticAction,
    EvidenceFamily,
)
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.reasoning.directional.therapeutic_alignment import (
    TherapeuticAlignmentEngine,
    normalize_drug_action,
)
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver


from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference


def _make_target(drug_chembl: str, uniprot: str, mech: str, affinity: float = 10.0) -> Target:
    return Target(
        drug_chembl_id=drug_chembl,
        protein_uniprot=uniprot,
        affinity_nm=affinity,
        affinity_type="IC50",
        mechanism=mech,
        erw=ERW(value=0.9, rationale="Curated ChEMBL bioactivity"),
        provenance=ProvenanceReference(source_name="ChEMBL", source_version="34", record_id=f"act_{uniprot}"),
    )


def _make_dir_ev(
    target: str,
    disease: str,
    source: str,
    req_action: str,
    family: EvidenceFamily,
    grounding: CausalGrounding,
    ref: str = "",
) -> TherapeuticDirectionEvidence:
    return TherapeuticDirectionEvidence(
        target_canonical_id=target,
        disease_canonical_id=disease,
        source=source,
        required_action=req_action,
        evidence_family=family,
        causal_grounding=grounding,
        underlying_reference=ref,
        provenance={"reference": ref},
    )


def build_case_package(drug_name: str, disease_name: str) -> RetrievalPackage:
    if drug_name == "Furosemide":
        # Multi-target: SLC12A1 (NKCC2 - primary, INHIBITION), SLC12A2 (NKCC1 - secondary, INHIBITION), CA2 (secondary, INHIBITION)
        targets = [
            _make_target("CHEMBL703", "P55011", "INHIBITOR", 10.0),
            _make_target("CHEMBL703", "P55017", "INHIBITOR", 150.0),
            _make_target("CHEMBL703", "P00918", "INHIBITOR", 500.0),
        ]
        proteins = [
            Protein(uniprot_accession="P55011", gene_symbol="SLC12A1", name="Solute carrier family 12 member 1"),
            Protein(uniprot_accession="P55017", gene_symbol="SLC12A2", name="Solute carrier family 12 member 2"),
            Protein(uniprot_accession="P00918", gene_symbol="CA2", name="Carbonic anhydrase 2"),
        ]
        dir_ev = [
            _make_dir_ev("SLC12A1", "Edema", "OpenTargets", "INHIBITION", EvidenceFamily.GENETIC, CausalGrounding.DIRECT, "pmid:11111"),
            _make_dir_ev("SLC12A2", "Edema", "OpenTargets", "INHIBITION", EvidenceFamily.GENETIC, CausalGrounding.INFERRED, "pmid:22222"),
        ]
        return RetrievalPackage(
            hypothesis_id=uuid.uuid4(),
            drug=Drug(name="Furosemide", chembl_id="CHEMBL703", identifiers={"chembl": "CHEMBL703"}),
            disease=Disease(name="Edema", mesh_id="D004487", identifiers={"mesh": "D004487"}),
            targets=targets,
            proteins=proteins,
            therapeutic_direction_evidence=dir_ev,
        )
    elif drug_name == "Norepinephrine":
        # Multi-target with conflict: ADRB1 (primary, ACTIVATOR, but HF needs INHIBITION) vs ADRA1A (ACTIVATOR, vasoconstriction)
        targets = [
            _make_target("CHEMBL1488", "P08588", "AGONIST", 5.0),
            _make_target("CHEMBL1488", "P35348", "AGONIST", 25.0),
        ]
        proteins = [
            Protein(uniprot_accession="P08588", gene_symbol="ADRB1", name="Beta-1 adrenergic receptor"),
            Protein(uniprot_accession="P35348", gene_symbol="ADRA1A", name="Alpha-1A adrenergic receptor"),
        ]
        dir_ev = [
            # Heart failure benefits from Beta-blockers (ADRB1 INHIBITION)
            _make_dir_ev("ADRB1", "Heart failure", "DATTs", "INHIBITION", EvidenceFamily.CURATED_REFERENCE, CausalGrounding.CURATED, "pmid:33333"),
            # ADRA1A activation in acute decompensation might transiently support MAP, but long-term opposes
            _make_dir_ev("ADRA1A", "Heart failure", "Literature", "ACTIVATION", EvidenceFamily.LITERATURE, CausalGrounding.INFERRED, "pmid:44444"),
        ]
        return RetrievalPackage(
            hypothesis_id=uuid.uuid4(),
            drug=Drug(name="Norepinephrine", chembl_id="CHEMBL1488", identifiers={"chembl": "CHEMBL1488"}),
            disease=Disease(name="Heart failure", mesh_id="D006333", identifiers={"mesh": "D006333"}),
            targets=targets,
            proteins=proteins,
            therapeutic_direction_evidence=dir_ev,
        )
    # Default single/multi-target fallback
    return RetrievalPackage(
        hypothesis_id=uuid.uuid4(),
        drug=Drug(name=drug_name, chembl_id="CHEMBL_X", identifiers={"chembl": "CHEMBL_X"}),
        disease=Disease(name=disease_name, mesh_id="D_Y", identifiers={"mesh": "D_Y"}),
    )


def audit_target_handling():
    print("=" * 95)
    print("CYNTHERA — PHASE 5.13.1 MULTI-TARGET HANDLING AUDIT")
    print("=" * 95)

    cases = [
        ("Furosemide", "Edema"),
        ("Norepinephrine", "Heart failure"),
    ]

    engine = TherapeuticAlignmentEngine()

    for drug_name, disease_name in cases:
        print(f"\nEvaluating: {drug_name} → {disease_name}")
        print("-" * 95)

        package = build_case_package(drug_name, disease_name)

        resolver = BiologicalIdentifierResolver(
            proteins=package.proteins,
            genes=package.genes,
            mappings=package.identifier_mappings,
        )

        # 1. Total targets in package
        raw_targets = package.targets
        print(f"  Total ChEMBL Target Records in Package: {len(raw_targets)}")

        # 2. Canonical target mapping
        drug_target_actions: dict[str, tuple[str, str, str]] = {}
        for target in raw_targets:
            uni = (target.protein_uniprot or "").strip().upper()
            res = resolver.resolve(uni, source="ChEMBL")
            sym = res.canonical_symbol or res.canonical_identifier or uni
            action = normalize_drug_action(target.mechanism)
            if sym not in drug_target_actions:
                drug_target_actions[sym] = (action.value, target.mechanism, uni)

        print(f"  Distinct Canonical Targets: {len(drug_target_actions)} -> {list(drug_target_actions.keys())}")

        # 3. Existing Alignment Report (Legacy behavior)
        report = engine.align_package(package, resolver=resolver)

        print(f"  Primary Targets Evaluated:   {len(report.primary_target_alignments)}")
        for pa in report.primary_target_alignments:
            print(f"    - [PRIMARY] {pa.target_id:<12} | Action: {pa.drug_action.value:<10} | Alignment: {pa.alignment.value:<12} | Groups: {len(pa.evidence_groups)} (Supp: {len(pa.supporting_groups)}, Opp: {len(pa.opposing_groups)})")

        print(f"  Secondary Targets Evaluated: {len(report.secondary_target_alignments)}")
        for sa in report.secondary_target_alignments:
            print(f"    - [SECONDARY] {sa.target_id:<10} | Action: {sa.drug_action.value:<10} | Alignment: {sa.alignment.value:<12} | Groups: {len(sa.evidence_groups)}")

        print(f"  Legacy Overall Alignment:    {report.overall_alignment.value}")
        print(f"  Legacy Explanation:          {report.explanation}")

    print("\n" + "=" * 95)
    print("KEY ARCHITECTURAL FINDINGS:")
    print("1. In legacy align_package(), secondary targets are partitioned into secondary_target_alignments")
    print("   and COMPLETELY DISCARDED from overall_alignment synthesis.")
    print("2. If a drug acts on Target A (primary, SUPPORTS) and Target B (primary, OPPOSES),")
    print("   legacy path flags MIXED without considering relative target relevance or evidence depth.")
    print("3. Target-level mechanism quality and independent evidence groups are not synthesized")
    print("   into an explicit multi-target domain object.")
    print("=" * 95)


if __name__ == "__main__":
    audit_target_handling()
