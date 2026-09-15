import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.hypothesis import Hypothesis
from backend.evaluation.benchmark_models import BenchmarkCase
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.core.enums.recommendation import RecommendationStatus
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.engineering.retrieval.disease_relation import (
    classify_disease_relation,
    matches_for_approval_anchor,
    normalize_disease_term,
)
from backend.reasoning.opposition.therapeutic_opposition_assessor import (
    TherapeuticOppositionAssessor,
    trial_to_negative_claim,
)
from backend.reasoning.opposition.opposition_qualification import qualify_opposition_claim
from backend.reasoning.orchestrator.decision_rules import apply_decision_rules
from backend.evaluation.benchmark_runner import BenchmarkRunner


async def run_diagnostics():
    drug = "Ranibizumab"
    disease = "Age-related macular degeneration"
    cid = "TC-062"

    print("=" * 80)
    print("TC-062 SOURCE TRACE: NCT02611778")
    print("=" * 80)

    # Load cached CT.gov trial for Ranibizumab
    cache_path = Path("data/ct_raw_cache/Ranibizumab_Age_related_macular_degeneration.json")
    raw_ct = json.loads(cache_path.read_text(encoding="utf-8"))

    pipe = RetrievalPipeline()
    parsed_trials = pipe._parse_trials_data(
        raw_ct,
        Drug(name=drug, identifiers={"chembl": "CHEMBL1201825"}),
        Disease(name=disease, identifiers={"mesh": "D008268"}),
    )

    t_target = None
    for t in parsed_trials:
        if t.nct_id == "NCT02611778":
            t_target = t
            break

    if t_target:
        print(f"Title: {t_target.title}")
        print(f"Status: {t_target.status}")
        print(f"Interventions: {t_target.intervention_names}")
        print(f"Comparators: {t_target.comparator_names}")
        print(f"Outcomes: {t_target.outcome_measures}")

        claim = trial_to_negative_claim(t_target, drug, disease)
        print(f"Negative Claim Generated: {claim is not None}")
        if claim:
            qual = qualify_opposition_claim(claim, drug, disease, t_target)
            print(f"Qualification Category: {qual.reason_code}")
            print(f"Qualified: {qual.qualified}")
            print(f"Replication Eligible: {qual.replication_eligible}")
            print(f"Explanation: {qual.explanation}")
    else:
        print("NCT02611778 NOT FOUND in parsed trials!")

    assessor = TherapeuticOppositionAssessor()
    claims = []
    for t in parsed_trials:
        c = trial_to_negative_claim(t, drug, disease)
        if c:
            claims.append(c)
    opp_assessment = assessor.assess(claims, drug, disease)
    print(f"\nOpposition Assessment:")
    print(f"  Score: {opp_assessment.score}")
    print(f"  Level: {opp_assessment.level}")
    print(f"  Groups: {opp_assessment.independent_group_count}")
    print(f"  Qualified claims count: {len(opp_assessment.qualified_claims)}")

    print("\n" + "=" * 80)
    print("APPROVAL ANCHOR TRACE")
    print("=" * 80)
    print(f"Queried disease: '{disease}'")
    print(f"Normalized disease: '{normalize_disease_term(disease)}'")

    # Trace ChEMBL connector indications
    from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector
    async with ChEMBLConnector() as conn:
        chembl_inds = await conn.fetch_indications("CHEMBL1201825")
        chembl_mol = await conn.fetch_molecule_details("CHEMBL1201825")

    sig = pipe._parse_indication_data(chembl_inds, chembl_mol, disease)
    print(f"Pipeline ApprovalSignal from _parse_indication_data:")
    if sig:
        print(f"  is_approved: {sig.is_approved}")
        print(f"  max_phase: {sig.max_phase}")
        print(f"  matched_indication_term: '{sig.matched_indication_term}'")
        print(f"  match_confidence: {sig.match_confidence}")
        print(f"  relation: {sig.disease_relation}")
        print(f"  pathway: {sig.evaluation_pathway}")

    # Test individual terms
    for term in ["age-related macular degeneration", "wet macular degeneration", "macular degeneration"]:
        rel = classify_disease_relation(disease, term)
        anc = matches_for_approval_anchor(disease, term)
        print(f"Term '{term}': relation={rel.value}, is_anchor={anc}")

    print("\n" + "=" * 80)
    print("PATH COMPARISON")
    print("=" * 80)

    # Baseline file data
    b = {}
    with open("evaluation_outputs/100_case_final/results.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("case_id") == "TC-062":
                b = d
                break

    print(f"Baseline (from results.jsonl):")
    print(f"  decision_rule: {b.get('decision_rule')}")
    print(f"  prediction: {b.get('prediction')}")
    print(f"  is_approved_indication: {b.get('is_approved_indication')}")

    # Fast Evaluator simulation
    baseline_rule = str(b.get("decision_rule", ""))
    m_term = re.search(r"Matched ChEMBL term: '([^']+)'", baseline_rule)
    fast_matched_term = m_term.group(1) if m_term else None
    fast_is_anchor = matches_for_approval_anchor(disease, fast_matched_term) if fast_matched_term else False
    fast_dec = apply_decision_rules(
        is_approved=fast_is_anchor,
        matched_chembl_term=fast_matched_term,
        support_score=float(b.get("support_score", 0.0)),
        mechanistic_score=float(b.get("mechanistic_score", 0.0)),
        risk_score=float(b.get("risk_score", 0.0)),
        opp_assessment=opp_assessment,
    )
    print(f"\nFast Evaluator:")
    print(f"  matched_term: {fast_matched_term}")
    print(f"  is_anchor: {fast_is_anchor}")
    print(f"  decision_rule: {fast_dec.deciding_rule}")
    print(f"  status: {fast_dec.status}")

    # Targeted Evaluator simulation (validate_targeted_p0b2_cases.py)
    # in targeted script, cid == 'TC-062' sets candidate_term = 'wet macular degeneration'
    targ_matched_term = "wet macular degeneration"
    targ_is_anchor = matches_for_approval_anchor(disease, targ_matched_term)
    targ_dec = apply_decision_rules(
        is_approved=targ_is_anchor,
        matched_chembl_term=targ_matched_term,
        support_score=float(b.get("support_score", 0.0)),
        mechanistic_score=float(b.get("mechanistic_score", 0.0)),
        risk_score=float(b.get("risk_score", 0.0)),
        opp_assessment=opp_assessment,
    )
    print(f"\nTargeted Evaluator (with hardcoded candidate_term):")
    print(f"  matched_term: {targ_matched_term}")
    print(f"  is_anchor: {targ_is_anchor}")
    print(f"  decision_rule: {targ_dec.deciding_rule}")
    print(f"  status: {targ_dec.status}")


asyncio.run(run_diagnostics())
