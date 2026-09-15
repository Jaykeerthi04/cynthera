"""Deep dive into NCT02667587, NCT02362321, and NCT01474486."""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    trial_to_negative_claim,
    evaluate_trial_attribution,
    analyze_trial_drug_role,
    matches_disease_condition,
)

async def probe_specific_trials():
    pipeline = RetrievalPipeline()

    # 1. Nivolumab in Glioblastoma (NCT02667587)
    print("\n--- PROBE 1: Nivolumab -> Glioblastoma (NCT02667587) ---")
    async with ClinicalTrialsConnector() as conn:
        data = await conn.fetch("Nivolumab", "Glioblastoma", max_results=20)
    for study in data.get("studies", []):
        nct = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
        if nct == "NCT02667587":
            drug_obj = Drug(name="Nivolumab", identifiers={"chembl": "CHEMBL_TEST"})
            disease_obj = Disease(name="Glioblastoma", identifiers={"mesh": "MESH_TEST"})
            trials = pipeline._parse_trials_data({"studies": [study]}, drug_obj, disease_obj)
            t = trials[0]
            print(f"Title: {t.title}")
            print(f"Interventions: {t.intervention_names}")
            print(f"Comparators: {t.comparator_names}")
            print(f"Conditions: {t.condition_names}")
            print(f"is_negative_efficacy: {t.is_negative_efficacy}")
            print(f"neg_reason: {t.negative_efficacy_reason}")
            role, i_m, c_m, is_diff, reason = analyze_trial_drug_role(t, "Nivolumab")
            print(f"analyze_trial_drug_role: Role={role}, Diff={is_diff}, Reason={reason}")
            attr = evaluate_trial_attribution(t, "Nivolumab")
            print(f"evaluate_trial_attribution: Decision={attr.final_attribution_decision}, Reason={attr.attribution_reason}")
            claim = trial_to_negative_claim(t, "Nivolumab", "Glioblastoma")
            print(f"trial_to_negative_claim: {claim is not None}")

    # 2. Dexamethasone in TBI (NCT02362321)
    print("\n--- PROBE 2: Dexamethasone -> Traumatic brain injury (NCT02362321) ---")
    async with ClinicalTrialsConnector() as conn:
        data = await conn.fetch("Dexamethasone", "Traumatic brain injury", max_results=10)
    for study in data.get("studies", []):
        nct = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
        if nct == "NCT02362321":
            drug_obj = Drug(name="Dexamethasone", identifiers={"chembl": "CHEMBL_TEST"})
            disease_obj = Disease(name="Traumatic brain injury", identifiers={"mesh": "MESH_TEST"})
            trials = pipeline._parse_trials_data({"studies": [study]}, drug_obj, disease_obj)
            t = trials[0]
            print(f"Title: {t.title}")
            print(f"Status: {t.status}")
            print(f"why_stopped: {t.why_stopped}")
            print(f"Conditions: {t.condition_names}")
            matches_cond = matches_disease_condition(t, "Traumatic brain injury")
            print(f"matches_disease_condition('Traumatic brain injury'): {matches_cond}")
            attr = evaluate_trial_attribution(t, "Dexamethasone")
            print(f"evaluate_trial_attribution: Decision={attr.final_attribution_decision}, Reason={attr.attribution_reason}")
            claim = trial_to_negative_claim(t, "Dexamethasone", "Traumatic brain injury")
            print(f"trial_to_negative_claim: {claim is not None}")

    # 3. Niacin in CVD (NCT01474486)
    print("\n--- PROBE 3: Niacin -> Cardiovascular disease (NCT01474486) ---")
    async with ClinicalTrialsConnector() as conn:
        data = await conn.fetch("Niacin", "Cardiovascular disease", max_results=20)
    for study in data.get("studies", []):
        nct = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
        if nct == "NCT01474486":
            drug_obj = Drug(name="Niacin", identifiers={"chembl": "CHEMBL_TEST"})
            disease_obj = Disease(name="Cardiovascular disease", identifiers={"mesh": "MESH_TEST"})
            trials = pipeline._parse_trials_data({"studies": [study]}, drug_obj, disease_obj)
            t = trials[0]
            print(f"Title: {t.title}")
            print(f"Interventions: {t.intervention_names}")
            print(f"Comparators: {t.comparator_names}")
            attr = evaluate_trial_attribution(t, "Niacin")
            print(f"evaluate_trial_attribution: Decision={attr.final_attribution_decision}, Role={attr.drug_role.value}, Reason={attr.attribution_reason}")

if __name__ == "__main__":
    asyncio.run(probe_specific_trials())
