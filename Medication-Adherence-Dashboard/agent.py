from __future__ import annotations
import os
import json
import requests
import pandas as pd
from openai import OpenAI
from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    PUSHOVER_API_TOKEN,
    PUSHOVER_USER_KEY,
    PREFER_PUSHOVER,
    THRESHOLD_LOW,
    THRESHOLD_MED,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
    TWILIO_WHATSAPP_FROM,
    SENDGRID_API_KEY,
    SENDER_EMAIL,
)
# Create OpenAI client only if key is available (prevents crashes)
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def _ai_enabled() -> bool:
    return client is not None


def build_messages(system_content=None, user_content=None, assistant_content=None, conversation_history=None):
    """
    Build messages list in OpenAI API format.
    Standard structure: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
    """
    messages = []
    if system_content:
        messages.append({"role": "system", "content": system_content})
    if conversation_history:
        for msg in conversation_history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role and content is not None:
                messages.append({"role": role, "content": str(content)})
    if assistant_content:
        messages.append({"role": "assistant", "content": assistant_content})
    if user_content:
        messages.append({"role": "user", "content": user_content})
    return messages


def openai_chat(messages, model=None, **kwargs):
    """
    Call OpenAI chat completions with messages.
    messages: list of {"role": "system"|"user"|"assistant", "content": "..."}
    Returns: response.choices[0].message.content.strip()
    """
    if client is None:
        raise RuntimeError("OpenAI client not configured (OPENAI_API_KEY)")
    model = model or OPENAI_MODEL
    response = client.chat.completions.create(model=model, messages=messages, **kwargs)
    return response.choices[0].message.content.strip()


def user_prompt_for_content(title, text, kind="website"):
    """
    Build user message for summarizing content (e.g. website).
    Use with build_messages + openai_chat for a standard summary agent:
      messages = build_messages(
          system_content="You provide short summaries in markdown. Include news/announcements if present.",
          user_content=user_prompt_for_content(website.title, website.text),
      )
      summary = openai_chat(messages)
    """
    return (
        f"You are looking at a {kind} titled: {title}\n\n"
        "The contents are as follows; please provide a short summary in markdown. "
        "If it includes news or announcements, summarize these too.\n\n"
        f"{text}"
    )


def build_adherence_message(row) -> str:
    """Build a short adherence reminder message for SMS/WhatsApp/Email/Call (no AI). Includes nearest pharmacy table by city."""
    from pharmacy import get_pharmacy_for_city, format_pharmacy_table
    name = _get_value(row, "Patient Name", "Patient_Name", default="Patient")
    medication = _get_value(row, "Medication Name", "Medication_Name", default="your medication")
    adherence = _coerce_float(
        _get_value(row, "Adherence Percentage", "Adeherence Percentage", default=0), default=0.0
    )
    city = _get_value(row, "City", "Patient City", "city", default=None)
    pharmacy = get_pharmacy_for_city(city)
    pharmacy_table = format_pharmacy_table(pharmacy)
    return (
        f"Hi {name}, this is a medication adherence reminder. "
        f"You are on {medication}. Your current adherence is {adherence:.0f} percent. "
        f"Please refill your medication if needed.\n\n{pharmacy_table}\n\nThank you."
    )


def notify_patient(row, via_pushover: bool = False) -> dict:
    """Return adherence message with nearest pharmacy table (by city). Optionally send via Pushover. No AI – always uses build_adherence_message so the pharmacy table is never replaced by 'your local pharmacy'."""
    message = build_adherence_message(row)
    if not via_pushover:
        return {"message": message}
    if not PUSHOVER_API_TOKEN or not PUSHOVER_USER_KEY:
        return {"message": message, "pushover_error": "Pushover credentials not configured"}
    medication = row.get("Medication Name") or row.get("Medication_Name") or "Medication"
    try:
        pushover_result = send_pushover_message(
            user_key=PUSHOVER_USER_KEY,
            token=PUSHOVER_API_TOKEN,
            title=f"{medication} Adherence Reminder",
            message=message,
        )
        if "error" not in pushover_result:
            return {"message": message, "pushover": pushover_result.get("request", "Sent")}
        return {"message": message, "pushover_error": pushover_result.get("error", "Unknown error")}
    except Exception as e:
        return {"message": message, "pushover_error": str(e)}


# ===============================
# Agentic AI: Additional Agents
# ===============================

def _get_value(row: dict, *keys, default=None):
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return default


def _coerce_float(v, default=None):
    try:
        return float(v)
    except Exception:
        return default


# --- Helper: truthiness parser for consent flags ---
def _truthy(v) -> bool:
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"true", "1", "yes", "y"}


def _compute_consent_ok(row: dict):
    """Compute effective consent: Opt-out wins; otherwise any explicit opt-in is OK; None if unknown."""
    # Check opt-out columns (compact and Excel-style with spaces)
    opt_out = (
        _truthy(row.get("OptOut")) or _truthy(row.get("Opt Out"))
        or _truthy(row.get("DoNotContact")) or _truthy(row.get("Do Not Contact"))
        or _truthy(row.get("DNC"))
    )
    if opt_out:
        return False
    consent_cols = ["Consent", "ConsentFlag", "OptIn", "PatientConsent"]
    seen = None
    for c in consent_cols:
        if c in row and row[c] is not None:
            val = _truthy(row[c])
            seen = val if seen is None else (seen or val)
    # If we never saw any consent column, return None (unknown)
    return seen if seen is not None else None


def validate_and_normalize_row(row) -> dict:
    """Data Quality Agent: normalize & validate a patient record for downstream agents."""
    issues, warnings = [], []

    member_id = _get_value(row, "Member ID", "Member_ID")
    if member_id is None:
        issues.append("Missing Member ID")
        member_id = _get_value(row, "id", default="UNKNOWN")

    name = _get_value(row, "Patient Name", "Patient_Name", default="Patient")
    medication = _get_value(row, "Medication Name", "Medication_Name", default="")
    contact = _get_value(row, "Patient Contact", "PatientContact")
    email = _get_value(row, "Patient EmailID", "PatientEmailID")

    if not contact and not email:
        warnings.append("No contact channel available (phone/email)")

    adherence = _get_value(row, "Adherence Percentage", "Adeherence Percentage", "PDC Percentage", default=0)
    adherence = _coerce_float(adherence, default=0.0)

    refill_days = _coerce_float(_get_value(row, "Refill Days", "RefillDays", "Refill_Days"), default=None)
    if refill_days is not None:
        days_until_refill = refill_days
        refill_due = refill_days < 7
    else:
        days_until_refill = None
        refill_due = False
        if "Refill Days" not in row and "RefillDays" not in row and "Refill_Days" not in row:
            warnings.append("Refill timing unknown (optional Refill Days column not present)")

    # NEW: Consent OK
    consent_ok = _compute_consent_ok(row)

    # NEW: Last notification timestamp
    notif_ts = None
    if "NotificationSentOn" in row and row["NotificationSentOn"] is not None:
        try:
            notif_ts = pd.to_datetime(row["NotificationSentOn"], errors="coerce")
        except Exception:
            notif_ts = None

    notification_channel = _get_value(row, "NotificationChannel", "Notification_Channel", "Notification Channel", default="")
    appreciation_sent_on = row.get("AppreciationSentOn") if "AppreciationSentOn" in row else None
    if appreciation_sent_on is not None:
        try:
            appreciation_sent_on = pd.to_datetime(appreciation_sent_on, errors="coerce")
        except Exception:
            appreciation_sent_on = None

    city = _get_value(row, "City", "Patient City", "city", default="")
    try:
        if city is None or (hasattr(city, "__float__") and str(city) == "nan") or not str(city).strip() or str(city).strip().lower() in ("nan", "none", "n/a", "<na>"):
            city = ""
        else:
            city = str(city).strip()
    except Exception:
        city = ""

    clean = {
        "Member ID": str(member_id),
        "Patient Name": name,
        "Medication Name": medication,
        "Patient Contact": contact,
        "Patient EmailID": email,
        "Adherence Percentage": adherence,
        "Adeherence Percentage": adherence,
        "days_until_refill": days_until_refill,
        "refill_due": refill_due,
        "ConsentOK": consent_ok,
        "NotificationSentOn": notif_ts,
        "NotificationChannel": notification_channel,
        "AppreciationSentOn": appreciation_sent_on,
        "City": city if city else "",
    }

    return {"clean": clean, "issues": issues, "warnings": warnings, "agent": "Data Quality Agent"}


def assess_adherence_risk(row) -> dict:
    """Adherence Risk Agent: returns risk score/label + signals + confidence."""
    signals = []

    adherence = _coerce_float(_get_value(row, "Adherence Percentage", "Adeherence Percentage", "PDC Percentage", default=0), default=0.0)
    refill_due = bool(_get_value(row, "refill_due", default=False))
    days_until_refill = _get_value(row, "days_until_refill")
    days_until_refill = _coerce_float(days_until_refill, default=None) if days_until_refill is not None else None

    risk = max(0.0, 100.0 - adherence)
    signals.append(f"Adherence at {adherence:.1f}%")

    if adherence < THRESHOLD_LOW:
        risk += 10
        signals.append(f"Below low threshold ({THRESHOLD_LOW}%)")
    elif adherence < THRESHOLD_MED:
        risk += 3
        signals.append(f"Below medium threshold ({THRESHOLD_MED}%)")

    if refill_due:
        risk += 15
        signals.append("Refill due within 7 days")

    if days_until_refill is not None:
        if days_until_refill <= 0:
            risk += 20
            signals.append("Refill overdue")
        elif days_until_refill <= 3:
            risk += 10
            signals.append("Refill imminent (≤3 days)")
        elif days_until_refill <= 7:
            risk += 5
            signals.append("Refill soon (≤7 days)")

    risk = max(0.0, min(100.0, risk))
    if risk >= 70:
        label = "High"
    elif risk >= 40:
        label = "Medium"
    else:
        label = "Low"

    confidence = round(min(0.95, 0.55 + (risk / 200.0)), 2)

    return {
        "risk_score": int(round(risk)),
        "risk_label": label,
        "signals": signals,
        "confidence": confidence,
        "agent": "Adherence Risk Agent",
    }


# ----------------------------------------------------------------------
# Agent 1: Consent & Channel Routing Agent
# ----------------------------------------------------------------------

def determine_contact_route(row: dict) -> dict:
    """
    Decide the outreach channel and whether contact is permitted.

    Returns:
      {
        "allowed": bool,
        "reason": str,
        "channel": "sms" | "email" | "pushover" | "call" | "whatsapp" | "none",
        "address": str | None,
        "agent": "Consent & Routing Agent"
      }
    """
    consent_ok = row.get("ConsentOK")
    if consent_ok is None:
        consent_ok = _compute_consent_ok(row)

    # Explicitly blocked
    if consent_ok is False:
        return {
            "allowed": False,
            "reason": "Contact not permitted (opt-out / Do Not Contact)",
            "channel": "none",
            "address": None,
            "agent": "Consent & Routing Agent",
        }

    # Check NotificationChannel column first - if "App Push" / "App Notify" (or variants), use Pushover only (do not fall back to SMS)
    notification_channel = _get_value(row, "NotificationChannel", "Notification_Channel", "Notification Channel", default="")
    _nc_lower = (str(notification_channel).strip().lower() if notification_channel else "")
    _app_channel_values = ["app push", "apppush", "push", "app notify", "appnotify", "notification", "notify"]
    if _nc_lower in _app_channel_values:
        pushover_configured = bool(PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY)
        if pushover_configured:
            return {
                "allowed": True if consent_ok in (True, None) else False,
                "reason": "App/Notify via NotificationChannel column",
                "channel": "pushover",
                "address": PUSHOVER_USER_KEY,
                "agent": "Consent & Routing Agent",
            }
        else:
            return {
                "allowed": False,
                "reason": "NotificationChannel set to App Notify/Push but Pushover not configured",
                "channel": "none",
                "address": None,
                "agent": "Consent & Routing Agent",
            }

    # If NotificationChannel is "call", use Twilio voice call (requires Patient Contact)
    _is_call = _nc_lower == "call" or (_nc_lower.startswith("call") and "callback" not in _nc_lower and "recall" not in _nc_lower)
    if _is_call:
        phone = _get_value(row, "Patient Contact", "Patient Contact Number", "PatientContact", default="")
        phone = str(phone).strip() if phone else ""
        if phone:
            return {
                "allowed": True if consent_ok in (True, None) else False,
                "reason": "Voice call via NotificationChannel column",
                "channel": "call",
                "address": phone,
                "agent": "Consent & Routing Agent",
            }
        return {
            "allowed": False,
            "reason": "NotificationChannel set to Call but no Patient Contact number",
            "channel": "none",
            "address": None,
            "agent": "Consent & Routing Agent",
        }

    # If NotificationChannel is "SMS" or "Text", use Twilio SMS (requires Patient Contact)
    if _nc_lower in ("sms", "text"):
        phone = _get_value(row, "Patient Contact", "Patient Contact Number", "PatientContact", default="")
        phone = str(phone).strip() if phone else ""
        if phone:
            return {
                "allowed": True if consent_ok in (True, None) else False,
                "reason": "SMS via NotificationChannel column (Twilio)",
                "channel": "sms",
                "address": phone,
                "agent": "Consent & Routing Agent",
            }
        return {
            "allowed": False,
            "reason": "NotificationChannel set to SMS but no Patient Contact number",
            "channel": "none",
            "address": None,
            "agent": "Consent & Routing Agent",
        }

    # If NotificationChannel is "WhatsApp", use Twilio WhatsApp (requires Patient Contact)
    if _nc_lower in ("whatsapp", "whats app"):
        phone = _get_value(row, "Patient Contact", "Patient Contact Number", "PatientContact", default="")
        phone = str(phone).strip() if phone else ""
        if phone:
            return {
                "allowed": True if consent_ok in (True, None) else False,
                "reason": "WhatsApp via NotificationChannel column (Twilio)",
                "channel": "whatsapp",
                "address": phone,
                "agent": "Consent & Routing Agent",
            }
        return {
            "allowed": False,
            "reason": "NotificationChannel set to WhatsApp but no Patient Contact number",
            "channel": "none",
            "address": None,
            "agent": "Consent & Routing Agent",
        }

    # If NotificationChannel is "Email", use email (requires Patient EmailID)
    if _nc_lower in ("email", "e-mail"):
        email = _get_value(row, "Patient EmailID", "Patient_EmailID", "PatientEmailID", default="")
        email = str(email).strip() if email else ""
        if email:
            return {
                "allowed": True if consent_ok in (True, None) else False,
                "reason": "Email via NotificationChannel column",
                "channel": "email",
                "address": email,
                "agent": "Consent & Routing Agent",
            }
        return {
            "allowed": False,
            "reason": "NotificationChannel set to Email but no Patient EmailID",
            "channel": "none",
            "address": None,
            "agent": "Consent & Routing Agent",
        }

    # When PREFER_PUSHOVER is set, send to your mobile via Pushover (so you receive notifications on your device)
    pushover_configured = bool(PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY)
    if PREFER_PUSHOVER and pushover_configured:
        return {
            "allowed": True if consent_ok in (True, None) else False,
            "reason": "Pushover (PREFER_PUSHOVER=true – deliver to your app)",
            "channel": "pushover",
            "address": PUSHOVER_USER_KEY,
            "agent": "Consent & Routing Agent",
        }

    # Channel priority: SMS -> Email -> Pushover -> None
    phone = row.get("Patient Contact")
    email = row.get("Patient EmailID")

    if phone:
        return {
            "allowed": True if consent_ok in (True, None) else False,
            "reason": "SMS via Patient Contact" if consent_ok in (True, None) else "Consent unknown/blocked",
            "channel": "sms",
            "address": str(phone),
            "agent": "Consent & Routing Agent",
        }
    if email:
        return {
            "allowed": True if consent_ok in (True, None) else False,
            "reason": "Email via Patient EmailID" if consent_ok in (True, None) else "Consent unknown/blocked",
            "channel": "email",
            "address": str(email),
            "agent": "Consent & Routing Agent",
        }

    # Fallback to Pushover if configured, else none
    pushover_configured = bool(PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY)
    if pushover_configured:
        return {
            "allowed": True if consent_ok in (True, None) else False,
            "reason": "Pushover fallback",
            "channel": "pushover",
            "address": PUSHOVER_USER_KEY,
            "agent": "Consent & Routing Agent",
        }

    return {
        "allowed": False,
        "reason": "No contact channel available",
        "channel": "none",
        "address": None,
        "agent": "Consent & Routing Agent",
    }


# ----------------------------------------------------------------------
# Agent 2: Safety & Throttling Agent
# ----------------------------------------------------------------------

def enforce_policy_and_throttle(row: dict, policy_context: dict | None = None) -> dict:
    """
    Enforce daily outreach caps and per-patient cooldowns.

    policy_context expected keys:
      - today_sent (int): count of distinct patients already notified today
      - cap (int): OUTREACH_MAX_PER_DAY
      - cooldown_days (int): per-patient minimum days between sends
      - last_sent_ts (pd.Timestamp | None): the patient's last NotificationSentOn timestamp (if any)

    Returns:
      {
        "allowed": bool,
        "reasons": list[str],
        "agent": "Safety & Throttling Agent"
      }
    """
    reasons = []
    allowed = True
    pc = policy_context or {}
    cap = int(pc.get("cap", int(os.getenv("OUTREACH_MAX_PER_DAY", "100"))))
    today_sent = int(pc.get("today_sent", 0))
    cooldown_days = int(pc.get("cooldown_days", int(os.getenv("OUTREACH_COOLDOWN_DAYS", "2"))))
    last_sent_ts = pc.get("last_sent_ts", None)

    # Daily cap
    if today_sent >= cap:
        allowed = False
        reasons.append(f"Daily throttle reached ({today_sent}/{cap})")

    # Governance: only one contact per patient per day (notification OR appreciation)
    if allowed and _any_contact_sent_today(row):
        allowed = False
        reasons.append("Governance: already sent today (notification or appreciation; one per day)")

    # Per-patient cooldown (additional: no send within cooldown_days)
    if allowed and last_sent_ts is not None:
        try:
            now = pd.Timestamp.now()
            delta_days = (now - pd.to_datetime(last_sent_ts)).days
            if delta_days < cooldown_days:
                allowed = False
                reasons.append(f"Cooldown active ({delta_days}/{cooldown_days} days)")
        except Exception:
            pass

    return {"allowed": allowed, "reasons": reasons, "agent": "Safety & Throttling Agent"}


def _appreciation_sent_today(row: dict) -> bool:
    """Governance: True if appreciation was already sent today for this patient."""
    ts = row.get("AppreciationSentOn")
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return False
    try:
        t = pd.to_datetime(ts, errors="coerce")
        if pd.isna(t):
            return False
        return t.normalize() == pd.Timestamp.now().normalize()
    except Exception:
        return False


def _any_contact_sent_today(row: dict) -> bool:
    """Governance: True if either a notification OR an appreciation was already sent today (one contact per patient per day)."""
    today = pd.Timestamp.now().normalize()
    for key in ("NotificationSentOn", "AppreciationSentOn"):
        ts = row.get(key)
        if ts is None or (isinstance(ts, float) and pd.isna(ts)):
            continue
        try:
            t = pd.to_datetime(ts, errors="coerce")
            if pd.notna(t) and t.normalize() == today:
                return True
        except Exception:
            pass
    return False


def orchestrate_refill_and_notify(row, send: bool = False, policy_context: dict | None = None, previous_state: dict | None = None) -> dict:
    """Orchestration Agent: plans autonomous decisions; optionally sends notifications."""
    # --- Compute risk
    risk = assess_adherence_risk(row)
    adherence = _coerce_float(_get_value(row, "Adherence Percentage", "Adeherence Percentage", default=0), default=0.0)
    refill_due = bool(_get_value(row, "refill_due", default=False))
    days_until_refill = _get_value(row, "days_until_refill")
    days_until_refill = _coerce_float(days_until_refill, default=None) if days_until_refill is not None else None

    # --- NEW: Sentiment & Behavior Analysis
    sentiment_analysis = analyze_patient_sentiment_and_behavior(row)
    
    # --- NEW: Patient Appreciation Check
    appreciation = check_and_appreciate_refilled_patient(row, previous_state=previous_state)
    
    # --- NEW: Enhanced Care Routing (can include issue_analysis if available)
    issue_analysis = None  # Can be passed in if patient response was analyzed
    care_routing = determine_care_routing(row, risk_assessment=risk, issue_analysis=issue_analysis)
    
    # --- NEW: Patient Care Needs Identification
    care_needs = identify_patient_care_needs(row, risk_assessment=risk, sentiment_analysis=sentiment_analysis)

    # --- Decide actions: use same high-risk definition as dashboard (low adherence AND refill days <= 7)
    actions = []
    refill_soon_or_over = days_until_refill is not None and days_until_refill <= 7
    dashboard_high_risk = (adherence < THRESHOLD_LOW) and refill_soon_or_over
    needs_clinician = care_routing.get("needs_routing", False)
    escalation_reason = care_routing.get("routing_reason", None)
    
    if dashboard_high_risk or risk["risk_label"] == "High":
        actions.append("notify_patient")
    
    # Use care routing agent's decision for escalation
    if care_routing.get("needs_routing", False):
        actions.append("escalate_care_team")
        needs_clinician = True
        escalation_reason = care_routing.get("routing_reason", "High risk patient")
    
    # Appreciation action
    if appreciation.get("should_appreciate", False):
        actions.append("appreciate_patient")

    if risk["risk_label"] == "Medium":
        actions.append("send_nudge")
    else:
        if "no_action" not in actions:
            actions.append("no_action")

    # --- Preview/summary message: use adherence message so it always includes pharmacy table (for Data Snapshot preview and chatbot)
    message = build_adherence_message(row)

    # --- NEW: Consent & Routing + Policy & Throttling gates
    route = determine_contact_route(row)
    policy_gate = enforce_policy_and_throttle(row, policy_context=policy_context)

    # Decide if we are allowed to send now (governance: no duplicate notification or appreciation today)
    can_send = ("notify_patient" in actions) and route.get("allowed", False) and policy_gate.get("allowed", False)
    can_appreciate = ("appreciate_patient" in actions) and route.get("allowed", False) and not _any_contact_sent_today(row)

    result = {
        "actions": actions,
        "risk": risk,
        "message": message,
        "status": "Planned",
        "decided_by": "Orchestration Agent",
        "autonomous_decision": True,
        "route": route,
        "policy_gate": policy_gate,
        "pushover": None,
        "pushover_error": None,
        # NEW: Enhanced agent outputs
        "sentiment_analysis": sentiment_analysis,
        "appreciation": appreciation,
        "care_routing": care_routing,
        "care_needs": care_needs,
        "needs_clinician": needs_clinician,
        "escalation_reason": escalation_reason,
    }

    # --- Execute: Call (Twilio), SMS (Twilio), WhatsApp (Twilio), Email (SendGrid), or Pushover
    if send and can_send:
        channel = route.get("channel", "")
        message = build_adherence_message(row)
        if channel == "call":
            phone = _get_value(row, "Patient Contact", "Patient Contact Number", "PatientContact", default="")
            phone = str(phone).strip() if phone else ""
            if phone:
                call_res = make_twilio_voice_call(to_number=phone, message=message)
                if "error" in call_res:
                    result["status"] = "Failed"
                    result["pushover_error"] = call_res.get("error")
                else:
                    result["status"] = "Sent"
                    result["pushover"] = "Sent"
            else:
                result["status"] = "Failed"
                result["pushover_error"] = "No Patient Contact for call"
        elif channel == "sms":
            phone = route.get("address") or _get_value(row, "Patient Contact", "PatientContact", default="")
            phone = str(phone).strip() if phone else ""
            if phone:
                sms_res = send_twilio_sms(to_number=phone, body=message)
                if "error" in sms_res:
                    result["status"] = "Failed"
                    result["pushover_error"] = sms_res.get("error")
                else:
                    result["status"] = "Sent"
                    result["pushover"] = "Sent"
            else:
                result["status"] = "Failed"
                result["pushover_error"] = "No Patient Contact for SMS"
        elif channel == "whatsapp":
            phone = route.get("address") or _get_value(row, "Patient Contact", "PatientContact", default="")
            phone = str(phone).strip() if phone else ""
            if phone:
                wa_res = send_twilio_whatsapp(to_number=phone, body=message)
                if "error" in wa_res:
                    result["status"] = "Failed"
                    result["pushover_error"] = wa_res.get("error")
                else:
                    result["status"] = "Sent"
                    result["pushover"] = "Sent"
            else:
                result["status"] = "Failed"
                result["pushover_error"] = "No Patient Contact for WhatsApp"
        elif channel == "email":
            to_addr = route.get("address") or _get_value(row, "Patient EmailID", "Patient_EmailID", default="")
            to_addr = str(to_addr).strip() if to_addr else ""
            if to_addr:
                email_res = send_email(to_email=to_addr, subject="Medication Adherence Reminder", body=message)
                if "error" in email_res:
                    result["status"] = "Failed"
                    result["pushover_error"] = email_res.get("error")
                else:
                    result["status"] = "Sent"
                    result["pushover"] = "Sent"
            else:
                result["status"] = "Failed"
                result["pushover_error"] = "No Patient EmailID for Email"
        else:
            # Pushover: send adherence message with pharmacy table (same as other channels)
            use_pushover = channel == "pushover"
            if use_pushover and PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY:
                medication = _get_value(row, "Medication Name", "Medication_Name", default="Medication")
                pushover_res = send_pushover_message(
                    user_key=PUSHOVER_USER_KEY,
                    token=PUSHOVER_API_TOKEN,
                    title=f"{medication} Adherence Reminder",
                    message=message,
                )
                if "error" not in pushover_res:
                    result["status"] = "Sent"
                    result["pushover"] = pushover_res.get("request", "Sent")
                else:
                    result["status"] = "Failed"
                    result["pushover_error"] = pushover_res.get("error", "Unknown error")
            else:
                result["status"] = "Failed"
                result["pushover_error"] = "Pushover not configured" if use_pushover else "Unknown channel"
    elif send and can_appreciate and appreciation.get("appreciation_message"):
        # Send appreciation message
        use_pushover = route.get("channel") == "pushover"
        if use_pushover:
            try:
                name = _get_value(row, "Patient Name", "Patient_Name", default="Patient")
                msg = appreciation.get("appreciation_message", "")
                if PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY:
                    requests.post(
                        "https://api.pushover.net/1/messages.json",
                        data={
                            "token": PUSHOVER_API_TOKEN,
                            "user": PUSHOVER_USER_KEY,
                            "message": msg,
                            "title": f"Appreciation: {name}",
                            "priority": 0,
                        },
                        timeout=5,
                    )
                    result["appreciation_sent"] = "Sent"
            except Exception:
                result["appreciation_sent"] = "Failed"
        if result.get("appreciation_sent") == "Sent":
            try:
                from utils import update_appreciation_sent_on
                member_id = str(_get_value(row, "Member ID", "Member_ID", default="")).strip()
                if member_id:
                    update_appreciation_sent_on([member_id])
            except Exception:
                pass
        result["status"] = "Appreciation Sent" if result.get("appreciation_sent") == "Sent" else "Planned"
    elif send and not can_send:
        result["status"] = "Failed"

    return result


def analyze_patient_sentiment_and_behavior(row, patient_history: list = None) -> dict:
    """
    Sentiment & Behavior Analysis Agent: Analyzes patient sentiment and behavioral patterns
    to understand patient engagement and predict adherence behavior.
    """
    adherence = _coerce_float(_get_value(row, "Adherence Percentage", "Adeherence Percentage", default=0), default=0.0)
    days_until_refill = _get_value(row, "days_until_refill")
    days_until_refill = _coerce_float(days_until_refill, default=None) if days_until_refill is not None else None
    
    # Analyze sentiment based on adherence patterns
    sentiment_score = 0.5  # Neutral baseline
    behavior_pattern = "stable"
    
    if adherence >= THRESHOLD_MED:
        sentiment_score = 0.8  # Positive
        behavior_pattern = "compliant"
    elif adherence >= THRESHOLD_LOW:
        sentiment_score = 0.5  # Neutral
        behavior_pattern = "moderate"
    else:
        sentiment_score = 0.2  # Negative
        behavior_pattern = "at_risk"
    
    # Adjust based on refill timing
    if days_until_refill is not None:
        if days_until_refill > 7:
            sentiment_score += 0.1  # Positive - has time
        elif days_until_refill <= 0:
            sentiment_score -= 0.2  # Negative - overdue
        elif days_until_refill <= 3:
            sentiment_score -= 0.1  # Concern - urgent
    
    sentiment_score = max(0.0, min(1.0, sentiment_score))
    
    # Determine sentiment label
    if sentiment_score >= 0.7:
        sentiment_label = "positive"
    elif sentiment_score >= 0.4:
        sentiment_label = "neutral"
    else:
        sentiment_label = "negative"
    
    # Behavioral insights
    behavioral_insights = []
    if adherence < THRESHOLD_LOW:
        behavioral_insights.append("Low medication compliance detected")
    if days_until_refill is not None and days_until_refill <= 3:
        behavioral_insights.append("Urgent refill needed")
    if adherence >= THRESHOLD_MED and days_until_refill is not None and days_until_refill > 7:
        behavioral_insights.append("Good adherence pattern maintained")
    
    return {
        "sentiment_score": round(sentiment_score, 2),
        "sentiment_label": sentiment_label,
        "behavior_pattern": behavior_pattern,
        "behavioral_insights": behavioral_insights,
        "agent": "Sentiment & Behavior Analysis Agent"
    }


def check_and_appreciate_refilled_patient(row, previous_state: dict = None) -> dict:
    """
    Patient Appreciation Agent: Identifies patients who have recently refilled
    and generates appreciation messages to encourage continued adherence.
    """
    member_id = str(_get_value(row, "Member ID", "Member_ID", default=""))
    name = _get_value(row, "Patient Name", "Patient_Name", default="Patient")
    adherence = _coerce_float(_get_value(row, "Adherence Percentage", "Adeherence Percentage", default=0), default=0.0)
    days_until_refill = _get_value(row, "days_until_refill")
    days_until_refill = _coerce_float(days_until_refill, default=None) if days_until_refill is not None else None
    
    should_appreciate = False
    appreciation_reason = None
    
    # Check if patient recently refilled (days_until_refill increased significantly or adherence improved)
    if previous_state:
        prev_days = previous_state.get("days_until_refill")
        prev_adherence = previous_state.get("adherence", 0)
        
        # If days until refill increased significantly (patient refilled)
        if prev_days is not None and days_until_refill is not None:
            if days_until_refill > prev_days + 20:  # Significant increase indicates refill
                should_appreciate = True
                appreciation_reason = "Recent medication refill completed"
        
        # If adherence improved significantly
        if adherence > prev_adherence + 10:
            should_appreciate = True
            appreciation_reason = "Significant improvement in adherence"
    
    # Also appreciate if patient has good adherence and refill is not urgent
    if adherence >= THRESHOLD_MED and days_until_refill is not None and days_until_refill > 14:
        should_appreciate = True
        appreciation_reason = "Maintaining excellent adherence"
    
    appreciation_message = None
    if should_appreciate and _ai_enabled():
        try:
            user_content = (
                f"Write a warm, encouraging appreciation message to {name} who has {appreciation_reason}. "
                "Celebrate their commitment to their health and encourage them to continue. Keep under 60 words. Do not add a subject line. Close with: Best regards, Your healthcare team."
            )
            messages = build_messages(
                system_content="You are a friendly healthcare assistant. Write warm, genuine appreciation messages.",
                user_content=user_content,
            )
            appreciation_message = openai_chat(messages, temperature=0.7, max_tokens=150)
        except Exception:
            appreciation_message = f"Hi {name}, thank you for staying on track with your medication! Your commitment to your health is appreciated. Best regards, Your healthcare team."
    elif should_appreciate:
        appreciation_message = f"Hi {name}, thank you for staying on track with your medication! Your commitment to your health is appreciated. Best regards, Your healthcare team."
    
    return {
        "should_appreciate": should_appreciate,
        "appreciation_reason": appreciation_reason,
        "appreciation_message": appreciation_message,
        "agent": "Patient Appreciation Agent"
    }


def determine_care_routing(row, risk_assessment: dict = None, issue_analysis: dict = None) -> dict:
    """
    Enhanced Care Routing Agent: Determines how to route high-risk patients
    to appropriate clinicians or hospitals based on severity, urgency, and patient issues.
    Now includes automatic routing for critical cases identified from patient responses.
    """
    if risk_assessment is None:
        risk_assessment = assess_adherence_risk(row)
    
    adherence = _coerce_float(_get_value(row, "Adherence Percentage", "Adeherence Percentage", default=0), default=0.0)
    days_until_refill = _get_value(row, "days_until_refill")
    days_until_refill = _coerce_float(days_until_refill, default=None) if days_until_refill is not None else None
    risk_score = risk_assessment.get("risk_score", 0)
    risk_label = risk_assessment.get("risk_label", "Low")
    
    routing_decision = {
        "needs_routing": False,
        "routing_level": None,
        "routing_target": None,
        "urgency": "normal",
        "routing_reason": None,
        "recommended_action": None,
        "immediate_action_required": False,
        "agent": "Enhanced Care Routing Agent"
    }
    
    # Check if issue analysis indicates critical routing
    if issue_analysis:
        urgency = issue_analysis.get("urgency", "normal")
        needs_hospital = issue_analysis.get("needs_hospital_routing", False)
        needs_clinical = issue_analysis.get("needs_clinical_intervention", False)
        
        if needs_hospital or urgency == "critical":
            routing_decision["needs_routing"] = True
            routing_decision["routing_level"] = "critical"
            routing_decision["routing_target"] = "hospital_emergency"
            routing_decision["urgency"] = "immediate"
            routing_decision["immediate_action_required"] = True
            issues = issue_analysis.get("issues", [])
            routing_decision["routing_reason"] = f"CRITICAL: Patient response indicates emergency - {', '.join(issues) if issues else 'Urgent medical attention needed'}"
            routing_decision["recommended_action"] = "IMMEDIATE: Route to hospital emergency department. Patient requires urgent medical intervention."
            
            # Get patient contact info for routing
            member_id = str(_get_value(row, "Member ID", "Member_ID", default=""))
            name = _get_value(row, "Patient Name", "Patient_Name", default="Unknown")
            contact = _get_value(row, "Patient Contact", "Patient_Contact", default="")
            email = _get_value(row, "Patient EmailID", "Patient_EmailID", default="")
            
            routing_decision["patient_info"] = {
                "member_id": member_id,
                "name": name,
                "contact": contact,
                "email": email
            }
            
            # Automatically route to hospital
            if member_id:
                try:
                    from utils import route_to_clinician
                    route_to_clinician(
                        member_ids=[member_id],
                        reason=routing_decision["routing_reason"],
                        clinician_note=f"CRITICAL: Auto-routed from patient response analysis. Urgency: {urgency}"
                    )
                    routing_decision["auto_routed"] = True
                except Exception as e:
                    routing_decision["auto_routed"] = False
                    routing_decision["routing_error"] = str(e)
            
            return routing_decision
        
        elif needs_clinical or urgency == "high":
            routing_decision["needs_routing"] = True
            routing_decision["routing_level"] = "high"
            routing_decision["routing_target"] = "primary_care_physician"
            routing_decision["urgency"] = "urgent"
            issues = issue_analysis.get("issues", [])
            routing_decision["routing_reason"] = f"High priority: {', '.join(issues) if issues else 'Patient needs clinical attention'}"
            routing_decision["recommended_action"] = "Schedule appointment with primary care physician within 24 hours"
    
    # Critical: Immediate hospital/clinician routing (based on risk metrics)
    if not routing_decision["needs_routing"]:
        if risk_score >= 85 or (adherence < 20 and days_until_refill is not None and days_until_refill <= 0):
            routing_decision["needs_routing"] = True
            routing_decision["routing_level"] = "critical"
            routing_decision["routing_target"] = "hospital_emergency"
            routing_decision["urgency"] = "immediate"
            routing_decision["immediate_action_required"] = True
            routing_decision["routing_reason"] = f"Critical risk (score: {risk_score}, adherence: {adherence:.1f}%)"
            routing_decision["recommended_action"] = "IMMEDIATE: Route to hospital emergency. Critical medication adherence failure."
        
        # High: Clinician routing
        elif risk_score >= 70 or (adherence < THRESHOLD_LOW and days_until_refill is not None and days_until_refill <= 3):
            routing_decision["needs_routing"] = True
            routing_decision["routing_level"] = "high"
            routing_decision["routing_target"] = "primary_care_physician"
            routing_decision["urgency"] = "urgent"
            routing_decision["routing_reason"] = f"High risk patient (score: {risk_score})"
            routing_decision["recommended_action"] = "Schedule appointment with primary care physician within 24-48 hours"
        
        # Medium: Care coordinator routing
        elif risk_score >= 50 or (adherence < THRESHOLD_MED and days_until_refill is not None and days_until_refill <= 7):
            routing_decision["needs_routing"] = True
            routing_decision["routing_level"] = "medium"
            routing_decision["routing_target"] = "care_coordinator"
            routing_decision["urgency"] = "moderate"
            routing_decision["routing_reason"] = f"Moderate risk (score: {risk_score})"
            routing_decision["recommended_action"] = "Care coordinator follow-up within 3-5 days"
    
    # Get patient contact info for routing
    member_id = str(_get_value(row, "Member ID", "Member_ID", default=""))
    name = _get_value(row, "Patient Name", "Patient_Name", default="Unknown")
    contact = _get_value(row, "Patient Contact", "Patient_Contact", default="")
    email = _get_value(row, "Patient EmailID", "Patient_EmailID", default="")
    
    routing_decision["patient_info"] = {
        "member_id": member_id,
        "name": name,
        "contact": contact,
        "email": email
    }
    
    return routing_decision


def analyze_patient_response(patient_message: str, patient_row: dict = None, conversation_history: list = None) -> dict:
    """
    Patient Response Analysis Agent: Analyzes patient messages to understand issues, 
    pain points, concerns, and emotional state. Extracts actionable insights.
    
    Args:
        patient_message: The patient's message/response
        patient_row: Patient data row (optional)
        conversation_history: Previous conversation messages (optional)
    
    Returns:
        dict: Analysis with issues, pain points, urgency, and recommended actions
    """
    if not _ai_enabled():
        return {
            "issues": [],
            "pain_points": [],
            "urgency": "normal",
            "emotional_state": "neutral",
            "recommended_actions": [],
            "confidence": 0.0,
            "agent": "Patient Response Analysis Agent"
        }
    
    # Build context for analysis
    context_parts = []
    if patient_row:
        name = _get_value(patient_row, "Patient Name", "Patient_Name", default="Patient")
        adherence = _coerce_float(_get_value(patient_row, "Adherence Percentage", "Adeherence Percentage", default=0), default=0.0)
        medication = _get_value(patient_row, "Medication Name", "Medication_Name", default="medication")
        context_parts.append(f"Patient: {name}, Adherence: {adherence:.1f}%, Medication: {medication}")
    
    if conversation_history:
        recent_messages = conversation_history[-5:]  # Last 5 messages
        context_parts.append(f"Recent conversation: {len(recent_messages)} messages")
    
    context_text = "\n".join(context_parts) if context_parts else "No additional context"
    
    # AI prompt for comprehensive analysis
    analysis_prompt = f"""You are a healthcare AI assistant analyzing a patient's message to understand their issues, pain points, and concerns.

Patient Message: "{patient_message}"

Context: {context_text}

Analyze this message and identify:
1. **Issues**: Specific problems the patient is facing (e.g., medication side effects, cost concerns, forgetfulness, confusion)
2. **Pain Points**: Emotional or practical difficulties (e.g., anxiety, frustration, difficulty remembering, financial stress)
3. **Urgency Level**: critical, high, medium, or normal
4. **Emotional State**: anxious, frustrated, confused, grateful, neutral, etc.
5. **Root Causes**: Underlying reasons for the issues (e.g., lack of understanding, side effects, cost, forgetfulness)
6. **Recommended Immediate Actions**: What should be done right away

Return STRICT JSON with this structure:
{{
    "issues": ["issue1", "issue2"],
    "pain_points": ["pain1", "pain2"],
    "urgency": "critical|high|medium|normal",
    "emotional_state": "state",
    "root_causes": ["cause1", "cause2"],
    "recommended_immediate_actions": ["action1", "action2"],
    "needs_clinical_intervention": true/false,
    "needs_hospital_routing": true/false,
    "confidence": 0.0-1.0
}}

Be thorough and empathetic in your analysis."""
    
    try:
        messages = build_messages(
            system_content="You are an expert healthcare AI that analyzes patient communications to identify issues and pain points.",
            user_content=analysis_prompt,
        )
        content = openai_chat(messages, temperature=0.3, max_tokens=1000)
        # Remove markdown code blocks if present
        content = content.strip('```json').strip('```').strip()
        analysis = json.loads(content)
        
        # Ensure all required fields exist
        result = {
            "issues": analysis.get("issues", []),
            "pain_points": analysis.get("pain_points", []),
            "urgency": analysis.get("urgency", "normal"),
            "emotional_state": analysis.get("emotional_state", "neutral"),
            "root_causes": analysis.get("root_causes", []),
            "recommended_immediate_actions": analysis.get("recommended_immediate_actions", []),
            "needs_clinical_intervention": analysis.get("needs_clinical_intervention", False),
            "needs_hospital_routing": analysis.get("needs_hospital_routing", False),
            "confidence": min(1.0, max(0.0, float(analysis.get("confidence", 0.7)))),
            "agent": "Patient Response Analysis Agent"
        }
        
        return result
        
    except Exception as e:
        # Fallback analysis using keyword matching
        message_lower = patient_message.lower()
        issues = []
        pain_points = []
        urgency = "normal"
        emotional_state = "neutral"
        
        # Detect issues
        if any(word in message_lower for word in ['side effect', 'nausea', 'dizzy', 'headache', 'pain', 'unwell']):
            issues.append("Possible medication side effects")
            urgency = "high"
            emotional_state = "concerned"
        
        if any(word in message_lower for word in ['cost', 'expensive', 'afford', 'money', 'price']):
            issues.append("Cost concerns")
            pain_points.append("Financial stress")
            urgency = "medium"
        
        if any(word in message_lower for word in ['forgot', 'missed', 'skip', 'forget']):
            issues.append("Medication forgetfulness")
            pain_points.append("Difficulty remembering doses")
            urgency = "medium"
        
        if any(word in message_lower for word in ['confused', 'understand', 'how to', 'what is', 'explain']):
            issues.append("Lack of understanding")
            pain_points.append("Confusion about medication")
            urgency = "medium"
            emotional_state = "confused"
        
        if any(word in message_lower for word in ['emergency', 'urgent', 'immediate', 'critical', 'severe', 'hospital']):
            urgency = "critical"
            emotional_state = "anxious"
            issues.append("Emergency situation")
        
        return {
            "issues": issues,
            "pain_points": pain_points,
            "urgency": urgency,
            "emotional_state": emotional_state,
            "root_causes": [],
            "recommended_immediate_actions": [],
            "needs_clinical_intervention": urgency in ["critical", "high"],
            "needs_hospital_routing": urgency == "critical",
            "confidence": 0.5,
            "agent": "Patient Response Analysis Agent (Fallback)"
        }


def generate_resolution_recommendations(issue_analysis: dict, patient_row: dict = None) -> dict:
    """
    Resolution Recommendations Agent: Provides best ways to resolve identified 
    patient issues and pain points with actionable, personalized recommendations.
    
    Args:
        issue_analysis: Output from analyze_patient_response()
        patient_row: Patient data row (optional)
    
    Returns:
        dict: Comprehensive resolution recommendations with steps and expected outcomes
    """
    if not _ai_enabled():
        return {
            "recommendations": [],
            "priority_order": [],
            "expected_outcomes": {},
            "agent": "Resolution Recommendations Agent"
        }
    
    issues = issue_analysis.get("issues", [])
    pain_points = issue_analysis.get("pain_points", [])
    root_causes = issue_analysis.get("root_causes", [])
    urgency = issue_analysis.get("urgency", "normal")
    
    # Build patient context
    context_parts = []
    if patient_row:
        name = _get_value(patient_row, "Patient Name", "Patient_Name", default="Patient")
        adherence = _coerce_float(_get_value(patient_row, "Adherence Percentage", "Adeherence Percentage", default=0), default=0.0)
        medication = _get_value(patient_row, "Medication Name", "Medication_Name", default="medication")
        context_parts.append(f"Patient: {name}, Current Adherence: {adherence:.1f}%, Medication: {medication}")
    
    context_text = "\n".join(context_parts) if context_parts else "No additional patient context"
    
    # AI prompt for resolution recommendations
    recommendations_prompt = f"""You are a healthcare AI assistant providing the BEST resolution recommendations for patient issues.

Identified Issues: {', '.join(issues) if issues else 'None identified'}
Pain Points: {', '.join(pain_points) if pain_points else 'None identified'}
Root Causes: {', '.join(root_causes) if root_causes else 'None identified'}
Urgency: {urgency}

Patient Context: {context_text}

Provide comprehensive, actionable resolution recommendations. For each issue, provide:
1. **Immediate Actions**: What to do right now
2. **Short-term Solutions**: Steps to take in the next few days
3. **Long-term Strategies**: Ongoing approaches
4. **Expected Outcomes**: What improvement to expect
5. **Resources Needed**: What support/help is required

Return STRICT JSON with this structure:
{{
    "recommendations": [
        {{
            "issue": "issue name",
            "priority": "critical|high|medium|low",
            "immediate_actions": ["action1", "action2"],
            "short_term_solutions": ["solution1", "solution2"],
            "long_term_strategies": ["strategy1", "strategy2"],
            "expected_outcome": "description",
            "resources_needed": ["resource1", "resource2"],
            "estimated_resolution_time": "timeframe"
        }}
    ],
    "priority_order": ["issue1", "issue2"],
    "overall_approach": "summary of recommended approach",
    "critical_actions_required": ["action1", "action2"]
}}

Focus on practical, achievable solutions that address root causes."""
    
    try:
        messages = build_messages(
            system_content="You are an expert healthcare AI that provides the best resolution strategies for patient issues.",
            user_content=recommendations_prompt,
        )
        content = openai_chat(messages, temperature=0.4, max_tokens=1500)
        content = content.strip('```json').strip('```').strip()
        recommendations = json.loads(content)
        
        return {
            "recommendations": recommendations.get("recommendations", []),
            "priority_order": recommendations.get("priority_order", []),
            "overall_approach": recommendations.get("overall_approach", ""),
            "critical_actions_required": recommendations.get("critical_actions_required", []),
            "expected_outcomes": {r.get("issue", ""): r.get("expected_outcome", "") for r in recommendations.get("recommendations", [])},
            "agent": "Resolution Recommendations Agent"
        }
        
    except Exception as e:
        # Fallback recommendations
        fallback_recommendations = []
        
        for issue in issues:
            if "side effect" in issue.lower():
                fallback_recommendations.append({
                    "issue": issue,
                    "priority": "high",
                    "immediate_actions": [
                        "Contact prescribing physician immediately",
                        "Document all symptoms and severity",
                        "Do not stop medication without medical advice"
                    ],
                    "short_term_solutions": [
                        "Schedule appointment with doctor to discuss side effects",
                        "Consider medication adjustment or alternative"
                    ],
                    "long_term_strategies": [
                        "Regular monitoring and follow-up",
                        "Medication review and optimization"
                    ],
                    "expected_outcome": "Side effects managed or medication adjusted",
                    "resources_needed": ["Physician consultation", "Medical review"],
                    "estimated_resolution_time": "1-2 weeks"
                })
            elif "cost" in issue.lower():
                fallback_recommendations.append({
                    "issue": issue,
                    "priority": "medium",
                    "immediate_actions": [
                        "Check for generic alternatives",
                        "Explore patient assistance programs",
                        "Contact pharmacy for cost-saving options"
                    ],
                    "short_term_solutions": [
                        "Apply for medication assistance programs",
                        "Review insurance coverage options"
                    ],
                    "long_term_strategies": [
                        "Financial counseling",
                        "Medication cost planning"
                    ],
                    "expected_outcome": "Reduced medication cost burden",
                    "resources_needed": ["Pharmacy consultation", "Financial assistance programs"],
                    "estimated_resolution_time": "2-4 weeks"
                })
            elif "forgot" in issue.lower() or "missed" in issue.lower():
                fallback_recommendations.append({
                    "issue": issue,
                    "priority": "medium",
                    "immediate_actions": [
                        "Set up medication reminders (phone alarms, apps)",
                        "Use pill organizer",
                        "Establish daily routine"
                    ],
                    "short_term_solutions": [
                        "Enroll in medication adherence program",
                        "Set up automated refill reminders"
                    ],
                    "long_term_strategies": [
                        "Habit formation support",
                        "Regular adherence monitoring"
                    ],
                    "expected_outcome": "Improved medication adherence",
                    "resources_needed": ["Reminder systems", "Adherence support"],
                    "estimated_resolution_time": "4-6 weeks"
                })
        
        return {
            "recommendations": fallback_recommendations,
            "priority_order": [r["issue"] for r in fallback_recommendations],
            "overall_approach": "Address each identified issue with targeted interventions",
            "critical_actions_required": [r["immediate_actions"][0] for r in fallback_recommendations if r["priority"] == "high"],
            "expected_outcomes": {},
            "agent": "Resolution Recommendations Agent (Fallback)"
        }


def auto_respond_to_patient(patient_message: str, patient_row: dict, conversation_history: list = None) -> dict:
    """
    Automatic Patient Response Agent: Automatically responds to patient messages 
    after analyzing their issues, understanding pain points, and providing 
    resolution recommendations. Routes critical cases appropriately.
    
    Args:
        patient_message: The patient's message
        patient_row: Patient data row
        conversation_history: Previous conversation messages
    
    Returns:
        dict: Complete response with analysis, recommendations, and actions taken
    """
    # Step 1: Analyze patient response to understand issues
    issue_analysis = analyze_patient_response(patient_message, patient_row, conversation_history)
    
    # Step 2: Generate resolution recommendations
    resolution_recommendations = generate_resolution_recommendations(issue_analysis, patient_row)
    
    # Step 3: Assess risk and determine if routing is needed (pass issue_analysis for enhanced routing)
    risk_assessment = assess_adherence_risk(patient_row)
    care_routing = determine_care_routing(patient_row, risk_assessment=risk_assessment, issue_analysis=issue_analysis)
    
    # Step 4: Check if critical case needs hospital routing
    needs_hospital = issue_analysis.get("needs_hospital_routing", False) or \
                    care_routing.get("routing_level") == "critical" or \
                    issue_analysis.get("urgency") == "critical"
    
    # Step 5: Generate empathetic, helpful response
    if not _ai_enabled():
        response_text = f"Thank you for your message. We understand your concerns and are here to help."
    else:
        name = _get_value(patient_row, "Patient Name", "Patient_Name", default="Patient")
        issues_summary = ", ".join(issue_analysis.get("issues", [])) if issue_analysis.get("issues") else "your concerns"
        urgency = issue_analysis.get("urgency", "normal")
        
        response_prompt = f"""You are a compassionate healthcare assistant responding to a patient's message.

Patient Name: {name}
Patient Message: "{patient_message}"

Identified Issues: {issues_summary}
Urgency Level: {urgency}
Emotional State: {issue_analysis.get("emotional_state", "neutral")}

Resolution Recommendations Available: {len(resolution_recommendations.get("recommendations", []))} recommendations

Write a warm, empathetic, and helpful response that:
1. Acknowledges their concerns and shows understanding
2. Addresses their specific issues and pain points
3. Provides clear, actionable next steps
4. Reassures them about the support available
5. If urgent/critical, emphasizes immediate action needed

Keep the tone:
- Empathetic and caring
- Professional but warm
- Clear and actionable
- Reassuring

Length: 3-5 sentences for normal urgency, 5-7 sentences for high/critical urgency.
Do not include medical advice beyond general guidance - refer to healthcare providers for medical decisions."""
        
        try:
            messages = build_messages(
                system_content="You are a compassionate healthcare assistant that helps patients with medication adherence and health concerns.",
                user_content=response_prompt,
            )
            response_text = openai_chat(messages, temperature=0.7, max_tokens=300)
        except Exception:
            response_text = f"Hi {name}, thank you for reaching out. We understand {issues_summary}. Our team is here to help you resolve these concerns. Please know that your health and wellbeing are our priority."
    
    # Step 6: Route to hospital if critical
    routing_action = None
    if needs_hospital:
        member_id = str(_get_value(patient_row, "Member ID", "Member_ID", default=""))
        if member_id:
            try:
                from utils import route_to_clinician
                route_to_clinician(
                    member_ids=[member_id],
                    reason=f"Critical patient response: {issue_analysis.get('urgency')} urgency - {', '.join(issue_analysis.get('issues', []))}",
                    clinician_note=f"Patient message: {patient_message[:200]}"
                )
                routing_action = {
                    "routed": True,
                    "target": "hospital_emergency",
                    "reason": "Critical case identified from patient response",
                    "timestamp": pd.Timestamp.now().isoformat()
                }
            except Exception as e:
                routing_action = {
                    "routed": False,
                    "error": str(e)
                }
    
    # Step 7: Compile comprehensive result
    result = {
        "response_message": response_text,
        "issue_analysis": issue_analysis,
        "resolution_recommendations": resolution_recommendations,
        "care_routing": care_routing,
        "routing_action": routing_action,
        "needs_follow_up": issue_analysis.get("urgency") in ["critical", "high"],
        "recommended_follow_up_time": "immediate" if issue_analysis.get("urgency") == "critical" else "within 24 hours" if issue_analysis.get("urgency") == "high" else "within 3 days",
        "agent": "Automatic Patient Response Agent"
    }
    
    return result


def identify_patient_care_needs(row, risk_assessment: dict = None, sentiment_analysis: dict = None) -> dict:
    """
    Patient Care Needs Identification Agent: Identifies specific care needs
    and provides actionable recommendations for refill assistance and issue resolution.
    """
    if risk_assessment is None:
        risk_assessment = assess_adherence_risk(row)
    if sentiment_analysis is None:
        sentiment_analysis = analyze_patient_sentiment_and_behavior(row)
    
    adherence = _coerce_float(_get_value(row, "Adherence Percentage", "Adeherence Percentage", default=0), default=0.0)
    days_until_refill = _get_value(row, "days_until_refill")
    days_until_refill = _coerce_float(days_until_refill, default=None) if days_until_refill is not None else None
    risk_score = risk_assessment.get("risk_score", 0)
    
    care_needs = {
        "priority": "low",
        "needs_attention": False,
        "care_actions": [],
        "refill_assistance": None,
        "issue_resolution": [],
        "recommended_interventions": [],
        "agent": "Patient Care Needs Identification Agent"
    }
    
    # Determine priority
    if risk_score >= 70 or adherence < THRESHOLD_LOW:
        care_needs["priority"] = "high"
        care_needs["needs_attention"] = True
    elif risk_score >= 50 or adherence < THRESHOLD_MED:
        care_needs["priority"] = "medium"
        care_needs["needs_attention"] = True
    else:
        care_needs["priority"] = "low"
    
    # Refill assistance needs
    if days_until_refill is not None:
        if days_until_refill <= 0:
            care_needs["refill_assistance"] = "urgent"
            care_needs["care_actions"].append("Immediate refill required - medication overdue")
            care_needs["recommended_interventions"].append("Contact pharmacy immediately for emergency refill")
            care_needs["issue_resolution"].append("Medication gap - risk of treatment interruption")
        elif days_until_refill <= 3:
            care_needs["refill_assistance"] = "high"
            care_needs["care_actions"].append("Urgent refill needed within 3 days")
            care_needs["recommended_interventions"].append("Schedule pharmacy refill appointment today")
            care_needs["issue_resolution"].append("Prevent medication gap by refilling before deadline")
        elif days_until_refill <= 7:
            care_needs["refill_assistance"] = "moderate"
            care_needs["care_actions"].append("Refill due within 7 days")
            care_needs["recommended_interventions"].append("Remind patient to refill medication")
    
    # Adherence-related care needs
    if adherence < THRESHOLD_LOW:
        care_needs["care_actions"].append("Low adherence detected - patient education needed")
        care_needs["recommended_interventions"].append("Provide medication adherence counseling")
        care_needs["issue_resolution"].append("Address barriers to medication compliance")
    elif adherence < THRESHOLD_MED:
        care_needs["care_actions"].append("Moderate adherence - support and monitoring needed")
        care_needs["recommended_interventions"].append("Regular check-ins and adherence reminders")
    
    # Behavioral insights-based recommendations
    behavior_pattern = sentiment_analysis.get("behavior_pattern", "stable")
    if behavior_pattern == "at_risk":
        care_needs["recommended_interventions"].append("Behavioral intervention program enrollment")
        care_needs["issue_resolution"].append("Address underlying behavioral barriers")
    
    # Generate personalized care plan
    member_id = str(_get_value(row, "Member ID", "Member_ID", default=""))
    name = _get_value(row, "Patient Name", "Patient_Name", default="Patient")
    
    care_needs["patient_id"] = member_id
    care_needs["patient_name"] = name
    care_needs["summary"] = f"Patient {name} (ID: {member_id}) requires {care_needs['priority']} priority care. " + \
                           f"Adherence: {adherence:.1f}%, Risk Score: {risk_score}"
    
    return care_needs


# ===============================
# Notification Agent Functions
# ===============================

def generate_patient_message(patient: dict, purpose: str = "medication_refill") -> str:
    """
    Uses AI to generate a friendly message for the patient.
    This is an alternative message generation function for SMS-style messages.
    
    Args:
        patient: dict with keys Patient_Name, Medication_Name, days_until_refill, adherence_pct etc.
        purpose: Purpose of the message (e.g., "medication_refill")
    
    Returns:
        Generated message string
    """
    name = patient.get("Patient_Name") or patient.get("Patient Name") or "Patient"
    med = patient.get("Medication_Name") or patient.get("Medication Name") or "your medication"
    days_left = patient.get("days_until_refill")
    adherence = patient.get("adherence_pct") or patient.get("Adherence Percentage", 0)

    system = (
        "You are a friendly medical assistant. Produce a short (1-3 sentence) SMS-style message "
        "to a patient informing them about their medication adherence and refill status. "
        "Be concise, empathetic, and include a clear action (e.g., call the pharmacy, schedule refill). "
        "Do not include medical advice beyond refill reminders. Use simple language."
    )
    prompt = (
        f"Patient name: {name}\n"
        f"Medication: {med}\n"
        f"Adherence percentage: {adherence}\n"
        f"Days until refill: {days_left}\n"
        f"Purpose: {purpose}\n\n"
        "Write a short SMS friendly message (max 280 characters)."
    )

    try:
        if not _ai_enabled():
            raise RuntimeError("AI disabled: OPENAI_API_KEY not configured")
        messages = build_messages(system_content=system, user_content=prompt)
        text = openai_chat(messages, temperature=0.6, max_tokens=150)
        return text
    except Exception:
        fallback = (
            f"Hi {name}, it's time to check on your {med}. Your adherence is {adherence}%."
            f" Please contact your pharmacy to schedule a refill."
        )
        return fallback


def send_pushover_message(user_key: str, token: str, title: str, message: str, url: str = None) -> dict:
    """
    Send a message via Pushover API.
    
    Args:
        user_key: Pushover user key
        token: Pushover API token
        title: Message title
        message: Message content
        url: Optional URL to include
    
    Returns:
        dict: Response from Pushover API or error information
    """
    PUSHOVER_URL = "https://api.pushover.net/1/messages.json"
    payload = {
        "token": (token or "").strip(),
        "user": (user_key or "").strip(),
        "title": title,
        "message": message,
    }
    if url:
        payload["url"] = url
    try:
        r = requests.post(PUSHOVER_URL, data=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        # Pushover returns status=1 on success; status=0 with "errors" list on failure
        if data.get("status") != 1:
            err_msg = data.get("errors") or data.get("error")
            if isinstance(err_msg, list):
                err_msg = "; ".join(str(x) for x in err_msg)
            return {"error": err_msg or "Pushover API returned failure", "status": data.get("status")}
        return data
    except requests.exceptions.RequestException as e:
        err = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                body = e.response.json()
                err = body.get("errors", body.get("error", err))
                if isinstance(err, list):
                    err = "; ".join(str(x) for x in err)
            except Exception:
                pass
        return {"error": err}
    except Exception as e:
        return {"error": str(e)}


def send_twilio_sms(to_number: str, body: str) -> dict:
    """
    Send an SMS using Twilio.
    
    Args:
        to_number: Recipient phone number
        body: Message body
    
    Returns:
        dict: Contains 'sid' when successful, 'error' when failed
    """
    try:
        from twilio.rest import Client  # type: ignore
    except Exception as e:
        return {"error": f"Twilio SDK not available: {e}"}

    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
        return {"error": "Twilio credentials not configured (TWILIO_*)."}

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            from_=TWILIO_FROM_NUMBER,
            to=str(to_number),
            body=body,
        )
        return {"sid": msg.sid, "status": getattr(msg, "status", "queued")}
    except Exception as e:
        return {"error": str(e)}


def send_twilio_whatsapp(to_number: str, body: str) -> dict:
    """
    Send a WhatsApp message using Twilio Messaging API.
    'from' and 'to' must use format whatsapp:+E164 (e.g. whatsapp:+14155551212).

    Args:
        to_number: Recipient phone in E.164 (e.g. +14155551212)
        body: Message body

    Returns:
        dict: {"sid": "...", "status": "queued"} on success, {"error": "..."} on failure.
    """
    try:
        from twilio.rest import Client  # type: ignore
    except Exception as e:
        return {"error": f"Twilio SDK not available: {e}"}

    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_WHATSAPP_FROM:
        return {"error": "Twilio WhatsApp not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM)."}

    to_num = str(to_number).strip()
    if not to_num:
        return {"error": "to_number is required."}
    if not to_num.startswith("whatsapp:"):
        to_num = f"whatsapp:{to_num}"

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            from_=TWILIO_WHATSAPP_FROM if TWILIO_WHATSAPP_FROM.startswith("whatsapp:") else f"whatsapp:{TWILIO_WHATSAPP_FROM}",
            to=to_num,
            body=body or "",
        )
        return {"sid": msg.sid, "status": getattr(msg, "status", "queued")}
    except Exception as e:
        return {"error": str(e)}


def send_email(to_email: str, subject: str, body: str, from_email: str = None) -> dict:
    """
    Send an email using SendGrid API (optional; Twilio/SendGrid).

    Args:
        to_email: Recipient email address
        subject: Subject line
        body: Plain text body
        from_email: Sender email (default: SENDER_EMAIL from config)

    Returns:
        dict: {"status_code": 202} on success, {"error": "..."} on failure.
    """
    if not SENDGRID_API_KEY:
        return {"error": "SendGrid not configured (SENDGRID_API_KEY)."}
    from_addr = (from_email or SENDER_EMAIL or "").strip()
    if not from_addr:
        return {"error": "Sender email not configured (SENDER_EMAIL)."}
    to_addr = str(to_email).strip()
    if not to_addr:
        return {"error": "to_email is required."}

    try:
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [{"to": [{"email": to_addr}]}],
                "from": {"email": from_addr, "name": "Medication Adherence"},
                "subject": subject or "Medication Adherence Reminder",
                "content": [{"type": "text/plain", "value": body or ""}],
            },
            timeout=15,
        )
        if resp.status_code in (200, 202):
            return {"status_code": resp.status_code}
        return {"error": f"SendGrid returned {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def _escape_twiml(text: str) -> str:
    """Escape text for use inside TwiML <Say> (XML)."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def make_twilio_voice_call(
    to_number: str,
    message: str,
    from_number: str = None,
    status_callback_url: str = None,
) -> dict:
    """
    Make an outbound voice call using Twilio Programmable Voice.
    Uses the Calls resource with inline TwiML to speak the message (TTS).
    See: https://www.twilio.com/docs/voice/tutorials/how-to-make-outbound-phone-calls

    Prerequisites (from Twilio tutorial):
    - Twilio account with a phone number that has voice capabilities
    - TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER set in env

    Args:
        to_number: Recipient phone number in E.164 format (e.g. +14155551212)
        message: Text to be spoken by Twilio (used in <Say> TwiML)
        from_number: Twilio number to call from (default: TWILIO_FROM_NUMBER)
        status_callback_url: Optional URL for call status updates (initiated, ringing, answered, completed)

    Returns:
        dict: On success {"call_sid": "...", "status": "queued"}; on failure {"error": "..."}
    """
    try:
        from twilio.rest import Client  # type: ignore
    except Exception as e:
        return {"error": f"Twilio SDK not available: {e}"}

    from_num = (from_number or TWILIO_FROM_NUMBER or "").strip()
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not from_num:
        return {"error": "Twilio voice credentials not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER)."}

    to_num = str(to_number).strip()
    if not to_num:
        return {"error": "to_number is required."}

    safe_message = _escape_twiml(message or "This is a reminder. Please contact your care team if you have questions.")
    twiml = f'<Response><Say voice="alice">{safe_message}</Say></Response>'

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        params = {
            "twiml": twiml,
            "to": to_num,
            "from_": from_num,
        }
        if status_callback_url:
            params["status_callback"] = status_callback_url
            params["status_callback_event"] = ["initiated", "ringing", "answered", "completed"]
            params["status_callback_method"] = "POST"
        call = client.calls.create(**params)
        return {
            "call_sid": call.sid,
            "status": getattr(call, "status", "queued"),
        }
    except Exception as e:
        return {"error": str(e)}


def chatbot_agent(
    user_message: str,
    dashboard_context: dict = None,
    patient_data: dict = None,
    patient_row: dict = None,
    conversation_history: list = None,
    allow_actions: bool = False,
    requested_member_id: str = None,
) -> str:
    """
    Enhanced AI Chatbot Agent: Comprehensive patient management assistant with full capabilities.
    
    Args:
        user_message: The user's question or message
        dashboard_context: Dictionary containing dashboard KPIs and system status
        patient_data: Dictionary containing patient data if querying specific patient
        patient_row: Full patient row data (dict) for comprehensive analysis
        conversation_history: List of previous messages in format [{"role": "user/assistant", "content": "..."}]
        allow_actions: Whether to allow executing actions like sending notifications
        requested_member_id: Member ID user asked about (e.g. IN-100003); if patient_row is None, agent can say "Patient not found"
    
    Returns:
        str: The AI agent's comprehensive response
    """
    if not _ai_enabled():
        return "AI assistant is currently unavailable. Please ensure OPENAI_API_KEY is configured."
    
    # Detect action requests from user message
    user_lower = user_message.lower()
    requested_actions = []
    
    # Check for specific action requests
    if any(phrase in user_lower for phrase in ['send notification', 'notify patient', 'send reminder', 'send message', 'notify']):
        requested_actions.append('send_notification')
    if any(phrase in user_lower for phrase in ['preview', 'notification preview', 'preview message', 'message that would be sent', 'show me the message', 'what message would be sent']):
        requested_actions.append('notification_preview')
    if any(phrase in user_lower for phrase in ['appreciate patient', 'send appreciation', 'thank patient', 'appreciate']):
        requested_actions.append('appreciate')
    if any(phrase in user_lower for phrase in ['check sentiment', 'sentiment analysis', 'patient sentiment', 'how is patient feeling']):
        requested_actions.append('sentiment')
    if any(phrase in user_lower for phrase in ['risk assessment', 'check risk', 'patient risk', 'risk score']):
        requested_actions.append('risk')
    if any(phrase in user_lower for phrase in ['care routing', 'routing', 'hospital', 'clinician', 'care team']):
        requested_actions.append('care_routing')
    if any(phrase in user_lower for phrase in ['care needs', 'patient needs', 'what does patient need']):
        requested_actions.append('care_needs')
    if any(phrase in user_lower for phrase in ['refill details', 'refill information', 'refill status', 'when is refill']):
        requested_actions.append('refill')
    
    # Analyze patient comprehensively if patient_row is provided
    patient_analysis = {}
    action_results = {}
    
    if patient_row:
        try:
            # Normalize patient row first
            normalized = validate_and_normalize_row(patient_row)
            clean_row = normalized.get('clean', patient_row)
            
            # Always do basic risk assessment (needed for other analyses)
            risk_assessment = assess_adherence_risk(clean_row)
            patient_analysis['risk'] = risk_assessment
            
            # Call agents based on requested actions or always for comprehensive analysis
            if 'sentiment' in requested_actions or not requested_actions:
                # Sentiment & behavior analysis
                sentiment_analysis = analyze_patient_sentiment_and_behavior(clean_row)
                patient_analysis['sentiment'] = sentiment_analysis
                if 'sentiment' in requested_actions:
                    action_results['sentiment'] = sentiment_analysis
            
            if 'care_routing' in requested_actions or not requested_actions:
                # Care routing
                care_routing = determine_care_routing(clean_row, risk_assessment=risk_assessment)
                patient_analysis['care_routing'] = care_routing
                if 'care_routing' in requested_actions:
                    action_results['care_routing'] = care_routing
            
            if 'care_needs' in requested_actions or not requested_actions:
                # Care needs
                sentiment_for_needs = patient_analysis.get('sentiment')
                if not sentiment_for_needs:
                    sentiment_for_needs = analyze_patient_sentiment_and_behavior(clean_row)
                care_needs = identify_patient_care_needs(clean_row, risk_assessment=risk_assessment, sentiment_analysis=sentiment_for_needs)
                patient_analysis['care_needs'] = care_needs
                if 'care_needs' in requested_actions:
                    action_results['care_needs'] = care_needs
            
            if 'appreciate' in requested_actions or not requested_actions:
                # Appreciation check
                appreciation = check_and_appreciate_refilled_patient(clean_row)
                patient_analysis['appreciation'] = appreciation
                if 'appreciate' in requested_actions:
                    action_results['appreciation'] = appreciation
                    # If user wants to appreciate and it's allowed, prepare to send
                    if allow_actions and appreciation.get('should_appreciate'):
                        action_results['appreciation_action'] = 'ready_to_send'
            
            # Orchestration (includes notification preview) - run when notification send/preview requested or for general analysis
            if 'send_notification' in requested_actions or 'notification_preview' in requested_actions or not requested_actions:
                # For notification send, actually send if allowed; for preview, only build message
                should_send = 'send_notification' in requested_actions and allow_actions
                orchestration = orchestrate_refill_and_notify(clean_row, send=should_send)
                patient_analysis['orchestration'] = orchestration
                if 'send_notification' in requested_actions or 'notification_preview' in requested_actions:
                    action_results['notification'] = {
                        'status': orchestration.get('status', 'Unknown'),
                        'message': orchestration.get('message', ''),
                        'channel': orchestration.get('route', {}).get('channel', 'unknown'),
                        'actions': orchestration.get('actions', []),
                        'sent': should_send and orchestration.get('status') in ['Sent', 'Queued']
                    }
            
            # Risk assessment result
            if 'risk' in requested_actions:
                action_results['risk'] = risk_assessment
            
        except Exception as e:
            patient_analysis['error'] = f"Analysis error: {str(e)}"
            action_results['error'] = f"Error processing request: {str(e)}"
    
    # Build comprehensive system prompt
    system_prompt = """You are an advanced AI Healthcare Assistant for a Medication Adherence Dashboard. You have comprehensive capabilities to help healthcare professionals manage patient care.

**YOUR CAPABILITIES:**

1. **Patient Information Management:**
   - Show complete patient details (demographics, contact, medication)
   - Display clinical information (adherence, risk scores, medication history)
   - Show hospital/clinic details and care routing information
   - Provide recent refill details and medication gaps
   - Analyze patient sentiment and behavioral patterns

2. **Patient Analysis:**
   - Risk assessment and scoring
   - Sentiment analysis (positive/neutral/negative)
   - Behavioral pattern identification (compliant/moderate/at_risk)
   - Care needs identification
   - Care routing recommendations (hospital/clinician/care coordinator)

3. **Patient Actions:**
   - Send notifications/reminders when requested
   - Appreciate patients for good adherence or refills
   - Generate personalized care plans
   - Recommend interventions based on patient needs

4. **Dashboard Analytics:**
   - KPIs (adherence rates, interventions, response rates, savings)
   - System status and health monitoring
   - High-risk patient identification
   - Trend analysis

**WHEN PROVIDED WITH PATIENT DATA, YOU MUST:**
- Provide ALL requested information comprehensively
- Include clinical details (adherence %, risk score, risk label)
- Show hospital/clinic routing information if patient needs care
- Display recent refill details (days until refill, refill due status)
- Analyze and report patient sentiment
- Check if patient should be appreciated
- Suggest appropriate actions (notifications, care routing, interventions)
- If user requests to send notification, acknowledge and provide notification preview

**RESPONSE FORMAT:**
- Use clear markdown formatting
- Use **bold** for important information
- Use bullet points for lists
- Organize information in logical sections
- Be comprehensive but concise

**ACTION HANDLING:**
- When user requests specific actions (send notification, appreciate, check sentiment, etc.), the system has already called the appropriate agents
- Show the action results clearly in your response
- If notification was sent or previewed: you MUST show the **exact** notification message text verbatim from the Action Results (including the full pharmacy table: Pharmacy Name | Address | Phone | Opening Hours | Source). Do NOT paraphrase the message. Do NOT replace the pharmacy section with phrases like "visit your local pharmacy" or "They're there to help you."
- If appreciation was requested, show the appreciation message and status
- Always explain what actions were taken and what the results mean
- Present action results in a clear, organized format

**TONE:**
- Professional, helpful, and empathetic
- Clear and actionable
- Data-driven insights

**CRITICAL - NO PLACEHOLDERS:**
- NEVER use placeholder text such as [Insert ...], [Patient Name], [X days], or similar. Use ONLY actual data from the context provided.
- If patient data or notification message is not in the context (e.g. patient not found, or no data for that Member ID), say clearly: "Patient not found" or "Could not load data for this patient. Please check the Member ID (e.g. IN-100003) and try again."
- When showing the notification message or preview, you MUST output the exact message from the Action Results verbatim, including the full pharmacy table.

Always provide complete, comprehensive answers using all available information."""
    
    # Build comprehensive context from available data
    context_parts = []
    
    if requested_member_id and not patient_data:
        context_parts.append(f"**Important:** The user asked about patient Member ID **{requested_member_id}**. This patient was NOT FOUND in the current dataset. You MUST tell the user clearly that the patient was not found and suggest they check the Member ID or try another patient.")
    
    if dashboard_context:
        kpis = dashboard_context.get('kpis', {})
        system = dashboard_context.get('system', {})
        
        context_parts.append("**Dashboard Context:**")
        if kpis:
            context_parts.append(f"- Average Adherence: {kpis.get('avg_adherence_now', 0):.1f}%")
            context_parts.append(f"- High-Risk Patients: {kpis.get('high_risk_now', 0)}")
            context_parts.append(f"- Interventions (30 days): {kpis.get('interventions_30d', 0)}")
            context_parts.append(f"- Interventions Today: {kpis.get('notified_today', 0)}")
            context_parts.append(f"- Notified Patients: {kpis.get('notified_unique', 0)}")
            context_parts.append(f"- Responded Patients: {kpis.get('responded_unique', 0)}")
            response_rate = (kpis.get('responded_unique', 0) / kpis.get('notified_unique', 1)) * 100 if kpis.get('notified_unique', 0) > 0 else 0
            context_parts.append(f"- Response Rate: {response_rate:.1f}%")
            context_parts.append(f"- Projected Savings (30 days): ₹{kpis.get('proj_savings_month', 0):,.0f}")
        
        if system:
            context_parts.append(f"- System Status: {system.get('status', 'Unknown')}")
            context_parts.append(f"- Live Monitoring: {'ON' if system.get('live_on', False) else 'OFF'}")
            context_parts.append(f"- Last Sync: {system.get('last_sync', '—')}")
            context_parts.append(f"- Agents Running: {system.get('agents_running', 0)}")
    
    # Add comprehensive patient information
    if patient_data:
        context_parts.append("\n**Patient Basic Information:**")
        # Organize patient data into categories
        demographics = []
        clinical = []
        contact = []
        medication = []
        refill = []
        other = []
        
        for key, value in patient_data.items():
            if not value or str(value) == 'nan' or str(value).strip() == '':
                continue
            value_str = str(value)
            
            # Categorize fields
            key_lower = key.lower()
            if any(term in key_lower for term in ['name', 'member id', 'age', 'gender', 'dob', 'date of birth']):
                demographics.append(f"- {key}: {value_str}")
            elif any(term in key_lower for term in ['adherence', 'risk', 'score', 'sentiment', 'behavior', 'clinical']):
                clinical.append(f"- {key}: {value_str}")
            elif any(term in key_lower for term in ['contact', 'email', 'phone', 'address']):
                contact.append(f"- {key}: {value_str}")
            elif any(term in key_lower for term in ['medication', 'drug', 'prescription']):
                medication.append(f"- {key}: {value_str}")
            elif any(term in key_lower for term in ['refill', 'days until', 'days since', 'gap']):
                refill.append(f"- {key}: {value_str}")
            else:
                other.append(f"- {key}: {value_str}")
        
        if demographics:
            context_parts.append("\n*Demographics:*")
            context_parts.extend(demographics)
        if clinical:
            context_parts.append("\n*Clinical Information:*")
            context_parts.extend(clinical)
        if contact:
            context_parts.append("\n*Contact Information:*")
            context_parts.extend(contact)
        if medication:
            context_parts.append("\n*Medication Information:*")
            context_parts.extend(medication)
        if refill:
            context_parts.append("\n*Refill Information:*")
            context_parts.extend(refill)
        if other:
            context_parts.append("\n*Additional Information:*")
            context_parts.extend(other)
    
    # Add comprehensive patient analysis if available
    if patient_analysis:
        context_parts.append("\n**Comprehensive Patient Analysis:**")
        
        if 'risk' in patient_analysis:
            risk = patient_analysis['risk']
            context_parts.append(f"\n*Risk Assessment:*")
            context_parts.append(f"- Risk Score: {risk.get('risk_score', 'N/A')}")
            context_parts.append(f"- Risk Label: {risk.get('risk_label', 'N/A')}")
            context_parts.append(f"- Risk Factors: {', '.join(risk.get('risk_factors', []))}")
        
        if 'sentiment' in patient_analysis:
            sentiment = patient_analysis['sentiment']
            context_parts.append(f"\n*Sentiment & Behavior Analysis:*")
            context_parts.append(f"- Sentiment Score: {sentiment.get('sentiment_score', 'N/A')}")
            context_parts.append(f"- Sentiment Label: {sentiment.get('sentiment_label', 'N/A')}")
            context_parts.append(f"- Behavior Pattern: {sentiment.get('behavior_pattern', 'N/A')}")
            insights = sentiment.get('behavioral_insights', [])
            if insights:
                context_parts.append(f"- Behavioral Insights: {', '.join(insights)}")
        
        if 'care_routing' in patient_analysis:
            routing = patient_analysis['care_routing']
            context_parts.append(f"\n*Care Routing:*")
            context_parts.append(f"- Needs Routing: {'Yes' if routing.get('needs_routing') else 'No'}")
            if routing.get('needs_routing'):
                context_parts.append(f"- Routing Level: {routing.get('routing_level', 'N/A')}")
                context_parts.append(f"- Routing Target: {routing.get('routing_target', 'N/A')}")
                context_parts.append(f"- Urgency: {routing.get('urgency', 'N/A')}")
                context_parts.append(f"- Reason: {routing.get('routing_reason', 'N/A')}")
                context_parts.append(f"- Recommended Action: {routing.get('recommended_action', 'N/A')}")
        
        if 'care_needs' in patient_analysis:
            needs = patient_analysis['care_needs']
            context_parts.append(f"\n*Care Needs:*")
            context_parts.append(f"- Priority: {needs.get('priority', 'N/A')}")
            context_parts.append(f"- Needs Attention: {'Yes' if needs.get('needs_attention') else 'No'}")
            if needs.get('refill_assistance'):
                context_parts.append(f"- Refill Assistance: {needs.get('refill_assistance')}")
            actions = needs.get('care_actions', [])
            if actions:
                context_parts.append(f"- Care Actions: {', '.join(actions)}")
            interventions = needs.get('recommended_interventions', [])
            if interventions:
                context_parts.append(f"- Recommended Interventions: {', '.join(interventions)}")
        
        if 'appreciation' in patient_analysis:
            appreciation = patient_analysis['appreciation']
            context_parts.append(f"\n*Appreciation Status:*")
            context_parts.append(f"- Should Appreciate: {'Yes' if appreciation.get('should_appreciate') else 'No'}")
            if appreciation.get('should_appreciate'):
                context_parts.append(f"- Reason: {appreciation.get('appreciation_reason', 'N/A')}")
                context_parts.append(f"- Message: {appreciation.get('appreciation_message', 'N/A')}")
        
        if 'orchestration' in patient_analysis:
            orchestration = patient_analysis['orchestration']
            context_parts.append(f"\n*Recommended Actions:*")
            actions = orchestration.get('actions', [])
            if actions:
                context_parts.append(f"- Actions: {', '.join(actions)}")
            if orchestration.get('message'):
                context_parts.append(f"- Notification Preview: {orchestration.get('message', 'N/A')}")
            route = orchestration.get('route', {})
            if route:
                context_parts.append(f"- Contact Channel: {route.get('channel', 'N/A')}")
                context_parts.append(f"- Allowed: {'Yes' if route.get('allowed') else 'No'}")
    
    # Add action results if specific actions were requested
    if action_results:
        context_parts.append("\n**Action Results (Requested Information):**")
        
        if 'notification' in action_results:
            notif = action_results['notification']
            exact_message = notif.get('message', '') or 'N/A'
            context_parts.append(f"\n*Notification Action:*")
            context_parts.append(f"- Status: {notif.get('status', 'Unknown')}")
            context_parts.append(f"- Channel: {notif.get('channel', 'unknown')}")
            context_parts.append(f"- Sent: {'Yes' if notif.get('sent') else 'No (Preview only)'}")
            context_parts.append(f"- **Exact notification message (show this verbatim in your response, including the pharmacy table):**\n```\n{exact_message}\n```")
            if notif.get('actions'):
                context_parts.append(f"- Recommended Actions: {', '.join(notif.get('actions', []))}")
        
        if 'appreciation' in action_results:
            appr = action_results['appreciation']
            context_parts.append(f"\n*Appreciation Check:*")
            context_parts.append(f"- Should Appreciate: {'Yes' if appr.get('should_appreciate') else 'No'}")
            if appr.get('should_appreciate'):
                context_parts.append(f"- Reason: {appr.get('appreciation_reason', 'N/A')}")
                context_parts.append(f"- Message: {appr.get('appreciation_message', 'N/A')}")
                if 'appreciation_action' in action_results:
                    context_parts.append(f"- Action Status: Ready to send")
            else:
                context_parts.append(f"- Patient does not currently meet appreciation criteria")
        
        if 'sentiment' in action_results:
            sent = action_results['sentiment']
            context_parts.append(f"\n*Sentiment Analysis Results:*")
            context_parts.append(f"- Sentiment Score: {sent.get('sentiment_score', 'N/A')} (0.0 = negative, 1.0 = positive)")
            context_parts.append(f"- Sentiment Label: {sent.get('sentiment_label', 'N/A')}")
            context_parts.append(f"- Behavior Pattern: {sent.get('behavior_pattern', 'N/A')}")
            insights = sent.get('behavioral_insights', [])
            if insights:
                context_parts.append(f"- Behavioral Insights: {', '.join(insights)}")
        
        if 'risk' in action_results:
            risk = action_results['risk']
            context_parts.append(f"\n*Risk Assessment Results:*")
            context_parts.append(f"- Risk Score: {risk.get('risk_score', 'N/A')}")
            context_parts.append(f"- Risk Label: {risk.get('risk_label', 'N/A')}")
            factors = risk.get('risk_factors', [])
            if factors:
                context_parts.append(f"- Risk Factors: {', '.join(factors)}")
        
        if 'care_routing' in action_results:
            routing = action_results['care_routing']
            context_parts.append(f"\n*Care Routing Results:*")
            context_parts.append(f"- Needs Routing: {'Yes' if routing.get('needs_routing') else 'No'}")
            if routing.get('needs_routing'):
                context_parts.append(f"- Routing Level: {routing.get('routing_level', 'N/A')}")
                context_parts.append(f"- Routing Target: {routing.get('routing_target', 'N/A')}")
                context_parts.append(f"- Urgency: {routing.get('urgency', 'N/A')}")
                context_parts.append(f"- Reason: {routing.get('routing_reason', 'N/A')}")
                context_parts.append(f"- Recommended Action: {routing.get('recommended_action', 'N/A')}")
        
        if 'care_needs' in action_results:
            needs = action_results['care_needs']
            context_parts.append(f"\n*Care Needs Results:*")
            context_parts.append(f"- Priority: {needs.get('priority', 'N/A')}")
            context_parts.append(f"- Needs Attention: {'Yes' if needs.get('needs_attention') else 'No'}")
            if needs.get('refill_assistance'):
                context_parts.append(f"- Refill Assistance Level: {needs.get('refill_assistance')}")
            actions_list = needs.get('care_actions', [])
            if actions_list:
                context_parts.append(f"- Care Actions Required: {', '.join(actions_list)}")
            interventions = needs.get('recommended_interventions', [])
            if interventions:
                context_parts.append(f"- Recommended Interventions: {', '.join(interventions)}")
        
        if 'error' in action_results:
            context_parts.append(f"\n*Error:* {action_results['error']}")
    
    context_text = "\n".join(context_parts) if context_parts else "No additional context available."
    
    # Build messages for OpenAI
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    
    # Add conversation history if available
    if conversation_history:
        for msg in conversation_history[-10:]:  # Keep last 10 messages for context
            if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
                messages.append({"role": msg['role'], "content": msg['content']})
    
    # Add current context and user message
    if context_parts:
        instruction = "Use this information to answer the user's question accurately."
        if action_results:
            instruction += "\n\nIMPORTANT: The user has requested specific actions. Action results have been gathered and are shown in the 'Action Results' section above. You MUST clearly present these action results in your response, showing what was done, what information was gathered, and what it means for the patient."
            if "notification" in action_results:
                instruction += "\n\nNOTIFICATION MESSAGE RULE: When Action Results include a Notification Action, your response MUST include the exact notification message in full. Copy the message from the code block above character-for-character (including the full pharmacy table: Pharmacy Name | Address | Phone | Opening Hours | Source). Do NOT replace it with a summary, 'Dear Patient...', or 'Your Local Pharmacy'. Output it in a markdown code block or blockquote."
        messages.append({
            "role": "system",
            "content": f"Current dashboard context:\n{context_text}\n\n{instruction}"
        })
    
    messages.append({"role": "user", "content": user_message})

    try:
        response = openai_chat(messages, temperature=0.7, max_tokens=2000)
        # Always append the exact notification message when we have one, so the user never sees only an LLM paraphrase ("your local pharmacy")
        if action_results and "notification" in action_results:
            notif = action_results["notification"]
            exact = (notif.get("message") or "").strip()
            if exact:
                response = response.rstrip() + "\n\n---\n\n**Notification message (includes nearest pharmacy by city):**\n\n```\n" + exact + "\n```"
        return response
    except Exception as e:
        return f"I apologize, but I encountered an error while processing your request: {str(e)}. Please try again or rephrase your question."
