import json
from pathlib import Path

requested = [
    ('Lisinopril', 'Hypertension'),
    ('Aspirin', 'Secondary cardiovascular prevention'),
    ('Budesonide', 'Asthma'),
    ('Fluticasone', 'Allergic rhinitis'),
    ('Trastuzumab', 'HER2-positive breast cancer'),
    ('Tamoxifen', 'ER-positive breast cancer'),
    ('Metformin', 'Type 2 diabetes'),
    ('Atorvastatin', 'Hypercholesterolemia'),
    ('Levothyroxine', 'Hypothyroidism'),
    ('Imatinib', 'Chronic myeloid leukemia'),
    ('Ivermectin', 'COVID-19'),
    ('Fluvoxamine', 'COVID-19'),
    ('Azithromycin', 'COVID-19'),
    ('Hydroxychloroquine', 'COVID-19'),
    ('Interferon beta-1a', 'COVID-19'),
    ('Niacin', 'Cardiovascular disease'),
    ('Doxorubicin', 'Breast cancer'),
    ('Celecoxib', 'Alzheimer\'s disease'),
    ('Simvastatin', 'Sepsis'),
    ('Dexamethasone', 'Traumatic brain injury'),
    ('Etanercept', 'Sepsis'),
    ('Infliximab', 'Heart failure'),
    ('Rosiglitazone', 'Type 2 diabetes'),
    ('Rofecoxib', 'Cardiovascular disease'),
    ('Propranolol', 'Migraine'),
    ('Gabapentin', 'Neuropathic pain'),
    ('Valproic acid', 'Glioblastoma'),
    ('Nivolumab', 'Glioblastoma'),
    ('Pembrolizumab', 'Glioblastoma'),
    ('Gefitinib', 'NSCLC'),
    ('Osimertinib', 'EGFR-mutant lung cancer'),
    ('Crizotinib', 'ALK-positive lung cancer'),
    ('Bevacizumab', 'AMD'),
    ('Ranibizumab', 'AMD'),
    ('Latanoprost', 'Glaucoma'),
    ('Sildenafil', 'Alzheimer\'s disease'),
    ('Sildenafil', 'Heart failure'),
    ('Verapamil', 'Migraine'),
    ('Dapagliflozin', 'Heart failure'),
    ('Empagliflozin', 'Heart failure'),
    ('Semaglutide', 'Type 2 diabetes'),
    ('Semaglutide', 'Alzheimer\'s disease'),
    ('Pioglitazone', 'Alzheimer\'s disease'),
    ('Fenofibrate', 'Cardiovascular disease'),
    ('Warfarin', 'Bleeding disorder'),
    ('Isotretinoin', 'Pregnancy'),
    ('Doxorubicin', 'Cardiomyopathy'),
    ('Budesonide/Formoterol', 'Asthma'),
    ('Metformin', 'Type 2 diabetes'),
    ('Tamoxifen', 'Breast cancer')
]

with open('scratch/manifest_100_cases.json', encoding='utf-8') as f:
    manifest = json.load(f)

# Explicit mapping overrides for slight naming variations
OVERRIDE_MAPPING = {
    ('Gefitinib', 'NSCLC'): 'TC-056',
    ('Bevacizumab', 'AMD'): 'TC-061',
    ('Ranibizumab', 'AMD'): 'TC-062',
}

manifest_by_id = {m['case_id']: m for m in manifest}

print(f'Total manifest items: {len(manifest)}')
seen_cids = set()
matched_cases = []

for idx, (drug, disease) in enumerate(requested, 1):
    selected = None
    if (drug, disease) in OVERRIDE_MAPPING:
        selected = manifest_by_id[OVERRIDE_MAPPING[(drug, disease)]]
        seen_cids.add(selected['case_id'])
    else:
        exact = [m for m in manifest if m['drug'].lower().strip() == drug.lower().strip() and m['disease'].lower().strip() == disease.lower().strip()]
        if not exact:
            exact = [m for m in manifest if m['drug'].lower().strip() == drug.lower().strip() and (disease.lower() in m['disease'].lower() or m['disease'].lower() in disease.lower())]
        for cand in exact:
            if cand['case_id'] not in seen_cids:
                selected = cand
                seen_cids.add(cand['case_id'])
                break
        if not selected and exact:
            selected = exact[0]
            
    matched_cases.append((idx, drug, disease, selected))
    cid = selected['case_id'] if selected else 'NOT_FOUND'
    m_drug = selected['drug'] if selected else ''
    m_dis = selected['disease'] if selected else ''
    std = selected['standard_gold'] if selected else 'N/A'
    epi = selected['epistemic_gold'] if selected else 'N/A'
    print(f'{idx:02d}: {drug} -> {disease} => {cid} ({m_drug} -> {m_dis}) [std={std}, epi={epi}]')

with open('scratch/resolved_50_cases.json', 'w', encoding='utf-8') as f:
    json.dump([c[3] for c in matched_cases], f, indent=2)

