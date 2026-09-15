"""Target Information & Multi-Target Synthesis Panel for CYNTHERA frontend."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from typing import Any


def render_target_panel(result: Any, package: Any | None = None, expected_target: str | None = None) -> None:
    """Render the Target Trace and Multi-Target Synthesis panel.

    Displays:
    - Primary/ranked pipeline target
    - Expected target (if in benchmark context)
    - Target match verification badge
    - Multi-target ranking summary (retaining secondary target evidence)
    - Clarification that ranking denotes the preferred target for this run, not biological ground truth
    """
    st.markdown("### 🎯 Target Trace & Multi-Target Synthesis")

    # Extract targets from score_components or therapeutic alignment
    ma = getattr(result, "mechanistic_assessment", None)
    sc = getattr(ma, "score_components", {}) if ma else {}
    ta = getattr(result.audit_report, "therapeutic_alignment", {}) if getattr(result, "audit_report", None) else {}

    primary_target = sc.get("ranked_target")
    if not primary_target and ta:
        target_aligns = ta.get("target_alignments", [])
        if target_aligns:
            primary_target = target_aligns[0].get("target_id")

    # Clean target name for display
    display_primary = primary_target.replace("UNIPROT:", "") if primary_target else "N/A"
    display_expected = expected_target or "N/A"

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"**Pipeline Target (Ranked):** `{display_primary}`")
    with c2:
        st.markdown(f"**Expected Target:** `{display_expected}`")
    with c3:
        if expected_target and display_primary != "N/A":
            # Match check
            all_pipeline_tids = [t.get("target_id", "") for t in ta.get("target_alignments", [])]
            match = (
                display_primary.upper() == expected_target.upper()
                or any(expected_target.upper() in tid.upper() for tid in all_pipeline_tids)
            )
            if match:
                st.success("Target Match: YES")
            else:
                st.warning("Target Match: NO")
        else:
            st.info("Target Match: N/A")

    st.caption(
        "Note: 'Pipeline Target' represents the highest-ranked preferred target for this analysis "
        "based on explicit mechanism annotation and candidate support quality. It is not an absolute "
        "claim of biological ground truth."
    )

    # Multi-target ranking breakdown
    ranking_summary = sc.get("target_ranking_summary", [])
    if not ranking_summary and ta:
        target_aligns = ta.get("target_alignments", [])
        ranking_summary = [
            {
                "target_id": t.get("target_id", "N/A"),
                "rank_score": "—",
                "support_level": t.get("alignment", "N/A"),
                "confidence": t.get("confidence", 0.0),
                "candidate_count": len(t.get("evidence_groups", [])),
            }
            for t in target_aligns
        ]

    if ranking_summary:
        with st.expander(f"📋 All Pipeline Targets Evaluated ({len(ranking_summary)})", expanded=False):
            t_rows = []
            for item in ranking_summary:
                t_rows.append({
                    "Target ID": item.get("target_id", "N/A"),
                    "Rank Score": item.get("rank_score", "N/A"),
                    "Support Quality": item.get("support_level", "N/A"),
                    "Confidence": f"{item.get('confidence', 0.0):.3f}" if isinstance(item.get("confidence"), (int, float)) else "N/A",
                    "Candidate Paths": item.get("candidate_count", "N/A"),
                })
            st.dataframe(pd.DataFrame(t_rows), use_container_width=True, hide_index=True)
