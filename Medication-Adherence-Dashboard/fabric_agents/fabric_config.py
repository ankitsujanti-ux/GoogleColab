"""
Fabric-compatible configuration loader.

Reads API keys and settings from:
  1. .env file uploaded to Fabric Lakehouse Files (preferred)
  2. Falls back to environment variables set in Fabric Spark config

Usage in Fabric Notebook:
    %run fabric_agents/fabric_config
    # Then: OPENAI_API_KEY, TWILIO_*, PUSHOVER_*, SENDGRID_*, thresholds are available
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate .env file
# ---------------------------------------------------------------------------
# In Fabric Notebooks the Lakehouse is mounted under /lakehouse/default/
# Upload your .env to the Lakehouse Files root.
# Priority: Lakehouse Files > project root > CWD
_CANDIDATE_ENV_PATHS = [
    Path("/lakehouse/default/Files/.env"),          # Fabric Lakehouse Files
    Path("/lakehouse/default/.env"),                # Fabric Lakehouse root
    Path(__file__).resolve().parent.parent / ".env", # Project root (local dev)
    Path.cwd() / ".env",                           # Current working directory
]

def _find_env_file() -> Path | None:
    for p in _CANDIDATE_ENV_PATHS:
        if p.exists():
            return p
    return None

_env_path = _find_env_file()

try:
    from dotenv import load_dotenv
    if _env_path:
        load_dotenv(_env_path, override=True)
        print(f"[fabric_config] Loaded .env from: {_env_path}")
    else:
        print("[fabric_config] WARNING: No .env file found. Using environment variables only.")
except ImportError:
    print("[fabric_config] python-dotenv not installed. Using environment variables only.")

# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ---------------------------------------------------------------------------
# Pushover (mobile push notifications)
# ---------------------------------------------------------------------------
PUSHOVER_USER_KEY = (os.getenv("PUSHOVER_USER_KEY") or "").strip()
PUSHOVER_API_TOKEN = (os.getenv("PUSHOVER_API_TOKEN") or "").strip()
PREFER_PUSHOVER = os.getenv("PREFER_PUSHOVER", "true").strip().lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Twilio (SMS, WhatsApp, Voice Calls)
# ---------------------------------------------------------------------------
TWILIO_ACCOUNT_SID = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
TWILIO_AUTH_TOKEN = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
TWILIO_FROM_NUMBER = (os.getenv("TWILIO_FROM_NUMBER") or "").strip()
TWILIO_WHATSAPP_FROM = (os.getenv("TWILIO_WHATSAPP_FROM") or "").strip()

# ---------------------------------------------------------------------------
# SendGrid (Email)
# ---------------------------------------------------------------------------
SENDGRID_API_KEY = (os.getenv("SENDGRID_API_KEY") or "").strip()
SENDER_EMAIL = (os.getenv("SENDER_EMAIL") or "").strip()

# ---------------------------------------------------------------------------
# Adherence Thresholds
# ---------------------------------------------------------------------------
THRESHOLD_LOW = float(os.getenv("THRESHOLD_LOW", "50"))
THRESHOLD_MED = float(os.getenv("THRESHOLD_MED", "80"))

# ---------------------------------------------------------------------------
# Dashboard / Pipeline
# ---------------------------------------------------------------------------
AUTO_REFRESH_SECONDS = int(os.getenv("AUTO_REFRESH_SECONDS", "60"))
TOAST_TIMEOUT = int(os.getenv("TOAST_TIMEOUT", "3"))

# ---------------------------------------------------------------------------
# Data paths — Fabric Lakehouse tables
# ---------------------------------------------------------------------------
# Excel file path (for local dev / upload script)
EXCEL_PATH = os.getenv("EXCEL_PATH", "./Data/patients.xlsx")

# Fabric Lakehouse table names
LAKEHOUSE_PATIENTS_TABLE = os.getenv("LAKEHOUSE_PATIENTS_TABLE", "patients")
LAKEHOUSE_AGENTS_TABLE = os.getenv("LAKEHOUSE_AGENTS_TABLE", "patients_with_agents")
LAKEHOUSE_FINAL_TABLE = os.getenv("LAKEHOUSE_FINAL_TABLE", "patients_final_report")
LAKEHOUSE_NOTIFICATION_LOG = os.getenv("LAKEHOUSE_NOTIFICATION_LOG", "notification_log")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def print_config_summary():
    """Print a summary of active configuration (safe — no secrets shown)."""
    print("=" * 60)
    print("  Fabric Config Summary")
    print("=" * 60)
    print(f"  .env loaded from:      {_env_path or 'NOT FOUND'}")
    print(f"  OpenAI API Key:        {'✅ Set' if OPENAI_API_KEY else '❌ Missing'}")
    print(f"  OpenAI Model:          {OPENAI_MODEL}")
    print(f"  Pushover:              {'✅ Set' if (PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN) else '❌ Missing'}")
    print(f"  Twilio (SMS/Call):     {'✅ Set' if (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN) else '❌ Missing'}")
    print(f"  SendGrid (Email):      {'✅ Set' if SENDGRID_API_KEY else '❌ Missing'}")
    print(f"  Threshold Low/Med:     {THRESHOLD_LOW}% / {THRESHOLD_MED}%")
    print(f"  Lakehouse Tables:      {LAKEHOUSE_PATIENTS_TABLE}, {LAKEHOUSE_AGENTS_TABLE}, {LAKEHOUSE_FINAL_TABLE}")
    print("=" * 60)

if __name__ == "__main__":
    print_config_summary()
