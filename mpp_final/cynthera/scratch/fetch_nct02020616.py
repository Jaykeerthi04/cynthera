import asyncio
import httpx

async def main():
    headers = {"Accept": "application/json"}
    async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
        r = await client.get("https://clinicaltrials.gov/api/v2/studies/NCT02020616")
        print("Status:", r.status_code)
        if r.status_code == 200:
            study = r.json()
            protocol = study.get("protocolSection", {})
            title = protocol.get("identificationModule", {}).get("briefTitle")
            conds = protocol.get("conditionsModule", {}).get("conditions")
            interventions = protocol.get("armsInterventionsModule", {}).get("interventions", [])
            print("Title:", title)
            print("Conditions:", conds)
            print("Interventions:", [i.get("name") for i in interventions])

if __name__ == "__main__":
    asyncio.run(main())
