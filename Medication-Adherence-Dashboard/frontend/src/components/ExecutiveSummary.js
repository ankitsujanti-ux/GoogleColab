import React from 'react';
import './ExecutiveSummary.css';

function ExecutiveSummary({ data }) {
  if (!data || !data.kpis) return null;

  const { kpis } = data;

  return (
    <div className="executive-summary-card">
      <div className="executive-summary-header">
        <div className="summary-title-wrapper">
          <svg className="summary-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M9 11L12 14L22 4" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M21 12V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V5C3 4.46957 3.21071 3.96086 3.58579 3.58579C3.96086 3.21071 4.46957 3 5 3H16" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <h2 className="executive-summary-title">Executive Summary</h2>
        </div>
        <div className="summary-badge">AI-Powered Insights</div>
      </div>
      <div className="executive-summary-content">
        <p className="summary-paragraph">
          <strong>{kpis.notified_today ?? 0}</strong> patients notified today. Active monitoring and real-time interventions are in place.
        </p>
        <p className="summary-paragraph">
          <strong>Adherence:</strong> Current average is <strong>{typeof kpis.avg_adherence_now === 'number' ? kpis.avg_adherence_now.toFixed(1) : '—'}%</strong>.
          {kpis.adh_delta_weekly != null
            ? ` This week: ${kpis.adh_delta_weekly > 0 ? 'up ' : kpis.adh_delta_weekly < 0 ? 'down ' : ''}${kpis.adh_delta_weekly === 0 ? 'no change' : Math.abs(kpis.adh_delta_weekly).toFixed(1) + '%'} vs last week.`
            : ' Week-over-week comparison is not available yet.'}
        </p>
        <p className="summary-paragraph">
          <strong>Month-over-month:</strong> {(kpis.adh_delta_monthly != null || kpis.adh_delta != null)
            ? (() => {
                const d = kpis.adh_delta_monthly ?? kpis.adh_delta ?? 0;
                const dir = d > 0 ? 'up ' : d < 0 ? 'down ' : '';
                const pct = Math.abs(d).toFixed(1);
                const trend = d > 0 ? 'improving' : d < 0 ? 'declining' : 'stable';
                return `Adherence is ${dir}${pct}% vs last month — ${trend}.`;
              })()
            : 'Comparison with last month is not available yet.'}
        </p>
        <p className="summary-paragraph">
          <strong>High-risk patients:</strong> <strong>{kpis.high_risk_now ?? 0}</strong> now.
          {kpis.high_risk_last_week != null
            ? kpis.hr_delta > 0
              ? ` Up ${kpis.hr_delta} from last week — needs more attention.`
              : kpis.hr_delta < 0
                ? ` Down ${Math.abs(kpis.hr_delta)} from last week — improving.`
                : ' No change from last week.'
            : ' Prior week comparison not available yet.'}
        </p>
      </div>
    </div>
  );
}

export default ExecutiveSummary;
