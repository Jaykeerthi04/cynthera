import React, { useState } from 'react';
import { TargetInfo } from '../../types/analysis';
import { ExternalLink, Target as TargetIcon } from 'lucide-react';
import { Drawer } from '../common/Drawer';
import { Badge } from '../common/Badge';

export interface TargetExplorerProps {
  targets: TargetInfo[];
}

export const TargetExplorer: React.FC<TargetExplorerProps> = ({ targets }) => {
  const [selectedTarget, setSelectedTarget] = useState<TargetInfo | null>(null);

  return (
    <div className="research-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Target Explorer</h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Identified biological targets & disease relevance
          </p>
        </div>
        <Badge variant="neutral">
          {targets.length} {targets.length === 1 ? 'Target' : 'Targets'}
        </Badge>
      </div>

      {targets.length === 0 ? (
        <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          No qualifying protein targets identified under current retrieval scope.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {targets.map((target) => (
            <div
              key={target.uniprot_id || target.symbol}
              onClick={() => setSelectedTarget(target)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                borderRadius: '6px',
                border: '1px solid var(--border-light)',
                backgroundColor: 'var(--bg-subtle)',
                cursor: 'pointer',
                transition: 'all 0.15s ease'
              }}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--primary-accent)')}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border-light)')}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <TargetIcon size={14} style={{ color: 'var(--primary-accent)' }} />
                  <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{target.symbol}</span>
                  <code style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{target.uniprot_id}</code>
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                  {target.name}
                </div>
              </div>

              <div style={{ textAlign: 'right' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>
                  Relevance
                </span>
                <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>
                  {target.disease_relevance > 0 ? target.disease_relevance.toFixed(2) : 'Indirect'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Target Details Drawer */}
      <Drawer
        isOpen={Boolean(selectedTarget)}
        onClose={() => setSelectedTarget(null)}
        title={selectedTarget ? `${selectedTarget.symbol} Target Details` : 'Target Details'}
        subtitle={selectedTarget?.name}
      >
        {selectedTarget && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', fontSize: '0.875rem' }}>
            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>
                UniProt Accession
              </span>
              <span style={{ fontWeight: 600, fontSize: '1rem' }}>{selectedTarget.uniprot_id}</span>
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>
                Gene Symbol & Name
              </span>
              <span style={{ fontWeight: 600 }}>{selectedTarget.symbol}</span> — {selectedTarget.name}
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>
                Affinity (Kd / Ki / IC50)
              </span>
              <span>
                {selectedTarget.affinity_nm !== null ? `${selectedTarget.affinity_nm.toFixed(1)} nM` : 'Affinity measurement not reported'}
              </span>
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>
                Disease Association Relevance Score
              </span>
              <span>
                {selectedTarget.disease_relevance > 0 ? selectedTarget.disease_relevance.toFixed(3) : 'No direct gene-disease association retrieved'}
              </span>
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>
                Provenance & Data Source
              </span>
              <span>{selectedTarget.source}</span>
            </div>

            {selectedTarget.source_url && (
              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-light)' }}>
                <a
                  href={selectedTarget.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-primary"
                  style={{ width: '100%' }}
                >
                  Open UniProt Record <ExternalLink size={16} />
                </a>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};
