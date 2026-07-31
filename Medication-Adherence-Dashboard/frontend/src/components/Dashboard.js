import React, { Component } from 'react';
import Header from './Header';
import ExecutiveSummary from './ExecutiveSummary';
import KPICards from './KPICards';
import AgentsFlow from './AgentsFlow';
import Charts from './Charts';
import DataSnapshot from './DataSnapshot';
import ImportantDetails from './ImportantDetails';
import './Dashboard.css';

// If Charts throws (e.g. amCharts .set on undefined), show fallback so dashboard is not blank
class ChartErrorBoundary extends Component {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(err, info) { console.error('Charts error:', err, info); }
  render() {
    if (this.state.hasError) {
      return (
        <div className="charts-container" style={{ padding: '24px', background: 'var(--card-bg, #f8fafc)', borderRadius: '8px' }}>
          <p style={{ margin: 0, color: 'var(--text-muted, #64748b)' }}>Charts are temporarily unavailable. KPIs and data above are still correct.</p>
        </div>
      );
    }
    return this.props.children;
  }
}

function Dashboard({ dashboardData, systemStatus, trendData, onSystemControl, toastFilter, onToastFilterChange }) {
  // Caller (App) passes default data when API fails so content is never blank
  if (!dashboardData || !systemStatus) {
    return <div className="loading">Loading...</div>;
  }

  return (
    <div className="dashboard">
      <Header
        systemStatus={systemStatus}
        onSystemControl={onSystemControl}
        toastFilter={toastFilter}
        onToastFilterChange={onToastFilterChange}
      />
      
      <div className="dashboard-content">
        <div className="dashboard-left">
          <ExecutiveSummary data={dashboardData} />
          <KPICards data={dashboardData} />
          <ChartErrorBoundary>
            <Charts trendData={trendData} data={dashboardData} />
          </ChartErrorBoundary>
        </div>
        
        <div className="dashboard-right">
          <ImportantDetails data={dashboardData} />
        </div>

        <div className="dashboard-snapshot-row">
          <DataSnapshot />
        </div>

        <div className="dashboard-agents-flow-row">
          <AgentsFlow systemStatus={systemStatus} />
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
