"""Statistical outcome direction and reason code enumerations.

Provides explicit, scientifically sound categories for interpreting
ClinicalTrials.gov resultsSection statistical analyses.
"""
from enum import Enum


class OutcomeDirection(str, Enum):
    """Semantic direction of a clinical trial outcome measure."""

    POSITIVE = "POSITIVE"
    """Demonstrated statistically significant therapeutic benefit or non-inferiority/equivalence."""

    NEGATIVE = "NEGATIVE"
    """Genuine therapeutic failure, explicit futility, or statistically significant harm on primary disease endpoint."""

    NEUTRAL = "NEUTRAL"
    """Non-significant difference (p >= 0.05, CI crosses unity) without explicit futility or harm.
    Crucially: does NOT establish therapeutic failure or opposition.
    """

    INCONCLUSIVE = "INCONCLUSIVE"
    """Incomplete statistical context, ambiguous non-inferiority margin, or conflicting signals."""

    SAFETY_HARM = "SAFETY_HARM"
    """Safety / adverse event endpoint showing elevated risk/harm.
    Separated from therapeutic efficacy opposition.
    """

    UNKNOWN = "UNKNOWN"
    """Non-efficacy endpoint (device usability, PK, patient preference), unanalyzed descriptive data, or missing context."""


class StatisticalReasonCode(str, Enum):
    """Audit reason codes explaining why an outcome was classified."""

    STATISTICALLY_SIGNIFICANT_BENEFIT = "STATISTICALLY_SIGNIFICANT_BENEFIT"
    STATISTICALLY_SIGNIFICANT_HARM = "STATISTICALLY_SIGNIFICANT_HARM"
    EXPLICIT_FUTILITY = "EXPLICIT_FUTILITY"
    EXPLICIT_LACK_OF_EFFICACY = "EXPLICIT_LACK_OF_EFFICACY"
    EXPLICIT_TERMINATION_FOR_HARM = "EXPLICIT_TERMINATION_FOR_HARM"
    NON_SIGNIFICANT_PRIMARY_ENDPOINT = "NON_SIGNIFICANT_PRIMARY_ENDPOINT"
    NON_SIGNIFICANT_SECONDARY_ENDPOINT = "NON_SIGNIFICANT_SECONDARY_ENDPOINT"
    NON_SIGNIFICANT_SUBGROUP = "NON_SIGNIFICANT_SUBGROUP"
    NON_INFERIOR = "NON_INFERIOR"
    NON_INFERIORITY_FAILURE = "NON_INFERIORITY_FAILURE"
    EQUIVALENT = "EQUIVALENT"
    EQUIVALENCE_FAILURE = "EQUIVALENCE_FAILURE"
    SINGLE_ARM_NO_COMPARATOR = "SINGLE_ARM_NO_COMPARATOR"
    SAFETY_ENDPOINT = "SAFETY_ENDPOINT"
    INSUFFICIENT_STATISTICAL_CONTEXT = "INSUFFICIENT_STATISTICAL_CONTEXT"
    NON_EFFICACY_ENDPOINT = "NON_EFFICACY_ENDPOINT"


class OutcomeEvaluationResult(tuple):
    """Result of statistical outcome evaluation.

    Inherits from tuple (direction, reason) for 100% backward compatibility
    with existing code unpacking `direction, reason = eval(...)`, while also
    providing structured attributes:
        .direction (OutcomeDirection)
        .reason (str | None)
        .reason_code (StatisticalReasonCode | None)
    """

    direction: OutcomeDirection
    reason: str | None
    reason_code: StatisticalReasonCode | None

    def __new__(
        cls,
        direction: OutcomeDirection | str,
        reason: str | None,
        reason_code: StatisticalReasonCode | str | None = None,
    ):
        dir_val = direction.value if isinstance(direction, OutcomeDirection) else str(direction)
        code_val = (
            reason_code
            if (reason_code is None or isinstance(reason_code, StatisticalReasonCode))
            else StatisticalReasonCode(str(reason_code))
        )
        instance = super().__new__(cls, (dir_val, reason))
        instance.direction = OutcomeDirection(dir_val)
        instance.reason = reason
        instance.reason_code = code_val
        return instance

    def __repr__(self) -> str:
        return f"OutcomeEvaluationResult(direction={self.direction.value!r}, reason={self.reason!r}, reason_code={self.reason_code.value if self.reason_code else None!r})"

