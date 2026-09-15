import sys
sys.path.insert(0, ".")
import json
import re
from pathlib import Path
from backend.engineering.retrieval.disease_relation import matches_for_approval_anchor
from backend.reasoning.orchestrator.decision_rules import apply_decision_rules
from backend.reasoning.opposition.therapeutic_opposition_assessor import TherapeuticOppositionAssessor, trial_to_negative_claim
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease

b = None
with open('evaluation_outputs/100_case_final/results.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        if d.get('case_id') == 'TC-062':
            b = d
            break

print('Baseline decision_rule:', repr(b.get('decision_rule')))
baseline_rule = str(b.get('decision_rule', ''))
m_term = re.search(r"Matched ChEMBL term: '([^']+)'", baseline_rule)
matched_term = m_term.group(1) if m_term else None
print('Extracted matched_term from baseline_rule:', repr(matched_term))

drug = 'Ranibizumab'
disease = 'Age-related macular degeneration'
cache_file = Path('data/ct_raw_cache/Ranibizumab_Age_related_macular_degeneration.json')
pipeline = RetrievalPipeline()
assessor = TherapeuticOppositionAssessor()
claims = []
if cache_file.exists():
    raw_data = json.loads(cache_file.read_text(encoding='utf-8'))
    parsed = pipeline._parse_trials_data(raw_data, Drug(name=drug, identifiers={'chembl': 'X'}), Disease(name=disease, identifiers={'mesh': 'Y'}))
    for t in parsed:
        c = trial_to_negative_claim(t, drug, disease)
        if c is not None:
            claims.append(c)

opp_assess = assessor.assess(claims, drug, disease)
print('Opp score:', opp_assess.score, 'level:', opp_assess.level, 'groups:', opp_assess.independent_group_count, 'qualified:', len(opp_assess.qualified_claims))

# Fast evaluator logic as written in run_50_case_post_clinicaltrials_fast.py:
is_anchor = matches_for_approval_anchor(disease, matched_term) if matched_term else False
print('is_anchor in fast evaluator:', is_anchor)

decision = apply_decision_rules(
    is_approved=is_anchor,
    matched_chembl_term=matched_term,
    support_score=float(b.get('support_score', 0.0)),
    mechanistic_score=float(b.get('mechanistic_score', 0.0)),
    risk_score=float(b.get('risk_score', 0.0)),
    opp_assessment=opp_assess,
)
print('Fast evaluator status:', decision.status, 'deciding_rule:', decision.deciding_rule)
