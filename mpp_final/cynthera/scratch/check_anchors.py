import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.engineering.retrieval.disease_relation import matches_for_approval_anchor

with open('evaluation_outputs/100_case_final/results.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        if d['case_id'] in ('TC-001', 'TC-003', 'TC-062', 'TC-030', 'TC-023', 'TC-026', 'TC-052', 'TC-024', 'TC-022'):
            baseline_rule = str(d.get('decision_rule', ''))
            m_term = re.search(r"Matched ChEMBL term: '([^']+)'", baseline_rule)
            matched_term = m_term.group(1) if m_term else None
            is_anchor = matches_for_approval_anchor(d['disease'], matched_term) if matched_term else False
            print(f"{d['case_id']} {d['drug']} -> {d['disease']}")
            print(f"  matched_term: {matched_term} | is_anchor: {is_anchor}")
            print(f"  decision_rule: {baseline_rule[:120]}")
