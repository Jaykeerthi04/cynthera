"""CYNTHERA — Phase 5.12.1 Reaction Evidence Aggregation Audit.

Demonstrates and audits:
1. Exact duplicate reaction records collapsed (Level 1 Representation Deduplication).
2. Multiple records sharing the same study (PMID/DOI/NCT) clustered into one independent group (Level 2).
3. Missing citation provenance marked UNKNOWN independence (no inflation).
4. Structural Reactome roles (CATALYST, INPUT, OUTPUT, PARTICIPANT) retaining UNKNOWN polarity.
5. Preserving raw records while avoiding overcounting.
"""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.domain.reactome_reaction_evidence import ReactomeReactionEvidence
from backend.reasoning.mechanistic.reaction_aggregator import (
    aggregate_reaction_evidence,
    AggregatedReactionEvidence,
)


def run_reaction_evidence_audit():
    print("=" * 85)
    print("CYNTHERA — PHASE 5.12 REACTION EVIDENCE AGGREGATION & DEDUPLICATION AUDIT")
    print("=" * 85)

    # Synthetic realistic case with duplication and shared citations
    raw_records = [
        # Reaction 1: R-HSA-1001 (CATALYST role) duplicated across 2 API calls
        ReactomeReactionEvidence(
            target_canonical_id="BRAF",
            target_original_id="P15056",
            reaction_id="R-HSA-1001",
            reaction_name="Phosphorylation of MEK1",
            target_role="CATALYST",
            pathway_id="R-HSA-5683057",
            pathway_name="MAPK signaling pathway",
            source_id="rec_1",
            provenance={"pmid": "12345678", "doi": "10.1016/j.cell.2020.01.001"},
        ),
        ReactomeReactionEvidence(
            target_canonical_id="BRAF",
            target_original_id="P15056",
            reaction_id="R-HSA-1001",
            reaction_name="Phosphorylation of MEK1",
            target_role="CATALYST",
            pathway_id="R-HSA-5683057",
            pathway_name="MAPK signaling pathway",
            source_id="rec_2",
            provenance={"pmid": "12345678"},  # Same PMID, duplicate record
        ),
        # Reaction 1 in secondary pathway context sharing same PMID
        ReactomeReactionEvidence(
            target_canonical_id="BRAF",
            target_original_id="P15056",
            reaction_id="R-HSA-1001",
            reaction_name="Phosphorylation of MEK1",
            target_role="POSITIVE_REGULATOR",
            pathway_id="R-HSA-5683057",
            pathway_name="MAPK signaling pathway",
            source_id="rec_3",
            provenance={"pmid": "12345678"},
        ),
        # Reaction 2: R-HSA-2002 (Different PMID)
        ReactomeReactionEvidence(
            target_canonical_id="BRAF",
            target_original_id="P15056",
            reaction_id="R-HSA-2002",
            reaction_name="Dimerization of RAF kinases",
            target_role="INPUT",
            pathway_id="R-HSA-5683057",
            pathway_name="MAPK signaling pathway",
            source_id="rec_4",
            provenance={"pmid": "87654321"},
        ),
        # Reaction 3: R-HSA-3003 (No provenance -> UNKNOWN independence)
        ReactomeReactionEvidence(
            target_canonical_id="BRAF",
            target_original_id="P15056",
            reaction_id="R-HSA-3003",
            reaction_name="Feedback phosphorylation of BRAF",
            target_role="PARTICIPANT",
            pathway_id="R-HSA-5683057",
            pathway_name="MAPK signaling pathway",
            source_id="rec_5",
            provenance={},  # Missing provenance!
        ),
        ReactomeReactionEvidence(
            target_canonical_id="BRAF",
            target_original_id="P15056",
            reaction_id="R-HSA-3003",
            reaction_name="Feedback phosphorylation of BRAF",
            target_role="PARTICIPANT",
            pathway_id="R-HSA-5683057",
            pathway_name="MAPK signaling pathway",
            source_id="rec_6",
            provenance={},  # Duplicate missing provenance
        ),
    ]

    total_raw = len(raw_records)
    aggregated = aggregate_reaction_evidence(raw_records)
    unique_canonical = len(aggregated)
    duplicate_count = sum(a.evidence_count - 1 for a in aggregated)

    # Calculate independent evidence groups
    indep_groups = set()
    for a in aggregated:
        if hasattr(a, "independence_group") and a.independence_group != "UNKNOWN":
            indep_groups.add(a.independence_group)
        elif hasattr(a, "independence_groups"):
            indep_groups.update(a.independence_groups)

    overcounting_factor = total_raw / max(1, unique_canonical)

    print(f"Total Raw Reaction Records:       {total_raw}")
    print(f"Unique Canonical Reactions:       {unique_canonical}")
    print(f"Duplicate Row Count:              {duplicate_count}")
    print(f"Overcounting Factor:              {overcounting_factor:.2f}x")
    print(f"\nCanonical Reaction Summaries:")
    for i, a in enumerate(aggregated, 1):
        print(f"\n  [{i}] Reaction: {a.reaction_id} ({a.reaction_name})")
        print(f"      Target:            {a.target_canonical_id}")
        print(f"      Pathway:           {a.pathway_id}")
        print(f"      Roles:             {', '.join(a.roles)}")
        print(f"      Polarity:          {a.polarity.value}")
        print(f"      Causal Grounding:  {a.causal_grounding.value}")
        print(f"      Raw Record Count:  {a.evidence_count}")
        if hasattr(a, "independence_group"):
            print(f"      Independence Grp:  {a.independence_group}")
        if hasattr(a, "raw_record_ids"):
            print(f"      Raw Record IDs:    {a.raw_record_ids}")
    print("=" * 85)


if __name__ == "__main__":
    run_reaction_evidence_audit()
