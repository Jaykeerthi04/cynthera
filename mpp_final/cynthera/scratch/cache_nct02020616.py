import asyncio
import httpx
import json
from pathlib import Path

async def main():
    cache_path = Path("data/ct_raw_cache/nct02020616.json")
    if not cache_path.exists():
        headers = {"Accept": "application/json"}
        async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
            r = await client.get("https://clinicaltrials.gov/api/v2/studies/NCT02020616")
            if r.status_code == 200:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(r.json(), f)
                print("Cached NCT02020616 successfully.")

if __name__ == "__main__":
    asyncio.run(main())
