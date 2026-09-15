import sys
sys.path.insert(0, ".")
import asyncio
import re
from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector
from backend.engineering.retrieval.disease_relation import (
    classify_disease_relation,
    matches_for_approval_anchor,
    DiseaseRelation,
)

async def test():
    async with ChEMBLConnector() as conn:
        res = await conn.fetch_indications('CHEMBL1201825')
        mol = await conn.fetch_molecule_details('CHEMBL1201825')

    indications = res.get('indications', [])
    disease_name = 'Age-related macular degeneration'
    disease_variants = [disease_name]

    best_match_phase = 0
    best_match_term = ''
    best_match_confidence = 0.0

    _GENERIC_DISEASE_TOKENS = {
        'cancer', 'cancers', 'disease', 'diseases', 'disorder', 'disorders',
        'syndrome', 'syndromes', 'condition', 'conditions', 'neoplasm', 'neoplasms',
        'carcinoma', 'carcinomas', 'tumor', 'tumors', 'tumour', 'tumours',
        'malignant', 'benign', 'chronic', 'acute', 'primary', 'secondary',
        'advanced', 'metastatic', 'recurrent', 'refractory',
        'type', 'stage', 'grade', 'positive', 'negative',
    }

    for variant in disease_variants:
        query_tokens = set(re.sub(r'[^a-z0-9]', ' ', variant.lower()).split()) - {'the', 'a', 'an', 'of', 'and', 'or', 'for', 'in', 'to'}
        for ind in indications:
            efo_term = str(ind.get('efo_term') or '').lower()
            mesh_heading = str(ind.get('mesh_heading') or '').lower()
            max_phase = int(float(ind.get('max_phase_for_ind') or 0))

            for term in (efo_term, mesh_heading):
                if not term:
                    continue
                term_tokens = set(re.sub(r'[^a-z0-9]', ' ', term).split()) - {'the', 'a', 'an', 'of', 'and', 'or', 'for', 'in', 'to'}
                union = query_tokens | term_tokens
                if not union:
                    continue
                intersection = query_tokens & term_tokens
                specific_intersection = intersection - _GENERIC_DISEASE_TOKENS
                if not specific_intersection:
                    continue

                orig_rel = classify_disease_relation(disease_name, term)
                if orig_rel == DiseaseRelation.SIBLING_EXCLUDED:
                    continue

                is_anchor = matches_for_approval_anchor(disease_name, term)
                if not is_anchor:
                    continue

                sim = len(intersection) / len(union)
                q_clean = variant.lower().replace(' ', '')
                t_clean = term.replace(' ', '')
                if q_clean in t_clean or t_clean in q_clean:
                    sim = max(sim, 0.6)

                candidate_rank = (max_phase == 4, max_phase, sim)
                best_rank = (best_match_phase == 4, best_match_phase, best_match_confidence)
                if candidate_rank > best_rank:
                    best_match_confidence = sim
                    best_match_term = term
                    best_match_phase = max_phase

    print('AFTER FIX:')
    print('  best_match_phase:', best_match_phase)
    print('  best_match_term:', repr(best_match_term))
    print('  best_match_confidence:', best_match_confidence)
    print('  is_approved:', best_match_phase == 4)

asyncio.run(test())
