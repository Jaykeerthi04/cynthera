import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ReportModel } from '../types/analysis';
import { fetchReport } from '../services/api';
import { ReportViewer } from '../components/reports/ReportViewer';

export const ReportPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [report, setReport] = useState<ReportModel | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id) {
      setLoading(true);
      fetchReport(id)
        .then((data) => {
          setReport(data);
          setLoading(false);
        })
        .catch((err) => {
          setError(err.message || 'Failed to load report.');
          setLoading(false);
        });
    }
  }, [id]);

  if (loading) {
    return (
      <div style={{ maxWidth: '800px', margin: '4rem auto', textAlign: 'center' }}>
        <p style={{ fontSize: '1.1rem', color: 'var(--text-muted)' }}>
          Generating structured 15-section scientific report...
        </p>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div style={{ maxWidth: '600px', margin: '4rem auto', textAlign: 'center' }}>
        <div style={{ padding: '2rem', backgroundColor: 'var(--oppose-bg)', borderRadius: '8px', border: '1px solid var(--oppose-border)' }}>
          <h3 style={{ color: 'var(--oppose-color)', marginBottom: '0.5rem' }}>Failed to Load Report</h3>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>{error || 'Report not found.'}</p>
          <button onClick={() => navigate(-1)} className="btn btn-primary">
            Go Back
          </button>
        </div>
      </div>
    );
  }

  return <ReportViewer report={report} onBack={() => navigate(-1)} />;
};
