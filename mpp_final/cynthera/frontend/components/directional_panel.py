"""Directional Mechanism Panel component for CYNTHERA frontend."""
from __future__ import annotations

import streamlit as st
from typing import Any


def render_directional_panel(result: Any, package: Any | None = None) -> None:
    """Render the Directional Mechanism panel reflecting Phase 5.3 multi-state consistency.

    Four explicit states:
    - UNKNOWN
    - PARTIAL
    - CONSISTENT
    - CONTRADICTORY
    """
    st.markdown("### 🧭 Directional Mechanism")

    # Safe extraction of directional mechanism status
    direction_status = "UNKNOWN"
    ma = getattr(result, "mechanistic_assessment", None)
    if ma:
        cands = getattr(ma, "candidate_mechanisms", [])
        if cands and isinstance(cands[0], dict):
            direction_status = cands[0].get("directional_mechanism_status", "UNKNOWN")
        score_comp = getattr(ma, "score_components", {}) or {}
        if "directional_mechanism_state" in score_comp:
            direction_status = score_comp["directional_mechanism_state"]

    direction_descriptions = {
        "UNKNOWN": "No reliable directional mechanism was established.",
        "PARTIAL": "Drug-target direction is known, but one or more intermediate mechanistic edges have unresolved polarity.",
        "CONSISTENT": "Available directional mechanism evidence is internally consistent.",
        "CONTRADICTORY": "Directional mechanism evidence contains conflicting causal directions.",
    }

    desc = direction_descriptions.get(direction_status, "Directional mechanism state not recorded.")

    # Status color badge
    status_colors = {
        "CONSISTENT": ("#10b981", "rgba(16, 185, 129, 0.12)"),
        "PARTIAL": ("#f59e0b", "rgba(245, 158, 11, 0.12)"),
        "CONTRADICTORY": ("#ef4444", "rgba(239, 68, 68, 0.12)"),
        "UNKNOWN": ("#64748b", "rgba(100, 116, 139, 0.12)"),
    }
    col, bg = status_colors.get(direction_status, ("#64748b", "rgba(100, 116, 139, 0.12)"))

    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Directional Mechanism", direction_status)
    with c2:
        st.markdown(
            f'<div style="padding: 1rem; border-radius: 8px; border: 1px solid {col}; background: {bg}; margin-top: 0.25rem;">'
            f'<div style="font-weight: 700; color: {col}; font-size: 0.95rem; margin-bottom: 0.25rem;">{direction_status}</div>'
            f'<div style="color: #cbd5e1; font-size: 0.85rem;">{desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
