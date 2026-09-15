"""Deep Scientific Validity Audit Script for Apixaban -> Atrial Fibrillation.

Inspects every layer of the retrieval, graph construction, pathfinding,
quality tiering, scoring, and rule evaluation.
"""
from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner
from backend.reasoning.mechanistic.mechanism_validation import MechanismValidator
from backend.reasoning.directional.therapeutic_alignment import (
    TherapeuticAlignmentEngine,
    group_evidence_by_independence,
)
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver


def run_audit():
    print("=" * 100)
    print("CYNTHERA DEEP SCIENTIFIC AUDIT: Apixaban -> Atrial Fibrillation")
    print("=" * 100)

    orchestrator = MasterOrchestrator(
        llm_api_key=os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
        ncbi_api_key=os.environ.get("NCBI_API_KEY"),
        disgenet_api_key=os.environ.get("DISGENET_API_KEY"),
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        hypothesis, package, result = loop.run_until_complete(
            orchestrator.evaluate(
                drug_name="Apixaban",
                disease_name="Atrial fibrillation",
                policy=RetrievalPolicy.STANDARD,
                bypass_cache=True,
            )
        )
    finally:
        loop.close()

    print(f"\n[BASIC INFO]")
    print(f"Hypothesis ID: {hypothesis.id}")
    print(f"Drug:          {hypothesis.drug_name} (ChEMBL: {hypothesis.drug_chembl_id})")
    print(f"Disease:       {hypothesis.disease_name} (MeSH: {hypothesis.disease_mesh_id})")
    print(f"Status:        {result.recommendation_status.value}")
    print(f"SS:            {result.support_assessment.score:.4f} ({result.support_assessment.level})")
    print(f"MS:            {result.mechanistic_assessment.score:.4f} ({result.mechanistic_assessment.level})")
    print(f"RS:            {result.risk_assessment.score:.4f} ({result.risk_assessment.level})")

    # 1. Targets
    print("\n" + "=" * 100)
    print("1. TARGETS IN PACKAGE")
    print("=" * 100)
    for idx, t in enumerate(package.targets, 1):
        print(f"  Target #{idx}: UniProt={t.protein_uniprot} | Mechanism={t.mechanism} | Affinity={t.affinity_nm} nM ({t.affinity_type}) | ERW={t.erw.value} | Source={t.provenance.source_name}")

    # 2. Directional Evidence (104 records)
    print("\n" + "=" * 100)
    print("2. THERAPEUTIC DIRECTION EVIDENCE (104 RECORDS)")
    print("=" * 100)
    dir_ev = package.therapeutic_direction_evidence
    print(f"Total Directional Records: {len(dir_ev)}")

    target_counts = Counter(d.target_canonical_id for d in dir_ev)
    disease_counts = Counter(d.disease_canonical_id for d in dir_ev)
    family_counts = Counter(d.evidence_family.value for d in dir_ev)
    grounding_counts = Counter(d.causal_grounding.value for d in dir_ev)
    source_counts = Counter(d.source for d in dir_ev)
    req_action_counts = Counter(str(d.required_action) for d in dir_ev)

    print(f"  - Unique Targets:        {dict(target_counts)}")
    print(f"  - Unique Diseases:       {dict(disease_counts)}")
    print(f"  - Evidence Families:     {dict(family_counts)}")
    print(f"  - Causal Groundings:     {dict(grounding_counts)}")
    print(f"  - Data Sources:          {dict(source_counts)}")
    print(f"  - Required Actions:      {dict(req_action_counts)}")

    # 3. Independent Groups (24 groups)
    print("\n" + "=" * 100)
    print("3. INDEPENDENCE GROUPS AUDIT")
    print("=" * 100)
    groups = group_evidence_by_independence(dir_ev)
    print(f"Total Independent Groups: {len(groups)}")
    for idx, g in enumerate(groups, 1):
        print(f"  Group #{idx:02d}: ID={g.group_id:<35} | Target={g.target_id:<6} | Desired={g.desired_action.value:<10} | Grounding={g.causal_grounding.value:<10} | Family={g.evidence_family.value:<15} | RecCount={g.member_record_count} | Refs={g.references[:2]}")

    # 4. Literature Records (73 records)
    print("\n" + "=" * 100)
    print("4. LITERATURE / EVIDENCE RECORDS (73 RECORDS)")
    print("=" * 100)
    ev_recs = package.evidence_records
    print(f"Total Evidence Records: {len(ev_recs)}")
    ev_type_counts = Counter(e.evidence_type.value for e in ev_recs)
    ev_source_counts = Counter(e.provenance.source_name for e in ev_recs if hasattr(e, "provenance") and hasattr(e.provenance, "source_name"))
    print(f"  - Evidence Types: {dict(ev_type_counts)}")
    print(f"  - Source Names:   {dict(ev_source_counts)}")

    citations = set(e.citation_key for e in ev_recs)
    print(f"  - Distinct Citation Keys in evidence records: {len(citations)}")
    print(f"  - Sample claims/titles (first 5):")
    for e in ev_recs[:5]:
        title_str = (e.title or "")[:80]
        source_name = getattr(e.provenance, "source_name", "UNKNOWN")
        print(f"    * [{e.evidence_type.value}] {source_name}: {title_str}... (Citation: {e.citation_key})")

    # 5. Graph & Mechanistic Paths
    print("\n" + "=" * 100)
    print("5. MECHANISTIC GRAPH & PATHS AUDIT")
    print("=" * 100)
    reasoner = MultiHopReasoner()
    paths = reasoner.trace_paths(package)
    print(f"Total Mechanistic Paths Discovered: {len(paths)}")

    validator = MechanismValidator()
    raw_candidates = reasoner.discover_candidate_mechanisms(package, paths)
    print(f"Total Raw Candidate Mechanisms Discovered: {len(raw_candidates)}")
    candidates = validator.validate(package, raw_candidates, [])
    print(f"Total Validated Candidate Mechanisms: {len(candidates)}")

    for idx, c in enumerate(candidates, 1):
        print(f"\n  Candidate Mechanism #{idx}:")
        print(f"    - Name:                  {c.name}")
        print(f"    - Quality Tier:          {c.quality_tier}")
        print(f"    - Support Level:         {c.support_level}")
        print(f"    - Confidence Score:      {c.confidence_score:.4f}")
        print(f"    - Discovery Status:      {c.discovery_status}")
        print(f"    - Grounded Edge Count:   {c.grounded_edge_count}")
        print(f"    - Independent Groups:    {c.independent_evidence_groups}")
        print(f"    - Quality Components:    {c.quality_components}")
        print(f"    - Summary Chain:         {' -> '.join(c.summary_chain)}")
        print(f"    - Hops ({len(c.hops)}):")
        for h_idx, h in enumerate(c.hops, 1):
            print(f"        Hop {h_idx}: ({h.from_node}) --[{h.predicate}]--> ({h.to_node}) | Source={h.source_database} | Status={h.status} | Polarity={h.polarity} | Grounding={h.causal_grounding}")

    # 6. Score Components in Reasoning Result
    print("\n" + "=" * 100)
    print("6. MECHANISTIC ASSESSMENT SCORE COMPONENTS IN RESULT")
    print("=" * 100)
    sc = result.mechanistic_assessment.score_components
    for k, v in sc.items():
        print(f"  {k}: {v}")

    # 7. Decision Rule Trace
    print("\n" + "=" * 100)
    print("7. DECISION RULE TRACE")
    print("=" * 100)
    print(f"Final Recommendation: {result.recommendation_status.value}")
    for idx, r in enumerate(result.recommendation_reasons, 1):
        print(f"  Reason {idx}: {r}")


if __name__ == "__main__":
    run_audit()
