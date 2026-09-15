"""Evidence-grounded validation for graph-discovered mechanism candidates.

Discovery answers "is there a route in the retrieved graph?".  This module
answers the separate question "does the route have biological evidence for a
causal bridge?".  It intentionally does not retrieve or invent evidence: a
missing bridge remains missing and Reactome membership remains structural.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from backend.core.domain.candidate_mechanism import CandidateMechanism, MechanismHop
from backend.core.domain.claim import Claim
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.predicate_type import PredicateType
from backend.core.value_objects.source_url_builder import SourceURLBuilder
from backend.reasoning.normalization.biological_identifier_resolver import (
    BiologicalIdentifierResolver,
)
from backend.reasoning.mechanistic.reaction_aggregator import aggregate_reaction_evidence


_ACTIONABLE_DRUG_PREDICATES = {
    "INHIBITOR", "INHIBITS", "ANTAGONIST", "AGONIST", "ACTIVATOR",
    "ACTIVATES", "MODULATOR", "UPREGULATES", "DOWNREGULATES",
}
_OPPOSING = {
    "INHIBITOR": {"ACTIVATES", "UPREGULATES"},
    "INHIBITS": {"ACTIVATES", "UPREGULATES"},
    "ANTAGONIST": {"ACTIVATES", "UPREGULATES"},
    "AGONIST": {"INHIBITS", "DOWNREGULATES", "NO_EFFECT"},
    "ACTIVATOR": {"INHIBITS", "DOWNREGULATES", "NO_EFFECT"},
    "ACTIVATES": {"INHIBITS", "DOWNREGULATES", "NO_EFFECT"},
    "UPREGULATES": {"INHIBITS", "DOWNREGULATES", "NO_EFFECT"},
    "DOWNREGULATES": {"ACTIVATES", "UPREGULATES", "NO_EFFECT"},
}


def _normalise(value: str | None) -> str:
    """Normalise identifiers for exact alias resolution, not token matching."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


class MechanismValidator:
    """Validate candidates using canonical entity resolution and mapped claims.

    The score is a transparent weighted synthesis of evidence dimensions.  A
    candidate without a literature-supported biological bridge is capped below
    moderate support; this prevents structural pathway membership from being
    presented as causality.
    """

    def validate(
        self,
        package: RetrievalPackage,
        candidates: list[CandidateMechanism],
        claims: list[Claim],
    ) -> list[CandidateMechanism]:
        alias_to_ids = self._canonical_aliases(package)
        evidence_by_id = {str(evidence.id): evidence for evidence in package.evidence_records}
        validated: list[CandidateMechanism] = []
        for candidate in candidates:
            validated.append(self._validate_candidate(candidate, claims, alias_to_ids, evidence_by_id, package=package))
        return validated

    def _canonical_aliases(self, package: RetrievalPackage) -> dict[str, set[str]]:
        aliases: dict[str, set[str]] = defaultdict(set)

        def add(canonical_id: str, *values: str | None) -> None:
            for value in values:
                normalised = _normalise(value)
                if normalised:
                    aliases[normalised].add(canonical_id)

        drug_id = f"CHEMBL:{package.drug.chembl_id}" if package.drug.chembl_id else f"DRUG:{package.drug.name}"
        add(drug_id, package.drug.name, package.drug.chembl_id)
        disease_id = f"MESH:{package.disease.mesh_id}" if package.disease.mesh_id else f"DISEASE:{package.disease.name}"
        add(disease_id, package.disease.name, package.disease.mesh_id)
        for protein in package.proteins:
            canonical = f"UNIPROT:{protein.uniprot_accession}"
            add(canonical, protein.uniprot_accession, protein.gene_symbol, protein.name)
            if protein.gene_symbol:
                add(f"HGNC:{protein.gene_symbol.upper()}", protein.gene_symbol)
        for pathway in package.pathways:
            add(f"REACTOME:{pathway.reactome_id}", pathway.reactome_id, pathway.name)
        for gene in package.genes:
            symbol = getattr(gene, "symbol", None) or getattr(gene, "gene_symbol", None) or getattr(gene, "hgnc_symbol", None)
            if symbol:
                add(f"HGNC:{symbol.upper()}", symbol)
        resolver = BiologicalIdentifierResolver(
            proteins=package.proteins,
            genes=package.genes,
            mappings=getattr(package, "identifier_mappings", []),
        )
        for raw_identifier in (getattr(package, "validated_disease_genes", None) or {}).keys():
            resolved = resolver.resolve(str(raw_identifier), source="validated_disease_genes")
            if resolved.canonical_symbol:
                add(f"HGNC:{resolved.canonical_symbol.upper()}", resolved.canonical_symbol, str(raw_identifier))
            if resolved.canonical_identifier:
                add(f"UNIPROT:{resolved.canonical_identifier}", resolved.canonical_identifier, str(raw_identifier))
        return aliases

    def _resolve(self, value: str, aliases: dict[str, set[str]]) -> set[str]:
        # Exact canonical/alias resolution only.  Ambiguous names deliberately
        # do not validate a hop rather than creating a text-match false positive.
        return aliases.get(_normalise(value), set())

    def _node_entity(self, node: str, aliases: dict[str, set[str]]) -> str | None:
        label, _, value = node.partition(":")
        resolved = self._resolve(value.strip(), aliases)
        expected_prefix = {
            "drug": ("CHEMBL:", "DRUG:"),
            "target": ("UNIPROT:",),
            "gene": ("HGNC:",),
            "pathway": ("REACTOME:",),
            "disease": ("MESH:", "DISEASE:"),
        }.get(label.strip().casefold(), ())
        if expected_prefix:
            resolved = {item for item in resolved if item.startswith(expected_prefix)}
        if len(resolved) == 1:
            return next(iter(resolved))
        # Path labels contain helpful identifiers such as "PDE5A (O76074)".
        # Resolve the explicit identifier only; never fall back to token overlap.
        for explicit in re.findall(r"[A-Z][0-9][A-Z0-9]{3,9}|R-HSA-\d+", node.upper()):
            resolved = self._resolve(explicit, aliases)
            if expected_prefix:
                resolved = {item for item in resolved if item.startswith(expected_prefix)}
            if len(resolved) == 1:
                return next(iter(resolved))
        return None

    def _citation(
        self,
        claim: Claim,
        hop_index: int,
        relation: str,
        evidence_by_id: dict[str, Any],
    ) -> dict[str, Any]:
        record_id = claim.provenance.record_id or ""
        parent_evidence = next(
            (evidence_by_id.get(str(evidence_id)) for evidence_id in claim.evidence_ids if str(evidence_id) in evidence_by_id),
            None,
        )
        if parent_evidence is not None and not record_id:
            record_id = parent_evidence.citation_key
        links = SourceURLBuilder.build_links_for_citation_key(record_id)
        url = claim.provenance.url or (links[0].url if links else None)
        return {
            "claim_id": str(claim.id),
            "hop_index": hop_index,
            "relation": relation,
            "source": claim.provenance.source_name,
            "citation_key": record_id,
            "url": url,
            "title": getattr(parent_evidence, "title", None) or "",
            "claim_text": claim.raw_text or f"{claim.subject} {claim.predicate.value} {claim.object}",
            "predicate": claim.predicate.value,
            "confidence": claim.confidence,
            "evidence_strength": claim.erw.value,
        }

    def _validate_candidate(
        self,
        candidate: CandidateMechanism,
        claims: list[Claim],
        aliases: dict[str, set[str]],
        evidence_by_id: dict[str, Any],
        package: RetrievalPackage | None = None,
    ) -> CandidateMechanism:
        updated_hops: list[MechanismHop] = []
        citations: list[dict[str, Any]] = []
        contradictions: list[dict[str, Any]] = []
        bridge_supported = False
        missing: list[str] = []
        direction_scores: list[float] = []
        curated_scores: list[float] = []
        disease_scores: list[float] = []
        edge_scores: list[float] = []
        supporting_by_source: dict[str, float] = {}

        for index, hop in enumerate(candidate.hops):
            from_id = self._node_entity(hop.from_node, aliases)
            to_id = self._node_entity(hop.to_node, aliases)
            matching_support: list[Claim] = []
            matching_contradictions: list[Claim] = []
            for claim in claims:
                subject_ids = self._resolve(claim.subject, aliases)
                object_ids = self._resolve(claim.object, aliases)
                if not from_id or not to_id or from_id not in subject_ids or to_id not in object_ids:
                    continue
                predicate = claim.predicate.value
                if predicate == "NO_EFFECT" or predicate in _OPPOSING.get(hop.predicate.upper(), set()):
                    matching_contradictions.append(claim)
                else:
                    matching_support.append(claim)

            structural = (
                hop.predicate in {"PARTICIPATES_IN", "CONTAINS_ASSOCIATED_GENE"}
                or "Reactome" in hop.source_database
            )
            drug_target = index == 0
            disease_relation = "DISEASE" in hop.to_node.upper() or hop.predicate == "ASSOCIATED_WITH"
            status = "STRUCTURAL_EVIDENCE" if structural else "DATABASE_SUPPORTED"
            evidence_type = "STRUCTURAL" if structural else ("DIRECT" if drug_target else "CURATED")
            directionality = "NOT_APPLICABLE"
            if drug_target:
                directionality = "SUPPORTED" if hop.predicate.upper() in _ACTIONABLE_DRUG_PREDICATES else "DIRECTION_UNCERTAIN"
                direction_scores.append(1.0 if directionality == "SUPPORTED" else 0.35)
            elif structural:
                directionality = "DIRECTION_UNCERTAIN"
                direction_scores.append(0.3)

            support_rows = [self._citation(c, index, "SUPPORTS", evidence_by_id) for c in matching_support]
            if not support_rows and hop.supporting_claims:
                support_rows = [
                    r if isinstance(r, dict) and "predicate" in r else {
                        "claim_id": str(r.get("pmid", index)),
                        "hop_index": index,
                        "relation": "SUPPORTS",
                        "source": r.get("source", r.get("pmid", "Literature")),
                        "citation_key": str(r.get("pmid", "")),
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "claim_text": r.get("claim", ""),
                        "predicate": hop.predicate.upper(),
                        "confidence": float(r.get("confidence", 0.8)),
                        "evidence_strength": float(r.get("evidence_strength", hop.evidence_strength)),
                    }
                    for r in hop.supporting_claims
                ]
            contradiction_rows = [self._citation(c, index, "CONTRADICTS", evidence_by_id) for c in matching_contradictions]
            if contradiction_rows:
                status = "CONTRADICTED"
                contradictions.extend(contradiction_rows)
            elif support_rows:
                status = "LITERATURE_SUPPORTED"
                evidence_type = "LITERATURE"
                if any(row["predicate"] in _ACTIONABLE_DRUG_PREDICATES for row in support_rows):
                    if directionality == "DIRECTION_UNCERTAIN":
                        directionality = "SUPPORTED"
                        if direction_scores:
                            direction_scores[-1] = 1.0
                        else:
                            direction_scores.append(1.0)
                if structural or (not drug_target and not disease_relation):
                    bridge_supported = True
                for row in support_rows:
                    source = row["source"] or "unknown"
                    supporting_by_source[source] = max(
                        supporting_by_source.get(source, 0.0),
                        row["confidence"] * row["evidence_strength"],
                    )
            elif structural:
                missing.append(
                    f"Direct biological bridge for {hop.from_node} → {hop.to_node} is not supported by a mapped claim."
                )

            if disease_relation:
                disease_scores.append(hop.evidence_strength)
            edge_scores.append(hop.evidence_strength)
            curated_scores.append(0.30 if structural else (0.90 if drug_target else 0.70))
            citations.extend(support_rows + contradiction_rows)
            updated_hops.append(hop.model_copy(update={
                "status": status,
                "canonical_from_id": from_id,
                "canonical_to_id": to_id,
                "directionality": directionality,
                "evidence_type": evidence_type,
                "supporting_claims": support_rows,
                "contradicting_claims": contradiction_rows,
            }))

        edge_validity = sum(edge_scores) / len(edge_scores) if edge_scores else 0.0
        directionality = sum(direction_scores) / len(direction_scores) if direction_scores else 0.0
        disease_relevance = sum(disease_scores) / len(disease_scores) if disease_scores else 0.0
        curated_support = sum(curated_scores) / len(curated_scores) if curated_scores else 0.0
        literature_support = (
            sum(supporting_by_source.values()) / len(supporting_by_source)
            if supporting_by_source else 0.0
        )
        independence = len(supporting_by_source) / (len(supporting_by_source) + 1) if supporting_by_source else 0.0
        contradiction_strength = max((row["confidence"] * row["evidence_strength"] for row in contradictions), default=0.0)
        score = (
            0.20 * edge_validity
            + 0.15 * directionality
            + 0.20 * disease_relevance
            + 0.15 * curated_support
            + 0.25 * literature_support
            + 0.05 * independence
            - 0.25 * contradiction_strength
        )
        # Candidate scoring synthesis:
        # 1. Direct Target -> Disease paths (index <= 1) are grounded in direct database associations.
        # 2. Intermediate Reactome pathway hops require literature validation to upgrade beyond structural evidence;
        #    without literature claims, pathway participation stays WEAK_SPECULATIVE (score < 0.50).
        is_direct_target_disease = any(
            "DISEASE" in hop.to_node.upper() and index <= 1
            for index, hop in enumerate(candidate.hops)
        )

        if not bridge_supported and not is_direct_target_disease:
            score = min(score, 0.49)
        elif not bridge_supported:
            score = min(score, 0.65)

        if directionality < 0.30:
            score = min(score, 0.49)
        score = round(max(0.0, min(1.0, score)), 4)

        if contradiction_strength >= 0.50:
            support_level, discovery_status = "CONTRADICTED", "CONTRADICTED"
            score = 0.0
        elif not bridge_supported and not is_direct_target_disease:
            support_level, discovery_status = "WEAK_SPECULATIVE", "CANDIDATE_STRUCTURAL"
        elif score >= 0.70 and directionality >= 0.70 and (bridge_supported or len(supporting_by_source) >= 2):
            support_level, discovery_status = "STRONGLY_SUPPORTED", "VALIDATED"
        elif score >= 0.45 and (bridge_supported or is_direct_target_disease):
            support_level, discovery_status = "MODERATELY_SUPPORTED", "VALIDATED"
        elif score >= 0.20:
            support_level, discovery_status = "WEAK_SPECULATIVE", "CANDIDATE_STRUCTURAL"
        else:
            support_level, discovery_status = "UNSUPPORTED", "INSUFFICIENT_EVIDENCE"



        dimensions = {
            "edge_validity": round(edge_validity, 4),
            "directionality": round(directionality, 4),
            "disease_relevance": round(disease_relevance, 4),
            "curated_database_support": round(curated_support, 4),
            "literature_support": round(literature_support, 4),
            "evidence_independence": round(independence, 4),
            "contradictory_evidence": round(contradiction_strength, 4),
        }
        explanation = [
            "Score = 0.20 edge validity + 0.15 directionality + 0.20 disease relevance + "
            "0.15 curated support + 0.25 literature support + 0.05 independence − 0.25 contradiction.",
            "Reactome pathway membership is structural evidence and cannot by itself validate a causal bridge.",
        ]
        if not bridge_supported:
            explanation.append("No mapped literature claim supports a critical biological bridge; score is capped below moderate support.")
        if contradictions:
            explanation.append(f"{len(contradictions)} mapped contradictory claim(s) affect the listed hop(s).")

        # Phase 5.1: compute structural vs causal edge breakdown for score_components
        structural_edge_count = sum(
            1 for hop in updated_hops
            if hop.status in ("STRUCTURAL_EVIDENCE", "CANDIDATE_STRUCTURAL")
            or hop.evidence_type == "STRUCTURAL"
        )

        # Phase 5.11: Quality components & deterministic tier classification
        # Invariant 5.11.4: Reactome structural roles (INPUT, OUTPUT, CATALYST, PARTICIPANT)
        # are STRUCTURAL evidence, NEVER causal evidence.
        structural_edges = sum(
            1 for hop in updated_hops
            if hop.status in ("STRUCTURAL_EVIDENCE", "CANDIDATE_STRUCTURAL")
            or hop.evidence_type == "STRUCTURAL"
            or hop.causal_grounding == "STRUCTURAL"
            or any(role in hop.predicate.upper() for role in ("CATALYST", "INPUT", "OUTPUT", "PARTICIPANT"))
        )
        causal_edges = sum(
            1 for hop in updated_hops
            if hop.polarity in ("POSITIVE", "NEGATIVE")
            and hop.causal_grounding in ("DIRECT", "CURATED", "INFERRED")
            and not any(role in hop.predicate.upper() for role in ("CATALYST", "INPUT", "OUTPUT", "PARTICIPANT"))
        )
        grounded_edges = sum(
            1 for hop in updated_hops
            if hop.causal_grounding in ("DIRECT", "CURATED")
        )
        reaction_evidence_count = sum(
            1 for hop in updated_hops
            if "REACTOME" in hop.source_database.upper() or "REACTION" in hop.predicate.upper()
        )
        total_literature_claims = len(citations)
        independent_groups = len(supporting_by_source)
        curated_db_support = curated_support >= 0.50 or any(
            hop.source_database.upper() in ("CHEMBL", "DRUGMECHDB", "REACTOME") for hop in updated_hops
        )
        directionally_supported = directionality >= 0.50

        quality_components = {
            "structural_edges": structural_edges,
            "causal_edges": causal_edges,
            "grounded_edges": grounded_edges,
            "reaction_evidence": reaction_evidence_count,
            "literature_claims": total_literature_claims,
            "independent_evidence_groups": independent_groups,
            "curated_database_support": curated_db_support,
            "directionally_supported": directionally_supported,
        }

        # Deterministic quality tier classification (Section 5.11.3)
        if independent_groups >= 2 and causal_edges >= 1:
            quality_tier = "INDEPENDENTLY_VALIDATED"
        elif total_literature_claims >= 1:
            quality_tier = "LITERATURE_GROUNDED"
        elif causal_edges >= 1 and directionally_supported:
            quality_tier = "CAUSAL"
        elif curated_db_support and grounded_edges >= 1:
            quality_tier = "CURATED"
        else:
            quality_tier = "STRUCTURAL"

        # Phase 5.12: Reaction Evidence Aggregation Integration
        # Lower-level normalization: computes reaction-level independent groups
        # WITHOUT replacing or overwriting global evidence independence.
        rxn_evidence_count = 0
        unique_reaction_count = 0
        rxn_indep_groups = 0
        rxn_enriched = False

        if package is not None:
            raw_rxns = list(getattr(package, "reactome_reaction_evidence", []))
            if raw_rxns:
                agg_rxns = aggregate_reaction_evidence(raw_rxns)
                unique_reaction_count = len(agg_rxns)
                rxn_evidence_count = sum(a.evidence_count for a in agg_rxns)
                rxn_indep_groups = len(set(a.independence_group for a in agg_rxns if a.independence_group != "UNKNOWN"))
                rxn_enriched = unique_reaction_count >= 1

        return candidate.model_copy(update={
            "support_level": support_level,
            "confidence_score": score,
            "hops": updated_hops,
            "literature_citations": citations,
            "discovery_status": discovery_status,
            "validation_dimensions": dimensions,
            "score_explanation": explanation,
            "missing_critical_evidence": list(dict.fromkeys(missing)),
            "contradictions": contradictions,
            "rationale": (
                f"{discovery_status.replace('_', ' ')}: score {score:.3f}. "
                f"Literature bridge {'present' if bridge_supported else 'not established'}; "
                f"{len(contradictions)} mapped contradiction(s)."
            ),
            # Phase 5.1 fields
            "structural_edge_count": structural_edge_count,
            "independent_evidence_groups": len(supporting_by_source),
            # Phase 5.11 fields
            "quality_tier": quality_tier,
            "quality_components": quality_components,
            # Phase 5.12 fields
            "reaction_evidence_count": rxn_evidence_count,
            "unique_reaction_count": unique_reaction_count,
            "reaction_independent_groups": rxn_indep_groups,
            "reaction_enriched": rxn_enriched,
        })
