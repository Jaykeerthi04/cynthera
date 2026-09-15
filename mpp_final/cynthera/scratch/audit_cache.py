"""Audit script for Section 15: Cache invalidation and key structure.
"""
import json
import hashlib
import time
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from backend.infrastructure.cache.evaluation_cache import EvaluationCache

def test_cache_keys():
    print("=" * 80)
    print("SECTION 15: CACHE AUDIT")
    print("=" * 80)
    
    drug = "Niacin"
    disease = "Cardiovascular disease"
    policy = "STANDARD"
    rule_ver = "3.2"

    # Old key with v7.8
    old_id = {
        "version_namespace": "v7.8_reactome_hop5",
        "drug": drug.lower().strip(),
        "disease": disease.lower().strip(),
        "policy": policy.upper().strip(),
        "rule_set_version": rule_ver,
    }
    old_key = hashlib.sha256(json.dumps(old_id, sort_keys=True).encode("utf-8")).hexdigest()

    # New key with v7.9_clinicaltrials_safe_fix
    new_key = EvaluationCache._make_key(drug, disease, policy, rule_ver)

    print(f"Old Cache Key (v7.8): {old_key}")
    print(f"New Cache Key (v7.9): {new_key}")
    print(f"Keys are distinct: {old_key != new_key}")

    # Test cache get on new key
    cache = EvaluationCache()
    res = cache.get(drug, disease, policy, rule_ver)
    print(f"Cache lookup for ({drug}, {disease}) under new key: {res is not None} (Expect None on cold)")

if __name__ == "__main__":
    test_cache_keys()
