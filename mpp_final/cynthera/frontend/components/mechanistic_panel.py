"""Mechanistic Evidence Panel component for CYNTHERA frontend."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from typing import Any


def render_mechanistic_panel(result: Any, package: Any | None = None) -> None:
    """Render the Mechanistic Evidence panel faithfully reflecting backend outputs.

    Displays:
    - Mechanistic Score (MS)
    - Confidence Level (HIGH, MEDIUM, LOW, NONE)
    - Mechanism Quality (WEAK_SPECULATIVE, MODERATELY_SUPPORTED, etc.)
    - Quality gate notice if structural connectivity alone does not pass Rule 1b
    - Transparent score_components table
    - Discovered candidate mechanisms and structural edge counts
    """
    st.markdown("### 🔗 Mechanistic Evidence")

    ma = getattr(result, "mechanistic_assessment", None)
    if ma is None:
        st.info("Mechanistic assessment data is not available.")
        return

    score = getattr(ma, "score", 0.0)
    level = getattr(ma, "level", "N/A")
    score_components = getattr(ma, "score_components", {}) or {}

    quality = score_components.get("support_level") or getattr(ma, "literature_grounding_level", "UNKNOWN")
    cand_count = score_components.get("candidate_count", len(getattr(ma, "candidate_mechanisms", [])))
    struct_edges = score_components.get("structural_edge_count", "N/A")
    indep_groups = score_components.get("independent_evidence_groups", "N/A")
    rxn_enriched = score_components.get("reaction_enriched", False)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Mechanistic Score", f"{score:.3f}" if isinstance(score, (int, float)) else "N/A")
    with col2:
        st.metric("Confidence", str(level))
    with col3:
        st.metric("Mechanism Quality", str(quality).replace("_", " "))

    # Phase 5.2 Quality Gate explanation
    if quality == "WEAK_SPECULATIVE" and isinstance(score, (int, float)) and score >= 0.40:
        st.info(
            "ℹ️ **Mechanistic Quality Gate Active**: Structural connectivity alone (WEAK_SPECULATIVE) "
            "is insufficient for a PROMISING recommendation. Mechanistic quality must meet the backend "
            "quality gate (MODERATELY_SUPPORTED or higher with causal validation)."
        )

    # Edge & Candidate summary metrics
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Candidate Paths", str(cand_count))
    with m2:
        st.metric("Structural Edges", str(struct_edges))
    with m3:
        st.metric("Independent Groups", str(indep_groups))
    with m4:
        st.metric("Reaction Enriched", "YES" if rxn_enriched else "NO")

    # Score components transparent display
    if score_components:
        with st.expander("🔬 Mechanistic Score Components Breakdown", expanded=False):
            rows = []
            for k, v in score_components.items():
                if k == "target_ranking_summary":
                    continue  # Displayed in target trace
                display_key = k.replace("_", " ").title()
                rows.append({"Component": display_key, "Value": str(v)})
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Primary mechanistic chain
    chain = getattr(ma, "mechanistic_chain", [])
    if chain:
        st.markdown("**Primary Mechanistic Chain:**")
        chain_html = " → ".join(
            f'<span style="background: #0f172a; border: 1px solid #334155; color: #e2e8f0; '
            f'padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.8rem; font-family: monospace;">{node}</span>'
            for node in chain
        )
        st.markdown(
            f'<div style="display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; '
            f'margin-bottom: 0.75rem; padding: 0.6rem; background: rgba(15,23,42,0.6); border-radius: 6px;">{chain_html}</div>',
            unsafe_allow_html=True,
        )
