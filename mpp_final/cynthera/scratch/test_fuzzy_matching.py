from backend.engineering.retrieval.pipeline import RetrievalPipeline

pipeline = RetrievalPipeline()

# Test 1: Metformin -> Pancreatic cancer (indications include liver cancer max_phase=4)
metformin_inds = {
    "indications": [
        {"efo_term": "liver cancer", "mesh_heading": "liver neoplasms", "max_phase_for_ind": 4},
        {"efo_term": "type 2 diabetes mellitus", "mesh_heading": "diabetes mellitus, type 2", "max_phase_for_ind": 4},
    ]
}
metformin_mol = {"pref_name": "Metformin", "max_phase": 4}
sig1 = pipeline._parse_indication_data(metformin_inds, metformin_mol, "Pancreatic cancer")
print("Metformin -> Pancreatic cancer:", sig1.is_approved, sig1.max_phase, sig1.matched_indication_term, sig1.match_confidence)

# Test 2: Tamsulosin -> Liver cancer (indications include prostate cancer max_phase=4)
tamsulosin_inds = {
    "indications": [
        {"efo_term": "prostate cancer", "mesh_heading": "prostatic neoplasms", "max_phase_for_ind": 4},
        {"efo_term": "benign prostatic hyperplasia", "mesh_heading": "prostatic hyperplasia", "max_phase_for_ind": 4},
    ]
}
tamsulosin_mol = {"pref_name": "Tamsulosin", "max_phase": 4}
sig2 = pipeline._parse_indication_data(tamsulosin_inds, tamsulosin_mol, "Liver cancer")
print("Tamsulosin -> Liver cancer:", sig2.is_approved, sig2.max_phase, sig2.matched_indication_term, sig2.match_confidence)

# Test 3: Tamoxifen -> ER-positive breast cancer (indications include breast cancer max_phase=4)
tamoxifen_inds = {
    "indications": [
        {"efo_term": "breast cancer", "mesh_heading": "breast neoplasms", "max_phase_for_ind": 4},
    ]
}
tamoxifen_mol = {"pref_name": "Tamoxifen", "max_phase": 4}
sig3 = pipeline._parse_indication_data(tamoxifen_inds, tamoxifen_mol, "ER-positive breast cancer")
print("Tamoxifen -> ER-positive breast cancer:", sig3.is_approved, sig3.max_phase, sig3.matched_indication_term, sig3.match_confidence)

# Test 4: Trastuzumab -> HER2-positive breast cancer (indications include breast cancer max_phase=4)
sig4 = pipeline._parse_indication_data(tamoxifen_inds, tamoxifen_mol, "HER2-positive breast cancer")
print("Trastuzumab -> HER2-positive breast cancer:", sig4.is_approved, sig4.max_phase, sig4.matched_indication_term, sig4.match_confidence)

# Test 5: Colchicine -> Colorectal cancer (indications include prostate cancer max_phase=2, gout max_phase=4)
colchicine_inds = {
    "indications": [
        {"efo_term": "gout", "mesh_heading": "gout", "max_phase_for_ind": 4},
        {"efo_term": "prostate cancer", "mesh_heading": "prostatic neoplasms", "max_phase_for_ind": 2},
    ]
}
colchicine_mol = {"pref_name": "Colchicine", "max_phase": 4}
sig5 = pipeline._parse_indication_data(colchicine_inds, colchicine_mol, "Colorectal cancer")
print("Colchicine -> Colorectal cancer:", sig5.is_approved, sig5.max_phase, sig5.matched_indication_term, sig5.match_confidence)
