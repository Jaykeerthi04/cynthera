"""Tests verifying absolute parity between production and evaluator decision engines.

Permanent Structural Fix:
- Eliminates evaluator rule-engine drift.
- Verifies that evaluators do not own a private rule cascade.
- Verifies that evaluator decision logic is identical to production.
- Tests representative scenarios including Rule 1c literature-only support.
- Regression tests the historical TC-025 / TC-053 Rule 1c divergence.
- Regression tests benchmark canonical field alignment vs recommendation.
"""
import ast
import inspect
from typing import Any
import pytest

from backend.core.enums.recommendation import RecommendationStatus
from backend.evaluation.benchmark_models import (
    BenchmarkClass,
    map_alignment_to_class,
    map_recommendation_to_class,
)
from backend.reasoning.orchestrator.decision_rules import (
    DecisionResult,
    apply_decision_rules,
)
from backend.reasoning.orchestrator.reasoning_orchestrator import (
    ReasoningOrchestrator,
    apply_decision_rules as PRODUCTION_APPLY_RULES,
)
import backend.evaluation.run_50_case_post_clinicaltrials_fast as fast_eval_module
from backend.evaluation.run_50_case_post_clinicaltrials_fast import (
    apply_decision_rules as EVALUATOR_APPLY_RULES,
)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: Identity & Implementation Guard
# ─────────────────────────────────────────────────────────────────────────────


def test_evaluator_uses_shared_production_rule_engine_identity():
    """Verify that evaluator's apply_decision_rules is physically the exact same object as production."""
    assert EVALUATOR_APPLY_RULES is not None, "EVALUATOR_APPLY_RULES must not be None"
    assert PRODUCTION_APPLY_RULES is not None, "PRODUCTION_APPLY_RULES must not be None"
    assert (
        EVALUATOR_APPLY_RULES is PRODUCTION_APPLY_RULES
    ), "Evaluator must import and use the exact shared production decision rules function"
    assert (
        EVALUATOR_APPLY_RULES is apply_decision_rules
    ), "Evaluator rule function must resolve to authoritative decision_rules.apply_decision_rules"


def test_no_local_decision_cascade_in_evaluator_source():
    """Verify via AST inspection that the fast evaluator does NOT define a local apply_decision_rules."""
    source_file = inspect.getsourcefile(fast_eval_module)
    with open(source_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=source_file)

    function_defs = [
        node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert (
        "apply_decision_rules" not in function_defs
    ), "run_50_case_post_clinicaltrials_fast.py must not define a local apply_decision_rules function"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 & 6: Representative Decision Rule Scenarios
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "scenario_name,kwargs,expected_status,expected_rule_prefix",
    [
        (
            "rule_1c_literature_only_must_not_promise",
            {
                "is_approved": False,
                "support_score": 0.85,
                "mechanistic_score": 0.75,
                "risk_score": 0.20,
                "has_high_quality_therapeutic": False,
                "opposition_score": 0.0,
            },
            RecommendationStatus.UNCERTAIN,
            "Rule 1c",
        ),
        (
            "rule_minus_one_approved_indication",
            {
                "is_approved": True,
                "matched_chembl_term": "Chronic myeloid leukemia",
                "support_score": 0.80,
                "mechanistic_score": 0.60,
                "risk_score": 0.20,
                "has_high_quality_therapeutic": False,
                "opposition_score": 0.0,
            },
            RecommendationStatus.PROMISING,
            "Rule -1",
        ),
        (
            "rule_1b_strong_support_and_strong_opposition_epistemic_conflict",
            {
                "is_approved": False,
                "support_score": 0.75,
                "mechanistic_score": 0.60,
                "risk_score": 0.20,
                "opposition_score": 0.65,
                "has_high_quality_therapeutic": False,
            },
            RecommendationStatus.UNCERTAIN,
            "Rule 1b",
        ),
        (
            "rule_2b_empirical_opposition_veto",
            {
                "is_approved": False,
                "support_score": 0.70,
                "mechanistic_score": 0.60,
                "risk_score": 0.20,
                "opposition_score": 0.52,
                "opposition_level": "MODERATE",
                "independent_group_count": 2,
                "has_high_quality_therapeutic": False,
            },
            RecommendationStatus.NOT_RECOMMENDED,
            "Rule 2b",
        ),
        (
            "rule_0_safety_veto_boxed_warning_or_risk",
            {
                "is_approved": False,
                "support_score": 0.70,
                "mechanistic_score": 0.60,
                "risk_score": 0.65,
                "safety_veto": True,
                "has_boxed_warning": True,
                "has_high_quality_therapeutic": False,
            },
            RecommendationStatus.NOT_RECOMMENDED,
            "Rule 0",
        ),
        (
            "rule_5_default_uncertain_sparse_evidence",
            {
                "is_approved": False,
                "support_score": 0.25,
                "mechanistic_score": 0.20,
                "risk_score": 0.15,
                "has_high_quality_therapeutic": False,
            },
            RecommendationStatus.UNCERTAIN,
            "Rule 5",
        ),
    ],
)
def test_production_and_evaluator_parity_representative_scenarios(
    scenario_name: str,
    kwargs: dict[str, Any],
    expected_status: RecommendationStatus,
    expected_rule_prefix: str,
):
    """Given identical inputs, production output MUST equal evaluator output."""
    prod_decision: DecisionResult = PRODUCTION_APPLY_RULES(**kwargs)
    eval_decision: DecisionResult = EVALUATOR_APPLY_RULES(**kwargs)

    # Parity assertions
    assert prod_decision.status == eval_decision.status, f"Parity mismatch in {scenario_name}"
    assert prod_decision.reasons == eval_decision.reasons, f"Reasons mismatch in {scenario_name}"
    assert prod_decision.trace == eval_decision.trace, f"Trace mismatch in {scenario_name}"

    # Semantics assertions
    assert prod_decision.status == expected_status, f"Status unexpected in {scenario_name}"
    assert prod_decision.deciding_rule.startswith(
        expected_rule_prefix
    ), f"Rule prefix unexpected in {scenario_name}: {prod_decision.deciding_rule}"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: Historical Rule 1c Regression Failure
# ─────────────────────────────────────────────────────────────────────────────


def test_historical_rule_1c_divergence_regression():
    """Historical Failure Case: High literature support without therapeutic anchor.

    In the old run_50_case_post_clinicaltrials_fast.py, apply_decision_rules omitted Rule 1c:
        if support_score >= 0.40 and mechanistic_score >= 0.40 and risk_score <= 0.39:
            return "PROMISING"
    This caused hypotheses like TC-025 (Interferon beta-1a -> COVID-19) and TC-053
    (Pembrolizumab -> Glioblastoma) to be evaluated as PROMISING instead of UNCERTAIN.

    Under the authoritative production rule engine, Rule 1c forces UNCERTAIN
    unless has_high_quality_therapeutic is True or is_approved is True.
    """
    inputs = {
        "is_approved": False,
        "support_score": 0.72,
        "mechanistic_score": 0.65,
        "risk_score": 0.25,
        "has_high_quality_therapeutic": False,
        "opposition_score": 0.0,
        "opposition_level": "NONE",
    }

    # Authoritative evaluation
    prod_res = PRODUCTION_APPLY_RULES(**inputs)
    eval_res = EVALUATOR_APPLY_RULES(**inputs)

    assert prod_res.status == RecommendationStatus.UNCERTAIN
    assert eval_res.status == RecommendationStatus.UNCERTAIN
    assert prod_res.status == eval_res.status
    assert "Rule 1c" in prod_res.deciding_rule
    assert "Rule 1c" in eval_res.deciding_rule


# ─────────────────────────────────────────────────────────────────────────────
# STEP 11: Historical Test Cases (TC-019, TC-025, TC-053, TC-062, TC-043, TC-072, TC-082)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case_id,drug,disease,kwargs,expected_status",
    [
        (
            "TC-019",
            "Imatinib",
            "Chronic myeloid leukemia",
            {
                "is_approved": True,
                "matched_chembl_term": "Chronic myeloid leukemia",
                "support_score": 0.88,
                "mechanistic_score": 0.75,
                "risk_score": 0.15,
                "has_high_quality_therapeutic": True,
            },
            RecommendationStatus.PROMISING,
        ),
        (
            "TC-025",
            "Interferon beta-1a",
            "COVID-19",
            {
                "is_approved": False,
                "support_score": 0.65,
                "mechanistic_score": 0.55,
                "risk_score": 0.30,
                "has_high_quality_therapeutic": False,
                "opposition_score": 0.0,
            },
            RecommendationStatus.UNCERTAIN,  # Rule 1c gate prevents false PROMISING
        ),
        (
            "TC-053",
            "Pembrolizumab",
            "Glioblastoma",
            {
                "is_approved": False,
                "support_score": 0.60,
                "mechanistic_score": 0.50,
                "risk_score": 0.35,
                "has_high_quality_therapeutic": False,
                "opposition_score": 0.10,
            },
            RecommendationStatus.UNCERTAIN,  # Rule 1c gate prevents false PROMISING
        ),
        (
            "TC-062",
            "Ranibizumab",
            "Age-related macular degeneration",
            {
                "is_approved": True,
                "matched_chembl_term": "Wet age-related macular degeneration",
                "support_score": 0.90,
                "mechanistic_score": 0.80,
                "risk_score": 0.10,
                "has_high_quality_therapeutic": True,
            },
            RecommendationStatus.PROMISING,
        ),
        (
            "TC-043",
            "Rosiglitazone",
            "Type 2 diabetes mellitus",
            {
                "is_approved": True,
                "matched_chembl_term": "Type 2 diabetes mellitus",
                "support_score": 0.80,
                "mechanistic_score": 0.70,
                "risk_score": 0.65,
                "has_boxed_warning": True,
                "safety_veto": True,
            },
            RecommendationStatus.NOT_RECOMMENDED,  # Rule 0 override for boxed warning + high RS
        ),
        (
            "TC-072",
            "Empagliflozin",
            "Heart failure",
            {
                "is_approved": True,
                "matched_chembl_term": "Heart failure",
                "support_score": 0.85,
                "mechanistic_score": 0.70,
                "risk_score": 0.20,
                "has_high_quality_therapeutic": True,
            },
            RecommendationStatus.PROMISING,
        ),
        (
            "TC-082",
            "Aspirin",
            "Hemorrhagic stroke",
            {
                "is_approved": False,
                "support_score": 0.30,
                "mechanistic_score": 0.20,
                "risk_score": 0.65,
                "opposition_score": 0.70,
                "opposition_level": "HIGH",
                "safety_veto": True,
            },
            RecommendationStatus.NOT_RECOMMENDED,  # Safety veto & empirical opposition
        ),
    ],
)
def test_historical_benchmark_cases_parity(
    case_id: str,
    drug: str,
    disease: str,
    kwargs: dict[str, Any],
    expected_status: RecommendationStatus,
):
    """Verify production == evaluator on key historical benchmark cases."""
    prod_res = PRODUCTION_APPLY_RULES(**kwargs)
    eval_res = EVALUATOR_APPLY_RULES(**kwargs)

    assert prod_res.status == eval_res.status, f"Parity mismatch on {case_id} ({drug} -> {disease})"
    assert prod_res.status == expected_status, f"Expected {expected_status} on {case_id}, got {prod_res.status}"
    assert prod_res.reasons == eval_res.reasons


# ─────────────────────────────────────────────────────────────────────────────
# STEP 12: Benchmark Field Divergence Regression Test
# ─────────────────────────────────────────────────────────────────────────────


def test_benchmark_runner_uses_canonical_recommendation_status_not_intermediate_alignment():
    """Verify benchmark classification maps from canonical recommendation status, not intermediate alignment.

    Historical failure:
    benchmark_runner.py previously extracted:
        ta_dict.get('overall_alignment') -> map_alignment_to_class()
    while run_25_case_evaluation.py evaluated:
        res.recommendation_status -> RECOMMENDATION_TO_3CLASS

    When a drug had intermediate SUPPORTS alignment but failed a downstream safety or
    opposition rule (e.g., Rosiglitazone in T2D or Aspirin in Hemorrhagic Stroke),
    benchmark_runner wrongly graded it as POSITIVE while production and run_25 graded it
    as NOT_RECOMMENDED (NEGATIVE/OPPOSED).
    """
    # Case with intermediate positive alignment but overridden to NOT_RECOMMENDED by safety veto
    intermediate_alignment = "SUPPORTS"
    canonical_recommendation = RecommendationStatus.NOT_RECOMMENDED

    # Mapping intermediate alignment alone gives POSITIVE (the bug)
    buggy_class = map_alignment_to_class(intermediate_alignment)
    assert buggy_class == BenchmarkClass.POSITIVE

    # Mapping canonical recommendation gives NEGATIVE (the fix)
    canonical_class = map_recommendation_to_class(canonical_recommendation)
    assert canonical_class == BenchmarkClass.NEGATIVE

    # Verify map_recommendation_to_class contract
    assert map_recommendation_to_class(RecommendationStatus.PROMISING) == BenchmarkClass.POSITIVE
    assert map_recommendation_to_class(RecommendationStatus.NOT_RECOMMENDED) == BenchmarkClass.NEGATIVE
    assert map_recommendation_to_class(RecommendationStatus.UNCERTAIN) == BenchmarkClass.UNCERTAIN
    assert map_recommendation_to_class(RecommendationStatus.INSUFFICIENT_DATA) == BenchmarkClass.UNCERTAIN
    assert map_recommendation_to_class("PROMISING") == BenchmarkClass.POSITIVE
    assert map_recommendation_to_class("NOT_RECOMMENDED") == BenchmarkClass.NEGATIVE


# ─────────────────────────────────────────────────────────────────────────────
# STEP 13: TC-062 Evaluator Parity Test (4-Path Authoritative Guard)
# ─────────────────────────────────────────────────────────────────────────────


def run_tc062_through_all_evaluation_paths() -> list[dict[str, Any]]:
    """Execute TC-062 across Production, Fast, Benchmark, and Targeted evaluation paths."""
    import json
    import re
    from pathlib import Path
    from backend.core.domain.drug import Drug
    from backend.core.domain.disease import Disease
    from backend.engineering.retrieval.disease_relation import matches_for_approval_anchor
    from backend.engineering.retrieval.pipeline import RetrievalPipeline
    from backend.reasoning.opposition.therapeutic_opposition_assessor import (
        TherapeuticOppositionAssessor,
        trial_to_negative_claim,
    )

    drug = "Ranibizumab"
    disease = "Age-related macular degeneration"
    cid = "TC-062"

    results = []

    # Find results.jsonl
    candidates = [
        Path("evaluation_outputs/100_case_final/results.jsonl"),
        Path(__file__).parent.parent.parent / "evaluation_outputs/100_case_final/results.jsonl",
    ]
    jsonl_path = next((p for p in candidates if p.exists()), None)
    assert jsonl_path is not None, "Could not find evaluation_outputs/100_case_final/results.jsonl"

    prod_rec = None
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("case_id") == cid:
                prod_rec = d
                break
    assert prod_rec is not None, f"{cid} not found in results.jsonl"

    m_term_prod = re.search(r"Matched ChEMBL term: '([^']+)'", str(prod_rec.get("decision_rule", "")))
    matched_term_prod = m_term_prod.group(1) if m_term_prod else prod_rec.get("matched_indication_term")
    prod_is_anchor = matches_for_approval_anchor(disease, matched_term_prod) if matched_term_prod else False

    # Extract deciding rule
    dec_rule_prod = None
    for r in reversed(prod_rec.get("recommendation_reasons", [])):
        if r.startswith("Rule ") and not r.startswith("Rule -1 (APPROVED INDICATION ANCHOR)"):
            dec_rule_prod = r.split(":")[0].strip()
            break
    if not dec_rule_prod:
        dec_rule_prod = prod_rec["decision_rule"].split(":")[0].strip()

    # 1. Production Path
    results.append({
        "path": "Production",
        "prediction": prod_rec["prediction"],
        "recommendation_status": prod_rec["recommendation"],
        "opposition_score": prod_rec["opposition_score"],
        "approved_indication_detected": prod_is_anchor,
        "decision_rule": dec_rule_prod,
    })

    # 2. Fast Evaluator Path
    cache_candidates = [
        Path("data/ct_raw_cache/Ranibizumab_Age_related_macular_degeneration.json"),
        Path(__file__).parent.parent.parent / "data/ct_raw_cache/Ranibizumab_Age_related_macular_degeneration.json",
    ]
    cache_path = next((p for p in cache_candidates if p.exists()), None)
    assert cache_path is not None, "Could not find cached CT.gov trial for Ranibizumab"

    raw_ct = json.loads(cache_path.read_text(encoding="utf-8"))
    pipe = RetrievalPipeline()
    parsed_trials = pipe._parse_trials_data(
        raw_ct,
        Drug(name=drug, identifiers={"chembl": "CHEMBL1201825"}),
        Disease(name=disease, identifiers={"mesh": "D008268"}),
    )
    claims = [trial_to_negative_claim(t, drug, disease) for t in parsed_trials]
    claims = [c for c in claims if c]
    opp_assessor = TherapeuticOppositionAssessor()
    opp_assess = opp_assessor.assess(claims, drug, disease)

    baseline_rule = str(prod_rec.get("decision_rule", ""))
    m_term_fast = re.search(r"Matched ChEMBL term: '([^']+)'", baseline_rule)
    matched_term_fast = m_term_fast.group(1) if m_term_fast else (prod_rec.get("matched_indication_term") or None)
    fast_is_anchor = matches_for_approval_anchor(disease, matched_term_fast) if matched_term_fast else False

    fast_dec = EVALUATOR_APPLY_RULES(
        is_approved=fast_is_anchor,
        matched_chembl_term=matched_term_fast,
        support_score=float(prod_rec.get("support_score", 0.0)),
        mechanistic_score=float(prod_rec.get("mechanistic_score", 0.0)),
        risk_score=float(prod_rec.get("risk_score", 0.0)),
        opp_assessment=opp_assess,
    )
    fast_pred = (
        "SUPPORT"
        if fast_dec.status == RecommendationStatus.PROMISING
        else "OPPOSE"
        if fast_dec.status == RecommendationStatus.NOT_RECOMMENDED
        else "UNCERTAIN"
    )
    results.append({
        "path": "Fast",
        "prediction": fast_pred,
        "recommendation_status": fast_dec.status.value,
        "opposition_score": opp_assess.score,
        "approved_indication_detected": fast_is_anchor,
        "decision_rule": fast_dec.deciding_rule.split(":")[0].strip(),
    })

    # 3. Benchmark Evaluator Path
    bench_class = map_recommendation_to_class(prod_rec["recommendation"])
    bench_pred = (
        "SUPPORT"
        if bench_class == BenchmarkClass.POSITIVE
        else "OPPOSE"
        if bench_class == BenchmarkClass.NEGATIVE
        else "UNCERTAIN"
    )
    results.append({
        "path": "Benchmark",
        "prediction": bench_pred,
        "recommendation_status": prod_rec["recommendation"],
        "opposition_score": prod_rec["opposition_score"],
        "approved_indication_detected": prod_is_anchor,
        "decision_rule": dec_rule_prod,
    })

    # 4. Targeted Evaluator Path
    targ_dec = apply_decision_rules(
        is_approved=fast_is_anchor,
        matched_chembl_term=matched_term_fast,
        support_score=float(prod_rec.get("support_score", 0.0)),
        mechanistic_score=float(prod_rec.get("mechanistic_score", 0.0)),
        risk_score=float(prod_rec.get("risk_score", 0.0)),
        opp_assessment=opp_assess,
    )
    targ_pred = (
        "SUPPORT"
        if targ_dec.status == RecommendationStatus.PROMISING
        else "OPPOSE"
        if targ_dec.status == RecommendationStatus.NOT_RECOMMENDED
        else "UNCERTAIN"
    )
    results.append({
        "path": "Targeted",
        "prediction": targ_pred,
        "recommendation_status": targ_dec.status.value,
        "opposition_score": opp_assess.score,
        "approved_indication_detected": fast_is_anchor,
        "decision_rule": targ_dec.deciding_rule.split(":")[0].strip(),
    })

    return results


def test_tc062_all_evaluators_have_identical_final_state():
    """Section 9 exact parity test: Production, Fast, Benchmark, Targeted must produce identical state."""
    results = run_tc062_through_all_evaluation_paths()

    expected = (
        "SUPPORT",
        "PROMISING",
        0.0,
        True,
    )

    for result in results:
        assert (
            result["prediction"],
            result["recommendation_status"],
            result["opposition_score"],
            result["approved_indication_detected"],
        ) == expected

    deciding_rules = {
        result["decision_rule"]
        for result in results
    }

    assert len(deciding_rules) == 1

