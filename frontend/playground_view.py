"""CYNTHERA Playground — Interactive Hypothesis Exploration & Scenario Workspace.

Provides the interactive evidence graph, 'Why is this relationship here?'
inspector, evidence landscape, honest scenario recomputation (MS-only),
and researcher notes.
"""
from __future__ import annotations

import logging
from typing import Any

import streamlit as st
import plotly.graph_objects as go

from backend.storage.repository import StorageRepository
from backend.playground.subgraph_extractor import extract_relevant_subgraph
from backend.playground.scenario_engine import ScenarioEngine
from backend.playground.investigation_store import InvestigationStore
from backend.playground.models import (
    PlaygroundGraphData,
    ScenarioModifications,
    ScenarioModification,
    ResearcherNote,
)
from backend.core.value_objects.source_url_builder import SourceURLBuilder

logger = logging.getLogger(__name__)

# Node type color mapping
NODE_COLORS = {
    "DRUG": "#3b82f6",     # Blue
    "TARGET": "#8b5cf6",   # Purple
    "GENE": "#10b981",     # Emerald green
    "PATHWAY": "#f59e0b",  # Amber
    "DISEASE": "#ef4444",  # Red
}

def _get_or_compute_layout(graph_data: PlaygroundGraphData) -> dict[str, tuple[float, float]]:
    """Compute and cache deterministic node layout coordinates."""
    cache_key = f"layout_{graph_data.hypothesis_id}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    type_tiers = {
        "DRUG": 0.0,
        "TARGET": 1.2,
        "GENE": 2.2,
        "PATHWAY": 2.6,
        "DISEASE": 3.8,
    }

    nodes_by_type: dict[str, list[str]] = {}
    for node in graph_data.nodes:
        nodes_by_type.setdefault(node.label, []).append(node.id)

    pos: dict[str, tuple[float, float]] = {}
    for label, node_ids in nodes_by_type.items():
        base_x = type_tiers.get(label, 2.0)
        n_count = len(node_ids)
        for idx, nid in enumerate(node_ids):
            y = (idx - (n_count - 1) / 2.0) * 1.3
            x = base_x + (0.15 if label == "PATHWAY" and idx % 2 == 1 else 0.0)
            pos[nid] = (x, y)

    st.session_state[cache_key] = pos
    return pos


def _build_playground_figure(
    graph_data: PlaygroundGraphData,
    positions: dict[str, tuple[float, float]],
    visible_types: set[str],
    selected_element: str | None,
    selected_type: str | None,
    disabled_edges: set[str],
) -> tuple[go.Figure, dict[str, Any]]:
    """Build the interactive Plotly network figure."""
    visible_node_ids = {n.id for n in graph_data.nodes if n.label in visible_types}

    # Edges
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    mid_x: list[float] = []
    mid_y: list[float] = []
    mid_text: list[str] = []
    mid_customdata: list[str] = []
    mid_colors: list[str] = []
    mid_symbols: list[str] = []

    edge_lookup: dict[str, Any] = {}
    for edge in graph_data.edges:
        if edge.source_id not in visible_node_ids or edge.target_id not in visible_node_ids:
            continue
        p0 = positions.get(edge.source_id, (0.0, 0.0))
        p1 = positions.get(edge.target_id, (1.0, 0.0))

        edge_key = f"EDGE:{edge.source_id}->{edge.target_id}:{edge.predicate}"
        edge_lookup[edge_key] = edge

        is_disabled = edge_key in disabled_edges or edge.is_disabled
        is_selected = (selected_type == "edge" and selected_element == edge_key)

        # Line segment
        edge_x.extend([p0[0], p1[0], None])
        edge_y.extend([p0[1], p1[1], None])

        # Midpoint marker
        mx = (p0[0] + p1[0]) / 2.0
        my = (p0[1] + p1[1]) / 2.0
        mid_x.append(mx)
        mid_y.append(my)
        status_tag = " [DISABLED]" if is_disabled else ""
        mid_text.append(f"{edge.predicate}{status_tag}<br>Strength: {edge.evidence_strength:.2f}")
        mid_customdata.append(edge_key)

        if is_disabled:
            mid_colors.append("#ef4444")
            mid_symbols.append("x")
        elif is_selected:
            mid_colors.append("#06b6d4")
            mid_symbols.append("diamond")
        else:
            mid_colors.append("#94a3b8")
            mid_symbols.append("diamond")

    lines_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line=dict(width=1.8, color="rgba(148, 163, 184, 0.35)"),
        hoverinfo="none",
        showlegend=False,
    )

    edge_markers_trace = go.Scatter(
        x=mid_x,
        y=mid_y,
        mode="markers+text",
        marker=dict(size=11, color=mid_colors, symbol=mid_symbols),
        text=[t.split("<br>")[0][:14] for t in mid_text],
        textposition="top center",
        textfont=dict(size=9, color="#94a3b8"),
        customdata=mid_customdata,
        hovertext=mid_text,
        hoverinfo="text",
        name="Relationships",
    )

    # Nodes
    node_x: list[float] = []
    node_y: list[float] = []
    node_text: list[str] = []
    node_customdata: list[str] = []
    node_colors: list[str] = []
    node_sizes: list[int] = []
    node_border_widths: list[int] = []
    node_border_colors: list[str] = []
    node_display_texts: list[str] = []

    node_lookup: dict[str, Any] = {}
    for node in graph_data.nodes:
        if node.id not in visible_node_ids:
            continue
        node_lookup[node.id] = node
        p = positions.get(node.id, (0.0, 0.0))
        node_x.append(p[0])
        node_y.append(p[1])

        is_selected = (selected_type == "node" and selected_element == f"NODE:{node.id}")
        color = NODE_COLORS.get(node.label, "#94a3b8")
        node_colors.append(color)
        node_sizes.append(32 if is_selected else 24)
        node_border_widths.append(3 if is_selected else 1)
        node_border_colors.append("#ffffff" if is_selected else "#1e293b")

        node_customdata.append(f"NODE:{node.id}")
        node_text.append(f"<b>{node.name}</b><br>Type: {node.label}<br>ID: {node.id}")

        # Format display text: split long multi-word names across 2 lines
        words = node.name.split()
        if len(words) > 2 and len(node.name) > 14:
            mid = len(words) // 2
            display_label = " ".join(words[:mid]) + "<br>" + " ".join(words[mid:])
        elif len(node.name) > 18:
            display_label = node.name[:16] + "…"
        else:
            display_label = node.name
        node_display_texts.append(display_label)

    nodes_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        marker=dict(
            size=node_sizes,
            color=node_colors,
            line=dict(width=node_border_widths, color=node_border_colors),
        ),
        text=node_display_texts,
        textposition="bottom center",
        textfont=dict(size=11, color="#f1f5f9"),
        customdata=node_customdata,
        hovertext=node_text,
        hoverinfo="text",
        name="Entities",
    )

    fig = go.Figure(data=[lines_trace, edge_markers_trace, nodes_trace])
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="#0b1120",
        paper_bgcolor="#0b1120",
        hovermode="closest",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=560,
        clickmode="event+select",
        dragmode="pan",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color="#94a3b8", size=10),
        ),
    )

    return fig, {"edges": edge_lookup, "nodes": node_lookup}


def render_playground_view() -> None:
    """Main render entrypoint for the Playground view."""
    repo = StorageRepository(db_path="data/cynthera.db")
    investigation_store = InvestigationStore(db_path="data/cynthera.db")
    scenario_engine = ScenarioEngine()

    st.markdown("## 🔍 CYNTHERA Playground")
    st.caption("Interactive Evidence Graph Exploration, Hop-level Traceability & Scenario Workspace")

    # ─────────────────────────────────────────────
    # Hypothesis Selection Bar
    # ─────────────────────────────────────────────
    evaluations = repo.list_evaluations(limit=100)
    if not evaluations and not st.session_state.get("results"):
        st.info("No completed evaluations found. Go to **🔬 Evaluate** to run an analysis first.")
        return

    # Build evaluation options
    eval_options: dict[str, str] = {}
    if st.session_state.get("results"):
        curr_res = st.session_state.results["result"]
        curr_pkg = st.session_state.results["package"]
        label = f"Current: {curr_pkg.drug.name} ➔ {curr_pkg.disease.name} ({curr_res.recommendation_status.value})"
        eval_options[label] = str(curr_res.hypothesis_id)

    for ev in evaluations:
        label = f"{ev.get('drug_name')} ➔ {ev.get('disease_name')} [{ev.get('recommendation')}] ({ev.get('hypothesis_id', '')[:8]})"
        eval_options[label] = ev.get("hypothesis_id", "")

    # Selected hypothesis ID
    default_idx = 0
    target_hyp_id = st.session_state.get("playground_hyp_id")
    if target_hyp_id:
        for idx, hid in enumerate(eval_options.values()):
            if hid == target_hyp_id:
                default_idx = idx
                break

    col_sel, col_reset = st.columns([5, 1])
    with col_sel:
        selected_label = st.selectbox(
            "Select Evaluation to Explore:",
            options=list(eval_options.keys()),
            index=default_idx,
            label_visibility="collapsed",
        )
    with col_reset:
        if st.button("🔄 Reset Graph View", use_container_width=True):
            st.session_state.pop("playground_selected_element", None)
            st.session_state.pop("playground_selected_type", None)
            target_id = eval_options.get(selected_label)
            if target_id:
                st.session_state.pop(f"layout_{target_id}", None)
            st.rerun()

    active_hyp_id = eval_options.get(selected_label)
    if not active_hyp_id:
        st.warning("Please select a valid evaluation.")
        return

    # Load Package and ReasoningResult
    pkg = repo.get_retrieval_package(active_hyp_id)
    res = repo.get_reasoning_result(active_hyp_id)

    # Fallback to session_state if active is currently running in memory
    if (pkg is None or res is None) and st.session_state.get("results"):
        if str(st.session_state.results["result"].hypothesis_id) == active_hyp_id:
            pkg = st.session_state.results["package"]
            res = st.session_state.results["result"]

    if pkg is None or res is None:
        st.error(f"Could not load data for hypothesis `{active_hyp_id}`.")
        return

    # Extract Graph Data
    graph_data = extract_relevant_subgraph(pkg, res)

    # State initialization for this hypothesis
    disabled_edges_key = f"disabled_edges_{active_hyp_id}"
    if disabled_edges_key not in st.session_state:
        st.session_state[disabled_edges_key] = set()
    disabled_edges: set[str] = st.session_state[disabled_edges_key]

    selected_element = st.session_state.get("playground_selected_element")
    selected_type = st.session_state.get("playground_selected_type")

    # ─────────────────────────────────────────────
    # Main Playground 2-Column Layout
    # ─────────────────────────────────────────────
    col_graph, col_sidebar = st.columns([7, 5])

    # Compute layout
    positions = _get_or_compute_layout(graph_data)

    with col_graph:
        # Filters toolbar
        all_labels = sorted(list({n.label for n in graph_data.nodes}))
        col_f1, col_f2 = st.columns([3, 1])
        with col_f1:
            visible_types = set(
                st.multiselect(
                    "Filter Node Types:",
                    options=all_labels,
                    default=all_labels,
                    label_visibility="collapsed",
                )
            )
        with col_f2:
            st.caption(f"**{len(graph_data.nodes)}** nodes, **{len(graph_data.edges)}** edges")

        fig, lookups = _build_playground_figure(
            graph_data,
            positions,
            visible_types,
            selected_element,
            selected_type,
            disabled_edges,
        )

        event = st.plotly_chart(
            fig,
            use_container_width=True,
            on_select="rerun",
            selection_mode=["points"],
            key=f"plotly_chart_{active_hyp_id}",
        )

        # Process click events
        if event and "selection" in event and event["selection"]["points"]:
            pt = event["selection"]["points"][0]
            cdata = pt.get("customdata")
            if cdata:
                if cdata.startswith("NODE:"):
                    st.session_state["playground_selected_type"] = "node"
                    st.session_state["playground_selected_element"] = cdata
                elif cdata.startswith("EDGE:"):
                    st.session_state["playground_selected_type"] = "edge"
                    st.session_state["playground_selected_element"] = cdata

        # Legend footer
        st.markdown(
            """
            <div style="display: flex; gap: 1rem; font-size: 0.8rem; color: #94a3b8; justify-content: center; margin-top: -0.5rem;">
                <span><span style="color: #3b82f6;">●</span> Drug</span>
                <span><span style="color: #8b5cf6;">●</span> Target</span>
                <span><span style="color: #10b981;">●</span> Gene</span>
                <span><span style="color: #f59e0b;">●</span> Pathway</span>
                <span><span style="color: #ef4444;">●</span> Disease</span>
                <span><span style="color: #06b6d4;">◆</span> Selected</span>
                <span><span style="color: #ef4444;">✕</span> Disabled Edge</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ─────────────────────────────────────────────
    # Right Sidebar: Inspector & Workspace Tabs
    # ─────────────────────────────────────────────
    with col_sidebar:
        tab_inspect, tab_landscape, tab_scenario, tab_notes = st.tabs([
            "❓ Inspector",
            "⚖️ Assessment",
            "🧪 Scenario",
            "📝 Notes",
        ])

        # ── Tab 1: "Why is this relationship here?" Inspector ────────────────
        with tab_inspect:
            if selected_type == "edge" and selected_element:
                edge = lookups["edges"].get(selected_element)
                if edge:
                    st.markdown("### ❓ Why is this relationship here?")
                    st.markdown(f"**From:** `{edge.source_id}`<br>**Predicate:** `{edge.predicate}`<br>**To:** `{edge.target_id}`", unsafe_allow_html=True)
                    st.markdown("---")

                    c_m1, c_m2, c_m3 = st.columns(3)
                    c_m1.metric("Paths", edge.path_count, help="Candidate mechanistic paths traversing this edge")
                    c_m2.metric("Evidence", edge.evidence_count, help="Direct evidence records supporting this connection")
                    c_m3.metric("Strength", f"{edge.evidence_strength:.2f}")

                    st.markdown("#### Provenance & Sources")
                    st.write(f"• **Source DB:** `{edge.source_database or 'Curated Biomedical DB'}`")
                    st.write(f"• **Quality:** `{edge.data_quality}`")
                    if edge.provenance:
                        st.write(f"• **Detail:** {edge.provenance}")

                    # Hop claims from candidate mechanisms
                    if edge.hop_claims:
                        st.markdown("#### Hop-Level Scientific Claims")
                        for hc in edge.hop_claims[:5]:
                            txt = hc.get("text", str(hc))
                            direction = hc.get("direction", "supporting")
                            icon = "✓" if direction == "supporting" else "⚠"
                            color = "#10b981" if direction == "supporting" else "#ef4444"
                            st.markdown(f"<span style='color: {color};'>{icon}</span> {txt}", unsafe_allow_html=True)

                    # External links
                    if edge.links:
                        st.markdown("#### Source Links")
                        for lk in edge.links:
                            url = lk.get("url")
                            lbl = lk.get("display_label") or lk.get("source_name") or "Open Source"
                            if url:
                                st.markdown(f"• [{lbl}]({url})")

                    st.markdown("---")
                    # Challenge / Disable button
                    is_dis = selected_element in disabled_edges
                    btn_text = "✅ Re-enable Relationship" if is_dis else "⚠️ Challenge & Disable Relationship"
                    if st.button(btn_text, key="toggle_edge_btn", type="secondary" if is_dis else "primary", use_container_width=True):
                        if is_dis:
                            disabled_edges.remove(selected_element)
                        else:
                            disabled_edges.add(selected_element)
                        st.rerun()
                else:
                    st.info("Select an edge on the graph to inspect why it was retrieved.")

            elif selected_type == "node" and selected_element:
                nid = selected_element.replace("NODE:", "")
                node = lookups["nodes"].get(nid)
                if node:
                    st.markdown(f"### Node: `{node.name}`")
                    st.write(f"• **Type:** `{node.label}`")
                    st.write(f"• **Identifier:** `{node.id}`")
                    st.write(f"• **Direct Evidence Count:** {node.evidence_count}")

                    # External links for this node
                    if node.links:
                        st.markdown("#### External Links")
                        for lk in node.links:
                            url = lk.get("url")
                            lbl = lk.get("display_label") or lk.get("source_name") or "View Record"
                            if url:
                                st.markdown(f"• [{lbl}]({url})")

                    # Connected relationships
                    connected = [e for e in graph_data.edges if e.source_id == nid or e.target_id == nid]
                    st.markdown(f"#### Connected Relationships ({len(connected)})")
                    for e in connected[:8]:
                        arrow = "➔" if e.source_id == nid else "⬅"
                        peer = e.target_id if e.source_id == nid else e.source_id
                        st.caption(f"{arrow} **{e.predicate}** with `{peer}` (Strength: {e.evidence_strength:.2f})")
                else:
                    st.info("Select a node on the graph to inspect details.")
            else:
                st.info("👈 Click any node (circle) or relationship (diamond) on the graph to inspect provenance, paths, and details.")

        # ── Tab 2: Evidence Landscape & Gaps ────────────────────────────────
        with tab_landscape:
            ls = graph_data.landscape
            st.markdown("### ⚖️ Evidence Assessment")

            c_s1, c_s2 = st.columns(2)
            with c_s1:
                st.metric("Support Score (SS)", f"{ls.support_score:.3f}", ls.support_level)
                st.metric("Mechanistic Score (MS)", f"{ls.mechanistic_score:.3f}", ls.mechanistic_level)
            with c_s2:
                st.metric("Risk Score (RS)", f"{ls.risk_score:.3f}", ls.risk_level)
                st.metric("Opposition Score", f"{ls.opposition_score:.3f}", ls.opposition_level)

            st.markdown(f"**Recommendation:** `{ls.recommendation_status}`")
            for reason in ls.recommendation_reasons[:3]:
                st.caption(f"• {reason}")

            st.markdown("---")
            st.markdown("### 🧩 Evidence Gaps & Coverage")
            for gap in graph_data.evidence_gaps:
                if gap.status == "FOUND":
                    icon = "✅"
                    color = "#10b981"
                elif gap.status == "LIMITED":
                    icon = "⚡"
                    color = "#f59e0b"
                elif gap.status == "CONFLICTED":
                    icon = "⚠️"
                    color = "#ef4444"
                else:
                    icon = "❓"
                    color = "#64748b"
                st.markdown(f"<span style='color: {color};'>{icon} <b>{gap.label}</b></span>", unsafe_allow_html=True)

            if graph_data.contradictions:
                st.markdown("---")
                st.markdown("### ⚠️ Conflicting Findings")
                for c in graph_data.contradictions:
                    st.warning(f"**{c.conflict_type.upper()} Conflict:** {c.explanation} (Score: {c.contradiction_score:.2f})")

        # ── Tab 3: Scenario What-If Mode (Honest Recomputation) ──────────────
        with tab_scenario:
            st.markdown("### 🧪 Scenario What-If Mode")
            st.caption("Test how the hypothesis holds up when specific biological relationships are challenged or removed.")

            disabled_count = len(disabled_edges)
            st.write(f"**Challenged / Disabled Relationships:** {disabled_count}")

            if disabled_count == 0:
                st.info("No relationships are disabled. Click any relationship on the graph and select 'Challenge & Disable Relationship' to start a scenario.")
            else:
                for d_edge in list(disabled_edges):
                    c_txt, c_btn = st.columns([4, 1])
                    with c_txt:
                        st.caption(f"• `{d_edge.replace('EDGE:', '')}`")
                    with c_btn:
                        if st.button("✕", key=f"del_{d_edge}", help="Remove from disabled"):
                            disabled_edges.remove(d_edge)
                            st.rerun()

                # Build modifications
                mods = ScenarioModifications(
                    modifications=[
                        ScenarioModification(action="disable_edge", edge_id=d_edge)
                        for d_edge in disabled_edges
                    ]
                )

                # Compute scenario result
                scen_res = scenario_engine.compute_scenario(pkg, res, mods)

                st.markdown("---")
                st.markdown("#### Scenario Impact Comparison")

                # Comparison metrics
                c_orig, c_scen, c_delta = st.columns(3)
                c_orig.metric("Original MS", f"{scen_res.original_mechanistic_score:.3f}")
                c_scen.metric("Scenario MS", f"{scen_res.scenario_mechanistic_score:.3f}")
                ms_delta = scen_res.scenario_mechanistic_score - scen_res.original_mechanistic_score
                c_delta.metric("MS Delta", f"{ms_delta:+.3f}")

                # Recommendation shift
                st.markdown(
                    f"**Recommendation Shift:** `{scen_res.original_recommendation}` ➔ "
                    f"<span style='color: {'#10b981' if scen_res.scenario_recommendation == 'PROMISING' else '#f59e0b'}; font-weight: 700;'>"
                    f"{scen_res.scenario_recommendation}</span>",
                    unsafe_allow_html=True,
                )

                st.markdown(f"• **Mechanistic Paths Lost:** {scen_res.affected_paths} (Remaining: {scen_res.scenario_path_count})")
                for chg in scen_res.changes_summary[:4]:
                    st.caption(f"• {chg}")

                st.markdown("---")
                # Honest disclaimer alert
                st.warning(
                    f"**Honest Evaluation Notice:** {scen_res.disclaimer}\n\n"
                    f"• **Recomputed:** `{scen_res.scores_recomputed}`\n"
                    f"• **Kept Original:** `{scen_res.scores_kept_original}`"
                )

                if st.button("Reset All Challenged Relationships", type="secondary"):
                    disabled_edges.clear()
                    st.rerun()

        # ── Tab 4: Researcher Notes (SQLite Persisted) ────────────────────────
        with tab_notes:
            st.markdown("### 📝 Researcher Notes")
            st.caption("Annotate and document your investigation findings. Persisted across sessions.")

            new_note_text = st.text_area("Add note:", height=90, placeholder="Document observations, rationale for challenged edges, or clinical context...")
            target_type_opt = st.selectbox("Attach note to:", ["hypothesis", "edge", "node"], index=0)

            target_id_val = None
            if target_type_opt == "edge" and selected_type == "edge":
                target_id_val = selected_element
            elif target_type_opt == "node" and selected_type == "node":
                target_id_val = selected_element

            if st.button("💾 Save Note", use_container_width=True, type="primary"):
                if new_note_text.strip():
                    note_obj = ResearcherNote(
                        hypothesis_id=active_hyp_id,
                        target_type=target_type_opt,
                        target_id=target_id_val,
                        text=new_note_text.strip(),
                    )
                    investigation_store.save_note(note_obj)
                    st.success("Note saved!")
                    st.rerun()
                else:
                    st.warning("Note cannot be empty.")

            st.markdown("---")
            existing_notes = investigation_store.get_notes(active_hyp_id)
            if existing_notes:
                st.markdown(f"**Saved Notes ({len(existing_notes)}):**")
                for nt in existing_notes:
                    c_ntext, c_ndel = st.columns([5, 1])
                    with c_ntext:
                        st.markdown(f"**[{nt.target_type.upper()}]** {nt.text}")
                        st.caption(f"Added: {nt.created_at.strftime('%Y-%m-%d %H:%M')}")
                    with c_ndel:
                        if st.button("🗑️", key=f"del_note_{nt.id}"):
                            investigation_store.delete_note(nt.id)
                            st.rerun()
            else:
                st.caption("No researcher notes added yet for this evaluation.")
