import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import io from 'socket.io-client';
import Dashboard from './components/Dashboard';
import Chatbot from './components/Chatbot';
import ToastNotification from './components/ToastNotification';
import './App.css';

// Use relative URLs in development (proxy handles it) or absolute in production
const API_BASE = process.env.REACT_APP_API_URL || '/api';
const WS_URL = process.env.REACT_APP_WS_URL || (process.env.NODE_ENV === 'production' ? window.location.origin : 'http://localhost:5000');

// Default dashboard data so UI never shows blank (e.g. when API fails or exe runs without backend ready)
const DEFAULT_DASHBOARD_DATA = {
  kpis: {
    interventions_30d: 0,
    interventions_7d: 0,
    notified_unique: 0,
    responded_unique: 0,
    notified_today: 0,
    proj_savings_month: 0,
    high_risk_now: 0,
    avg_adherence_now: 0,
    hr_delta: 0,
    adh_delta: 0,
    adh_delta_weekly: null,
    adh_delta_monthly: null,
    high_risk_last_week: null,
    avg_adherence_last_month: null,
    low_count: 0,
    med_count: 0,
    high_count: 0,
    notified_push: 0,
    notified_whatsapp: 0,
    notified_sms: 0,
    notified_email: 0,
  },
  system: {
    status: 'Offline',
    live_on: false,
    refresh_interval: 300,
    last_sync: 'Never',
    agents_running: 0,
  },
  trends: {
    date_col: null,
    high_risk_last_week: null,
    avg_adherence_last_month: null,
  },
};

const DEFAULT_SYSTEM_STATUS = {
  status: 'Offline',
  live_on: false,
  send_auto_notifications: true,
  refresh_interval: 300,
  last_sync: 'Never',
  agents_running: 0,
  stats: {},
};

const TOAST_FILTER_KEY = 'toastFilter';
const TOAST_FILTER_ALL = 'all';
const TOAST_FILTER_NOTIFICATION_SENT = 'notification_sent';
const TOAST_FILTER_APPRECIATION = 'appreciation';

function isNotificationSentToast(notif) {
  const status = notif.data?.status;
  const sent = status === 'Sent' || status === 'Queued';
  return (notif.type === 'success' && sent) || (notif.type === 'high_risk' && sent);
}
/** Any toast from the automatic notification pipeline (sent, high-risk, appreciation, care routing/needs) */
function isAutomaticNotificationToast(notif) {
  const t = notif.type;
  if (t === 'success' || t === 'high_risk' || t === 'appreciation' || t === 'care_routing' || t === 'care_needs') return true;
  if (t === 'warning' && notif.message && /notification|blocked|failed/i.test(notif.message)) return true;
  return false;
}
function isAppreciationToast(notif) {
  return notif.type === 'appreciation';
}

function matchesToastFilter(notif, filter) {
  if (filter === TOAST_FILTER_ALL) return true;
  if (filter === TOAST_FILTER_NOTIFICATION_SENT) return isNotificationSentToast(notif);
  if (filter === TOAST_FILTER_APPRECIATION) return isAppreciationToast(notif);
  return true;
}

function App() {
  const [dashboardData, setDashboardData] = useState(null);
  const [systemStatus, setSystemStatus] = useState(null);
  const [trendData, setTrendData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [toastFilter, setToastFilterState] = useState(() => {
    try {
      const saved = localStorage.getItem(TOAST_FILTER_KEY);
      if (saved === TOAST_FILTER_ALL || saved === TOAST_FILTER_NOTIFICATION_SENT || saved === TOAST_FILTER_APPRECIATION) return saved;
    } catch (_) {}
    return TOAST_FILTER_ALL;
  });

  /** When false, do not add/show any automatic notification toasts */
  const sendAutoNotificationsRef = useRef(true);
  useEffect(() => {
    sendAutoNotificationsRef.current = systemStatus?.send_auto_notifications !== false;
  }, [systemStatus?.send_auto_notifications]);

  const setToastFilter = (value) => {
    setToastFilterState(value);
    try {
      localStorage.setItem(TOAST_FILTER_KEY, value);
    } catch (_) {}
  };

  // Initialize WebSocket connection (fail silently so dashboard still works without WS)
  useEffect(() => {
    let newSocket;
    try {
      // Use polling only to avoid "Invalid frame header" WebSocket errors (e.g. when accessing via IP or exe)
      newSocket = io(WS_URL, { transports: ['polling'], reconnection: true, reconnectionAttempts: 5 });
    } catch (e) {
      return;
    }
    if (!newSocket) return;

    newSocket.on('connect', () => {
      console.log('Connected to WebSocket');
    });
    newSocket.on('connect_error', (err) => {
      console.warn('WebSocket connection error (dashboard still works):', err?.message || err);
    });

    newSocket.on('notification_sent', (data) => {
      if (!sendAutoNotificationsRef.current) return;
      console.log('Notification sent event received:', data);
      const patientName = data.first && data.last 
        ? `${data.first} ${data.last}`.trim()
        : data.first || data.name || 'patient';
      
      // Show different notification types based on status
      let notificationType = 'success';
      let message = `Notification sent to ${patientName}`;
      
      if (data.status === 'Blocked') {
        notificationType = 'warning';
        message = `Notification blocked: ${data.reason || 'Contact not permitted'}`;
      } else if (data.status === 'Failed') {
        notificationType = 'warning';
        message = `Notification failed for ${patientName}`;
      } else if (data.status === 'Sent' || data.status === 'Queued') {
        notificationType = 'success';
        const channel = data.channel || 'notification';
        const channelDisplay = {
          'sms': 'SMS',
          'email': 'Email',
          'pushover': 'Pushover',
          'whatsapp': 'WhatsApp',
          'notification': 'Notification'
        }[channel] || 'Notification';
        message = `${channelDisplay} sent to ${patientName}`;
      }
      
      addNotification({
        type: notificationType,
        message: message,
        data: {
          ...data,
          status: data.status || 'Sent',
          channel: data.channel || 'notification'
        }
      });
    });

    newSocket.on('high_risk_alert', (data) => {
      if (!sendAutoNotificationsRef.current) return;
      addNotification({
        type: 'high_risk',
        message: `High-risk patient alert: ${data.name}`,
        data: data
      });
    });

    newSocket.on('patient_appreciation', (data) => {
      if (!sendAutoNotificationsRef.current) return;
      addNotification({
        type: 'appreciation',
        message: `Patient appreciation: ${data.name}`,
        data: data
      });
    });

    newSocket.on('care_routing_alert', (data) => {
      if (!sendAutoNotificationsRef.current) return;
      addNotification({
        type: 'care_routing',
        message: `Care routing required: ${data.name}`,
        data: data
      });
    });

    newSocket.on('care_needs_alert', (data) => {
      if (!sendAutoNotificationsRef.current) return;
      addNotification({
        type: 'care_needs',
        message: `Patient care needs: ${data.name}`,
        data: data
      });
    });

    return () => {
      newSocket.close();
    };
  }, []);

  const addNotification = (notification) => {
    const id = Date.now() + Math.random();
    const notificationWithId = { ...notification, id };
    setNotifications(prev => [...prev, notificationWithId]);
  };

  const removeNotification = (id) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  const fetchDashboardData = useCallback(async () => {
    try {
      const [dashboardRes, systemRes, trendRes] = await Promise.all([
        axios.get(`${API_BASE}/dashboard-data`),
        axios.get(`${API_BASE}/system-status`),
        axios.get(`${API_BASE}/trend-chart`)
      ]);
      
      setDashboardData(dashboardRes.data);
      setSystemStatus(systemRes.data);
      setTrendData(trendRes.data);
      setError(null);
    } catch (err) {
      let errorMessage = err.message;
      if (err.code === 'ECONNREFUSED' || err.message?.includes('Network Error')) {
        errorMessage = 'Cannot connect to backend. Start the app (e.g. run MedicationDashboard.exe or python main.py).';
      } else if (err.response) {
        const backendError = err.response.data?.error || err.response.data?.message || (typeof err.response.data === 'string' ? err.response.data : null);
        const rawMessage = backendError || err.response.statusText || '';
        // Friendly message when backend complains about missing date column (Excel may lack EventDate/ClaimDate/NotificationSentOn)
        if (typeof rawMessage === 'string' && rawMessage.toLowerCase().includes('date column')) {
          errorMessage = 'Trend chart unavailable: no date column in your data. Add a column named EventDate, ClaimDate, or NotificationSentOn to see trends. Dashboard metrics still work.';
        } else {
          errorMessage = `Backend error: ${err.response.status} - ${rawMessage}`;
        }
        if (!backendError && err.response.data) {
          console.error('Backend response (may not be JSON):', err.response.data);
        }
      }
      setError(errorMessage);
      console.error('Error fetching dashboard data:', err);
      // Always set default data so dashboard content is never blank (charts/KPIs show zeros)
      setDashboardData(DEFAULT_DASHBOARD_DATA);
      setSystemStatus(DEFAULT_SYSTEM_STATUS);
      setTrendData({ data: [], correlation: 0 });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
    
    // Auto-refresh every minute
    const interval = setInterval(() => {
      fetchDashboardData();
    }, 60000);
    
    return () => clearInterval(interval);
  }, [fetchDashboardData]);

  const handleSystemControl = async (updates) => {
    try {
      await axios.post(`${API_BASE}/system-control`, updates);
      fetchDashboardData();
    } catch (err) {
      console.error('Error updating system control:', err);
    }
  };

  if (loading) {
    return (
      <div className="loading">
        <div style={{ 
          fontSize: '24px', 
          fontWeight: '700', 
          background: 'linear-gradient(135deg, #667eea, #764ba2)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
          marginBottom: '20px'
        }}>
          Loading Dashboard...
        </div>
        <p style={{ color: 'var(--text-muted)', marginTop: '12px' }}>Fetching real-time data</p>
      </div>
    );
  }

  const dataSource = dashboardData?.data_source;
  const noDataFile = dataSource && dataSource.exists === false;
  const dataError = dashboardData?.data_error;

  // Never show blank: render dashboard with default data when API fails; show error as banner
  return (
    <div className="App">
      {(noDataFile || dataError) && (
        <div className="data-source-banner" role="alert" style={{
          padding: '12px 16px',
          background: 'linear-gradient(135deg, #DBEAFE 0%, #BFDBFE 100%)',
          color: '#1E40AF',
          fontSize: '14px',
          borderBottom: '1px solid #3B82F6'
        }}>
          <strong>Input file not loaded.</strong>{' '}
          {dataError || 'To see real dashboard data, put your Excel file (patients.xlsx) in the Data folder next to the app.'}
          {noDataFile && dataSource?.path && (
            <div style={{ marginTop: '8px', fontFamily: 'monospace', fontSize: '13px', wordBreak: 'break-all', fontWeight: 600 }}>
              Put file here: {dataSource.path}
            </div>
          )}
          <div style={{ marginTop: '4px', fontSize: '12px', opacity: 0.9 }}>You can set EXCEL_PATH in .env to use a different path.</div>
        </div>
      )}
      {error && !noDataFile && (
        <div className="error-banner" role="alert" style={{
          padding: '10px 16px',
          background: 'linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)',
          color: '#92400E',
          fontSize: '14px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '8px',
          borderBottom: '1px solid #F59E0B'
        }}>
          <span><strong>Limited data:</strong> {error}</span>
          <span style={{ fontSize: '12px' }}>Dashboard shows default values. Fix connection and refresh.</span>
        </div>
      )}
      <Dashboard
        dashboardData={dashboardData ?? DEFAULT_DASHBOARD_DATA}
        systemStatus={systemStatus ?? DEFAULT_SYSTEM_STATUS}
        trendData={trendData ?? { data: [], correlation: 0 }}
        onSystemControl={handleSystemControl}
        toastFilter={toastFilter}
        onToastFilterChange={setToastFilter}
      />
      
      {/* AI Chatbot - Always available */}
      <Chatbot dashboardData={dashboardData} systemStatus={systemStatus} />
      
      {/* Toast Notifications - when automatic notifications are off, hide all automatic toasts; else filter by user preference */}
      <div className="toast-container">
        {notifications
          .filter((n) => {
            if (systemStatus?.send_auto_notifications === false && isAutomaticNotificationToast(n)) return false;
            return matchesToastFilter(n, toastFilter);
          })
          .slice(0, 2)
          .map((notif) => (
          <ToastNotification
            key={notif.id}
            notification={notif}
            onClose={() => removeNotification(notif.id)}
          />
        ))}
      </div>
    </div>
  );
}

export default App;
