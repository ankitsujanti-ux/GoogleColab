import React from 'react';
import './ImportantDetails.css';

/** Format integer for display (e.g. 1234 → "1,234") */
function formatCount(n) {
  if (n == null || Number.isNaN(n)) return '0';
  return Number(n).toLocaleString();
}

function ImportantDetails({ data }) {
  if (!data || !data.kpis) return null;

  const { kpis } = data;

  const alertLevel = kpis.high_risk_now > 50 ? 'high' :
                     kpis.high_risk_now > 20 ? 'medium' : 'low';

  return (
    <div className="important-details-card key-metrics-card">
      <div className="important-details-header">
        <div className="details-title-wrapper">
          <svg className="details-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
            <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <h2 className="important-details-title">Key Metrics</h2>
        </div>
        <div className={`alert-badge alert-${alertLevel}`} role="status">
          {alertLevel === 'high' ? 'Critical' : alertLevel === 'medium' ? 'Attention' : 'Normal'}
        </div>
      </div>

      <div className="important-details-content key-metrics-content">
        <section className="key-metric-adherence-box" aria-labelledby="key-metric-adherence-label">
          <h3 id="key-metric-adherence-label" className="key-metric-adherence-box-title">Adherence patient count</h3>
          <div className="key-metric-adherence-row">
            <div className="key-metric-adherence-cell key-metric-low">
              <span className="key-metric-adherence-label">Low</span>
              <span className="key-metric-adherence-value">{formatCount(kpis.low_count)}</span>
            </div>
            <div className="key-metric-adherence-divider" aria-hidden />
            <div className="key-metric-adherence-cell key-metric-med">
              <span className="key-metric-adherence-label">Medium</span>
              <span className="key-metric-adherence-value">{formatCount(kpis.med_count)}</span>
            </div>
            <div className="key-metric-adherence-divider" aria-hidden />
            <div className="key-metric-adherence-cell key-metric-high">
              <span className="key-metric-adherence-label">High</span>
              <span className="key-metric-adherence-value">{formatCount(kpis.high_count)}</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

export default ImportantDetails;
