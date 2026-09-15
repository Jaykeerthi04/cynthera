import json
from pathlib import Path

cache_path = Path("data/ct_raw_cache/Dexamethasone_Traumatic_brain_injury.json")
if cache_path.exists():
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    print("Studies count:", len(data.get("studies", [])))
    for s in data.get("studies", []):
        protocol = s.get("protocolSection", {})
        ident = protocol.get("identificationModule", {})
        nct = ident.get("nctId")
        title = ident.get("briefTitle")
        status = protocol.get("statusModule", {})
        overall_status = status.get("overallStatus")
        why_stopped = status.get("whyStopped")
        design = protocol.get("designModule", {})
        outcomes = protocol.get("outcomesModule", {})
        results_sec = s.get("resultsSection", {})
        print(f"\nNCT: {nct}")
        print(f"Title: {title}")
        print(f"Status: {overall_status}, WhyStopped: {why_stopped}")
        if results_sec:
            print("Results section present!")
            om_module = results_sec.get("outcomeMeasuresModule", {})
            for om in om_module.get("outcomeMeasures", []):
                print("  OM Title:", om.get("title"))
                for group in om.get("groups", []):
                    print("    Group:", group.get("title"), group.get("description"))
                for anal in om.get("analyses", []):
                    print("    Analysis:", anal.get("paramType"), anal.get("paramValue"), anal.get("pValue"), anal.get("ciNumSides"))
else:
    print("No cache file found for Dexamethasone_Traumatic_brain_injury.json")
