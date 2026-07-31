import React, { useState, useEffect } from 'react';
import './AgentsFlow.css';

const AGENTS_FLOW_MINIMIZED_KEY = 'dashboard-agents-flow-minimized';

/* Agents from backend/templates/agent_flow.html and agent.py pipeline */
const AGENT_STEPS = [
  { id: 'data-quality', label: 'Data Quality Agent', description: 'Validates & normalizes patient records, consent flags, refill timing', icon: '📋', color: '#1E40AF' },
  { id: 'adherence-risk', label: 'Adherence Risk Agent', description: 'Assesses risk score (0–100), labels High/Medium/Low, signals, confidence', icon: '🎯', color: '#D97706' },
  { id: 'escalation', label: 'Escalation Decision Agent', description: 'Evaluates clinician escalation from risk thresholds and refill status', icon: '⚠️', color: '#9333EA' },
  { id: 'orchestration', label: 'Orchestration Agent', description: 'Coordinates decisions, routes to specialized agents, executes actions', icon: '🎭', color: '#16A34A', subAgents: [
    { id: 'consent-routing', label: 'Consent & Routing Agent', description: 'Contact channel (SMS/Email/Pushover), validates consent' },
    { id: 'safety-throttling', label: 'Safety & Throttling Agent', description: 'Daily caps, per-patient cooldowns, policy gates' },
    { id: 'messaging', label: 'Messaging Agent', description: 'Generates personalized notification messages via AI' },
  ]},
  { id: 'audit', label: 'Audit & Compliance Agent', description: 'Logs decisions, notification status, audit trail for governance', icon: '📊', color: '#16A34A' },
];

/** All 8 agent names in pipeline order (5 main + 3 under Orchestration) */
const ALL_AGENT_NAMES = [
  'Data Quality Agent',
  'Adherence Risk Agent',
  'Escalation Decision Agent',
  'Orchestration Agent',
  'Consent & Routing Agent',
  'Safety & Throttling Agent',
  'Messaging Agent',
  'Audit & Compliance Agent',
];
const TOTAL_AGENTS = ALL_AGENT_NAMES.length;

function AgentsFlow({ systemStatus }) {
  const [minimized, setMinimized] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(AGENTS_FLOW_MINIMIZED_KEY) || 'false');
    } catch {
      return false;
    }
  });
  const [showAllNames, setShowAllNames] = useState(false);
  const agentsRunning = systemStatus?.agents_running ?? 0;
  const liveOn = systemStatus?.live_on ?? false;

  useEffect(() => {
    try {
      localStorage.setItem(AGENTS_FLOW_MINIMIZED_KEY, JSON.stringify(minimized));
    } catch (_) {}
  }, [minimized]);

  return (
    <div className={`agents-flow-section ${minimized ? 'agents-flow-section-minimized' : ''}`}>
      <div className="agents-flow-inner">
        <button
          type="button"
          className="agents-flow-header agents-flow-header-toggle"
          onClick={() => setMinimized((m) => !m)}
          aria-expanded={!minimized}
          aria-label={minimized ? 'Expand Agents Flow' : 'Minimize Agents Flow'}
        >
          <div className="agents-flow-header-left">
            <h2 className="agents-flow-title">Agents Flow</h2>
            <span className="agents-flow-total" title="Total agents in pipeline">
              Total: {TOTAL_AGENTS} agents
            </span>
            {!minimized && (
              <button
                type="button"
                className="agents-flow-names-toggle"
                onClick={(e) => { e.stopPropagation(); setShowAllNames((v) => !v); }}
                aria-expanded={showAllNames}
              >
                {showAllNames ? 'Hide names' : 'All agent names'}
              </button>
            )}
          </div>
          <span className="agents-flow-header-right">
            <span className={`agents-flow-badge ${liveOn ? 'agents-flow-badge-on' : 'agents-flow-badge-off'}`}>
              {agentsRunning} agent{agentsRunning !== 1 ? 's' : ''} running
            </span>
            <svg className="agents-flow-chevron" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <polyline points={minimized ? '6 9 12 15 18 9' : '18 15 12 9 6 15'} />
            </svg>
          </span>
        </button>
        {!minimized && showAllNames && (
          <div className="agents-flow-all-names">
            {ALL_AGENT_NAMES.map((name, i) => (
              <span key={i} className="agents-flow-name-chip">{i + 1}. {name}</span>
            ))}
          </div>
        )}
        {!minimized && (
        <div className="agents-flow-pipeline agents-flow-pipeline-vertical">
          {AGENT_STEPS.map((step, index) => (
            <React.Fragment key={step.id}>
              <div className="agents-flow-node agents-flow-node-animated" style={{ borderLeftColor: step.color || '#64748B', animationDelay: `${index * 0.12}s` }}>
                <div className="agents-flow-node-content">
                  <span className="agents-flow-node-number" style={{ background: step.color || '#64748B' }}>{index + 1}</span>
                  <span className="agents-flow-node-icon" aria-hidden>{step.icon}</span>
                  <div>
                    <span className="agents-flow-node-label">{step.label}</span>
                    {step.description && (
                      <span className="agents-flow-node-desc">{step.description}</span>
                    )}
                  </div>
                </div>
                {step.subAgents && step.subAgents.length > 0 && (
                  <div className="agents-flow-subagents">
                    {step.subAgents.map((sub, i) => (
                      <div key={sub.id} className="agents-flow-subnode">
                        <span className="agents-flow-subnode-id">{index + 1}{String.fromCharCode(97 + i)}</span>
                        <div>
                          <span className="agents-flow-subnode-label">{sub.label}</span>
                          {sub.description && <span className="agents-flow-subnode-desc">{sub.description}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              {index < AGENT_STEPS.length - 1 && (
                <div className="agents-flow-arrow agents-flow-arrow-vertical agents-flow-arrow-animated" aria-hidden style={{ animationDelay: `${(index + 1) * 0.12}s` }}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M7 10l5 5 5-5" />
                  </svg>
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
        )}
      </div>
    </div>
  );
}

export default AgentsFlow;
