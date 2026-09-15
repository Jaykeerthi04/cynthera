import asyncio
import json
import sys
import os
import re
sys.path.insert(0, os.path.abspath("."))
from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from uuid import uuid4

cases = [
    ("CYN-013", "Aspirin", "Secondary prevention of cardiovascular disease"),
    ("CYN-026", "Fluticasone", "Allergic rhinitis"),
    ("CYN-041", "Tamoxifen", "ER-positive breast cancer"),
    ("CYN-186", "Colchicine", "Colorectal cancer"),
    ("CYN-200", "Escitalopram", "Neuropathic pain"),
]

async def audit_indications():
    orch = MasterOrchestrator()
    for cid, drug_name, disease_name in cases:
        print(f"\n=======================================================")
        print(f"AUDITING INDICATION MATCHING FOR {cid}: {drug_name} -> {disease_name}")
        print(f"=======================================================")
        
        drug_res = await orch._resolver.resolve_drug(drug_name)
        dis_res = await orch._resolver.resolve_disease(disease_name)
        
        d_entity = Drug(
            name=drug_res.entity_name,
            identifiers=drug_res,
        )
        dis_entity = Disease(
            name=dis_res.entity_name,
            identifiers=dis_res,
        )
        
        print(f"Canonical drug name: {d_entity.name} (ChEMBL: {d_entity.chembl_id})")
        print(f"Canonical disease name: {dis_entity.name} (MeSH: {dis_entity.mesh_id})")
        
        # Call _fetch_chembl with chembl_id string
        chembl_data = await orch._retrieval._fetch_chembl(d_entity.chembl_id)
        ind_data = chembl_data.get("indications", {})
        indications = ind_data.get("indications", [])
        molecule_data = chembl_data.get("molecule", {})
        print(f"Retrieved {len(indications)} ChEMBL indication entries.")
        print(f"Molecule max_phase: {molecule_data.get('max_phase')}")
        
        # Test current matching logic
        sig = orch._retrieval._parse_indication_data(ind_data, molecule_data, disease_name)
        print(f"Current ApprovalSignal: {sig}")
        
        # Token overlap analysis
        query_tokens = set(re.sub(r"[^a-z0-9]", " ", disease_name.lower()).split()) - {"the", "a", "an", "of", "and", "or", "for", "in", "to"}
        print(f"Query tokens: {query_tokens}")
        
        matches = []
        for ind in indications:
            efo = str(ind.get("efo_term") or "").lower()
            mesh = str(ind.get("mesh_heading") or "").lower()
            max_phase = int(ind.get("max_phase_for_ind") or 0)
            
            for term in (efo, mesh):
                if not term:
                    continue
                term_tokens = set(re.sub(r"[^a-z0-9]", " ", term).split()) - {"the", "a", "an", "of", "and", "or", "for", "in", "to"}
                union = query_tokens | term_tokens
                intersection = query_tokens & term_tokens
                sim = len(intersection) / len(union) if union else 0.0
                q_clean = disease_name.lower().replace(" ", "")
                t_clean = term.replace(" ", "")
                if q_clean in t_clean or t_clean in q_clean:
                    sim = max(sim, 0.6)
                matches.append((term, max_phase, sim, intersection, term_tokens))
                
        matches.sort(key=lambda x: x[2], reverse=True)
        print("Top 10 Indication Matches:")
        seen = set()
        count = 0
        for m in matches:
            if m[0] in seen:
                continue
            seen.add(m[0])
            print(f"  term='{m[0]}' | phase={m[1]} | sim={m[2]:.3f} | overlap={list(m[3])} | term_tokens={list(m[4])}")
            count += 1
            if count >= 8:
                break

asyncio.run(audit_indications())
