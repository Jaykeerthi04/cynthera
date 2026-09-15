"""Contradiction and Epistemic Uncertainty Panel for CYNTHERA frontend."""
from __future__ import annotations

import streamlit as st
from typing import Any


def render_contradiction_panel(result: Any, package: Any | None = None) -> None:
    """Render the Contradiction & Uncertainty panel reflecting Phase 5.6 capabilities.

    Explicitly preserves conflicts and prevents forcing unknown or contradictory evidence
    into false positive or negative classifications.
    """
    st.markdown("### ⚡ Contradiction & Uncertainty")

    cs = getattr(result, "contradiction_summary", None)
    ta_dict = getattr(result.audit_report, "therapeutic_alignment", {}) if getattr(result, "audit_report", None) else {}

    # Safe extraction
    if cs is not None:
        supp_groups = getattr(cs, "support_groups", 0)
        opp_groups = getattr(cs, "opposition_groups", 0)
        has_conflict = getattr(cs, "has_conflict", False)
        strong_conflict = getattr(cs, "strong_conflict", False)
        resolution = getattr(cs, "resolution", "INSUFFICIENT")
        conflict_sources = getattr(cs, "conflict_sources", []) or []
        explanation = getattr(cs, "explanation", "")
        supp_weight = getattr(cs, "support_weight", 0.0)
        opp_weight = getattr(cs, "opposition_weight", 0.0)
    else:
        # Fallback to therapeutic_alignment dict
        supp_groups = ta_dict.get("supporting_groups_count", 0)
        opp_groups = ta_dict.get("opposing_groups_count", 0)
        has_conflict = (supp_groups > 0 and opp_groups > 0)
        strong_conflict = False
        resolution = ta_dict.get("overall_alignment", "INSUFFICIENT")
        conflict_sources = []
        explanation = ta_dict.get("explanation", "")
        supp_weight = float(supp_groups)
        opp_weight = float(opp_groups)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Supporting Groups", f"{supp_groups} (wt: {supp_weight:.1f})")
    with c2:
        st.metric("Opposing Groups", f"{opp_groups} (wt: {opp_weight:.1f})")
    with c3:
        st.metric("Conflict Detected", "YES" if has_conflict else "NO")
    with c4:
        st.metric("Resolution", str(resolution))

    # Prominent warning on strong conflict
    if strong_conflict:
        st.warning(
            "⚠️ **Strong Contradictory Evidence Detected**: "
            "Both supporting and opposing directions have high-confidence curated evidence. "
            "The system preserves this conflict and does NOT force an artificial directional resolution."
        )
    elif resolution in ("UNRESOLVED_CONFLICT", "INSUFFICIENT") and has_conflict:
        st.info(
            "ℹ️ **Balanced Directional Conflict**: "
            "Evidence exists in opposing directions with equal weight. "
            "System safely outputs INSUFFICIENT / UNCERTAIN rather than guessing a winner."
        )

    # Explanation and conflict sources
    if explanation:
        st.markdown(f"**Alignment Narrative:** {explanation}")

    if conflict_sources:
        with st.expander(f"⚠️ Documented Conflict Sources ({len(conflict_sources)})", expanded=False):
            for src in conflict_sources:
                st.markdown(f"- {src}")
