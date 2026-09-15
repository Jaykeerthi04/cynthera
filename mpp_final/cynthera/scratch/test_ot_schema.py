import httpx

query = """
query DiseaseOntology($efoId: String!) {
  disease(efoId: $efoId) {
    id
    name
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
    associatedTargets(page: {index: 0, size: 5}) {
      count
      rows {
        target {
          approvedSymbol
        }
        score
      }
    }
  }
}
"""

cases = [
    ("Heart failure", "MONDO_0005252"),
    ("Polycystic Ovary Syndrome", "MONDO_0008487"),
    ("Hypertension", "MONDO_0005044"),
    ("Major Depressive Disorder", "MONDO_0002009"),
]

for name, efo_id in cases:
    r = httpx.post(
        "https://api.platform.opentargets.org/api/v4/graphql",
        json={"query": query, "variables": {"efoId": efo_id}},
        timeout=30.0,
    )
    d = r.json().get("data", {}).get("disease")
    if d:
        print(f"=== {name} ({efo_id}) ===")
        print(f"  Name: {d.get('name')}")
        syns = d.get('synonyms') or []
        for s in syns:
            print(f"    Synonym relation: {s.get('relation')} -> {s.get('terms')[:3]}")
        print(f"  DbXRefs ({len(d.get('dbXRefs') or [])}): {d.get('dbXRefs')[:6]}")
        print(f"  Parents ({len(d.get('parents') or [])}): {[(p['id'], p['name']) for p in d.get('parents', [])]}")
        print(f"  Children ({len(d.get('children') or [])}): {[(c['id'], c['name']) for c in d.get('children', [])[:3]]}")
        targets_count = d.get('associatedTargets', {}).get('count', 0)
        top_targets = [r['target']['approvedSymbol'] for r in d.get('associatedTargets', {}).get('rows', [])]
        print(f"  Associated Targets count: {targets_count} | Top: {top_targets}")
        print()
    else:
        print(f"=== {name} ({efo_id}) === NOT FOUND: {r.text[:200]}")
