import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
    evaluate_trial_attribution,
    determine_trial_evidence_type,
)
from backend.reasoning.conflict.evidence_weighting import (
    compute_claim_weight,
    evidence_group_key,
    cluster_into_evidence_groups,
    group_weight,
    EVIDENCE_TYPE_WEIGHTS,
)

# ── P0.1: Trace Lisinopril -> Hypertension ──
print("=" * 80)
print("P0.1: TRACE LISINOPRIL -> HYPERTENSION END-TO-END")
print("=" * 80)

safe_name = "Lisinopril_Hypertension.json"
cache_path = Path("data/ct_raw_cache") / safe_name
raw_data = json.load(open(cache_path, "r", encoding="utf-8"))
studies = raw_data.get("studies", [])

pipeline = RetrievalPipeline()
drug_obj = Drug(name="Lisinopril", identifiers={"chembl": "CHEMBL_TEST"})
disease_obj = Disease(name="Hypertension", identifiers={"mesh": "MESH_TEST"})
parsed_trials = pipeline._parse_trials_data({"studies": studies}, drug_obj, disease_obj)

print(f"Total raw studies: {len(studies)}")
print(f"Total parsed trials: {len(parsed_trials)}")

claims = []
for idx, t in enumerate(parsed_trials):
    c = trial_to_negative_claim(t, "Lisinopril", "Hypertension")
    if c is not None:
        attr = evaluate_trial_attribution(t, "Lisinopril")
        claims.append((t, c, attr, idx))

print(f"Negative claims generated: {len(claims)}")
for t, c, attr, idx in claims:
    print(f"\n--- Claim from trial {t.nct_id} (index {idx}) ---")
    print(f"  Title: {t.title}")
    print(f"  Status: {t.status}")
    print(f"  why_stopped: {getattr(t, 'why_stopped', None)}")
    print(f"  Predicate: {c.predicate}")
    print(f"  Confidence: {c.confidence}")
    print(f"  ERW: {c.erw.value}")
    print(f"  Evidence Type: {c.evidence_type}")
    print(f"  Evidence Type Multiplier: {EVIDENCE_TYPE_WEIGHTS.get(str(c.evidence_type), 0.5)}")
    print(f"  Recency Multiplier: 1.0 (no pub_year)")
    cw = compute_claim_weight(c)
    print(f"  Final Claim Weight: {cw}")
    gk = evidence_group_key(c)
    print(f"  evidence_group_key: {gk}")
    print(f"  provenance.record_id: {c.provenance.record_id}")
    print(f"  Attribution Decision: {attr.final_attribution_decision}")
    print(f"  Drug Role: {attr.drug_role}")
    print(f"  Attribution Reason: {attr.attribution_reason}")

groups = cluster_into_evidence_groups([c for _, c, _, _ in claims])
print(f"\nUnique independent groups: {len(groups)}")
for gk, g_claims in groups.items():
    gw = group_weight(g_claims)
    print(f"  Group '{gk}': {len(g_claims)} claim(s), weight = {gw}")

assessor = TherapeuticOppositionAssessor()
assessment = assessor.assess([c for _, c, _, _ in claims], "Lisinopril", "Hypertension")
print(f"\nOpposition Assessment Result:")
print(f"  Score: {assessment.score}")
print(f"  Level: {assessment.level}")
print(f"  Rationale: {assessment.rationale}")
