import React from 'react';
import { AlertCircle } from 'lucide-react';

export interface SourceAvailabilityBannerProps {
  failedSources: string[];
}

export const SourceAvailabilityBanner: React.FC<SourceAvailabilityBannerProps> = ({
  failedSources,
}) => {
  if (!failedSources || failedSources.length === 0) return null;

  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-start',
      gap: '0.75rem',
      padding: '1rem 1.25rem',
      backgroundColor: '#fffbeb',
      border: '1px solid #fde68a',
      borderRadius: '8px',
      marginBottom: '1.5rem',
      fontSize: '0.875rem'
    }}>
      <AlertCircle size={20} style={{ color: '#d97706', flexShrink: 0, marginTop: '0.1rem' }} />
      <div>
        <div style={{ fontWeight: 600, color: '#92400e', marginBottom: '0.2rem' }}>
          Limited Source Availability ({failedSources.length} {failedSources.length === 1 ? 'source' : 'sources'} unavailable)
        </div>
        <p style={{ color: '#78350f', lineHeight: 1.5 }}>
          The following biomedical data sources could not be queried during this run:{' '}
          <strong>{failedSources.join(', ')}</strong>. Evidence from these sources was not available for synthesis.
        </p>
        <p style={{ color: '#92400e', fontSize: '0.775rem', marginTop: '0.35rem', fontStyle: 'italic' }}>
          Note: This is NOT equivalent to "no evidence exists in these sources". It represents an API availability or timeout condition.
        </p>
      </div>
    </div>
  );
};
