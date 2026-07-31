import React, { useState, useEffect } from 'react';
import './Header.css';
import './SystemStatus.css';

const TOAST_FILTER_ALL = 'all';
const TOAST_FILTER_NOTIFICATION_SENT = 'notification_sent';
const TOAST_FILTER_APPRECIATION = 'appreciation';

function Header({ systemStatus, onSystemControl, toastFilter = TOAST_FILTER_ALL, onToastFilterChange }) {
  const [liveOn, setLiveOn] = useState(systemStatus?.live_on ?? true);
  const [sendAutoNotifications, setSendAutoNotifications] = useState(systemStatus?.send_auto_notifications ?? true);

  useEffect(() => {
    if (systemStatus?.live_on !== undefined) {
      setLiveOn(systemStatus.live_on);
    }
  }, [systemStatus]);
  useEffect(() => {
    if (systemStatus?.send_auto_notifications !== undefined) {
      setSendAutoNotifications(systemStatus.send_auto_notifications);
    }
  }, [systemStatus]);

  const handleToggleLive = (e) => {
    const newValue = e.target.checked;
    setLiveOn(newValue);
    if (onSystemControl) {
      onSystemControl({ live_on: newValue });
    }
  };

  const handleToggleAutoNotifications = (e) => {
    const newValue = e.target.checked;
    setSendAutoNotifications(newValue);
    if (onSystemControl) {
      onSystemControl({ send_auto_notifications: newValue });
    }
  };

  const getStatusColor = (status) => {
    if (status === 'Healthy') return '#10b981';
    if (status === 'Degraded') return '#f59e0b';
    return '#6b7280';
  };

  return (
    <div className="dashboard-header">
      <div className="header-content">
        <div className="header-title-section">
          <div className="header-title-wrapper">
            <svg className="header-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <div className="header-title-group">
              <h1 className="header-title">
                Medication Adherence Agentic Dashboard
              </h1>
              <p className="header-subtitle">AI-powered patient adherence monitoring and risk prediction</p>
            </div>
          </div>
        </div>
        <div className="header-gear-container">
          {/* Notification preferences - hover to see toast filter options */}
          <div className="header-icons-row">
            {/* 1. Send notifications toggle */}
            <div className="header-auto-notifications-toggle">
              <label className="header-toggle-label">
                <span className="header-toggle-text">Send automatic notifications</span>
                <input
                  type="checkbox"
                  checked={sendAutoNotifications}
                  onChange={handleToggleAutoNotifications}
                  className="header-toggle-checkbox"
                />
                <span className="header-toggle-slider" />
              </label>
            </div>
            {/* 2. Notification icon (hover for toast filter) */}
            <div className="relative-inline-block group notification-prefs-group">
              <button className="gear-icon-button notification-icon-button" type="button" aria-label="Toast notification preferences">
                <svg className="notification-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 22C13.1 22 14 21.1 14 20H10C10 21.1 10.9 22 12 22Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M18 8C18 6.4087 17.3679 4.88258 16.2426 3.75736C15.1174 2.63214 13.5913 2 12 2C10.4087 2 8.88258 2.63214 7.75736 3.75736C6.63214 4.88258 6 6.4087 6 8C6 15 3 17 3 17H21C21 17 18 15 18 8Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              <div className="toast-filter-tooltip">
                <div className="toast-filter-tooltip-content">
                  <div className="toast-filter-tooltip-header">
                    <span className="toast-filter-tooltip-title">Show toasts</span>
                  </div>
                  <div className="toast-filter-tooltip-body">
                    <label className="toast-filter-radio">
                      <input
                        type="radio"
                        name="toastFilter"
                        value={TOAST_FILTER_ALL}
                        checked={toastFilter === TOAST_FILTER_ALL}
                        onChange={() => onToastFilterChange && onToastFilterChange(TOAST_FILTER_ALL)}
                      />
                      <span>All toast notifications</span>
                    </label>
                    <label className="toast-filter-radio">
                      <input
                        type="radio"
                        name="toastFilter"
                        value={TOAST_FILTER_NOTIFICATION_SENT}
                        checked={toastFilter === TOAST_FILTER_NOTIFICATION_SENT}
                        onChange={() => onToastFilterChange && onToastFilterChange(TOAST_FILTER_NOTIFICATION_SENT)}
                      />
                      <span>Only notification sent toasts</span>
                    </label>
                    <label className="toast-filter-radio">
                      <input
                        type="radio"
                        name="toastFilter"
                        value={TOAST_FILTER_APPRECIATION}
                        checked={toastFilter === TOAST_FILTER_APPRECIATION}
                        onChange={() => onToastFilterChange && onToastFilterChange(TOAST_FILTER_APPRECIATION)}
                      />
                      <span>Only appreciation toasts</span>
                    </label>
                  </div>
                  <div className="toast-filter-tooltip-arrow"></div>
                </div>
              </div>
            </div>
            <div className="relative-inline-block group">
            <button className="gear-icon-button" type="button" aria-label="Settings">
              <svg className="gear-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 15C13.6569 15 15 13.6569 15 12C15 10.3431 13.6569 9 12 9C10.3431 9 9 10.3431 9 12C9 13.6569 10.3431 15 12 15Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M19.4 15C19.2669 15.3016 19.2272 15.6362 19.286 15.9606C19.3448 16.285 19.4995 16.5843 19.73 16.82L19.79 16.88C19.976 17.0657 20.1235 17.2863 20.2241 17.5291C20.3248 17.7719 20.3766 18.0322 20.3766 18.295C20.3766 18.5578 20.3248 18.8181 20.2241 19.0609C20.1235 19.3037 19.976 19.5243 19.79 19.71C19.6043 19.896 19.3837 20.0435 19.1409 20.1441C18.8981 20.2448 18.6378 20.2966 18.375 20.2966C18.1122 20.2966 17.8519 20.2448 17.6091 20.1441C17.3663 20.0435 17.1457 19.896 16.96 19.71L16.9 19.65C16.6643 19.4195 16.365 19.2648 16.0406 19.206C15.7162 19.1472 15.3816 19.1869 15.08 19.32C14.7842 19.4468 14.532 19.6572 14.3543 19.9255C14.1766 20.1938 14.0813 20.5082 14.08 20.83V21C14.08 21.5304 13.8693 22.0391 13.4942 22.4142C13.1191 22.7893 12.6104 23 12.08 23C11.5496 23 11.0409 22.7893 10.6658 22.4142C10.2907 22.0391 10.08 21.5304 10.08 21V20.91C10.0723 20.579 9.96512 20.258 9.77251 19.9887C9.5799 19.7194 9.31074 19.5143 9 19.4C8.69838 19.2669 8.36381 19.2272 8.03941 19.286C7.71502 19.3448 7.41568 19.4995 7.18 19.73L7.12 19.79C6.93425 19.976 6.71368 20.1235 6.47088 20.2241C6.22808 20.3248 5.96783 20.3766 5.705 20.3766C5.44217 20.3766 5.18192 20.3248 4.93912 20.2241C4.69632 20.1235 4.47575 19.976 4.29 19.79C4.10405 19.6043 3.95653 19.3837 3.85588 19.1409C3.75523 18.8981 3.70343 18.6378 3.70343 18.375C3.70343 18.1122 3.75523 17.8519 3.85588 17.6091C3.95653 17.3663 4.10405 17.1457 4.29 16.96L4.35 16.9C4.58054 16.6643 4.73519 16.365 4.794 16.0406C4.85282 15.7162 4.81312 15.3816 4.68 15.08C4.55324 14.7842 4.34276 14.532 4.07447 14.3543C3.80618 14.1766 3.49179 14.0813 3.17 14.08H3C2.46957 14.08 1.96086 13.8693 1.58579 13.4942C1.21071 13.1191 1 12.6104 1 12.08C1 11.5496 1.21071 11.0409 1.58579 10.6658C1.96086 10.2907 2.46957 10.08 3 10.08H3.09C3.42099 10.0723 3.742 9.96512 4.01131 9.77251C4.28062 9.5799 4.48571 9.31074 4.6 9C4.73312 8.69838 4.77282 8.36381 4.714 8.03941C4.65519 7.71502 4.50054 7.41568 4.27 7.18L4.21 7.12C4.02405 6.93425 3.87653 6.71368 3.77588 6.47088C3.67523 6.22808 3.62343 5.96783 3.62343 5.705C3.62343 5.44217 3.67523 5.18192 3.77588 4.93912C3.87653 4.69632 4.02405 4.47575 4.21 4.29C4.39575 4.10405 4.61632 3.95653 4.85912 3.85588C5.10192 3.75523 5.36217 3.70343 5.625 3.70343C5.88783 3.70343 6.14808 3.75523 6.39088 3.85588C6.63368 3.95653 6.85425 4.10405 7.04 4.29L7.1 4.35C7.33568 4.58054 7.63502 4.73519 7.95941 4.794C8.28381 4.85282 8.61838 4.81312 8.92 4.68H9C9.29577 4.55324 9.54802 4.34276 9.72569 4.07447C9.90337 3.80618 9.99872 3.49179 10 3.17V3C10 2.46957 10.2107 1.96086 10.5858 1.58579C10.9609 1.21071 11.4696 1 12 1C12.5304 1 13.0391 1.21071 13.4142 1.58579C13.7893 1.96086 14 2.46957 14 3V3.09C14.0013 3.41179 14.0966 3.72618 14.2743 3.99447C14.452 4.26276 14.7042 4.47324 15 4.6C15.3016 4.73312 15.6362 4.77282 15.9606 4.714C16.285 4.65519 16.5843 4.50054 16.82 4.27L16.88 4.21C17.0657 4.02405 17.2863 3.87653 17.5291 3.77588C17.7719 3.67523 18.0322 3.62343 18.295 3.62343C18.5578 3.62343 18.8181 3.67523 19.0609 3.77588C19.3037 3.87653 19.5243 4.02405 19.71 4.21C19.896 4.39575 20.0435 4.61632 20.1441 4.85912C20.2448 5.10192 20.2966 5.36217 20.2966 5.625C20.2966 5.88783 20.2448 6.14808 20.1441 6.39088C20.0435 6.63368 19.896 6.85425 19.71 7.04L19.65 7.1C19.4195 7.33568 19.2648 7.63502 19.206 7.95941C19.1472 8.28381 19.1869 8.61838 19.32 8.92C19.4468 9.21577 19.6572 9.46802 19.9255 9.64569C20.1938 9.82337 20.5082 9.91872 20.83 9.92H21C21.5304 9.92 22.0391 10.1307 22.4142 10.5058C22.7893 10.8809 23 11.3896 23 11.92C23 12.4504 22.7893 12.9591 22.4142 13.3342C22.0391 13.7093 21.5304 13.92 21 13.92H20.91C20.5882 13.9213 20.2738 14.0166 20.0055 14.1943C19.7372 14.372 19.5268 14.6242 19.4 14.92Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            
            {systemStatus && (
              <div className="system-status-tooltip">
                <div className="system-status-tooltip-content">
                  <div className="system-status-tooltip-header">
                    <div className="system-status-tooltip-icon">
                      <svg viewBox="0 0 20 20" fill="currentColor">
                        <path clipRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" fillRule="evenodd"></path>
                      </svg>
                    </div>
                    <h3 className="system-status-tooltip-title">System Status</h3>
                    
                    {/* Live Monitoring Toggle - Next to System Status */}
                    <div className="system-status-tooltip-toggle-in-header">
                      <div className="live-monitoring-toggle-container">
                        <div className="neo-toggle-container">
                          <input 
                            className="neo-toggle-input" 
                            id="header-neo-toggle" 
                            type="checkbox"
                            checked={liveOn}
                            onChange={handleToggleLive}
                          />
                          <label className="neo-toggle" htmlFor="header-neo-toggle">
                            <div className="neo-track">
                              <div className="neo-background-layer"></div>
                              <div className="neo-grid-layer"></div>
                              <div className="neo-spectrum-analyzer">
                                <div className="neo-spectrum-bar"></div>
                                <div className="neo-spectrum-bar"></div>
                                <div className="neo-spectrum-bar"></div>
                                <div className="neo-spectrum-bar"></div>
                                <div className="neo-spectrum-bar"></div>
                              </div>
                              <div className="neo-track-highlight"></div>
                            </div>

                            <div className="neo-thumb">
                              <div className="neo-thumb-ring"></div>
                              <div className="neo-thumb-core">
                                <div className="neo-thumb-icon">
                                  <div className="neo-thumb-wave"></div>
                                  <div className="neo-thumb-pulse"></div>
                                </div>
                              </div>
                            </div>

                            <div className="neo-gesture-area"></div>

                            <div className="neo-interaction-feedback">
                              <div className="neo-ripple"></div>
                              <div className="neo-progress-arc"></div>
                            </div>

                            <div className="neo-status">
                              <div className="neo-status-indicator">
                                <div className="neo-status-dot"></div>
                                <div className="neo-status-text"></div>
                              </div>
                            </div>
                          </label>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="system-status-tooltip-body">
                    <div className="system-status-tooltip-item">
                      <span className="system-status-tooltip-label">Status:</span>
                      <span className="system-status-tooltip-value" style={{ color: getStatusColor(systemStatus.status) }}>
                        {systemStatus.status || 'Unknown'}
                      </span>
                    </div>
                    
                    <div className="system-status-tooltip-item">
                      <span className="system-status-tooltip-label">Refresh Interval:</span>
                      <span className="system-status-tooltip-value">
                        {systemStatus.refresh_interval || 60}s
                      </span>
                    </div>
                    <div className="system-status-tooltip-item">
                      <span className="system-status-tooltip-label">Last Sync:</span>
                      <span className="system-status-tooltip-value">
                        {systemStatus.last_sync || '—'}
                      </span>
                    </div>
                    <div className="system-status-tooltip-item">
                      <span className="system-status-tooltip-label">Agents Running:</span>
                      <span className="system-status-tooltip-value">
                        {systemStatus.agents_running || 0}
                      </span>
                    </div>
                  </div>

                  <div className="system-status-tooltip-gradient"></div>
                  <div className="system-status-tooltip-arrow"></div>
                </div>
              </div>
            )}
          </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Header;
