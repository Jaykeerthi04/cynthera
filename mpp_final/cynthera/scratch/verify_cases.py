"""Targeted verification script for Section 22 & 23 cases.

Verifies:
1. TC-026 Niacin -> Cardiovascular disease (NCT00120289 index 37)
2. TC-030 Dexamethasone -> Traumatic brain injury (NCT02362321)
3. TC-053 Pembrolizumab -> Glioblastoma
4. TC-082 Aspirin -> Hemorrhagic stroke (Rule -1 anchor check)
5. Pioglitazone -> Alzheimer's disease (NCT02284906)
6. Nivolumab -> Glioblastoma (CheckMate 498 NCT02667587 & CheckMate 143 NCT02617589)
7. Metformin -> Type 2 diabetes (background therapy check)
"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
    evaluate_trial_attribution,
    TherapeuticOppositionAssessor,
    matches_disease_condition,
)
from backend.engineering.retrieval.disease_relation import (
    classify_disease_relation,
    matches_for_approval_anchor,
    matches_for_trial_attribution,
    DiseaseRelation,
)

TARGET_CASES = [
    ("Niacin", "Cardiovascular disease"),
    ("Dexamethasone", "Traumatic brain injury"),
    ("Pembrolizumab", "Glioblastoma"),
    ("Aspirin", "Hemorrhagic stroke"),
    ("Pioglitazone", "Alzheimer's disease"),
    ("Nivolumab", "Glioblastoma"),
    ("Metformin", "Type 2 diabetes"),
]

async def verify_all():
    print("=" * 80)
    print("VERIFYING TARGETED REAL CASES (SECTIONS 22 & 23)")
    print("=" * 80)

    # 1. Aspirin -> Hemorrhagic stroke check (Approval Anchor & Trial Matching)
    print("\n--- 1. TC-082 Aspirin -> Hemorrhagic stroke ---")
    rel = classify_disease_relation("stroke", "hemorrhagic stroke")
    appr_match = matches_for_approval_anchor("stroke", "hemorrhagic stroke")
    trial_match = matches_for_trial_attribution("stroke", "hemorrhagic stroke")
    print(f"Disease relation ('stroke', 'hemorrhagic stroke'): {rel.value}")
    print(f"matches_for_approval_anchor: {appr_match} (Expected: False - NO anchor granted!)")
    print(f"matches_for_trial_attribution: {trial_match} (Expected: False - SIBLING_EXCLUDED!)")
    assert appr_match is False, "Aspirin stroke -> hemorrhagic stroke must NOT match for approval anchor"
    assert trial_match is False, "Aspirin stroke -> hemorrhagic stroke must NOT match for trial attribution"
    print("[PASS] Aspirin -> Hemorrhagic stroke Rule -1 anchor is strictly BLOCKED.")

    # 2. Dexamethasone -> Traumatic brain injury disease relation check
    print("\n--- 2. TC-030 Dexamethasone -> Traumatic brain injury disease relation ---")
    rel_tbi = classify_disease_relation("traumatic brain injury", "subdural hematoma, chronic")
    trial_match_tbi = matches_for_trial_attribution("traumatic brain injury", "subdural hematoma, chronic")
    print(f"Relation ('traumatic brain injury', 'subdural hematoma, chronic'): {rel_tbi.value}")
    print(f"matches_for_trial_attribution: {trial_match_tbi} (Expected: True)")
    assert trial_match_tbi is True, "Subdural hematoma must match TBI for trial attribution"
    print("[PASS] Dexamethasone TBI -> Subdural hematoma relation verified.")

    pipeline = RetrievalPipeline()
    assessor = TherapeuticOppositionAssessor()

    # 3. Verify live ClinicalTrials.gov parsing & attribution for target cases
    for drug_name, disease_name in TARGET_CASES:
        if drug_name == "Aspirin" and disease_name == "Hemorrhagic stroke":
            continue
        print(f"\n--- Fetching & evaluating: {drug_name} -> {disease_name} ---")
        try:
            async with ClinicalTrialsConnector() as conn:
                data = await conn.fetch(drug_name, disease_name, max_results=50)
            studies = data.get("studies", [])
            print(f"Total retrieved studies: {len(studies)}")
            
            drug_obj = Drug(name=drug_name, identifiers={"chembl": "CHEMBL_TEST"})
            disease_obj = Disease(name=disease_name, identifiers={"mesh": "MESH_TEST"})
            parsed_trials = pipeline._parse_trials_data(data, drug_obj, disease_obj)
            print(f"Total parsed trials: {len(parsed_trials)}")

            # Check specific NCT IDs or key trials
            nct_list = [t.nct_id for t in parsed_trials]
            if drug_name == "Niacin":
                print(f"  AIM-HIGH NCT00120289 present in parsed trials: {'NCT00120289' in nct_list}")
                aim = next((t for t in parsed_trials if t.nct_id == "NCT00120289"), None)
                if aim:
                    attr = evaluate_trial_attribution(aim, drug_name)
                    claim = trial_to_negative_claim(aim, drug_name, disease_name)
                    print(f"  NCT00120289 status: {aim.status}, neg_eff: {aim.is_negative_efficacy}")
                    print(f"  NCT00120289 attribution: {attr.final_attribution_decision}, role: {attr.drug_role.value}")
                    print(f"  NCT00120289 negative claim generated: {claim is not None}")

            elif drug_name == "Nivolumab":
                checkmates = [nct for nct in ["NCT02667587", "NCT02617589"] if nct in nct_list]
                print(f"  CheckMate trials present: {checkmates}")
                for nct in checkmates:
                    t = next(tr for tr in parsed_trials if tr.nct_id == nct)
                    attr = evaluate_trial_attribution(t, drug_name)
                    claim = trial_to_negative_claim(t, drug_name, disease_name)
                    print(f"  [{nct}] status: {t.status}, neg_eff: {t.is_negative_efficacy}, why_stopped: {t.why_stopped}")
                    print(f"  [{nct}] attribution: {attr.final_attribution_decision}, role: {attr.drug_role.value}")
                    print(f"  [{nct}] negative claim generated: {claim is not None}")

            elif drug_name == "Pioglitazone":
                tommorrow = next((t for t in parsed_trials if t.nct_id == "NCT02284906"), None)
                print(f"  TOMMORROW NCT02284906 present: {tommorrow is not None}")
                if tommorrow:
                    attr = evaluate_trial_attribution(tommorrow, drug_name)
                    claim = trial_to_negative_claim(tommorrow, drug_name, disease_name)
                    print(f"  NCT02284906 status: {tommorrow.status}, why_stopped: {tommorrow.why_stopped}")
                    print(f"  NCT02284906 attribution: {attr.final_attribution_decision}, role: {attr.drug_role.value}")
                    print(f"  NCT02284906 negative claim generated: {claim is not None}")

            elif drug_name == "Metformin":
                print(f"  Evaluating Metformin -> T2D attribution protection...")
                attr_counts = {"ATTRIBUTED": 0, "NOT_ATTRIBUTED": 0}
                for t in parsed_trials:
                    attr = evaluate_trial_attribution(t, drug_name)
                    if attr.final_attribution_decision:
                        attr_counts["ATTRIBUTED"] += 1
                    else:
                        attr_counts["NOT_ATTRIBUTED"] += 1
                print(f"  Metformin trial attribution counts: {attr_counts}")

            claims = []
            for t in parsed_trials:
                c = trial_to_negative_claim(t, drug_name, disease_name)
                if c:
                    claims.append(c)
            print(f"  Total negative claims generated: {len(claims)}")
            assessment = assessor.assess(claims, drug_name, disease_name)
            print(f"  Opposition Score: {assessment.score:.3f}, Level: {assessment.level}")

        except Exception as e:
            print(f"  Error fetching/evaluating {drug_name}: {e}")

if __name__ == "__main__":
    asyncio.run(verify_all())
