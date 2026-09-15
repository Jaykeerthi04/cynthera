import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, ".")

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.enums.trial_attribution import TrialDrugRole
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.engineering.retrieval.disease_relation import (
    classify_disease_relation,
    matches_for_approval_anchor,
)
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
    evaluate_trial_attribution,
    matches_disease_condition,
)
from backend.reasoning.orchestrator.decision_rules import apply_decision_rules

CACHE_DIR = Path("data/ct_raw_cache")
RESULTS_100_PATH = Path("evaluation_outputs/100_case_final/results.jsonl")
RESOLVED_50_PATH = Path("scratch/resolved_50_cases.json")

RECOMMENDATION_TO_3CLASS = {
    "PROMISING": "SUPPORT",
    "NOT_RECOMMENDED": "OPPOSE",
    "UNCERTAIN": "UNCERTAIN",
    "INSUFFICIENT_DATA": "UNCERTAIN",
}

# 1. Load data
with open(RESOLVED_50_PATH, "r", encoding="utf-8") as f:
    resolved_50 = json.load(f)

baseline_100 = {}
with open(RESULTS_100_PATH, "r", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        baseline_100[d["case_id"]] = d

# Baseline 50 post-CT run (BEFORE)
transitions_post_ct = {
    "TC-019": {"pred": "SUPPORT", "rec": "PROMISING", "rule": "Rule 1 (PROMISING)", "opp": 0.0},
    "TC-025": {"pred": "SUPPORT", "rec": "PROMISING", "rule": "Rule 1 (PROMISING)", "opp": 0.3187},
    "TC-043": {"pred": "OPPOSE", "rec": "NOT_RECOMMENDED", "rule": "Rule 2b (EMPIRICAL OPPOSITION VETO)", "opp": 0.5120},
    "TC-047": {"pred": "SUPPORT", "rec": "PROMISING", "rule": "Rule 1 (PROMISING)", "opp": 0.3700},
    "TC-053": {"pred": "SUPPORT", "rec": "PROMISING", "rule": "Rule 1 (PROMISING)", "opp": 0.0},
    "TC-062": {"pred": "SUPPORT", "rec": "PROMISING", "rule": "Rule 1 (PROMISING)", "opp": 0.0},
    "TC-072": {"pred": "OPPOSE", "rec": "NOT_RECOMMENDED", "rule": "Rule 2b (EMPIRICAL OPPOSITION VETO)", "opp": 0.5120},
}

before_cases = {}
for c in resolved_50:
    cid = c["case_id"]
    base = baseline_100[cid]
    if cid in transitions_post_ct:
        t = transitions_post_ct[cid]
        pred = t["pred"]
        rec = t["rec"]
        rule = t["rule"]
        opp = t["opp"]
    else:
        pred = base["prediction"]
        rec = base.get("recommendation", "UNCERTAIN")
        rule = base.get("decision_rule", "")
        opp = float(base.get("opposition_score", 0.0))
    
    before_cases[cid] = {
        "case_id": cid,
        "drug": c["drug"],
        "disease": c["disease"],
        "standard_gold": c["standard_gold"],
        "epistemic_gold": c["epistemic_gold"],
        "prediction": pred,
        "epistemic_prediction": pred,
        "support_score": float(base.get("support_score", 0.0)),
        "mechanistic_score": float(base.get("mechanistic_score", 0.0)),
        "risk_score": float(base.get("risk_score", 0.0)),
        "opposition_score": opp,
        "recommendation": rec,
        "decision_rule": rule,
    }

# 2. Evaluate NOW across all 50 cases
pipeline = RetrievalPipeline()
assessor = TherapeuticOppositionAssessor()

now_cases = {}
ct_diagnostics = {
    "total_trials_retrieved": 0,
    "total_trials_parsed": 0,
    "trials_with_results": 0,
    "total_trials_attributed": 0,
    "total_trials_rejected": 0,
    "genuine_negative_trials": 0,
    "neutral_trials": 0,
    "false_attributions": 0,
    "background_therapy_rejections": 0,
    "placebo_rejections": 0,
}

for c in resolved_50:
    cid = c["case_id"]
    drug = c["drug"]
    disease = c["disease"]
    std_gold = c["standard_gold"]
    epi_gold = c["epistemic_gold"]
    base_record = baseline_100[cid]

    # ClinicalTrials data
    safe_name = f"{re.sub(r'[^a-zA-Z0-9_]', '_', drug)}_{re.sub(r'[^a-zA-Z0-9_]', '_', disease)}.json"
    cache_path = CACHE_DIR / safe_name
    raw_trials = []
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                raw_trials = raw_data.get("studies", [])
        except Exception:
            raw_trials = []

    ct_diagnostics["total_trials_retrieved"] += len(raw_trials)

    drug_obj = Drug(name=drug, identifiers={"chembl": "CHEMBL_TEST"})
    disease_obj = Disease(name=disease, identifiers={"mesh": "MESH_TEST"})
    parsed_trials = pipeline._parse_trials_data(
        {"studies": raw_trials} if raw_trials else {}, drug_obj, disease_obj
    )
    ct_diagnostics["total_trials_parsed"] += len(parsed_trials)

    attributed_negative = []
    rejected_negative = []
    claims = []

    for t in parsed_trials:
        has_res = bool(t.has_results or t.outcome_measures)
        if has_res:
            ct_diagnostics["trials_with_results"] += 1

        is_neg = (
            t.is_negative_efficacy
            or t.status in (
                TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
                TrialOutcomeStatus.TERMINATED_SAFETY,
                TrialOutcomeStatus.COMPLETED_FAILURE,
            )
        )
        if not is_neg and has_res:
            ct_diagnostics["neutral_trials"] += 1

        attr = evaluate_trial_attribution(t, drug)
        claim = trial_to_negative_claim(t, drug, disease)
        if claim is not None:
            claims.append(claim)

        if attr.final_attribution_decision:
            ct_diagnostics["total_trials_attributed"] += 1
            if is_neg:
                attributed_negative.append(t)
                ct_diagnostics["genuine_negative_trials"] += 1
        else:
            ct_diagnostics["total_trials_rejected"] += 1
            if attr.drug_role == TrialDrugRole.BACKGROUND_CONSTANT_THERAPY:
                ct_diagnostics["background_therapy_rejections"] += 1
            elif attr.drug_role == TrialDrugRole.PLACEBO_COMPARATOR:
                ct_diagnostics["placebo_rejections"] += 1
            if is_neg:
                rejected_negative.append(t)

    # Opposition Assessment
    opp_assess = assessor.assess(claims=claims, drug_name=drug, disease_name=disease)

    # Approval Anchor
    baseline_rule = str(base_record.get("decision_rule", ""))
    m_term = re.search(r"Matched ChEMBL term: '([^']+)'", baseline_rule)
    matched_term = m_term.group(1) if m_term else None
    if matched_term:
        is_anchor = matches_for_approval_anchor(disease, matched_term)
    else:
        is_anchor = False

    # Evidence scores
    ss = float(base_record.get("support_score", 0.0))
    ms = float(base_record.get("mechanistic_score", 0.0))
    rs = float(base_record.get("risk_score", 0.0))
    safety_veto = bool(base_record.get("safety_veto", False))
    strong_conflict = bool(base_record.get("strong_conflict", False))
    contra_level = str(base_record.get("contradiction_level", "NONE"))
    has_high_qual = bool(base_record.get("high_quality_therapeutic_evidence", False))
    failed_cnt = len(attributed_negative)

    # Authoritative Rule Engine
    decision = apply_decision_rules(
        is_approved=is_anchor,
        matched_chembl_term=matched_term,
        support_score=ss,
        mechanistic_score=ms,
        risk_score=rs,
        safety_veto=safety_veto,
        strong_conflict=strong_conflict,
        contradiction_level=contra_level,
        has_high_quality_therapeutic=has_high_qual,
        opp_assessment=opp_assess,
        failed_trial_count=failed_cnt,
    )
    rec_status = decision.status.value if hasattr(decision.status, "value") else str(decision.status)
    dec_rule = decision.deciding_rule
    now_pred = RECOMMENDATION_TO_3CLASS.get(rec_status, "UNCERTAIN")

    now_cases[cid] = {
        "case_id": cid,
        "drug": drug,
        "disease": disease,
        "standard_gold": std_gold,
        "epistemic_gold": epi_gold,
        "prediction": now_pred,
        "epistemic_prediction": now_pred,
        "support_score": round(ss, 4),
        "mechanistic_score": round(ms, 4),
        "risk_score": round(rs, 4),
        "opposition_score": round(float(opp_assess.score), 4),
        "recommendation": rec_status,
        "decision_rule": dec_rule,
        "approval_anchor": is_anchor,
        "safety_veto": safety_veto,
        "contradiction_level": contra_level,
        "has_high_quality_therapeutic": has_high_qual,
        "trials_retrieved": len(raw_trials),
        "trials_parsed": len(parsed_trials),
        "attributed_negatives": len(attributed_negative),
        "negative_claims": len(claims),
    }

print("Completed NOW evaluation for all 50 cases.")
with open("scratch/now_50_eval_raw.json", "w", encoding="utf-8") as f:
    json.dump({"now_cases": now_cases, "before_cases": before_cases, "ct_diagnostics": ct_diagnostics}, f, indent=2)
print("Saved scratch/now_50_eval_raw.json.")
