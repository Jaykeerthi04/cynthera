import asyncio
from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease

async def check():
    async with ClinicalTrialsConnector() as conn:
        data = await conn.fetch("Budesonide", "Asthma", max_results=20)
        pipeline = RetrievalPipeline(db_path=":memory:")
        drug = Drug(name="Budesonide", identifiers={"chembl": "CHEMBL123"})
        disease = Disease(name="Asthma", identifiers={"mesh": "D001249"})
        trials = pipeline._parse_trials_data(data, drug, disease)
        print(f"Total trials: {len(trials)}")
        for t in trials:
            if t.is_negative_efficacy or t.status.value in ("COMPLETED_FAILURE", "TERMINATED_LACK_OF_EFFICACY", "TERMINATED_SAFETY"):
                print(f"  {t.nct_id}: status={t.status.value}, is_neg={t.is_negative_efficacy}, reason={t.negative_efficacy_reason}")
                for om in t.outcome_measures:
                    if om.get("direction") == "NEGATIVE":
                        print(f"    NEGATIVE om: {om.get('type')}, {om.get('title')}: {om.get('reason')}")

if __name__ == "__main__":
    asyncio.run(check())
