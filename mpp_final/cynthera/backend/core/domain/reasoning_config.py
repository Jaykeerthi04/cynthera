"""ReasoningConfig domain model (Phase 5.15).

Feature flags and configuration for the Phase 5.13-5.15 reasoning architecture.
Guarantees full backward compatibility: all new reasoning modules default to False.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReasoningConfig:
    """Configuration switch controlling activation of Phase 5.13-5.15 reasoning.

    Attributes:
        enable_production_evidence_weighting: If True, activates multi-dimensional evidence weighting.
        enable_multitarget_synthesis: If True, activates multi-target synthesis engine.
        enable_contradiction_propagation: If True, activates hierarchical contradiction propagation.
    """

    enable_production_evidence_weighting: bool = False
    enable_multitarget_synthesis: bool = False
    enable_contradiction_propagation: bool = False


# Default configuration: 100% preservation of legacy production behavior
DEFAULT_REASONING_CONFIG = ReasoningConfig()
