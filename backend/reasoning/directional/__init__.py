"""Phase 4B directional evidence infrastructure.

Modules:
    chembl_polarity:       ChEMBL action_type → MolecularPolarity mapping.
    reactome_polarity:     Reactome role → MolecularPolarity + CausalGrounding mapping.
    canonical_entity_gate: Validates that claims reference canonical biological entities.
    path_polarity:         Safe path-level polarity propagation over GraphEdge chains.
"""
