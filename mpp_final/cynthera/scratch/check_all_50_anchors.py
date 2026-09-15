import json
import re
from pathlib import Path
from backend.engineering.retrieval.disease_relation import matches_for_approval_anchor

with open('evaluation_outputs/100_case_final/results.jsonl', 'r', encoding='utf-8') as f:
    baseline_by_cid = {d['case_id']: d for d in (json.loads(line) for line in f if line.strip())}

with open('scratch/resolved_50_cases.json', 'r', encoding='utf-8') as f:
    cases = json.load(f)

for item in cases:
    cid = item['case_id']
    b = baseline_by_cid.get(cid, {})
    drug = item['drug']
    disease = item['disease']
    baseline_rule = str(b.get('decision_rule', ''))
    m_term = re.search(r"Matched ChEMBL term: '([^']+)'", baseline_rule)
    matched_term = m_term.group(1) if m_term else (b.get('matched_indication_term') or None)
    is_anchor = matches_for_approval_anchor(disease, matched_term) if matched_term else False
    if is_anchor:
        print(f"{cid}: {drug} -> {disease} is_anchor=True (term='{matched_term}')")
