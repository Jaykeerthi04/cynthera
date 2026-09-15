import urllib.request
import json

ncts = ["NCT04885530", "NCT04510194", "NCT04727424"]

for nct in ncts:
    print(f"\n{'='*70}\nINSPECTING STUDY: {nct}\n{'='*70}")
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error fetching {nct}: {e}")
        continue
        
    protocol = data.get("protocolSection", {})
    ident = protocol.get("identificationModule", {})
    status_mod = protocol.get("statusModule", {})
    design_mod = protocol.get("designModule", {})
    arms_mod = protocol.get("armsInterventionsModule", {})
    outcomes_mod = protocol.get("outcomesModule", {})
    results_sec = data.get("resultsSection", {})
    
    print(f"Brief Title: {ident.get('briefTitle')}")
    print(f"Overall Status: {status_mod.get('overallStatus')}")
    print(f"Why Stopped: {status_mod.get('whyStopped')}")
    print(f"Has Results: {data.get('hasResults')}")
    
    # Design
    design_info = design_mod.get("designInfo", {})
    print(f"Study Type: {design_mod.get('studyType')}")
    print(f"Allocation: {design_info.get('allocation')}")
    print(f"Intervention Model: {design_info.get('interventionModel')}")
    
    # Arms
    print("\nArms & Interventions:")
    for arm in arms_mod.get("armGroups", []):
        print(f"  Arm: '{arm.get('label')}' | Type: {arm.get('type')} | Interventions: {arm.get('interventionNames')}")
        
    # Primary outcomes
    print("\nPrimary Outcomes:")
    for po in outcomes_mod.get("primaryOutcomes", []):
        print(f"  Measure: {po.get('measure')}")
        print(f"  TimeFrame: {po.get('timeFrame')}")
        print(f"  Description: {po.get('description', '')[:200]}")
        
    # Results Section
    if results_sec:
        print(f"\nresultsSection is PRESENT! Keys: {list(results_sec.keys())}")
        outcome_measures = results_sec.get("outcomeMeasuresModule", {}).get("outcomeMeasures", [])
        print(f"Number of outcome measures with results: {len(outcome_measures)}")
        for om in outcome_measures[:3]:
            print(f"  Result Outcome: {om.get('title')}")
            for group in om.get("groups", []):
                print(f"    Group: {group.get('title')}")
            for d in om.get("denoms", []):
                print(f"    Denom units: {d.get('units')}")
            analyses = om.get("analyses", [])
            print(f"    Statistical Analyses count: {len(analyses)}")
            for an in analyses:
                print(f"      P-value: {an.get('pValue')}, Param: {an.get('paramType')} = {an.get('paramValue')}, CI: {an.get('ciPct')}% [{an.get('ciLowerLimit')}, {an.get('ciUpperLimit')}]")
    else:
        print(f"\nresultsSection is NOT PRESENT (None or empty)")
