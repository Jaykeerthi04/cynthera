"""Regression coverage for ChEMBL indication evidence normalization."""
from __future__ import annotations

import pytest

from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector
from backend.engineering.retrieval.pipeline import RetrievalPipeline


@pytest.mark.asyncio
async def test_decimal_phase_does_not_discard_disease_matched_approval(monkeypatch):
    """ChEMBL's string-formatted ``4.0`` remains a phase-four indication."""
    payload = {
        "drug_indications": [
            {
                "efo_id": "EFO:0000537",
                "efo_term": "hypertension",
                "mesh_id": "D006973",
                "mesh_heading": "Hypertension",
                "max_phase_for_ind": "4.0",
                "indication_refs": [{"ref_id": "daily-med-label"}],
            }
        ]
    }

    async def fake_get(self, url, params=None):
        return payload

    monkeypatch.setattr(ChEMBLConnector, "_get", fake_get)
    async with ChEMBLConnector() as connector:
        normalized = await connector.fetch_indications("CHEMBL419213")

    assert normalized["indications"] == [
        {
            "efo_id": "EFO:0000537",
            "efo_term": "hypertension",
            "mesh_id": "D006973",
            "mesh_heading": "hypertension",
            "max_phase_for_ind": 4,
            "indication_refs": [{"ref_id": "daily-med-label"}],
        }
    ]


@pytest.mark.asyncio
async def test_bad_indication_phase_does_not_drop_other_indications(monkeypatch):
    payload = {
        "drug_indications": [
            {"efo_term": "bad", "max_phase_for_ind": "not-a-number"},
            {"efo_term": "asthma", "max_phase_for_ind": "4.0"},
        ]
    }

    async def fake_get(self, url, params=None):
        return payload

    monkeypatch.setattr(ChEMBLConnector, "_get", fake_get)
    async with ChEMBLConnector() as connector:
        normalized = await connector.fetch_indications("CHEMBL1370")

    assert [row["max_phase_for_ind"] for row in normalized["indications"]] == [0, 4]


def test_normalized_phase_four_indication_reaches_pair_approval_signal():
    """The normalized ChEMBL record becomes a strict disease-matched signal."""
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    signal = pipeline._parse_indication_data(
        {
            "indications": [
                {
                    "efo_term": "hypertension",
                    "mesh_heading": "hypertension",
                    "max_phase_for_ind": 4,
                    "indication_refs": [{"ref_id": "daily-med-label"}],
                }
            ]
        },
        {"max_phase": 4},
        "Hypertension",
    )

    assert signal is not None
    assert signal.is_approved is True
    assert signal.matched_indication_term == "hypertension"
