"""Phase 5.1-5.3 regression tests.

Tests the mechanistic score semantics (Phase 5.1 score_components),
recommendation quality gate (Phase 5.2 Rule 1b), and directional
mechanism PARTIAL state (Phase 5.3).

Each test is deterministic and self-contained - no external DB or API calls.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from backend.core.domain.candidate_mechanism import CandidateMechanism, MechanismHop
from backend.core.domain.reasoning_result import (
    MechanisticAssessment,
    SupportAssessment,
    RiskAssessment,
)
from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.enums.causal_grounding import CausalGrounding
from backend.core.enums.recommendation import RecommendationStatus
from backend.reasoning.directional.directional_mechanism_evaluator import (
    DirectionalMechanismEvaluator,
)
from backend.reasoning.mechanistic.multi_hop_reasoner import MultiHopReasoner
from backend.reasoning.directional.chembl_polarity import chembl_action_to_polarity
from backend.reasoning.directional.reactome_polarity import reactome_role_to_polarity


# Helpers

def _make_hop(
    from_node: str,
    to_node: str,
    predicate: str,
    polarity: str = "UNKNOWN",
    causal_grounding: str = "STRUCTURAL",
    evidence_strength: float = 0.7,
    source_database: str = "Reactome",
) -> MechanismHop:
    return MechanismHop(
        from_node=from_node,
        to_node=to_node,
        predicate=predicate,
        polarity=polarity,
        causal_grounding=causal_grounding,
        evidence_strength=evidence_strength,
        source_database=source_database,
    )


def _make_candidate(
    support_level: str,
    confidence_score: float,
    hops: list | None = None,
    structural_edge_count: int = 3,
    independent_evidence_groups: int = 0,
    grounded_edge_count: int = 0,
    candidate_index: int = 1,
) -> CandidateMechanism:
    return CandidateMechanism(
        candidate_index=candidate_index,
        name=f"Mechanism {candidate_index}",
        support_level=support_level,
        confidence_score=confidence_score,
        hops=hops or [],
        structural_edge_count=structural_edge_count,
        independent_evidence_groups=independent_evidence_groups,
        grounded_edge_count=grounded_edge_count,
    )


# MECHANISTIC TESTS (1-8)

class TestMechanisticScoreSemantics:

    def test_1_no_valid_path_ms_zero(self):
        """MS = 0 when no candidates exist."""
        reasoner = MultiHopReasoner()
        score, level = reasoner.compute_mechanistic_score_from_candidates([])
        assert score == 0.0
        assert level == "NONE"

    def test_2_weak_speculative_raw_score_preserved(self):
        """WEAK_SPECULATIVE: MS = raw confidence (not multiplied). Level = LOW."""
        cand = _make_candidate("WEAK_SPECULATIVE", 0.409)
        reasoner = MultiHopReasoner()
        score, level = reasoner.compute_mechanistic_score_from_candidates([cand])
        assert score == pytest.approx(0.409, abs=0.01)
        assert level == "LOW"

    def test_3_moderately_supported_yields_medium_level(self):
        """MODERATELY_SUPPORTED candidate -> level MEDIUM."""
        cand = _make_candidate("MODERATELY_SUPPORTED", 0.55)
        reasoner = MultiHopReasoner()
        score, level = reasoner.compute_mechanistic_score_from_candidates([cand])
        assert score == pytest.approx(0.55, abs=0.01)
        assert level == "MEDIUM"

    def test_4_strongly_supported_yields_high_level(self):
        """STRONGLY_SUPPORTED -> level HIGH."""
        cand = _make_candidate("STRONGLY_SUPPORTED", 0.80)
        reasoner = MultiHopReasoner()
        score, level = reasoner.compute_mechanistic_score_from_candidates([cand])
        assert score == pytest.approx(0.80, abs=0.01)
        assert level == "HIGH"

    def test_5_structural_edge_count_field_exists(self):
        """CandidateMechanism.structural_edge_count is stored and serialized."""
        cand = _make_candidate("WEAK_SPECULATIVE", 0.40, structural_edge_count=4)
        assert cand.structural_edge_count == 4
        d = cand.to_dict()
        assert "structural_edge_count" in d
        assert d["structural_edge_count"] == 4

    def test_6_independent_evidence_groups_field_exists(self):
        """CandidateMechanism.independent_evidence_groups is stored and serialized."""
        cand = _make_candidate("WEAK_SPECULATIVE", 0.40, independent_evidence_groups=2)
        assert cand.independent_evidence_groups == 2
        d = cand.to_dict()
        assert "independent_evidence_groups" in d
        assert d["independent_evidence_groups"] == 2

    def test_7_contradicted_candidates_excluded(self):
        """CONTRADICTED candidates are excluded from scoring. Next usable candidate is used."""
        cands = [
            _make_candidate("CONTRADICTED", 0.80, candidate_index=1),
            _make_candidate("WEAK_SPECULATIVE", 0.35, candidate_index=2),
        ]
        reasoner = MultiHopReasoner()
        score, level = reasoner.compute_mechanistic_score_from_candidates(cands)
        assert score == pytest.approx(0.35, abs=0.01)
        assert level == "LOW"

    def test_8_score_components_on_mechanistic_assessment(self):
        """MechanisticAssessment.score_components is a dict[str, Any] with default={}."""
        ma = MechanisticAssessment(score=0.40, level="LOW")
        assert isinstance(ma.score_components, dict)
        assert ma.score_components == {}

        ma2 = MechanisticAssessment(
            score=0.40,
            level="LOW",
            score_components={
                "raw_confidence": 0.40,
                "support_level": "WEAK_SPECULATIVE",
                "structural_edge_count": 3,
                "causal_edge_count": 0,
                "grounded_edge_count": 0,
                "independent_evidence_groups": 0,
                "reaction_enriched": False,
                "candidate_count": 1,
                "best_candidate_name": "Mechanism 1",
            },
        )
        assert ma2.score_components["support_level"] == "WEAK_SPECULATIVE"
        assert ma2.score_components["reaction_enriched"] is False


# DIRECTIONAL TESTS (9-17)

class TestDirectionalMechanismSemantics:

    def test_9_inhibitor_negative_polarity(self):
        pol = chembl_action_to_polarity("INHIBITOR")
        assert pol == MolecularPolarity.NEGATIVE

    def test_10_agonist_positive_polarity(self):
        pol = chembl_action_to_polarity("AGONIST")
        assert pol == MolecularPolarity.POSITIVE

    def test_11_modulator_unknown_polarity(self):
        pol = chembl_action_to_polarity("MODULATOR")
        assert pol == MolecularPolarity.UNKNOWN

    def test_12_reactome_catalyst_unknown(self):
        pol = reactome_role_to_polarity("CATALYST")
        assert pol == MolecularPolarity.UNKNOWN

    def test_13_reactome_positive_regulator_positive(self):
        pol = reactome_role_to_polarity("POSITIVE_REGULATOR")
        assert pol == MolecularPolarity.POSITIVE

    def test_14_reactome_negative_regulator_negative(self):
        pol = reactome_role_to_polarity("NEGATIVE_REGULATOR")
        assert pol == MolecularPolarity.NEGATIVE

    def test_15_agonist_plus_inhibition_required_contradictory(self):
        """AGONIST + disease requires INHIBITION -> CONTRADICTORY."""
        evaluator = DirectionalMechanismEvaluator()
        hop0 = _make_hop("Drug", "Target:AR", predicate="AGONIST", polarity="POSITIVE", causal_grounding="CURATED")
        cand = _make_candidate("WEAK_SPECULATIVE", 0.40, hops=[hop0])
        result = evaluator.evaluate_candidate(cand, package=None, disease_required_action="INHIBITION", drug_action="AGONIST")
        assert result.path_direction_status == "CONTRADICTORY"
        assert result.contradiction_detected is True
        assert result.directionally_consistent is False

    def test_16_inhibitor_plus_structural_intermediates_partial(self):
        """INHIBITOR + INHIBITION required + structural intermediate hops -> PARTIAL."""
        evaluator = DirectionalMechanismEvaluator()
        hop0 = _make_hop("Drug", "Target:MMP1", predicate="INHIBITOR", polarity="NEGATIVE", causal_grounding="CURATED")
        hop1 = _make_hop("Target:MMP1", "Pathway:P1", predicate="PARTICIPATES_IN", polarity="UNKNOWN", causal_grounding="STRUCTURAL")
        hop2 = _make_hop("Pathway:P1", "Gene:G1", predicate="CONTAINS_GENE", polarity="UNKNOWN", causal_grounding="STRUCTURAL")
        hop3 = _make_hop("Gene:G1", "Disease:HF", predicate="ASSOCIATED_WITH", polarity="UNKNOWN", causal_grounding="STRUCTURAL")
        cand = _make_candidate("WEAK_SPECULATIVE", 0.409, hops=[hop0, hop1, hop2, hop3])
        result = evaluator.evaluate_candidate(cand, package=None, disease_required_action="INHIBITION", drug_action="INHIBITOR")
        assert result.path_direction_status == "PARTIAL", (
            f"Expected PARTIAL, got {result.path_direction_status}. Explanation: {result.explanation}"
        )
        assert result.directionally_consistent is None
        assert result.contradiction_detected is False

    def test_17_unknown_action_does_not_become_contradictory(self):
        """MODULATOR/unknown action -> UNKNOWN, never CONTRADICTORY."""
        evaluator = DirectionalMechanismEvaluator()
        hop0 = _make_hop("Drug", "Target:NA", predicate="MODULATES", polarity="UNKNOWN", causal_grounding="STRUCTURAL")
        cand = _make_candidate("WEAK_SPECULATIVE", 0.35, hops=[hop0])
        result = evaluator.evaluate_candidate(cand, package=None, disease_required_action="UNKNOWN", drug_action="MODULATES")
        assert result.path_direction_status == "UNKNOWN"
        assert result.contradiction_detected is False
        assert result.directionally_consistent is None


# RECOMMENDATION TESTS (18-20)

class TestRecommendationGating:

    def _make_triple(self, ss, ms, rs, support_level="WEAK_SPECULATIVE"):
        support = SupportAssessment(
            score=ss,
            level="HIGH" if ss >= 0.7 else "MEDIUM" if ss >= 0.4 else "LOW",
            evidence_count=5,
            weighted_sum=2.0,
            # Rule 1c gate: set has_high_quality_therapeutic=True for non-WEAK_SPECULATIVE tests
            # so they can still reach PROMISING when SS and MS qualify.
            # Rule 1b (MECHANISTIC QUALITY GATE) blocks WEAK_SPECULATIVE before Rule 1c fires.
            has_high_quality_therapeutic=(support_level != "WEAK_SPECULATIVE"),
        )
        mechanistic = MechanisticAssessment(
            score=ms,
            level="HIGH" if ms >= 0.7 else "MEDIUM" if ms >= 0.4 else "LOW",
            score_components={
                "raw_confidence": ms,
                "support_level": support_level,
                "structural_edge_count": 3,
                "causal_edge_count": 0,
                "grounded_edge_count": 0,
                "independent_evidence_groups": 0,
                "reaction_enriched": False,
                "candidate_count": 1,
                "best_candidate_name": "Mechanism 1",
            },
        )
        risk = RiskAssessment(
            score=rs,
            level="HIGH" if rs >= 0.7 else "MEDIUM" if rs >= 0.4 else "LOW",
            failed_trial_count=0,
            contradiction_count=0,
        )
        return support, mechanistic, risk

    def _make_mocks(self, boxed_warning=False, grade="B", approved=False):
        package = MagicMock()
        package.sources_failed = []
        package.drug.name = "TestDrug"
        package.disease.name = "TestDisease"
        safety = MagicMock()
        safety.has_boxed_warning = boxed_warning
        safety.overall_safety_grade = grade
        prior = MagicMock()
        prior.has_established_precedent = False
        prior.matched_indication_term = ""
        prior.evidence_boost = 0.0
        sci_ctx = MagicMock()
        sci_ctx.regulatory.status = "APPROVED" if approved else "NOT_APPROVED"
        sci_ctx.regulatory.confidence = 1.0 if approved else 0.0
        return package, safety, prior, sci_ctx

    def test_18_weak_speculative_blocked_from_promising(self):
        """WEAK_SPECULATIVE + MS>=0.40 + SS>=0.40 + RS<=0.39 -> UNCERTAIN (Rule 1b fires)."""
        from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
        orchestrator = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        support, mechanistic, risk = self._make_triple(ss=0.50, ms=0.41, rs=0.20, support_level="WEAK_SPECULATIVE")
        pkg, safety, prior, sci_ctx = self._make_mocks()
        status, reasons = orchestrator._apply_rules(support, mechanistic, risk, [], pkg, safety, prior, sci_ctx)
        assert status == RecommendationStatus.UNCERTAIN, f"Got {status.value}. Reasons: {reasons}"
        assert any("MECHANISTIC QUALITY GATE" in r for r in reasons)

    def test_19_moderately_supported_reaches_promising(self):
        """MODERATELY_SUPPORTED + MS>=0.40 + SS>=0.40 + RS<=0.39 -> PROMISING (Rule 1a fires)."""
        from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
        orchestrator = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        support, mechanistic, risk = self._make_triple(ss=0.55, ms=0.50, rs=0.15, support_level="MODERATELY_SUPPORTED")
        pkg, safety, prior, sci_ctx = self._make_mocks()
        status, reasons = orchestrator._apply_rules(support, mechanistic, risk, [], pkg, safety, prior, sci_ctx)
        assert status == RecommendationStatus.PROMISING, f"Got {status.value}. Reasons: {reasons}"

    def test_20_safety_veto_overrides_strong_mechanism(self):
        """Boxed warning + high risk -> NOT_RECOMMENDED regardless of mechanism quality."""
        from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
        orchestrator = ReasoningOrchestrator.__new__(ReasoningOrchestrator)
        support, mechanistic, risk = self._make_triple(ss=0.80, ms=0.75, rs=0.65, support_level="STRONGLY_SUPPORTED")
        risk_high = RiskAssessment(score=0.65, level="HIGH", failed_trial_count=0, contradiction_count=0)
        pkg, safety, prior, sci_ctx = self._make_mocks(boxed_warning=True, grade="D")
        status, reasons = orchestrator._apply_rules(support, mechanistic, risk_high, [], pkg, safety, prior, sci_ctx)
        assert status == RecommendationStatus.NOT_RECOMMENDED, f"Got {status.value}"
