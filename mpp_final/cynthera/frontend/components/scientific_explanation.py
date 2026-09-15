"""Scientific Explanation and Epistemic Principles Panel for CYNTHERA frontend."""
from __future__ import annotations

import streamlit as st


def render_scientific_explanation() -> None:
    """Render the 'How CYNTHERA Reasons' scientific explanation panel."""
    st.markdown("### 🧬 How CYNTHERA Reasons")

    st.markdown("""
    CYNTHERA evaluates drug repurposing hypotheses through a multi-stage epistemic reasoning pipeline:
    """)

    st.markdown("""
    <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid #334155; border-radius: 10px; padding: 1.25rem; margin-bottom: 1.25rem;">
        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; justify-content: center; font-family: monospace; font-size: 0.85rem;">
            <span style="background: #1e293b; padding: 0.35rem 0.7rem; border-radius: 6px; border: 1px solid #3b82f6; color: #60a5fa;">💊 Drug</span>
            <span>→</span>
            <span style="background: #1e293b; padding: 0.35rem 0.7rem; border-radius: 6px; border: 1px solid #8b5cf6; color: #a78bfa;">🎯 Drug Targets</span>
            <span>→</span>
            <span style="background: #1e293b; padding: 0.35rem 0.7rem; border-radius: 6px; border: 1px solid #06b6d4; color: #22d3ee;">🔗 Mechanistic Evidence</span>
            <span>→</span>
            <span style="background: #1e293b; padding: 0.35rem 0.7rem; border-radius: 6px; border: 1px solid #10b981; color: #34d399;">🧭 Directional Alignment</span>
            <span>→</span>
            <span style="background: #1e293b; padding: 0.35rem 0.7rem; border-radius: 6px; border: 1px solid #f59e0b; color: #fbbf24;">📚 Independence Clustering</span>
            <span>→</span>
            <span style="background: #1e293b; padding: 0.35rem 0.7rem; border-radius: 6px; border: 1px solid #ef4444; color: #f87171;">⚡ Contradiction Analysis</span>
            <span>→</span>
            <span style="background: #1e293b; padding: 0.35rem 0.7rem; border-radius: 6px; border: 1px solid #ec4899; color: #f472b6;">⚖️ Multi-Target Synthesis</span>
            <span>→</span>
            <span style="background: #1e293b; padding: 0.35rem 0.7rem; border-radius: 6px; border: 1px solid #64748b; color: #94a3b8;">🛡️ Risk & Safety Veto</span>
            <span>→</span>
            <span style="background: #0f766e; padding: 0.35rem 0.7rem; border-radius: 6px; border: 1px solid #14b8a6; color: #ffffff; font-weight: 700;">🏆 Recommendation</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🔬 Core Epistemic Distinctions")
        st.markdown("""
        - **`UNKNOWN ≠ OPPOSING`**: Lack of directional evidence does not mean therapeutic opposition. Unknown states remain strictly non-directional (`INSUFFICIENT`).
        - **`STRUCTURAL ≠ CAUSAL`**: Pathway topology (e.g. Reactome `CATALYST`, `INPUT`, `OUTPUT`) provides necessary connectivity but carries zero directional weight until causally grounded.
        - **`DUPLICATE CITATIONS ≠ INDEPENDENT EVIDENCE`**: Multiple database entries citing the same underlying publication (PMID/DOI/NCT) are clustered into a single vote to prevent row-count inflation.
        - **`UNCERTAIN ≠ NEGATIVE`**: Incomplete or unresolved evidence is held in explicit uncertainty rather than forced into an artificial verdict.
        """)

    with c2:
        st.markdown("#### 🛡️ Scientific Guardrails")
        st.markdown("""
        - **Evidence Quality Over Quantity**: High raw candidate counts cannot overwhelm a verified curated target.
        - **Quality Gate (Rule 1b)**: Even if Mechanistic Score $\\ge 0.40$, candidates with `WEAK_SPECULATIVE` support are blocked from `PROMISING`.
        - **Contradiction Preservation**: Conflicting evidence is preserved as `UNRESOLVED_CONFLICT` rather than averaged away.
        - **Safety Veto Dominance**: Severe adverse events or clinical trial failures immediately veto mechanistic promise.
        """)
