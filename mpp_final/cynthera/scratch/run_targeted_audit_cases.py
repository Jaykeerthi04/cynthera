import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.enums.recommendation import RecommendationStatus
from backend.engineering.retrieval.disease_relation import matches_for_approval_anchor
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
)
from backend.reasoning.orchestrator.decision_rules import apply_decision_rules
from backend.evaluation.run_50_case_post_clinicaltrials_fast import (
    apply_decision_rules as fast_apply_rules,
    RECOMMENDATION_TO_3CLASS,
)

TARGET_CASES = [
    ("TC-001", "Lisinopril", "Hypertension", "SUPPORT"),
    ("TC-003", "Budesonide", "Asthma", "SUPPORT"),
    ("TC-026", "Niacin", "Cardiovascular disease", "UNCERTAIN"),
    ("TC-030", "Dexamethasone", "Traumatic brain injury", "OPPOSE"),
    ("TC-052", "Nivolumab", "Glioblastoma", "OPPOSE"),
    ("TC-062", "Ranibizumab", "Age-related macular degeneration", "SUPPORT"),
    ("TC-024", "Aspirin", "Hemorrhagic stroke", "OPPOSE"),
    ("TC-022", "Hydroxychloroquine", "COVID-19", "UNCERTAIN"),
]

def run_targeted():
    # Load 100_case results.jsonl for baseline / canonical signals
    results_by_cid = {}
    with open("evaluation_outputs/100_case_final/results.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            results_by_cid[d["case_id"]] = d

    print("=" * 120)
    print(f"{'Case':<8} | {'Drug':<18} | {'Disease':<32} | {'Gold':<8} | {'Pred':<8} | {'Opp':<6} | {'Anchor':<7} | {'Deciding Rule'}")
    print("=" * 120)

    audit_records = []

    for cid, drug, disease, gold in TARGET_CASES:
        b = results_by_cid.get(cid, {})
        assert b, f"Missing {cid} in results.jsonl"

        # Cached CT trials
        clean_drug = re.sub(r'[^a-zA-Z0-9_]', '_', drug)
        clean_disease = re.sub(r'[^a-zA-Z0-9_]', '_', disease)
        cache_path = Path(f"data/ct_raw_cache/{clean_drug}_{clean_disease}.json")
        if not cache_path.exists():
            # Try alternate naming
            matches = list(Path("data/ct_raw_cache").glob(f"*{clean_drug}*.json"))
            if matches:
                cache_path = matches[0]

        parsed_trials = []
        if cache_path.exists():
            raw_ct = json.loads(cache_path.read_text(encoding="utf-8"))
            pipe = RetrievalPipeline()
            parsed_trials = pipe._parse_trials_data(
                raw_ct,
                Drug(name=drug, identifiers={}),
                Disease(name=disease, identifiers={}),
            )

        claims = [trial_to_negative_claim(t, drug, disease) for t in parsed_trials]
        claims = [c for c in claims if c]
        opp_assessor = TherapeuticOppositionAssessor()
        opp_assess = opp_assessor.assess(claims, drug, disease)

        # Approval anchor
        baseline_rule = str(b.get("decision_rule", ""))
        m_term = re.search(r"Matched ChEMBL term: '([^']+)'", baseline_rule)
        matched_term = m_term.group(1) if m_term else (b.get("matched_indication_term") or None)
        is_anchor = matches_for_approval_anchor(disease, matched_term) if matched_term else False

        dec = fast_apply_rules(
            is_approved=is_anchor,
            matched_chembl_term=matched_term,
            support_score=float(b.get("support_score", 0.0)),
            mechanistic_score=float(b.get("mechanistic_score", 0.0)),
            risk_score=float(b.get("risk_score", 0.0)),
            opp_assessment=opp_assess,
        )

        pred = (
            "SUPPORT"
            if dec.status == RecommendationStatus.PROMISING
            else "OPPOSE"
            if dec.status == RecommendationStatus.NOT_RECOMMENDED
            else "UNCERTAIN"
        )

        rule_short = dec.deciding_rule.split(":")[0].strip()
        print(f"{cid:<8} | {drug:<18} | {disease[:32]:<32} | {gold:<8} | {pred:<8} | {opp_assess.score:<6.3f} | {str(is_anchor):<7} | {rule_short}")

        audit_records.append({
            "case_id": cid,
            "drug": drug,
            "disease": disease,
            "gold": gold,
            "prediction": pred,
            "recommendation_status": dec.status.value,
            "opposition_score": opp_assess.score,
            "opposition_level": opp_assess.level,
            "approved_anchor": is_anchor,
            "matched_chembl_term": matched_term,
            "deciding_rule": dec.deciding_rule,
            "correct": (pred == gold),
        })

    print("=" * 120)
    with open("scratch/targeted_audit_results.json", "w", encoding="utf-8") as f:
        json.dump(audit_records, f, indent=2)

    return audit_records

if __name__ == "__main__":
    run_targeted()
