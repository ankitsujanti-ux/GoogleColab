import React, { useEffect, useRef, useState } from 'react';
import './ToastNotification.css';

const POPUP_AUTO_CLOSE_MS = 5000;
const FADE_OUT_MS = 300;

const WAVE_PATH = 'M0,256L11.4,240C22.9,224,46,192,69,192C91.4,192,114,224,137,234.7C160,245,183,235,206,213.3C228.6,192,251,160,274,149.3C297.1,139,320,149,343,181.3C365.7,213,389,267,411,282.7C434.3,299,457,277,480,250.7C502.9,224,526,192,549,181.3C571.4,171,594,181,617,208C640,235,663,277,686,256C708.6,235,731,149,754,122.7C777.1,96,800,128,823,165.3C845.7,203,869,245,891,224C914.3,203,937,117,960,112C982.9,107,1006,181,1029,197.3C1051.4,213,1074,171,1097,144C1120,117,1143,107,1166,133.3C1188.6,160,1211,224,1234,218.7C1257.1,213,1280,139,1303,133.3C1325.7,128,1349,192,1371,192C1394.3,192,1417,128,1429,96L1440,64L1440,320L1428.6,320C1417.1,320,1394,320,1371,320C1348.6,320,1326,320,1303,320C1280,320,1257,320,1234,320C1211.4,320,1189,320,1166,320C1142.9,320,1120,320,1097,320C1074.3,320,1051,320,1029,320C1005.7,320,983,320,960,320C937.1,320,914,320,891,320C868.6,320,846,320,823,320C800,320,777,320,754,320C731.4,320,709,320,686,320C662.9,320,640,320,617,320C594.3,320,571,320,549,320C525.7,320,503,320,480,320C457.1,320,434,320,411,320C388.6,320,366,320,343,320C320,320,297,320,274,320C251.4,320,229,320,206,320C182.9,320,160,320,137,320C114.3,320,91,320,69,320C45.7,320,23,320,11,320L0,320Z';

const CLOSE_PATH = 'M11.7816 4.03157C12.0062 3.80702 12.0062 3.44295 11.7816 3.2184C11.5571 2.99385 11.193 2.99385 10.9685 3.2184L7.50005 6.68682L4.03164 3.2184C3.80708 2.99385 3.44301 2.99385 3.21846 3.2184C2.99391 3.44295 2.99391 3.80702 3.21846 4.03157L6.68688 7.49999L3.21846 10.9684C2.99391 11.193 2.99391 11.557 3.21846 11.7816C3.44301 12.0061 3.80708 12.0061 4.03164 11.7816L7.50005 8.31316L10.9685 11.7816C11.193 12.0061 11.5571 12.0061 11.7816 11.7816C12.0062 11.557 12.0062 11.193 11.7816 10.9684L8.31322 7.49999L11.7816 4.03157Z';

/* Channel icons (SVG paths) - used when notification is "sent" so we show which channel was used */
const CHANNEL_ICONS = {
  pushover: (
    <path fill="currentColor" d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-2v1a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V4.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2zM7.5 13A1.5 1.5 0 0 0 6 14.5V18h3v-3.5A1.5 1.5 0 0 0 7.5 13zm9 0a1.5 1.5 0 0 0-1.5 1.5V18h3v-3.5a1.5 1.5 0 0 0-1.5-1.5z" />
  ),
  whatsapp: (
    <path fill="currentColor" d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
  ),
  sms: (
    <path fill="currentColor" d="M2 3a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V3zm3.5 2v.5h9V5h-9zm0 2.5v.5h9v-.5h-9zm0 2.5v.5h6v-.5h-6z" />
  ),
  email: (
    <path fill="currentColor" d="M2 4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2H2zm2.08 0L12 9.75 19.92 4H4.08zM2 6.25l7.5 5.5L2 17.25V6.25zm8.5 5.5l8.5 5.5V6.25l-8.5 5.5z" />
  ),
};

const DEFAULT_INFO_ICON = (
  <>
    <path d="M13 7.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm-3 3.75a.75.75 0 0 1 .75-.75h1.5a.75.75 0 0 1 .75.75v4.25h.75a.75.75 0 0 1 0 1.5h-3a.75.75 0 0 1 0-1.5h.75V12h-.75a.75.75 0 0 1-.75-.75Z" />
    <path d="M12 1c6.075 0 11 4.925 11 11s-4.925 11-11 11S1 18.075 1 12 5.925 1 12 1ZM2.5 12a9.5 9.5 0 0 0 9.5 9.5 9.5 9.5 0 0 0 9.5-9.5A9.5 9.5 0 0 0 12 2.5 9.5 9.5 0 0 0 2.5 12Z" />
  </>
);

/** Emoji icons per toast type (used instead of default SVG) */
function getToastEmojiIcon(notification) {
  const type = notification.type;
  const data = notification.data || {};
  const isNotificationSent =
    (type === 'success' && (data.status === 'Sent' || data.status === 'Queued')) ||
    (type === 'high_risk' && (data.status === 'Sent' || data.status === 'Queued'));

  if (type === 'care_needs') return '🩺';
  if (type === 'care_routing') {
    const target = (data.routing_target || '').toLowerCase();
    if (target.includes('hospital')) return '➡️🏥';
    return '➡️👨‍⚕️'; // doctor / clinician
  }
  if (isNotificationSent) return '🔔';
  if (type === 'appreciation') return '👏';
  return null; // fallback: use SVG
}

function ToastNotification({ notification, onClose }) {
  const [isVisible, setIsVisible] = useState(true);
  const onCloseRef = useRef(onClose);
  const closeTimerRef = useRef(null);
  onCloseRef.current = onClose;

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(false);
      closeTimerRef.current = setTimeout(() => {
        onCloseRef.current();
      }, FADE_OUT_MS);
    }, POPUP_AUTO_CLOSE_MS);
    return () => {
      clearTimeout(timer);
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    };
  }, []); // Run once on mount so the 5s countdown is not reset by parent re-renders

  const getTitle = () => {
    switch (notification.type) {
      case 'high_risk':
        if (notification.data?.status === 'Sent' || notification.data?.status === 'Queued') {
          return 'Notification Sent';
        }
        return 'High-Risk Patient Alert';
      case 'appreciation':
        return 'Patient Appreciation';
      case 'care_routing':
        return 'Care Routing Required';
      case 'care_needs':
        return 'Patient Care Needs';
      case 'success':
        return 'Success';
      case 'warning':
        return 'Warning';
      default:
        return 'Notification';
    }
  };

  const getMessage = () => {
    if (notification.type === 'high_risk') {
      const fullName = notification.data?.full_name ||
        (notification.data?.first_name && notification.data?.last_name
          ? `${notification.data.first_name} ${notification.data.last_name}`.trim()
          : notification.data?.name || 'Patient');
      const adherence = notification.data?.adherence_percentage || 'N/A';
      const channel = notification.data?.channel_display || 'Notification';
      if (notification.data?.status === 'Sent' || notification.data?.status === 'Queued') {
        return `${fullName}, ${adherence} ${channel} sent`;
      }
      return `${fullName} - Risk Score: ${notification.data?.risk_score || 'N/A'}`;
    } else if (notification.type === 'success') {
      const fullName = notification.data?.first && notification.data?.last
        ? `${notification.data.first} ${notification.data.last}`.trim()
        : notification.data?.first || notification.data?.name || 'patient';
      const channel = notification.data?.channel || 'notification';
      const channelDisplay = { sms: 'SMS', email: 'Email', pushover: 'Notification', whatsapp: 'WhatsApp' }[channel] || 'Notification';
      return `${fullName} - ${channelDisplay} sent successfully`;
    } else if (notification.type === 'appreciation') {
      const fullName = notification.data?.first && notification.data?.last
        ? `${notification.data.first} ${notification.data.last}`.trim()
        : notification.data?.first || notification.data?.name || 'Patient';
      return `${fullName} - ${notification.data?.reason || 'Good adherence'}`;
    } else if (notification.type === 'care_routing') {
      return `${notification.data?.name || 'Patient'} - Route to ${notification.data?.routing_target || 'clinician'}`;
    } else if (notification.type === 'care_needs') {
      return `${notification.data?.name || 'Patient'} - ${notification.data?.priority || 'medium'} priority care needed`;
    }
    return notification.message || 'Notification';
  };

  const getDetails = () => {
    if (notification.type === 'high_risk' && notification.data?.needs_clinician) {
      return `Requires clinician attention: ${notification.data.escalation_reason || 'High risk'}`;
    } else if (notification.type === 'care_routing') {
      return notification.data?.recommended_action || '';
    } else if (notification.type === 'care_needs' && notification.data?.refill_assistance) {
      return `Refill assistance: ${notification.data.refill_assistance}`;
    }
    return null;
  };

  const subText = getDetails() ? `${getMessage()} · ${getDetails()}` : getMessage();

  const handleClose = () => {
    setIsVisible(false);
    setTimeout(() => onClose(), FADE_OUT_MS);
  };

  const isNotificationSentToast =
    (notification.type === 'success' && (notification.data?.status === 'Sent' || notification.data?.status === 'Queued')) ||
    (notification.type === 'high_risk' && (notification.data?.status === 'Sent' || notification.data?.status === 'Queued'));
  const channel = (notification.data?.channel || '').toLowerCase().replace(/\s/g, '');
  const channelKey = channel === 'notification' || channel === 'apppush' || channel === 'push' ? 'pushover' : channel;
  const channelIcon = isNotificationSentToast && CHANNEL_ICONS[channelKey] ? CHANNEL_ICONS[channelKey] : DEFAULT_INFO_ICON;

  const emojiIcon = getToastEmojiIcon(notification);

  if (!isVisible) return null;

  return (
    <div className={`toast-card toast-${notification.type} ${isVisible ? 'toast-visible' : ''} ${isNotificationSentToast && channelKey ? `toast-channel-${channelKey}` : ''}`}>
      <svg className="toast-wave" viewBox="0 0 1440 320" xmlns="http://www.w3.org/2000/svg" fillOpacity={1}>
        <path d={WAVE_PATH} />
      </svg>
      <div className="toast-icon-container">
        {emojiIcon ? (
          <span className="toast-icon-emoji" aria-hidden="true">{emojiIcon}</span>
        ) : (
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" strokeWidth={0} fill="currentColor" stroke="currentColor" className="toast-icon-svg">
            {channelIcon}
          </svg>
        )}
      </div>
      <div className="toast-message-text-container">
        <p className="toast-message-text">{getTitle()}</p>
        <p className="toast-sub-text">{subText}</p>
      </div>
      <button type="button" className="toast-cross-btn" onClick={handleClose} aria-label="Close">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 15 15" strokeWidth={0} fill="none" stroke="currentColor" className="toast-cross-icon">
          <path fill="currentColor" d={CLOSE_PATH} clipRule="evenodd" fillRule="evenodd" />
        </svg>
      </button>
    </div>
  );
}

export default ToastNotification;
