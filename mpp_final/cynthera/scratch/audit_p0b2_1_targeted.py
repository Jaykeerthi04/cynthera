"""Targeted validation and audit generation for CYNTHERA P0b-2.1.

Evaluates the 8 canonical cases:
- TC-001 (Lisinopril -> Hypertension)
- TC-003 (Budesonide -> Asthma)
- TC-062 (Ranibizumab -> AMD)
- TC-026 (Niacin -> CVD)
- TC-030 (Dexamethasone -> TBI)
- TC-052 (Nivolumab -> GBM)
- TC-024 (Hydroxychloroquine -> COVID-19)
- TC-022 (Fluvoxamine -> COVID-19)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.enums.recommendation import RecommendationStatus
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.engineering.retrieval.disease_relation import matches_for_approval_anchor
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
)
from backend.reasoning.opposition.opposition_qualification import qualify_opposition_claim
from backend.reasoning.orchestrator.decision_rules import apply_decision_rules, classify_opposition_conflict

cache_dir = Path("data/ct_raw_cache")
results_100_path = Path("evaluation_outputs/100_case_final/results.jsonl")

baseline_by_cid = {}
with open(results_100_path, "r", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        baseline_by_cid[d["case_id"]] = d

with open("backend/evaluation/before_vs_now_50_end_to_end_ledger.json", "r", encoding="utf-8") as f:
    before_ledger = json.load(f)
cases_by_cid = {c["case_id"]: c for c in before_ledger["cases"]}

target_cases = [
    ("TC-001", "Lisinopril", "Hypertension", "SUPPORT"),
    ("TC-003", "Budesonide", "Asthma", "SUPPORT"),
    ("TC-062", "Ranibizumab", "Age-related macular degeneration", "SUPPORT"),
    ("TC-026", "Niacin", "Cardiovascular disease", "OPPOSE"),
    ("TC-030", "Dexamethasone", "Traumatic brain injury", "OPPOSE"),
    ("TC-052", "Nivolumab", "Glioblastoma", "UNCERTAIN"),
    ("TC-024", "Hydroxychloroquine", "COVID-19", "OPPOSE"),
    ("TC-022", "Fluvoxamine", "COVID-19", "OPPOSE"),
]

pipeline = RetrievalPipeline()
assessor = TherapeuticOppositionAssessor()

print("=" * 110)
print(f"{'Case ID':<8} | {'Drug':<18} | {'Opp Score':<9} | {'Groups':<6} | {'Qual Category':<30} | {'Anchor':<6} | {'Conflict Type':<25} | {'Final Pred'}")
print("=" * 110)

audit_records = []

for cid, drug, disease, gold in target_cases:
    b = baseline_by_cid.get(cid, {})
    prev_entry = cases_by_cid.get(cid, {})

    # Determine approval anchor
    baseline_rule = str(b.get("decision_rule", ""))
    m_term = re.search(r"Matched ChEMBL term: '([^']+)'", baseline_rule)
    matched_term = m_term.group(1) if m_term else (b.get("matched_indication_term") or None)
    is_anchor = matches_for_approval_anchor(disease, matched_term) if matched_term else False

    safe_name = f"{re.sub(r'[^a-zA-Z0-9_]', '_', drug)}_{re.sub(r'[^a-zA-Z0-9_]', '_', disease)}.json"
    cache_path = cache_dir / safe_name
    claims = []
    claim_qualifications = []
    if cache_path.exists():
        raw_data = json.loads(cache_path.read_text(encoding="utf-8"))
        parsed = pipeline._parse_trials_data(
            raw_data,
            Drug(name=drug, identifiers={"chembl": "CHEMBL_TEST"}),
            Disease(name=disease, identifiers={"mesh": "MESH_TEST"}),
        )
        for t in parsed:
            c = trial_to_negative_claim(t, drug, disease)
            if c is not None:
                claims.append(c)
                q = qualify_opposition_claim(c, drug, disease, t)
                claim_qualifications.append({
                    "nct_id": t.nct_id,
                    "title": t.title,
                    "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                    "qualification": q.to_dict(),
                })

    opp_assess = assessor.assess(claims, drug, disease)

    # Baseline scores
    ss = float(b.get("support_score", 0.0))
    ms = float(b.get("mechanistic_score", 0.0))
    rs = float(b.get("risk_score", 0.0))
    has_high_qual = bool(b.get("high_quality_therapeutic_evidence", False))
    failed_trials_cnt = int(b.get("negative_trial_count", 0))
    safety_boxed = bool(b.get("safety_boxed", False) or "boxed warning" in str(b.get("decision_rule", "")).lower())
    effective_safety_veto = bool(b.get("safety_veto", False))
    strong_conflict = bool(b.get("strong_conflict", False))
    contra_level = b.get("contradiction_resolution", "")
    evidence_count = int(b.get("evidence_record_count", 0))

    decision = apply_decision_rules(
        is_approved=is_anchor,
        matched_chembl_term=matched_term,
        support_score=ss,
        evidence_count=evidence_count,
        mechanistic_score=ms,
        risk_score=rs,
        safety_veto=effective_safety_veto,
        strong_conflict=strong_conflict,
        contradiction_level=contra_level,
        has_high_quality_therapeutic=has_high_qual,
        opp_assessment=opp_assess,
        failed_trial_count=failed_trials_cnt,
    )

    rec_status = decision.status.value if hasattr(decision.status, "value") else str(decision.status)
    pred_3class = "SUPPORT" if rec_status == "PROMISING" else ("OPPOSE" if rec_status == "NOT_RECOMMENDED" else "UNCERTAIN")

    # Qualification summary for primary claim or disqualified claim
    primary_qual_code = "NONE"
    primary_qualified = False
    if opp_assess.qualified_claims:
        # Check qualified claim
        primary_qual_code = opp_assess.qualified_claims[0].get("qualification", {}).get("reason_code", "DIRECT_THERAPEUTIC_FAILURE")
        primary_qualified = True
    elif claim_qualifications:
        primary_qual_code = claim_qualifications[0]["qualification"]["reason_code"]
        primary_qualified = claim_qualifications[0]["qualification"]["qualified"]

    conflict_type = decision.trace.get("conflict_type", "N/A")
    rule_fired = decision.deciding_rule

    print(f"{cid:<8} | {drug:<18} | {opp_assess.score:<9.4f} | {opp_assess.independent_group_count:<6} | {primary_qual_code:<30} | {str(is_anchor):<6} | {conflict_type:<25} | {pred_3class}")

    audit_records.append({
        "case_id": cid,
        "drug": drug,
        "disease": disease,
        "gold_standard": gold,
        "approved_anchor": is_anchor,
        "matched_term": matched_term,
        "opposition_score": opp_assess.score,
        "group_count": opp_assess.independent_group_count,
        "primary_qualification_category": primary_qual_code,
        "qualified": primary_qualified,
        "conflict_type": conflict_type,
        "rule_fired": rule_fired,
        "final_prediction": pred_3class,
        "recommendation_status": rec_status,
        "claims_evaluated": claim_qualifications,
        "qualified_claims": opp_assess.qualified_claims,
        "decision_trace": decision.trace,
        "all_reasons": decision.reasons,
    })

audit_json_path = Path("backend/evaluation/p0b2_1_conflict_semantics_audit.json")
audit_json_path.write_text(json.dumps({"cases": audit_records}, indent=2), encoding="utf-8")
print(f"\nWritten {len(audit_records)} case audit records to {audit_json_path}")
