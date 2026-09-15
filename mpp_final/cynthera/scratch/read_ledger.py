import json

with open('backend/evaluation/post_clinicaltrials_50_fast_ledger.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

cases = data['cases']
print(f"Total cases: {len(cases)}")
print("Sample case TC-001:")
for k, v in cases[0].items():
    if k != 'trial_telemetry':
        print(f"  {k}: {v}")
