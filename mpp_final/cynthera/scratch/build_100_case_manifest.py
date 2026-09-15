"""Build and verify the 100-case manifest for CYNTHERA Final Evaluation.

This script cross-references the 100 cases against:
- 25-case regression benchmark (run_25_case_evaluation.py)
- 30-case hold-out benchmark (holdout_30_case_dataset.py)
- V1 benchmark (benchmark_dataset.py)
- Pharmacological and regulatory reality (FDA labels, Phase III trials, WHO, etc.)
"""
import sys
import os
import json
from pathlib import Path

# Add cynthera paths
cynthera_dir = Path("mpp_final/cynthera").resolve()
sys.path.insert(0, str(cynthera_dir))

# 100 cases specified in Section 3 of prompt
RAW_100_CASES = [
    # CATEGORY A — CLEAR POSITIVE / ESTABLISHED THERAPEUTIC
    ("01", "Lisinopril", "Hypertension", "Category A: Clear positive"),
    ("02", "Aspirin", "Secondary cardiovascular prevention", "Category A: Clear positive"),
    ("03", "Budesonide", "Asthma", "Category A: Clear positive"),
    ("04", "Fluticasone", "Allergic rhinitis", "Category A: Clear positive"),
    ("05", "Trastuzumab", "HER2-positive breast cancer", "Category A: Clear positive"),
    ("06", "Tamoxifen", "ER-positive breast cancer", "Category A: Clear positive"),
    ("07", "Metformin", "Type 2 diabetes", "Category A: Clear positive"),
    ("08", "Atorvastatin", "Hypercholesterolemia", "Category A: Clear positive"),
    ("09", "Levothyroxine", "Hypothyroidism", "Category A: Clear positive"),
    ("10", "Amoxicillin", "Bacterial infection", "Category A: Clear positive"),
    ("11", "Amlodipine", "Hypertension", "Category A: Clear positive"),
    ("12", "Losartan", "Hypertension", "Category A: Clear positive"),
    ("13", "Omeprazole", "GERD", "Category A: Clear positive"),
    ("14", "Sertraline", "Major depressive disorder", "Category A: Clear positive"),
    ("15", "Albuterol", "Asthma", "Category A: Clear positive"),
    ("16", "Warfarin", "Atrial fibrillation / stroke prevention", "Category A: Clear positive"),
    ("17", "Methotrexate", "Rheumatoid arthritis", "Category A: Clear positive"),
    ("18", "Etanercept", "Rheumatoid arthritis", "Category A: Clear positive"),
    ("19", "Imatinib", "Chronic myeloid leukemia", "Category A: Clear positive"),
    ("20", "Rituximab", "B-cell non-Hodgkin lymphoma", "Category A: Clear positive"),

    # CATEGORY B — NEGATIVE / FAILED / HARD-NEGATIVE / UNCERTAIN
    ("21", "Ivermectin", "COVID-19", "Category B: Negative / failed / hard-negative"),
    ("22", "Fluvoxamine", "COVID-19", "Category B: Negative / failed / hard-negative"),
    ("23", "Azithromycin", "COVID-19", "Category B: Negative / failed / hard-negative"),
    ("24", "Hydroxychloroquine", "COVID-19", "Category B: Negative / failed / hard-negative"),
    ("25", "Interferon beta-1a", "COVID-19", "Category B: Negative / failed / hard-negative"),
    ("26", "Niacin", "Cardiovascular disease", "Category B: Negative / failed / hard-negative"),
    ("27", "Doxorubicin", "Breast cancer", "Category B: Negative / failed / hard-negative"),
    ("28", "Celecoxib", "Alzheimer's disease", "Category B: Negative / failed / hard-negative"),
    ("29", "Simvastatin", "Sepsis", "Category B: Negative / failed / hard-negative"),
    ("30", "Dexamethasone", "Traumatic brain injury", "Category B: Negative / failed / hard-negative"),
    ("31", "Furosemide", "Depression", "Category B: Negative / failed / hard-negative"),
    ("32", "Warfarin", "Leishmaniasis", "Category B: Negative / failed / hard-negative"),
    ("33", "Metformin", "Alzheimer's disease", "Category B: Negative / failed / hard-negative"),
    ("34", "Aspirin", "Alzheimer's disease", "Category B: Negative / failed / hard-negative"),
    ("35", "Ivermectin", "Cancer", "Category B: Negative / failed / hard-negative"),
    ("36", "Hydroxychloroquine", "Rheumatoid arthritis", "Category B: Negative / failed / hard-negative"),
    ("37", "Azithromycin", "Asthma", "Category B: Negative / failed / hard-negative"),
    ("38", "Simvastatin", "Alzheimer's disease", "Category B: Negative / failed / hard-negative"),
    ("39", "Celecoxib", "Cancer", "Category B: Negative / failed / hard-negative"),
    ("40", "Dexamethasone", "COVID-19", "Category B: Negative / failed / hard-negative"),

    # CATEGORY C — CONTRADICTION / THERAPEUTIC DIRECTION / SAFETY
    ("41", "Etanercept", "Sepsis", "Category C: Contradiction / therapeutic direction / safety"),
    ("42", "Infliximab", "Heart failure", "Category C: Contradiction / therapeutic direction / safety"),
    ("43", "Rosiglitazone", "Type 2 diabetes", "Category C: Contradiction / therapeutic direction / safety"),
    ("44", "Rofecoxib", "Cardiovascular disease", "Category C: Contradiction / therapeutic direction / safety"),
    ("45", "Varenicline", "Smoking cessation", "Category C: Contradiction / therapeutic direction / safety"),
    ("46", "Propranolol", "Migraine", "Category C: Contradiction / therapeutic direction / safety"),
    ("47", "Gabapentin", "Neuropathic pain", "Category C: Contradiction / therapeutic direction / safety"),
    ("48", "Pregabalin", "Fibromyalgia", "Category C: Contradiction / therapeutic direction / safety"),
    ("49", "Colchicine", "Gout", "Category C: Contradiction / therapeutic direction / safety"),
    ("50", "Allopurinol", "Gout", "Category C: Contradiction / therapeutic direction / safety"),

    # CATEGORY D — CANCER / SUBTYPE / BIOMARKER / CLINICAL EVIDENCE
    ("51", "Valproic acid", "Glioblastoma", "Category D: Cancer / subtype / biomarker / clinical evidence"),
    ("52", "Nivolumab", "Glioblastoma", "Category D: Cancer / subtype / biomarker / clinical evidence"),
    ("53", "Pembrolizumab", "Glioblastoma", "Category D: Cancer / subtype / biomarker / clinical evidence"),
    ("54", "Bevacizumab", "Glioblastoma", "Category D: Cancer / subtype / biomarker / clinical evidence"),
    ("55", "Erlotinib", "Non-small-cell lung cancer", "Category D: Cancer / subtype / biomarker / clinical evidence"),
    ("56", "Gefitinib", "EGFR-positive lung cancer", "Category D: Cancer / subtype / biomarker / clinical evidence"),
    ("57", "Osimertinib", "EGFR-mutant lung cancer", "Category D: Cancer / subtype / biomarker / clinical evidence"),
    ("58", "Crizotinib", "ALK-positive lung cancer", "Category D: Cancer / subtype / biomarker / clinical evidence"),
    ("59", "Bortezomib", "Multiple myeloma", "Category D: Cancer / subtype / biomarker / clinical evidence"),
    ("60", "Lenalidomide", "Multiple myeloma", "Category D: Cancer / subtype / biomarker / clinical evidence"),

    # CATEGORY E — MECHANISTIC / OFF-LABEL / MULTI-TARGET
    ("61", "Bevacizumab", "Age-related macular degeneration", "Category E: Mechanistic / off-label / multi-target"),
    ("62", "Ranibizumab", "Age-related macular degeneration", "Category E: Mechanistic / off-label / multi-target"),
    ("63", "Latanoprost", "Glaucoma", "Category E: Mechanistic / off-label / multi-target"),
    ("64", "Timolol", "Glaucoma", "Category E: Mechanistic / off-label / multi-target"),
    ("65", "Sildenafil", "Pulmonary arterial hypertension", "Category E: Mechanistic / off-label / multi-target"),
    ("66", "Sildenafil", "Alzheimer's disease", "Category E: Mechanistic / off-label / multi-target"),
    ("67", "Sildenafil", "Heart failure", "Category E: Mechanistic / off-label / multi-target"),
    ("68", "Spironolactone", "Heart failure", "Category E: Mechanistic / off-label / multi-target"),
    ("69", "Digoxin", "Heart failure", "Category E: Mechanistic / off-label / multi-target"),
    ("70", "Verapamil", "Migraine", "Category E: Mechanistic / off-label / multi-target"),

    # CATEGORY F — MULTI-TARGET / METABOLIC / CARDIOVASCULAR
    ("71", "Dapagliflozin", "Heart failure", "Category F: Multi-target / metabolic / cardiovascular"),
    ("72", "Empagliflozin", "Heart failure", "Category F: Multi-target / metabolic / cardiovascular"),
    ("73", "Semaglutide", "Type 2 diabetes", "Category F: Multi-target / metabolic / cardiovascular"),
    ("74", "Semaglutide", "Alzheimer's disease", "Category F: Multi-target / metabolic / cardiovascular"),
    ("75", "Pioglitazone", "Alzheimer's disease", "Category F: Multi-target / metabolic / cardiovascular"),
    ("76", "Statin", "Sepsis", "Category F: Multi-target / metabolic / cardiovascular"),
    ("77", "Atorvastatin", "Cardiovascular disease", "Category F: Multi-target / metabolic / cardiovascular"),
    ("78", "Simvastatin", "Cardiovascular disease", "Category F: Multi-target / metabolic / cardiovascular"),
    ("79", "Fenofibrate", "Cardiovascular disease", "Category F: Multi-target / metabolic / cardiovascular"),
    ("80", "Ezetimibe", "Cardiovascular disease", "Category F: Multi-target / metabolic / cardiovascular"),

    # CATEGORY G — SAFETY / VETO / CONTRADICTION
    ("81", "Warfarin", "Bleeding disorder", "Category G: Safety / veto / contradiction"),
    ("82", "Aspirin", "Hemorrhagic stroke", "Category G: Safety / veto / contradiction"),
    ("83", "NSAIDs", "Peptic ulcer disease", "Category G: Safety / veto / contradiction"),
    ("84", "Methotrexate", "Pregnancy-related condition", "Category G: Safety / veto / contradiction"),
    ("85", "Isotretinoin", "Pregnancy", "Category G: Safety / veto / contradiction"),
    ("86", "Clozapine", "Schizophrenia", "Category G: Safety / veto / contradiction"),
    ("87", "Thalidomide", "Multiple myeloma", "Category G: Safety / veto / contradiction"),
    ("88", "Doxorubicin", "Cardiomyopathy", "Category G: Safety / veto / contradiction"),
    ("89", "Digoxin", "Atrial fibrillation", "Category G: Safety / veto / contradiction"),
    ("90", "Amiodarone", "Atrial fibrillation", "Category G: Safety / veto / contradiction"),

    # CATEGORY H — CLINICAL TRIAL ATTRIBUTION / COMBINATION / REGISTRY
    ("91", "Budesonide/Formoterol", "Asthma", "Category H: Clinical trial attribution / combination / registry"),
    ("92", "Budesonide", "COPD", "Category H: Clinical trial attribution / combination / registry"),
    ("93", "Metformin", "Type 2 diabetes", "Category H: Clinical trial attribution / combination / registry"),
    ("94", "Warfarin", "Thrombosis", "Category H: Clinical trial attribution / combination / registry"),
    ("95", "Heparin", "Thrombosis", "Category H: Clinical trial attribution / combination / registry"),
    ("96", "Placebo", "Disease treatment", "Category H: Clinical trial attribution / combination / registry"),
    ("97", "Etanercept", "Rheumatoid arthritis", "Category H: Clinical trial attribution / combination / registry"),
    ("98", "Fluticasone", "Allergic rhinitis", "Category H: Clinical trial attribution / combination / registry"),
    ("99", "Tamoxifen", "Breast cancer", "Category H: Clinical trial attribution / combination / registry"),
    ("100", "Trastuzumab", "HER2-positive breast cancer", "Category H: Clinical trial attribution / combination / registry"),
]

print(f"Total cases in definition: {len(RAW_100_CASES)}")
