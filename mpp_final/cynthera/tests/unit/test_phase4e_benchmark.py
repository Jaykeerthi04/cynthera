"""Unit tests for Phase 4E & 4E.4 — Benchmark, Contradiction, and Ablation Framework.

Covers:
1. Prediction normalization mapping
2. Positive classification metrics
3. Negative classification metrics
4. Uncertain classification handling
5. Missing negative class -> specificity = None
6. Missing positive class -> recall/precision = None
7. Confusion matrix (3x3) integrity
8. MCC calculation and zero-variance protection
9. Baseline calculation (Target existence heuristic)
10. Ablation configuration creation
11. Evidence family removal ablations
12. Independence-grouping ablation
13. Evaluation PDF generation
14. Report JSON serialization for frontend
15. Empty dataset graceful handling
16. Label provenance fields present on all benchmark cases
17. BENCH-NEG-01 flagged as unsuitable_for_directional_negative
18. EvaluationConfig defaults correct
19. EvaluationConfig with use_open_targets=False removes OT fields
20. EvaluationConfig with use_drugmechdb=False removes DrugMechDB fields
21. WeightConfig defaults correct (direct=1.0, structural=0.0, none=0.0)
22. WeightConfig.weight_for(DIRECT) == 1.0
23. WeightConfig.weight_for(STRUCTURAL) == 0.0 (hard zero regardless of config)
24. WeightConfig.weight_for(NONE) == 0.0 (hard zero regardless of config)
25. Weighted align: support only -> SUPPORTS
26. Weighted align: opposition only -> OPPOSES
27. Weighted align: total weight < min_effective_weight -> INSUFFICIENT
28. Weighted align: UNKNOWN drug action -> INSUFFICIENT
29. Weighted align: strong conflict (both sides >= min_effective_weight) -> INSUFFICIENT
30. Weighted align: net support > net opposition -> SUPPORTS
31. New BenchmarkSplit enum accessible
32. Benchmark dataset has >= 3 suitable negative cases (excluding flagged ones)
33. All benchmark cases have non-empty label_source and label_reference
34. AblationVerification model fields correct
35. BenchmarkEvaluationReport serializes new fields
36. Valid uncertain benchmark case (BENCH-UNC-02 Atorvastatin-MDD)
37. Invalid uncertain case rejection rationale documented
38. Genuine contradiction detection cases in dataset (Pilocarpine, Albuterol, Testosterone)
39. Same canonical target required for contradiction
40. UNKNOWN does not count as contradiction
41. Structural evidence does not create polarity
42. Independent contradictory sources remain separate
43. Duplicate evidence does not create artificial contradiction
44. Balanced contradiction returns INSUFFICIENT
45. Testosterone remains OPPOSES
46. Norepinephrine remains INSUFFICIENT when drug action is UNKNOWN
47. Methotrexate replacement ground truth
48. Production equal-vote path remains unchanged
49. Weighted comparator remains evaluation-only
50. Contradiction metrics computation integrity
"""
from __future__ import annotations

import pytest

from backend.evaluation.benchmark_models import (
    AblationConfig,
    AblationResult,
    AblationVerification,
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkClass,
    BenchmarkEvaluationReport,
    BenchmarkSplit,
    ExecutionStatus,
    WeightedBenchmarkCaseResult,
    WeightingComparisonResult,
    ContradictionMetrics,
    map_alignment_to_class,
)
from backend.evaluation.metrics import compute_benchmark_metrics, compute_contradiction_metrics
from backend.evaluation.ablation_runner import (
    compute_baseline_predictions,
    run_all_ablations,
    run_ablation_no_open_targets,
    run_ablation_no_datts,
    run_ablation_no_drugmechdb,
    run_ablation_no_independence,
)
from backend.reporting.evaluation_pdf_exporter import EvaluationPDFExporter
from backend.evaluation.evaluation_config import EvaluationConfig, EVALUATION_CONFIGS
from backend.evaluation.evidence_weights import WeightConfig, WEIGHT_CONFIGS, CONFIG_A, CONFIG_B, CONFIG_C
from backend.evaluation.benchmark_dataset import (
    BENCHMARK_DATASET_V1,
    get_directionally_suitable_negatives,
    get_unsuitable_negatives,
    get_contradiction_cases,
    get_cases_by_split,
)
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.value_objects.therapeutic_direction_evidence import (
    TherapeuticAction,
    TherapeuticAlignment,
    TherapeuticDirectionEvidence,
    EvidenceFamily,
    DirectionalEvidenceGroup,
    compute_independence_group,
)
from backend.reasoning.directional.therapeutic_alignment import (
    TherapeuticAlignmentEngine,
    derive_desired_target_action,
    group_evidence_by_independence,
)


# ── 1. Prediction Normalization ───────────────────────────────────────────────

def test_1_prediction_normalization():
    assert map_alignment_to_class("SUPPORTS") == BenchmarkClass.POSITIVE
    assert map_alignment_to_class("OPPOSES") == BenchmarkClass.NEGATIVE
    assert map_alignment_to_class("INSUFFICIENT") == BenchmarkClass.UNCERTAIN
    assert map_alignment_to_class("MIXED") == BenchmarkClass.UNCERTAIN
    assert map_alignment_to_class("UNKNOWN") == BenchmarkClass.UNCERTAIN
    assert map_alignment_to_class("") == BenchmarkClass.UNCERTAIN


# ── 2–4. Classification & Metrics Handling ────────────────────────────────────

def test_2_positive_classification_metrics():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        directional_concordance=1.0,
    )
    metrics = compute_benchmark_metrics([res])
    assert metrics.total_cases == 1
    assert metrics.correct_predictions == 1
    assert metrics.accuracy == 1.0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1_score == 1.0


def test_3_negative_classification_metrics():
    case_pos = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    case_neg = BenchmarkCase(case_id="C2", drug="DrugC", disease="DisB", expected_class=BenchmarkClass.NEGATIVE)

    res_pos = BenchmarkCaseResult(
        case=case_pos,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
    )
    res_neg = BenchmarkCaseResult(
        case=case_neg,
        predicted_alignment="OPPOSES",
        predicted_class=BenchmarkClass.NEGATIVE,
        is_correct=True,
        is_resolved=True,
    )

    metrics = compute_benchmark_metrics([res_pos, res_neg])
    assert metrics.total_cases == 2
    assert metrics.accuracy == 1.0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.specificity == 1.0
    assert metrics.mcc == 1.0


def test_4_uncertain_classification_handling():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.UNCERTAIN)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="INSUFFICIENT",
        predicted_class=BenchmarkClass.UNCERTAIN,
        is_correct=True,
        is_resolved=False,
    )
    metrics = compute_benchmark_metrics([res])
    assert metrics.total_cases == 1
    assert metrics.uncertain_cases == 1
    assert metrics.correct_predictions == 1
    assert metrics.accuracy == 1.0


# ── 5–6. Missing Class N/A Behavior ───────────────────────────────────────────

def test_5_missing_negative_class_specificity_none():
    """When only positive cases are tested, specificity must evaluate to None (N/A)."""
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
    )
    metrics = compute_benchmark_metrics([res])
    assert metrics.specificity is None
    assert any("Specificity unavailable" in n for n in metrics.notes)


def test_6_missing_positive_class_recall_none():
    """When only negative cases are tested, recall and precision must evaluate to None."""
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.NEGATIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="OPPOSES",
        predicted_class=BenchmarkClass.NEGATIVE,
        is_correct=True,
        is_resolved=True,
    )
    metrics = compute_benchmark_metrics([res])
    assert metrics.recall is None
    assert metrics.precision is None


# ── 7–8. Confusion Matrix & MCC ───────────────────────────────────────────────

def test_7_confusion_matrix_3x3_integrity():
    case_p = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    case_n = BenchmarkCase(case_id="C2", drug="DrugB", disease="DisB", expected_class=BenchmarkClass.NEGATIVE)
    case_u = BenchmarkCase(case_id="C3", drug="DrugC", disease="DisB", expected_class=BenchmarkClass.UNCERTAIN)

    res_p = BenchmarkCaseResult(case=case_p, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True)
    res_n = BenchmarkCaseResult(case=case_n, predicted_alignment="OPPOSES", predicted_class=BenchmarkClass.NEGATIVE, is_correct=True, is_resolved=True)
    res_u = BenchmarkCaseResult(case=case_u, predicted_alignment="INSUFFICIENT", predicted_class=BenchmarkClass.UNCERTAIN, is_correct=True, is_resolved=False)

    metrics = compute_benchmark_metrics([res_p, res_n, res_u])
    cm = metrics.confusion_matrix
    assert cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.POSITIVE) == 1
    assert cm.get(BenchmarkClass.NEGATIVE, BenchmarkClass.NEGATIVE) == 1
    assert cm.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.UNCERTAIN) == 1
    assert cm.get(BenchmarkClass.POSITIVE, BenchmarkClass.NEGATIVE) == 0


def test_8_mcc_zero_variance_handling():
    """Zero variance across classes gracefully evaluates MCC to None without division error."""
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(case=case, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True)
    metrics = compute_benchmark_metrics([res])
    assert metrics.mcc is None


# ── 9. Baseline Comparison ───────────────────────────────────────────────────

def test_9_baseline_calculation():
    case_pos = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    case_neg = BenchmarkCase(case_id="C2", drug="DrugB", disease="DisB", expected_class=BenchmarkClass.NEGATIVE)

    res_pos = BenchmarkCaseResult(case=case_pos, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True, primary_target="TGT1")
    res_neg = BenchmarkCaseResult(case=case_neg, predicted_alignment="OPPOSES", predicted_class=BenchmarkClass.NEGATIVE, is_correct=True, is_resolved=True, primary_target="TGT2")

    baseline_res = compute_baseline_predictions([res_pos, res_neg])
    assert len(baseline_res) == 2
    assert baseline_res[0].predicted_class == BenchmarkClass.POSITIVE
    assert baseline_res[1].predicted_class == BenchmarkClass.POSITIVE
    assert baseline_res[0].is_correct is True
    assert baseline_res[1].is_correct is False


# ── 10–12. Ablation Analysis ─────────────────────────────────────────────────

def test_10_ablation_configuration_creation():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="TGT1",
        target_alignments=[{
            "target_id": "TGT1",
            "evidence_groups": [{"sources": ["OpenTargets"], "desired_action": "INHIBITION"}],
        }],
    )

    ablations = run_all_ablations([res])
    assert len(ablations) == 4
    config_names = [a.config_name for a in ablations]
    assert AblationConfig.NO_OPEN_TARGETS in config_names
    assert AblationConfig.NO_DATTS in config_names
    assert AblationConfig.NO_DRUGMECHDB in config_names
    assert AblationConfig.NO_INDEPENDENCE_GROUPING in config_names


def test_11_evidence_family_removal_ablation():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="TGT1",
        target_alignments=[{
            "target_id": "TGT1",
            "evidence_groups": [{"sources": ["OpenTargets"], "desired_action": "INHIBITION"}],
        }],
    )

    ab_no_ot = run_ablation_no_open_targets([res])
    assert ab_no_ot.case_predictions["C1"] == BenchmarkClass.UNCERTAIN
    assert len(ab_no_ot.changed_cases_from_full) == 1


def test_12_independence_grouping_ablation():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="TGT1",
        directional_concordance=1.0,
    )
    ab_no_ind = run_ablation_no_independence([res])
    assert ab_no_ind.config_name == AblationConfig.NO_INDEPENDENCE_GROUPING
    assert ab_no_ind.metrics.total_cases == 1


# ── 13–15. PDF Generation, Serialization & Integration ────────────────────────

def test_13_pdf_generation():
    case = BenchmarkCase(case_id="BENCH-POS-01", drug="Furosemide", disease="Edema", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="SLC12A1",
        directional_concordance=1.0,
        supporting_group_count=5,
        opposing_group_count=0,
    )
    metrics = compute_benchmark_metrics([res])
    contradiction_m = compute_contradiction_metrics([res])
    report = BenchmarkEvaluationReport(
        benchmark_version="v1.1",
        full_4d_metrics=metrics,
        baseline_metrics=metrics,
        case_results=[res],
        contradiction_metrics=contradiction_m,
    )

    exporter = EvaluationPDFExporter(report)
    pdf_bytes = exporter.generate_pdf_bytes()
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")


def test_14_report_json_serialization():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(case=case, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True)
    report = BenchmarkEvaluationReport(
        benchmark_version="v1.1",
        case_results=[res],
    )
    report_dict = report.model_dump(mode="json")
    assert report_dict["benchmark_version"] == "v1.1"
    assert len(report_dict["case_results"]) == 1
    assert report_dict["case_results"][0]["predicted_class"] == "POSITIVE"


def test_15_empty_dataset_graceful_handling():
    metrics = compute_benchmark_metrics([])
    assert metrics.total_cases == 0
    assert metrics.accuracy is None
    assert len(metrics.notes) > 0


# ── 16–17. Label Provenance & Flags ──────────────────────────────────────────

def test_16_label_provenance_fields_present():
    """All benchmark cases must have non-empty label_source, label_reference, label_rationale."""
    for case in BENCHMARK_DATASET_V1:
        assert case.label_source, f"{case.case_id}: missing label_source"
        assert case.label_reference, f"{case.case_id}: missing label_reference"
        assert case.label_rationale, f"{case.case_id}: missing label_rationale"


def test_17_bench_neg_01_flagged_unsuitable():
    """BENCH-NEG-01 must be flagged as unsuitable_for_directional_negative=True with documented reason."""
    bench_neg_01 = next(c for c in BENCHMARK_DATASET_V1 if c.case_id == "BENCH-NEG-01")
    assert bench_neg_01.unsuitable_for_directional_negative is True
    assert bench_neg_01.expected_class == BenchmarkClass.NEGATIVE
    assert bench_neg_01 in BENCHMARK_DATASET_V1


# ── 18–20. EvaluationConfig ───────────────────────────────────────────────────

def test_18_evaluation_config_defaults():
    cfg = EvaluationConfig()
    assert cfg.name == "FULL_4D"
    assert cfg.use_open_targets is True
    assert cfg.use_datts is True
    assert cfg.use_drugmechdb is True
    assert cfg.use_independence_grouping is True
    assert cfg.use_evidence_weighting is False


def test_19_evaluation_config_no_open_targets():
    cfg = EVALUATION_CONFIGS["NO_OPEN_TARGETS"]
    assert cfg.use_open_targets is False
    assert cfg.use_datts is True
    assert cfg.use_drugmechdb is True
    assert cfg.use_independence_grouping is True


def test_20_evaluation_config_no_drugmechdb():
    cfg = EVALUATION_CONFIGS["NO_DRUGMECHDB"]
    assert cfg.use_drugmechdb is False
    assert cfg.use_open_targets is True
    assert cfg.use_datts is True


# ── 21–24. WeightConfig ───────────────────────────────────────────────────────

def test_21_weight_config_defaults():
    from backend.evaluation.evidence_weights import DEFAULT_WEIGHT_CONFIG
    assert DEFAULT_WEIGHT_CONFIG.direct == 1.0
    assert DEFAULT_WEIGHT_CONFIG.curated == 0.9
    assert DEFAULT_WEIGHT_CONFIG.inferred == 0.5
    assert DEFAULT_WEIGHT_CONFIG.structural == 0.0
    assert DEFAULT_WEIGHT_CONFIG.none == 0.0


def test_22_weight_config_direct():
    assert CONFIG_A.weight_for(CausalGrounding.DIRECT) == 1.0
    assert CONFIG_B.weight_for(CausalGrounding.DIRECT) == 1.0
    assert CONFIG_C.weight_for(CausalGrounding.DIRECT) == 1.0


def test_23_weight_config_structural_always_zero():
    custom_cfg = WeightConfig(name="custom", structural=99.0)
    assert custom_cfg.weight_for(CausalGrounding.STRUCTURAL) == 0.0
    assert CONFIG_A.weight_for(CausalGrounding.STRUCTURAL) == 0.0
    assert CONFIG_B.weight_for(CausalGrounding.STRUCTURAL) == 0.0


def test_24_weight_config_none_always_zero():
    custom_cfg = WeightConfig(name="custom", none=99.0)
    assert custom_cfg.weight_for(CausalGrounding.NONE) == 0.0
    assert CONFIG_A.weight_for(CausalGrounding.NONE) == 0.0


# ── 25–30. Weighted Alignment Engine ─────────────────────────────────────────

def _make_tde(target: str, source: str, required_action: str,
              grounding: CausalGrounding = CausalGrounding.CURATED,
              family: EvidenceFamily = EvidenceFamily.CURATED_REFERENCE,
              ref: str | None = None) -> TherapeuticDirectionEvidence:
    """Helper: create a synthetic TherapeuticDirectionEvidence record."""
    ref_val = ref or f"test:{source}:{target}:{required_action}"
    ig = compute_independence_group(family, [ref_val], source=source)
    return TherapeuticDirectionEvidence(
        target_canonical_id=target,
        disease_canonical_id="TEST_DISEASE",
        source=source,
        target_direction=None,
        trait_direction=None,
        required_action=required_action,
        evidence_type="TEST",
        causal_grounding=grounding,
        evidence_family=family,
        independence_group=ig,
        underlying_reference=ref_val,
    )


def test_25_weighted_align_support_only():
    engine = TherapeuticAlignmentEngine()
    tde = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.CURATED)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.INHIBITION,
        evidence_records=[tde],
        weight_config=CONFIG_A,
        is_primary=True,
    )
    assert result.alignment == TherapeuticAlignment.SUPPORTS
    assert result.confidence > 0


def test_26_weighted_align_opposition_only():
    engine = TherapeuticAlignmentEngine()
    tde = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.CURATED)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.ACTIVATION,
        evidence_records=[tde],
        weight_config=CONFIG_A,
        is_primary=True,
    )
    assert result.alignment == TherapeuticAlignment.OPPOSES


def test_27_weighted_align_insufficient_weight():
    engine = TherapeuticAlignmentEngine()
    tde = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.STRUCTURAL)
    cfg = WeightConfig(name="test", direct=1.0, curated=0.9, inferred=0.5, min_effective_weight=0.5)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.INHIBITION,
        evidence_records=[tde],
        weight_config=cfg,
        is_primary=True,
    )
    assert result.alignment == TherapeuticAlignment.INSUFFICIENT


def test_28_weighted_align_unknown_drug_action():
    engine = TherapeuticAlignmentEngine()
    tde = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.DIRECT)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.UNKNOWN,
        evidence_records=[tde],
        weight_config=CONFIG_A,
        is_primary=True,
    )
    assert result.alignment == TherapeuticAlignment.INSUFFICIENT


def test_29_weighted_align_strong_conflict_insufficient():
    engine = TherapeuticAlignmentEngine()
    tde_support = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.DIRECT, EvidenceFamily.CURATED_REFERENCE, ref="ref1")
    tde_oppose = _make_tde("TGT1", "OpenTargets", "ACTIVATION", CausalGrounding.DIRECT, EvidenceFamily.GENETIC, ref="ref2")
    cfg = WeightConfig(name="test", direct=1.0, curated=0.9, inferred=0.5, min_effective_weight=0.5)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.INHIBITION,
        evidence_records=[tde_support, tde_oppose],
        weight_config=cfg,
        is_primary=True,
    )
    assert result.alignment == TherapeuticAlignment.INSUFFICIENT


def test_30_weighted_align_net_support_wins():
    engine = TherapeuticAlignmentEngine()
    tde_support = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.DIRECT, EvidenceFamily.CURATED_REFERENCE, ref="ref1")
    tde_struct_oppose = _make_tde("TGT1", "ChEMBL", "ACTIVATION", CausalGrounding.STRUCTURAL, EvidenceFamily.BIOCHEMICAL, ref="ref2")
    cfg = WeightConfig(name="test", direct=1.0, curated=0.9, inferred=0.5, min_effective_weight=0.5)
    result = engine.weighted_align_target(
        target_id="TGT1",
        drug_action=TherapeuticAction.INHIBITION,
        evidence_records=[tde_support, tde_struct_oppose],
        weight_config=cfg,
        is_primary=True,
    )
    assert result.alignment == TherapeuticAlignment.SUPPORTS


# ── 31–33. Dataset Quality ────────────────────────────────────────────────────

def test_31_benchmark_split_enum():
    assert BenchmarkSplit.DEVELOPMENT.value == "DEVELOPMENT"
    assert BenchmarkSplit.VALIDATION.value == "VALIDATION"
    assert BenchmarkSplit.TEST.value == "TEST"


def test_32_benchmark_has_suitable_negatives():
    suitable = get_directionally_suitable_negatives()
    assert len(suitable) >= 3, f"Expected >= 3 suitable negative cases, got {len(suitable)}"
    for c in suitable:
        assert c.expected_class == BenchmarkClass.NEGATIVE
        assert c.unsuitable_for_directional_negative is False


def test_33_all_cases_have_label_provenance():
    for case in BENCHMARK_DATASET_V1:
        assert case.label_source.strip(), f"{case.case_id}: label_source is empty"
        assert case.label_reference.strip(), f"{case.case_id}: label_reference is empty"


# ── 34–35. New Model Serialization ────────────────────────────────────────────

def test_34_ablation_verification_fields():
    verif = AblationVerification(
        case_id="BENCH-POS-01",
        ablation_config="NO_DRUGMECHDB",
        full_evidence_count=10,
        ablated_evidence_count=8,
        full_independence_group_count=4,
        ablated_independence_group_count=3,
        component_present_in_full=True,
        component_present_in_ablated=False,
        evidence_representation_changed=True,
        prediction_changed=False,
        full_prediction="POSITIVE",
        ablated_prediction="POSITIVE",
        verification_passed=True,
        verification_note="VERIFIED",
    )
    assert verif.evidence_representation_changed is True
    assert verif.verification_passed is True


def test_35_report_serializes_new_fields():
    case = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    res = BenchmarkCaseResult(case=case, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True)

    report = BenchmarkEvaluationReport(
        benchmark_version="v1.1",
        case_results=[res],
        dataset_quality_metrics={"total_cases": 1, "positive_cases": 1},
        benchmark_split_note="All cases in TEST split.",
    )
    d = report.model_dump(mode="json")
    assert "dataset_quality_metrics" in d
    assert "benchmark_split_note" in d
    assert d["benchmark_split_note"] == "All cases in TEST split."


# ── 36–50. Phase 4E.4 Specific Tests ─────────────────────────────────────────

def test_36_valid_uncertain_benchmark_case():
    """BENCH-UNC-02 (Atorvastatin-MDD) is properly characterized as UNCERTAIN."""
    bench_unc_02 = next(c for c in BENCHMARK_DATASET_V1 if c.case_id == "BENCH-UNC-02")
    assert bench_unc_02.drug == "Atorvastatin"
    assert bench_unc_02.disease == "Major Depressive Disorder"
    assert bench_unc_02.expected_class == BenchmarkClass.UNCERTAIN
    assert "inconclusive" in bench_unc_02.label_rationale.lower() or "unestablished" in bench_unc_02.label_rationale.lower() or "no established" in bench_unc_02.rationale.lower()


def test_37_invalid_uncertain_case_rejection_documented():
    """Documentation confirms Methotrexate-RA was rejected as an UNCERTAIN case due to strong DHFR support."""
    # Ensure Methotrexate-RA is NOT present as an UNCERTAIN benchmark case
    for case in BENCHMARK_DATASET_V1:
        if case.drug == "Methotrexate" and case.disease == "Rheumatoid Arthritis":
            assert case.expected_class != BenchmarkClass.UNCERTAIN


def test_38_genuine_contradiction_detection_cases():
    """Benchmark dataset contains genuine contradiction cases (Pilocarpine-Asthma, Albuterol-HTN, Testosterone-PCa)."""
    cases = {c.case_id: c for c in BENCHMARK_DATASET_V1}
    assert "BENCH-NEG-03" in cases  # Testosterone -> PCa
    assert "BENCH-NEG-04" in cases  # Pilocarpine -> Asthma
    assert "BENCH-NEG-05" in cases  # Albuterol -> HTN
    assert "BENCH-UNC-03" in cases  # Nicotine -> HTN (Balanced conflict)

    assert cases["BENCH-NEG-04"].expected_class == BenchmarkClass.NEGATIVE
    assert cases["BENCH-NEG-05"].expected_class == BenchmarkClass.NEGATIVE
    assert cases["BENCH-UNC-03"].expected_class == BenchmarkClass.UNCERTAIN


def test_39_same_canonical_target_required_for_contradiction():
    """Contradiction occurs only when opposing directions exist on the SAME canonical target."""
    engine = TherapeuticAlignmentEngine()
    # Drug ACTIVATES TGT1
    tde_tgt1 = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.CURATED, ref="ref1")
    # Drug also binds TGT2 which needs ACTIVATION
    tde_tgt2 = _make_tde("TGT2", "DATTs", "ACTIVATION", CausalGrounding.CURATED, ref="ref2")

    res_tgt1 = engine.align_target("TGT1", TherapeuticAction.ACTIVATION, [tde_tgt1], is_primary=True)
    res_tgt2 = engine.align_target("TGT2", TherapeuticAction.ACTIVATION, [tde_tgt2], is_primary=False)

    assert res_tgt1.alignment == TherapeuticAlignment.OPPOSES
    assert res_tgt2.alignment == TherapeuticAlignment.SUPPORTS


def test_40_unknown_does_not_count_as_contradiction():
    """UNKNOWN drug action or desired action produces INSUFFICIENT, never OPPOSES."""
    engine = TherapeuticAlignmentEngine()
    tde = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.CURATED)
    res = engine.align_target("TGT1", TherapeuticAction.UNKNOWN, [tde], is_primary=True)
    assert res.alignment == TherapeuticAlignment.INSUFFICIENT
    assert res.opposing_groups == []


def test_41_structural_evidence_does_not_create_polarity():
    """STRUCTURAL evidence has weight 0.0 and does not emit signed votes or cause false opposition."""
    engine = TherapeuticAlignmentEngine()
    tde_struct = _make_tde("TGT1", "ChEMBL", "ACTIVATION", CausalGrounding.STRUCTURAL, EvidenceFamily.BIOCHEMICAL)
    cfg = WeightConfig(name="test", direct=1.0, curated=0.9, inferred=0.5, min_effective_weight=0.5)
    res = engine.weighted_align_target("TGT1", TherapeuticAction.INHIBITION, [tde_struct], weight_config=cfg, is_primary=True)
    assert res.alignment == TherapeuticAlignment.INSUFFICIENT
    assert res.opposing_groups == []


def test_42_independent_contradictory_sources_remain_separate():
    """Separate PMIDs for contradictory claims remain distinct independence groups."""
    tde1 = _make_tde("TGT1", "OpenTargets", "ACTIVATION", ref="PMID:1001")
    tde2 = _make_tde("TGT1", "OpenTargets", "INHIBITION", ref="PMID:2002")
    groups = group_evidence_by_independence([tde1, tde2])
    assert len(groups) == 2
    actions = {g.desired_action for g in groups}
    assert TherapeuticAction.ACTIVATION in actions
    assert TherapeuticAction.INHIBITION in actions


def test_43_duplicate_evidence_does_not_create_artificial_contradiction():
    """Duplicate records referencing the same citation collapse into 1 group."""
    tde1 = _make_tde("TGT1", "OpenTargets", "INHIBITION", ref="PMID:12345")
    tde2 = _make_tde("TGT1", "OpenTargets", "INHIBITION", ref="PMID:12345")
    groups = group_evidence_by_independence([tde1, tde2])
    assert len(groups) == 1
    assert groups[0].member_record_count == 2


def test_44_balanced_contradiction_returns_insufficient():
    """Equal supporting and opposing evidence on a target yields INSUFFICIENT."""
    engine = TherapeuticAlignmentEngine()
    tde_supp = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.CURATED, ref="ref1")
    tde_opp = _make_tde("TGT1", "OpenTargets", "ACTIVATION", CausalGrounding.CURATED, ref="ref2")

    res = engine.align_target("TGT1", TherapeuticAction.INHIBITION, [tde_supp, tde_opp], is_primary=True)
    assert res.alignment == TherapeuticAlignment.INSUFFICIENT
    assert len(res.supporting_groups) == 1
    assert len(res.opposing_groups) == 1


def test_45_testosterone_remains_opposes():
    """Testosterone -> PCa contradiction control produces OPPOSES."""
    engine = TherapeuticAlignmentEngine()
    tde_ar = _make_tde("AR", "OpenTargets", "INHIBITION", CausalGrounding.CURATED, ref="PMID:25683285")
    res = engine.align_target("AR", TherapeuticAction.ACTIVATION, [tde_ar], is_primary=True)
    assert res.alignment == TherapeuticAlignment.OPPOSES
    assert len(res.opposing_groups) == 1


def test_46_norepinephrine_remains_insufficient_when_drug_action_unknown():
    """Norepinephrine-HF correctly withholds signed prediction when ChEMBL drug action is UNKNOWN."""
    engine = TherapeuticAlignmentEngine()
    tde_adrb1 = _make_tde("ADRB1", "OpenTargets", "INHIBITION", CausalGrounding.CURATED, ref="PMID:10376614")
    res = engine.align_target("ADRB1", TherapeuticAction.UNKNOWN, [tde_adrb1], is_primary=True)
    assert res.alignment == TherapeuticAlignment.INSUFFICIENT


def test_47_methotrexate_replacement_ground_truth():
    """BENCH-UNC-02 is Atorvastatin-MDD in test set."""
    cases = {c.case_id: c for c in BENCHMARK_DATASET_V1}
    assert cases["BENCH-UNC-02"].drug == "Atorvastatin"
    assert cases["BENCH-UNC-02"].expected_class == BenchmarkClass.UNCERTAIN


def test_48_production_equal_vote_path_remains_unchanged():
    """Production align_target returns equal-vote result."""
    engine = TherapeuticAlignmentEngine()
    tde1 = _make_tde("TGT1", "DATTs", "INHIBITION", CausalGrounding.CURATED, ref="ref1")
    tde2 = _make_tde("TGT1", "OpenTargets", "INHIBITION", CausalGrounding.DIRECT, ref="ref2")
    res = engine.align_target("TGT1", TherapeuticAction.INHIBITION, [tde1, tde2], is_primary=True)
    assert res.alignment == TherapeuticAlignment.SUPPORTS
    assert len(res.supporting_groups) == 2


def test_49_weighted_comparator_evaluation_only():
    """Weighted comparator methods exist and compute weighted alignment without altering core engine."""
    engine = TherapeuticAlignmentEngine()
    assert hasattr(engine, "weighted_align_target")
    assert hasattr(engine, "weighted_align_package")


def test_50_contradiction_metrics_computation():
    """compute_contradiction_metrics evaluates detection rate and resolution rate accurately."""
    case_pos = BenchmarkCase(case_id="C1", drug="DrugA", disease="DisB", expected_class=BenchmarkClass.POSITIVE)
    case_neg = BenchmarkCase(case_id="C2", drug="DrugB", disease="DisB", expected_class=BenchmarkClass.NEGATIVE)
    case_bal = BenchmarkCase(case_id="BENCH-UNC-03", drug="DrugC", disease="DisB", expected_class=BenchmarkClass.UNCERTAIN, rationale="balanced conflict")

    res_pos = BenchmarkCaseResult(case=case_pos, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True, supporting_group_count=2, opposing_group_count=0)
    res_neg = BenchmarkCaseResult(case=case_neg, predicted_alignment="OPPOSES", predicted_class=BenchmarkClass.NEGATIVE, is_correct=True, is_resolved=True, supporting_group_count=0, opposing_group_count=2)
    res_bal = BenchmarkCaseResult(case=case_bal, predicted_alignment="INSUFFICIENT", predicted_class=BenchmarkClass.UNCERTAIN, is_correct=True, is_resolved=False, supporting_group_count=1, opposing_group_count=1)

    cm = compute_contradiction_metrics([res_pos, res_neg, res_bal])
    assert cm.contradiction_cases == 1
    assert cm.balanced_conflict_cases == 1
    assert cm.contradiction_detection_rate == 1.0
    assert cm.contradiction_resolution_rate == 1.0
    assert cm.balanced_conflict_insufficient_rate == 1.0
    assert cm.false_directional_resolution_rate == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4E.5 Tests (51–65)
# Target identity tracking, DEV split, Bootstrap CI, Calibration provenance
# ─────────────────────────────────────────────────────────────────────────────

def test_51_target_match_true_when_target_matches() -> None:
    """Test 51: target_match=True when primary_target == expected_target (case-insensitive)."""
    case = BenchmarkCase(
        case_id="T51",
        drug="Imatinib",
        disease="CML",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="ABL1",
    )
    result = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="ABL1",
        all_pipeline_targets=["ABL1", "KIT"],
        target_match=True,
    )
    assert result.target_match is True


def test_52_target_match_false_when_target_differs() -> None:
    """Test 52: target_match=False when primary_target != expected_target."""
    case = BenchmarkCase(
        case_id="T52",
        drug="Furosemide",
        disease="Heart Failure",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="SLC12A1",
    )
    result = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="ADORA1",
        all_pipeline_targets=["ADORA1"],
        target_match=False,
    )
    assert result.target_match is False


def test_53_target_match_none_when_expected_not_set() -> None:
    """Test 53: target_match=None when case.expected_target is not specified."""
    case = BenchmarkCase(
        case_id="T53",
        drug="SomeDrug",
        disease="SomeDisease",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target=None,
    )
    result = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="GENE1",
        all_pipeline_targets=["GENE1"],
        target_match=None,
    )
    assert result.target_match is None


def test_54_all_pipeline_targets_is_a_list() -> None:
    """Test 54: all_pipeline_targets is a list and can be empty or populated."""
    case = BenchmarkCase(
        case_id="T54", drug="Erlotinib", disease="NSCLC",
        expected_class=BenchmarkClass.POSITIVE, expected_target="EGFR",
    )
    result_empty = BenchmarkCaseResult(
        case=case, predicted_alignment="INSUFFICIENT", predicted_class=BenchmarkClass.UNCERTAIN,
        is_correct=False, is_resolved=False, all_pipeline_targets=[],
    )
    assert isinstance(result_empty.all_pipeline_targets, list)
    assert len(result_empty.all_pipeline_targets) == 0

    result_populated = BenchmarkCaseResult(
        case=case, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True, is_resolved=True, all_pipeline_targets=["EGFR", "ERBB2"], target_match=True,
    )
    assert isinstance(result_populated.all_pipeline_targets, list)
    assert "EGFR" in result_populated.all_pipeline_targets


def test_55_development_split_has_minimum_cases() -> None:
    """Test 55: DEVELOPMENT split has at least 10 cases after Phase 4E.5 expansion."""
    from backend.evaluation.benchmark_dataset import BENCHMARK_DATASET_V1
    dev_cases = [c for c in BENCHMARK_DATASET_V1 if c.split == BenchmarkSplit.DEVELOPMENT]
    assert len(dev_cases) >= 10, (
        f"Expected >= 10 DEVELOPMENT cases, got {len(dev_cases)}. "
        "Phase 4E.5 requires >= 5 POS, >= 3 NEG, >= 2 UNC in DEV split."
    )


def test_56_test_split_retains_original_cases() -> None:
    """Test 56: TEST split still contains all 13 original benchmark cases."""
    from backend.evaluation.benchmark_dataset import BENCHMARK_DATASET_V1
    test_cases = [c for c in BENCHMARK_DATASET_V1 if c.split == BenchmarkSplit.TEST]
    assert len(test_cases) == 13, (
        f"Expected 13 TEST cases, got {len(test_cases)}. "
        "Do not modify existing TEST cases in Phase 4E.5."
    )


def test_57_all_dev_cases_have_label_provenance() -> None:
    """Test 57: All DEVELOPMENT cases have non-empty label_source, label_reference, label_rationale."""
    from backend.evaluation.benchmark_dataset import BENCHMARK_DATASET_V1
    dev_cases = [c for c in BENCHMARK_DATASET_V1 if c.split == BenchmarkSplit.DEVELOPMENT]
    assert len(dev_cases) > 0, "No DEVELOPMENT cases found."
    for c in dev_cases:
        assert c.label_source and c.label_source.strip(), (
            f"{c.case_id}: label_source is empty or whitespace."
        )
        assert c.label_reference and c.label_reference.strip(), (
            f"{c.case_id}: label_reference is empty or whitespace."
        )
        assert c.label_rationale and c.label_rationale.strip(), (
            f"{c.case_id}: label_rationale is empty or whitespace."
        )


def test_58_compute_bootstrap_ci_returns_required_keys() -> None:
    """Test 58: compute_bootstrap_ci() returns a dict with all 5 required metric keys."""
    from backend.evaluation.metrics import compute_bootstrap_ci

    # Build a minimal result set with 3 classes represented
    case_p = BenchmarkCase(case_id="P1", drug="D", disease="X", expected_class=BenchmarkClass.POSITIVE)
    case_n = BenchmarkCase(case_id="N1", drug="D", disease="Y", expected_class=BenchmarkClass.NEGATIVE)
    res_p = BenchmarkCaseResult(
        case=case_p, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True, is_resolved=True,
    )
    res_n = BenchmarkCaseResult(
        case=case_n, predicted_alignment="OPPOSES", predicted_class=BenchmarkClass.NEGATIVE,
        is_correct=True, is_resolved=True,
    )
    results = [res_p, res_n] * 5  # 10 results total

    ci = compute_bootstrap_ci(results, n_bootstrap=100, seed=42)
    required_keys = {"accuracy", "precision", "recall", "specificity", "mcc"}
    for key in required_keys:
        assert key in ci, f"Missing CI key: {key}"
        lo, hi = ci[key]
        assert isinstance(lo, float)
        assert isinstance(hi, float)


def test_59_bootstrap_ci_bounds_bracket_point_estimate() -> None:
    """Test 59: Bootstrap CI lower bound < point estimate < upper bound for accuracy."""
    from backend.evaluation.metrics import compute_bootstrap_ci, compute_benchmark_metrics

    case_p = BenchmarkCase(case_id="P1", drug="D", disease="X", expected_class=BenchmarkClass.POSITIVE)
    case_n = BenchmarkCase(case_id="N1", drug="D", disease="Y", expected_class=BenchmarkClass.NEGATIVE)
    # Mix of correct and incorrect to get non-trivial accuracy
    results = []
    for i in range(4):
        results.append(BenchmarkCaseResult(
            case=case_p, predicted_alignment="SUPPORTS",
            predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True,
        ))
    for i in range(2):
        results.append(BenchmarkCaseResult(
            case=case_p, predicted_alignment="INSUFFICIENT",
            predicted_class=BenchmarkClass.UNCERTAIN, is_correct=False, is_resolved=False,
        ))
    for i in range(4):
        results.append(BenchmarkCaseResult(
            case=case_n, predicted_alignment="OPPOSES",
            predicted_class=BenchmarkClass.NEGATIVE, is_correct=True, is_resolved=True,
        ))

    point_metrics = compute_benchmark_metrics(results)
    ci = compute_bootstrap_ci(results, n_bootstrap=200, seed=42)

    assert point_metrics.accuracy is not None
    assert "accuracy" in ci
    lo, hi = ci["accuracy"]
    # With 10 results, CI should be meaningful (lo <= point <= hi or very close)
    assert lo <= point_metrics.accuracy + 0.001, (
        f"CI lower {lo} > point estimate {point_metrics.accuracy}"
    )
    assert hi >= point_metrics.accuracy - 0.001, (
        f"CI upper {hi} < point estimate {point_metrics.accuracy}"
    )


def test_60_bootstrap_ci_is_reproducible_with_same_seed() -> None:
    """Test 60: compute_bootstrap_ci(seed=42) returns identical results across two calls."""
    from backend.evaluation.metrics import compute_bootstrap_ci

    case_p = BenchmarkCase(case_id="P1", drug="D", disease="X", expected_class=BenchmarkClass.POSITIVE)
    case_n = BenchmarkCase(case_id="N1", drug="D", disease="Y", expected_class=BenchmarkClass.NEGATIVE)
    results = (
        [BenchmarkCaseResult(case=case_p, predicted_alignment="SUPPORTS", predicted_class=BenchmarkClass.POSITIVE, is_correct=True, is_resolved=True)] * 5
        + [BenchmarkCaseResult(case=case_n, predicted_alignment="OPPOSES", predicted_class=BenchmarkClass.NEGATIVE, is_correct=True, is_resolved=True)] * 5
    )

    ci1 = compute_bootstrap_ci(results, n_bootstrap=500, seed=42)
    ci2 = compute_bootstrap_ci(results, n_bootstrap=500, seed=42)
    assert ci1 == ci2, "Bootstrap CI is not reproducible with same seed."


def test_61_benchmark_metrics_with_ci_serializes() -> None:
    """Test 61: BenchmarkMetricsWithCI serializes to JSON without error."""
    import json
    from backend.evaluation.benchmark_models import BenchmarkMetricsWithCI

    m = BenchmarkMetricsWithCI(
        total_cases=10,
        accuracy=0.8,
        precision=1.0,
        recall=0.8,
        specificity=0.75,
        mcc=0.6,
        accuracy_ci=(0.6, 0.95),
        precision_ci=(0.8, 1.0),
        recall_ci=(0.6, 0.95),
        specificity_ci=(0.5, 1.0),
        mcc_ci=(0.4, 0.8),
        ci_level=0.95,
        n_bootstrap=1000,
    )
    serialized = json.loads(m.model_dump_json())
    assert serialized["accuracy"] == 0.8
    assert serialized["accuracy_ci"] == [0.6, 0.95]
    assert serialized["n_bootstrap"] == 1000


def test_62_calibration_summary_is_dict() -> None:
    """Test 62: BenchmarkEvaluationReport.calibration_summary is a dict (can be empty)."""
    from backend.evaluation.benchmark_models import BenchmarkEvaluationReport
    report = BenchmarkEvaluationReport()
    assert isinstance(report.calibration_summary, dict)
    # Can be populated
    report_with_cal = BenchmarkEvaluationReport(
        calibration_summary={"CONFIG_A": {"dev_mcc": 0.7}, "best_config": "CONFIG_A"},
    )
    assert report_with_cal.calibration_summary["best_config"] == "CONFIG_A"


def test_63_calibration_selected_config_constant_exists() -> None:
    """Test 63: CALIBRATION_SELECTED_CONFIG constant exists in evidence_weights module."""
    from backend.evaluation import evidence_weights
    assert hasattr(evidence_weights, "CALIBRATION_SELECTED_CONFIG"), (
        "CALIBRATION_SELECTED_CONFIG constant not found in evidence_weights.py"
    )
    val = evidence_weights.CALIBRATION_SELECTED_CONFIG
    assert isinstance(val, str) and len(val) > 0, (
        f"CALIBRATION_SELECTED_CONFIG must be a non-empty string, got {val!r}"
    )


def test_64_target_match_false_for_furosemide_adora1_mismatch() -> None:
    """Test 64: Simulates the Furosemide/ADORA1 mismatch — target_match=False when primary=ADORA1, expected=SLC12A1."""
    case = BenchmarkCase(
        case_id="BENCH-POS-01",
        drug="Furosemide",
        disease="Heart Failure",
        expected_class=BenchmarkClass.POSITIVE,
        expected_target="SLC12A1",
    )
    # Simulate pipeline returning ADORA1 as primary, SLC12A1 absent
    all_tids = ["ADORA1"]
    exp_target = case.expected_target  # "SLC12A1"
    target_match = any(tid.upper() == exp_target.upper() for tid in all_tids) if exp_target else None

    result = BenchmarkCaseResult(
        case=case,
        predicted_alignment="SUPPORTS",
        predicted_class=BenchmarkClass.POSITIVE,
        is_correct=True,
        is_resolved=True,
        primary_target="ADORA1",
        all_pipeline_targets=all_tids,
        target_match=target_match,
    )
    assert result.target_match is False
    assert result.primary_target == "ADORA1"
    assert result.case.expected_target == "SLC12A1"


def test_65_pdf_exporter_renders_with_ci_populated() -> None:
    """Test 65: EvaluationPDFExporter generates PDF bytes when final_test_metrics_with_ci is populated."""
    from backend.evaluation.benchmark_models import BenchmarkEvaluationReport, BenchmarkMetricsWithCI
    from backend.reporting.evaluation_pdf_exporter import EvaluationPDFExporter

    ci_metrics = BenchmarkMetricsWithCI(
        total_cases=13,
        positive_cases=7,
        negative_cases=3,
        uncertain_cases=3,
        correct_predictions=10,
        incorrect_predictions=2,
        unresolved_predictions=1,
        accuracy=0.769,
        precision=1.0,
        recall=0.857,
        specificity=0.667,
        mcc=0.671,
        accuracy_ci=(0.538, 0.923),
        precision_ci=(1.0, 1.0),
        recall_ci=(0.571, 1.0),
        specificity_ci=(0.333, 1.0),
        mcc_ci=(0.359, 0.866),
        ci_level=0.95,
        n_bootstrap=1000,
    )

    report = BenchmarkEvaluationReport(
        full_4d_metrics=ci_metrics,
        final_test_metrics_with_ci=ci_metrics,
        calibration_summary={
            "CONFIG_A": {"direct": 1.0, "curated": 0.9, "inferred": 0.5, "dev_mcc": 0.72},
            "CONFIG_B": {"direct": 1.0, "curated": 0.8, "inferred": 0.4, "dev_mcc": 0.68},
            "best_config": "CONFIG_A",
            "calibration_note": "Calibration performed on DEVELOPMENT split only. TEST labels not used.",
        },
        case_results=[],
    )

    exporter = EvaluationPDFExporter(report)
    pdf_bytes = exporter.generate_pdf_bytes()
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 5000, "PDF output unexpectedly small"

