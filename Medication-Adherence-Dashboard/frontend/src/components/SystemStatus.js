import React, { useState } from 'react';
import './SystemStatus.css';

function SystemStatus({ status, onSystemControl }) {
  const [refreshInterval, setRefreshInterval] = useState(status?.refresh_interval ?? 60);

  const handleIntervalChange = (e) => {
    const newValue = parseInt(e.target.value);
    setRefreshInterval(newValue);
    onSystemControl({ refresh_interval: newValue });
  };

  const statusClass = status?.status === 'Healthy' ? 'status-healthy' : 
                      status?.status === 'Degraded' ? 'status-degraded' : 'status-paused';

  return (
    <div className="system-status">
      <div className="system-status-header">
        <h3 className="system-status-title">System Status</h3>
      </div>
        
      <div className="status-info">
        <div className={`status-item ${statusClass}`}>
          <span className="status-icon-pulse"></span>
          <strong>{status?.status || 'Unknown'}</strong>
        </div>
        <div className="status-item">
          <span className="status-label">Refresh</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginLeft: 'auto' }}>
            <input
              type="number"
              value={refreshInterval}
              onChange={handleIntervalChange}
              min="5"
              max="300"
              className="interval-input"
            />
            <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>sec</span>
          </div>
        </div>
        <div className="status-item">
          <span className="status-label">Last Sync</span>
          <span className="status-value">{status?.last_sync || '—'}</span>
        </div>
        <div className="status-item">
          <span className="status-label">Agents Running</span>
          <span className="status-value">{status?.agents_running || 0}</span>
        </div>
      </div>
    </div>
  );
}

export default SystemStatus;
