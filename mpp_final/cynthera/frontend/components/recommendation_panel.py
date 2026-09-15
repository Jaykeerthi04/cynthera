"""Recommendation Decision Trace Panel component for CYNTHERA frontend."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from typing import Any


def render_recommendation_panel(result: Any, package: Any | None = None) -> None:
    """Render the Final Recommendation summary and rule-based decision trace.

    Faithfully displays the backend's multi-dimensional decision factors without
    recalculating or altering any backend rules.
    """
    st.markdown("### 🏆 Final Recommendation & Decision Trace")

    rec_status = getattr(result, "recommendation_status", None)
    rec_val = rec_status.value if hasattr(rec_status, "value") else str(rec_status)
    reasons = getattr(result, "recommendation_reasons", []) or []

    # Score extractions
    ms = getattr(result.mechanistic_assessment, "score", 0.0) if hasattr(result, "mechanistic_assessment") else 0.0
    sc = getattr(result.mechanistic_assessment, "score_components", {}) if hasattr(result, "mechanistic_assessment") else {}
    quality = sc.get("support_level") or (result.mechanistic_assessment.level if hasattr(result, "mechanistic_assessment") else "N/A")
    rs = getattr(result.risk_assessment, "score", 0.0) if hasattr(result, "risk_assessment") else 0.0
    ss = getattr(result.support_assessment, "score", 0.0) if hasattr(result, "support_assessment") else 0.0

    ta = getattr(result.audit_report, "therapeutic_alignment", {}) if getattr(result, "audit_report", None) else {}
    alignment = ta.get("overall_alignment", "INSUFFICIENT")

    cs = getattr(result, "contradiction_summary", None)
    contra_status = "DETECTED" if (cs and cs.has_conflict) else "NONE"

    # Recommendation Hero Banner
    badge_colors = {
        "PROMISING": ("#10b981", "rgba(16, 185, 129, 0.15)", "🟢 PROMISING — Proceed with Experimental Validation"),
        "UNCERTAIN": ("#f59e0b", "rgba(245, 158, 11, 0.15)", "🟡 UNCERTAIN — Mechanistic or Directional Validation Needed"),
        "NOT_RECOMMENDED": ("#ef4444", "rgba(239, 68, 68, 0.15)", "🔴 NOT RECOMMENDED — Safety Veto or Directional Opposition"),
    }
    col, bg, label = badge_colors.get(rec_val, ("#64748b", "rgba(100, 116, 139, 0.15)", rec_val))

    st.markdown(
        f"""
        <div style="text-align: center; padding: 1.25rem; border-radius: 12px; background: {bg}; border: 2px solid {col}; margin-bottom: 1.5rem;">
            <div style="font-size: 1.5rem; font-weight: 700; color: {col}; letter-spacing: 0.05em;">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Multi-dimensional summary table
    summary_rows = [
        {"Dimension": "Mechanistic Score (MS)", "Value": f"{ms:.3f}" if isinstance(ms, (int, float)) else "N/A"},
        {"Dimension": "Mechanism Quality", "Value": str(quality).replace("_", " ")},
        {"Dimension": "Therapeutic Alignment", "Value": str(alignment)},
        {"Dimension": "Support Score (SS)", "Value": f"{ss:.3f}" if isinstance(ss, (int, float)) else "N/A"},
        {"Dimension": "Risk Score (RS)", "Value": f"{rs:.3f}" if isinstance(rs, (int, float)) else "N/A"},
        {"Dimension": "Contradiction Status", "Value": contra_status},
        {"Dimension": "Final Decision", "Value": rec_val},
    ]
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    # Display Rule-based explanation trace
    if reasons:
        st.markdown("#### 📜 Decision Trace (Backend Rule Application)")
        for r_i, reason in enumerate(reasons):
            if "Rule 1b" in reason or "QUALITY GATE" in reason:
                st.warning(f"**Step {r_i+1}:** {reason}")
            elif "Rule 0" in reason or "Rule 2" in reason or "Rule 3" in reason:
                st.error(f"**Step {r_i+1}:** {reason}")
            elif "Rule 1" in reason:
                st.success(f"**Step {r_i+1}:** {reason}")
            else:
                st.info(f"**Step {r_i+1}:** {reason}")
