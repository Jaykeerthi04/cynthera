import json
import sys

# Load 30-case holdout
r30 = json.load(open('evaluation_outputs/30_case_holdout/results.json', 'r', encoding='utf-8'))
r30_by_pair = {(c['drug'].lower(), c['disease'].lower()): c for c in r30}

# Load 25-case freeze
r25 = json.load(open('evaluation_outputs/25_case_freeze_v3_2/results.json', 'r', encoding='utf-8'))
r25_by_pair = {(c['drug'].lower(), c['disease'].lower()): c for c in r25}

target_cases = [
    # Rule -1 / matched-pair cases
    ("niacin_cvd", "Niacin", "Cardiovascular disease"),
    ("metformin_t2d", "Metformin", "Type 2 diabetes mellitus"),
    # Existing regression cases
    ("lisinopril_hypertension", "Lisinopril", "Hypertension"),
    ("adalimumab_crohn", "Adalimumab", "Crohn disease"),
    ("omeprazole_gerd", "Omeprazole", "Gastroesophageal reflux disease"),
    ("rituximab_nhl", "Rituximab", "Non-Hodgkin lymphoma"),
    ("insulin_glargine_t1d", "Insulin glargine", "Type 1 diabetes mellitus"),
    ("sertraline_mdd", "Sertraline", "Major depressive disorder"),
    ("methotrexate_ra", "Methotrexate", "Rheumatoid arthritis"),
    # Separate diagnostic cases
    ("dexamethasone_tbi", "Dexamethasone", "Traumatic brain injury"),
    ("doxorubicin_breast", "Doxorubicin", "Breast cancer"),
]

output_data = {}
for key, drug, disease in target_cases:
    pair = (drug.lower(), disease.lower())
    c = r30_by_pair.get(pair) or r25_by_pair.get(pair)
    if c:
        gate = c.get('decision_gate', '')
        if not gate and c.get('recommendation_reasons'):
            gate = c['recommendation_reasons'][0]
        output_data[key] = {
            "drug": drug,
            "disease": disease,
            "recommendation": c.get('recommendation'),
            "prediction": c.get('prediction'),
            "support_score": c.get('support_score'),
            "mechanistic_score": c.get('mechanistic_score'),
            "risk_score": c.get('risk_score'),
            "opposition_score": c.get('opposition_score'),
            "opposition_level": c.get('opposition_level'),
            "decision_gate": gate[:120] if gate else "N/A",
            "source_benchmark": "30_case_holdout" if pair in r30_by_pair else "25_case_freeze_v3_2"
        }
        print(f"{key}: {drug} -> {disease} | Rec: {output_data[key]['recommendation']} | SS: {output_data[key]['support_score']} | MS: {output_data[key]['mechanistic_score']} | RS: {output_data[key]['risk_score']} | Opp: {output_data[key]['opposition_score']} ({output_data[key]['opposition_level']}) | Gate: {output_data[key]['decision_gate'][:60]}")
    else:
        print(f"MISSING: {drug} -> {disease}")

with open(r'C:\Users\win10\.gemini\antigravity-ide\brain\338359ef-11f5-4696-8f5a-aa4b94f640c7\scratch\baseline_11_cases.json', 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=2)
