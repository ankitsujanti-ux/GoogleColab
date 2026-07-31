import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import './DataSnapshot.css';

const API_BASE = process.env.REACT_APP_API_URL || '/api';
const MEMBER_ID_COLS = ['Member ID', 'Member_ID'];
const PREVIEW_COUNTDOWN_SEC = 30;

function DataSnapshot() {
  const [filter, setFilter] = useState('all');
  const [maskPII, setMaskPII] = useState(true);
  const [data, setData] = useState({
    rows: [],
    columns: [],
    counts: { all: 0, low: 0, medium: 0, high: 0 },
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedRowIndex, setSelectedRowIndex] = useState(null);
  const [sendStatus, setSendStatus] = useState(null);
  const [sending, setSending] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewMessage, setPreviewMessage] = useState('');
  const [previewPayload, setPreviewPayload] = useState(null);
  const [countdown, setCountdown] = useState(PREVIEW_COUNTDOWN_SEC);
  const countdownRef = useRef(null);
  const [piiConfirmOpen, setPiiConfirmOpen] = useState(false);

  const fetchSnapshot = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSendStatus(null);
    try {
      const res = await axios.get(`${API_BASE}/patient-snapshot`, {
        params: { filter, filter_by: 'adherence', mask_pii: maskPII },
      });
      setData({
        rows: res.data.rows || [],
        columns: res.data.columns || [],
        counts: res.data.counts || { all: 0, low: 0, medium: 0, high: 0 },
      });
      setSelectedRowIndex(null);
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'Failed to load snapshot');
      setData({ rows: [], columns: [], counts: { all: 0, low: 0, medium: 0, high: 0 } });
    } finally {
      setLoading(false);
    }
  }, [filter, maskPII]);

  useEffect(() => {
    fetchSnapshot();
  }, [fetchSnapshot]);

  const getMemberIdFromRow = (row) => {
    for (const col of MEMBER_ID_COLS) {
      if (row[col] != null && String(row[col]).trim() && String(row[col]).trim() !== '••••••') {
        return String(row[col]).trim();
      }
    }
    return null;
  };

  const performSend = useCallback(async (payload) => {
    if (!payload) return;
    setSending(true);
    setSendStatus(null);
    try {
      const res = await axios.post(`${API_BASE}/send-notification`, payload);
      const d = res.data;
      if (d.success) {
        setSendStatus({ type: 'success', message: `Notification ${d.status} via ${d.channel || 'channel'}.` });
      } else {
        const errMsg = d.pushover_error || d.error || d.message || 'Send failed';
        setSendStatus({ type: 'error', message: errMsg });
      }
    } catch (err) {
      const msg = err.response?.data?.error || err.message || 'Failed to send notification';
      setSendStatus({ type: 'error', message: msg });
    } finally {
      setSending(false);
    }
  }, []);

  useEffect(() => {
    if (!previewOpen || !previewPayload) return;
    const id = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          performSend(previewPayload);
          setPreviewOpen(false);
          setPreviewPayload(null);
          setPreviewMessage('');
          return PREVIEW_COUNTDOWN_SEC;
        }
        return c - 1;
      });
    }, 1000);
    countdownRef.current = id;
    return () => {
      clearInterval(id);
      countdownRef.current = null;
    };
  }, [previewOpen, previewPayload, performSend]);

  const handleSendNotification = useCallback(async () => {
    if (selectedRowIndex == null || selectedRowIndex < 0) return;
    setSending(true);
    setSendStatus(null);
    setPreviewOpen(false);
    try {
      const row = data.rows[selectedRowIndex];
      const memberId = getMemberIdFromRow(row);
      const payload = memberId
        ? { member_id: memberId }
        : { row_index: selectedRowIndex, filter, filter_by: 'adherence' };
      const res = await axios.post(`${API_BASE}/notification-preview`, payload);
      const d = res.data;
      if (!d.success) {
        setSendStatus({ type: 'error', message: d.error || 'Could not load preview' });
        return;
      }
      setPreviewMessage(d.message || '');
      setPreviewPayload(payload);
      setCountdown(PREVIEW_COUNTDOWN_SEC);
      setPreviewOpen(true);
    } catch (err) {
      const msg = err.response?.data?.error || err.message || 'Failed to load preview';
      setSendStatus({ type: 'error', message: msg });
    } finally {
      setSending(false);
    }
  }, [selectedRowIndex, data.rows, filter]);

  const handlePreviewSendNow = useCallback(() => {
    if (countdownRef.current) clearInterval(countdownRef.current);
    countdownRef.current = null;
    if (previewPayload) {
      performSend(previewPayload);
    }
    setPreviewOpen(false);
    setPreviewPayload(null);
    setPreviewMessage('');
    setCountdown(PREVIEW_COUNTDOWN_SEC);
  }, [previewPayload, performSend]);

  const handlePreviewCancel = useCallback(() => {
    if (countdownRef.current) clearInterval(countdownRef.current);
    countdownRef.current = null;
    setPreviewOpen(false);
    setPreviewPayload(null);
    setPreviewMessage('');
    setCountdown(PREVIEW_COUNTDOWN_SEC);
  }, []);

  const hasSelection = selectedRowIndex != null && selectedRowIndex >= 0 && selectedRowIndex < data.rows.length;
  const filters = [
    { key: 'all', label: 'All', count: data.counts.all },
    { key: 'low', label: 'Low', count: data.counts.low },
    { key: 'medium', label: 'Medium', count: data.counts.medium },
    { key: 'high', label: 'High', count: data.counts.high },
  ];

  return (
    <div className="data-snapshot card chart-3d">
      <div className="data-snapshot-header">
        <h3 className="card-title">📋 Data Snapshot (Excel)</h3>
        <div className="data-snapshot-controls">
          <div className="snapshot-filter-group">
            <span className="filter-label">Adherence:</span>
            {filters.map((f) => (
              <button
                key={f.key}
                type="button"
                className={`snapshot-filter-btn ${filter === f.key ? 'active' : ''} ${f.key !== 'all' ? `filter-${f.key}` : ''}`}
                onClick={() => setFilter(f.key)}
              >
                {f.label}
                <span className="filter-count">({f.count})</span>
              </button>
            ))}
          </div>
          <div className="snapshot-actions">
            <button
              type="button"
              className="send-notification-btn"
              disabled={!hasSelection || sending}
              onClick={handleSendNotification}
              title={hasSelection ? 'Send notification to selected patient' : 'Select a row first'}
            >
              {sending ? 'Sending…' : '📤 Send notification'}
            </button>
          </div>
          <div className="pii-toggle-wrap">
            <button
              type="button"
              className={`pii-toggle-btn ${!maskPII ? 'visible' : ''}`}
              onClick={() => (maskPII ? setPiiConfirmOpen(true) : setMaskPII(true))}
              title={maskPII ? 'Click to show PII data' : 'Click to hide PII data'}
            >
              {maskPII ? (
                <>
                  <span className="pii-icon">👁‍🗨</span>
                  Show PII
                </>
              ) : (
                <>
                  <span className="pii-icon">🔒</span>
                  Hide PII
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="data-snapshot-body">
        {(error || sendStatus) && (
          <div className="data-snapshot-messages">
            {error && <div className="data-snapshot-error">{error}</div>}
            {sendStatus && (
              <div className={`data-snapshot-send-status ${sendStatus.type === 'success' ? 'success' : 'error'}`}>
                {sendStatus.message}
              </div>
            )}
          </div>
        )}

        {loading ? (
          <div className="data-snapshot-loading">Loading snapshot...</div>
        ) : data.rows.length === 0 ? (
          <div className="data-snapshot-empty">No patient data.</div>
        ) : (
          <>
            <div className="data-snapshot-table-wrap">
              <table className="data-snapshot-table">
                <thead>
                  <tr>
                    {data.columns.map((col) => (
                      <th key={col}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row, idx) => (
                    <tr
                      key={idx}
                      className={selectedRowIndex === idx ? 'selected' : ''}
                      onClick={() => setSelectedRowIndex(idx)}
                    >
                      {data.columns.map((col) => (
                        <td key={col}>{row[col] ?? ''}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="data-snapshot-hint">Click a row to select a patient, then use &quot;Send notification&quot; to send manually.</p>
          </>
        )}
      </div>

      {previewOpen && (
        <div className="notification-preview-overlay" role="dialog" aria-modal="true" aria-labelledby="preview-title">
          <div className="notification-preview-modal">
            <h3 id="preview-title" className="notification-preview-title">Preview – sending in {countdown}s</h3>
            <div className="notification-preview-message">{previewMessage}</div>
            <div className="notification-preview-actions">
              <button type="button" className="notification-preview-btn send-now" onClick={handlePreviewSendNow}>
                Send now
              </button>
              <button type="button" className="notification-preview-btn cancel" onClick={handlePreviewCancel}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {piiConfirmOpen && (
        <div className="notification-preview-overlay pii-confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="pii-confirm-title">
          <div className="notification-preview-modal pii-confirm-modal">
            <h3 id="pii-confirm-title" className="notification-preview-title">Confirm</h3>
            <p className="pii-confirm-message">Are you sure you want to see PII data?</p>
            <div className="notification-preview-actions">
              <button type="button" className="notification-preview-btn send-now" onClick={() => { setMaskPII(false); setPiiConfirmOpen(false); }}>
                Yes, show PII
              </button>
              <button type="button" className="notification-preview-btn cancel" onClick={() => setPiiConfirmOpen(false)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default DataSnapshot;
