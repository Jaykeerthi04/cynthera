import json

ledger = json.load(open('backend/evaluation/post_clinicaltrials_50_fast_ledger.json', encoding='utf-8'))
case = [c for c in ledger['cases'] if c['case_id'] == 'TC-082']
if not case:
    # check in controls
    case = [c for c in ledger['controls'] if c['case_id'] == 'TC-082']

c = case[0]
print("Case:", c['case_id'], c['drug'], '->', c['disease'])
print("Gold:", c['standard_gold'], "Pred:", c['prediction'], "Rec:", c['recommendation'])
print("Rule:", c['decision_rule'])
print("Approval Anchor:", c['approval_anchor'])
print("SS:", c['support_score'], "MS:", c['mechanistic_score'], "RS:", c['risk_score'])
print("Opp:", c['opposition_score'], c['opposition_level'])
print("Trials retrieved:", c['clinical_trials_retrieved'], "Parsed:", c['clinical_trials_parsed'])
print("Safety veto:", c['safety_veto'])
