import json
import re
import os
import sys
sys.path.insert(0, os.path.abspath("."))
from backend.engineering.retrieval.disease_relation import matches_for_approval_anchor, classify_disease_relation

with open('scratch/resolved_50_cases.json', encoding='utf-8') as f:
    cases = json.load(f)

results_by_cid = {}
with open('evaluation_outputs/100_case_final/results.jsonl', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        results_by_cid[d['case_id']] = d

for c in cases:
    cid = c['case_id']
    b = results_by_cid.get(cid, {})
    rule = b.get('decision_rule', '')
    m = re.search(r"Matched ChEMBL term: '([^']+)'", rule)
    term = m.group(1) if m else None
    if term:
        rel = classify_disease_relation(c['disease'], term)
        anchor = matches_for_approval_anchor(c['disease'], term)
        print(f"{cid} {c['drug']} -> {c['disease']} | Term: '{term}' | Rel: {rel.value} | Anchor: {anchor}")
