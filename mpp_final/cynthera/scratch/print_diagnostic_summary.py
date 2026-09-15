import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("phase_5_16_10_case_diagnostic.json") as f:
    cases = json.load(f)

print(f"Total cases evaluated: {len(cases)}")
print("=" * 120)
for c in cases:
    print(f"[{c['case_id']}] {c['drug']} -> {c['disease']}")
    print(f"  Expected 3-Class: {c['expected_3class']} | Epistemic Expected: {c['epistemic_expected_class']}")
    print(f"  Prediction: {c['prediction']} | Recommendation: {c['recommendation']} | Rule: {c['rule_that_fired']}")
    print(f"  MS: {c['mechanistic_score']:.3f} ({c['mechanistic_direction']}) | SS: {c['support_score']:.3f} ({c['support_level']}) | Opp: {c['opposition_score']:.3f} ({c['opposition_level']}, groups={c['opposition_independent_groups']})")
    print(f"  Contradiction: {c['contradiction_state']} | Cache Hit: {c['evaluation_cache_hit']}")
    print(f"  All Negative Claims ({len(c['all_negative_claims'])}):")
    for cl in c['all_negative_claims']:
        print(f"    - src={cl['source']} id={cl['record_id']} pred={cl['predicate']} rel={cl['relevance']:.2f} qual={cl['quality']:.2f} wt={cl['weight']:.2f} grp={cl['independence_group']}")
    print(f"  Converted Trial Claims ({len(c['converted_trial_claims'])}):")
    for cl in c['converted_trial_claims']:
        print(f"    - nct={cl.get('nct_id')} status={cl.get('original_status')} why={cl.get('why_stopped')} pred={cl.get('mapped_predicate')}")
    print("-" * 120)
