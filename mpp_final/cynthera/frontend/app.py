"""CYNTHERA — Streamlit Frontend (Phase 2 & 3 Enhanced).

Phase 2 additions: Safety profile display, prior knowledge indicator,
                   mechanistic path visualization.
Phase 3 additions: API key configuration, bypass_cache option,
                   PDF download button, cache stats display.
"""
import asyncio
import sys
import os

from dotenv import load_dotenv

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

import streamlit as st
from backend.core.value_objects.source_url_builder import SourceURLBuilder
from frontend.components.mechanistic_panel import render_mechanistic_panel
from frontend.components.directional_panel import render_directional_panel
from frontend.components.contradiction_panel import render_contradiction_panel
from frontend.components.evidence_panel import render_evidence_panel
from frontend.components.target_panel import render_target_panel
from frontend.components.recommendation_panel import render_recommendation_panel
from frontend.components.scientific_explanation import render_scientific_explanation
from frontend.components.benchmark_panel import render_benchmark_panel
from frontend.components.ablation_panel import render_ablation_panel

st.set_page_config(
    page_title="CYNTHERA — Drug Repurposing AI",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# Custom CSS — Premium Dark Design
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

:root {
    --bg-primary: #0a0e1a;
    --bg-secondary: #111827;
    --bg-card: #1a2235;
    --border: #2a3a55;
    --accent-blue: #3b82f6;
    --accent-purple: #8b5cf6;
    --accent-cyan: #06b6d4;
    --accent-green: #10b981;
    --accent-amber: #f59e0b;
    --accent-red: #ef4444;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

.main {
    background-color: var(--bg-primary) !important;
    padding: 0 !important;
}

.block-container {
    padding: 2rem 3rem !important;
    max-width: 1400px !important;
}

/* Header */
.cynthera-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
    border: 1px solid rgba(139, 92, 246, 0.3);
    border-radius: 16px;
    padding: 2rem 3rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
}

.cynthera-header::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(ellipse at center, rgba(139, 92, 246, 0.08) 0%, transparent 70%);
    pointer-events: none;
}

.cynthera-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2.5rem;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6, #06b6d4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0;
    line-height: 1.2;
}

.cynthera-subtitle {
    color: var(--text-secondary);
    font-size: 1rem;
    margin-top: 0.5rem;
    font-weight: 400;
}

/* Score Cards */
.score-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    text-align: center;
    transition: all 0.2s ease;
    height: 100%;
}

.score-card:hover {
    border-color: var(--accent-blue);
    box-shadow: 0 0 20px rgba(59, 130, 246, 0.1);
}

.score-value {
    font-size: 2.5rem;
    font-weight: 700;
    font-family: 'Space Grotesk', sans-serif;
}

.score-label {
    font-size: 0.85rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top: 0.25rem;
}

.score-level {
    font-size: 0.75rem;
    font-weight: 600;
    margin-top: 0.5rem;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    display: inline-block;
}

/* Recommendation Badge */
.rec-badge {
    padding: 0.75rem 2rem;
    border-radius: 50px;
    font-size: 1.1rem;
    font-weight: 700;
    display: inline-block;
    letter-spacing: 0.05em;
    font-family: 'Space Grotesk', sans-serif;
}

.rec-promising {
    background: linear-gradient(135deg, #065f46, #10b981);
    border: 1px solid #10b981;
    color: white;
}

.rec-uncertain {
    background: linear-gradient(135deg, #78350f, #f59e0b);
    border: 1px solid #f59e0b;
    color: white;
}

.rec-not-recommended {
    background: linear-gradient(135deg, #7f1d1d, #ef4444);
    border: 1px solid #ef4444;
    color: white;
}

/* Panels */
.info-panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}

.info-panel-title {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 600;
    font-size: 1rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 1rem;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border) !important;
}

[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stTextInput label {
    color: var(--text-secondary) !important;
}

/* Streamlit widget overrides */
.stTextInput input, .stSelectbox select {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
    border-radius: 8px !important;
}

.stButton button {
    background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple)) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.5rem 2rem !important;
    transition: all 0.2s ease !important;
}

.stButton button:hover {
    opacity: 0.9 !important;
    transform: translateY(-1px) !important;
}

/* Dividers */
hr {
    border-color: var(--border) !important;
    margin: 1.5rem 0 !important;
}

/* Tables */
.stDataFrame {
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}

/* Progress bars */
.stProgress > div > div > div {
    background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple)) !important;
}

/* Expander */
.streamlit-expanderHeader {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
}

/* Alerts */
.stAlert {
    border-radius: 8px !important;
}

/* ─────────────────────────────────────────────
 * Phase 3 Reaction Layer & Node Chain Styles
 * ───────────────────────────────────────────── */
.node-chain-container {
    display: flex;
    flex-wrap: wrap;
    align-items: stretch;
    gap: 0.5rem;
    padding: 0.85rem;
    background: #0b1120;
    border: 1px solid #1e293b;
    border-radius: 10px;
    margin-bottom: 0.85rem;
}

.node-chip {
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 0.5rem 0.85rem;
    border-radius: 8px;
    background: #1e293b;
    border: 1px solid #334155;
    min-width: 130px;
    flex: 1;
}

.node-chip-drug {
    background: rgba(59, 130, 246, 0.12);
    border-color: rgba(59, 130, 246, 0.45);
}
.node-chip-target {
    background: rgba(139, 92, 246, 0.12);
    border-color: rgba(139, 92, 246, 0.45);
}
.node-chip-reaction {
    background: rgba(245, 158, 11, 0.14);
    border-color: rgba(245, 158, 11, 0.55);
}
.node-chip-pathway {
    background: rgba(6, 182, 212, 0.12);
    border-color: rgba(6, 182, 212, 0.45);
}
.node-chip-gene {
    background: rgba(16, 185, 129, 0.12);
    border-color: rgba(16, 185, 129, 0.45);
}
.node-chip-disease {
    background: rgba(244, 63, 94, 0.12);
    border-color: rgba(244, 63, 94, 0.45);
}

.node-header {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.15rem;
}

.node-title {
    font-size: 0.88rem;
    font-weight: 600;
    color: #f1f5f9;
    line-height: 1.25;
}

.node-sub {
    font-size: 0.72rem;
    color: #94a3b8;
    margin-top: 0.2rem;
    font-family: monospace;
}

.arrow-divider {
    color: #64748b;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 0 0.25rem;
    font-weight: 700;
}

.arrow-label {
    font-size: 0.65rem;
    color: #818cf8;
    font-weight: 600;
    margin-bottom: 0.1rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.role-badge {
    display: inline-block;
    padding: 0.2rem 0.55rem;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

.direction-badge {
    display: inline-block;
    padding: 0.2rem 0.55rem;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 600;
    border: 1px solid #334155;
    background: rgba(30, 41, 59, 0.6);
    color: #94a3b8;
}

.disclaimer-box {
    background: rgba(30, 41, 59, 0.35);
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-left: 3px solid #64748b;
    border-radius: 6px;
    padding: 0.65rem 0.9rem;
    color: #94a3b8;
    font-size: 0.8rem;
    line-height: 1.4;
    margin-bottom: 0.85rem;
}
</style>
""", unsafe_allow_html=True)


def render_header() -> None:
    """Render the CYNTHERA header banner."""
    st.markdown("""
    <div class="cynthera-header">
        <div class="cynthera-title">🧬 CYNTHERA</div>
        <div class="cynthera-subtitle">
            Contradiction-Aware Mechanistic Reasoning for Explainable Drug Repurposing
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_score_card(
    label: str,
    score: float,
    level: str,
    color: str,
    icon: str,
    degraded: bool = False,
) -> None:
    """Render a score card widget.

    Args:
        label: Card label (e.g., 'Support Score').
        score: Float score value [0.0, 1.0].
        level: Categorical level string.
        color: Hex color for the score value.
        icon: Emoji icon.
        degraded: If True, show a warning that this score is based on
            incomplete input due to retrieval failures. The score is
            still displayed -- it is not suppressed -- but the user is
            explicitly told it may not reflect the full evidence picture.
    """
    level_colors = {
        "HIGH": "#10b981", "MEDIUM": "#f59e0b",
        "LOW": "#ef4444", "NONE": "#64748b",
    }
    badge_color = level_colors.get(level.upper(), "#64748b")
    degraded_html = (
        '<div style="margin-top: 0.5rem; font-size: 0.7rem; color: #f59e0b; '
        'border: 1px solid #f59e0b44; background: #f59e0b11; padding: 0.2rem 0.4rem; '
        'border-radius: 4px; text-align: center;">'
        '⚠ DATA DEGRADED — retrieval failures above</div>'
    ) if degraded else ""
    st.markdown(f"""
    <div class="score-card">
        <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">{icon}</div>
        <div class="score-value" style="color: {color};">{score:.3f}</div>
        <div class="score-label">{label}</div>
        <div class="score-level" style="background: {badge_color}22; color: {badge_color}; border: 1px solid {badge_color}55;">
            {level}
        </div>
        {degraded_html}
    </div>
    """, unsafe_allow_html=True)


def render_recommendation_badge(status: str) -> None:
    """Render the recommendation status badge.

    Args:
        status: 'PROMISING', 'UNCERTAIN', or 'NOT_RECOMMENDED'.
    """
    config = {
        "PROMISING": ("🟢", "rec-promising", "PROMISING — Proceed with Validation"),
        "UNCERTAIN": ("🟡", "rec-uncertain", "UNCERTAIN — Additional Evidence Needed"),
        "NOT_RECOMMENDED": ("🔴", "rec-not-recommended", "NOT RECOMMENDED"),
    }
    icon, css_class, label = config.get(status, ("⚪", "rec-uncertain", status))
    st.markdown(f"""
    <div style="text-align: center; padding: 1.5rem 0;">
        <div class="rec-badge {css_class}">
            {icon} &nbsp; {label}
        </div>
    </div>
    """, unsafe_allow_html=True)


_ROLE_CONFIG = {
    "CATALYST": ("#f59e0b", "rgba(245, 158, 11, 0.15)", "#fbbf24"),
    "INPUT": ("#3b82f6", "rgba(59, 130, 246, 0.15)", "#60a5fa"),
    "OUTPUT": ("#10b981", "rgba(16, 185, 129, 0.15)", "#34d399"),
    "COMPLEX_COMPONENT": ("#8b5cf6", "rgba(139, 92, 246, 0.15)", "#a78bfa"),
    "ENTITY_SET_MEMBER": ("#ec4899", "rgba(236, 72, 153, 0.15)", "#f472b6"),
    "POSITIVE_REGULATOR": ("#10b981", "rgba(16, 185, 129, 0.15)", "#34d399"),
    "NEGATIVE_REGULATOR": ("#ef4444", "rgba(239, 68, 68, 0.15)", "#f87171"),
    "REQUIREMENT": ("#06b6d4", "rgba(6, 182, 212, 0.15)", "#22d3ee"),
    "PARTICIPANT": ("#64748b", "rgba(100, 116, 139, 0.15)", "#94a3b8"),
    "UNKNOWN": ("#64748b", "rgba(100, 116, 139, 0.15)", "#94a3b8"),
}


def get_role_badge_html(role_str: str) -> str:
    clean_role = role_str.upper().replace(" ", "_") if role_str else "UNKNOWN"
    color, bg, border = _ROLE_CONFIG.get(clean_role, ("#64748b", "rgba(100, 116, 139, 0.15)", "#94a3b8"))
    display_label = clean_role.replace("_", " ")
    return f'<span class="role-badge" style="color: {color}; background: {bg}; border: 1px solid {border};">{display_label}</span>'


def get_direction_badge_html(direction_str: str) -> str:
    d = (direction_str or "UNKNOWN").upper()
    if d == "POSITIVE":
        return '<span class="direction-badge" style="color: #10b981; border-color: #10b98155; background: rgba(16,185,129,0.12);" title="Curated positive regulation (activation/stimulation)">Direction: POSITIVE</span>'
    elif d == "NEGATIVE":
        return '<span class="direction-badge" style="color: #ef4444; border-color: #ef444455; background: rgba(239,68,68,0.12);" title="Curated negative regulation (inhibition/repression)">Direction: NEGATIVE</span>'
    else:
        return '<span class="direction-badge" style="color: #94a3b8; border-color: #334155; background: rgba(30,41,59,0.6);" title="No explicit regulatory polarity established">Direction: UNKNOWN</span>'



# ─────────────────────────────────────────────
# Session State Initialization
# ─────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None
if "history" not in st.session_state:
    st.session_state.history = []
if "current_tab" not in st.session_state:
    st.session_state.current_tab = "evaluate"

# ─────────────────────────────────────────────
# Sidebar Navigation
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🧬 CYNTHERA")
    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["🔬 Evaluate", "📊 Results", "📋 Audit Report", "🧪 Evaluation & Benchmark", "🕐 History", "⚡ Batch"],
        index=0,
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.markdown("**Configuration**")
    policy = st.selectbox(
        "Retrieval Policy",
        ["STANDARD", "FAST", "COMPREHENSIVE"],
        help="Controls depth and scope of data retrieval",
    )
    bypass_cache = st.checkbox(
        "Bypass Cache",
        value=False,
        help="Force a fresh evaluation, ignoring any cached results",
    )
    st.markdown("---")
    st.markdown(
        "<small style='color: #64748b;'>CYNTHERA v2.0 | Rule Set v2.0</small>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────
# Render Header
# ─────────────────────────────────────────────
render_header()

# ─────────────────────────────────────────────
# Page: Evaluate
# ─────────────────────────────────────────────
if page == "🔬 Evaluate":
    st.markdown("## Hypothesis Evaluation")
    st.markdown(
        "<p style='color: #94a3b8;'>Enter a drug-disease pair to evaluate repurposing potential using multi-source biomedical evidence.</p>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        drug_name = st.text_input(
            "💊 Drug Name",
            placeholder="e.g., Sildenafil, Metformin, Aspirin",
            help="Enter the common name of the drug to evaluate",
        )
    with col2:
        disease_name = st.text_input(
            "🏥 Disease Name",
            placeholder="e.g., Pulmonary Arterial Hypertension, Type 2 Diabetes",
            help="Enter the disease name to evaluate as the target indication",
        )

    col_btn, col_ex = st.columns([1, 3])
    with col_btn:
        run_button = st.button("🚀 Run Evaluation", use_container_width=True)
    with col_ex:
        st.markdown(
            "<div style='padding: 0.6rem 0; color: #64748b; font-size: 0.9rem;'>"
            "⚡ Try: <b>Sildenafil</b> → <b>Pulmonary Arterial Hypertension</b>"
            "</div>",
            unsafe_allow_html=True,
        )

    if run_button:
        if not drug_name or not disease_name:
            st.error("⚠️ Please enter both a drug name and a disease name.")
        else:
            with st.spinner(f"🔬 Evaluating **{drug_name}** → **{disease_name}**..."):
                try:
                    # Import and run the evaluation
                    from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
                    from backend.core.enums.retrieval_policy import RetrievalPolicy

                    policy_map = {
                        "STANDARD": RetrievalPolicy.STANDARD,
                        "FAST": RetrievalPolicy.FAST,
                        "COMPREHENSIVE": RetrievalPolicy.COMPREHENSIVE,
                    }

                    orchestrator = MasterOrchestrator(
                        llm_api_key=os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
                        ncbi_api_key=os.environ.get("NCBI_API_KEY"),
                        disgenet_api_key=os.environ.get("DISGENET_API_KEY"),
                    )

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    hypothesis, pkg, result = loop.run_until_complete(
                        orchestrator.evaluate(
                            drug_name,
                            disease_name,
                            policy=policy_map.get(policy, RetrievalPolicy.STANDARD),
                            bypass_cache=bypass_cache,
                        )
                    )
                    loop.close()

                    st.session_state.results = {
                        "drug": drug_name,
                        "disease": disease_name,
                        "hypothesis": hypothesis,
                        "package": pkg,
                        "result": result,
                    }
                    st.session_state.history.append({
                        "drug": drug_name,
                        "disease": disease_name,
                        "recommendation": result.recommendation_status.value,
                        "ss": result.support_assessment.score,
                        "ms": result.mechanistic_assessment.score,
                        "rs": result.risk_assessment.score,
                    })
                    st.success("✅ Evaluation complete! Navigate to **Results** to view the full report.")
                    st.rerun()

                except Exception as exc:
                    st.error(f"❌ Evaluation failed: {exc}")
                    st.exception(exc)

    # Example cards
    st.markdown("---")
    st.markdown("### 💡 Example Queries")
    ex_cols = st.columns(3)
    examples = [
        ("Sildenafil", "Pulmonary Arterial Hypertension", "Known repurposing success (PAH)"),
        ("Metformin", "Type 2 Diabetes", "Well-established primary indication"),
        ("Aspirin", "Pancreatic Cancer", "Negative control — not recommended"),
    ]
    for i, (drug, disease, desc) in enumerate(examples):
        with ex_cols[i]:
            st.markdown(f"""
            <div class="info-panel" style="cursor: pointer;">
                <div style="font-weight: 600; margin-bottom: 0.25rem;">{drug}</div>
                <div style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 0.5rem;">→ {disease}</div>
                <div style="color: #64748b; font-size: 0.75rem;">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Page: Results
# ─────────────────────────────────────────────
elif page == "📊 Results":
    if not st.session_state.results:
        st.info("No evaluation results yet. Go to **🔬 Evaluate** to run an analysis.")
    else:
        r = st.session_state.results
        result = r["result"]
        pkg = r["package"]

        st.markdown(f"## Results: {r['drug']} → {r['disease']}")

        # ── Visual Hierarchy per Phase 5.8 Specification ──
        # 1. Final Recommendation Banner & Decision Trace
        render_recommendation_panel(result, pkg)
        st.markdown("---")

        # 2. Mechanistic Evidence Panel (Exposes MS, Quality, score_components, quality gate notice)
        render_mechanistic_panel(result, pkg)
        st.markdown("---")

        # 3. Directional Mechanism Panel (Phase 5.3 four states)
        render_directional_panel(result, pkg)
        st.markdown("---")

        # 4. Contradiction & Uncertainty Panel (Phase 5.6)
        render_contradiction_panel(result, pkg)
        st.markdown("---")

        # 5. Target Trace Panel (Ranked target, expected target, match, all targets list)
        render_target_panel(result, pkg)
        st.markdown("---")

        # 6. Evidence & Frozen Weighting Metadata Panel (CONFIG_A, family breakdown)
        render_evidence_panel(result, pkg)
        st.markdown("---")

        # 7. Scientific Explanation Panel (How CYNTHERA reasons, core epistemic distinctions)
        render_scientific_explanation()
        st.markdown("---")

        # Evidence summary with Phase 3 Reaction Metrics
        rxn_evidence = getattr(pkg, "reactome_reaction_evidence", []) or []
        unique_rxn_ids = set(r.reaction_id for r in rxn_evidence if hasattr(r, "reaction_id"))
        cands = getattr(result.audit_report, "candidate_mechanisms", []) or getattr(result.mechanistic_assessment, "candidate_mechanisms", []) or []
        
        # Count reaction-enriched candidate mechanisms
        enriched_cand_count = sum(
            1 for c in cands if any(
                "REACTION" in str(h.get("from_node", "")).upper() or "REACTION" in str(h.get("to_node", "")).upper()
                for h in c.get("hops", [])
            )
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("### 📊 Evidence & Pathway Summary")
            st.markdown(f"""
            <div class="info-panel">
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem;">
                    <div><div style="font-size: 1.6rem; font-weight: 700; color: #3b82f6;">{len(cands) or (1 if result.mechanistic_assessment.mechanistic_chain else 0)}</div><div style="color: #94a3b8; font-size: 0.75rem;">Mechanistic Paths</div></div>
                    <div><div style="font-size: 1.6rem; font-weight: 700; color: #f59e0b;">{enriched_cand_count}</div><div style="color: #94a3b8; font-size: 0.75rem;">Reaction-Enriched</div></div>
                    <div><div style="font-size: 1.6rem; font-weight: 700; color: #10b981;">{len(unique_rxn_ids)}</div><div style="color: #94a3b8; font-size: 0.75rem;">Reactome Reactions</div></div>
                    <div><div style="font-size: 1.6rem; font-weight: 700; color: #8b5cf6;">{len(pkg.targets)}</div><div style="color: #94a3b8; font-size: 0.75rem;">Drug Targets</div></div>
                    <div><div style="font-size: 1.6rem; font-weight: 700; color: #06b6d4;">{len(pkg.pathways)}</div><div style="color: #94a3b8; font-size: 0.75rem;">Reactome Pathways</div></div>
                    <div><div style="font-size: 1.6rem; font-weight: 700; color: #ec4899;">{len(pkg.evidence_records)}</div><div style="color: #94a3b8; font-size: 0.75rem;">Evidence Records</div></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        with col_b:
            st.markdown("### 🌐 Data Sources")
            st.markdown(f"""
            <div class="info-panel">
                <div style="margin-bottom: 0.5rem;"><span style="color: #10b981;">✓</span> <b>Queried:</b> {', '.join(pkg.sources_queried) or 'None'}</div>
                <div><span style="color: #ef4444;">✗</span> <b>Failed:</b> {', '.join(pkg.sources_failed) or 'None'}</div>
                <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #2a3a55;">
                    <b>Retrieval Confidence:</b>
                    <span style="color: {'#10b981' if pkg.retrieval_confidence == 'HIGH' else '#f59e0b' if pkg.retrieval_confidence == 'MEDIUM' else '#ef4444'};">
                        {pkg.retrieval_confidence}
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Candidate Biological Mechanisms Discovery Display (Phase 3 Enriched) ──
        if cands:
            st.markdown("### 🧬 Candidate Biological Mechanisms Discovered")
            
            for cand in cands[:5]:
                c_idx = cand.get("candidate_index", 1)
                c_name = cand.get("name", f"Mechanism {c_idx}")
                c_level = cand.get("support_level", "MODERATELY_SUPPORTED")
                c_conf = cand.get("confidence_score", 0.5)
                c_chain = cand.get("summary_chain", [])
                c_status = cand.get("discovery_status", "CANDIDATE_STRUCTURAL")
                hops = cand.get("hops", [])

                has_reaction_hop = any(
                    "REACTION" in str(h.get("from_node", "")).upper() or "REACTION" in str(h.get("to_node", "")).upper()
                    for h in hops
                ) or any("REACTION" in str(node).upper() for node in c_chain)

                c_dir_status = cand.get("directional_mechanism_status", "UNKNOWN")
                dir_badge_color = "#10b981" if c_dir_status == "CONSISTENT" else ("#ef4444" if c_dir_status == "CONTRADICTORY" else ("#f59e0b" if c_dir_status == "PARTIAL" else "#64748b"))
                dir_badge_bg = "rgba(16,185,129,0.12)" if c_dir_status == "CONSISTENT" else ("rgba(239,68,68,0.12)" if c_dir_status == "CONTRADICTORY" else ("rgba(245,158,11,0.12)" if c_dir_status == "PARTIAL" else "rgba(100,116,139,0.12)"))
                dir_badge_html = f'<span style="background: {dir_badge_bg}; border: 1px solid {dir_badge_color}; color: {dir_badge_color}; padding: 0.15rem 0.5rem; border-radius: 4px; font-weight: 700; font-size: 0.72rem; margin-right: 0.5rem;">DIRECTION: {c_dir_status}</span>'

                badge_color = "#10b981" if "STRONGLY" in c_level else ("#f59e0b" if "MODERATELY" in c_level else "#ef4444")
                badge_bg = "rgba(16,185,129,0.12)" if "STRONGLY" in c_level else ("rgba(245,158,11,0.12)" if "MODERATELY" in c_level else "rgba(239,68,68,0.12)")
                path_type_badge = (
                    '<span style="background: rgba(245,158,11,0.18); border: 1px solid #f59e0b; color: #fbbf24; padding: 0.15rem 0.5rem; border-radius: 4px; font-weight: 700; font-size: 0.72rem; margin-right: 0.5rem;">⚡ 5-HOP REACTION-ENRICHED</span>'
                    if has_reaction_hop else
                    '<span style="background: rgba(59,130,246,0.15); border: 1px solid #3b82f6; color: #60a5fa; padding: 0.15rem 0.5rem; border-radius: 4px; font-weight: 700; font-size: 0.72rem; margin-right: 0.5rem;">🔬 4-HOP DIRECT PATHWAY</span>'
                )

                st.markdown(f"""
                <div class="info-panel" style="border-left: 4px solid {badge_color}; margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            {path_type_badge}
                            {dir_badge_html}
                            <span style="font-weight: 700; font-size: 1.05rem; color: #f8fafc;">{c_name}</span>
                        </div>
                        <div style="background: {badge_bg}; border: 1px solid {badge_color}; color: {badge_color}; padding: 0.2rem 0.6rem; border-radius: 6px; font-weight: 700; font-size: 0.8rem;">
                            {c_level.replace('_', ' ')} ({c_conf:.1%})
                        </div>
                    </div>
                    <div style="color: #94a3b8; margin-top: 0.35rem; font-size: 0.82rem;">Discovery Status: {c_status.replace('_', ' ')}</div>
                </div>
                """, unsafe_allow_html=True)


                # Render structured multi-node visual chain (Drug → Target → Reaction → Pathway → Gene → Disease)
                if hops:
                    chain_chips_html = []
                    for h_i, h in enumerate(hops):
                        from_raw = h.get("from_node", "")
                        to_raw = h.get("to_node", "")
                        pred = h.get("predicate", "MODULATES")

                        # Parse from_node on the very first hop
                        if h_i == 0:
                            f_label, _, f_val = from_raw.partition(":")
                            f_lbl_clean = f_label.strip().upper()
                            chip_cls = "node-chip-drug" if "DRUG" in f_lbl_clean else "node-chip-target"
                            f_header_col = "#60a5fa" if "DRUG" in f_lbl_clean else "#a78bfa"
                            chain_chips_html.append(f"""
                            <div class="node-chip {chip_cls}">
                                <div class="node-header" style="color: {f_header_col};">{f_label.strip()}</div>
                                <div class="node-title">{f_val.strip() or f_label.strip()}</div>
                            </div>
                            """)

                        # Divider arrow
                        chain_chips_html.append(f"""
                        <div class="arrow-divider">
                            <span class="arrow-label">{pred.replace('_', ' ')}</span>
                            <span>↓</span>
                        </div>
                        """)

                        # Parse to_node
                        t_label, _, t_val = to_raw.partition(":")
                        t_lbl_clean = t_label.strip().upper()
                        if "TARGET" in t_lbl_clean or "PROTEIN" in t_lbl_clean:
                            chip_cls = "node-chip-target"
                            t_header_col = "#a78bfa"
                            sub_text = f"UniProt: {h.get('canonical_to_id')}" if h.get('canonical_to_id') else ""
                        elif "REACTION" in t_lbl_clean:
                            chip_cls = "node-chip-reaction"
                            t_header_col = "#fbbf24"
                            sub_text = "Reactome Curated Event"
                        elif "PATHWAY" in t_lbl_clean:
                            chip_cls = "node-chip-pathway"
                            t_header_col = "#22d3ee"
                            sub_text = "Reactome Pathway"
                        elif "GENE" in t_lbl_clean:
                            chip_cls = "node-chip-gene"
                            t_header_col = "#34d399"
                            sub_text = "Disease-Associated Gene"
                        elif "DISEASE" in t_lbl_clean:
                            chip_cls = "node-chip-disease"
                            t_header_col = "#f43f5e"
                            sub_text = "Indication"
                        else:
                            chip_cls = "node-chip"
                            t_header_col = "#94a3b8"
                            sub_text = ""

                        sub_html = f'<div class="node-sub">{sub_text}</div>' if sub_text else ""
                        chain_chips_html.append(f"""
                        <div class="node-chip {chip_cls}">
                            <div class="node-header" style="color: {t_header_col};">{t_label.strip()}</div>
                            <div class="node-title">{t_val.strip() or t_label.strip()}</div>
                            {sub_html}
                        </div>
                        """)

                    st.markdown(f'<div class="node-chain-container">{"".join(chain_chips_html)}</div>', unsafe_allow_html=True)
                elif c_chain:
                    chain_html = " → ".join(
                        f'<span style="background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 0.25rem 0.6rem; border-radius: 4px; font-size: 0.85rem; font-family: monospace;">{node}</span>'
                        for node in c_chain
                    )
                    st.markdown(
                        f'<div style="display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin-bottom: 0.75rem; padding: 0.5rem; background: rgba(15,23,42,0.6); border-radius: 6px;">{chain_html}</div>',
                        unsafe_allow_html=True,
                    )

                # Hop-level evidence expander
                if hops:
                    with st.expander(f"🔬 Candidate Mechanism {c_idx} — Step-by-Step Biological Evidence & Links"):
                        for h in hops:
                            h_from = h.get("from_node", "")
                            h_to = h.get("to_node", "")
                            h_pred = h.get("predicate", "MODULATES")
                            h_src = h.get("source_database", "")
                            h_links = h.get("links", [])
                            h_status = h.get("status", "CANDIDATE_STRUCTURAL")
                            h_direction = h.get("directionality", "DIRECTION_UNCERTAIN")

                            link_buttons = []
                            for l in h_links:
                                u = l.get("url")
                                lbl = l.get("display_label", l.get("source_name", "Open"))
                                if u:
                                    link_buttons.append(f'<a href="{u}" target="_blank" style="background: #1e293b; border: 1px solid #3b82f6; color: #60a5fa; text-decoration: none; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600;">{lbl} ↗</a>')
                            button_html = " ".join(link_buttons) if link_buttons else f'<span style="color: #64748b; font-size: 0.75rem;">[{h_src}]</span>'

                            st.markdown(f"""
                            <div style="background: #111827; border: 1px solid #1f2937; padding: 0.5rem 0.75rem; border-radius: 6px; margin-bottom: 0.4rem; display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <span style="color: #cbd5e1; font-weight: 600;">{h_from}</span> 
                                    <span style="color: #818cf8; font-weight: 700; font-size: 0.85rem;"> —{h_pred}→ </span> 
                                    <span style="color: #cbd5e1; font-weight: 600;">{h_to}</span>
                                </div>
                                <div style="display: flex; gap: 0.3rem;">{button_html}</div>
                            </div>
                            """, unsafe_allow_html=True)
                            st.caption(f"Status: {h_status.replace('_', ' ')} | Directionality: {h_direction.replace('_', ' ')} | Source: {h_src}")
                            for citation in h.get("supporting_claims", []):
                                url = citation.get("url")
                                label = citation.get("citation_key") or citation.get("source", "literature")
                                st.markdown(f"Supporting claim ({citation.get('source', 'literature')}): [{label}]({url})" if url else f"Supporting claim: {label}")
                            for citation in h.get("contradicting_claims", []):
                                url = citation.get("url")
                                label = citation.get("citation_key") or citation.get("source", "literature")
                                st.warning(f"Contradicting claim ({citation.get('source', 'literature')}): {label}" + (f" — {url}" if url else ""))
                        for explanation in cand.get("score_explanation", []):
                            st.caption(explanation)
                        for gap in cand.get("missing_critical_evidence", []):
                            st.info(f"Missing evidence: {gap}")
        elif result.mechanistic_assessment.mechanistic_chain:
            st.markdown("### 🔗 Mechanistic Chain")
            chain = result.mechanistic_assessment.mechanistic_chain
            chain_html = " → ".join(
                f'<span style="background: #1a2235; border: 1px solid #2a3a55; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.85rem;">{node}</span>'
                for node in chain
            )
            st.markdown(
                f'<div class="info-panel"><div style="display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;">{chain_html}</div></div>',
                unsafe_allow_html=True,
            )

        # ── Dedicated Reactome Reaction & Event Evidence Cards (Phase 3) ──
        if rxn_evidence:
            st.markdown("---")
            st.markdown("### ⚡ Reactome Reaction & Molecular Event Evidence")
            st.markdown("""
            <div class="disclaimer-box">
                ℹ️ <b>Biological Role Context:</b> Reactome reaction evidence describes the target's specific molecular role within the reaction/event.
                It establishes molecular participation without converting catalyst/structural roles into unsupported therapeutic activation or inhibition claims.
            </div>
            """, unsafe_allow_html=True)

            # Filtering if multiple reactions exist
            roles_present = sorted(list(set(
                (r.target_role.value if hasattr(r.target_role, "value") else str(r.target_role)).upper()
                for r in rxn_evidence
            )))
            filter_col1, filter_col2 = st.columns([2, 2])
            with filter_col1:
                selected_role_filter = st.selectbox(
                    "Filter by Target Role",
                    ["ALL ROLES"] + roles_present,
                    index=0,
                    key="rxn_role_filter",
                )
            with filter_col2:
                selected_dir_filter = st.selectbox(
                    "Filter by Direction",
                    ["ALL DIRECTIONS", "UNKNOWN", "POSITIVE", "NEGATIVE"],
                    index=0,
                    key="rxn_dir_filter",
                )

            filtered_ev = rxn_evidence
            if selected_role_filter != "ALL ROLES":
                filtered_ev = [
                    r for r in filtered_ev
                    if (r.target_role.value if hasattr(r.target_role, "value") else str(r.target_role)).upper() == selected_role_filter
                ]
            if selected_dir_filter != "ALL DIRECTIONS":
                filtered_ev = [
                    r for r in filtered_ev
                    if (getattr(r, "direction", "UNKNOWN") or "UNKNOWN").upper() == selected_dir_filter
                ]

            st.caption(f"Showing {len(filtered_ev)} of {len(rxn_evidence)} Reactome reaction evidence records")

            # Group evidence by target symbol / reaction
            for ev_i, ev in enumerate(filtered_ev):
                role_val = ev.target_role.value if hasattr(ev.target_role, "value") else str(ev.target_role)
                dir_val = getattr(ev, "direction", "UNKNOWN") or "UNKNOWN"
                rxn_name = ev.reaction_name or "Reaction Event"
                rxn_id = ev.reaction_id or "R-HSA-UNKNOWN"
                pw_name = ev.pathway_name or "Reactome Pathway"
                pw_id = ev.pathway_id or ""
                target_sym = getattr(ev, "target_canonical_id", None) or getattr(ev, "target_symbol", "Target")
                uniprot_acc = getattr(ev, "target_original_id", None) or getattr(ev, "target_uniprot", "")

                role_badge_html = get_role_badge_html(role_val)
                dir_badge_html = get_direction_badge_html(dir_val)
                rxn_url = f"https://reactome.org/content/detail/{rxn_id}"
                pw_url = f"https://reactome.org/content/detail/{pw_id}" if pw_id else "#"

                st.markdown(f"""
                <div style="background: #111827; border: 1px solid #1f2937; border-left: 4px solid #f59e0b; border-radius: 8px; padding: 0.85rem 1.1rem; margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.4rem;">
                        <div>
                            <span style="font-size: 0.72rem; font-weight: 700; color: #fbbf24; text-transform: uppercase; letter-spacing: 0.06em;">⚡ REACTOME REACTION</span>
                            <div style="font-size: 1.05rem; font-weight: 700; color: #f8fafc; margin-top: 0.15rem;">
                                {rxn_name}
                            </div>
                        </div>
                        <div style="display: flex; gap: 0.4rem; align-items: center;">
                            {role_badge_html}
                            {dir_badge_html}
                        </div>
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 1.2rem; font-size: 0.82rem; color: #94a3b8; margin-top: 0.4rem; padding-top: 0.4rem; border-top: 1px solid #1e293b;">
                        <div><b>Target:</b> <span style="color: #cbd5e1;">{target_sym}</span> <span style="color: #64748b; font-family: monospace;">({uniprot_acc})</span></div>
                        <div><b>Reactome ID:</b> <a href="{rxn_url}" target="_blank" style="color: #60a5fa; text-decoration: none; font-family: monospace;">{rxn_id} ↗</a></div>
                        <div><b>Containing Pathway:</b> <a href="{pw_url}" target="_blank" style="color: #22d3ee; text-decoration: none;">{pw_name} ({pw_id}) ↗</a></div>
                        <div><b>Evidence Source:</b> <span style="color: #10b981;">Reactome · Curated Reaction</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                with st.expander(f"📋 View Full Reaction & Provenance Details — {rxn_id}"):
                    d_col1, d_col2 = st.columns(2)
                    with d_col1:
                        st.markdown(f"**Target Canonical Symbol:** `{target_sym}`")
                        st.markdown(f"**Target UniProt Accession:** `{uniprot_acc}`")
                        st.markdown(f"**Reactome Reaction StId:** [`{rxn_id}`]({rxn_url})")
                        st.markdown(f"**Schema Class:** `{getattr(ev, 'schema_class', 'Reaction')}`")
                        st.markdown(f"**Target Role:** `{role_val}`")
                        st.markdown(f"**Directionality:** `{dir_val}` (No causal polarity assumed)")
                    with d_col2:
                        st.markdown(f"**Pathway ID:** [`{pw_id}`]({pw_url})")
                        st.markdown(f"**Pathway Name:** {pw_name}")
                        st.markdown(f"**Mapping Type:** `{getattr(ev, 'mapping_type', 'DIRECT_PATHWAY_MAPPING')}`")
                        st.markdown(f"**Species:** `{getattr(ev, 'species', 'Homo sapiens')}`")
                        cmps = getattr(ev, "compartment", []) or []
                        st.markdown(f"**Compartment:** {', '.join(cmps) if cmps else 'Unspecified'}")
                        dis_ctx = getattr(ev, "disease_context", None)
                        st.markdown(f"**Disease Context:** {dis_ctx or 'Normal Physiology'}")

                    prov = getattr(ev, "provenance", {}) or {}
                    if prov:
                        st.caption(f"Provenance Source: {prov.get('source', 'reactome')} | Retrieved: {prov.get('retrieved_at', 'Session')}")
        elif result.mechanistic_assessment.mechanistic_chain:
            st.markdown("### 🔗 Mechanistic Chain")
            chain = result.mechanistic_assessment.mechanistic_chain
            chain_html = " → ".join(
                f'<span style="background: #1a2235; border: 1px solid #2a3a55; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.85rem;">{node}</span>'
                for node in chain
            )
            st.markdown(
                f'<div class="info-panel"><div style="display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;">{chain_html}</div></div>',
                unsafe_allow_html=True,
            )

        # Contradictions
        if result.contradictions:
            st.markdown("### ⚔️ Contradictions Detected")
            for c in result.contradictions[:5]:
                st.markdown(f"""
                <div class="info-panel" style="border-left: 3px solid #ef4444;">
                    <div style="font-weight: 600; color: #ef4444;">Score: {c.contradiction_score:.3f}</div>
                    <div style="color: #94a3b8; margin-top: 0.25rem;">{c.explanation}</div>
                </div>
                """, unsafe_allow_html=True)

        # ── Phase 2: Safety Profile Display ──────────────────────────
        result_obj = r["result"]
        audit = result_obj.audit_report
        safety_grade_in_summary = ""
        for marker in ["Safety grade: A", "Safety grade: B", "Safety grade: C", "Safety grade: D"]:
            if marker in audit.summary:
                safety_grade_in_summary = marker.split(": ")[1]
                break

        if safety_grade_in_summary:
            st.markdown("### 🛡️ Clinical Safety Profile")
            grade = safety_grade_in_summary
            grade_color = {"A": "#10b981", "B": "#3b82f6", "C": "#f59e0b", "D": "#ef4444"}.get(grade, "#64748b")
            grade_desc = {
                "A": "Strong clean safety record",
                "B": "Acceptable safety profile",
                "C": "Moderate concerns — monitoring recommended",
                "D": "Significant safety concerns",
            }.get(grade, "Unknown")
            st.markdown(f"""
            <div class="info-panel" style="border-left: 4px solid {grade_color};">
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <div style="font-size: 2rem; font-weight: 700; color: {grade_color}; font-family: 'Space Grotesk', sans-serif;">Grade {grade}</div>
                    <div>
                        <div style="font-weight: 600; color: {grade_color};">{grade_desc}</div>
                        <div style="color: #94a3b8; font-size: 0.85rem; margin-top: 0.25rem;">Safety grade from ClinicalSafetyAgent analysis</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Scientific Context Banner (dimensional prior knowledge) ──────────
        audit = result.audit_report
        ct_status = getattr(audit, "clinical_trial_status", "NOT_ATTEMPTED")
        scientific_context = getattr(audit, "scientific_context", {}) or {}

        _STATUS_STYLE = {
            "APPROVED": ("✅", "#10b981", "rgba(16,185,129,0.12)"),
            "INVESTIGATIONAL": ("🧪", "#3b82f6", "rgba(59,130,246,0.12)"),
            "ESTABLISHED": ("✅", "#10b981", "rgba(16,185,129,0.12)"),
            "EMERGING": ("🟡", "#f59e0b", "rgba(245,158,11,0.12)"),
            "STRONG": ("🟢", "#10b981", "rgba(16,185,129,0.12)"),
            "MODERATE": ("🟡", "#f59e0b", "rgba(245,158,11,0.12)"),
            "HUMAN_EVIDENCE": ("🧬", "#3b82f6", "rgba(59,130,246,0.12)"),
            "ANIMAL_ONLY": ("🐁", "#8b5cf6", "rgba(139,92,246,0.12)"),
            "GROWING": ("🌱", "#3b82f6", "rgba(59,130,246,0.12)"),
        }
        _DIMENSION_LABELS = {
            "regulatory": "Regulatory",
            "repurposing": "Repurposing",
            "mechanistic": "Mechanistic",
            "clinical": "Clinical",
            "knowledge_maturity": "Knowledge Maturity",
        }

        if scientific_context:
            chips: list[str] = []
            for dim_key in ("regulatory", "repurposing", "mechanistic", "clinical", "knowledge_maturity"):
                dim = scientific_context.get(dim_key) or {}
                status = dim.get("status", "—")
                icon, color, bg = _STATUS_STYLE.get(status, ("🔬", "#64748b", "rgba(100,116,139,0.1)"))
                conf = float(dim.get("confidence", 0.0))
                evidence = " ".join(dim.get("evidence", [])[:2])
                chips.append(
                    f"<div style='flex:1;min-width:150px;background:{bg};border:1px solid {color}33;"
                    f"border-radius:8px;padding:0.6rem 0.75rem;margin:0.15rem 0;'>"
                    f"<div style='color:#94a3b8;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.05em;'>"
                    f"{_DIMENSION_LABELS.get(dim_key, dim_key)}</div>"
                    f"<div style='font-size:0.95rem;font-weight:700;color:{color};'>{icon} {status} "
                    f"<span style='color:#94a3b8;font-weight:400;'>· {conf:.0%}</span></div>"
                    f"<div style='color:#cbd5e1;font-size:0.75rem;margin-top:0.2rem;'>{evidence[:160]}</div>"
                    f"</div>"
                )
            st.markdown(
                "<div style='font-size:0.85rem;font-weight:700;color:#94a3b8;text-transform:uppercase;"
                "letter-spacing:0.05em;margin:0.5rem 0 0.25rem;'>Prior Knowledge — Scientific Context</div>"
                + "".join(chips),
                unsafe_allow_html=True,
            )
        else:
            # Fallback: legacy single-pathway banner
            evaluation_pathway = getattr(audit, "evaluation_pathway", "NOVEL_HYPOTHESIS")
            _PATHWAY_CONFIG = {
                "APPROVED_INDICATION": ("✅", "#10b981", "rgba(16,185,129,0.1)", "FDA / EMA APPROVED INDICATION"),
                "NOVEL_HYPOTHESIS": ("🔬", "#64748b", "rgba(100,116,139,0.1)", "REPURPOSING HYPOTHESIS"),
            }
            cfg = _PATHWAY_CONFIG.get(evaluation_pathway, _PATHWAY_CONFIG["NOVEL_HYPOTHESIS"])
            st.markdown(f"""
            <div style="border-left: 4px solid {cfg[1]}; background: {cfg[2]};
                        padding: 1rem 1.25rem; border-radius: 8px; margin-bottom: 1rem;">
                <div style="font-size: 1rem; font-weight: 700; color: {cfg[1]}; letter-spacing: 0.05em;">
                    {cfg[0]} {cfg[3]}
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Multi-Agent Consensus Panel ────────────────────────────────────────────
        agent_verdicts = getattr(audit, "agent_verdicts", {})
        if agent_verdicts:
            st.markdown("### 🤖 Multi-Agent Consensus")
            _VERDICT_COLORS = {
                "HIGH": "#10b981", "VERY HIGH": "#10b981", "MEDIUM": "#f59e0b",
                "LOW": "#ef4444", "NONE": "#64748b", "CLEAR": "#10b981",
                "APPROVED": "#10b981", "ESTABLISHED": "#10b981",
            }
            verdict_rows = ""
            for agent, verdict in agent_verdicts.items():
                first_word = verdict.split()[0].upper() if verdict else ""
                color = _VERDICT_COLORS.get(first_word, "#94a3b8")
                verdict_rows += f"""
                <tr>
                    <td style="padding: 0.5rem 0.75rem; color: #94a3b8; font-size: 0.85rem;">{agent}</td>
                    <td style="padding: 0.5rem 0.75rem; color: {color}; font-size: 0.85rem; font-weight: 600;">{verdict}</td>
                </tr>"""
            st.markdown(f"""
            <div class="info-panel" style="padding: 0;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="border-bottom: 1px solid #2a3a55;">
                        <th style="padding: 0.5rem 0.75rem; text-align: left; color: #64748b; font-size: 0.75rem;">AGENT</th>
                        <th style="padding: 0.5rem 0.75rem; text-align: left; color: #64748b; font-size: 0.75rem;">VERDICT</th>
                    </tr>
                </thead>
                <tbody>{verdict_rows}</tbody>
            </table>
            </div>
            """, unsafe_allow_html=True)

        # ── Clinical Trial Status ──────────────────────────────────────────────
        _CT_STATUS_CONFIG = {
            "RETRIEVED": ("🟢", f"{len(pkg.clinical_trials)} trial(s) retrieved", "#10b981"),
            "NOT_FOUND": ("🟡", "ClinicalTrials.gov queried — 0 trials found for this pair", "#f59e0b"),
            "API_FAILURE": ("🔴", "ClinicalTrials.gov API error — trial count unknown (not 0)", "#ef4444"),
            "NOT_ATTEMPTED": ("⚪", "Clinical trial query not attempted", "#64748b"),
        }
        ct_icon, ct_label, ct_color = _CT_STATUS_CONFIG.get(ct_status, ("⚪", ct_status, "#64748b"))

        # Positive / Negative factors
        positive_factors = getattr(audit, "positive_factors", [])
        negative_factors = getattr(audit, "negative_factors", [])
        if positive_factors or negative_factors:
            st.markdown("### ⚖️ Decision Factors")
            fc1, fc2 = st.columns(2)
            with fc1:
                st.markdown("✅ **Supporting Factors**")
                for f in positive_factors[:6]:
                    st.markdown(f"- {f}")
                if not positive_factors:
                    st.caption("_None identified_")
            with fc2:
                st.markdown("❌ **Limiting Factors**")
                for f in negative_factors[:6]:
                    st.markdown(f"- {f}")
                if not negative_factors:
                    st.caption("_None identified_")

        st.markdown("---")


# ─────────────────────────────────────────────
# Page: Audit Report
# ─────────────────────────────────────────────
elif page == "📋 Audit Report":
    if not st.session_state.results:
        st.info("No evaluation results yet. Go to **🔬 Evaluate** to run an analysis.")
    else:
        r = st.session_state.results
        result = r["result"]
        audit = result.audit_report

        st.markdown(f"## Scientific Audit Report")
        st.markdown(f"**Drug:** {r['drug']} | **Disease:** {r['disease']}")
        st.markdown("---")

        st.markdown("### 📝 Executive Summary")
        st.markdown(f"""
        <div class="info-panel">
            <p style="line-height: 1.7; color: #cbd5e1;">{audit.summary}</p>
        </div>
        """, unsafe_allow_html=True)

        # ── Fix 6: 4-Dimensional Evidence Synthesis Panel ─────────────────────────
        m_narrative = getattr(audit, "mechanistic_narrative", "")
        c_narrative = getattr(audit, "clinical_narrative", "")
        s_narrative = getattr(audit, "safety_narrative", "")
        f_synthesis = getattr(audit, "final_synthesis", "")

        if m_narrative or c_narrative or s_narrative or f_synthesis:
            st.markdown("### 🧩 Evidence Synthesis & Dimensional Assessment")
            st_col1, st_col2 = st.columns(2)
            with st_col1:
                st.markdown(f"""
                <div class="info-panel" style="border-left: 4px solid #8b5cf6;">
                    <div style="font-weight: 700; color: #8b5cf6; margin-bottom: 0.5rem;">1. 🧬 Mechanistic Assessment</div>
                    <div style="color: #cbd5e1; font-size: 0.9rem; line-height: 1.5; white-space: pre-wrap;">{m_narrative}</div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(f"""
                <div class="info-panel" style="border-left: 4px solid #10b981;">
                    <div style="font-weight: 700; color: #10b981; margin-bottom: 0.5rem;">3. 🛡️ Safety & Risk Assessment</div>
                    <div style="color: #cbd5e1; font-size: 0.9rem; line-height: 1.5; white-space: pre-wrap;">{s_narrative}</div>
                </div>
                """, unsafe_allow_html=True)

            with st_col2:
                st.markdown(f"""
                <div class="info-panel" style="border-left: 4px solid #3b82f6;">
                    <div style="font-weight: 700; color: #3b82f6; margin-bottom: 0.5rem;">2. 📊 Clinical Evidence Assessment</div>
                    <div style="color: #cbd5e1; font-size: 0.9rem; line-height: 1.5; white-space: pre-wrap;">{c_narrative}</div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(f"""
                <div class="info-panel" style="border-left: 4px solid #f59e0b;">
                    <div style="font-weight: 700; color: #f59e0b; margin-bottom: 0.5rem;">4. 🎯 Final Recommendation Synthesis</div>
                    <div style="color: #cbd5e1; font-size: 0.9rem; line-height: 1.5; white-space: pre-wrap;">{f_synthesis}</div>
                </div>
                """, unsafe_allow_html=True)

        # Evaluation pathway and clinical trial status
        audit_pathway = getattr(audit, "evaluation_pathway", "NOVEL_HYPOTHESIS")
        audit_ct_status = getattr(audit, "clinical_trial_status", "NOT_ATTEMPTED")
        _audit_pw_cfg = _PATHWAY_CONFIG if "_PATHWAY_CONFIG" in dir() else {
            "APPROVED_INDICATION": {"icon": "✅", "label": "FDA/EMA Approved Indication", "color": "#10b981", "bg": "rgba(16,185,129,0.1)", "desc": ""},
            "NOVEL_HYPOTHESIS": {"icon": "🔬", "label": "Repurposing Hypothesis", "color": "#64748b", "bg": "rgba(100,116,139,0.1)", "desc": ""},
        }
        _pw_info = _audit_pw_cfg.get(audit_pathway, {"icon": "🔬", "label": audit_pathway, "color": "#64748b", "bg": "#1a2235", "desc": ""})
        _ct_status_labels = {
            "RETRIEVED": ("🟢", f"Retrieved ({len(r['package'].clinical_trials) if 'package' in r and hasattr(r['package'], 'clinical_trials') else '?'} trials)", "#10b981"),
            "NOT_FOUND": ("🟡", "Query succeeded — 0 trials found", "#f59e0b"),
            "API_FAILURE": ("🔴", "ClinicalTrials.gov API error (trial count unknown)", "#ef4444"),
            "NOT_ATTEMPTED": ("⚪", "Not attempted", "#64748b"),
        }
        _ct_icon2, _ct_lbl2, _ct_col2 = _ct_status_labels.get(audit_ct_status, ("⚪", audit_ct_status, "#64748b"))

        col_ap, col_ct = st.columns(2)
        with col_ap:
            st.markdown(f"""
            <div style="background: {_pw_info['bg']}; border-left: 3px solid {_pw_info['color']};
                        padding: 0.75rem 1rem; border-radius: 6px;">
                <b style="color: {_pw_info['color']};">{_pw_info['icon']} {_pw_info['label']}</b>
            </div>
            """, unsafe_allow_html=True)
        with col_ct:
            st.markdown(f"""
            <div style="background: rgba(30,40,60,0.5); border-left: 3px solid {_ct_col2};
                        padding: 0.75rem 1rem; border-radius: 6px;">
                <b style="color: {_ct_col2};">{_ct_icon2} Clinical Trials: {_ct_lbl2}</b>
            </div>
            """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### ✅ Key Supporting Claims")
            if audit.key_supporting_claim_ids:
                for cid in audit.key_supporting_claim_ids[:5]:
                    st.markdown(f"• `{cid[:8]}...`")
            else:
                st.markdown("_No supporting claims recorded._")

        with col2:
            st.markdown("### ❌ Key Contradicting Claims")
            if audit.key_contradicting_claim_ids:
                for cid in audit.key_contradicting_claim_ids[:5]:
                    st.markdown(f"• `{cid[:8]}...`")
            else:
                st.markdown("_No contradicting claims recorded._")

        if audit.data_gaps:
            st.markdown("### 🔍 Data Gaps Identified")
            for gap in audit.data_gaps:
                st.warning(f"⚠️ {gap}")

        # Agent verdicts in audit report
        audit_verdicts = getattr(audit, "agent_verdicts", {})
        if audit_verdicts:
            st.markdown("### 🤖 Expert Agent Assessments")
            for agent, verdict in audit_verdicts.items():
                st.markdown(f"**{agent}:** {verdict}")

        # Positive / negative factors in audit
        pos_f = getattr(audit, "positive_factors", [])
        neg_f = getattr(audit, "negative_factors", [])
        if pos_f or neg_f:
            st.markdown("### ⚖️ Recommendation Factors")
            fca, fcb = st.columns(2)
            with fca:
                st.markdown("✅ **Supporting**")
                for f in pos_f[:8]: st.markdown(f"- {f}")
            with fcb:
                st.markdown("❌ **Limiting**")
                for f in neg_f[:8]: st.markdown(f"- {f}")

        # Safety breakdown in audit
        safety_bd = getattr(audit, "safety_breakdown", {})
        if safety_bd:
            st.markdown("### 🛡️ Safety Profile Breakdown")
            grade = safety_bd.get("overall_grade", "?")
            grade_color = {"A": "#10b981", "B": "#3b82f6", "C": "#f59e0b", "D": "#ef4444"}.get(grade, "#64748b")
            boxed = safety_bd.get("has_boxed_warning", False)
            st.markdown(f"""
            <div class="info-panel" style="border-left: 4px solid {grade_color};">
                <span style="font-size: 1.5rem; font-weight: 700; color: {grade_color};">Grade {grade}</span>
                {'<span style="color: #ef4444; margin-left: 1rem;"> ⚠ Boxed Warning</span>' if boxed else ''}
            </div>
            """, unsafe_allow_html=True)
            aes = safety_bd.get("adverse_events", [])
            if aes:
                st.markdown("**Adverse Events:**")
                for ae in aes[:5]:
                    ev_name = ae.get("event", str(ae))
                    sev = ae.get("severity", "")
                    st.markdown(f"- {ev_name} ({sev})" if sev and sev != "unknown" else f"- {ev_name}")
            dis = safety_bd.get("drug_interactions", [])
            if dis:
                st.markdown(f"**Drug Interactions:** {', '.join(str(d) for d in dis[:3])}")

        # Sources Accessed Grid
        srcs = getattr(audit, "sources_accessed", []) or []
        if srcs:
            st.markdown("### 🌐 Biomedical Data Sources Accessed")
            sc_cols = st.columns(4)
            for i, s in enumerate(srcs):
                with sc_cols[i % 4]:
                    s_name = s.get("name", "")
                    s_stat = s.get("status", "SUCCESS")
                    s_url = s.get("url", "#")
                    s_lbl = s.get("label", "Open Portal")
                    badge_c = "#10b981" if s_stat == "SUCCESS" else ("#ef4444" if s_stat == "FAILED" else "#64748b")

                    st.markdown(f"""
                    <div style="background: #111827; border: 1px solid #1f2937; padding: 0.6rem 0.8rem; border-radius: 8px; margin-bottom: 0.5rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                            <span style="font-weight: 700; color: #f8fafc; font-size: 0.9rem;">{s_name}</span>
                            <span style="color: {badge_c}; font-size: 0.7rem; font-weight: 700; background: {badge_c}1a; padding: 0.1rem 0.4rem; border-radius: 4px;">{s_stat}</span>
                        </div>
                        <a href="{s_url}" target="_blank" style="color: #60a5fa; text-decoration: none; font-size: 0.75rem; font-weight: 600;">{s_lbl} ↗</a>
                    </div>
                    """, unsafe_allow_html=True)

        # Citations
        top_cits = getattr(audit, "top_citations", [])
        if top_cits:
            st.markdown("### 📚 Evidence Citations")
            with st.expander(f"{len(top_cits)} Citation(s) — click to expand"):
                for cit in top_cits:
                    # Parse PMID or DOI out of citation string to make clickable
                    links = SourceURLBuilder.build_links_for_citation_key(cit.split()[0] if cit else "")
                    link_html = ""
                    if links:
                        link_html = " " + " ".join(f'<a href="{l.url}" target="_blank" style="color: #60a5fa; text-decoration: none; font-size: 0.8rem; margin-left: 0.3rem;">[{l.display_label}] ↗</a>' for l in links)
                    st.markdown(f"- {cit}{link_html}", unsafe_allow_html=True)

        with st.expander("📜 Recommendation Rule Trace"):
            st.markdown(f"""
            ```
            {audit.recommendation_rationale}
            ```
            """)

        with st.expander("📈 Confidence Narrative"):
            st.markdown(audit.confidence_narrative)

        st.markdown("---")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Rule Set Version", result.rule_set_version)
        with col_b:
            st.metric("Reasoning Duration", f"{result.reasoning_duration_ms:.0f} ms")
        with col_c:
            st.metric("Completed At", result.completed_at.strftime("%Y-%m-%d %H:%M UTC"))

        # ── Phase 3: PDF Download ─────────────────────────────────────
        st.markdown("---")
        st.markdown("### 📄 Export Report")
        col_pdf, col_txt = st.columns(2)

        with col_pdf:
            try:
                from backend.reporting.pdf_exporter import PDFReporter
                reporter = PDFReporter(
                    drug_name=r['drug'],
                    disease_name=r['disease'],
                )
                pdf_bytes = reporter.generate(result)
                is_pdf = pdf_bytes[:4] == b"%PDF"
                mime = "application/pdf" if is_pdf else "text/plain"
                ext = "pdf" if is_pdf else "txt"
                filename = f"CYNTHERA_{r['drug']}_{r['disease']}.{ext}".replace(" ", "_")

                st.download_button(
                    label=f"{'📄 Download PDF Report' if is_pdf else '📝 Download Text Report'}",
                    data=pdf_bytes,
                    file_name=filename,
                    mime=mime,
                    use_container_width=True,
                )
                if not is_pdf:
                    st.caption("Install `reportlab` for full PDF support: `pip install reportlab`")
            except Exception as exc:
                st.warning(f"Report export unavailable: {exc}")


# ─────────────────────────────────────────────
# Page: History
# ─────────────────────────────────────────────
elif page == "🕐 History":
    st.markdown("## Evaluation History")
    st.markdown("Past evaluations are loaded from the persistent SQLite database.")

    import pandas as pd
    from backend.storage.repository import StorageRepository

    _repo = StorageRepository(db_path="data/cynthera.db")
    evaluations = _repo.list_evaluations(limit=100)

    if not evaluations:
        st.info("No evaluations yet. Go to **🔬 Evaluate** to run your first analysis.")
    else:
        rows = []
        for ev in evaluations:
            rows.append({
                "Hypothesis ID": ev.get("hypothesis_id", "")[:12] + "...",
                "Drug": ev.get("drug_name", ""),
                "Disease": ev.get("disease_name", ""),
                "Recommendation": ev.get("recommendation", ""),
                "Support Score": round(float(ev.get("support_score", 0)), 3),
                "Mech. Score": round(float(ev.get("mechanistic_score", 0)), 3),
                "Risk Score": round(float(ev.get("risk_score", 0)), 3),
                "Retrieval Confidence": ev.get("retrieval_confidence", ""),
                "Completed At": ev.get("completed_at", ""),
            })
        df = pd.DataFrame(rows)

        def color_rec(val: str) -> str:
            colors = {
                "PROMISING": "color: #10b981; font-weight: 600",
                "UNCERTAIN": "color: #f59e0b; font-weight: 600",
                "NOT_RECOMMENDED": "color: #ef4444; font-weight: 600",
            }
            return colors.get(val, "")

        styled = df.style.map(color_rec, subset=["Recommendation"])
        st.dataframe(styled, use_container_width=True)

        st.caption(f"Showing {len(rows)} evaluation(s) from persistent storage.")

        col_dl, _ = st.columns([1, 3])
        with col_dl:
            csv = df.to_csv(index=False)
            st.download_button(
                "📥 Export CSV",
                data=csv,
                file_name="cynthera_history.csv",
                mime="text/csv",
            )

# ─────────────────────────────────────────────
# Page: Batch Evaluation (Phase 3)
# ─────────────────────────────────────────────
elif page == "⚡ Batch":
    st.markdown("## ⚡ Batch Evaluation")
    st.markdown(
        "<p style='color: #94a3b8;'>Submit multiple drug-disease pairs for parallel evaluation. "
        "Results are processed asynchronously in the background.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("### 📝 Enter Batch Items")
    st.markdown("One item per line, format: `DrugName | DiseaseName`")

    batch_input = st.text_area(
        "Drug-Disease Pairs",
        height=200,
        placeholder="Sildenafil | Pulmonary Arterial Hypertension\nMetformin | Cancer\nAspirin | Colorectal Cancer",
        label_visibility="collapsed",
    )

    col_b1, col_b2, _ = st.columns([1, 1, 2])
    with col_b1:
        batch_policy = st.selectbox("Policy", ["STANDARD", "FAST", "COMPREHENSIVE"], key="batch_policy")
    with col_b2:
        submit_batch_btn = st.button("🚀 Submit Batch", use_container_width=True)

    if submit_batch_btn:
        if not batch_input.strip():
            st.error("Please enter at least one drug-disease pair.")
        else:
            items = []
            errors = []
            for line in batch_input.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                if "|" not in line:
                    errors.append(f"Invalid format: '{line}' (expected 'Drug | Disease')")
                    continue
                parts = line.split("|", 1)
                drug = parts[0].strip()
                disease = parts[1].strip()
                if drug and disease:
                    items.append({"drug_name": drug, "disease_name": disease, "retrieval_policy": batch_policy})

            if errors:
                for err in errors:
                    st.warning(err)

            if items:
                try:
                    from backend.storage.batch_repository import BatchRepository
                    repo = BatchRepository(db_path="data/cynthera.db")
                    batch_id = repo.create_batch(items)
                    st.success(f"✅ Batch submitted! **Batch ID:** `{batch_id}`")
                    st.info(
                        f"Processing {len(items)} item(s) in the background. "
                        f"Use the API endpoint `GET /api/v1/batch/{batch_id}` to check progress, "
                        f"or poll `GET /api/v1/batch/{batch_id}/results` for results."
                    )
                    st.code(f"Batch ID: {batch_id}", language="text")
                except Exception as exc:
                    st.error(f"Failed to submit batch: {exc}")

    st.markdown("---")
    st.markdown("### 📋 Recent Batches")
    try:
        from backend.storage.batch_repository import BatchRepository
        repo = BatchRepository(db_path="data/cynthera.db")
        batches = repo.list_batches(limit=10)
        if batches:
            import pandas as pd
            batch_df = pd.DataFrame(batches)
            st.dataframe(batch_df[["batch_id", "status", "total_items", "completed_items", "failed_items", "created_at"]], use_container_width=True)
        else:
            st.info("No batch jobs yet.")
    except Exception as exc:
        st.warning(f"Could not load batch history: {exc}")


# ─────────────────────────────────────────────
# Page: Phase 4E Evaluation (Benchmark & Ablations)
# ─────────────────────────────────────────────
elif page in ("🧪 Phase 4E Evaluation", "🧪 Evaluation & Benchmark"):
    # ── Phase 5.8 Final Test Benchmark & Validation Dashboard ──
    render_benchmark_panel(st.session_state.get("phase4e_report"))
    st.markdown("---")
    render_ablation_panel(st.session_state.get("phase4e_report"))

    with st.expander("⚡ Live Pipeline Benchmark Execution", expanded=False):
        st.markdown(
            "<p style='color: #94a3b8;'>Optionally re-execute all 24 benchmark cases through the live MasterOrchestrator pipeline.</p>",
            unsafe_allow_html=True,
        )
        run_bench_btn = st.button("🚀 Re-Run Live Benchmark", type="primary", use_container_width=True)
        if run_bench_btn:
            with st.spinner("Running Live Benchmark & Ablation Study..."):
                try:
                    from backend.evaluation.benchmark_runner import BenchmarkRunner
                    runner = BenchmarkRunner()
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    report = loop.run_until_complete(runner.run_benchmark(bypass_cache=True, include_ablations=True))
                    st.session_state.phase4e_report = report
                    st.success("✅ Live benchmark complete!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Live benchmark failed: {exc}")

