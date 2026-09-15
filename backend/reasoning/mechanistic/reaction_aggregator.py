"""Reactome reaction evidence aggregation and deduplication (Phase 5.4 & Phase 5.12).

Two-Tier Deduplication:
  Level 1 — Representation Deduplication:
    Collapses multiple records belonging to the same canonical biological reaction entity:
        (target_canonical_id, reaction_id, pathway_id, species)
    into one canonical evidence unit, preserving all distinct biological roles.

  Level 2 — Study-Level Independence Grouping:
    Clusters records by underlying publication citation (PMID, DOI, NCT, study_id).
    Different PMIDs remain distinct independent evidence units.
    Missing citation provenance is marked UNKNOWN (never assumed independent).

Critical Scientific Invariants:
  1. Structural roles (CATALYST, INPUT, OUTPUT, PARTICIPANT) retain UNKNOWN polarity.
  2. Raw records and their provenance are strictly preserved in AggregatedReactionEvidence.
  3. Duplicate representation rows do NOT inflate independent group counts.
  4. Lower-level reaction independence contributes to candidate mechanism metadata
     without replacing global therapeutic evidence independence.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Sequence

from backend.core.domain.reactome_reaction_evidence import ReactomeReactionEvidence
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.reasoning.directional.reactome_polarity import (
    reactome_role_to_grounding,
    reactome_role_to_polarity,
)

_STRUCTURAL_ROLES = {
    "CATALYST",
    "INPUT",
    "OUTPUT",
    "PARTICIPANT",
    "COMPLEX_COMPONENT",
    "ENTITY_SET_MEMBER",
}

_REGULATORY_ROLES = {
    "POSITIVE_REGULATOR",
    "NEGATIVE_REGULATOR",
    "REQUIREMENT",
}


def extract_reaction_independence_group(rec: ReactomeReactionEvidence) -> str:
    """Extract study-level publication identifier from Reactome record provenance.

    Hierarchy:
      PMID -> DOI -> NCT -> STUDY_ID -> UNKNOWN
    """
    prov = rec.provenance or {}
    if not isinstance(prov, dict):
        return "UNKNOWN"

    # 1. PubMed ID
    for key in ("pmid", "PMID", "pubmed_id", "pubMedId", "pmids"):
        val = prov.get(key)
        if isinstance(val, (list, tuple)) and val:
            val = val[0]
        if val:
            clean = str(val).strip()
            if clean:
                return f"PMID:{clean}"

    # 2. DOI
    for key in ("doi", "DOI", "dois"):
        val = prov.get(key)
        if isinstance(val, (list, tuple)) and val:
            val = val[0]
        if val:
            clean = str(val).strip()
            if clean:
                return f"DOI:{clean}"

    # 3. Clinical trial ID
    for key in ("nct", "NCT", "nct_id", "clinical_trial_id"):
        val = prov.get(key)
        if isinstance(val, (list, tuple)) and val:
            val = val[0]
        if val:
            clean = str(val).strip().upper()
            if clean:
                return f"NCT:{clean}"

    # 4. Explicit study ID
    for key in ("study_id", "studyId"):
        val = prov.get(key)
        if val:
            clean = str(val).strip()
            if clean:
                return f"STUDY:{clean}"

    # Absent provenance -> UNKNOWN (do not fabricate independence)
    return "UNKNOWN"


@dataclass(frozen=True)
class AggregatedReactionEvidence:
    """Aggregated biological reaction record for a target within a pathway.

    Represents a unique (target, reaction, pathway, species) entity, aggregating
    any duplicate participant rows while preserving distinct biological roles and
    complete raw provenance.
    """

    target_canonical_id: str
    reaction_id: str
    pathway_id: str | None
    reaction_name: str
    schema_class: str
    species: str
    compartment: str | None
    disease_context: bool | None

    roles: tuple[str, ...]
    has_structural_role: bool
    has_positive_regulation: bool
    has_negative_regulation: bool

    polarity: MolecularPolarity
    causal_grounding: CausalGrounding

    evidence_count: int
    provenance_sources: tuple[str, ...] = field(default_factory=tuple)
    target_original_id: str = ""

    # Phase 5.12 fields
    canonical_key: str = ""
    representative: ReactomeReactionEvidence | None = None
    raw_record_ids: tuple[str, ...] = field(default_factory=tuple)
    duplicate_count: int = 0
    independence_group: str = "UNKNOWN"
    independence_groups: tuple[str, ...] = field(default_factory=tuple)
    raw_records: tuple[ReactomeReactionEvidence, ...] = field(default_factory=tuple)
    provenance: list[dict[str, Any]] = field(default_factory=list)


def aggregate_reaction_evidence(
    records: Sequence[ReactomeReactionEvidence],
) -> list[AggregatedReactionEvidence]:
    """Aggregate and deduplicate Reactome reaction evidence records.

    Level 1: Representation deduplication collapses identical canonical entities into one.
    Level 2: Independence grouping clusters records by verified study citations.

    Args:
        records: Raw ReactomeReactionEvidence records.

    Returns:
        List of deduplicated AggregatedReactionEvidence objects.
    """
    if not records:
        return []

    # Group by canonical reaction entity key
    grouped: dict[tuple[str, str, str, str], list[ReactomeReactionEvidence]] = defaultdict(list)

    for rec in records:
        key = (
            rec.target_canonical_id.strip().upper(),
            rec.reaction_id.strip(),
            (rec.pathway_id or "").strip(),
            (rec.species or "Homo sapiens").strip(),
        )
        grouped[key].append(rec)

    aggregated: list[AggregatedReactionEvidence] = []

    for key, group in grouped.items():
        sample = group[0]
        target_canonical = sample.target_canonical_id.strip().upper()
        reaction_id = sample.reaction_id.strip()
        pathway_id = sample.pathway_id
        reaction_name = sample.reaction_name
        schema_class = sample.schema_class
        species = sample.species or "Homo sapiens"
        compartment = sample.compartment
        disease_context = sample.disease_context
        canonical_key = f"{target_canonical}:{reaction_id}:{(pathway_id or '')}:{species}"

        # Collect and preserve all distinct normalized roles
        seen_roles: list[str] = []
        for r in group:
            norm_role = (r.target_role or "UNKNOWN").strip().upper()
            if norm_role not in seen_roles:
                seen_roles.append(norm_role)
        roles = tuple(seen_roles)

        has_structural = any(r in _STRUCTURAL_ROLES for r in roles)
        has_pos_reg = "POSITIVE_REGULATOR" in roles
        has_neg_reg = "NEGATIVE_REGULATOR" in roles

        # Determine directional polarity from regulatory roles
        # Invariant 5.12.6: Structural roles alone MUST have UNKNOWN polarity.
        if has_pos_reg and not has_neg_reg:
            polarity = MolecularPolarity.POSITIVE
        elif has_neg_reg and not has_pos_reg:
            polarity = MolecularPolarity.NEGATIVE
        else:
            polarity = MolecularPolarity.UNKNOWN

        # Highest causal grounding among member roles
        _GROUNDING_PRIORITY = {
            CausalGrounding.DIRECT: 4,
            CausalGrounding.CURATED: 3,
            CausalGrounding.INFERRED: 2,
            CausalGrounding.STRUCTURAL: 1,
            CausalGrounding.NONE: 0,
        }
        best_grounding = CausalGrounding.STRUCTURAL
        for r in roles:
            g = reactome_role_to_grounding(r)
            if _GROUNDING_PRIORITY.get(g, 0) > _GROUNDING_PRIORITY.get(best_grounding, 0):
                best_grounding = g

        # Provenance source IDs
        prov_set: set[str] = set()
        raw_ids: list[str] = []
        prov_dicts: list[dict[str, Any]] = []
        indep_groups_set: set[str] = set()

        for idx, r in enumerate(group):
            r_id = r.source_id or f"{r.reaction_id}_{idx}"
            raw_ids.append(r_id)
            if r.source_id:
                prov_set.add(r.source_id)
            elif r.reaction_id:
                prov_set.add(r.reaction_id)
            if r.provenance:
                prov_dicts.append(dict(r.provenance))
            indep = extract_reaction_independence_group(r)
            indep_groups_set.add(indep)

        indep_groups_tuple = tuple(sorted(indep_groups_set))
        # Primary independence group prefers verified citation over UNKNOWN
        primary_indep = next((g for g in indep_groups_tuple if g != "UNKNOWN"), "UNKNOWN")

        aggregated.append(
            AggregatedReactionEvidence(
                target_canonical_id=target_canonical,
                reaction_id=reaction_id,
                pathway_id=pathway_id,
                reaction_name=reaction_name,
                schema_class=schema_class,
                species=species,
                compartment=compartment,
                disease_context=disease_context,
                target_original_id=getattr(sample, "target_original_id", "") or target_canonical,
                roles=roles,
                has_structural_role=has_structural,
                has_positive_regulation=has_pos_reg,
                has_negative_regulation=has_neg_reg,
                polarity=polarity,
                causal_grounding=best_grounding,
                evidence_count=len(group),
                provenance_sources=tuple(sorted(prov_set)),
                canonical_key=canonical_key,
                representative=sample,
                raw_record_ids=tuple(raw_ids),
                duplicate_count=max(0, len(group) - 1),
                independence_group=primary_indep,
                independence_groups=indep_groups_tuple,
                raw_records=tuple(group),
                provenance=prov_dicts,
            )
        )

    return aggregated
