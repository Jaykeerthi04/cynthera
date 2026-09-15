import httpx

query_assoc = """
query Assoc($mondoId: String!) {
  disease(efoId: $mondoId) {
    id
    name
    associatedTargets(page: {index: 0, size: 50}) {
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

r = httpx.post(
    "https://api.platform.opentargets.org/api/v4/graphql",
    json={"query": query_assoc, "variables": {"mondoId": "MONDO_0008487"}},
    timeout=30.0,
)
pcos_genes = [row['target']['approvedSymbol'] for row in r.json()['data']['disease']['associatedTargets']['rows']]
print(f"Top 50 PCOS genes in Open Targets: {pcos_genes[:15]} ... (total {len(pcos_genes)})")
print(f"Is PRKAA1 in PCOS top 50? {'PRKAA1' in pcos_genes}")
print(f"Is INSR in PCOS top 50? {'INSR' in pcos_genes}")
print(f"Is IRS1 in PCOS top 50? {'IRS1' in pcos_genes}")
print(f"Is AKT1 in PCOS top 50? {'AKT1' in pcos_genes}")
print(f"Is ESR1 in PCOS top 50? {'ESR1' in pcos_genes}")
print(f"Is FTO in PCOS top 50? {'FTO' in pcos_genes}")
