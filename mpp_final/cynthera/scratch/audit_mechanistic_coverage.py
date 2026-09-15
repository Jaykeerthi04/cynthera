"""CYNTHERA — Phase 5.9 Mechanistic Coverage & Zero-Score Audit.

DIAGNOSTIC AUDIT ONLY:
- Does NOT modify production reasoning logic.
- Does NOT change scoring formulas or benchmark labels.
- Analyzes 20+ cases to determine whether MS=0 results are scientifically justified
  or caused by retrieval, graph construction, pathfinding, or validation failures.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from dotenv import load_dotenv
load_dotenv()

from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.reasoning.mechanistic.evidence_graph import (
    EvidenceGraph,
    EvidenceGraphBuilder,
    clean_uniprot,
    is_human_protein,
    _MAX_TARGETS,
    _MAX_PATHWAYS_PER_TARGET,
    _MAX_HOPS,
    _MIN_PATH_CONFIDENCE,
)
from backend.reasoning.mechanistic.multi_hop_reasoner import (
    MultiHopReasoner,
    PathFinder,
    PathScorer,
)
from backend.reasoning.mechanistic.mechanism_validation import MechanismValidator

# Suppress overly verbose logging during diagnostic audit
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("audit_mechanistic_coverage")

# Output cache file for checkpointing
CACHE_FILE = root_dir / "scratch" / "mechanistic_coverage_cache.json"

AUDIT_CASES = [
    # 1-10: Mandated core test cases
    ("Ivermectin", "Heart failure", "Anthelmintic, invertebrate GluCl channels"),
    ("Aspirin", "Colorectal Cancer", "NSAID, PTGS2 inhibition"),
    ("Oseltamivir", "Influenza", "Antiviral, viral neuraminidase"),
    ("Furosemide", "Edema", "Diuretic, SLC12A1 inhibition"),
    ("Testosterone", "Prostate Cancer", "Androgen agonist, AR counterfactual"),
    ("Dapagliflozin", "Heart failure", "SGLT2 inhibitor, SLC5A2"),
    ("Propranolol", "Infantile Hemangioma", "Beta-blocker, ADRB1/ADRB2"),
    ("Methotrexate", "Rheumatoid Arthritis", "Antifolate DMARD, DHFR/AICARFT"),
    ("Tocilizumab", "COVID-19", "Biologic mAb, IL6R"),
    ("Gabapentin", "Postherpetic neuralgia", "Anticonvulsant/analgesic, CACNA2D1"),

    # 11-23: Additional balanced diagnostic cases
    ("Albuterol", "Hypertension", "Beta-2 agonist counterfactual"),
    ("Pilocarpine", "Asthma", "Muscarinic agonist counterfactual"),
    ("Isoproterenol", "Infantile Hemangioma", "Beta-agonist counterfactual"),
    ("Norepinephrine", "Heart failure", "Inotropic counterfactual"),
    ("Thalidomide", "Multiple Myeloma", "Immunomodulator, CRBN"),
    ("Thalidomide", "Hypertension", "Uncertain control"),
    ("Nicotine", "Hypertension", "Nicotinic agonist, balanced conflict"),
    ("Atorvastatin", "Major Depressive Disorder", "Statin, uncertain psychiatric"),
    ("Sildenafil", "Pulmonary Arterial Hypertension", "PDE5 inhibitor, PDE5A"),
    ("Metformin", "Polycystic Ovary Syndrome", "Biguanide, AMPK pathway"),
    ("Doxycycline", "Heart failure", "Antibiotic/MMP inhibitor, MMP2/MMP9"),
    ("Digoxin", "Heart failure", "Cardiac glycoside, ATP1A1"),
    ("Warfarin", "Atrial Fibrillation", "Anticoagulant, VKORC1"),
]


def is_human_target(target: Any, proteins: list[Any]) -> bool:
    """Check if target organism is human."""
    org = getattr(target, "organism", None)
    if org:
        org_lower = org.strip().lower()
        if any(w in org_lower for w in ("human", "homo sapiens")):
            return True
        if any(w in org_lower for w in ("bacteria", "virus", "nematode", "parasite", "helminth", "worm", "yeast", "rattus", "mouse")):
            return False

    # Check matching protein
    uniprot = clean_uniprot(getattr(target, "uniprot_id", None))
    for p in proteins:
        if clean_uniprot(getattr(p, "uniprot_accession", None)) == uniprot:
            return is_human_protein(p)
    return True


def audit_case_stages(drug: str, disease: str, package: Any, result: Any) -> dict[str, Any]:
    """Perform stage-by-stage mechanistic audit on a retrieved package and result."""
    targets_raw = list(package.targets)
    human_targets = [t for t in targets_raw if is_human_target(t, package.proteins)]
    non_human_targets = [t for t in targets_raw if not is_human_target(t, package.proteins)]

    canonical_targets = list({clean_uniprot(t.uniprot_id) for t in targets_raw if getattr(t, "uniprot_id", None)})

    pathways_raw = list(package.pathways)
    reactions_raw = getattr(package, "reactome_reaction_evidence", []) or []

    # Reconstruct graph locally to inspect exact edge distribution
    builder = EvidenceGraphBuilder()
    graph, resolver = builder.build(package)

    drug_id = f"DRUG:{package.drug.name}"
    disease_id = f"DISEASE:{package.disease.name}"

    drug_node_exists = drug_id in graph.nodes
    disease_node_exists = disease_id in graph.nodes

    # Count edge types
    target_rxn_edges = [e for e in graph.edges if e.source_id.startswith("TARGET:") and e.target_id.startswith("REACTION:")]
    rxn_pw_edges = [e for e in graph.edges if e.source_id.startswith("REACTION:") and e.target_id.startswith("PATHWAY:")]
    target_pw_edges = [e for e in graph.edges if e.source_id.startswith("TARGET:") and e.target_id.startswith("PATHWAY:")]
    pw_gene_edges = [e for e in graph.edges if e.source_id.startswith("PATHWAY:") and e.target_id.startswith("GENE:")]
    target_gene_edges = [e for e in graph.edges if e.source_id.startswith("TARGET:") and e.target_id.startswith("GENE:")]
    gene_disease_edges = [e for e in graph.edges if e.source_id.startswith("GENE:") and e.target_id.startswith("DISEASE:")]

    # PathFinder tracing
    path_finder = PathFinder()
    path_scorer = PathScorer()
    raw_paths = []
    scored_paths = []
    pathfinder_rejection_reason = "NONE"

    if not drug_node_exists:
        pathfinder_rejection_reason = "DRUG_NODE_MISSING"
    elif not disease_node_exists:
        pathfinder_rejection_reason = "DISEASE_NODE_MISSING"
    elif len(gene_disease_edges) == 0:
        pathfinder_rejection_reason = "NO_GENE_DISEASE_EDGES"
    elif len(target_rxn_edges) == 0 and len(target_pw_edges) == 0 and len(target_gene_edges) == 0:
        pathfinder_rejection_reason = "TARGETS_DISCONNECTED"
    else:
        raw_paths = path_finder.find(graph, drug_id, disease_id)
        if not raw_paths:
            pathfinder_rejection_reason = "NO_CONNECTED_SIMPLE_PATH"
        else:
            for p in raw_paths:
                conf = path_scorer.score(p)
                if conf >= _MIN_PATH_CONFIDENCE:
                    p.confidence = conf
                    scored_paths.append(p)
            if raw_paths and not scored_paths:
                pathfinder_rejection_reason = "ALL_PATHS_BELOW_CONFIDENCE_THRESHOLD"

    # Candidates
    reasoner = MultiHopReasoner()
    candidates = reasoner.discover_candidate_mechanisms(package, scored_paths)

    # Validation
    validator = MechanismValidator()
    all_claims = getattr(package, "claims", []) or []
    validated_cands = validator.validate(package, candidates, all_claims)

    validation_rejection_reasons = []
    for c in validated_cands:
        if c.support_level == "UNSUPPORTED":
            dim = c.validation_dimensions
            if dim.get("literature_support", 0.0) == 0.0:
                validation_rejection_reasons.append(f"Candidate '{c.name}': zero literature support (score={c.confidence_score:.3f} < 0.20)")
            else:
                validation_rejection_reasons.append(f"Candidate '{c.name}': low overall validity score ({c.confidence_score:.3f} < 0.20)")
        elif c.support_level == "CONTRADICTED":
            validation_rejection_reasons.append(f"Candidate '{c.name}': contradiction detected ({c.rationale})")

    # Final MS from result
    ma = result.mechanistic_assessment
    ms = getattr(ma, "score", 0.0)
    level = getattr(ma, "level", "NONE")
    sc = getattr(ma, "score_components", {}) or {}
    quality = sc.get("support_level") or getattr(ma, "literature_grounding_level", "UNKNOWN")

    # Classify Root Cause
    root_cause = "NON_ZERO"
    if ms == 0.0:
        if len(targets_raw) == 0:
            root_cause = "ZERO_TARGET"
        elif len(human_targets) == 0:
            root_cause = "NON_HUMAN_TARGET"
        elif len(pathways_raw) == 0:
            root_cause = "ZERO_PATHWAY"
        elif not package.validated_disease_genes:
            root_cause = "DISEASE_BRIDGE_FAILURE"
        elif len(gene_disease_edges) == 0:
            root_cause = "DISEASE_BRIDGE_FAILURE"
        elif len(target_pw_edges) == 0 and len(target_gene_edges) == 0:
            root_cause = "PATHWAY_RELEVANCE_FAILURE"
        elif len(scored_paths) == 0:
            root_cause = "PATHFINDER_FAILURE"
        elif len(validated_cands) > 0 and all(c.support_level == "UNSUPPORTED" for c in validated_cands):
            root_cause = "VALIDATION_FAILURE"
        elif len(validated_cands) > 0 and all(c.support_level == "CONTRADICTED" for c in validated_cands):
            root_cause = "SCIENTIFICALLY_UNSUPPORTED"
        else:
            root_cause = "SCIENTIFICALLY_UNSUPPORTED"

    return {
        "drug": drug,
        "disease": disease,
        "targets_total": len(targets_raw),
        "targets_human": len(human_targets),
        "targets_non_human": len(non_human_targets),
        "canonical_targets": canonical_targets,
        "pathways_total": len(pathways_raw),
        "reactions_total": len(reactions_raw),
        "graph_nodes": len(graph.nodes),
        "graph_edges": len(graph.edges),
        "target_rxn_edges": len(target_rxn_edges),
        "rxn_pw_edges": len(rxn_pw_edges),
        "target_pw_edges": len(target_pw_edges),
        "pw_gene_edges": len(pw_gene_edges),
        "target_gene_edges": len(target_gene_edges),
        "gene_disease_edges": len(gene_disease_edges),
        "paths_raw": len(raw_paths),
        "paths_scored": len(scored_paths),
        "pathfinder_rejection_reason": pathfinder_rejection_reason,
        "candidates_count": len(validated_cands),
        "validation_rejection_reasons": validation_rejection_reasons,
        "ms": ms,
        "level": level,
        "quality": quality,
        "root_cause": root_cause,
        "recommendation": result.recommendation_status.value,
    }


def audit_filtering_mechanisms() -> list[dict[str, Any]]:
    """Audit all hardcoded caps, pre-filters, and thresholds in the mechanistic reasoning pipeline."""
    return [
        {
            "filter": "_MAX_TARGETS = 8",
            "location": "backend/reasoning/mechanistic/evidence_graph.py:71, 411",
            "purpose": "Limits graph combinatorial explosion by taking only top 8 drug targets.",
            "false_negative_risk": "Moderate: Promiscuous drugs with >8 targets lose targets ranked 9+. If the therapeutically relevant target is not in the top 8 by affinity/volume, its mechanistic path is omitted.",
            "remedy": "Allow disease-associated targets to be prioritized into the top 8 rather than taking a blind slice.",
        },
        {
            "filter": "_MAX_PATHWAYS_PER_TARGET = 6",
            "location": "backend/reasoning/mechanistic/evidence_graph.py:72, 630",
            "purpose": "Caps Reactome pathways per target to top 6 sorted by disease-gene overlap relevance.",
            "false_negative_risk": "Low-Moderate: Sorted by disease overlap relevance, so relevant pathways are prioritized, but distant multi-hop reaction cascades without direct gene overlap can be truncated.",
            "remedy": "Increase cap to 10 for reaction-enriched pathways.",
        },
        {
            "filter": "_MAX_HOPS = 5",
            "location": "backend/reasoning/mechanistic/evidence_graph.py:73, 353",
            "purpose": "Enforces simple path length bound (Drug → Target → Reaction → Pathway → Gene → Disease = 5 hops).",
            "false_negative_risk": "Low: 5 hops accommodates the complete canonical reaction-enriched path. Longer paths suffer severe biological confidence decay.",
            "remedy": "Keep 5 hops; longer paths are biologically speculative.",
        },
        {
            "filter": "paths[:5] candidate limit",
            "location": "backend/reasoning/mechanistic/multi_hop_reasoner.py:363",
            "purpose": "Limits discovery to the top 5 scored graph paths.",
            "false_negative_risk": "Moderate: If paths 1-5 lack literature claim coverage, but path 6 has literature claims, path 6 is dropped before validation.",
            "remedy": "Pass top 10 paths to validation, then pick top 5 validated candidates.",
        },
        {
            "filter": "is_human_protein() / _NON_HUMAN_KEYWORDS",
            "location": "backend/reasoning/mechanistic/evidence_graph.py:113-130",
            "purpose": "Prevents non-human organism targets (bacterial, viral, invertebrate) from building human graph edges.",
            "false_negative_risk": "Intentional / Scientifically Justified: Anti-infective drugs (e.g. Ivermectin targeting helminth GluCl channels, Oseltamivir targeting viral neuraminidase) do not act on human host proteins; their human cardiometabolic or host mechanistic score is legitimately 0.0.",
            "remedy": "Do not remove. Anti-infective host mechanisms must be modeled through host-pathogen interaction layers, not by fabricating human targets.",
        },
        {
            "filter": "pw_gene_syms & disease_gene_syms requirement",
            "location": "backend/reasoning/mechanistic/evidence_graph.py:753",
            "purpose": "Requires pathway participants to intersect with curated disease-associated genes in Open Targets/DisGeNET.",
            "false_negative_risk": "High: If Open Targets lacks disease-gene annotations for the queried disease entity (e.g. rare diseases or uncurated terms), the Disease node has zero in-degree, causing all paths to fail.",
            "remedy": "Add ontology expansion / fallback disease synonym mapping.",
        },
        {
            "filter": "score < 0.20 -> UNSUPPORTED threshold",
            "location": "backend/reasoning/mechanistic/mechanism_validation.py:304",
            "purpose": "Marks candidate mechanisms as UNSUPPORTED if composite validation score < 0.20.",
            "false_negative_risk": "Moderate: Weakly supported structural candidates without mapped literature claims or direct database links are zeroed out.",
            "remedy": "Scientifically sound: structural connectivity alone without biological grounding should not produce positive mechanistic confidence.",
        },
    ]


async def run_audit():
    print("=" * 80)
    print("CYNTHERA — PHASE 5.9 MECHANISTIC COVERAGE & ZERO-SCORE AUDIT")
    print("=" * 80)
    print(f"Auditing {len(AUDIT_CASES)} balanced cases across diverse pharmacological classes...\n")

    orchestrator = MasterOrchestrator(
        llm_api_key=os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
        ncbi_api_key=os.environ.get("NCBI_API_KEY"),
        disgenet_api_key=os.environ.get("DISGENET_API_KEY"),
    )

    results = []
    t_start = time.time()

    # Semaphore to prevent hitting rate limits while running concurrently
    sem = asyncio.Semaphore(2)

    async def process_one(drug: str, disease: str, description: str):
        async with sem:
            print(f"  --> Auditing: {drug} → {disease} ({description})...")
            try:
                hyp, pkg, res = await orchestrator.evaluate(
                    drug_name=drug,
                    disease_name=disease,
                    policy=RetrievalPolicy.STANDARD,
                    bypass_cache=False,  # Use cache if available, else fetch
                )
                audit_dict = audit_case_stages(drug, disease, pkg, res)
                audit_dict["description"] = description
                return audit_dict
            except Exception as exc:
                print(f"      [ERROR] {drug} → {disease}: {exc}")
                return {
                    "drug": drug,
                    "disease": disease,
                    "description": description,
                    "targets_total": 0,
                    "targets_human": 0,
                    "targets_non_human": 0,
                    "canonical_targets": [],
                    "pathways_total": 0,
                    "reactions_total": 0,
                    "graph_nodes": 0,
                    "graph_edges": 0,
                    "target_rxn_edges": 0,
                    "rxn_pw_edges": 0,
                    "target_pw_edges": 0,
                    "pw_gene_edges": 0,
                    "target_gene_edges": 0,
                    "gene_disease_edges": 0,
                    "paths_raw": 0,
                    "paths_scored": 0,
                    "pathfinder_rejection_reason": f"EXCEPTION: {exc}",
                    "candidates_count": 0,
                    "validation_rejection_reasons": [str(exc)],
                    "ms": 0.0,
                    "level": "NONE",
                    "quality": "UNKNOWN",
                    "root_cause": "RETRIEVAL_FAILURE",
                    "recommendation": "ERROR",
                }

    tasks = [process_one(d, dis, desc) for d, dis, desc in AUDIT_CASES]
    results = await asyncio.gather(*tasks)

    elapsed = time.time() - t_start
    print(f"\nAudit completed in {elapsed:.1f}s across {len(results)} cases.\n")

    # ── Summary Table ────────────────────────────────────────────────────────
    print("=" * 110)
    print(f"{'Drug':<16} | {'Disease':<22} | {'Tgt':<4} | {'Pw':<4} | {'Rxn':<4} | {'Edges':<5} | {'Paths':<5} | {'MS':<6} | {'Quality':<18} | {'Root Cause'}")
    print("-" * 110)
    for r in results:
        ms_str = f"{r['ms']:.3f}" if isinstance(r['ms'], (int, float)) else str(r['ms'])
        print(f"{r['drug']:<16} | {r['disease']:<22} | {r['targets_total']:<4} | {r['pathways_total']:<4} | {r['reactions_total']:<4} | {r['graph_edges']:<5} | {r['paths_scored']:<5} | {ms_str:<6} | {r['quality']:<18} | {r['root_cause']}")
    print("=" * 110)

    # ── Zero-Score Distribution ──────────────────────────────────────────────
    zero_cases = [r for r in results if r['ms'] == 0.0]
    non_zero_cases = [r for r in results if r['ms'] > 0.0]

    causes_count = {}
    for z in zero_cases:
        c = z['root_cause']
        causes_count[c] = causes_count.get(c, 0) + 1

    print("\n" + "=" * 80)
    print("ZERO-SCORE DISTRIBUTION & ROOT CAUSE BREAKDOWN")
    print("=" * 80)
    print(f"Total Cases Evaluated:       {len(results)}")
    print(f"Non-Zero MS Cases (MS > 0):  {len(non_zero_cases)} ({len(non_zero_cases)/len(results):.1%})")
    print(f"Zero MS Cases (MS = 0.0):    {len(zero_cases)} ({len(zero_cases)/len(results):.1%})")
    print("-" * 80)
    for cause, count in sorted(causes_count.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cause:<30}: {count:>3} cases ({count/len(zero_cases):.1%} of zeros)")
    print("=" * 80)

    # ── PathFinder & Validation Inspections ───────────────────────────────────
    print("\n" + "=" * 80)
    print("PATHFINDER & VALIDATION DETAILED REJECTION TRACES")
    print("=" * 80)
    for r in results:
        if r['ms'] == 0.0:
            print(f"\nCase: {r['drug']} → {r['disease']} (Cause: {r['root_cause']})")
            print(f"  Targets: {r['targets_total']} (Human: {r['targets_human']}, Non-human: {r['targets_non_human']})")
            print(f"  Pathways: {r['pathways_total']} | Reactions: {r['reactions_total']}")
            print(f"  Graph: {r['graph_nodes']} nodes, {r['graph_edges']} edges (Target→Pw: {r['target_pw_edges']}, Pw→Gene: {r['pw_gene_edges']}, Gene→Disease: {r['gene_disease_edges']})")
            print(f"  Pathfinder: raw={r['paths_raw']}, scored={r['paths_scored']} (Reason: {r['pathfinder_rejection_reason']})")
            if r['validation_rejection_reasons']:
                print(f"  Validation Rejections: {r['validation_rejection_reasons']}")
            print(f"  Scientific Rationale: {r['description']}")

    # ── Filter Audit Report ───────────────────────────────────────────────────
    filters = audit_filtering_mechanisms()
    print("\n" + "=" * 80)
    print("FILTER AUDIT & SENSITIVITY REPORT")
    print("=" * 80)
    for f in filters:
        print(f"\nFilter:               {f['filter']}")
        print(f"Location:             {f['location']}")
        print(f"Purpose:              {f['purpose']}")
        print(f"False-Negative Risk:  {f['false_negative_risk']}")
        print(f"Recommended Remedy:   {f['remedy']}")
    print("=" * 80)

    # Save complete trace to JSON
    with open(root_dir / "scratch" / "mechanistic_coverage_audit_output.json", "w") as out_f:
        json.dump(
            {
                "audit_timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "total_cases": len(results),
                "non_zero_count": len(non_zero_cases),
                "zero_count": len(zero_cases),
                "zero_distribution": causes_count,
                "cases": results,
                "filters": filters,
            },
            out_f,
            indent=2,
        )
    print(f"\nFull diagnostic JSON saved to scratch/mechanistic_coverage_audit_output.json")


if __name__ == "__main__":
    asyncio.run(run_audit())
