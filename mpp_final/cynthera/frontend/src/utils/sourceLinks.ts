/**
 * CYNTHERA Canonical Source Links Utility
 *
 * Strictly adheres to verified canonical URL patterns.
 * Never fabricates URLs from unverified strings or guesses.
 */

export function getPubMedUrl(pmid: string | null | undefined): string | null {
  if (!pmid) return null;
  const clean = pmid.replace(/^PMID:\s*/i, '').trim();
  if (/^\d+$/.test(clean)) {
    return `https://pubmed.ncbi.nlm.nih.gov/${clean}/`;
  }
  return null;
}

export function getClinicalTrialsUrl(nctId: string | null | undefined): string | null {
  if (!nctId) return null;
  const clean = nctId.trim().toUpperCase();
  if (/^NCT\d{8}$/.test(clean)) {
    return `https://clinicaltrials.gov/study/${clean}`;
  }
  return null;
}

export function getChEMBLCompoundUrl(chemblId: string | null | undefined): string | null {
  if (!chemblId) return null;
  const clean = chemblId.trim().toUpperCase();
  if (/^CHEMBL\d+$/.test(clean)) {
    return `https://www.ebi.ac.uk/chembl/compound_report_card/${clean}/`;
  }
  return null;
}

export function getChEMBLTargetUrl(chemblId: string | null | undefined): string | null {
  if (!chemblId) return null;
  const clean = chemblId.trim().toUpperCase();
  if (/^CHEMBL\d+$/.test(clean)) {
    return `https://www.ebi.ac.uk/chembl/target_report_card/${clean}/`;
  }
  return null;
}

export function getUniProtUrl(accession: string | null | undefined): string | null {
  if (!accession) return null;
  const clean = accession.split('-')[0].trim().toUpperCase();
  if (/^[A-N,R-Z][0-9]([A-Z][A-Z, 0-9][A-Z, 0-9][0-9]){1,2}$/.test(clean) || clean.length >= 6) {
    return `https://www.uniprot.org/uniprotkb/${clean}/entry`;
  }
  return null;
}

export function getReactomeUrl(reactomeId: string | null | undefined): string | null {
  if (!reactomeId) return null;
  const clean = reactomeId.trim().toUpperCase();
  if (/^R-[A-Z]{3}-\d+$/.test(clean)) {
    return `https://reactome.org/content/detail/${clean}`;
  }
  return null;
}

export function getDoiUrl(doi: string | null | undefined): string | null {
  if (!doi) return null;
  const clean = doi.replace(/^doi:\s*/i, '').trim();
  if (/^10\.\d{4,9}\/[-._;()/:A-Z0-9]+$/i.test(clean)) {
    return `https://doi.org/${clean}`;
  }
  return null;
}

export function resolveCanonicalUrl(
  citationKey: string | null | undefined,
  sourceHint?: string | null
): string | null {
  if (!citationKey) return null;
  const key = citationKey.trim();
  const hint = (sourceHint || '').toLowerCase();

  if (/^NCT\d{8}$/i.test(key) || hint.includes('clinicaltrials')) {
    return getClinicalTrialsUrl(key);
  }
  if (/^(PMID:\s*)?\d+$/i.test(key) || hint.includes('pubmed')) {
    return getPubMedUrl(key);
  }
  if (/^10\.\d{4,9}\//.test(key) || hint.includes('doi')) {
    return getDoiUrl(key);
  }
  if (/^CHEMBL\d+$/i.test(key) || hint.includes('chembl')) {
    return getChEMBLCompoundUrl(key);
  }
  if (/^R-[A-Z]{3}-\d+$/i.test(key) || hint.includes('reactome')) {
    return getReactomeUrl(key);
  }

  return null;
}
