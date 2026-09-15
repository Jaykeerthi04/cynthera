import json
from collections import Counter
from pathlib import Path

ledger_path = Path("backend/evaluation/post_clinicaltrials_50_fast_ledger.json")
with open(ledger_path, "r", encoding="utf-8") as f:
    ledger = json.load(f)

cases = ledger["cases"]
errs = [c for c in cases if c["prediction"] != c["standard_gold"]]

taxonomy_map = {
    "TC-002": {"primary": "F", "secondary": "A", "name": "Therapeutic direction", "note": "Secondary prevention lacks exact indication matching in ChEMBL or therapeutic trial anchor"},
    "TC-021": {"primary": "I", "secondary": "K", "name": "Evidence weighting / score saturation", "note": "Massive literature co-mentions inflate Support Score to 0.989, causing Rule 1b epistemic conflict with 0.770 opposition"},
    "TC-023": {"primary": "I", "secondary": "C", "name": "Evidence weighting / score saturation", "note": "Support Score saturation (0.986) with high-quality therapeutic flag overrides moderate opposition (0.319)"},
    "TC-025": {"primary": "L", "secondary": "I", "name": "Benchmark/evaluator artifact", "note": "Evaluator script omitted Rule 1c (Therapeutic Anchor Gate), allowing literature SS=0.961 to trigger Rule 1 PROMISING"},
    "TC-028": {"primary": "A", "secondary": "C", "name": "ClinicalTrials retrieval", "note": "ADAPT Alzheimer's prevention trial not retrieved or mapped from CT.gov search"},
    "TC-029": {"primary": "A", "secondary": "K", "name": "ClinicalTrials retrieval", "note": "Historic sepsis trials for simvastatin missing or not registered on CT.gov"},
    "TC-030": {"primary": "I", "secondary": "E", "name": "Evidence weighting / score saturation", "note": "Single CRASH trial termination gives Opp=0.319, which falls below Rule 2b threshold (0.45), defaulting to Rule 5 UNCERTAIN"},
    "TC-041": {"primary": "K", "secondary": "A", "name": "Literature retrieval", "note": "1990s sepsis failure trials published in literature/NEJM but absent from CT.gov registry"},
    "TC-042": {"primary": "K", "secondary": "A", "name": "Literature retrieval", "note": "ATTACH trial (2003) failure published in NEJM/literature, not indexed on CT.gov"},
    "TC-043": {"primary": "E", "secondary": "C", "name": "Statistical direction parsing", "note": "Secondary neutral trial (NCT00367055) with p>=0.05 parsed as COMPLETED_FAILURE, pushing Opp to 0.512 and triggering Rule 2b veto"},
    "TC-044": {"primary": "H", "secondary": "A", "name": "Safety/contraindication", "note": "APPROVe trial cardiovascular toxicity / stroke risk should be captured via safety/cardiotoxicity contraindication"},
    "TC-051": {"primary": "I", "secondary": "F", "name": "Evidence weighting / score saturation", "note": "Historical adjuvant trials in glioblastoma parsed as positive therapeutic anchor (SS=0.985)"},
    "TC-052": {"primary": "I", "secondary": "K", "name": "Evidence weighting / score saturation", "note": "Glioblastoma literature volume yields SS=0.986, creating Rule 1b epistemic conflict with Opp=0.700"},
    "TC-053": {"primary": "L", "secondary": "I", "name": "Benchmark/evaluator artifact", "note": "Evaluator script omitted Rule 1c, allowing literature SS=0.985 to trigger Rule 1 PROMISING"},
    "TC-056": {"primary": "F", "secondary": "G", "name": "Therapeutic direction", "note": "Directional contradiction / target polarity conflict triggers Rule 2b directional opposition veto"},
    "TC-057": {"primary": "D", "secondary": "F", "name": "Disease relation", "note": "EGFR-mutant lung cancer vs non-small cell lung cancer ChEMBL indication mapping mismatch"},
    "TC-058": {"primary": "H", "secondary": "F", "name": "Safety/contraindication", "note": "High Risk Score (0.763) / boxed warning triggers Rule 0 safety veto, overriding oncology indication"},
    "TC-066": {"primary": "A", "secondary": "K", "name": "ClinicalTrials retrieval", "note": "No definitive negative clinical trial found on CT.gov; primarily observational claims in literature"},
    "TC-067": {"primary": "B", "secondary": "E", "name": "ClinicalTrials parsing", "note": "RELAX trial (HFpEF) not parsed as failure outcome"},
    "TC-072": {"primary": "E", "secondary": "C", "name": "Statistical direction parsing", "note": "EMPACT-MI neutral secondary prevention trial (p=0.2061) parsed as COMPLETED_FAILURE, pushing Opp to 0.512 and triggering Rule 2b veto"},
    "TC-074": {"primary": "M", "secondary": "A", "name": "Other", "note": "EVOKE trial is currently active / ongoing; cannot be parsed as a completed failure"},
    "TC-079": {"primary": "D", "secondary": "F", "name": "Disease relation", "note": "Fenofibrate approved for hypertriglyceridemia, inappropriately matched to broad Cardiovascular Disease under Rule -1"},
    "TC-081": {"primary": "H", "secondary": "F", "name": "Safety/contraindication", "note": "Warfarin in bleeding disorders is an absolute contraindication, not an efficacy trial failure"},
    "TC-085": {"primary": "H", "secondary": "F", "name": "Safety/contraindication", "note": "Isotretinoin in pregnancy is a black-box teratogen / contraindication, not an efficacy trial failure"},
    "TC-088": {"primary": "H", "secondary": "F", "name": "Safety/contraindication", "note": "Doxorubicin in cardiomyopathy is a drug-induced cardiotoxicity / absolute contraindication, not an efficacy trial failure"},
}

primary_counts = Counter(v["primary"] for v in taxonomy_map.values())
taxonomy_names = {
    "A": "ClinicalTrials retrieval",
    "B": "ClinicalTrials parsing",
    "C": "ClinicalTrials attribution",
    "D": "Disease relation",
    "E": "Statistical direction parsing",
    "F": "Therapeutic direction",
    "G": "Mechanistic reasoning",
    "H": "Safety/contraindication",
    "I": "Evidence weighting / score saturation",
    "J": "Deduplication / independence",
    "K": "Literature retrieval",
    "L": "Benchmark/evaluator artifact",
    "M": "Other"
}

print("TAXONOMY DISTRIBUTION (Total Errors = 25):")
for cat in sorted(taxonomy_names.keys()):
    count = primary_counts.get(cat, 0)
    pct = (count / len(errs)) * 100
    print(f"  {cat}. {taxonomy_names[cat]:<40}: {count:>2} ({pct:>5.1f}%)")
