"""Targeted validation script for Step 14.

Runs the pipeline with updated statistical direction semantics on the 7 required cases:
- TC-043 Rosiglitazone -> Type 2 diabetes
- TC-072 Empagliflozin -> Heart failure
- TC-025 Interferon beta-1a -> COVID-19
- TC-053 Pembrolizumab -> Glioblastoma
- TC-023 Azithromycin -> COVID-19
- TC-026 Niacin -> Cardiovascular disease
- TC-030 Dexamethasone -> Traumatic brain injury
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.engineering.retrieval.disease_relation import matches_for_approval_anchor
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
    evaluate_trial_attribution,
)
from backend.reasoning.orchestrator.decision_rules import apply_decision_rules

TARGET_CASES = [
    "TC-043",  # Rosiglitazone -> Type 2 diabetes
    "TC-072",  # Empagliflozin -> Heart failure
    "TC-025",  # Interferon beta-1a -> COVID-19
    "TC-053",  # Pembrolizumab -> Glioblastoma
    "TC-023",  # Azithromycin -> COVID-19
    "TC-026",  # Niacin -> Cardiovascular disease
    "TC-030",  # Dexamethasone -> Traumatic brain injury
]

# Load baseline ledger
ledger_path = Path("backend/evaluation/post_clinicaltrials_50_fast_ledger.json")
with open(ledger_path, "r", encoding="utf-8") as f:
    ledger = json.load(f)

cases_dict = {c["case_id"]: c for c in ledger["cases"]}

# Load cache
ct_cache_dir = Path("data/ct_raw_cache")
pipe = RetrievalPipeline(db_path=":memory:")
assessor = TherapeuticOppositionAssessor()

print("=" * 80)
print("TARGETED VALIDATION RESULTS (7 CASES)")
print("=" * 80)

results = []

for cid in TARGET_CASES:
    b = cases_dict.get(cid)
    if not b:
        print(f"Case {cid} not found in ledger")
        continue

    drug = b["drug"]
    disease = b["disease"]
    std_gold = b["standard_gold"]

    # Match cache file
    cache_file = None
    drug_norm = drug.lower().replace("-", "_").replace(" ", "_")
    disease_norm = disease.lower().replace("-", "_").replace(" ", "_")
    for cf in ct_cache_dir.glob("*.json"):
        cf_stem = cf.stem.lower().replace("-", "_")
        if drug_norm in cf_stem and (disease_norm[:5] in cf_stem or disease_norm in cf_stem):
            cache_file = cf
            break

    if not cache_file:
        for cf in ct_cache_dir.glob("*.json"):
            cf_stem = cf.stem.lower().replace("-", "_")
            if drug_norm in cf_stem:
                cache_file = cf
                break

    if not cache_file or not cache_file.exists():
        print(f"[{cid}] Cache file not found for {drug} -> {disease}")
        continue

    with open(cache_file, "r", encoding="utf-8") as f:
        raw_ct = json.load(f)

    parsed_trials = pipe._parse_trials_data(raw_ct, Drug(name=drug, identifiers={"chembl": "X"}), Disease(name=disease, identifiers={"mesh": "Y"}))

    claims = []
    attributed_neg_trials = []
    neutral_trials = []
    for t in parsed_trials:
        claim = trial_to_negative_claim(t, drug, disease)
        attr = evaluate_trial_attribution(t, drug)
        if claim is not None:
            claims.append(claim)
            attributed_neg_trials.append(t.nct_id)
        if any(om.get("direction") == "NEUTRAL" for om in t.outcome_measures):
            neutral_trials.append(t.nct_id)

    opp_assess = assessor.assess(claims=claims, drug_name=drug, disease_name=disease)

    # Re-evaluate approval anchor
    baseline_rule = str(b.get("decision_rule", ""))
    m_term = re.search(r"Matched ChEMBL term: '([^']+)'", baseline_rule)
    matched_term = m_term.group(1) if m_term else None
    is_anchor = matches_for_approval_anchor(disease, matched_term) if matched_term else False

    decision = apply_decision_rules(
        is_approved=is_anchor,
        matched_chembl_term=matched_term,
        support_score=float(b.get("support_score", 0.0)),
        mechanistic_score=float(b.get("mechanistic_score", 0.0)),
        risk_score=float(b.get("risk_score", 0.0)),
        safety_veto=bool(b.get("safety_veto", False)),
        strong_conflict=bool(b.get("strong_conflict", False)),
        contradiction_level=str(b.get("contradiction_level", "NONE")),
        has_high_quality_therapeutic=bool(b.get("high_quality_therapeutic_evidence", False)),
        opp_assessment=opp_assess,
        failed_trial_count=len(attributed_neg_trials),
    )

    rec_status = decision.status.value if hasattr(decision.status, "value") else str(decision.status)
    mapping = {"PROMISING": "SUPPORT", "NOT_RECOMMENDED": "OPPOSE", "UNCERTAIN": "UNCERTAIN", "INSUFFICIENT_DATA": "UNCERTAIN"}
    new_pred = mapping.get(rec_status, "UNCERTAIN")

    print(f"[{cid}] {drug} -> {disease}")
    print(f"  Gold: {std_gold}")
    print(f"  Old Post-CT: Pred={b['prediction']}, OppScore={b['opposition_score']}, AttributedNegTrials={b['attributed_negative_trials']}")
    print(f"  New Post-Fix: Pred={new_pred} ({rec_status}), OppScore={opp_assess.score:.4f} ({opp_assess.level}), AttributedNegTrials={len(attributed_neg_trials)}")
    print(f"  Deciding Rule: {decision.deciding_rule}")
    print(f"  Negative Claims: {len(claims)} (NCTs: {attributed_neg_trials})")
    print(f"  Neutral Trials: {len(neutral_trials)}")
    print("-" * 80)

    results.append({
        "case_id": cid,
        "drug": drug,
        "disease": disease,
        "gold": std_gold,
        "old_pred": b["prediction"],
        "old_opp": b["opposition_score"],
        "new_pred": new_pred,
        "new_opp": opp_assess.score,
        "rule": decision.deciding_rule,
        "negative_claims": len(claims),
        "attributed_trials": attributed_neg_trials,
    })
