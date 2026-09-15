import React from 'react';
import { Database, CheckCircle2, AlertTriangle, ExternalLink } from 'lucide-react';
import { SourceStatus } from '../../types/analysis';
import { Badge } from '../common/Badge';

export interface SourceExplorerProps {
  sources: SourceStatus[];
}

export const SourceExplorer: React.FC<SourceExplorerProps> = ({ sources }) => {
  return (
    <div className="research-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Biomedical Data Source Coverage</h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Audit breakdown of records retrieved, filtered, and used in synthesis
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {sources.map((src) => {
          const isAvailable = src.status === 'available';
          return (
            <div
              key={src.name}
              style={{
                padding: '0.85rem 1rem',
                borderRadius: '6px',
                border: '1px solid var(--border-light)',
                backgroundColor: isAvailable ? 'var(--bg-surface)' : 'var(--uncertain-bg)'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Database size={16} style={{ color: isAvailable ? 'var(--primary-accent)' : 'var(--uncertain-color)' }} />
                  <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{src.name}</span>
                </div>

                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <Badge variant={isAvailable ? 'support' : 'uncertain'}>
                    {isAvailable ? 'Available' : 'Unavailable during run'}
                  </Badge>
                  {src.canonical_portal_url && (
                    <a
                      href={src.canonical_portal_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
                    >
                      Portal <ExternalLink size={12} />
                    </a>
                  )}
                </div>
              </div>

              {isAvailable ? (
                <div style={{ display: 'flex', gap: '1.5rem', fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.35rem' }}>
                  <span>Retrieved: <strong>{src.retrieved_count}</strong></span>
                  <span>Used: <strong style={{ color: 'var(--support-color)' }}>{src.used_count}</strong></span>
                  <span>Excluded: <strong>{src.excluded_count}</strong></span>
                </div>
              ) : (
                <p style={{ fontSize: '0.8rem', color: 'var(--uncertain-color)', marginTop: '0.25rem' }}>
                  {src.impact || 'Service could not be reached. Evidence from this source was omitted.'}
                </p>
              )}

              {src.reason_for_exclusion && isAvailable && (
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
                  Exclusion filter: {src.reason_for_exclusion}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
