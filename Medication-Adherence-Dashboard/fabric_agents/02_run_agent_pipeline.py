"""
═══════════════════════════════════════════════════════════════════════════════
  NOTEBOOK 2: Run Agent Pipeline on Lakehouse Data
═══════════════════════════════════════════════════════════════════════════════

STEPS TO RUN IN FABRIC:
  1. Create a new Fabric Notebook in your workspace
  2. Attach it to your Lakehouse
  3. Copy-paste each cell below into separate notebook cells
  4. Ensure .env is uploaded to Lakehouse Files
  5. Ensure 01_setup_lakehouse.py has been run (patients table exists)
  6. Run all cells

This notebook:
  - Loads .env from Lakehouse Files for API keys
  - Reads `patients` Delta table
  - Runs the full agent pipeline on each patient row:
      Data Quality → Risk Assessment → Sentiment → Care Routing →
      Consent/Channel → Throttling → Orchestration (with REAL notifications)
  - Writes enriched results to `patients_with_agents` Delta table
═══════════════════════════════════════════════════════════════════════════════
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 1: Install dependencies
# ═══════════════════════════════════════════════════════════════════════════════
# %pip install openai requests twilio sendgrid python-dotenv openpyxl pandas

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 2: Load .env from Lakehouse Files
# ═══════════════════════════════════════════════════════════════════════════════

import os
import sys
from pathlib import Path

# Add project root to sys.path so agent.py, pharmacy.py etc. can be imported
# In Fabric, upload the project Python files to Lakehouse Files/code/
# or use %run to reference them
PROJECT_ROOT = Path("/lakehouse/default/Files/code")
if PROJECT_ROOT.exists():
    sys.path.insert(0, str(PROJECT_ROOT))
    print(f"Added {PROJECT_ROOT} to Python path")
else:
    # Fallback: try parent directory (local dev)
    _local_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_local_root))
    print(f"Added {_local_root} to Python path (local dev)")

# Load .env
from dotenv import load_dotenv

ENV_CANDIDATES = [
    Path("/lakehouse/default/Files/.env"),
    Path("/lakehouse/default/Files/code/.env"),
    Path(__file__).resolve().parent.parent / ".env",
]

env_loaded = False
for env_path in ENV_CANDIDATES:
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print(f"✅ Loaded .env from: {env_path}")
        env_loaded = True
        break

if not env_loaded:
    print("⚠️ WARNING: No .env file found. API keys must be set as environment variables.")

# Verify critical keys
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
PUSHOVER_USER_KEY = (os.getenv("PUSHOVER_USER_KEY") or "").strip()
PUSHOVER_API_TOKEN = (os.getenv("PUSHOVER_API_TOKEN") or "").strip()
TWILIO_ACCOUNT_SID = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()

print(f"OpenAI API Key:  {'✅ Set' if OPENAI_API_KEY else '❌ Missing'}")
print(f"Pushover:        {'✅ Set' if (PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN) else '❌ Missing'}")
print(f"Twilio:          {'✅ Set' if TWILIO_ACCOUNT_SID else '❌ Missing'}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 3: Import agent functions
# ═══════════════════════════════════════════════════════════════════════════════

import pandas as pd
import json
from datetime import datetime

# These imports work if agent.py, pharmacy.py, config.py, structure.py,
# runtime_paths.py, utils.py are in the Python path (Lakehouse Files/code/)
try:
    from agent import (
        validate_and_normalize_row,
        assess_adherence_risk,
        analyze_patient_sentiment_and_behavior,
        check_and_appreciate_refilled_patient,
        determine_care_routing,
        identify_patient_care_needs,
        determine_contact_route,
        enforce_policy_and_throttle,
        orchestrate_refill_and_notify,
        build_adherence_message,
        _any_contact_sent_today,
    )
    print("✅ Agent functions imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure agent.py and its dependencies are uploaded to Lakehouse Files/code/")
    raise

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 4: Load patients table from Lakehouse
# ═══════════════════════════════════════════════════════════════════════════════

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

TABLE_NAME = "patients"
AGENTS_TABLE = "patients_with_agents"

print(f"Loading table: {TABLE_NAME}")
patients_sdf = spark.table(TABLE_NAME)
row_count = patients_sdf.count()
print(f"✅ Loaded {row_count} rows from {TABLE_NAME}")

# Convert to Pandas for row-level agent processing
patients_pdf = patients_sdf.toPandas()
patients_pdf.columns = [str(c).strip() for c in patients_pdf.columns]
print(f"Columns: {list(patients_pdf.columns)}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 5: Run agent pipeline on each row
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 60)
print("  Running Agent Pipeline")
print("=" * 60)

# Track stats
stats = {
    "total": 0,
    "high_risk": 0,
    "medium_risk": 0,
    "low_risk": 0,
    "notifications_sent": 0,
    "notifications_failed": 0,
    "escalated": 0,
    "appreciated": 0,
    "errors": 0,
}

enriched_rows = []

# Policy context for throttling
today = pd.Timestamp.now().normalize()
today_sent_count = 0
OUTREACH_MAX_PER_DAY = int(os.getenv("OUTREACH_MAX_PER_DAY", "100"))
OUTREACH_COOLDOWN_DAYS = int(os.getenv("OUTREACH_COOLDOWN_DAYS", "2"))

for idx, row in patients_pdf.iterrows():
    stats["total"] += 1
    row_dict = row.to_dict()

    try:
        # Step 1: Data Quality Agent — validate and normalize
        normalized = validate_and_normalize_row(row_dict)
        clean = normalized["clean"]

        # Step 2: Adherence Risk Agent — assess risk
        risk = assess_adherence_risk(clean)
        risk_score = risk.get("risk_score", 0)
        risk_label = risk.get("risk_label", "Low")

        if risk_label == "High":
            stats["high_risk"] += 1
        elif risk_label == "Medium":
            stats["medium_risk"] += 1
        else:
            stats["low_risk"] += 1

        # Step 3: Sentiment & Behavior Analysis Agent
        sentiment = analyze_patient_sentiment_and_behavior(clean)

        # Step 4: Care Routing Agent
        care_routing = determine_care_routing(clean, risk_assessment=risk)

        # Step 5: Patient Care Needs Agent
        care_needs = identify_patient_care_needs(
            clean, risk_assessment=risk, sentiment_analysis=sentiment
        )

        # Step 6: Consent & Channel Routing Agent
        route = determine_contact_route(clean)

        # Step 7: Build policy context for throttling
        last_sent_ts = clean.get("NotificationSentOn")
        policy_context = {
            "today_sent": today_sent_count,
            "cap": OUTREACH_MAX_PER_DAY,
            "cooldown_days": OUTREACH_COOLDOWN_DAYS,
            "last_sent_ts": last_sent_ts,
        }

        # Step 8: Safety & Throttling Agent
        policy_gate = enforce_policy_and_throttle(clean, policy_context=policy_context)

        # Step 9: Orchestration Agent — with REAL notification sending
        result = orchestrate_refill_and_notify(
            clean, send=True, policy_context=policy_context
        )

        status = result.get("status", "Planned")
        if status in ("Sent", "Queued"):
            stats["notifications_sent"] += 1
            today_sent_count += 1
        elif status == "Failed":
            stats["notifications_failed"] += 1

        if care_routing.get("needs_routing", False):
            stats["escalated"] += 1

        appreciation = result.get("appreciation", {})
        if appreciation.get("should_appreciate", False):
            stats["appreciated"] += 1

        # Build enriched output row
        enriched = {
            # Original patient data
            "Member_ID": clean.get("Member ID", ""),
            "Patient_Name": clean.get("Patient Name", ""),
            "Medication_Name": clean.get("Medication Name", ""),
            "Patient_Contact": clean.get("Patient Contact", ""),
            "Patient_EmailID": clean.get("Patient EmailID", ""),
            "City": clean.get("City", ""),
            "Adherence_Percentage": clean.get("Adherence Percentage", 0),
            "days_until_refill": clean.get("days_until_refill"),
            "refill_due": clean.get("refill_due", False),
            "ConsentOK": clean.get("ConsentOK"),
            "EventDate": clean.get("EventDate"),

            # Risk Agent output
            "risk_score": risk_score,
            "risk_label": risk_label,
            "risk_signals": "; ".join(risk.get("signals", [])),
            "risk_confidence": risk.get("confidence", 0),

            # Sentiment Agent output
            "sentiment_score": sentiment.get("sentiment_score", 0),
            "sentiment_label": sentiment.get("sentiment_label", "neutral"),
            "behavior_pattern": sentiment.get("behavior_pattern", "stable"),

            # Care Routing Agent output
            "should_route": care_routing.get("needs_routing", False),
            "routing_level": care_routing.get("routing_level", ""),
            "routing_target": care_routing.get("routing_target", ""),
            "routing_reason": care_routing.get("routing_reason", ""),
            "routing_urgency": care_routing.get("urgency", ""),

            # Care Needs Agent output
            "care_priority": care_needs.get("priority", ""),
            "care_summary": care_needs.get("summary", ""),
            "needs_attention": care_needs.get("needs_attention", False),

            # Consent & Channel output
            "route_channel": route.get("channel", "none"),
            "route_allowed": route.get("allowed", False),
            "route_reason": route.get("reason", ""),

            # Throttling output
            "policy_allowed": policy_gate.get("allowed", False),
            "policy_reasons": "; ".join(policy_gate.get("reasons", [])),

            # Orchestration result
            "notification_status": status,
            "notification_channel_used": result.get("route", {}).get("channel", ""),
            "notification_message_preview": (result.get("message", "") or "")[:500],

            # Appreciation
            "appreciation_sent": appreciation.get("should_appreciate", False),
            "appreciation_reason": appreciation.get("appreciation_reason", ""),

            # Notification timestamps
            "NotificationSentOn": clean.get("NotificationSentOn"),
            "NotificationChannel": clean.get("NotificationChannel", ""),
            "NotificationStatus": clean.get("NotificationStatus", ""),
            "RoutedToClinicianOn": clean.get("RoutedToClinicianOn"),
            "AppreciationSentOn": clean.get("AppreciationSentOn"),

            # Metadata
            "agent_run_timestamp": pd.Timestamp.now(),
            "agent_pipeline_version": "1.0",
        }

        enriched_rows.append(enriched)

    except Exception as e:
        stats["errors"] += 1
        print(f"  ❌ Error processing row {idx} (Member ID: {row_dict.get('Member ID', '?')}): {e}")
        # Still add a minimal row so we don't lose the patient
        enriched_rows.append({
            "Member_ID": str(row_dict.get("Member ID", "")),
            "Patient_Name": str(row_dict.get("Patient Name", "")),
            "error": str(e),
            "agent_run_timestamp": pd.Timestamp.now(),
            "agent_pipeline_version": "1.0",
        })

    # Progress log every 50 rows
    if (idx + 1) % 50 == 0:
        print(f"  Processed {idx + 1}/{len(patients_pdf)} rows...")

print(f"\n✅ Pipeline complete. Processed {stats['total']} rows.")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 6: Print pipeline summary
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 60)
print("  AGENT PIPELINE SUMMARY")
print("=" * 60)
print(f"  Total patients processed:   {stats['total']}")
print(f"  High risk:                  {stats['high_risk']}")
print(f"  Medium risk:                {stats['medium_risk']}")
print(f"  Low risk:                   {stats['low_risk']}")
print(f"  Notifications sent:         {stats['notifications_sent']}")
print(f"  Notifications failed:       {stats['notifications_failed']}")
print(f"  Escalated to clinician:     {stats['escalated']}")
print(f"  Appreciated:                {stats['appreciated']}")
print(f"  Errors:                     {stats['errors']}")
print("=" * 60)

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 7: Write enriched results to Lakehouse Delta table
# ═══════════════════════════════════════════════════════════════════════════════

enriched_pdf = pd.DataFrame(enriched_rows)

# Convert datetime columns
dt_cols = ["EventDate", "NotificationSentOn", "RoutedToClinicianOn",
           "AppreciationSentOn", "agent_run_timestamp"]
for col in dt_cols:
    if col in enriched_pdf.columns:
        enriched_pdf[col] = pd.to_datetime(enriched_pdf[col], errors="coerce")

# Convert boolean columns
bool_cols = ["refill_due", "should_route", "route_allowed", "policy_allowed",
             "needs_attention", "appreciation_sent"]
for col in bool_cols:
    if col in enriched_pdf.columns:
        enriched_pdf[col] = enriched_pdf[col].astype(bool)

# Convert numeric columns
num_cols = ["Adherence_Percentage", "risk_score", "risk_confidence",
            "sentiment_score", "days_until_refill"]
for col in num_cols:
    if col in enriched_pdf.columns:
        enriched_pdf[col] = pd.to_numeric(enriched_pdf[col], errors="coerce")

print(f"Writing {len(enriched_pdf)} rows to {AGENTS_TABLE}...")
enriched_sdf = spark.createDataFrame(enriched_pdf)
enriched_sdf.write.mode("overwrite").format("delta").saveAsTable(AGENTS_TABLE)

print(f"\n✅ Successfully wrote {len(enriched_pdf)} rows to: {AGENTS_TABLE}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 8: Verify output table
# ═══════════════════════════════════════════════════════════════════════════════

result = spark.table(AGENTS_TABLE)
print(f"Table '{AGENTS_TABLE}' verification:")
print(f"  Row count: {result.count()}")
print(f"  Columns:   {len(result.columns)}")

# Show high-risk patients
print("\nHigh-risk patients:")
result.filter("risk_label = 'High'").select(
    "Member_ID", "Patient_Name", "Adherence_Percentage",
    "risk_score", "risk_label", "notification_status", "route_channel"
).show(10, truncate=False)

print("\n" + "=" * 60)
print("  ✅ AGENT PIPELINE COMPLETE")
print("  Next: Run 03_high_risk_alerts.py")
print("=" * 60)
