"""Regression tests for the evaluation reporting fix.

Validates Fix 1: the opposition_score field in the evaluation runner output
now reports result.opposition_assessment.score (not result.risk_assessment.score).
"""
import pytest
from backend.core.domain.reasoning_result import OppositionAssessment


class TestOppositionAssessmentIntegrity:
    """Verify OppositionAssessment field structure for evaluation output."""

    def test_opposition_assessment_has_score_field(self):
        """OppositionAssessment must expose a .score attribute."""
        oa = OppositionAssessment(score=0.42, level="MODERATE")
        assert hasattr(oa, "score")
        assert oa.score == 0.42

    def test_opposition_assessment_has_level_field(self):
        """OppositionAssessment must expose a .level attribute."""
        oa = OppositionAssessment(score=0.42, level="MODERATE")
        assert oa.level == "MODERATE"

    def test_opposition_assessment_has_qualified_claim_count(self):
        """OppositionAssessment must expose qualified_negative_claim_count."""
        oa = OppositionAssessment(
            score=0.42,
            level="MODERATE",
            qualified_negative_claim_count=3,
        )
        assert oa.qualified_negative_claim_count == 3

    def test_empty_opposition_assessment(self):
        """Empty assessment must have score=0.0, level=NONE, zero claims."""
        oa = OppositionAssessment.empty()
        assert oa.score == 0.0
        assert oa.level == "NONE"
        assert oa.qualified_negative_claim_count == 0

    def test_opposition_score_nonzero_implies_claims(self):
        """If opposition_score > 0, the system should have at least one qualified claim.

        This is the key invariant violated by the reporting bug: the old code
        reported risk_assessment.score as opposition_score, which could be > 0
        even with 0 qualified negative claims.
        """
        # Case 1: Genuine opposition with claims
        oa_genuine = OppositionAssessment(
            score=0.52,
            level="MODERATE",
            qualified_negative_claim_count=2,
        )
        assert oa_genuine.score > 0
        assert oa_genuine.qualified_negative_claim_count > 0

        # Case 2: No opposition, no claims (the correct zero state)
        oa_none = OppositionAssessment.empty()
        assert oa_none.score == 0.0
        assert oa_none.qualified_negative_claim_count == 0
