"""EvaluationConfig — configurable evidence-source control for benchmark ablation studies.

Design Notes
------------
EvaluationConfig controls which evidence components are included in a benchmark evaluation
run. It operates by filtering the already-retrieved RetrievalPackage evidence BEFORE
DirectionalEvidenceBuilder.build_all() is called.

Scope of equivalence:
    Source filtering in EvaluationConfig is equivalent to disabling the connector
    for the purpose of DOWNSTREAM EVIDENCE CONTRIBUTION ONLY.
    It is NOT equivalent for testing retrieval behavior, cache behavior, network
    latency effects, or connector-level error handling. Those require separate
    integration-level testing with connectors disabled at the network boundary.

This distinction is documented explicitly because ablation studies are valid for
measuring the contribution of each evidence source to final alignment decisions,
which is what we need for Phase 4E.

Ablation correctness:
    An ablation is CORRECTLY APPLIED if the evidence component is actually absent
    from the filtered package passed to DirectionalEvidenceBuilder. Whether the
    final prediction changes is an EXPERIMENTAL OBSERVATION — not a correctness
    requirement. Evidence representation change is verified separately via
    AblationVerification records.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvaluationConfig:
    """Immutable configuration controlling which evidence sources contribute to evaluation.

    Attributes:
        name: Human-readable configuration name.
        use_open_targets: Include Open Targets Direction-of-Effect (DoE) evidence.
        use_datts: Include DATTs curated disease-target required-action evidence.
        use_drugmechdb: Include DrugMechDB mechanistic path evidence.
        use_independence_grouping: Apply publication-level independence grouping.
            If False, each raw evidence row casts one vote (naive row counting).
            This inflates multi-row evidence sources relative to single-row sources.
        use_evidence_weighting: Apply causal-grounding-tier weights to evidence groups.
            If False, all evidence groups contribute equally (binary vote).
            NOTE: This is an evaluation-only comparator. Production always uses False.
        use_literature_direction: Include grounded literature directional claims.
        weight_config_name: Name of WeightConfig to use when use_evidence_weighting=True.
            Must match a key in WEIGHT_CONFIGS from evidence_weights.py.
    """
    name: str = "FULL_4D"
    use_open_targets: bool = True
    use_datts: bool = True
    use_drugmechdb: bool = True
    use_independence_grouping: bool = True
    use_evidence_weighting: bool = False
    use_literature_direction: bool = True
    weight_config_name: str = "DEFAULT_HEURISTIC"


# ── Standard evaluation configurations ───────────────────────────────────────

EVALUATION_CONFIGS: dict[str, EvaluationConfig] = {
    "FULL_4D": EvaluationConfig(
        name="FULL_4D",
    ),
    "NO_OPEN_TARGETS": EvaluationConfig(
        name="NO_OPEN_TARGETS",
        use_open_targets=False,
    ),
    "NO_DATTS": EvaluationConfig(
        name="NO_DATTS",
        use_datts=False,
    ),
    "NO_DRUGMECHDB": EvaluationConfig(
        name="NO_DRUGMECHDB",
        use_drugmechdb=False,
    ),
    "NO_INDEPENDENCE_GROUPING": EvaluationConfig(
        name="NO_INDEPENDENCE_GROUPING",
        use_independence_grouping=False,
    ),
    "NO_EVIDENCE_WEIGHTING": EvaluationConfig(
        name="NO_EVIDENCE_WEIGHTING",
        use_evidence_weighting=False,
    ),
    "WEIGHTED_4D_A": EvaluationConfig(
        name="WEIGHTED_4D_A",
        use_evidence_weighting=True,
        weight_config_name="CONFIG_A",
    ),
    "WEIGHTED_4D_B": EvaluationConfig(
        name="WEIGHTED_4D_B",
        use_evidence_weighting=True,
        weight_config_name="CONFIG_B",
    ),
    "WEIGHTED_4D_C": EvaluationConfig(
        name="WEIGHTED_4D_C",
        use_evidence_weighting=True,
        weight_config_name="CONFIG_C",
    ),
}
