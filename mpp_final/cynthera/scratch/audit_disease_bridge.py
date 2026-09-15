"""CYNTHERA — Phase 5.10.1 Disease-Bridge Audit.

Audits how disease names and MeSH IDs resolve to canonical MONDO/EFO IDs,
inspects ontology synonyms and cross-references (dbXRefs), and traces
disease-associated genes with complete provenance.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
import httpx

logging.basicConfig(level=logging.WARNING)

OT_GQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"

DISEASE_CASES = [
    {"name": "Polycystic Ovary Syndrome", "mesh_id": "D011085"},
    {"name": "Heart failure", "mesh_id": "D006333"},
    {"name": "Hypertension", "mesh_id": "D006973"},
    {"name": "Edema", "mesh_id": "D004487"},
    {"name": "Colorectal Cancer", "mesh_id": "D015179"},
    {"name": "Multiple Myeloma", "mesh_id": "D009101"},
    {"name": "Major Depressive Disorder", "mesh_id": "D003865"},
    {"name": "Asthma", "mesh_id": "D001249"},
    {"name": "Infantile Hemangioma", "mesh_id": "D006391"},
]

GQL_SEARCH = """
query SearchDisease($name: String!) {
  search(queryString: $name, entityNames: ["disease"], page: {index: 0, size: 5}) {
    hits {
      id
      name
      entity
      score
    }
  }
}
"""

GQL_DISEASE_DETAIL = """
query DiseaseDetail($efoId: String!) {
  disease(efoId: $efoId) {
    id
    name
    description
    synonyms {
      relation
      terms
    }
    dbXRefs
    parents {
      id
      name
    }
    children {
      id
      name
    }
    associatedTargets(page: {index: 0, size: 50}) {
      count
      rows {
        target {
          id
          approvedSymbol
        }
        score
      }
    }
  }
}
"""

async def query_ot(client: httpx.AsyncClient, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    resp = await client.post(OT_GQL_URL, json={"query": query, "variables": variables}, timeout=30.0)
    resp.raise_for_status()
    return resp.json().get("data", {})

async def audit_disease(client: httpx.AsyncClient, case: dict[str, str]):
    name = case["name"]
    mesh_id = case["mesh_id"]
    print("=" * 80)
    print(f"Disease: {name}")
    print("=" * 80)
    print(f"Input Name:       {name}")
    print(f"Input MeSH ID:    {mesh_id}")

    # Step 1: Search Open Targets for canonical MONDO/EFO
    search_data = await query_ot(client, GQL_SEARCH, {"name": name})
    hits = search_data.get("search", {}).get("hits", [])
    if not hits:
        print("  [ERROR] No Open Targets search hits found.")
        return

    canonical_hit = hits[0]
    canonical_id = canonical_hit["id"]
    canonical_name = canonical_hit["name"]
    print(f"Canonical OT ID:  {canonical_id} ({canonical_name})")

    # Step 2: Fetch details, synonyms, dbXRefs, parents, children, and associations
    detail_data = await query_ot(client, GQL_DISEASE_DETAIL, {"efoId": canonical_id})
    disease_obj = detail_data.get("disease")
    if not disease_obj:
        print(f"  [ERROR] Could not fetch details for {canonical_id}.")
        return

    # Extract dbXRefs
    db_xrefs = disease_obj.get("dbXRefs") or []
    related_ontology = [x for x in db_xrefs if any(x.startswith(p) for p in ("EFO:", "MONDO:", "DOID:", "MESH:", "HP:", "UMLS:"))]
    print(f"Related Ontology: {', '.join(related_ontology[:8]) if related_ontology else 'None'}")

    # Extract exact and related synonyms
    exact_syns = []
    related_syns = []
    for syn_group in (disease_obj.get("synonyms") or []):
        rel = syn_group.get("relation", "")
        terms = syn_group.get("terms") or []
        if rel == "hasExactSynonym":
            exact_syns.extend(terms)
        elif rel in ("hasRelatedSynonym", "hasNarrowSynonym"):
            related_syns.extend(terms)
    print(f"Exact Synonyms ({len(exact_syns)}):   {', '.join(exact_syns[:5]) if exact_syns else 'None'}")
    if related_syns:
        print(f"Related Synonyms ({len(related_syns)}): {', '.join(related_syns[:4])}")

    # Parents & Children
    parents = [(p["id"], p["name"]) for p in (disease_obj.get("parents") or [])]
    children = [(c["id"], c["name"]) for c in (disease_obj.get("children") or [])]
    print(f"Parent Classes ({len(parents)}):   {', '.join(f'{p[0]} ({p[1]})' for p in parents[:3]) if parents else 'None'}")
    print(f"Child Classes ({len(children)}):    {', '.join(f'{c[0]} ({c[1]})' for c in children[:3]) if children else 'None'}")

    # Associations for canonical ID
    assoc_rows = disease_obj.get("associatedTargets", {}).get("rows", [])
    total_target_count = disease_obj.get("associatedTargets", {}).get("count", 0)
    print(f"\nDisease-Gene Sources:")
    print(f"  OpenTargets:{canonical_id} (EXACT) = {total_target_count} total targets (retrieved top {len(assoc_rows)})")

    # Map genes with provenance
    genes_with_provenance = {}
    for r in assoc_rows:
        sym = r["target"]["approvedSymbol"]
        score = r["score"]
        genes_with_provenance[sym] = {
            "gene_symbol": sym,
            "gene_id": r["target"]["id"],
            "disease_id": canonical_id,
            "ontology_source": "MONDO/EFO",
            "evidence_source": "OpenTargets",
            "evidence_score": score,
            "scope": "EXACT",
            "provenance": f"Direct OpenTargets association for canonical disease {canonical_id} ({canonical_name})",
        }

    # Step 3: Check children for CHILD tier provenance
    if children:
        child_id, child_name = children[0]
        child_data = await query_ot(client, GQL_DISEASE_DETAIL, {"efoId": child_id})
        child_rows = (child_data.get("disease") or {}).get("associatedTargets", {}).get("rows", [])
        child_total = (child_data.get("disease") or {}).get("associatedTargets", {}).get("count", 0)
        print(f"  OpenTargets:{child_id} (CHILD: {child_name}) = {child_total} total targets (retrieved top {len(child_rows)})")
        for r in child_rows[:15]:
            sym = r["target"]["approvedSymbol"]
            if sym not in genes_with_provenance:
                genes_with_provenance[sym] = {
                    "gene_symbol": sym,
                    "gene_id": r["target"]["id"],
                    "disease_id": child_id,
                    "ontology_source": "MONDO/EFO",
                    "evidence_source": "OpenTargets",
                    "evidence_score": r["score"],
                    "scope": "CHILD",
                    "provenance": f"Child subtype association: {child_name} ({child_id})",
                }

    print(f"\nFinal Genes Set ({len(genes_with_provenance)} unique genes with provenance):")
    for i, (sym, pinfo) in enumerate(list(genes_with_provenance.items())[:8], 1):
        print(f"  {i}. {sym:<10} | score: {pinfo['evidence_score']:.4f} | scope: {pinfo['scope']:<7} | source: {pinfo['evidence_source']}:{pinfo['disease_id']}")
    print()

async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        for case in DISEASE_CASES:
            await audit_disease(client, case)

if __name__ == "__main__":
    asyncio.run(main())
