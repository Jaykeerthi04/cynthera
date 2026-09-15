import asyncio
from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector

async def check():
    async with ClinicalTrialsConnector() as conn:
        for nct in ['NCT00676897', 'NCT00528580']:
            data = await conn._get(f"{conn.base_url}/studies/{nct}", params={"format": "json"})
            res = data.get("resultsSection", {})
            oms = res.get("outcomeMeasuresModule", {}).get("outcomeMeasures", [])
            print(f"=== {nct} ===")
            for om in oms:
                print(f"Type: {om.get('type')}, Title: {om.get('title')}, Desc: {om.get('description')}")
                print(f"  Analyses: {om.get('analyses')}")
                for grp in om.get('groups', []):
                    print(f"    Group: {grp.get('title')}")
                for c in om.get('classes', []):
                    for cat in c.get('categories', []):
                        for m in cat.get('measurements', []):
                            print(f"      Measurement: groupId={m.get('groupId')}, val={m.get('value')}")

if __name__ == "__main__":
    asyncio.run(check())
