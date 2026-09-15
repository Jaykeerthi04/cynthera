"""Phase 5.1-5.3 live diagnostic script.

Runs deterministic scoring checks without any API calls.
Tests the quality gate, PARTIAL directional state, and score_components
against synthetic test vectors that mimic the 6 test cases from the spec.

Usage:
    .\\venv\\Scripts\\python.exe scratch/audit_phase5_1_5_3.py
"""
from __future__ import annotations
import sys
sys.path.insert(0, ".")

from backend.core.domain.candidate_mechanism import CandidateMechanism, MechanismHop
from backend.core.domain.reasoning_result import MechanisticAssessment, SupportAssessment, RiskAssessment
from backend.core.enums.recommendation import RecommendationStatus
from backend.reasoning.directional.directional_mechanism_evaluator import DirectionalMechanismEvaluator
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner
from unittest.mock import MagicMock


def make_hop(from_n, to_n, pred, pol="UNKNOWN", g="STRUCTURAL"):
    return MechanismHop(from_node=from_n, to_node=to_n, predicate=pred, polarity=pol, causal_grounding=g, evidence_strength=0.7, source_database="Reactome")

def make_cand(name, support, conf, hops, struct_ec=3, ind_grp=0, grounded=0):
    return CandidateMechanism(
        candidate_index=1, name=name, support_level=support, confidence_score=conf,
        hops=hops, structural_edge_count=struct_ec, independent_evidence_groups=ind_grp,
        grounded_edge_count=grounded,
    )

def run_rule1(ss, ms_score, rs, support_level, boxed=False):
    from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
    orchestrator = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
    support = SupportAssessment(score=ss, level="HIGH" if ss>=0.7 else "MEDIUM" if ss>=0.4 else "LOW", evidence_count=5, weighted_sum=2.0)
    mechanistic = MechanisticAssessment(score=ms_score, level="HIGH" if ms_score>=0.7 else "MEDIUM" if ms_score>=0.4 else "LOW",
        score_components={"raw_confidence": ms_score, "support_level": support_level, "structural_edge_count": 3, "causal_edge_count": 0,
            "grounded_edge_count": 0, "independent_evidence_groups": 0, "reaction_enriched": False, "candidate_count": 1, "best_candidate_name": "M"})
    risk = RiskAssessment(score=rs, level="HIGH" if rs>=0.7 else "MEDIUM" if rs>=0.4 else "LOW", failed_trial_count=0, contradiction_count=0)
    pkg = MagicMock(); pkg.sources_failed = []; pkg.drug.name = "TestDrug"; pkg.disease.name = "TestDisease"
    safety = MagicMock(); safety.has_boxed_warning = boxed; safety.overall_safety_grade = "D" if boxed else "B"
    prior = MagicMock(); prior.has_established_precedent = False; prior.matched_indication_term = ""; prior.evidence_boost = 0.0
    sci_ctx = MagicMock(); sci_ctx.regulatory.status = "NOT_APPROVED"; sci_ctx.regulatory.confidence = 0.0
    status, reasons = orchestrator._apply_rules(support, mechanistic, risk, [], pkg, safety, prior, sci_ctx)
    return status, reasons


evaluator = DirectionalMechanismEvaluator()
reasoner = MultiHopReasoner()

sep = "=" * 72
print(sep)
print("CYNTHERA Phase 5.1-5.3 Diagnostic Audit")
print(sep)

# --- Case 1: Doxycycline -> Heart failure (WEAK_SPECULATIVE, structural path) ---
print("\n[CASE 1] Doxycycline -> Heart failure")
hops_doxy = [
    make_hop("Drug:Doxycycline","Target:MMP1","INHIBITOR","NEGATIVE","CURATED"),
    make_hop("Target:MMP1","Pathway:BasiginInt","PARTICIPATES_IN","UNKNOWN","STRUCTURAL"),
    make_hop("Pathway:BasiginInt","Gene:ATP1B1","CONTAINS_GENE","UNKNOWN","STRUCTURAL"),
    make_hop("Gene:ATP1B1","Disease:HeartFailure","ASSOCIATED_WITH","UNKNOWN","STRUCTURAL"),
]
cand_doxy = make_cand("Doxy->HF via MMP1", "WEAK_SPECULATIVE", 0.409, hops_doxy, struct_ec=3, ind_grp=0)
score_d, level_d = reasoner.compute_mechanistic_score_from_candidates([cand_doxy])
d_result = evaluator.evaluate_candidate(cand_doxy, package=None, disease_required_action="INHIBITION", drug_action="INHIBITOR")
status_d, reasons_d = run_rule1(ss=0.50, ms_score=score_d, rs=0.25, support_level="WEAK_SPECULATIVE")
print(f"  MS (raw)     : {score_d:.4f}  Level: {level_d}")
print(f"  support_level: WEAK_SPECULATIVE")
print(f"  Direction    : {d_result.path_direction_status}  (consistent={d_result.directionally_consistent})")
print(f"  Gate result  : {status_d.value}")
print(f"  Explanation  : {d_result.explanation[:120]}...")
assert level_d == "LOW", f"FAIL: expected LOW, got {level_d}"
assert d_result.path_direction_status == "PARTIAL", f"FAIL: expected PARTIAL, got {d_result.path_direction_status}"
assert status_d == RecommendationStatus.UNCERTAIN, f"FAIL: expected UNCERTAIN, got {status_d}"
print("  [PASS]")

# --- Case 2: Aspirin -> Colorectal Cancer (WEAK_SPECULATIVE) ---
print("\n[CASE 2] Aspirin -> Colorectal Cancer")
cand_asp = make_cand("ASP->CRC via PTGS2", "WEAK_SPECULATIVE", 0.46, [
    make_hop("Drug:Aspirin","Target:PTGS2","INHIBITOR","NEGATIVE","CURATED"),
    make_hop("Target:PTGS2","Pathway:ArachAcid","PARTICIPATES_IN","UNKNOWN","STRUCTURAL"),
    make_hop("Pathway:ArachAcid","Gene:TP53","CONTAINS_GENE","UNKNOWN","STRUCTURAL"),
    make_hop("Gene:TP53","Disease:CRC","ASSOCIATED_WITH","UNKNOWN","STRUCTURAL"),
], struct_ec=3)
score_a, level_a = reasoner.compute_mechanistic_score_from_candidates([cand_asp])
d_asp = evaluator.evaluate_candidate(cand_asp, package=None, disease_required_action="INHIBITION", drug_action="INHIBITOR")
status_a, _ = run_rule1(ss=0.55, ms_score=score_a, rs=0.20, support_level="WEAK_SPECULATIVE")
print(f"  MS (raw): {score_a:.4f}  Level: {level_a}  Direction: {d_asp.path_direction_status}  Gate: {status_a.value}")
assert d_asp.path_direction_status == "PARTIAL"
assert status_a == RecommendationStatus.UNCERTAIN
print("  [PASS]")

# --- Case 3: Oseltamivir -> Influenza (MODULATOR drug action -> UNKNOWN direction) ---
print("\n[CASE 3] Oseltamivir -> Influenza")
cand_osel = make_cand("OSEL->INF via NA", "WEAK_SPECULATIVE", 0.35, [
    make_hop("Drug:Oseltamivir","Target:NA","MODULATES","UNKNOWN","STRUCTURAL"),
    make_hop("Target:NA","Pathway:NeurInf","PARTICIPATES_IN","UNKNOWN","STRUCTURAL"),
    make_hop("Pathway:NeurInf","Gene:IFNB1","CONTAINS_GENE","UNKNOWN","STRUCTURAL"),
    make_hop("Gene:IFNB1","Disease:Influenza","ASSOCIATED_WITH","UNKNOWN","STRUCTURAL"),
], struct_ec=4)
score_o, level_o = reasoner.compute_mechanistic_score_from_candidates([cand_osel])
d_osel = evaluator.evaluate_candidate(cand_osel, package=None, disease_required_action="UNKNOWN", drug_action="MODULATES")
status_o, _ = run_rule1(ss=0.35, ms_score=score_o, rs=0.20, support_level="WEAK_SPECULATIVE")
print(f"  MS (raw): {score_o:.4f}  Level: {level_o}  Direction: {d_osel.path_direction_status}  Gate: {status_o.value}")
assert d_osel.path_direction_status == "UNKNOWN", f"FAIL: got {d_osel.path_direction_status}"
assert d_osel.contradiction_detected is False
print("  [PASS]")

# --- Case 4: Testosterone -> Prostate Cancer (AGONIST + INHIBITION needed -> CONTRADICTORY) ---
print("\n[CASE 4] Testosterone -> Prostate Cancer")
cand_test = make_cand("TEST->PRCA via AR", "WEAK_SPECULATIVE", 0.50, [
    make_hop("Drug:Testosterone","Target:AR","AGONIST","POSITIVE","CURATED"),
    make_hop("Target:AR","Pathway:Androgen","PARTICIPATES_IN","UNKNOWN","STRUCTURAL"),
    make_hop("Gene:MYC","Disease:ProstateCancer","ASSOCIATED_WITH","UNKNOWN","STRUCTURAL"),
], struct_ec=2)
score_t, level_t = reasoner.compute_mechanistic_score_from_candidates([cand_test])
d_test = evaluator.evaluate_candidate(cand_test, package=None, disease_required_action="INHIBITION", drug_action="AGONIST")
print(f"  MS (raw): {score_t:.4f}  Level: {level_t}  Direction: {d_test.path_direction_status}")
assert d_test.path_direction_status == "CONTRADICTORY"
assert d_test.contradiction_detected is True
print("  [PASS]")

# --- Case 5: MODERATELY_SUPPORTED reaches PROMISING ---
print("\n[CASE 5] MODERATELY_SUPPORTED + valid SS/RS -> PROMISING")
cand_mod = make_cand("M->D via validated", "MODERATELY_SUPPORTED", 0.58, [
    make_hop("Drug:X","Target:Y","INHIBITOR","NEGATIVE","CURATED"),
    make_hop("Target:Y","Gene:Z","NEGATIVE_REGULATES","NEGATIVE","CURATED"),
    make_hop("Gene:Z","Disease:D","ASSOCIATED_WITH","UNKNOWN","STRUCTURAL"),
], struct_ec=1, ind_grp=2, grounded=2)
score_m, level_m = reasoner.compute_mechanistic_score_from_candidates([cand_mod])
status_m, reasons_m = run_rule1(ss=0.55, ms_score=score_m, rs=0.15, support_level="MODERATELY_SUPPORTED")
print(f"  MS (raw): {score_m:.4f}  Level: {level_m}  Gate: {status_m.value}")
assert level_m == "MEDIUM"
assert status_m == RecommendationStatus.PROMISING, f"FAIL: expected PROMISING, got {status_m}"
print("  [PASS]")

# --- Case 6: Safety veto overrides strong mechanism ---
print("\n[CASE 6] Safety veto overrides STRONGLY_SUPPORTED mechanism")
status_s, reasons_s = run_rule1(ss=0.80, ms_score=0.75, rs=0.65, support_level="STRONGLY_SUPPORTED", boxed=True)
print(f"  Gate: {status_s.value}")
assert status_s == RecommendationStatus.NOT_RECOMMENDED
print("  [PASS]")

print()
print(sep)
print("ALL 6 CASES PASSED")
print(sep)
