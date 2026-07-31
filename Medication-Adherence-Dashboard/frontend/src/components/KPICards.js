import React, { useState, useEffect, useRef } from 'react';
import './KPICards.css';

const KPI_MINIMIZED_KEY = 'dashboard-kpi-minimized';

function AnimatedNumber({ value, duration = 1000, formatter = (v) => v.toLocaleString() }) {
  const [displayValue, setDisplayValue] = useState(0);
  const startTimeRef = useRef(null);
  const animationFrameRef = useRef(null);

  useEffect(() => {
    const startValue = displayValue;
    const endValue = value;
    const startTime = performance.now();
    startTimeRef.current = startTime;

    const animate = (currentTime) => {
      if (!startTimeRef.current) return;
      
      const elapsed = currentTime - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);
      
      // Easing function (ease-out)
      const easeOut = 1 - Math.pow(1 - progress, 3);
      const current = startValue + (endValue - startValue) * easeOut;
      
      setDisplayValue(Math.floor(current));
      
      if (progress < 1) {
        animationFrameRef.current = requestAnimationFrame(animate);
      } else {
        setDisplayValue(endValue);
      }
    };

    animationFrameRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, duration]);

  return <span>{formatter(displayValue)}</span>;
}

function KPICards({ data }) {
  const [minimized, setMinimized] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(KPI_MINIMIZED_KEY) || 'false');
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(KPI_MINIMIZED_KEY, JSON.stringify(minimized));
    } catch (_) {}
  }, [minimized]);

  if (!data || !data.kpis) return null;

  const { kpis, system } = data;
  // Use API date when available; otherwise show today (so the line is always visible)
  const dataThroughDate = system?.last_sync_date || (() => {
    const d = new Date();
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  })();
  const response_rate = kpis.notified_unique > 0 
    ? ((kpis.responded_unique / kpis.notified_unique) * 100).toFixed(1)
    : 0;

  const hr_support = kpis.high_risk_last_week == null
    ? "No prior week data"
    : kpis.hr_delta === 0
    ? "No change vs last week"
    : kpis.hr_delta > 0
    ? `↑ ${kpis.hr_delta} vs last week`
    : `↓ ${Math.abs(kpis.hr_delta)} vs last week`;

  return (
    <>
    <div className="kpi-cards grid grid-4">
      {/* Patients Stabilized by AI - Same design as Notified & Responded, violet color + checkmark icon */}
      <div className="card kpi-card-featured">
        <div className="card-content">
          <div className="card-header">
            <div className="icon-wrapper icon-featured">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M9 11l3 3L22 4" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <div className="card-title-section">
              <div className="card-title">Patients Stabilized by AI</div>
              <div className="card-subtitle">Average Adherence Rate</div>
            </div>
          </div>
          <div className="card-main-value">
            <span className="main-number">{kpis.avg_adherence_now.toFixed(1)}%</span>
          </div>
          <div className="card-secondary-value">
            <span className="secondary-label">Total Interventions</span>
            <span className="secondary-number">
              <AnimatedNumber value={kpis.interventions_30d} />
            </span>
          </div>
        </div>
      </div>

      {/* Notified & Responded */}
      <div className="card kpi-card-info">
        <div className="card-content">
          <div className="card-header">
            <div className="icon-wrapper icon-info">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <div className="card-title-section">
              <div className="card-title">Notified & Responded</div>
              <div className="card-subtitle">Response Rate</div>
            </div>
          </div>
          <div className="card-main-value">
            <span className="main-number">{response_rate}%</span>
          </div>
          <div className="card-secondary-value split-values">
            <div className="split-item">
              <span className="secondary-label">Notified</span>
              <span className="secondary-number">
                <AnimatedNumber value={kpis.notified_unique} />
              </span>
            </div>
            <div className="split-divider"></div>
            <div className="split-item">
              <span className="secondary-label">Responded</span>
              <span className="secondary-number">
                <AnimatedNumber value={kpis.responded_unique} />
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Projected Cost Savings */}
      <div className="card kpi-card-success">
        <div className="card-content">
          <div className="card-header">
            <div className="icon-wrapper icon-success-alt">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="12" y1="1" x2="12" y2="23" strokeLinecap="round"/>
                <path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <div className="card-title-section">
              <div className="card-title">Projected Cost Savings</div>
              <div className="card-subtitle">30-Day Projection</div>
            </div>
          </div>
          <div className="card-main-value">
            <span className="currency-symbol">₹</span>
            <span className="main-number">{Math.round(kpis.proj_savings_month / 1000)}K</span>
          </div>
          <div className="card-secondary-value card-secondary-value-tbd">
            <span className="secondary-label">Total Savings</span>
            <span className="secondary-number secondary-number-tbd">TBD (per Business)</span>
          </div>
        </div>
      </div>

      {/* High-Risk Patients */}
      <div className="card kpi-card-warning">
        <div className="card-content">
          <div className="card-header">
            <div className="icon-wrapper icon-warning">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M10.29 3.86L1 20h18.84M5 20l5.29-16.14M19 20l-5.29-16.14" strokeLinecap="round" strokeLinejoin="round"/>
                <circle cx="12" cy="12" r="1" fill="currentColor"/>
              </svg>
            </div>
            <div className="card-title-section">
              <div className="card-title">High-Risk Patients</div>
              <div className="card-subtitle">{hr_support}</div>
            </div>
          </div>
          <div className="card-main-value">
            <span className="main-number">
              <AnimatedNumber value={kpis.high_risk_now} />
            </span>
          </div>
          <div className="card-secondary-value">
            <span className="secondary-label">In AI Care</span>
            <span className="secondary-number">
              {kpis.high_risk_now > 0 ? 'Yes' : 'None'}
            </span>
          </div>
        </div>
      </div>
    </div>
    </>
  );
}

export default KPICards;
