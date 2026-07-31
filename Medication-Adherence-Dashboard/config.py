# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

from runtime_paths import get_app_dir

# Load .env: try exe directory first, then current working directory (so running exe from project folder with .env works)
_app_dir = get_app_dir()
_env_app = _app_dir / ".env"
_env_cwd = Path.cwd() / ".env"
load_dotenv(_env_app)
# CWD .env fills in any vars not set by app-dir .env (e.g. when .env is only in project root)
if _env_cwd.resolve() != _env_app.resolve():
    load_dotenv(_env_cwd, override=False)

# Strip whitespace so accidental spaces/newlines don't truncate or break the key
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Trim to avoid spaces breaking the API
PUSHOVER_USER_KEY = (os.getenv("PUSHOVER_USER_KEY") or "").strip()
PUSHOVER_API_TOKEN = (os.getenv("PUSHOVER_API_TOKEN") or "").strip()
# When True, send notifications via Pushover (to your app) so you receive on your mobile
PREFER_PUSHOVER = os.getenv("PREFER_PUSHOVER", "true").strip().lower() in ("1", "true", "yes")

def _resolve_excel_path():
    p = os.getenv("EXCEL_PATH", "./Data/patients.xlsx")
    if os.path.isabs(p) and os.path.exists(p):
        return p
    # Resolve relative to app dir (exe dir when frozen) so it works on any machine
    base_dir = get_app_dir()
    resolved = (base_dir / p.replace("\\", "/").lstrip("./")).resolve()
    if resolved.exists():
        return str(resolved)
    # Try alternate casing (e.g. Data/ vs data/) on Windows
    name = os.path.basename(p)
    for folder in ("Data", "data"):
        alt = base_dir / folder / name
        if alt.exists():
            return str(alt)
    return str(resolved)  # return so FileNotFoundError shows expected path

EXCEL_PATH = _resolve_excel_path()

# Default to 60 seconds so live monitoring refreshes the dashboard every 1 minute
AUTO_REFRESH_SECONDS = int(os.getenv("AUTO_REFRESH_SECONDS", "60"))

THRESHOLD_LOW = float(os.getenv("THRESHOLD_LOW", "50"))
THRESHOLD_MED = float(os.getenv("THRESHOLD_MED", "80"))

# Toast notification timeout in seconds
TOAST_TIMEOUT = int(os.getenv("TOAST_TIMEOUT", "3"))

# Strip so spaces in .env don't break Twilio auth (error 20003)
TWILIO_ACCOUNT_SID = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
TWILIO_AUTH_TOKEN = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
TWILIO_FROM_NUMBER = (os.getenv("TWILIO_FROM_NUMBER") or "").strip()
# WhatsApp: use Twilio sandbox e.g. whatsapp:+14155238886 or your WhatsApp-enabled number
TWILIO_WHATSAPP_FROM = (os.getenv("TWILIO_WHATSAPP_FROM") or "").strip()

# SendGrid for email (optional)
SENDGRID_API_KEY = (os.getenv("SENDGRID_API_KEY") or "").strip()
SENDER_EMAIL = (os.getenv("SENDER_EMAIL") or "").strip()
