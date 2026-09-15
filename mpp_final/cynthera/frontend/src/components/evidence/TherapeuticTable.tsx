import React, { useState, useMemo } from 'react';
import { ExternalLink, ChevronRight, CheckCircle2, XCircle, HelpCircle } from 'lucide-react';
import { TherapeuticEvidenceItem } from '../../types/analysis';
import { Badge } from '../common/Badge';
import { EvidenceFilterBar, EvidenceFilterState } from './EvidenceFilterBar';
import { resolveCanonicalUrl } from '../../utils/sourceLinks';

export interface TherapeuticTableProps {
  evidence: TherapeuticEvidenceItem[];
  onSelectEvidence: (item: TherapeuticEvidenceItem) => void;
}

export const TherapeuticTable: React.FC<TherapeuticTableProps> = ({
  evidence,
  onSelectEvidence,
}) => {
  const [filterState, setFilterState] = useState<EvidenceFilterState>({
    search: '',
    direction: 'ALL',
    evidenceType: 'ALL',
    qualityTier: 'ALL',
    pairSpecificOnly: false,
    sortBy: 'quality',
  });

  const availableTypes = useMemo(() => {
    return Array.from(new Set(evidence.map((e) => e.evidence_type))).filter(Boolean);
  }, [evidence]);

  const filteredEvidence = useMemo(() => {
    return evidence.filter((item) => {
      // Search
      if (filterState.search) {
        const q = filterState.search.toLowerCase();
        const matchesCitation = item.citation_key.toLowerCase().includes(q);
        const matchesTitle = item.title?.toLowerCase().includes(q);
        const matchesClaim = item.extracted_claim?.toLowerCase().includes(q);
        const matchesSource = item.source.toLowerCase().includes(q);
        if (!matchesCitation && !matchesTitle && !matchesClaim && !matchesSource) {
          return false;
        }
      }

      // Direction
      if (filterState.direction !== 'ALL' && item.direction !== filterState.direction) {
        return false;
      }

      // Evidence Type
      if (filterState.evidenceType !== 'ALL' && item.evidence_type !== filterState.evidenceType) {
        return false;
      }

      // Quality Tier
      if (filterState.qualityTier !== 'ALL' && item.quality_tier !== filterState.qualityTier) {
        return false;
      }

      // Pair specificity
      if (filterState.pairSpecificOnly && !item.pair_specificity) {
        return false;
      }

      return true;
    }).sort((a, b) => {
      if (filterState.sortBy === 'quality') {
        const qualityRank: Record<string, number> = { HIGH: 3, MODERATE: 2, LOW: 1, UNVERIFIED: 0 };
        return (qualityRank[b.quality_tier] || 0) - (qualityRank[a.quality_tier] || 0);
      }
      if (filterState.sortBy === 'direction') {
        return a.direction.localeCompare(b.direction);
      }
      if (filterState.sortBy === 'source') {
        return a.source.localeCompare(b.source);
      }
      return a.evidence_type.localeCompare(b.evidence_type);
    });
  }, [evidence, filterState]);

  const getDirectionBadge = (dir: string) => {
    switch (dir) {
      case 'SUPPORTS':
        return <Badge variant="support" icon={<CheckCircle2 size={12} />}>SUPPORTS</Badge>;
      case 'OPPOSES':
        return <Badge variant="oppose" icon={<XCircle size={12} />}>OPPOSES</Badge>;
      case 'UNCERTAIN':
      default:
        return <Badge variant="uncertain" icon={<HelpCircle size={12} />}>{dir}</Badge>;
    }
  };

  return (
    <div className="research-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>Therapeutic Evidence Ledger</h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Showing {filteredEvidence.length} of {evidence.length} retrieved evidence records
          </p>
        </div>
      </div>

      {/* Filter Toolbar */}
      <EvidenceFilterBar
        filterState={filterState}
        onChange={setFilterState}
        availableTypes={availableTypes}
      />

      {/* Evidence Table */}
      {filteredEvidence.length === 0 ? (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          No qualifying evidence records matched your current filter criteria.
        </div>
      ) : (
        <div className="table-container">
          <table className="research-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Source</th>
                <th>Record / Study</th>
                <th>Direction</th>
                <th>Quality</th>
                <th>Pair Specific</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvidence.map((item) => {
                const canonicalUrl = item.source_url || resolveCanonicalUrl(item.citation_key, item.source);
                return (
                  <tr
                    key={item.id}
                    onClick={() => onSelectEvidence(item)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>
                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                        {item.evidence_type.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: '0.8rem' }}>{item.source}</span>
                    </td>
                    <td style={{ maxWidth: '300px' }}>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>
                        <code>{item.citation_key}</code>
                      </div>
                      <div style={{
                        fontSize: '0.75rem',
                        color: 'var(--text-muted)',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                      }}>
                        {item.title || item.extracted_claim || 'Study record details'}
                      </div>
                    </td>
                    <td>
                      {getDirectionBadge(item.direction)}
                    </td>
                    <td>
                      <Badge variant={item.quality_tier === 'HIGH' ? 'support' : 'neutral'}>
                        {item.quality_tier}
                      </Badge>
                    </td>
                    <td>
                      <Badge variant={item.pair_specificity ? 'accent' : 'neutral'}>
                        {item.pair_specificity ? 'YES' : 'NO'}
                      </Badge>
                    </td>
                    <td>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectEvidence(item);
                        }}
                        className="btn btn-secondary"
                        style={{ padding: '0.25rem 0.55rem', fontSize: '0.75rem' }}
                      >
                        Inspect Trace
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
