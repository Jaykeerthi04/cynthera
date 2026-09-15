"""Domain models for Phase 4E — Benchmark and Ablation Framework.

Defines:
- BenchmarkClass (POSITIVE, NEGATIVE, UNCERTAIN)
- BenchmarkSplit (DEVELOPMENT, VALIDATION, TEST)
- ExecutionStatus (SUCCESS, FAILED, SKIPPED)
- BenchmarkCase (metadata, rationale, expected class, label provenance, split)
- ConfusionMatrix3x3 (Expected vs Predicted 3x3 table)
- BenchmarkMetrics (Accuracy, Precision, Recall, Specificity, F1, MCC with N/A support)
- BenchmarkCaseResult (Evaluation output per benchmark case)
- AblationConfig & AblationResult (Ablation study models)
- AblationVerification (Evidence-level verification of ablation correctness)
- WeightedBenchmarkCaseResult (Weighted evaluation output)
- WeightingComparisonResult (Equal-vote vs weighted comparison)
- ContradictionMetrics (Conflict detection metrics)
- BenchmarkEvaluationReport (Complete serialization container for UI and PDF)
"""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class BenchmarkClass(str, Enum):
    """Ground truth and predicted evaluation classes."""
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNCERTAIN = "UNCERTAIN"


class BenchmarkSplit(str, Enum):
    """Dataset split designation for temporal or random holdout partitioning."""
    DEVELOPMENT = "DEVELOPMENT"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


class ExecutionStatus(str, Enum):
    """Execution status for a single benchmark case."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AblationConfig(str, Enum):
    """Ablation configuration modes."""
    FULL_4D = "FULL_4D"
    NO_OPEN_TARGETS = "NO_OPEN_TARGETS"
    NO_DATTS = "NO_DATTS"
    NO_DRUGMECHDB = "NO_DRUGMECHDB"
    NO_INDEPENDENCE_GROUPING = "NO_INDEPENDENCE_GROUPING"
    NO_EVIDENCE_WEIGHTING = "NO_EVIDENCE_WEIGHTING"
    WEIGHTED_4D = "WEIGHTED_4D"


def map_alignment_to_class(alignment: str) -> BenchmarkClass:
    """Normalize Phase 4D alignment verdicts into benchmark evaluation classes.

    Mapping:
        SUPPORTS     -> POSITIVE
        OPPOSES      -> NEGATIVE
        INSUFFICIENT -> UNCERTAIN
        MIXED        -> UNCERTAIN
    """
    al = (alignment or "").upper().strip()
    if al == "SUPPORTS":
        return BenchmarkClass.POSITIVE
    elif al == "OPPOSES":
        return BenchmarkClass.NEGATIVE
    elif al in ("INSUFFICIENT", "MIXED"):
        return BenchmarkClass.UNCERTAIN
    return BenchmarkClass.UNCERTAIN


def map_recommendation_to_class(rec: Any) -> BenchmarkClass:
    """Normalize canonical production RecommendationStatus into benchmark evaluation classes.

    Distinguishes the final production recommendation verdict from the
    intermediate analytical therapeutic alignment verdict.

    Mapping:
        PROMISING         -> POSITIVE
        NOT_RECOMMENDED   -> NEGATIVE
        UNCERTAIN         -> UNCERTAIN
        INSUFFICIENT_DATA -> UNCERTAIN
    """
    val = rec.value if hasattr(rec, "value") else str(rec or "").upper().strip()
    if val == "PROMISING":
        return BenchmarkClass.POSITIVE
    elif val == "NOT_RECOMMENDED":
        return BenchmarkClass.NEGATIVE
    return BenchmarkClass.UNCERTAIN


class BenchmarkCase(BaseModel):
    """A single drug-disease evaluation benchmark case.

    Label provenance fields document HOW and WHY a ground-truth label was assigned.
    This is required for scientific reproducibility and benchmark quality auditing.

    Attributes:
        case_id: Unique benchmark case identifier (e.g. 'BENCH-POS-01').
        drug: Drug common name.
        disease: Disease name.
        expected_class: Ground-truth benchmark label.
        expected_target: Primary biological target gene symbol if known.
        rationale: Scientific rationale for the expected label.
        evidence_reference: Primary citation or database reference supporting label.
        source: Data source(s) the label was derived from.
        notes: Additional comments.
        label_source: Where the ground truth label assignment originated (e.g. 'FDA Approval', 'PMID:XXXXXXXX', 'Expert curation').
        label_reference: Specific reference for the label (PMID, DOI, FDA URL, etc.).
        label_rationale: Scientific explanation of why this label was assigned.
        split: Dataset split this case belongs to (DEVELOPMENT / VALIDATION / TEST).
        evidence_cutoff_date: ISO date string of evidence cutoff, if applicable.
        unsuitable_for_directional_negative: If True, this negative case cannot produce OPPOSES
            from the live pipeline because directional annotations are unavailable for this
            target-disease pair in the configured data sources. The case is retained for
            dataset completeness documentation but excluded from directional specificity metrics.
    """
    case_id: str
    drug: str
    disease: str
    expected_class: BenchmarkClass
    expected_target: str | None = None
    rationale: str = ""
    evidence_reference: str = ""
    source: str = ""
    notes: str = ""
    # Label provenance (required for benchmark quality)
    label_source: str = ""
    label_reference: str = ""
    label_rationale: str = ""
    # Split and temporal metadata
    split: BenchmarkSplit = BenchmarkSplit.TEST
    evidence_cutoff_date: str | None = None
    # Quality flags
    unsuitable_for_directional_negative: bool = False


class ConfusionMatrix3x3(BaseModel):
    """3x3 confusion matrix covering POSITIVE, NEGATIVE, UNCERTAIN."""
    matrix: dict[str, dict[str, int]] = Field(
        default_factory=lambda: {
            "POSITIVE": {"POSITIVE": 0, "NEGATIVE": 0, "UNCERTAIN": 0},
            "NEGATIVE": {"POSITIVE": 0, "NEGATIVE": 0, "UNCERTAIN": 0},
            "UNCERTAIN": {"POSITIVE": 0, "NEGATIVE": 0, "UNCERTAIN": 0},
        }
    )

    def record(self, expected: BenchmarkClass | str, predicted: BenchmarkClass | str) -> None:
        e_key = expected.value if hasattr(expected, "value") else str(expected).upper()
        p_key = predicted.value if hasattr(predicted, "value") else str(predicted).upper()
        if e_key in self.matrix and p_key in self.matrix[e_key]:
            self.matrix[e_key][p_key] += 1

    def get(self, expected: BenchmarkClass | str, predicted: BenchmarkClass | str) -> int:
        e_key = expected.value if hasattr(expected, "value") else str(expected).upper()
        p_key = predicted.value if hasattr(predicted, "value") else str(predicted).upper()
        return self.matrix.get(e_key, {}).get(p_key, 0)


class BenchmarkMetrics(BaseModel):
    """Evaluation metrics for a benchmark run.

    Handles missing class scenarios gracefully: unavailable metrics evaluate to None.
    """
    total_cases: int = 0
    positive_cases: int = 0
    negative_cases: int = 0
    uncertain_cases: int = 0

    correct_predictions: int = 0
    incorrect_predictions: int = 0
    unresolved_predictions: int = 0

    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    specificity: float | None = None
    f1_score: float | None = None
    mcc: float | None = None

    confusion_matrix: ConfusionMatrix3x3 = Field(default_factory=ConfusionMatrix3x3)
    notes: list[str] = Field(default_factory=list)


class BenchmarkCaseResult(BaseModel):
    """Detailed evaluation result for a single benchmark case."""
    case: BenchmarkCase
    predicted_alignment: str
    predicted_class: BenchmarkClass
    is_correct: bool
    is_resolved: bool
    primary_target: str | None = None
    # Target identity tracking (Phase 4E.5)
    all_pipeline_targets: list[str] = Field(default_factory=list)
    # True  = expected_target found among pipeline targets (case-insensitive)
    # False = expected_target not found
    # None  = case.expected_target was not specified
    target_match: bool | None = None
    target_alignments: list[dict[str, Any]] = Field(default_factory=list)
    directional_concordance: float = 0.0  # Renamed from confidence as required by Rule 6
    supporting_group_count: int = 0
    opposing_group_count: int = 0
    evidence_family_summary: dict[str, int] = Field(default_factory=dict)
    execution_status: ExecutionStatus = ExecutionStatus.SUCCESS
    error_message: str | None = None
    execution_time_ms: float = 0.0
    explanation: str = ""


class AblationVerification(BaseModel):
    """Records evidence-level verification that an ablation was correctly applied.

    Correctness of an ablation is determined by whether the intended evidence
    component was actually removed — NOT by whether the final prediction changed.
    Prediction change is an experimental observation recorded separately.

    Ablation is VERIFIED if:
        full_evidence_count != ablated_evidence_count
        OR
        full_independence_group_count != ablated_independence_group_count
        OR
        component_present_in_full == True and component_present_in_ablated == False

    If predictions happen to remain identical despite evidence removal, the ablation
    is still VERIFIED and CORRECT. This outcome indicates the removed component was
    not the deciding factor for this case.
    """
    case_id: str
    ablation_config: str
    full_evidence_count: int = 0
    ablated_evidence_count: int = 0
    full_independence_group_count: int = 0
    ablated_independence_group_count: int = 0
    component_present_in_full: bool = False
    component_present_in_ablated: bool = False
    evidence_representation_changed: bool = False
    prediction_changed: bool = False
    full_prediction: str = ""
    ablated_prediction: str = ""
    verification_passed: bool = False
    verification_note: str = ""


class AblationResult(BaseModel):
    """Result of running an ablation configuration across the benchmark dataset."""
    config_name: AblationConfig
    description: str
    metrics: BenchmarkMetrics
    case_predictions: dict[str, BenchmarkClass]
    changed_cases_from_full: list[dict[str, Any]] = Field(default_factory=list)
    verifications: list[AblationVerification] = Field(default_factory=list)
    # Summary: how many cases had evidence representation changed vs prediction changed
    evidence_changed_count: int = 0
    prediction_changed_count: int = 0


class WeightedBenchmarkCaseResult(BaseModel):
    """Weighted evaluation result for a single benchmark case (evaluation-only comparator).

    NOTE: This model is used exclusively by the evaluation framework to compare
    weighted vs equal-vote scoring. It does NOT replace or modify the production
    TherapeuticAlignmentEngine.align_target() path.

    The production pipeline always uses equal-vote independence-grouped alignment.
    Weighted alignment is an experimental comparator for research purposes only.
    """
    case: BenchmarkCase
    equal_vote_class: BenchmarkClass
    equal_vote_alignment: str
    weighted_class: BenchmarkClass
    weighted_alignment: str
    weight_config_name: str
    weighted_support: float = 0.0
    weighted_opposition: float = 0.0
    weighted_concordance: float = 0.0
    equal_vote_concordance: float = 0.0
    prediction_agrees: bool = True  # True if equal-vote and weighted produce same class


class WeightingComparisonResult(BaseModel):
    """Comparison of equal-vote vs weighted evaluation across benchmark cases.

    Used for sensitivity analysis to understand which cases are weight-sensitive.
    """
    weight_config_name: str
    total_cases: int = 0
    agreement_count: int = 0  # Cases where weighted == equal-vote
    disagreement_count: int = 0
    agreement_rate: float | None = None
    case_comparisons: list[WeightedBenchmarkCaseResult] = Field(default_factory=list)
    interpretation: str = ""


class ContradictionMetrics(BaseModel):
    """Metrics for conflict and contradiction detection capability.

    Definitions:
        contradiction_detection_rate: Fraction of genuine contradictory/opposing cases
            where directional conflict is detected (opposing groups > 0 or balanced).
        contradiction_resolution_rate: Fraction of contradictory cases correctly
            resolved to OPPOSES / NEGATIVE.
        balanced_conflict_insufficient_rate: Fraction of balanced conflicting cases
            correctly resolved to INSUFFICIENT / UNCERTAIN rather than arbitrary polarity.
        false_directional_resolution_rate: Fraction of contradictory cases falsely
            resolved to SUPPORTS / POSITIVE.
    """
    total_cases: int = 0
    contradiction_cases: int = 0
    balanced_conflict_cases: int = 0
    correctly_detected_conflicts: int = 0
    correctly_resolved_contradictions: int = 0
    correctly_resolved_balanced_conflicts: int = 0
    false_directional_resolutions: int = 0
    contradiction_detection_rate: float | None = None
    contradiction_resolution_rate: float | None = None
    balanced_conflict_insufficient_rate: float | None = None
    false_directional_resolution_rate: float | None = None
    notes: list[str] = Field(default_factory=list)


class BenchmarkMetricsWithCI(BenchmarkMetrics):
    """BenchmarkMetrics extended with bootstrap confidence intervals (Phase 4E.5).

    CI fields are None when not computed (e.g., for baseline/ablation runs).
    CI is computed only for the final TEST split run.

    Attributes:
        accuracy_ci: (lower, upper) 95% CI for accuracy.
        precision_ci: (lower, upper) 95% CI for precision.
        recall_ci: (lower, upper) 95% CI for recall.
        specificity_ci: (lower, upper) 95% CI for specificity.
        mcc_ci: (lower, upper) 95% CI for MCC.
        ci_level: Confidence level used (default 0.95).
        n_bootstrap: Number of bootstrap resamples used.
    """
    accuracy_ci: tuple[float, float] | None = None
    precision_ci: tuple[float, float] | None = None
    recall_ci: tuple[float, float] | None = None
    specificity_ci: tuple[float, float] | None = None
    mcc_ci: tuple[float, float] | None = None
    ci_level: float = 0.95
    n_bootstrap: int = 1000


class BenchmarkEvaluationReport(BaseModel):
    """Complete evaluation report containing benchmark results, ablations, and provenance."""
    benchmark_version: str = "v1.0"
    evaluation_timestamp: str = ""
    cache_version: str = "v4.2_phase4e_benchmark"
    baseline_metrics: BenchmarkMetrics = Field(default_factory=BenchmarkMetrics)
    full_4d_metrics: BenchmarkMetrics = Field(default_factory=BenchmarkMetrics)
    weighted_4d_metrics: BenchmarkMetrics | None = None  # None if weighting not run
    # Final TEST run with bootstrap CI (Phase 4E.5)
    final_test_metrics_with_ci: BenchmarkMetricsWithCI | None = None
    # Calibration summary: {config_name: dev_mcc, ...} populated after DEV calibration
    calibration_summary: dict[str, Any] = Field(default_factory=dict)
    case_results: list[BenchmarkCaseResult] = Field(default_factory=list)
    ablation_results: list[AblationResult] = Field(default_factory=list)
    evidence_family_contributions: dict[str, Any] = Field(default_factory=dict)
    summary_narrative: str = ""
    # Weighting and contradiction analysis (evaluation-only)
    weighting_comparison: WeightingComparisonResult | None = None
    contradiction_metrics: ContradictionMetrics | None = None
    # Dataset quality
    dataset_quality_metrics: dict[str, Any] = Field(default_factory=dict)
    benchmark_split_note: str = ""
