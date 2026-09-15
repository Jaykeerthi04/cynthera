import React from 'react';
import { Search, Filter } from 'lucide-react';

export interface EvidenceFilterState {
  search: string;
  direction: string;
  evidenceType: string;
  qualityTier: string;
  pairSpecificOnly: boolean;
  sortBy: 'quality' | 'direction' | 'source' | 'type';
}

export interface EvidenceFilterBarProps {
  filterState: EvidenceFilterState;
  onChange: (newState: EvidenceFilterState) => void;
  availableTypes: string[];
}

export const EvidenceFilterBar: React.FC<EvidenceFilterBarProps> = ({
  filterState,
  onChange,
  availableTypes,
}) => {
  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: '0.75rem',
      alignItems: 'center',
      marginBottom: '1rem',
      padding: '0.75rem 1rem',
      backgroundColor: 'var(--bg-surface)',
      borderRadius: '6px',
      border: '1px solid var(--border-color)'
    }}>
      {/* Search Input */}
      <div style={{ position: 'relative', flex: '1 1 200px' }}>
        <Search size={16} style={{ position: 'absolute', left: '0.65rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
        <input
          type="text"
          placeholder="Search study, PMID, NCT ID..."
          value={filterState.search}
          onChange={(e) => onChange({ ...filterState, search: e.target.value })}
          style={{
            width: '100%',
            padding: '0.45rem 0.65rem 0.45rem 2rem',
            borderRadius: '4px',
            border: '1px solid var(--border-color)',
            fontSize: '0.85rem'
          }}
        />
      </div>

      {/* Direction Filter */}
      <select
        value={filterState.direction}
        onChange={(e) => onChange({ ...filterState, direction: e.target.value })}
        style={{
          padding: '0.45rem 0.65rem',
          borderRadius: '4px',
          border: '1px solid var(--border-color)',
          fontSize: '0.85rem',
          backgroundColor: 'var(--bg-surface)'
        }}
      >
        <option value="ALL">All Directions</option>
        <option value="SUPPORTS">Supports Only</option>
        <option value="OPPOSES">Opposes Only</option>
        <option value="UNCERTAIN">Uncertain Only</option>
      </select>

      {/* Evidence Type Filter */}
      <select
        value={filterState.evidenceType}
        onChange={(e) => onChange({ ...filterState, evidenceType: e.target.value })}
        style={{
          padding: '0.45rem 0.65rem',
          borderRadius: '4px',
          border: '1px solid var(--border-color)',
          fontSize: '0.85rem',
          backgroundColor: 'var(--bg-surface)'
        }}
      >
        <option value="ALL">All Evidence Types</option>
        {availableTypes.map((t) => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>

      {/* Quality Tier Filter */}
      <select
        value={filterState.qualityTier}
        onChange={(e) => onChange({ ...filterState, qualityTier: e.target.value })}
        style={{
          padding: '0.45rem 0.65rem',
          borderRadius: '4px',
          border: '1px solid var(--border-color)',
          fontSize: '0.85rem',
          backgroundColor: 'var(--bg-surface)'
        }}
      >
        <option value="ALL">All Quality Tiers</option>
        <option value="HIGH">High Quality</option>
        <option value="MODERATE">Moderate Quality</option>
        <option value="LOW">Low Quality</option>
      </select>

      {/* Sort Selector */}
      <select
        value={filterState.sortBy}
        onChange={(e) => onChange({ ...filterState, sortBy: e.target.value as any })}
        style={{
          padding: '0.45rem 0.65rem',
          borderRadius: '4px',
          border: '1px solid var(--border-color)',
          fontSize: '0.85rem',
          backgroundColor: 'var(--bg-surface)'
        }}
      >
        <option value="quality">Sort by Quality</option>
        <option value="direction">Sort by Direction</option>
        <option value="source">Sort by Source</option>
        <option value="type">Sort by Type</option>
      </select>

      {/* Pair-Specific Checkbox */}
      <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.825rem', cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={filterState.pairSpecificOnly}
          onChange={(e) => onChange({ ...filterState, pairSpecificOnly: e.target.checked })}
        />
        Pair-Specific Only
      </label>
    </div>
  );
};
