"""Unit tests for CYNTHERA frontend modular components."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from backend.core.domain.contradiction_summary import ContradictionSummary
from backend.core.domain.reasoning_result import (
    MechanisticAssessment,
    ReasoningResult,
    RiskAssessment,
    ScientificAuditReport,
    SupportAssessment,
)
from backend.core.enums.recommendation import RecommendationStatus
from frontend.components.ablation_panel import render_ablation_panel
from frontend.components.benchmark_panel import render_benchmark_panel
from frontend.components.contradiction_panel import render_contradiction_panel
from frontend.components.directional_panel import render_directional_panel
from frontend.components.evidence_panel import render_evidence_panel
from frontend.components.mechanistic_panel import render_mechanistic_panel
from frontend.components.recommendation_panel import render_recommendation_panel
from frontend.components.scientific_explanation import render_scientific_explanation
from frontend.components.target_panel import render_target_panel


@pytest.fixture
def mock_result():
    """Create a minimal valid ReasoningResult for testing rendering."""
    ma = MechanisticAssessment(
        score=0.45,
        level="LOW",
        score_components={
            "raw_confidence": 0.45,
            "support_level": "WEAK_SPECULATIVE",
            "structural_edge_count": 3,
            "causal_edge_count": 0,
            "grounded_edge_count": 0,
            "independent_evidence_groups": 1,
            "reaction_enriched": False,
            "candidate_count": 1,
            "ranked_target": "SLC12A1",
            "target_count": 1,
            "directional_mechanism_state": "PARTIAL",
        },
        candidate_mechanisms=[{"directional_mechanism_status": "PARTIAL"}],
    )
    sa = SupportAssessment(score=0.55, level="MEDIUM", confidence=0.8)
    ra = RiskAssessment(score=0.15, level="LOW", failed_trial_count=0, contradiction_count=0)
    audit = ScientificAuditReport(
        summary="Test summary",
        therapeutic_alignment={
            "overall_alignment": "SUPPORTS",
            "target_alignments": [{"target_id": "SLC12A1", "alignment": "SUPPORTS", "confidence": 0.8}],
        },
    )
    cs = ContradictionSummary(
        has_conflict=True,
        strong_conflict=False,
        support_groups=2,
        opposition_groups=1,
        support_weight=2.0,
        opposition_weight=1.0,
        resolution="SUPPORTS",
        conflict_sources=["Literature conflict"],
    )
    res = ReasoningResult.__new__(ReasoningResult)
    object.__setattr__(res, "mechanistic_assessment", ma)
    object.__setattr__(res, "support_assessment", sa)
    object.__setattr__(res, "risk_assessment", ra)
    object.__setattr__(res, "audit_report", audit)
    object.__setattr__(res, "recommendation_status", RecommendationStatus.UNCERTAIN)
    object.__setattr__(
        res,
        "recommendation_reasons",
        ["Rule 1b (MECHANISTIC QUALITY GATE): Mechanistic score >= 0.40 but support_level is WEAK_SPECULATIVE."],
    )
    object.__setattr__(res, "contradiction_summary", cs)
    return res


def test_render_mechanistic_panel_defensive(mock_result):
    """Test render_mechanistic_panel executes without raising exceptions."""
    with patch("streamlit.markdown"), patch("streamlit.metric"), patch("streamlit.columns", side_effect=lambda n: [MagicMock() for _ in range(n)]), patch("streamlit.info"), patch("streamlit.expander"), patch("streamlit.dataframe"):
        render_mechanistic_panel(mock_result)
        # Also test None handling
        render_mechanistic_panel(None)


def test_render_directional_panel_defensive(mock_result):
    """Test render_directional_panel executes with PARTIAL and other states."""
    with patch("streamlit.markdown"), patch("streamlit.metric"), patch("streamlit.columns", return_value=[MagicMock(), MagicMock()]):
        render_directional_panel(mock_result)
        render_directional_panel(None)


def test_render_contradiction_panel_defensive(mock_result):
    """Test render_contradiction_panel executes with conflict handling."""
    with patch("streamlit.markdown"), patch("streamlit.metric"), patch("streamlit.columns", return_value=[MagicMock(), MagicMock(), MagicMock(), MagicMock()]), patch("streamlit.warning"), patch("streamlit.info"), patch("streamlit.expander"):
        render_contradiction_panel(mock_result)
        render_contradiction_panel(None)


def test_render_target_panel_defensive(mock_result):
    """Test render_target_panel executes and verifies target match."""
    with patch("streamlit.markdown"), patch("streamlit.columns", return_value=[MagicMock(), MagicMock(), MagicMock()]), patch("streamlit.success"), patch("streamlit.caption"), patch("streamlit.expander"):
        render_target_panel(mock_result, expected_target="SLC12A1")
        render_target_panel(None)


def test_render_evidence_panel_defensive(mock_result):
    """Test render_evidence_panel displays frozen CONFIG_A metadata."""
    with patch("streamlit.markdown"), patch("streamlit.columns", return_value=[MagicMock(), MagicMock()]), patch("streamlit.dataframe"), patch("streamlit.info"):
        render_evidence_panel(mock_result)
        render_evidence_panel(None)


def test_render_recommendation_panel_defensive(mock_result):
    """Test render_recommendation_panel displays Rule 1b decision trace."""
    with patch("streamlit.markdown"), patch("streamlit.dataframe"), patch("streamlit.warning"), patch("streamlit.info"), patch("streamlit.error"), patch("streamlit.success"):
        render_recommendation_panel(mock_result)
        render_recommendation_panel(None)


def test_render_scientific_explanation():
    """Test render_scientific_explanation renders epistemic distinctions."""
    with patch("streamlit.markdown"), patch("streamlit.columns", return_value=[MagicMock(), MagicMock()]):
        render_scientific_explanation()


def test_render_benchmark_and_ablation_panels():
    """Test render_benchmark_panel and render_ablation_panel display frozen results."""
    with patch("streamlit.markdown"), patch("streamlit.info"), patch("streamlit.dataframe"), patch("streamlit.table"), patch("streamlit.expander"), patch("streamlit.download_button"):
        render_benchmark_panel(None)
        render_ablation_panel(None)
