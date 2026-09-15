from types import SimpleNamespace

from backend.reasoning.directional.therapeutic_evidence import (
    is_therapeutically_eligible_evidence,
)


def record(title: str, abstract: str = ""):
    return SimpleNamespace(title=title, abstract=abstract)


def test_risk_factor_record_is_not_direct_therapeutic_support():
    eligible, reason = is_therapeutically_eligible_evidence(
        record("Aspirin as a risk factor for hemorrhagic stroke")
    )
    assert eligible is False
    assert "non-therapeutic" in reason or "Risk" in reason


def test_treatment_efficacy_record_remains_eligible():
    eligible, _ = is_therapeutically_eligible_evidence(
        record("Aspirin treatment efficacy in secondary stroke prevention")
    )
    assert eligible is True


def test_ambiguous_record_fails_open_to_contextual_pipeline():
    eligible, _ = is_therapeutically_eligible_evidence(record("Aspirin and stroke outcomes"))
    assert eligible is True
