import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Sparkles, ArrowRight, Dna, Activity, ShieldCheck, Database, FileText } from 'lucide-react';
import { submitAnalysis } from '../services/api';

const EXAMPLE_HYPOTHESES = [
  {
    category: 'Negative Clinical Trial Veto',
    drug: 'Azithromycin',
    disease: 'COVID-19',
    expected: 'OPPOSE',
    badge: 'oppose',
    desc: 'Empirical clinical trial failure contradicts initial in vitro antiviral hypotheses.'
  },
  {
    category: 'Established Regulatory Positive',
    drug: 'Aspirin',
    disease: 'Secondary prevention of cardiovascular disease',
    expected: 'SUPPORT',
    badge: 'support',
    desc: 'Disease-matched regulatory indication and extensive RCT secondary prevention evidence.'
  },
  {
    category: 'Established Positive',
    drug: 'Lisinopril',
    disease: 'Hypertension',
    expected: 'SUPPORT',
    badge: 'support',
    desc: 'ACE inhibition with robust clinical and regulatory anchor.'
  },
  {
    category: 'Hard Negative / Hallucination Trap',
    drug: 'Metformin',
    disease: 'Pancreatic cancer',
    expected: 'OPPOSE / UNCERTAIN',
    badge: 'uncertain',
    desc: 'Epidemiological association without therapeutic outcome support.'
  },
  {
    category: 'Weak / Indirect Literature',
    drug: 'Propranolol',
    disease: 'Depression',
    expected: 'UNCERTAIN',
    badge: 'uncertain',
    desc: 'Sparse mechanistic overlap without pair-specific clinical trials.'
  },
];

const PROGRESS_STEPS = [
  'Canonicalizing entities & resolving ontologies',
  'Retrieving multi-database evidence (ChEMBL, CT.gov, PubMed)',
  'Building directional evidence graph',
  'Evaluating biological candidate mechanisms',
  'Auditing pair-specific therapeutic evidence',
  'Evaluating clinical opposition & trial termination reasons',
  'Checking contradictions & evidence discordance',
  'Synthesizing final epistemic recommendation',
];

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const [drug, setDrug] = useState('');
  const [disease, setDisease] = useState('');
  const [policy, setPolicy] = useState<'STANDARD' | 'FAST' | 'COMPREHENSIVE'>('STANDARD');
  const [isLoading, setIsLoading] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!drug.trim() || !disease.trim()) {
      setErrorMessage('Please provide both drug and disease names.');
      return;
    }

    setErrorMessage(null);
    setIsLoading(true);
    setCurrentStepIndex(0);

    // Advance deterministic progress steps while analysis runs
    const interval = setInterval(() => {
      setCurrentStepIndex((prev) => (prev < PROGRESS_STEPS.length - 1 ? prev + 1 : prev));
    }, 1800);

    try {
      const result = await submitAnalysis({ drug, disease, policy });
      clearInterval(interval);
      navigate(`/analysis/${result.analysis_id}`, { state: { result } });
    } catch (err: any) {
      clearInterval(interval);
      setIsLoading(false);
      setErrorMessage(err?.message || 'Failed to complete evaluation.');
    }
  };

  const handleSelectExample = (exDrug: string, exDisease: string) => {
    setDrug(exDrug);
    setDisease(exDisease);
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '3rem 1.5rem' }}>
      {/* Hero Header */}
      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.4rem',
          padding: '0.25rem 0.75rem',
          backgroundColor: 'var(--primary-accent-subtle)',
          borderRadius: '999px',
          color: 'var(--primary-accent)',
          fontSize: '0.8rem',
          fontWeight: 600,
          marginBottom: '1rem'
        }}>
          <Dna size={14} /> Contradiction-Aware Mechanistic Reasoning Engine
        </div>
        <h1 style={{ fontSize: '2.5rem', fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text-primary)' }}>
          CYNTHERA
        </h1>
        <p style={{ fontSize: '1.15rem', color: 'var(--text-secondary)', marginTop: '0.75rem', maxWidth: '720px', margin: '0.75rem auto 0', lineHeight: 1.6 }}>
          Evidence-grounded drug–disease hypothesis reasoning with multi-hop mechanistic tracing, qualified clinical opposition vetoes, and full provenance traceability.
        </p>
      </div>

      {/* Input Card */}
      <div className="research-card" style={{ padding: '2rem', marginBottom: '2.5rem' }}>
        <form onSubmit={handleSubmit}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem', marginBottom: '1.5rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.825rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.4rem' }}>
                Drug / Intervention Name
              </label>
              <input
                type="text"
                placeholder="e.g. Aspirin, Azithromycin, Lisinopril..."
                value={drug}
                onChange={(e) => setDrug(e.target.value)}
                disabled={isLoading}
                style={{
                  width: '100%',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.95rem'
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.825rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.4rem' }}>
                Disease / Indication
              </label>
              <input
                type="text"
                placeholder="e.g. COVID-19, Hypertension, Depression..."
                value={disease}
                onChange={(e) => setDisease(e.target.value)}
                disabled={isLoading}
                style={{
                  width: '100%',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.95rem'
                }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Retrieval Depth:</span>
              <select
                value={policy}
                onChange={(e) => setPolicy(e.target.value as any)}
                disabled={isLoading}
                style={{
                  padding: '0.35rem 0.65rem',
                  borderRadius: '4px',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.8rem',
                  backgroundColor: 'var(--bg-surface)'
                }}
              >
                <option value="STANDARD">Standard (Balanced)</option>
                <option value="FAST">Fast (Cached / Prior Knowledge)</option>
                <option value="COMPREHENSIVE">Comprehensive (Deep)</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="btn btn-primary"
              style={{ padding: '0.65rem 1.75rem', fontSize: '0.95rem' }}
            >
              {isLoading ? 'Evaluating Hypothesis...' : (
                <>Evaluate Hypothesis <ArrowRight size={16} /></>
              )}
            </button>
          </div>
        </form>

        {errorMessage && (
          <div style={{
            marginTop: '1.25rem',
            padding: '0.75rem 1rem',
            backgroundColor: 'var(--oppose-bg)',
            border: '1px solid var(--oppose-border)',
            borderRadius: '6px',
            color: 'var(--oppose-color)',
            fontSize: '0.875rem'
          }}>
            {errorMessage}
          </div>
        )}
      </div>

      {/* Loading Progress State */}
      {isLoading && (
        <div className="research-card" style={{ padding: '1.75rem', marginBottom: '2.5rem', backgroundColor: 'var(--bg-subtle)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
            <Activity size={20} style={{ color: 'var(--primary-accent)' }} />
            <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Executing Multi-Stage Evidence Synthesis</h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {PROGRESS_STEPS.map((step, idx) => {
              const isPast = idx < currentStepIndex;
              const isCurrent = idx === currentStepIndex;
              return (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.65rem',
                    fontSize: '0.85rem',
                    color: isPast ? 'var(--support-color)' : (isCurrent ? 'var(--primary-accent)' : 'var(--text-muted)'),
                    fontWeight: isCurrent ? 600 : 400
                  }}
                >
                  <div style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: isPast ? 'var(--support-color)' : (isCurrent ? 'var(--primary-accent)' : 'var(--border-color)')
                  }} />
                  <span>{step}</span>
                  {isCurrent && <span style={{ fontSize: '0.75rem', fontStyle: 'italic' }}>— in progress</span>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Example Hypotheses Section */}
      <div>
        <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
          Curated Benchmark Hypotheses (Quick-Trigger)
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.85rem' }}>
          {EXAMPLE_HYPOTHESES.map((ex, idx) => (
            <div
              key={idx}
              onClick={() => handleSelectExample(ex.drug, ex.disease)}
              style={{
                padding: '1rem',
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-light)',
                borderRadius: '6px',
                cursor: 'pointer',
                transition: 'all 0.15s ease'
              }}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--primary-accent)')}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border-light)')}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  {ex.category}
                </span>
                <span className={`badge badge-${ex.badge}`} style={{ fontSize: '0.7rem' }}>
                  {ex.expected}
                </span>
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)', marginTop: '0.25rem' }}>
                {ex.drug} × {ex.disease}
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem', lineHeight: 1.4 }}>
                {ex.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
