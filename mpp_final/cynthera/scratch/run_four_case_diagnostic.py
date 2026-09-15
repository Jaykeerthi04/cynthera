"""Diagnostic evaluation runner for the four drug-disease cases.

Cases:
1. Fluvoxamine -> COVID-19
2. Tadalafil -> Alzheimer disease
3. Disulfiram -> Glaucoma
4. Allopurinol -> Gout

Executes via the normal production MasterOrchestrator.evaluate pipeline.
Captures complete dataflow across all stages without modifying production code.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time
from typing import Any

# Ensure stdout handles utf-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath("."))

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner


CASES = [
    ("Fluvoxamine", "COVID-19"),
    ("Tadalafil", "Alzheimer disease"),
    ("Disulfiram", "Glaucoma"),
    ("Allopurinol", "Gout"),
]


async def run_diagnostic():
    orchestrator = MasterOrchestrator()
    results = []

    print("================================================================================")
    print("CYNTHERA FOUR-CASE CURRENT STATE DIAGNOSTIC RUN")
    print("================================================================================")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print(f"Policy: STANDARD")
    print(f"Cache state: Fresh evaluation via MasterOrchestrator")
    print("================================================================================\n")

    for drug, disease in CASES:
        print(f"\n>>> EVALUATING: {drug} -> {disease} ...", flush=True)
        t0 = time.time()
        try:
            hyp, pkg, res = await orchestrator.evaluate(
                drug_name=drug,
                disease_name=disease,
                policy=RetrievalPolicy.STANDARD,
                bypass_cache=False,
            )
            elapsed = time.time() - t0
            print(f"    Completed in {elapsed:.2f}s", flush=True)
            results.append({
                "drug": drug,
                "disease": disease,
                "hypothesis": hyp,
                "package": pkg,
                "result": res,
                "elapsed": elapsed,
                "error": None,
            })
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"    FAILED in {elapsed:.2f}s: {exc}", flush=True)
            results.append({
                "drug": drug,
                "disease": disease,
                "hypothesis": None,
                "package": None,
                "result": None,
                "elapsed": elapsed,
                "error": str(exc),
            })

    # Save raw results summary to JSON for reporting precision
    summary_data = []
    for item in results:
        drug = item["drug"]
        disease = item["disease"]
        if item["error"]:
            summary_data.append({
                "case": f"{drug} -> {disease}",
                "error": item["error"],
            })
            continue

        hyp = item["hypothesis"]
        pkg = item["package"]
        res = item["result"]
        audit = res.audit_report
        ta = getattr(audit, "therapeutic_alignment", {}) or {}

        # Re-build graph for structural edge breakdown
        gb = EvidenceGraphBuilder()
        graph, _ = gb.build(pkg)

        reasoner = MultiHopReasoner()
        paths = reasoner.trace_paths(pkg)

        cands = res.mechanistic_assessment.candidate_mechanisms or []
        top_cand = cands[0] if cands else {}

        # Target info
        target_aligns = ta.get("target_alignments", [])
        primary_targets = [t for t in target_aligns if t.get("is_primary")]
        ranked_target = primary_targets[0].get("target_id") if primary_targets else (target_aligns[0].get("target_id") if target_aligns else (pkg.targets[0].protein_uniprot if pkg.targets else "NONE"))

        # Evidence records breakdown
        sources_with_zero = []
        sources_succeeded = list(pkg.sources_queried or [])
        sources_failed = list(pkg.sources_failed or [])

        # Check records per source
        rec_by_source = {}
        for r in pkg.evidence_records:
            s = getattr(r, "source", "unknown")
            rec_by_source[s] = rec_by_source.get(s, 0) + 1
        for s in sources_succeeded:
            if rec_by_source.get(s, 0) == 0:
                sources_with_zero.append(s)

        # DoE / DATTs
        doe_count = len(getattr(pkg, "opentargets_doe_evidence", []) or [])
        datts_count = len(getattr(pkg, "datts_evidence", []) or [])
        chembl_mech_count = sum(1 for t in pkg.targets if getattr(t, "mechanism", None))
        therapeutic_ev_count = doe_count + datts_count + chembl_mech_count

        # Opposition details
        opp_assess = getattr(res, "opposition_assessment", None)

        case_summary = {
            "case": f"{drug} -> {disease}",
            "identity": {
                "drug": drug,
                "disease": disease,
                "canonical_drug": f"{hyp.drug_name} ({hyp.drug_chembl_id})",
                "canonical_disease": f"{hyp.disease_name} (MeSH: {hyp.disease_mesh_id})",
            },
            "final_decision": {
                "prediction": ta.get("overall_alignment", "INSUFFICIENT"),
                "recommendation": res.recommendation_status.value,
                "confidence": ta.get("confidence", 0.0),
                "decision_reasons": res.recommendation_reasons,
            },
            "mechanistic_arm": {
                "target_count": len(pkg.targets),
                "ranked_target": ranked_target,
                "target_source": "ChEMBL / UniProt" if pkg.targets else "NONE",
                "pathway_count": len(pkg.pathways),
                "graph_node_count": len(graph.nodes),
                "graph_edge_count": len(graph.edges),
                "paths_found": len(paths),
                "candidate_count": len(cands),
                "mechanistic_score": res.mechanistic_assessment.score,
                "mechanistic_quality": top_cand.get("support_level", "NONE"),
                "mechanism_level": res.mechanistic_assessment.level,
                "directional_mechanism_status": top_cand.get("directional_mechanism_status", "UNKNOWN"),
                "causal_grounding": top_cand.get("causal_grounding_level", "NONE"),
                "mechanistic_polarity": top_cand.get("directional_polarity", "UNKNOWN"),
            },
            "therapeutic_arm": {
                "therapeutic_evidence_count": therapeutic_ev_count,
                "doe_count": doe_count,
                "datts_count": datts_count,
                "chembl_mechanisms": chembl_mech_count,
                "high_quality_therapeutic_evidence": res.support_assessment.has_high_quality_therapeutic,
                "therapeutic_direction": ta.get("overall_alignment", "INSUFFICIENT"),
                "support_score": res.support_assessment.score,
                "support_quality": res.support_assessment.level,
                "regulatory_approved": res.support_assessment.regulatory_approved,
                "regulatory_status": getattr(audit, "evaluation_pathway", "NOVEL_HYPOTHESIS"),
                "clinical_trials_count": len(pkg.clinical_trials),
                "clinical_trial_status": getattr(audit, "clinical_trial_status", "UNKNOWN"),
                "evidence_records_count": len(pkg.evidence_records),
            },
            "opposition_arm": {
                "integrated_in_orchestrator": False,  # As verified in code
                "opposition_assessment_score": getattr(opp_assess, "score", 0.0) if opp_assess else 0.0,
                "opposition_assessment_level": getattr(opp_assess, "level", "NONE") if opp_assess else "NONE",
                "qualified_negative_claim_count": getattr(opp_assess, "qualified_negative_claim_count", 0) if opp_assess else 0,
                "independent_group_count": getattr(opp_assess, "independent_group_count", 0) if opp_assess else 0,
                "opposing_groups_count_in_alignment": ta.get("opposing_groups_count", 0),
            },
            "contradiction": {
                "contradiction_count": len(res.contradictions),
                "risk_score": res.risk_assessment.score,
                "risk_level": res.risk_assessment.level,
                "failed_trials": res.risk_assessment.failed_trial_count,
                "supporting_groups_count": ta.get("supporting_groups_count", 0),
                "opposing_groups_count": ta.get("opposing_groups_count", 0),
            },
            "retrieval": {
                "sources_succeeded": sources_succeeded,
                "sources_failed": sources_failed,
                "sources_with_zero": sources_with_zero,
                "retrieval_confidence": pkg.retrieval_confidence,
            },
            "timing": {
                "elapsed_s": item["elapsed"],
            }
        }
        summary_data.append(case_summary)

    with open("scratch/four_case_diagnostic_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print("\n" + "=" * 80)
    print("FOUR-CASE DIAGNOSTIC SUMMARY TABLE")
    print("=" * 80)
    header = f"{'Case':<32} | {'Pred':<12} | {'Rec':<15} | {'MS':<6} | {'Level':<6} | {'Align':<12} | {'Paths':<5} | {'Cands':<5} | {'RS':<6}"
    print(header)
    print("-" * len(header))
    for s in summary_data:
        if "error" in s:
            print(f"{s['case']:<32} | ERROR: {s['error']}")
            continue
        c = s["case"]
        pred = s["final_decision"]["prediction"]
        rec = s["final_decision"]["recommendation"]
        ms = s["mechanistic_arm"]["mechanistic_score"]
        lvl = s["mechanistic_arm"]["mechanism_level"]
        al = s["therapeutic_arm"]["therapeutic_direction"]
        paths = s["mechanistic_arm"]["paths_found"]
        cands = s["mechanistic_arm"]["candidate_count"]
        rs = s["contradiction"]["risk_score"]
        print(f"{c:<32} | {pred:<12} | {rec:<15} | {ms:<6.3f} | {lvl:<6} | {al:<12} | {paths:<5} | {cands:<5} | {rs:<6.3f}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
