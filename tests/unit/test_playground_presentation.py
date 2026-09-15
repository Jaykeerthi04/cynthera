from types import SimpleNamespace

from frontend.playground_view import (
    _get_or_compute_layout,
    _playground_summary,
    _presentation_gaps,
    _short_label,
)


def graph_data(**kwargs):
    defaults = dict(
        hypothesis_id="h1",
        nodes=[],
        edges=[],
        evidence=[],
        clinical_trials=[],
        contradictions=[],
        candidate_mechanisms=[],
        claim_citations={},
        evidence_gaps=[],
        landscape=SimpleNamespace(supporting_count=0),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def node(node_id, label, name):
    return SimpleNamespace(id=node_id, label=label, name=name)


def test_summary_distinguishes_total_evidence_from_mapped_supporting():
    data = graph_data(
        evidence=[1, 2, 3],
        clinical_trials=[1, 2],
        contradictions=[1],
        candidate_mechanisms=[1, 2],
        claim_citations={"claim-1": ["e-1"], "claim-2": ["e-2"]},
        landscape=SimpleNamespace(supporting_count=1),
    )

    assert _playground_summary(data) == {
        "mechanisms": 2,
        "evidence": 3,
        "claims": 2,
        "trials": 2,
        "contradictions": 1,
        "mapped_supporting": 1,
    }


def test_presentation_gaps_surfaces_existing_result_diagnostics():
    data = graph_data(
        evidence_gaps=[
            SimpleNamespace(status="FOUND", label="Literature evidence"),
            SimpleNamespace(status="MISSING", label="Missing mechanistic bridge"),
        ]
    )
    result = SimpleNamespace(data_gaps=["No approved therapeutic indication", "Missing mechanistic bridge"])

    assert _presentation_gaps(data, result) == [
        "Missing mechanistic bridge",
        "No approved therapeutic indication",
    ]


def test_layout_places_drug_and_disease_at_opposite_sides():
    data = graph_data(
        hypothesis_id="layout-test",
        nodes=[
            node("DRUG:d", "DRUG", "Drug"),
            node("TARGET:t", "TARGET", "Target"),
            node("PATHWAY:p", "PATHWAY", "Pathway"),
            node("GENE:g", "GENE", "Gene"),
            node("DISEASE:x", "DISEASE", "Disease"),
        ],
    )
    # Avoid Streamlit cache/session state in this pure layout regression.
    import frontend.playground_view as view
    view.st.session_state.pop("layout_layout-test", None)
    positions = _get_or_compute_layout(data)

    assert positions["DRUG:d"][0] < positions["TARGET:t"][0]
    assert positions["TARGET:t"][0] < positions["PATHWAY:p"][0]
    assert positions["PATHWAY:p"][0] < positions["GENE:g"][0]
    assert positions["GENE:g"][0] < positions["DISEASE:x"][0]


def test_long_labels_are_abbreviated_for_dense_graphs():
    label = "A very long biological relationship label"
    assert _short_label(label) == "A very long biolo…"
    assert _short_label(label) != label
