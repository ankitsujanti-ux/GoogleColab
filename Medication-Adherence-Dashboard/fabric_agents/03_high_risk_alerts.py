"""
═══════════════════════════════════════════════════════════════════════════════
  NOTEBOOK 3: High-Risk Patient Alerts — Targeted Notifications
═══════════════════════════════════════════════════════════════════════════════

STEPS TO RUN IN FABRIC:
  1. Create a new Fabric Notebook
  2. Attach it to your Lakehouse
  3. Copy-paste each cell below into separate notebook cells
  4. Ensure 02_run_agent_pipeline.py has been run first
  5. Run all cells

This notebook:
  - Queries `patients_with_agents` for HIGH-RISK patients only
  - Sends targeted real notifications (Twilio SMS/Call/WhatsApp, Pushover, Email)
  - Logs all notification attempts to `notification_log` Delta table
  - Updates the source table with notification timestamps
═══════════════════════════════════════════════════════════════════════════════
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 1: Install dependencies
# ═══════════════════════════════════════════════════════════════════════════════
# %pip install openai requests twilio sendgrid python-dotenv openpyxl

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 2: Load .env and imports
# ═══════════════════════════════════════════════════════════════════════════════

import os
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import json

# Add project code to path
PROJECT_ROOT = Path("/lakehouse/default/Files/code")
if PROJECT_ROOT.exists():
    sys.path.insert(0, str(PROJECT_ROOT))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env
from dotenv import load_dotenv

for env_path in [
    Path("/lakehouse/default/Files/.env"),
    Path("/lakehouse/default/Files/code/.env"),
    Path(__file__).resolve().parent.parent / ".env",
]:
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print(f"✅ Loaded .env from: {env_path}")
        break

# Import agent functions
from agent import (
    build_adherence_message,
    determine_contact_route,
    enforce_policy_and_throttle,
    notify_patient,
    send_twilio_sms,
    send_twilio_whatsapp,
    make_twilio_voice_call,
    send_email,
    _any_contact_sent_today,
)

try:
    from agent import send_pushover_message
except ImportError:
    # Inline fallback
    import requests as req
    def send_pushover_message(user_key, token, title, message, **kwargs):
        try:
            r = req.post("https://api.pushover.net/1/messages.json", data={
                "token": token, "user": user_key,
                "title": title, "message": message, "priority": 0,
            }, timeout=10)
            return r.json()
        except Exception as e:
            return {"error": str(e)}

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

print("✅ All imports loaded")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 3: Load high-risk patients from agents table
# ═══════════════════════════════════════════════════════════════════════════════

AGENTS_TABLE = "patients_with_agents"
NOTIFICATION_LOG_TABLE = "notification_log"

print(f"Loading high-risk patients from: {AGENTS_TABLE}")

high_risk_sdf = spark.table(AGENTS_TABLE).filter("risk_label = 'High'")
hr_count = high_risk_sdf.count()
print(f"Found {hr_count} high-risk patient records")

if hr_count == 0:
    print("No high-risk patients found. Exiting.")
else:
    high_risk_pdf = high_risk_sdf.toPandas()
    print(f"Columns: {list(high_risk_pdf.columns)}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 4: Send targeted notifications to high-risk patients
# ═══════════════════════════════════════════════════════════════════════════════

PUSHOVER_USER_KEY = (os.getenv("PUSHOVER_USER_KEY") or "").strip()
PUSHOVER_API_TOKEN = (os.getenv("PUSHOVER_API_TOKEN") or "").strip()
TWILIO_ACCOUNT_SID = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
SENDGRID_API_KEY = (os.getenv("SENDGRID_API_KEY") or "").strip()

notification_log = []

# De-duplicate: one notification per patient (latest row)
if hr_count > 0:
    # Group by Member_ID and take the latest record
    hr_unique = high_risk_pdf.sort_values("agent_run_timestamp", ascending=False) \
        .drop_duplicates(subset=["Member_ID"], keep="first")

    print(f"\n{'='*60}")
    print(f"  SENDING NOTIFICATIONS TO {len(hr_unique)} HIGH-RISK PATIENTS")
    print(f"{'='*60}\n")

    sent_count = 0
    failed_count = 0
    skipped_count = 0

    for idx, row in hr_unique.iterrows():
        member_id = row.get("Member_ID", "")
        patient_name = row.get("Patient_Name", "Unknown")
        adherence = row.get("Adherence_Percentage", 0)
        risk_score = row.get("risk_score", 0)
        channel = row.get("route_channel", "pushover")
        phone = row.get("Patient_Contact", "")
        email_addr = row.get("Patient_EmailID", "")
        medication = row.get("Medication_Name", "Medication")
        city = row.get("City", "")

        # Skip if already notified (notification_status = Sent)
        if row.get("notification_status") == "Sent":
            skipped_count += 1
            notification_log.append({
                "member_id": member_id,
                "patient_name": patient_name,
                "channel": channel,
                "status": "Skipped",
                "reason": "Already notified in pipeline run",
                "timestamp": pd.Timestamp.now(),
            })
            continue

        # Build message
        msg_row = {
            "Patient Name": patient_name,
            "Medication Name": medication,
            "Adherence Percentage": adherence,
            "City": city,
        }
        message = build_adherence_message(msg_row)

        # Send notification based on channel
        result = {"status": "Failed", "error": "Unknown channel"}

        try:
            if channel == "sms" and phone and TWILIO_ACCOUNT_SID:
                sms_res = send_twilio_sms(to_number=str(phone), body=message)
                if "error" not in sms_res:
                    result = {"status": "Sent", "sid": sms_res.get("sid", "")}
                else:
                    result = {"status": "Failed", "error": sms_res.get("error", "")}

            elif channel == "call" and phone and TWILIO_ACCOUNT_SID:
                call_res = make_twilio_voice_call(to_number=str(phone), message=message)
                if "error" not in call_res:
                    result = {"status": "Sent", "sid": call_res.get("sid", "")}
                else:
                    result = {"status": "Failed", "error": call_res.get("error", "")}

            elif channel == "whatsapp" and phone and TWILIO_ACCOUNT_SID:
                wa_res = send_twilio_whatsapp(to_number=str(phone), body=message)
                if "error" not in wa_res:
                    result = {"status": "Sent", "sid": wa_res.get("sid", "")}
                else:
                    result = {"status": "Failed", "error": wa_res.get("error", "")}

            elif channel == "email" and email_addr and SENDGRID_API_KEY:
                email_res = send_email(
                    to_email=str(email_addr),
                    subject=f"Medication Adherence Alert — {medication}",
                    body=message,
                )
                if "error" not in email_res:
                    result = {"status": "Sent"}
                else:
                    result = {"status": "Failed", "error": email_res.get("error", "")}

            elif channel == "pushover" and PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY:
                po_res = send_pushover_message(
                    user_key=PUSHOVER_USER_KEY,
                    token=PUSHOVER_API_TOKEN,
                    title=f"⚠️ High Risk: {patient_name}",
                    message=message,
                )
                if "error" not in po_res:
                    result = {"status": "Sent", "request": po_res.get("request", "")}
                else:
                    result = {"status": "Failed", "error": po_res.get("error", "")}

            # Fallback to Pushover if primary channel not configured
            elif PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY:
                po_res = send_pushover_message(
                    user_key=PUSHOVER_USER_KEY,
                    token=PUSHOVER_API_TOKEN,
                    title=f"⚠️ High Risk: {patient_name}",
                    message=message,
                )
                if "error" not in po_res:
                    result = {"status": "Sent (Pushover fallback)", "request": po_res.get("request", "")}
                else:
                    result = {"status": "Failed", "error": po_res.get("error", "")}
            else:
                result = {"status": "Failed", "error": f"Channel '{channel}' not configured"}

        except Exception as e:
            result = {"status": "Failed", "error": str(e)}

        # Log result
        is_sent = "Sent" in result.get("status", "")
        if is_sent:
            sent_count += 1
            print(f"  ✅ {patient_name} ({member_id}): {result['status']} via {channel}")
        else:
            failed_count += 1
            print(f"  ❌ {patient_name} ({member_id}): {result['status']} — {result.get('error','')}")

        notification_log.append({
            "member_id": member_id,
            "patient_name": patient_name,
            "adherence_percentage": adherence,
            "risk_score": risk_score,
            "channel": channel,
            "status": result.get("status", "Failed"),
            "error": result.get("error", ""),
            "message_preview": message[:200],
            "timestamp": pd.Timestamp.now(),
        })

    print(f"\n{'='*60}")
    print(f"  NOTIFICATION SUMMARY")
    print(f"{'='*60}")
    print(f"  Total high-risk patients: {len(hr_unique)}")
    print(f"  Sent:                     {sent_count}")
    print(f"  Failed:                   {failed_count}")
    print(f"  Skipped (already sent):   {skipped_count}")
    print(f"{'='*60}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 5: Save notification log to Lakehouse
# ═══════════════════════════════════════════════════════════════════════════════

if notification_log:
    log_pdf = pd.DataFrame(notification_log)
    log_pdf["timestamp"] = pd.to_datetime(log_pdf["timestamp"], errors="coerce")

    log_sdf = spark.createDataFrame(log_pdf)

    # Append to notification_log table (don't overwrite previous runs)
    log_sdf.write.mode("append").format("delta").saveAsTable(NOTIFICATION_LOG_TABLE)

    print(f"\n✅ Saved {len(notification_log)} log entries to: {NOTIFICATION_LOG_TABLE}")

    # Show log
    spark.table(NOTIFICATION_LOG_TABLE).orderBy("timestamp", ascending=False).show(10, truncate=False)
else:
    print("\nNo notification log entries to save.")

print("\n" + "=" * 60)
print("  ✅ HIGH-RISK ALERTS COMPLETE")
print("  Next: Run 04_build_final_report_table.py")
print("=" * 60)
