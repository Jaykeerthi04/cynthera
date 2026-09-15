import json
import re

with open('evaluation_outputs/100_case_final/results.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        cid = d.get('case_id')
        rule = d.get('decision_rule', '')
        m = re.search(r"Matched ChEMBL term: '([^']+)'", rule)
        if m:
            pass
        elif d.get('standard_gold') == 'SUPPORT':
            print(f"SUPPORT without matched term: {cid}: {d.get('drug')} -> {d.get('disease')}: rule={rule[:80]}")
