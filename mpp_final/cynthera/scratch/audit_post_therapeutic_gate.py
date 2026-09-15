"""Read-only diagnostic for post-therapeutic-gate evidence representation."""
from __future__ import annotations

import json
import sqlite3
import asyncio

from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector


PAIRS = [
    ("Lisinopril", "Hypertension"),
    ("Aspirin", "Secondary prevention of cardiovascular disease"),
    ("Budesonide", "Asthma"),
    ("Fluticasone", "Allergic rhinitis"),
    ("Etanercept", "Rheumatoid arthritis"),
    ("Tamoxifen", "ER-positive breast cancer"),
    ("Trastuzumab", "HER2-positive breast cancer"),
    ("Metformin", "Pancreatic cancer"),
    ("Furosemide", "Depression"),
    ("Warfarin", "Leishmaniasis"),
    ("Pregabalin", "Breast cancer"),
    ("Azithromycin", "COVID-19"),
]


def load_packages() -> list[dict]:
    conn = sqlite3.connect("data/cynthera.db")
    rows = conn.execute(
        "SELECT sealed_at, data_json FROM retrieval_packages ORDER BY sealed_at DESC"
    ).fetchall()
    latest: dict[tuple[str, str], tuple[str, dict]] = {}
    for sealed_at, raw in rows:
        package = json.loads(raw)
        key = (package["drug"]["name"].lower(), package["disease"]["name"].lower())
        latest.setdefault(key, (sealed_at, package))

    report: list[dict] = []
    for drug, disease in PAIRS:
        hit = latest.get((drug.lower(), disease.lower()))
        if hit is None:
            report.append({"drug": drug, "disease": disease, "found": False})
            continue
        sealed_at, package = hit
        trials = package.get("clinical_trials", [])
        status_counts = {
            status: sum(1 for trial in trials if trial.get("status") == status)
            for status in sorted({trial.get("status") for trial in trials})
        }
        report.append(
            {
                "drug": drug,
                "disease": disease,
                "found": True,
                "sealed_at": sealed_at,
                "approval_signal": package.get("approval_signal"),
                "clinical_trial_retrieval_status": package.get("clinical_trial_retrieval_status"),
                "trials_by_status": status_counts,
                "opentargets_doe_count": len(package.get("opentargets_doe_evidence", [])),
                "datts_count": len(package.get("datts_evidence", [])),
                "drugmechdb_validated_count": sum(
                    1 for record in package.get("drugmechdb_evidence", [])
                    if record.get("is_curated_path_available")
                ),
                "literature_record_count": len(package.get("evidence_records", [])),
                "sources_failed": package.get("sources_failed", []),
            }
        )
    return report


async def inspect_chembl_indications() -> list[dict]:
    """Retrieve raw ChEMBL indication terms without invoking normalization."""
    conn = sqlite3.connect("data/cynthera.db")
    rows = conn.execute(
        "SELECT sealed_at, data_json FROM retrieval_packages ORDER BY sealed_at DESC"
    ).fetchall()
    latest: dict[tuple[str, str], dict] = {}
    for _, raw in rows:
        package = json.loads(raw)
        key = (package["drug"]["name"].lower(), package["disease"]["name"].lower())
        latest.setdefault(key, package)

    result: list[dict] = []
    async with ChEMBLConnector() as chembl:
        for drug, disease in PAIRS[:7]:
            package = latest[(drug.lower(), disease.lower())]
            chembl_id = next(
                item["value"]
                for item in package["drug"]["identifiers"]["identifiers"]
                if item["namespace"] == "chembl"
            )
            raw = await chembl._get(
                f"{chembl.base_url}/drug_indication.json",
                params={"molecule_chembl_id": chembl_id, "limit": 100, "format": "json"},
            )
            indications = raw.get("drug_indications", [])
            result.append(
                {
                    "drug": drug,
                    "disease": disease,
                    "chembl_id": chembl_id,
                    "indication_count": len(indications),
                    "approved_terms": [
                        {
                            "efo_term": row.get("efo_term"),
                            "mesh_heading": row.get("mesh_heading"),
                            "max_phase_for_ind": row.get("max_phase_for_ind"),
                        }
                        for row in indications
                        if float(row.get("max_phase_for_ind") or 0) == 4
                    ][:20],
                }
            )
    return result


if __name__ == "__main__":
    print(json.dumps({"packages": load_packages(), "raw_chembl": asyncio.run(inspect_chembl_indications())}, ensure_ascii=True, indent=2))
