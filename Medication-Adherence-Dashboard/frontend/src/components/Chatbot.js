import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import './Chatbot.css';

const API_BASE = process.env.REACT_APP_API_URL || '/api';

const INITIAL_MESSAGE = {
  role: 'assistant',
  content: 'Hi! I\'m your AI assistant. Ask me about **patients**, **interventions**, **system status**, or **metrics**.'
};

function Chatbot({ dashboardData, systemStatus }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([INITIAL_MESSAGE]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const lastActivityRef = useRef(Date.now());
  const autoResetTimerRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Auto-reset after 5 minutes of inactivity
  useEffect(() => {
    if (!isOpen) return;

    const resetChat = () => {
      setMessages([INITIAL_MESSAGE]);
      lastActivityRef.current = Date.now();
    };

    const checkInactivity = () => {
      const timeSinceLastActivity = Date.now() - lastActivityRef.current;
      if (timeSinceLastActivity >= 5 * 60 * 1000) { // 5 minutes
        resetChat();
      }
    };

    // Check every minute
    autoResetTimerRef.current = setInterval(checkInactivity, 60000);

    return () => {
      if (autoResetTimerRef.current) {
        clearInterval(autoResetTimerRef.current);
      }
    };
  }, [isOpen]);

  const handleClearChat = () => {
    setMessages([INITIAL_MESSAGE]);
    lastActivityRef.current = Date.now();
  };


  const handleSend = async (e) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading) return;

    const userMessage = inputValue.trim();
    setInputValue('');
    setIsLoading(true);
    lastActivityRef.current = Date.now(); // Update activity time

    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);

    try {
      // Call the AI agent backend endpoint
      const conversationHistory = messages.map(msg => ({
        role: msg.role,
        content: msg.content
      }));
      
      const response = await axios.post(`${API_BASE}/chatbot`, {
        message: userMessage,
        history: conversationHistory
      });
      
      if (response.data && response.data.response) {
        setMessages(prev => [...prev, { role: 'assistant', content: response.data.response }]);
      } else {
        throw new Error('Invalid response from server');
      }
    } catch (error) {
      console.error('Chatbot error:', error);
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: error.response?.data?.response || 'Sorry, I encountered an error. Please try again.' 
      }]);
    } finally {
      setIsLoading(false);
      lastActivityRef.current = Date.now(); // Update activity time after response
    }
  };

  return (
    <>
      {!isOpen && (
        <button className="chatbot-toggle" onClick={() => setIsOpen(true)}>
          <div className="animated-robot-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="6" y="8" width="12" height="10" rx="2" fill="currentColor" opacity="0.9"/>
              <circle className="robot-eye robot-eye-left" cx="9.5" cy="12" r="1.5" fill="#fff"/>
              <circle className="robot-eye robot-eye-right" cx="14.5" cy="12" r="1.5" fill="#fff"/>
              <rect x="10" y="15" width="4" height="2" rx="1" fill="#fff" opacity="0.8"/>
              <rect x="4" y="6" width="4" height="2" rx="1" fill="currentColor" opacity="0.7"/>
              <rect x="16" y="6" width="4" height="2" rx="1" fill="currentColor" opacity="0.7"/>
              <rect x="8" y="18" width="2" height="3" rx="1" fill="currentColor" opacity="0.7"/>
              <rect x="14" y="18" width="2" height="3" rx="1" fill="currentColor" opacity="0.7"/>
            </svg>
          </div>
          <span>AI Assistant</span>
        </button>
      )}

      {isOpen && (
        <div className="chatbot-container">
          <div className="chatbot-header">
            <div className="chatbot-header-content">
              <div className="chatbot-icon animated-robot-icon">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect x="6" y="8" width="12" height="10" rx="2" fill="currentColor" opacity="0.9"/>
                  <circle className="robot-eye robot-eye-left" cx="9.5" cy="12" r="1.5" fill="#fff"/>
                  <circle className="robot-eye robot-eye-right" cx="14.5" cy="12" r="1.5" fill="#fff"/>
                  <rect x="10" y="15" width="4" height="2" rx="1" fill="#fff" opacity="0.8"/>
                  <rect x="4" y="6" width="4" height="2" rx="1" fill="currentColor" opacity="0.7"/>
                  <rect x="16" y="6" width="4" height="2" rx="1" fill="currentColor" opacity="0.7"/>
                  <rect x="8" y="18" width="2" height="3" rx="1" fill="currentColor" opacity="0.7"/>
                  <rect x="14" y="18" width="2" height="3" rx="1" fill="currentColor" opacity="0.7"/>
                </svg>
              </div>
              <div>
                <h3 className="chatbot-title">AI Dashboard Assistant</h3>
                <p className="chatbot-subtitle">Ask me anything about patients & dashboard</p>
              </div>
            </div>
            <div className="chatbot-header-actions">
              <button className="chatbot-clear" onClick={handleClearChat} title="Clear chat">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M3 6H5H21M8 6V4C8 3.46957 8.21071 2.96086 8.58579 2.58579C8.96086 2.21071 9.46957 2 10 2H14C14.5304 2 15.0391 2.21071 15.4142 2.58579C15.7893 2.96086 16 3.46957 16 4V6M19 6V20C19 20.5304 18.7893 21.0391 18.4142 21.4142C18.0391 21.7893 17.5304 22 17 22H7C6.46957 22 5.96086 21.7893 5.58579 21.4142C5.21071 21.0391 5 20.5304 5 20V6H19Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              <button className="chatbot-close" onClick={() => setIsOpen(false)}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
            </div>
          </div>

          <div className="chatbot-messages">
            {messages.map((message, index) => (
              <div key={index} className={`chatbot-message chatbot-message-${message.role}`}>
                <div className="chatbot-message-content">
                  {message.role === 'assistant' && (
                    <div className="chatbot-avatar animated-robot-icon">
                      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect x="6" y="8" width="12" height="10" rx="2" fill="currentColor" opacity="0.9"/>
                        <circle className="robot-eye robot-eye-left" cx="9.5" cy="12" r="1.5" fill="#fff"/>
                        <circle className="robot-eye robot-eye-right" cx="14.5" cy="12" r="1.5" fill="#fff"/>
                        <rect x="10" y="15" width="4" height="2" rx="1" fill="#fff" opacity="0.8"/>
                        <rect x="4" y="6" width="4" height="2" rx="1" fill="currentColor" opacity="0.7"/>
                        <rect x="16" y="6" width="4" height="2" rx="1" fill="currentColor" opacity="0.7"/>
                        <rect x="8" y="18" width="2" height="3" rx="1" fill="currentColor" opacity="0.7"/>
                        <rect x="14" y="18" width="2" height="3" rx="1" fill="currentColor" opacity="0.7"/>
                      </svg>
                    </div>
                  )}
                  <div className="chatbot-text">
                    {message.content.split('\n').map((line, lineIdx) => {
                      const parts = line.split('**').map((part, i) => 
                        i % 2 === 1 ? <strong key={i}>{part}</strong> : part
                      );
                      return <div key={lineIdx}>{parts}{lineIdx < message.content.split('\n').length - 1 && <br />}</div>;
                    })}
                  </div>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="chatbot-message chatbot-message-assistant">
                <div className="chatbot-message-content">
                  <div className="chatbot-avatar animated-robot-icon robot-thinking">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <rect x="6" y="8" width="12" height="10" rx="2" fill="currentColor" opacity="0.9"/>
                      <circle className="robot-eye robot-eye-left" cx="9.5" cy="12" r="1.5" fill="#fff"/>
                      <circle className="robot-eye robot-eye-right" cx="14.5" cy="12" r="1.5" fill="#fff"/>
                      <rect x="10" y="15" width="4" height="2" rx="1" fill="#fff" opacity="0.8"/>
                      <rect x="4" y="6" width="4" height="2" rx="1" fill="currentColor" opacity="0.7"/>
                      <rect x="16" y="6" width="4" height="2" rx="1" fill="currentColor" opacity="0.7"/>
                      <rect x="8" y="18" width="2" height="3" rx="1" fill="currentColor" opacity="0.7"/>
                      <rect x="14" y="18" width="2" height="3" rx="1" fill="currentColor" opacity="0.7"/>
                    </svg>
                  </div>
                  <div className="chatbot-typing">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <form className="chatbot-input-form" onSubmit={handleSend}>
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Ask about patients, interventions, or dashboard metrics..."
              className="chatbot-input"
              disabled={isLoading}
            />
            <button type="submit" className="chatbot-send" disabled={isLoading || !inputValue.trim()}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </form>
        </div>
      )}
    </>
  );
}

export default Chatbot;
