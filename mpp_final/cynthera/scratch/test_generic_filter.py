import re

_GENERIC_DISEASE_TOKENS = {
    "cancer", "cancers", "disease", "diseases", "disorder", "disorders",
    "syndrome", "syndromes", "condition", "conditions", "neoplasm", "neoplasms",
    "carcinoma", "carcinomas", "tumor", "tumors", "tumour", "tumours",
}

STOP_WORDS = {"the", "a", "an", "of", "and", "or", "for", "in", "to"}

def check_match(variant, term):
    query_tokens = set(re.sub(r"[^a-z0-9]", " ", variant.lower()).split()) - STOP_WORDS
    term_tokens = set(re.sub(r"[^a-z0-9]", " ", term.lower()).split()) - STOP_WORDS
    
    union = query_tokens | term_tokens
    if not union:
        return 0.0
    intersection = query_tokens & term_tokens
    
    # Check specific overlap
    specific_intersection = intersection - _GENERIC_DISEASE_TOKENS
    has_specific_overlap = len(specific_intersection) > 0
    has_meaningful_generic_only = len(intersection) >= 2
    
    sim = len(intersection) / len(union)
    
    # Substring containment boost
    q_clean = variant.lower().replace(" ", "")
    t_clean = term.lower().replace(" ", "")
    if (q_clean in t_clean or t_clean in q_clean) and (has_specific_overlap or has_meaningful_generic_only):
        sim = max(sim, 0.6)
    elif not has_specific_overlap and not has_meaningful_generic_only:
        sim = 0.0
        
    return sim

pairs = [
    ("Pancreatic cancer", "liver cancer"),
    ("Liver cancer", "prostate cancer"),
    ("Colorectal cancer", "prostate cancer"),
    ("ER-positive breast cancer", "breast cancer"),
    ("HER2-positive breast cancer", "breast cancer"),
    ("breast cancer", "breast cancer"),
    ("allergic rhinitis", "allergic rhinitis"),
    ("Secondary prevention of cardiovascular disease", "myocardial infarction"),
    ("cardiovascular disease", "myocardial infarction"), # note: composite maps "cardiovascular disease" to "myocardial infarction"
    ("myocardial infarction", "myocardial infarction"),
    ("Hypertension", "hypertension"),
    ("Asthma", "asthma"),
    ("Rheumatoid arthritis", "rheumatoid arthritis"),
]

for v, t in pairs:
    sim = check_match(v, t)
    print(f"'{v}' vs '{t}' -> sim={sim:.4f}")
