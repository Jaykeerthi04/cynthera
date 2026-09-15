import sys
sys.path.insert(0, ".")
from backend.engineering.retrieval.disease_relation import classify_disease_relation, matches_for_approval_anchor

d1 = "Age-related macular degeneration"
terms = ["macular degeneration", "wet macular degeneration", "choroidal neovascularization", "age-related macular degeneration"]

for t in terms:
    rel = classify_disease_relation(d1, t)
    anchor = matches_for_approval_anchor(d1, t)
    print(f'Term: "{t}" -> rel={rel}, anchor={anchor}')
