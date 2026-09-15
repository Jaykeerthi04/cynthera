"""Phase 0: Graph Library Prototype — test Plotly network graph in Streamlit.

Tests:
- Click node -> state updates
- Click edge -> state updates
- Zoom / pan
- Node type coloring
- Selection persistence across rerenders
- Edge labels
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import json
from collections import Counter

from backend.storage.repository import StorageRepository
from backend.reasoning.mechanistic.evidence_graph import EvidenceGraphBuilder


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
st.set_page_config(page_title="Graph Prototype", layout="wide")
st.markdown("""
<style>
    body { background: #0f172a; color: #e2e8f0; }
    .stApp { background: #0f172a; }
    .node-detail { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1rem; margin-top: 1rem; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────
if "selected_node" not in st.session_state:
    st.session_state.selected_node = None
if "selected_edge" not in st.session_state:
    st.session_state.selected_edge = None
if "disabled_edges" not in st.session_state:
    st.session_state.disabled_edges = set()


# ─────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────
@st.cache_data
def load_graph_data(hypothesis_id: str):
    repo = StorageRepository(db_path="data/cynthera.db")
    pkg = repo.get_retrieval_package(hypothesis_id)
    result = repo.get_reasoning_result(hypothesis_id)
    if not pkg or not result:
        return None, None, None, None
    
    builder = EvidenceGraphBuilder()
    graph = builder.build(pkg)
    return pkg, result, graph, {
        "nodes": list(graph.nodes.values()),
        "edges": list(graph.edges),
    }


@st.cache_data
def get_evaluations():
    repo = StorageRepository(db_path="data/cynthera.db")
    return repo.list_evaluations(limit=20)


# ─────────────────────────────────────────────
# Sidebar: select evaluation
# ─────────────────────────────────────────────
st.sidebar.markdown("### Graph Prototype")
evals = get_evaluations()
options = [f"{ev['drug_name']} -> {ev['disease_name']} ({ev['recommendation']})" for ev in evals]
selected_idx = st.sidebar.selectbox("Select evaluation", range(len(options)), format_func=lambda i: options[i])
hypothesis_id = evals[selected_idx]['hypothesis_id']

pkg, result, graph, graph_data = load_graph_data(hypothesis_id)

if not pkg:
    st.error("No data found for this evaluation.")
    st.stop()

st.markdown(f"## {pkg.drug.name} → {pkg.disease.name}")
st.markdown(f"**{result.recommendation_status.value}** | SS={result.support_assessment.score:.3f} MS={result.mechanistic_assessment.score:.3f} RS={result.risk_assessment.score:.3f}")

# ─────────────────────────────────────────────
# Node type config
# ─────────────────────────────────────────────
NODE_CONFIG = {
    "DRUG": {"color": "#8b5cf6", "size": 25, "symbol": "diamond", "emoji": "💊"},
    "TARGET": {"color": "#06b6d4", "size": 20, "symbol": "circle", "emoji": "🎯"},
    "GENE": {"color": "#10b981", "size": 18, "symbol": "triangle-up", "emoji": "🧬"},
    "PATHWAY": {"color": "#f59e0b", "size": 18, "symbol": "square", "emoji": "🔬"},
    "DISEASE": {"color": "#ef4444", "size": 25, "symbol": "star", "emoji": "🏥"},
    "CLINICAL_TRIAL": {"color": "#64748b", "size": 15, "symbol": "pentagon", "emoji": "📋"},
}

EDGE_COLORS = {
    "INHIBITOR": "#ef4444",
    "AGONIST": "#10b981",
    "MODULATES": "#8b5cf6",
    "PARTICIPATES_IN": "#64748b",
    "ENCODED_BY_DISEASE_ASSOCIATED_GENE": "#f59e0b",
    "CONTAINS_ASSOCIATED_GENE": "#f59e0b",
    "ASSOCIATED_WITH": "#06b6d4",
    "OPENER": "#10b981",
}

# ─────────────────────────────────────────────
# Build Plotly graph
# ─────────────────────────────────────────────
import math

nodes = graph_data["nodes"]
edges = graph_data["edges"]

# Layout: simple hierarchical by type
type_order = {"DRUG": 0, "TARGET": 1, "PATHWAY": 2, "GENE": 3, "DISEASE": 4}
type_groups = {}
for n in nodes:
    label = n.label
    if label not in type_groups:
        type_groups[label] = []
    type_groups[label].append(n)

# Position nodes
positions = {}
for label, group in type_groups.items():
    x_base = type_order.get(label, 2)
    n_count = len(group)
    for i, node in enumerate(group):
        y = (i - n_count / 2) * 1.5
        positions[node.id] = (x_base, y)

# Filters
st.sidebar.markdown("---")
st.sidebar.markdown("**Filters**")
show_types = st.sidebar.multiselect(
    "Node types",
    list(NODE_CONFIG.keys()),
    default=list(type_groups.keys()),
)

visible_node_ids = {n.id for n in nodes if n.label in show_types}

# Build figure
fig = go.Figure()

# Add edges
for edge in edges:
    if edge.source_id not in visible_node_ids or edge.target_id not in visible_node_ids:
        continue
    
    edge_key = f"{edge.source_id}|{edge.target_id}"
    is_disabled = edge_key in st.session_state.disabled_edges
    
    x0, y0 = positions.get(edge.source_id, (0, 0))
    x1, y1 = positions.get(edge.target_id, (0, 0))
    
    color = EDGE_COLORS.get(edge.predicate, "#475569")
    if is_disabled:
        color = "#1e293b"
    
    fig.add_trace(go.Scatter(
        x=[x0, x1, None],
        y=[y0, y1, None],
        mode="lines",
        line=dict(
            width=2 if not is_disabled else 1,
            color=color,
            dash="dash" if is_disabled else "solid",
        ),
        hoverinfo="text",
        text=f"{edge.source_id} --[{edge.predicate}]--> {edge.target_id}<br>Strength: {edge.evidence_strength:.3f}<br>Source: {edge.source}",
        showlegend=False,
        customdata=[edge_key],
    ))
    
    # Edge label at midpoint
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    fig.add_annotation(
        x=mx, y=my,
        text=edge.predicate,
        showarrow=False,
        font=dict(size=8, color="#94a3b8"),
        bgcolor="#0f172a",
        opacity=0.8,
    )

# Add nodes (one trace per type for legend)
for label, config in NODE_CONFIG.items():
    group = type_groups.get(label, [])
    if not group or label not in show_types:
        continue
    
    xs = [positions[n.id][0] for n in group]
    ys = [positions[n.id][1] for n in group]
    texts = [n.name for n in group]
    hovers = [
        f"<b>{n.name}</b><br>Type: {n.label}<br>ID: {n.id}<br>Meta: {json.dumps(n.meta, indent=2)[:200]}"
        for n in group
    ]
    ids = [n.id for n in group]
    
    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="markers+text",
        marker=dict(
            size=config["size"],
            color=config["color"],
            symbol=config["symbol"],
            line=dict(width=2, color="#e2e8f0"),
        ),
        text=texts,
        textposition="bottom center",
        textfont=dict(size=10, color="#e2e8f0"),
        hovertext=hovers,
        hoverinfo="text",
        name=f"{config['emoji']} {label}",
        customdata=ids,
    ))

fig.update_layout(
    plot_bgcolor="#0f172a",
    paper_bgcolor="#0f172a",
    font=dict(color="#e2e8f0"),
    height=500,
    margin=dict(l=20, r=20, t=20, b=20),
    legend=dict(
        bgcolor="#1e293b",
        bordercolor="#334155",
        borderwidth=1,
        font=dict(size=12),
    ),
    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    dragmode="pan",
)

# ─────────────────────────────────────────────
# Render graph with click event capture
# ─────────────────────────────────────────────
col_graph, col_panel = st.columns([2, 1])

with col_graph:
    click_data = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="graph_chart")
    
    if click_data and click_data.selection and click_data.selection.points:
        point = click_data.selection.points[0]
        curve_idx = point.get("curve_number", 0)
        point_idx = point.get("point_index", 0)
        
        # Figure out which trace/node was clicked
        trace = fig.data[curve_idx]
        if hasattr(trace, 'customdata') and trace.customdata is not None:
            if isinstance(trace.customdata, list) and point_idx < len(trace.customdata):
                clicked_id = trace.customdata[point_idx]
                if "|" in str(clicked_id):
                    # Edge click
                    st.session_state.selected_edge = clicked_id
                    st.session_state.selected_node = None
                else:
                    # Node click
                    st.session_state.selected_node = clicked_id
                    st.session_state.selected_edge = None

with col_panel:
    st.markdown("### Inspector")
    
    if st.session_state.selected_node:
        node_id = st.session_state.selected_node
        node = graph.nodes.get(node_id)
        if node:
            config = NODE_CONFIG.get(node.label, {"emoji": "?", "color": "#64748b"})
            st.markdown(f"#### {config['emoji']} {node.name}")
            st.markdown(f"**Type:** {node.label}")
            st.markdown(f"**ID:** `{node.id}`")
            
            # Count connected edges
            connected = [e for e in edges if e.source_id == node_id or e.target_id == node_id]
            st.markdown(f"**Connected edges:** {len(connected)}")
            
            # Show metadata
            if node.meta:
                with st.expander("Metadata"):
                    st.json(node.meta)
            
            # Count evidence
            ev_count = sum(
                1 for e in pkg.evidence_records
                if getattr(e, "target_uniprot", None) and
                node.meta.get("uniprot") == getattr(e, "target_uniprot", None)
            )
            if ev_count > 0:
                st.markdown(f"**Evidence records:** {ev_count}")
            
            # Show why this node is here
            st.markdown("---")
            st.markdown("#### Why is this node here?")
            for e in connected:
                direction = "outgoing" if e.source_id == node_id else "incoming"
                other = e.target_id if direction == "outgoing" else e.source_id
                st.markdown(f"- {direction}: `{e.predicate}` {'to' if direction == 'outgoing' else 'from'} **{other}** (strength: {e.evidence_strength:.3f})")
    
    elif st.session_state.selected_edge:
        parts = st.session_state.selected_edge.split("|")
        if len(parts) == 2:
            source_id, target_id = parts
            edge = None
            for e in edges:
                if e.source_id == source_id and e.target_id == target_id:
                    edge = e
                    break
            if edge:
                st.markdown(f"#### Edge: {edge.predicate}")
                st.markdown(f"**From:** {edge.source_id}")
                st.markdown(f"**To:** {edge.target_id}")
                st.markdown(f"**Strength:** {edge.evidence_strength:.3f}")
                st.markdown(f"**Source:** {edge.source}")
                st.markdown(f"**Data quality:** {edge.data_quality}")
                
                # Why is this relationship here?
                st.markdown("---")
                st.markdown("#### Why is this relationship here?")
                
                # Check how many paths use this edge
                drug_id = f"DRUG:{pkg.drug.name}"
                disease_id = f"DISEASE:{pkg.disease.name}"
                all_paths = list(graph.find_simple_paths(drug_id, disease_id))
                paths_using = sum(
                    1 for p in all_paths
                    if any(pe.source_id == source_id and pe.target_id == target_id for pe in p)
                )
                st.markdown(f"- Appears in **{paths_using}** of {len(all_paths)} mechanistic paths")
                st.markdown(f"- Source database: **{edge.source}**")
                st.markdown(f"- Provenance: {edge.provenance}")
                
                # Links
                if hasattr(edge, 'links') and edge.links:
                    st.markdown("**Source links:**")
                    for link in edge.links:
                        url = link.url if hasattr(link, 'url') else link.get('url', '')
                        label = link.display_label if hasattr(link, 'display_label') else link.get('display_label', 'Link')
                        st.markdown(f"- [{label}]({url})")
                
                # Challenge button
                st.markdown("---")
                edge_key = f"{source_id}|{target_id}"
                is_disabled = edge_key in st.session_state.disabled_edges
                if is_disabled:
                    if st.button("Re-enable this relationship"):
                        st.session_state.disabled_edges.discard(edge_key)
                        st.rerun()
                else:
                    if st.button("Challenge this relationship"):
                        st.session_state.disabled_edges.add(edge_key)
                        st.rerun()
    else:
        st.info("Click a node or edge to inspect it.")
    
    # Show disabled edges
    if st.session_state.disabled_edges:
        st.markdown("---")
        st.markdown("#### Disabled relationships")
        for ek in st.session_state.disabled_edges:
            parts = ek.split("|")
            st.markdown(f"- ~~{parts[0]} -> {parts[1]}~~")

# ─────────────────────────────────────────────
# Bottom panel: Evidence landscape
# ─────────────────────────────────────────────
st.markdown("---")
col_s, col_m, col_r, col_o = st.columns(4)
with col_s:
    st.metric("Support Score", f"{result.support_assessment.score:.3f}", delta=result.support_assessment.level)
with col_m:
    st.metric("Mechanistic Score", f"{result.mechanistic_assessment.score:.3f}", delta=result.mechanistic_assessment.level)
with col_r:
    st.metric("Risk Score", f"{result.risk_assessment.score:.3f}", delta=result.risk_assessment.level)
with col_o:
    st.metric("Opposition", f"{result.opposition_assessment.score:.3f}", delta=result.opposition_assessment.level)

st.markdown("---")
st.caption(f"Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges | Evidence: {len(pkg.evidence_records)} records | Trials: {len(pkg.clinical_trials)} | Claim citations: {len(result.audit_report.claim_citations)}")
