"""
Flask backend API for Medication Adherence Dashboard
Replaces Streamlit with a faster, more scalable solution
"""
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta
import threading
import time
import os
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dotenv import load_dotenv
import json
import hashlib
import requests
import uuid

from utils import load_patient_data, update_notification_sent_on, update_appreciation_sent_on
from config import (
    AUTO_REFRESH_SECONDS, THRESHOLD_LOW, THRESHOLD_MED, 
    OPENAI_API_KEY, OPENAI_MODEL, TOAST_TIMEOUT,
    PUSHOVER_API_TOKEN, PUSHOVER_USER_KEY,
    EXCEL_PATH,
)
from agent import (
    validate_and_normalize_row,
    assess_adherence_risk,
    orchestrate_refill_and_notify,
    analyze_patient_sentiment_and_behavior,
    check_and_appreciate_refilled_patient,
    determine_care_routing,
    identify_patient_care_needs,
    chatbot_agent,
    analyze_patient_response,
    generate_resolution_recommendations,
    auto_respond_to_patient,
    determine_contact_route,
    notify_patient,
    make_twilio_voice_call,
    send_twilio_sms,
    send_twilio_whatsapp,
    send_email,
    build_adherence_message,
    _any_contact_sent_today,
)
from structure import (
    load_html_template,
    load_html_template_template,
    html_escape,
    safe_float,
    fmt_minutes_ago,
    trend,
    name_parts,
)
from runtime_paths import get_resource_dir, get_app_dir

# .env is loaded in config.py from app dir
app = Flask(
    __name__,
    static_folder=str(get_resource_dir() / "frontend" / "build"),
    static_url_path="",
)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Render/Railway free tiers OOM/timeout when the heavy agent loop runs on every refresh.
ON_CLOUD = any(
    os.getenv(k)
    for k in ("RENDER", "RAILWAY_ENVIRONMENT", "FLY_APP_NAME", "WEBSITE_INSTANCE_ID")
)
# Heavy BackendRunner (per-row orchestration) kills the only gunicorn worker → Cloudflare 520.
ENABLE_HEAVY_BACKEND = os.getenv(
    "ENABLE_HEAVY_BACKEND",
    "0" if ON_CLOUD else "1",
).strip().lower() in ("1", "true", "yes")

# Global state
backend_runner = None
last_sync_ts = datetime.now()
audit_log = []
high_risk_notifications = []
processed_high_risk_patients = set()
previous_columns_hash = None
previous_data_hash = None
shown_notification_popups = set()
last_sent_events = []
live_on = True
# On cloud, default OFF so the process stays responsive; local exe keeps prior behavior.
send_auto_notifications = (
    os.getenv("SEND_AUTO_NOTIFICATIONS", "0" if ON_CLOUD else "1").strip().lower()
    in ("1", "true", "yes")
)
patient_previous_states = {}  # Store previous patient states for comparison
refresh_interval = AUTO_REFRESH_SECONDS

# Short-lived response cache so polling does not thrash CPU/memory
_dashboard_cache = {"ts": 0.0, "payload": None}
_DASHBOARD_CACHE_TTL = float(os.getenv("DASHBOARD_CACHE_TTL", "20" if ON_CLOUD else "5"))

# Helper functions are now imported from structure.py

# Backend Runner (background thread)
class BackendRunner:
    def __init__(self, refresh_sec: int = 300):
        self.refresh_sec = max(5, int(refresh_sec))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.last_run_ts: datetime | None = None
        self.last_error: str | None = None
        self.last_sent_events: list[dict] = []
        self.stats = {
            "monitored": 0,
            "rescored": 0,
            "interventions": 0,
            "errors": 0,
        }

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.0):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)

    def set_refresh_interval(self, sec: int):
        self.refresh_sec = max(5, int(sec))

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                self.last_error = str(e)
                self.stats["errors"] += 1
            self._stop.wait(self.refresh_sec)

    def _tick(self):
        # Light tick: refresh stats only. Full per-row orchestration is opt-in
        # (ENABLE_HEAVY_BACKEND=1) because it freezes the web worker on cloud.
        df = load_patient_data(force_reload=False)
        self.stats["monitored"] = int(len(df))
        self.stats["rescored"] = int(len(df))
        self.last_run_ts = datetime.now()

        if not ENABLE_HEAVY_BACKEND or not send_auto_notifications or df is None or df.empty:
            return

        clean_rows = []
        for _, r in df.iterrows():
            norm = validate_and_normalize_row(r)
            clean_rows.append(norm["clean"])
        clean_df = pd.DataFrame(clean_rows) if clean_rows else pd.DataFrame()
        self.stats["rescored"] = len(clean_df)

        today = pd.Timestamp.now().normalize()
        notif_ts = pd.to_datetime(clean_df.get("NotificationSentOn"), errors="coerce") if "NotificationSentOn" in clean_df.columns else pd.Series(dtype="datetime64[ns]")
        today_sent_before = int((notif_ts.dt.normalize() == today).sum()) if notif_ts is not None and len(clean_df) else 0

        sent_ids: list[str] = []
        sent_details: dict[str, dict] = {}
        sent_events: list[dict] = []
        # Cap work per tick so one cycle cannot take down the host
        max_rows = int(os.getenv("HEAVY_BACKEND_MAX_ROWS", "50"))
        for _, row in clean_df.head(max_rows).iterrows():
            row_dict = dict(row)
            last_sent_ts = row_dict.get("NotificationSentOn")
            policy_context = {
                "today_sent": today_sent_before + len(sent_ids),
                "cap": int(os.getenv("OUTREACH_MAX_PER_DAY", "100")),
                "cooldown_days": int(os.getenv("OUTREACH_COOLDOWN_DAYS", "2")),
                "last_sent_ts": last_sent_ts,
            }
            orchestration = orchestrate_refill_and_notify(row_dict, send=send_auto_notifications, policy_context=policy_context)
            result = orchestration if isinstance(orchestration, dict) else orchestration[0]
            status = (result or {}).get("status", "Planned")
            if status in {"Sent", "Queued"}:
                mid = str(row.get("Member ID", "")).strip()
                if mid:
                    sent_ids.append(mid)
                    channel = ((result or {}).get("route") or {}).get("channel")
                    sms_meta = (result or {}).get("sms") or {}
                    msg_id = sms_meta.get("sid") or (result or {}).get("pushover") or ""
                    sent_details[mid] = {
                        "NotificationStatus": status,
                        "NotificationChannel": channel or "",
                        "NotificationMessageId": msg_id or "",
                    }
                    first, last = name_parts(row.get("Patient Name"))
                    sent_events.append({
                        "member_id": mid,
                        "first": first,
                        "last": last,
                        "ts": datetime.now().isoformat(),
                        "channel": channel or "",
                        "message_id": msg_id or "",
                        "status": status,
                    })
        if sent_ids:
            try:
                update_notification_sent_on(sent_ids, pd.Timestamp.now(), details_by_member_id=sent_details)
            except Exception as e:
                self.last_error = f"Persist NotificationSentOn failed: {e}"
        self.stats["interventions"] = len(sent_ids)
        self.last_run_ts = datetime.now()
        if sent_events:
            with self._lock:
                self.last_sent_events.extend(sent_events)
                socketio.emit('notification_sent', sent_events[-1])

# Initialize backend runner (will be created on first request if needed)
def get_backend_runner():
    global backend_runner, live_on, refresh_interval
    if backend_runner is None:
        # On cloud use a longer interval so background work never storms the worker
        sec = max(refresh_interval, 120) if ON_CLOUD else refresh_interval
        backend_runner = BackendRunner(refresh_sec=sec)
        if live_on:
            backend_runner.start()
    return backend_runner


def _preload_patient_data():
    """Warm the data cache after boot so the first user request stays fast."""
    try:
        df = load_patient_data(force_reload=False)
        print(f"[startup] Preloaded {len(df)} patient rows", flush=True)
    except Exception as e:
        print(f"[startup] Preload skipped: {e}", flush=True)


# Initialize on module load — light runner only (stats), never block HTTP with orchestration
backend_runner = BackendRunner(refresh_sec=max(AUTO_REFRESH_SECONDS, 120 if ON_CLOUD else AUTO_REFRESH_SECONDS))
if live_on:
    backend_runner.start()

# Defer heavy data load so gunicorn can bind PORT quickly (Render health checks)
if ON_CLOUD:
    threading.Thread(target=_preload_patient_data, daemon=True).start()
else:
    try:
        _preload_patient_data()
    except Exception:
        pass

# API Routes
@app.route('/favicon.ico', methods=['GET'])
def favicon():
    """Handle favicon requests to prevent proxy errors"""
    from flask import Response
    return Response(status=204)  # No content

def _care_teams_path():
    """Path to care teams JSON file (Data/care_teams.json in app dir)."""
    app_dir = get_app_dir()
    data_dir = app_dir / "Data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "care_teams.json"


def _load_care_teams():
    """Load care teams from JSON file. Returns list of team dicts."""
    path = _care_teams_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("teams", [])
    except (json.JSONDecodeError, IOError):
        return []


def _save_care_teams(teams):
    """Save care teams to JSON file."""
    path = _care_teams_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"teams": teams}, f, indent=2)


@app.route('/api/health', methods=['GET'])
def health():
    # Must stay trivial — Render/Cloudflare probe this. Never touch Excel/pandas here.
    return jsonify({"status": "ok", "cloud": ON_CLOUD})


@app.route('/api/data-source', methods=['GET'])
def get_data_source():
    """Tell the UI where the app looks for the Excel file and whether it exists."""
    path = EXCEL_PATH
    csv_path = os.path.splitext(path)[0] + ".csv"
    exists = os.path.isfile(path) or os.path.isfile(csv_path)
    return jsonify({
        "path": path,
        "exists": exists,
        "csv_exists": os.path.isfile(csv_path),
        "message": "Data file found." if exists else "Put patients.xlsx in the Data folder next to the app (or set EXCEL_PATH in .env)."
    })


@app.route('/api/care-teams', methods=['GET', 'POST'])
def care_teams_list_or_create():
    """GET: List all care teams with optional query params name, status. POST: Create a care team."""
    if request.method == 'POST':
        # Create Care Team
        body = request.get_json() or {}
        name = (body.get("name") or "").strip()
        members = body.get("members")
        status = (body.get("status") or "active").strip().lower() or "active"
        if not name:
            return jsonify({"error": "name is required"}), 400
        if members is None:
            members = []
        if not isinstance(members, list):
            return jsonify({"error": "members must be a list"}), 400
        teams = _load_care_teams()
        team_id = uuid.uuid4().hex
        team = {
            "id": team_id,
            "name": name,
            "members": members,
            "status": status,
        }
        teams.append(team)
        _save_care_teams(teams)
        return jsonify(team), 201

    # GET: Get all care teams (optional filters: name, status)
    name_filter = (request.args.get("name") or "").strip().lower()
    status_filter = (request.args.get("status") or "").strip().lower()
    teams = _load_care_teams()
    if name_filter:
        teams = [t for t in teams if name_filter in (t.get("name") or "").lower()]
    if status_filter:
        teams = [t for t in teams if (t.get("status") or "").lower() == status_filter]
    return jsonify({"teams": teams})


@app.route('/api/care-teams/<team_id>', methods=['GET'])
def care_team_get(team_id):
    """Get a care team by id."""
    teams = _load_care_teams()
    for t in teams:
        if t.get("id") == team_id:
            return jsonify(t)
    return jsonify({"error": "Care team not found"}), 404


def _default_dashboard_response(data_error: str = None):
    """Return a valid dashboard payload with zero KPIs so the UI never shows blank. Used when Excel is missing, empty, or load fails."""
    runner = get_backend_runner()
    last_sync_ts_runner = (runner.last_run_ts if runner is not None else None) or last_sync_ts
    payload = {
        "kpis": {
            "interventions_30d": 0,
            "notified_unique": 0,
            "responded_unique": 0,
            "notified_today": 0,
            "proj_savings_month": 0.0,
            "high_risk_now": 0,
            "avg_adherence_now": 0.0,
            "hr_delta": 0,
            "adh_delta": 0.0,
            "adh_delta_weekly": None,
            "adh_delta_monthly": None,
            "high_risk_last_week": None,
            "avg_adherence_last_month": None,
            "interventions_7d": 0,
            "low_count": 0,
            "med_count": 0,
            "high_count": 0,
            "notified_push": 0,
            "notified_whatsapp": 0,
            "notified_sms": 0,
            "notified_email": 0,
            "high_risk_refill_over": 0,
            "refill_over_due_count": 0,
            "appreciation_sent_count": 0,
        },
        "system": {
            "status": "Degraded" if data_error else "No data",
            "live_on": live_on,
            "send_auto_notifications": send_auto_notifications,
            "refresh_interval": refresh_interval,
            "last_sync": fmt_minutes_ago(last_sync_ts_runner),
            "last_sync_date": (last_sync_ts_runner or datetime.now()).strftime("%d %b %Y"),
            "agents_running": 5 if (getattr(runner, "_thread", None) and runner._thread.is_alive()) else 0,
        },
        "trends": {
            "date_col": None,
            "high_risk_last_week": None,
            "avg_adherence_last_month": None,
        },
    }
    if data_error:
        payload["data_error"] = data_error
    payload["data_source"] = {"path": EXCEL_PATH, "exists": os.path.isfile(EXCEL_PATH)}
    return payload


@app.route('/api/dashboard-data', methods=['GET'])
def get_dashboard_data():
    """Get all dashboard data. Always returns 200 with valid structure (zeros when no data) so dashboard is never blank."""
    global last_sync_ts, previous_columns_hash, previous_data_hash, processed_high_risk_patients, high_risk_notifications
    import traceback

    now_mono = time.time()
    cached = _dashboard_cache.get("payload")
    if cached is not None and (now_mono - float(_dashboard_cache.get("ts") or 0)) < _DASHBOARD_CACHE_TTL:
        return jsonify(cached)

    try:
        # Never force-reload on the HTTP path — mtime cache in utils handles freshness.
        # force_reload=True previously re-read 2300 rows on every poll and caused 520s.
        df = load_patient_data(force_reload=False)
    except Exception as e:
        traceback.print_exc()
        return jsonify(_default_dashboard_response(data_error=str(e)))

    last_sync_ts = datetime.now()

    # Empty data: return valid structure so charts and KPIs render with zeros
    if df.empty:
        return jsonify(_default_dashboard_response(data_error="No patient data (Excel missing or empty). Add Data/patients.xlsx or set EXCEL_PATH in .env"))

    # Normalize columns
    adherence_col = "Adherence Percentage" if "Adherence Percentage" in df.columns else "Adeherence Percentage"
    member_id_col = "Member ID" if "Member ID" in df.columns else "Member_ID"
    name_col = "Patient Name" if "Patient Name" in df.columns else "Patient_Name"
    if adherence_col not in df.columns:
        df[adherence_col] = 0
    df[adherence_col] = pd.to_numeric(df[adherence_col], errors="coerce").fillna(0)

    # When EventDate exists, keep full dataset for trends and use latest row per patient for KPIs
    df_all = df.copy()
    if "EventDate" in df.columns and df["EventDate"].notna().any():
        df["EventDate"] = pd.to_datetime(df["EventDate"], errors="coerce")
        df = df.sort_values("EventDate", ascending=False).drop_duplicates(subset=[member_id_col], keep="first").reset_index(drop=True)

    # Track data hash only. Do NOT run agent orchestration on this HTTP path —
    # that blocks for minutes on ~2300 rows and breaks browsers (HTTP/2 protocol errors).
    # Background BackendRunner handles live notifications separately.
    current_columns = sorted(df.columns.tolist())
    data_hash = hashlib.md5(
        f"{str(current_columns)}|{len(df)}|{df[adherence_col].sum() if adherence_col in df.columns else 0}".encode()
    ).hexdigest()
    previous_columns_hash = current_columns
    previous_data_hash = data_hash

    # Calculate KPIs: High-risk = low adherence AND refill days <= 7
    dur = pd.to_numeric(df.get("days_until_refill"), errors="coerce")
    refill_soon_or_over = dur.notna() & (dur <= 7)
    refill_overdue_mask = dur.notna() & (dur <= 0)
    high_risk_now = int(((df[adherence_col] < THRESHOLD_LOW) & refill_soon_or_over).sum())
    # Routed-to-clinic style escalation: low adherence + refill overdue/soon
    high_risk_refill_over = int(((df[adherence_col] < THRESHOLD_LOW) & refill_overdue_mask).sum())
    if high_risk_refill_over == 0:
        high_risk_refill_over = int(((df[adherence_col] < THRESHOLD_LOW) & refill_soon_or_over).sum())
    refill_over_due_count = int(refill_overdue_mask.sum())
    avg_adherence_now = float(df[adherence_col].mean()) if len(df) else 0.0
    appreciation_sent_count = 0
    if "AppreciationSentOn" in df.columns and member_id_col in df.columns:
        appreciation_sent_count = int(
            df[pd.to_datetime(df["AppreciationSentOn"], errors="coerce").notna()][member_id_col]
            .astype(str)
            .nunique()
        )
    
    notified_today = 0
    if "NotificationSentOn" in df.columns and member_id_col in df.columns:
        df["NotificationSentOn"] = pd.to_datetime(df["NotificationSentOn"], errors="coerce")
        today = pd.Timestamp.now().normalize()
        notified_today = int(df[df["NotificationSentOn"].dt.normalize() == today][member_id_col].astype(str).nunique())
    
    notified_unique = int(df[df["NotificationSentOn"].notna()][member_id_col].astype(str).nunique()) if "NotificationSentOn" in df.columns else 0
    responded_unique = 0
    if "NotificationStatus" in df.columns and member_id_col in df.columns:
        ack_mask = df["NotificationStatus"].astype(str).str.strip().str.lower() == "acknowledged"
        responded_unique = int(df.loc[ack_mask, member_id_col].astype(str).nunique())
    
    # Trends: use full history (df_all) so previous months are included in trend charts
    date_col = None
    trend_df = df_all
    for c in ["EventDate", "ClaimDate", "NotificationSentOn"]:
        if c in trend_df.columns:
            date_col = c
            break

    high_risk_last_week = None
    avg_adherence_last_month = None
    interventions_7d = 0
    interventions_30d = 0
    adh_delta_weekly = None
    adh_delta_monthly = None  # same-period: this month (1st–today) vs last month (1st–same day)

    if date_col:
        trend_df = trend_df.copy()
        trend_df[date_col] = pd.to_datetime(trend_df[date_col], errors="coerce")
        if trend_df[date_col].notna().any():
            now = pd.Timestamp.now().normalize()
            wk_start = now - pd.Timedelta(days=7)
            prev_wk_start = now - pd.Timedelta(days=14)
            prev = trend_df[(trend_df[date_col] >= prev_wk_start) & (trend_df[date_col] < wk_start)]
            if len(prev) > 0:
                prev_dur = pd.to_numeric(prev.get("days_until_refill"), errors="coerce")
                prev_refill_soon = prev_dur.notna() & (prev_dur <= 7)
                high_risk_last_week = int(((prev[adherence_col] < THRESHOLD_LOW) & prev_refill_soon).sum())

            # Weekly comparison: last 7 days vs previous 7 days
            this_week = trend_df[(trend_df[date_col] >= wk_start) & (trend_df[date_col] <= now)]
            prev_week = trend_df[(trend_df[date_col] >= prev_wk_start) & (trend_df[date_col] < wk_start)]
            if len(this_week) > 0 and len(prev_week) > 0:
                avg_this_week = float(this_week[adherence_col].mean())
                avg_prev_week = float(prev_week[adherence_col].mean())
                adh_delta_weekly = round(avg_this_week - avg_prev_week, 1)

            # Monthly same-period: this month (1st–today) vs last month (1st–same day), e.g. Feb 1–15 vs Jan 1–15
            start_this_month = now.replace(day=1)
            start_last_month = (start_this_month - pd.offsets.MonthBegin(1))  # first day of last month
            last_month_end_day = (start_last_month + pd.offsets.MonthEnd(0)).day  # last day of last month
            same_day_last_month = min(now.day, last_month_end_day)
            end_last_month_same = start_last_month.replace(day=same_day_last_month)

            this_month_period = trend_df[(trend_df[date_col] >= start_this_month) & (trend_df[date_col] <= now)]
            last_month_same_period = trend_df[(trend_df[date_col] >= start_last_month) & (trend_df[date_col] <= end_last_month_same)]
            if len(this_month_period) > 0 and len(last_month_same_period) > 0:
                avg_this_month = float(this_month_period[adherence_col].mean())
                avg_last_month_same = float(last_month_same_period[adherence_col].mean())
                adh_delta_monthly = round(avg_this_month - avg_last_month_same, 1)
            # Fallback: original 30-day vs previous 30-day for avg_adherence_last_month / adh_delta
            m_start = now - pd.Timedelta(days=30)
            prev_m_start = now - pd.Timedelta(days=60)
            m_prev = trend_df[(trend_df[date_col] >= prev_m_start) & (trend_df[date_col] < m_start)]
            if len(m_prev) > 0:
                avg_adherence_last_month = float(m_prev[adherence_col].mean())

            if "NotificationSentOn" in trend_df.columns:
                notif_ts = pd.to_datetime(trend_df["NotificationSentOn"], errors="coerce")
                interventions_7d = int(trend_df.loc[notif_ts >= wk_start, member_id_col].astype(str).nunique())
                interventions_30d = int(trend_df.loc[notif_ts >= m_start, member_id_col].astype(str).nunique())

    hr_delta = (high_risk_now - high_risk_last_week) if high_risk_last_week is not None else 0
    adh_delta = (avg_adherence_now - avg_adherence_last_month) if avg_adherence_last_month is not None else 0
    if adh_delta_monthly is None:
        adh_delta_monthly = adh_delta  # fallback to legacy adh_delta when same-period not available
    
    # Model-based projections
    SAVINGS_PER_INTERVENTION = float(os.getenv("SAVINGS_PER_INTERVENTION", "1000"))
    MODEL_CI_WIDTH = float(os.getenv("MODEL_CI_WIDTH", "0.20"))
    proj_savings_month = max(0.0, interventions_30d * SAVINGS_PER_INTERVENTION)
    
    # Risk distribution
    low_count = int((df[adherence_col] < THRESHOLD_LOW).sum())
    med_count = int(((df[adherence_col] >= THRESHOLD_LOW) & (df[adherence_col] < THRESHOLD_MED)).sum())
    high_count = int((df[adherence_col] >= THRESHOLD_MED).sum())
    
    # Notification counts by channel (rows with NotificationSentOn, grouped by channel)
    notified_push = 0
    notified_whatsapp = 0
    notified_sms = 0
    notified_email = 0
    if "NotificationChannel" in df.columns and "NotificationSentOn" in df.columns:
        sent = df[df["NotificationSentOn"].notna()]
        if len(sent) > 0:
            ch = sent["NotificationChannel"].astype(str).str.strip().str.lower()
            notified_push = int((ch.isin(["pushover", "push", "notification", "app push", "apppush"])).sum())
            notified_whatsapp = int((ch == "whatsapp").sum())
            notified_sms = int((ch == "sms").sum())
            notified_email = int((ch == "email").sum())
    
    # System status
    runner = get_backend_runner()
    last_sync_ts_runner = (runner.last_run_ts if runner is not None else None) or last_sync_ts
    age_sec = (datetime.now() - last_sync_ts_runner).total_seconds() if last_sync_ts_runner else 0
    
    if live_on:
        agents_running = 5 if (getattr(runner, "_thread", None) and runner._thread.is_alive()) else 0
        system_status = "Healthy" if age_sec <= (2 * refresh_interval) else "Degraded"
    else:
        agents_running = 0
        system_status = "Paused"
    
    payload = {
        "kpis": {
            "interventions_30d": interventions_30d,
            "notified_unique": notified_unique,
            "responded_unique": responded_unique,
            "notified_today": notified_today,
            "proj_savings_month": proj_savings_month,
            "high_risk_now": high_risk_now,
            "avg_adherence_now": avg_adherence_now,
            "hr_delta": hr_delta,
            "adh_delta": adh_delta,
            "adh_delta_weekly": adh_delta_weekly,
            "adh_delta_monthly": adh_delta_monthly,
            "high_risk_last_week": high_risk_last_week,
            "avg_adherence_last_month": avg_adherence_last_month,
            "interventions_7d": interventions_7d,
            "low_count": low_count,
            "med_count": med_count,
            "high_count": high_count,
            "notified_push": notified_push,
            "notified_whatsapp": notified_whatsapp,
            "notified_sms": notified_sms,
            "notified_email": notified_email,
            "high_risk_refill_over": high_risk_refill_over,
            "refill_over_due_count": refill_over_due_count,
            "appreciation_sent_count": appreciation_sent_count,
        },
        "system": {
            "status": system_status,
            "live_on": live_on,
            "send_auto_notifications": send_auto_notifications,
            "refresh_interval": refresh_interval,
            "last_sync": fmt_minutes_ago(last_sync_ts_runner),
            "last_sync_date": (last_sync_ts_runner or last_sync_ts).strftime("%d %b %Y"),
            "agents_running": agents_running,
        },
        "trends": {
            "date_col": date_col,
            "high_risk_last_week": high_risk_last_week,
            "avg_adherence_last_month": avg_adherence_last_month,
        },
        "data_source": {
            "path": EXCEL_PATH,
            "exists": os.path.isfile(EXCEL_PATH) or os.path.isfile(os.path.splitext(EXCEL_PATH)[0] + ".csv"),
        },
    }
    _dashboard_cache["payload"] = payload
    _dashboard_cache["ts"] = time.time()
    return jsonify(payload)

@app.errorhandler(500)
def handle_500(e):
    """Return JSON error for 500 so frontend can show the real message."""
    import traceback
    traceback.print_exc()
    msg = str(e) if e else "Internal server error"
    return jsonify({"error": msg}), 500

def _safe_trend_chart_response():
    """Build trend chart JSON. Returns (data_list, correlation). Never raises; on any error returns ([], 0.0)."""
    try:
        df = load_patient_data()
        if df is None or df.empty:
            return [], 0.0
        adherence_col = "Adherence Percentage" if "Adherence Percentage" in df.columns else "Adeherence Percentage"
        member_id_col = "Member ID" if "Member ID" in df.columns else "Member_ID"
        date_col = None
        for c in ["EventDate", "ClaimDate", "NotificationSentOn"]:
            if c in df.columns:
                date_col = c
                break
        if not date_col:
            return [], 0.0
        trend_df = df.copy()
        trend_df[date_col] = pd.to_datetime(trend_df[date_col], errors="coerce")
        trend_df = trend_df.dropna(subset=[date_col])
        if trend_df.empty:
            return [], 0.0
        week_values = trend_df[date_col].dt.to_period('W').apply(lambda r: r.start_time)
        trend_df = trend_df.copy()
        trend_df['week'] = week_values
        def _high_risk_count(g):
            d = pd.to_numeric(g.get("days_until_refill"), errors="coerce")
            refill_soon = d.notna() & (d <= 7)
            return ((g[adherence_col] < THRESHOLD_LOW) & refill_soon).sum()
        risk_trend = trend_df.groupby('week').apply(_high_risk_count).rename('High-Risk Patients')
        if "NotificationSentOn" in trend_df.columns:
            ai_trend = trend_df.groupby('week').apply(lambda g: g[member_id_col][g['NotificationSentOn'].notna()].nunique()).rename('AI Interventions')
        else:
            ai_trend = trend_df.groupby('week').apply(lambda g: 0).rename('AI Interventions')
        if "NotificationStatus" in trend_df.columns:
            responded_trend = trend_df.groupby('week').apply(
                lambda g: g[member_id_col][g["NotificationStatus"].astype(str).str.strip().str.lower() == "acknowledged"].nunique()
            ).rename('Patient Responded')
        else:
            responded_trend = trend_df.groupby('week').apply(lambda g: 0).rename('Patient Responded')
        trend_data = pd.concat([risk_trend, ai_trend, responded_trend], axis=1).fillna(0)
        if "week" in trend_data.columns:
            trend_data = trend_data.drop(columns=["week"])
        trend_data = trend_data.reset_index()
        trend_data["week"] = trend_data["week"].astype(str)
        correlation = float(trend_data['High-Risk Patients'].corr(trend_data['AI Interventions'])) if len(trend_data) > 1 else 0.0
        return trend_data.to_dict('records'), correlation
    except Exception:
        return [], 0.0


@app.route('/api/trend-chart', methods=['GET'])
def get_trend_chart():
    """Get trend chart data. Always returns 200 with valid structure (empty when no date column). Never returns 400."""
    data, correlation = _safe_trend_chart_response()
    return jsonify({"data": data, "correlation": correlation})

@app.route('/api/system-status', methods=['GET'])
def get_system_status():
    """Get system status"""
    global live_on, refresh_interval
    runner = get_backend_runner()
    last_sync_ts_runner = (runner.last_run_ts if runner is not None else None) or last_sync_ts
    age_sec = (datetime.now() - last_sync_ts_runner).total_seconds() if last_sync_ts_runner else 0
    
    if live_on:
        agents_running = 5 if (getattr(runner, "_thread", None) and runner._thread.is_alive()) else 0
        system_status = "Healthy" if age_sec <= (2 * refresh_interval) else "Degraded"
    else:
        agents_running = 0
        system_status = "Paused"
    
    return jsonify({
        "status": system_status,
        "live_on": live_on,
        "send_auto_notifications": send_auto_notifications,
        "refresh_interval": refresh_interval,
        "last_sync": fmt_minutes_ago(last_sync_ts_runner),
        "agents_running": agents_running,
        "stats": runner.stats if runner else {}
    })

@app.route('/api/system-control', methods=['POST'])
def system_control():
    """Control system (toggle live monitoring, send auto notifications, set refresh interval)"""
    global live_on, refresh_interval, send_auto_notifications
    
    data = request.get_json()
    if 'live_on' in data:
        live_on = bool(data['live_on'])
        runner = get_backend_runner()
        if live_on:
            runner.start()
        else:
            runner.stop()
    if 'send_auto_notifications' in data:
        send_auto_notifications = bool(data['send_auto_notifications'])
    
    if 'refresh_interval' in data:
        refresh_interval = int(data['refresh_interval'])
        runner = get_backend_runner()
        runner.set_refresh_interval(refresh_interval)
    
    return jsonify({"success": True})

@app.route('/api/patient-query', methods=['POST'])
def patient_query():
    """Query patient data from database/excel"""
    try:
        data = request.get_json()
        query_type = data.get('query_type', '').lower()
        
        # Load patient data from database/excel
        df = load_patient_data(force_reload=False)
        
        if df.empty:
            return jsonify({
                "total_patients": 0,
                "message": "No patient data available"
            })
        
        # Get total patient count
        total_patients = len(df)
        
        # Get member ID column
        member_id_col = "Member ID" if "Member ID" in df.columns else "Member_ID"
        
        # Get unique patient count (by Member ID)
        unique_patients = df[member_id_col].nunique() if member_id_col in df.columns else total_patients
        
        # Get adherence column
        adherence_col = "Adherence Percentage" if "Adherence Percentage" in df.columns else "Adeherence Percentage"
        
        # Calculate statistics
        if adherence_col in df.columns:
            df[adherence_col] = pd.to_numeric(df[adherence_col], errors="coerce")
            avg_adherence = float(df[adherence_col].mean()) if not df[adherence_col].isna().all() else 0
            low_adherence = int((df[adherence_col] < THRESHOLD_LOW).sum())
            med_adherence = int(((df[adherence_col] >= THRESHOLD_LOW) & (df[adherence_col] < THRESHOLD_MED)).sum())
            high_adherence = int((df[adherence_col] >= THRESHOLD_MED).sum())
        else:
            avg_adherence = 0
            low_adherence = 0
            med_adherence = 0
            high_adherence = 0
        
        # Get columns available
        columns = df.columns.tolist()
        
        response_data = {
            "total_patients": total_patients,
            "unique_patients": unique_patients,
            "avg_adherence": round(avg_adherence, 1),
            "low_adherence_count": low_adherence,
            "med_adherence_count": med_adherence,
            "high_adherence_count": high_adherence,
            "columns": columns,
            "has_adherence_data": adherence_col in df.columns
        }
        
        # If querying specific patient
        if query_type == 'patient' and 'member_id' in data:
            member_id = str(data['member_id']).strip()
            patient_df = df[df[member_id_col].astype(str).str.strip() == member_id] if member_id_col in df.columns else pd.DataFrame()
            
            if not patient_df.empty:
                patient_row = patient_df.iloc[0].to_dict()
                response_data["patient"] = {k: str(v) if pd.notna(v) else "" for k, v in patient_row.items()}
            else:
                response_data["patient"] = None
                response_data["message"] = f"Patient with ID {member_id} not found"
        
        # If querying all patients (summary)
        if query_type == 'all':
            # Already included in response_data above
            pass
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# PII columns to mask when mask_pii=True (only these are hidden in data snapshot)
PII_COLUMNS = [
    "Patient Name", "Patient_Name",
    "Member ID", "Member_ID",
    "Patient Contact", "Patient EmailID",
]

def _apply_snapshot_filter(df, filter_type, filter_by, adherence_col, risk_label_col):
    """Apply user-selected filter to dataframe. Returns filtered subset and counts dict."""
    valid_filter = filter_type in ("low", "medium", "high") or filter_type == "all"
    if not valid_filter:
        filter_type = "all"

    if filter_by == "risk" and risk_label_col and risk_label_col in df.columns:
        # Filter by Risk Label column (Low/Medium/High)
        r = df[risk_label_col].astype(str).str.strip().str.lower()
        if filter_type == "all":
            subset = df
        elif filter_type == "low":
            subset = df[r == "low"]
        elif filter_type == "medium":
            subset = df[r == "medium"]
        else:
            subset = df[r == "high"]
        low_count = int((r == "low").sum())
        med_count = int((r == "medium").sum())
        high_count = int((r == "high").sum())
    else:
        # Filter by adherence (default)
        if filter_type == "low":
            subset = df[df[adherence_col] < THRESHOLD_LOW]
        elif filter_type == "medium":
            subset = df[(df[adherence_col] >= THRESHOLD_LOW) & (df[adherence_col] < THRESHOLD_MED)]
        elif filter_type == "high":
            subset = df[df[adherence_col] >= THRESHOLD_MED]
        else:
            subset = df
        low_count = int((df[adherence_col] < THRESHOLD_LOW).sum())
        med_count = int(((df[adherence_col] >= THRESHOLD_LOW) & (df[adherence_col] < THRESHOLD_MED)).sum())
        high_count = int((df[adherence_col] >= THRESHOLD_MED).sum())

    counts = {"all": len(df), "low": low_count, "medium": med_count, "high": high_count}
    return subset, counts, filter_type


@app.route('/api/patient-snapshot', methods=['GET'])
def get_patient_snapshot():
    """Return patient rows from Excel filtered by user selection (adherence or risk, all/low/medium/high), with optional PII masking."""
    try:
        df = load_patient_data(force_reload=False)
        if df.empty:
            return jsonify({"rows": [], "columns": [], "counts": {"all": 0, "low": 0, "medium": 0, "high": 0}, "filter": "all", "filter_by": "adherence"})

        adherence_col = "Adherence Percentage" if "Adherence Percentage" in df.columns else "Adeherence Percentage"
        if adherence_col not in df.columns and "PDC Percentage" in df.columns:
            adherence_col = "PDC Percentage"
        if adherence_col not in df.columns:
            df[adherence_col] = 0
        df[adherence_col] = pd.to_numeric(df[adherence_col], errors="coerce").fillna(0)

        risk_label_col = "RiskLabel" if "RiskLabel" in df.columns else ("Risk_Label" if "Risk_Label" in df.columns else None)

        filter_type = (request.args.get("filter") or "all").strip().lower()
        filter_by = (request.args.get("filter_by") or "adherence").strip().lower()
        if filter_by not in ("adherence", "risk"):
            filter_by = "adherence"
        mask_pii = request.args.get("mask_pii", "true").strip().lower() in ("true", "1", "yes")

        subset, counts, filter_type = _apply_snapshot_filter(df, filter_type, filter_by, adherence_col, risk_label_col)

        # Hide backend/technical columns from Data Snapshot grid
        HIDDEN_SNAPSHOT_COLUMNS = {
            "NotificationSentOn",
            "NotificationSentAt",
            "NotificationStatus",
            "NotificationChannel",
            "NotificationMessageId",
            "AppreciationSentOn",
            "LastUpdated",
        }
        subset = subset[[c for c in subset.columns if c not in HIDDEN_SNAPSHOT_COLUMNS]]

        columns = [str(c) for c in subset.columns]
        rows = []
        for _, row in subset.iterrows():
            rec = {}
            for col in columns:
                val = row.get(col)
                if pd.isna(val):
                    rec[col] = ""
                elif isinstance(val, (pd.Timestamp, datetime)):
                    rec[col] = val.strftime("%Y-%m-%d %H:%M") if hasattr(val, "strftime") else str(val)
                else:
                    rec[col] = str(val).strip() if isinstance(val, str) else val
                if mask_pii and col in PII_COLUMNS and rec[col]:
                    rec[col] = "••••••"
            rows.append(rec)

        return jsonify({
            "rows": rows,
            "columns": columns,
            "counts": counts,
            "mask_pii": mask_pii,
            "filter": filter_type,
            "filter_by": filter_by,
            "has_risk_column": risk_label_col is not None,
        })
    except Exception as e:
        return jsonify({"error": str(e), "rows": [], "columns": [], "counts": {"all": 0, "low": 0, "medium": 0, "high": 0}}), 500


def _resolve_patient_for_notification(data):
    """Resolve patient row from member_id or (row_index + filter + filter_by). Returns (member_id, patient_row_dict) or (None, None) with error."""
    data = data or {}
    member_id = (data.get("member_id") or "").strip()
    row_index = data.get("row_index")
    filter_type = (data.get("filter") or "all").strip().lower()
    filter_by = (data.get("filter_by") or "adherence").strip().lower()
    if filter_by not in ("adherence", "risk"):
        filter_by = "adherence"

    df = load_patient_data(force_reload=False)
    if df.empty:
        return None, None, "No patient data available"

    adherence_col = "Adherence Percentage" if "Adherence Percentage" in df.columns else "Adeherence Percentage"
    if adherence_col not in df.columns and "PDC Percentage" in df.columns:
        adherence_col = "PDC Percentage"
    if adherence_col not in df.columns:
        df[adherence_col] = 0
    df[adherence_col] = pd.to_numeric(df[adherence_col], errors="coerce").fillna(0)
    risk_label_col = "RiskLabel" if "RiskLabel" in df.columns else ("Risk_Label" if "Risk_Label" in df.columns else None)
    member_id_col = "Member ID" if "Member ID" in df.columns else "Member_ID"

    if not member_id and row_index is not None and row_index >= 0:
        subset, _, filter_type = _apply_snapshot_filter(df, filter_type, filter_by, adherence_col, risk_label_col)
        subset = subset.reset_index(drop=True)
        if row_index >= len(subset):
            return None, None, "Invalid row index for current filter"
        row = subset.iloc[row_index]
        member_id = str(row.get(member_id_col, "")).strip()
        patient_row = row.to_dict()
    elif member_id:
        patient_df = df[df[member_id_col].astype(str).str.strip() == member_id]
        if patient_df.empty:
            return None, None, f"Patient with Member ID {member_id} not found"
        patient_row = patient_df.iloc[0].to_dict()
    else:
        return None, None, "Provide member_id or (row_index and filter)"

    if not member_id:
        return None, None, "Could not resolve patient identifier"
    return member_id, patient_row, None


def _get_city_from_row(row):
    """Get city from row trying multiple column names; handle pandas nan and empty."""
    for key in ("City", "Patient City", "city", "CITY", "PatientCity"):
        val = row.get(key)
        if val is not None and str(val).strip() and str(val).lower() not in ("nan", "none", "n/a"):
            return str(val).strip()
    return None


def _build_preview_message_inline(clean_row):
    """Build adherence + pharmacy table message here in app_flask. No agent/AI – guarantees Data Snapshot preview always shows pharmacy table."""
    from pharmacy import get_pharmacy_for_city, format_pharmacy_table
    name = (clean_row.get("Patient Name") or clean_row.get("Patient_Name") or "Patient").strip()
    medication = (clean_row.get("Medication Name") or clean_row.get("Medication_Name") or "your medication").strip()
    adh = clean_row.get("Adherence Percentage") or clean_row.get("Adeherence Percentage") or clean_row.get("PDC Percentage") or 0
    try:
        adherence = float(adh)
    except (TypeError, ValueError):
        adherence = 0.0
    city = _get_city_from_row(clean_row)
    pharmacy = get_pharmacy_for_city(city)
    pharmacy_table = format_pharmacy_table(pharmacy)
    return (
        f"Hi {name}, this is a medication adherence reminder. "
        f"You are on {medication}. Your current adherence is {adherence:.0f} percent. "
        f"Please refill your medication if needed.\n\n{pharmacy_table}\n\nThank you."
    )


@app.route('/api/patient-lists', methods=['GET'])
def get_patient_lists():
    """Return Member ID + reason lists for routed-to-clinic / refill-overdue views (no other PII)."""
    try:
        list_type = (request.args.get("type") or "").strip().lower()
        df = load_patient_data(force_reload=False)
        empty = {"routed_to_clinic": [], "refill_overdue": []}
        if df is None or df.empty:
            return jsonify(empty)

        adherence_col = "Adherence Percentage" if "Adherence Percentage" in df.columns else "Adeherence Percentage"
        if adherence_col not in df.columns:
            df[adherence_col] = 0
        df[adherence_col] = pd.to_numeric(df[adherence_col], errors="coerce").fillna(0)
        member_id_col = "Member ID" if "Member ID" in df.columns else "Member_ID"
        dur = pd.to_numeric(df.get("days_until_refill"), errors="coerce")
        refill_overdue_mask = dur.notna() & (dur <= 0)
        refill_soon_mask = dur.notna() & (dur <= 7)
        routed_mask = (df[adherence_col] < THRESHOLD_LOW) & refill_soon_mask

        def _rows(mask, reason, insight):
            out = []
            if member_id_col not in df.columns:
                return out
            subset = df.loc[mask, [member_id_col]].drop_duplicates()
            for _, row in subset.iterrows():
                mid = str(row.get(member_id_col, "")).strip()
                if not mid:
                    continue
                out.append({
                    "member_id": mid,
                    "reason": reason,
                    "ai_insight": insight,
                })
            return out

        routed = _rows(
            routed_mask,
            "Low adherence with refill due soon — escalate to clinic",
            "AI flagged escalation candidate based on adherence and refill timing",
        )
        overdue = _rows(
            refill_overdue_mask,
            "Refill overdue — patient needs refill now",
            "Days until refill is zero or negative",
        )
        if list_type == "routed_to_clinic":
            return jsonify({"routed_to_clinic": routed, "refill_overdue": []})
        if list_type == "refill_overdue":
            return jsonify({"routed_to_clinic": [], "refill_overdue": overdue})
        return jsonify({"routed_to_clinic": routed, "refill_overdue": overdue})
    except Exception as e:
        return jsonify({"error": str(e), "routed_to_clinic": [], "refill_overdue": []}), 500


@app.route('/api/notification-preview', methods=['POST'])
def notification_preview():
    """Return the notification message preview for a patient (no send). Built inline – no agent, no AI – so the pharmacy table is always shown."""
    try:
        data = request.get_json() or {}
        member_id, patient_row, err = _resolve_patient_for_notification(data)
        if err:
            return jsonify({"success": False, "error": err}), 400

        normalized = validate_and_normalize_row(patient_row)
        clean_row = normalized.get("clean", patient_row)
        route = determine_contact_route(clean_row)
        if not route.get("allowed", False):
            return jsonify({
                "success": False,
                "error": route.get("reason", "Contact not permitted"),
            }), 200

        # Build message here only (pharmacy module). Do not call agent.build_adherence_message or any AI.
        message = _build_preview_message_inline(clean_row)
        return jsonify({"success": True, "message": message})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/send-notification', methods=['POST'])
def send_notification_manual():
    """
    Manually send a notification to a specific patient.
    Accepts either member_id (when PII is visible) or row_index + filter (when PII is masked).
    """
    try:
        data = request.get_json() or {}
        member_id, patient_row, err = _resolve_patient_for_notification(data)
        if err:
            return jsonify({"success": False, "error": err}), 400 if "Provide" in err or "No patient" in err else 404

        normalized = validate_and_normalize_row(patient_row)
        clean_row = normalized.get("clean", patient_row)
        route = determine_contact_route(clean_row)
        channel = route.get("channel", "pushover")
        notification_channel = clean_row.get("NotificationChannel", "")
        _nc = (str(notification_channel).strip().lower() if notification_channel else "")
        use_pushover = channel == "pushover" or (
            _nc in ["app push", "apppush", "push", "app notify", "appnotify", "notification", "notify"]
        )
        use_call = channel == "call" or _nc == "call"
        use_sms = channel == "sms"
        use_whatsapp = channel == "whatsapp"
        use_email_ch = channel == "email"

        if not route.get("allowed", False):
            return jsonify({
                "success": False,
                "status": "Blocked",
                "error": route.get("reason", "Contact not permitted"),
            }), 200

        # Governance: only one contact per patient per day (notification or appreciation)
        try:
            if _any_contact_sent_today(clean_row):
                return jsonify({
                    "success": False,
                    "status": "Blocked",
                    "error": "Governance: already sent today (notification or appreciation). Only one contact per patient per day.",
                }), 200
        except Exception:
            pass

        status = "Failed"
        msg_id = ""
        send_res = {}
        try:
            if use_call:
                # Twilio voice call when NotificationChannel is "call"
                phone = clean_row.get("Patient Contact") or clean_row.get("Patient Contact Number") or ""
                phone = str(phone).strip()
                if not phone:
                    send_res = {"message": "", "error": "No Patient Contact for call"}
                else:
                    message = build_adherence_message(clean_row)
                    result = make_twilio_voice_call(to_number=phone, message=message)
                    if "error" in result:
                        send_res = {"message": message, "error": result["error"]}
                    else:
                        status = "Sent"
                        msg_id = result.get("call_sid") or "queued"
                        send_res = {"message": message, "call_sid": msg_id}
            elif use_sms:
                phone = route.get("address") or clean_row.get("Patient Contact") or ""
                phone = str(phone).strip()
                if not phone:
                    send_res = {"message": "", "error": "No Patient Contact for SMS"}
                else:
                    message = build_adherence_message(clean_row)
                    result = send_twilio_sms(to_number=phone, body=message)
                    if "error" in result:
                        send_res = {"message": message, "error": result["error"]}
                    else:
                        status = "Sent"
                        msg_id = result.get("sid") or "queued"
                        send_res = {"message": message, "sid": msg_id}
            elif use_whatsapp:
                phone = route.get("address") or clean_row.get("Patient Contact") or ""
                phone = str(phone).strip()
                if not phone:
                    send_res = {"message": "", "error": "No Patient Contact for WhatsApp"}
                else:
                    message = build_adherence_message(clean_row)
                    result = send_twilio_whatsapp(to_number=phone, body=message)
                    if "error" in result:
                        send_res = {"message": message, "error": result["error"]}
                    else:
                        status = "Sent"
                        msg_id = result.get("sid") or "queued"
                        send_res = {"message": message, "sid": msg_id}
            elif use_email_ch:
                to_addr = route.get("address") or clean_row.get("Patient EmailID") or ""
                to_addr = str(to_addr).strip()
                if not to_addr:
                    send_res = {"message": "", "error": "No Patient EmailID for Email"}
                else:
                    message = build_adherence_message(clean_row)
                    subject = "Medication Adherence Reminder"
                    result = send_email(to_email=to_addr, subject=subject, body=message)
                    if "error" in result:
                        send_res = {"message": message, "error": result["error"]}
                    else:
                        status = "Sent"
                        msg_id = result.get("status_code") or "sent"
                        send_res = {"message": message}
            else:
                # Pushover: use adherence message with pharmacy table (same as other channels)
                message = build_adherence_message(clean_row)
                send_res = {"message": message}
                if use_pushover:
                    from agent import send_pushover_message
                    from config import PUSHOVER_API_TOKEN, PUSHOVER_USER_KEY
                    if PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY:
                        medication = clean_row.get("Medication Name", "Medication")
                        pushover_res = send_pushover_message(
                            user_key=PUSHOVER_USER_KEY,
                            token=PUSHOVER_API_TOKEN,
                            title=f"{medication} Adherence Reminder",
                            message=message,
                        )
                        if "error" not in pushover_res:
                            status = "Sent"
                            msg_id = pushover_res.get("request", "")
                        else:
                            status = "Failed"
                            send_res["pushover_error"] = pushover_res.get("error", "Unknown error")
                    else:
                        status = "Failed"
                        send_res["pushover_error"] = "Pushover not configured"
                else:
                    status = "Queued"
        except Exception as e:
            send_res = {"message": "", "pushover_error": str(e)}

        # Only persist sent/queued to Excel so failed sends don't block retries or show as "contacted"
        if member_id and status in ("Sent", "Queued"):
            try:
                sent_details = {
                    member_id: {
                        "NotificationStatus": status,
                        "NotificationChannel": channel or "",
                        "NotificationMessageId": msg_id or "",
                    }
                }
                update_notification_sent_on([member_id], pd.Timestamp.now(), details_by_member_id=sent_details)
            except Exception as e:
                pass

        first, last = name_parts(clean_row.get("Patient Name", "Patient"))
        pushover_error = send_res.get("pushover_error") or send_res.get("error") or ""
        notification_event = {
            "member_id": member_id,
            "first": first,
            "last": last,
            "ts": datetime.now().isoformat(),
            "channel": channel or "",
            "message_id": msg_id or "",
            "status": status,
            "pushover_error": pushover_error or None,
        }
        socketio.emit("notification_sent", notification_event)

        return jsonify({
            "success": status in ("Sent", "Queued"),
            "status": status,
            "message": send_res.get("message", ""),
            "channel": channel,
            "pushover_error": pushover_error or None,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/make-call', methods=['POST'])
def make_call():
    """
    Make an outbound voice call to a patient using Twilio Programmable Voice.
    Uses the same patient resolution as send-notification (member_id or row_index + filter).
    Speaks a short medication adherence reminder (TTS) via TwiML <Say>.
    See: https://www.twilio.com/docs/voice/tutorials/how-to-make-outbound-phone-calls
    """
    try:
        data = request.get_json() or {}
        member_id, patient_row, err = _resolve_patient_for_notification(data)
        if err:
            return jsonify({"success": False, "error": err}), 400 if "Provide" in err or "No patient" in err else 404

        normalized = validate_and_normalize_row(patient_row)
        clean_row = normalized.get("clean", patient_row)
        phone = clean_row.get("Patient Contact") or patient_row.get("Patient Contact") or ""
        phone = str(phone).strip()
        if not phone:
            return jsonify({"success": False, "error": "Patient has no contact number (Patient Contact)."}), 400

        message = build_adherence_message(clean_row)
        result = make_twilio_voice_call(to_number=phone, message=message)
        if "error" in result:
            return jsonify({
                "success": False,
                "error": result["error"],
                "call_sid": None,
            }), 200
        return jsonify({
            "success": True,
            "call_sid": result.get("call_sid"),
            "status": result.get("status", "queued"),
            "message": "Voice call initiated.",
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/patient-response', methods=['POST'])
def patient_response_endpoint():
    """
    Patient Response endpoint: Automatically processes patient messages,
    understands issues and pain points, provides resolution recommendations,
    and routes critical cases to hospitals.
    """
    try:
        data = request.get_json()
        patient_message = data.get('message', '').strip()
        member_id = data.get('member_id', '').strip()
        conversation_history = data.get('history', [])
        
        if not patient_message:
            return jsonify({"error": "Patient message is required"}), 400
        
        if not member_id:
            return jsonify({"error": "Member ID is required"}), 400
        
        # Load patient data
        try:
            df = load_patient_data(force_reload=False)
            member_id_col = "Member ID" if "Member ID" in df.columns else "Member_ID"
            
            if member_id_col not in df.columns:
                return jsonify({"error": "Member ID column not found in data"}), 500
            
            patient_df = df[df[member_id_col].astype(str).str.strip() == member_id]
            if patient_df.empty:
                return jsonify({"error": f"Patient with ID {member_id} not found"}), 404
            
            patient_row = patient_df.iloc[0].to_dict()
            
            # Normalize patient row
            normalized = validate_and_normalize_row(patient_row)
            clean_row = normalized.get('clean', patient_row)
            
        except Exception as e:
            return jsonify({"error": f"Error loading patient data: {str(e)}"}), 500
        
        # Auto-respond to patient with comprehensive analysis
        try:
            auto_response = auto_respond_to_patient(
                patient_message=patient_message,
                patient_row=clean_row,
                conversation_history=conversation_history
            )
            
            # Extract key information
            response_message = auto_response.get("response_message", "")
            issue_analysis = auto_response.get("issue_analysis", {})
            resolution_recommendations = auto_response.get("resolution_recommendations", {})
            care_routing = auto_response.get("care_routing", {})
            routing_action = auto_response.get("routing_action")
            
            # Emit WebSocket events for critical cases
            if routing_action and routing_action.get("routed"):
                socketio.emit('critical_patient_alert', {
                    "type": "critical_patient_response",
                    "member_id": member_id,
                    "name": clean_row.get("Patient Name", "Unknown"),
                    "urgency": issue_analysis.get("urgency", "normal"),
                    "issues": issue_analysis.get("issues", []),
                    "routing_target": care_routing.get("routing_target"),
                    "routing_reason": care_routing.get("routing_reason"),
                    "timestamp": datetime.now().isoformat()
                })
            
            # Emit care routing alert if needed
            if care_routing.get("needs_routing"):
                socketio.emit('care_routing_alert', {
                    "type": "care_routing",
                    "member_id": member_id,
                    "name": clean_row.get("Patient Name", "Unknown"),
                    "routing_level": care_routing.get("routing_level"),
                    "routing_target": care_routing.get("routing_target"),
                    "urgency": care_routing.get("urgency"),
                    "routing_reason": care_routing.get("routing_reason"),
                    "recommended_action": care_routing.get("recommended_action"),
                    "immediate_action_required": care_routing.get("immediate_action_required", False),
                })
            
            result = {
                "success": True,
                "response_message": response_message,
                "issue_analysis": {
                    "issues": issue_analysis.get("issues", []),
                    "pain_points": issue_analysis.get("pain_points", []),
                    "urgency": issue_analysis.get("urgency", "normal"),
                    "emotional_state": issue_analysis.get("emotional_state", "neutral"),
                    "root_causes": issue_analysis.get("root_causes", []),
                },
                "resolution_recommendations": {
                    "recommendations": resolution_recommendations.get("recommendations", []),
                    "priority_order": resolution_recommendations.get("priority_order", []),
                    "overall_approach": resolution_recommendations.get("overall_approach", ""),
                    "critical_actions_required": resolution_recommendations.get("critical_actions_required", []),
                },
                "care_routing": {
                    "needs_routing": care_routing.get("needs_routing", False),
                    "routing_level": care_routing.get("routing_level"),
                    "routing_target": care_routing.get("routing_target"),
                    "urgency": care_routing.get("urgency"),
                    "routing_reason": care_routing.get("routing_reason"),
                    "recommended_action": care_routing.get("recommended_action"),
                    "immediate_action_required": care_routing.get("immediate_action_required", False),
                },
                "routing_action": routing_action,
                "needs_follow_up": auto_response.get("needs_follow_up", False),
                "recommended_follow_up_time": auto_response.get("recommended_follow_up_time", ""),
            }
            
            return jsonify(result)
            
        except Exception as e:
            return jsonify({
                "error": str(e),
                "success": False,
                "response_message": "I apologize, but I encountered an error processing your message. Please contact your healthcare provider directly for immediate assistance."
            }), 500
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "success": False
        }), 500

@app.route('/api/chatbot', methods=['POST'])
def chatbot_endpoint():
    """AI Chatbot endpoint that uses the chatbot agent to answer user questions"""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        conversation_history = data.get('history', [])
        
        if not user_message:
            return jsonify({"error": "Message is required"}), 400
        
        # Get dashboard context from current state
        dashboard_context = None
        try:
            df = load_patient_data(force_reload=False)
            runner = get_backend_runner()
            
            # Build dashboard context similar to get_dashboard_data
            if not df.empty:
                adherence_col = "Adherence Percentage" if "Adherence Percentage" in df.columns else "Adeherence Percentage"
                if adherence_col not in df.columns and "PDC Percentage" in df.columns:
                    adherence_col = "PDC Percentage"
                
                if adherence_col in df.columns:
                    df[adherence_col] = pd.to_numeric(df[adherence_col], errors="coerce")
                    avg_adherence = float(df[adherence_col].mean()) if not df[adherence_col].isna().all() else 0
                else:
                    avg_adherence = 0
                
                # Calculate KPIs
                member_id_col = "Member ID" if "Member ID" in df.columns else "Member_ID"
                unique_patients = df[member_id_col].nunique() if member_id_col in df.columns else len(df)
                
                # High risk: low adherence AND refill days <= 7
                if adherence_col in df.columns:
                    dur = pd.to_numeric(df.get("days_until_refill"), errors="coerce")
                    refill_soon = dur.notna() & (dur <= 7)
                    high_risk = int(((df[adherence_col] < THRESHOLD_LOW) & refill_soon).sum())
                else:
                    high_risk = 0
                
                # Get interventions data (from runner stats if available)
                interventions_30d = runner.stats.get('total_interventions_30d', 0) if runner else 0
                notified_today = runner.stats.get('notified_today', 0) if runner else 0
                notified_unique = runner.stats.get('notified_unique', 0) if runner else 0
                responded_unique = runner.stats.get('responded_unique', 0) if runner else 0
                
                # Projected savings (rough estimate)
                proj_savings_month = interventions_30d * 500  # ₹500 per intervention estimate
                
                dashboard_context = {
                    'kpis': {
                        'avg_adherence_now': avg_adherence,
                        'high_risk_now': high_risk,
                        'interventions_30d': interventions_30d,
                        'notified_today': notified_today,
                        'notified_unique': notified_unique,
                        'responded_unique': responded_unique,
                        'proj_savings_month': proj_savings_month,
                    },
                    'system': {
                        'status': 'Active' if live_on else 'Paused',
                        'live_on': live_on,
                        'last_sync': fmt_minutes_ago(last_sync_ts),
                        'agents_running': 1 if live_on else 0,
                    }
                }
        except Exception as e:
            # If dashboard context fails, continue without it
            print(f"Warning: Could not build dashboard context: {e}")
            dashboard_context = None
        
        # Check if user is asking about a specific patient
        patient_data = None
        member_id_match = None
        if 'member_id' in data:
            member_id_match = data['member_id']
        else:
            # Try to extract member ID from message
            import re
            match = re.search(r'(?:member|patient|id)[\s:]*([A-Z0-9\-]+)', user_message, re.IGNORECASE) or \
                    re.search(r'\b([A-Z0-9]{3,}[-]?[A-Z0-9]*)\b', user_message)
            if match:
                member_id_match = match.group(1)
        
        # Get patient row data for comprehensive analysis
        patient_row = None
        if member_id_match:
            try:
                df = load_patient_data(force_reload=False)
                member_id_col = "Member ID" if "Member ID" in df.columns else "Member_ID"
                if member_id_col in df.columns:
                    patient_df = df[df[member_id_col].astype(str).str.strip() == str(member_id_match).strip()]
                    if not patient_df.empty:
                        patient_row_dict = patient_df.iloc[0].to_dict()
                        patient_row = patient_row_dict
                        patient_data = {k: str(v) if pd.notna(v) else "" for k, v in patient_row_dict.items()}
            except Exception as e:
                print(f"Error loading patient data: {e}")
                pass  # Continue without patient data if lookup fails
        
        # Check if user wants to execute actions (send notification, appreciate, etc.)
        user_lower = user_message.lower()
        wants_action = any(phrase in user_lower for phrase in [
            'send notification', 'notify patient', 'send reminder', 'send message',
            'appreciate patient', 'send appreciation', 'thank patient'
        ])
        
        # Execute actions if requested and patient_row is available
        # Allow actions by default (can be made configurable)
        allow_actions = True
        action_result = None
        if wants_action and patient_row and allow_actions:
            try:
                # Normalize patient row for agent functions
                normalized_row = validate_and_normalize_row(patient_row)
                clean_row = normalized_row.get('clean', patient_row)
                
                if 'send notification' in user_lower or 'notify' in user_lower:
                    # Force send notification when user explicitly requests it
                    # Bypass policy checks for manual sends, but still respect consent
                    print(f"[CHATBOT] User requested notification send")
                    
                    member_id = str(clean_row.get('Member ID', '')).strip()
                    patient_name = clean_row.get('Patient Name', 'Patient')
                    first, last = name_parts(patient_name)
                    
                    # Governance: only one contact per patient per day (notification or appreciation)
                    try:
                        if _any_contact_sent_today(clean_row):
                            result = {
                                "response": f"⚠️ **Governance: One contact per day**\n\nA notification or appreciation was already sent to **{patient_name}** today. We cannot send another contact to this patient on the same day.",
                                "success": True,
                                "action_result": {
                                    'action': 'blocked_governance',
                                    'status': 'Blocked',
                                    'message': 'Already sent today (notification or appreciation). Only one per patient per day.',
                                }
                            }
                            return jsonify(result)
                    except Exception as e:
                        print(f"[CHATBOT] Error checking contact-sent-today: {e}")

                    # Get route (respects NotificationChannel column)
                    route = determine_contact_route(clean_row)
                    channel = route.get('channel', 'pushover')
                    print(f"[CHATBOT] Route determined: allowed={route.get('allowed')}, channel={channel}, reason={route.get('reason')}")
                    
                    # Force send if route is allowed (consent check)
                    if route.get('allowed', False):
                        # Check if NotificationChannel is "App Push" to use Pushover, or "call" for Twilio voice
                        notification_channel = clean_row.get('NotificationChannel', '')
                        _nc = (str(notification_channel).strip().lower() if notification_channel else '')
                        use_pushover = (channel == 'pushover' or 
                                       _nc in ['app push', 'apppush', 'push', 'app notify', 'appnotify', 'notification', 'notify'])
                        use_call = (channel == 'call' or _nc == 'call')
                        use_sms = (channel == 'sms')
                        use_whatsapp = (channel == 'whatsapp')
                        use_email_ch = (channel == 'email')
                        print(f"[CHATBOT] use_pushover={use_pushover}, use_call={use_call}, use_sms={use_sms}, use_whatsapp={use_whatsapp}, use_email={use_email_ch}, notification_channel={notification_channel}")
                        
                        # Send notification
                        send_res = {}
                        try:
                            if use_call:
                                phone = clean_row.get('Patient Contact') or clean_row.get('Patient Contact Number') or ''
                                phone = str(phone).strip()
                                if not phone:
                                    status, msg_id, send_res = 'Failed', '', {'message': '', 'error': 'No Patient Contact for call'}
                                    print(f"[CHATBOT] Call skipped: no phone number")
                                else:
                                    message = build_adherence_message(clean_row)
                                    result = make_twilio_voice_call(to_number=phone, message=message)
                                    send_res = result
                                    if 'error' in result:
                                        status, msg_id = 'Failed', ''
                                        print(f"[CHATBOT] Twilio call failed: {result.get('error')}")
                                    else:
                                        status, msg_id = 'Sent', result.get('call_sid') or 'queued'
                                        print(f"[CHATBOT] Twilio call initiated, SID: {msg_id}")
                            elif use_sms:
                                phone = route.get('address') or clean_row.get('Patient Contact') or ''
                                phone = str(phone).strip()
                                if not phone:
                                    status, msg_id, send_res = 'Failed', '', {'message': '', 'error': 'No Patient Contact for SMS'}
                                else:
                                    message = build_adherence_message(clean_row)
                                    result = send_twilio_sms(to_number=phone, body=message)
                                    if 'error' in result:
                                        status, msg_id, send_res = 'Failed', '', {'message': message, 'error': result['error']}
                                        print(f"[CHATBOT] Twilio SMS failed: {result.get('error')}")
                                    else:
                                        status, msg_id, send_res = 'Sent', result.get('sid') or 'queued', {'message': message, 'sid': result.get('sid')}
                                        print(f"[CHATBOT] Twilio SMS sent, SID: {msg_id}")
                            elif use_whatsapp:
                                phone = route.get('address') or clean_row.get('Patient Contact') or ''
                                phone = str(phone).strip()
                                if not phone:
                                    status, msg_id, send_res = 'Failed', '', {'message': '', 'error': 'No Patient Contact for WhatsApp'}
                                else:
                                    message = build_adherence_message(clean_row)
                                    result = send_twilio_whatsapp(to_number=phone, body=message)
                                    if 'error' in result:
                                        status, msg_id, send_res = 'Failed', '', {'message': message, 'error': result['error']}
                                        print(f"[CHATBOT] Twilio WhatsApp failed: {result.get('error')}")
                                    else:
                                        status, msg_id, send_res = 'Sent', result.get('sid') or 'queued', {'message': message, 'sid': result.get('sid')}
                                        print(f"[CHATBOT] Twilio WhatsApp sent, SID: {msg_id}")
                            elif use_email_ch:
                                to_addr = route.get('address') or clean_row.get('Patient EmailID') or ''
                                to_addr = str(to_addr).strip()
                                if not to_addr:
                                    status, msg_id, send_res = 'Failed', '', {'message': '', 'error': 'No Patient EmailID for Email'}
                                else:
                                    message = build_adherence_message(clean_row)
                                    result = send_email(to_email=to_addr, subject='Medication Adherence Reminder', body=message)
                                    if 'error' in result:
                                        status, msg_id, send_res = 'Failed', '', {'message': message, 'error': result['error']}
                                        print(f"[CHATBOT] SendGrid email failed: {result.get('error')}")
                                    else:
                                        status, msg_id, send_res = 'Sent', 'sent', {'message': message}
                                        print(f"[CHATBOT] Email sent via SendGrid")
                            else:
                                # Pushover: use adherence message with pharmacy table (same as other channels)
                                message = build_adherence_message(clean_row)
                                send_res = {"message": message}
                                if use_pushover:
                                    from agent import send_pushover_message
                                    from config import PUSHOVER_API_TOKEN, PUSHOVER_USER_KEY
                                    if PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY:
                                        medication = clean_row.get('Medication Name', 'Medication')
                                        pushover_res = send_pushover_message(
                                            user_key=PUSHOVER_USER_KEY,
                                            token=PUSHOVER_API_TOKEN,
                                            title=f"{medication} Adherence Reminder",
                                            message=message,
                                        )
                                        if 'error' not in pushover_res:
                                            status = 'Sent'
                                            msg_id = pushover_res.get('request', '')
                                            print(f"[CHATBOT] Pushover sent with adherence message (pharmacy table)")
                                        else:
                                            status = 'Failed'
                                            msg_id = ''
                                            send_res['pushover_error'] = pushover_res.get('error', '')
                                            print(f"[CHATBOT] Pushover API error: {pushover_res.get('error')}")
                                    else:
                                        status = 'Failed'
                                        msg_id = ''
                                        send_res['pushover_error'] = 'Pushover not configured'
                                        print(f"[CHATBOT] Pushover credentials not configured")
                                else:
                                    status = 'Queued'
                                    msg_id = ''
                                    print(f"[CHATBOT] Notification queued for {channel}")
                        except Exception as e:
                            status = 'Failed'
                            msg_id = ''
                            print(f"[CHATBOT] Error sending notification: {e}")
                            import traceback
                            traceback.print_exc()
                        
                        # Only persist when actually sent/queued so failed sends don't block retries
                        if member_id and status in ('Sent', 'Queued'):
                            try:
                                sent_details = {
                                    member_id: {
                                        "NotificationStatus": status,
                                        "NotificationChannel": channel or "",
                                        "NotificationMessageId": msg_id or "",
                                    }
                                }
                                update_notification_sent_on([member_id], pd.Timestamp.now(), details_by_member_id=sent_details)
                                print(f"[CHATBOT] ✅ Updated Excel - NotificationSentOn for member {member_id}")
                            except Exception as e:
                                print(f"[CHATBOT] ❌ Error updating NotificationSentOn: {e}")
                        
                        send_error = send_res.get('pushover_error') or send_res.get('error') or '' if send_res else ''
                        action_result = {
                            'action': 'notification_sent',
                            'status': status,
                            'message': send_res.get('message', '') if send_res else 'Notification attempt',
                            'channel': channel,
                            'error': send_error or None,
                        }
                        
                        # ALWAYS emit WebSocket event (even for failures) so user gets feedback
                        notification_event = {
                            'member_id': member_id,
                            'first': first,
                            'last': last,
                            'ts': datetime.now().isoformat(),
                            'channel': channel or '',
                            'message_id': msg_id or '',
                            'status': status,
                            'pushover_error': send_error or None,
                        }
                        
                        print(f"[CHATBOT] Emitting WebSocket event: {notification_event}")
                        # Emit to WebSocket clients
                        socketio.emit('notification_sent', notification_event)
                        print(f"[CHATBOT] WebSocket event emitted")
                    else:
                        # Consent blocked - still emit event so user knows why
                        action_result = {
                            'action': 'notification_blocked',
                            'status': 'Blocked',
                            'message': route.get('reason', 'Contact not permitted'),
                            'channel': 'none'
                        }
                        
                        # Emit blocked event
                        notification_event = {
                            'member_id': member_id,
                            'first': first,
                            'last': last,
                            'ts': datetime.now().isoformat(),
                            'channel': 'none',
                            'message_id': '',
                            'status': 'Blocked',
                            'reason': route.get('reason', 'Contact not permitted'),
                        }
                        print(f"[CHATBOT] Notification blocked, emitting event: {notification_event}")
                        socketio.emit('notification_sent', notification_event)
                elif 'appreciate' in user_lower or 'thank' in user_lower:
                    # Send appreciation - force send when user explicitly requests
                    
                    appreciation = check_and_appreciate_refilled_patient(clean_row)
                    if appreciation.get('should_appreciate'):
                        # Governance: only one contact per patient per day (notification or appreciation)
                        try:
                            if _any_contact_sent_today(clean_row):
                                patient_name = clean_row.get('Patient Name', 'Patient')
                                result = {
                                    "response": f"⚠️ **Governance: One contact per day**\n\nA notification or appreciation was already sent to **{patient_name}** today. We cannot send another contact to this patient on the same day.",
                                    "success": True,
                                    "action_result": {
                                        'action': 'blocked_governance',
                                        'status': 'Blocked',
                                        'message': 'Already sent today (notification or appreciation). Only one per patient per day.',
                                    }
                                }
                                return jsonify(result)
                        except Exception as e:
                            print(f"[CHATBOT] Error checking contact-sent-today: {e}")

                        # Get route (respects NotificationChannel column)
                        route = determine_contact_route(clean_row)
                        channel = route.get('channel', 'pushover')
                        
                        # Force send if route is allowed (consent check)
                        if route.get('allowed', False):
                            # Check if NotificationChannel is "App Push" to use Pushover
                            notification_channel = clean_row.get('NotificationChannel', '')
                            _nc = (str(notification_channel).strip().lower() if notification_channel else '')
                            use_pushover = (channel == 'pushover' or 
                                           _nc in ['app push', 'apppush', 'push', 'app notify', 'appnotify', 'notification', 'notify'])
                            
                            msg = appreciation.get('appreciation_message', '')
                            name = clean_row.get('Patient Name', 'Patient')
                            status = 'Failed'
                            msg_id = ''
                            
                            if use_pushover:
                                try:
                                    if PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY:
                                        response = requests.post(
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
                                        if response.status_code == 200:
                                            status = 'Sent'
                                            msg_id = response.json().get('request', '')
                                except Exception as e:
                                    print(f"Error sending appreciation via Pushover: {e}")
                            
                            # Governance: record appreciation sent today (no duplicate appreciation same day)
                            member_id = str(clean_row.get('Member ID', '')).strip()
                            if member_id and status == 'Sent':
                                try:
                                    update_appreciation_sent_on([member_id], pd.Timestamp.now())
                                except Exception as e:
                                    print(f"Error updating AppreciationSentOn: {e}")
                            
                            action_result = {
                                'action': 'appreciation_sent',
                                'status': status,
                                'message': msg,
                                'reason': appreciation.get('appreciation_reason', ''),
                                'channel': channel
                            }
                            
                            # Emit WebSocket event if appreciation was sent successfully
                            if status == 'Sent':
                                first, last = name_parts(name)
                                
                                appreciation_event = {
                                    'member_id': member_id,
                                    'first': first,
                                    'last': last,
                                    'ts': datetime.now().isoformat(),
                                    'channel': channel or '',
                                    'message_id': msg_id or '',
                                    'status': status,
                                    'type': 'appreciation'
                                }
                                
                                # Emit to WebSocket clients
                                socketio.emit('patient_appreciation', appreciation_event)
                            else:
                                # Consent blocked
                                action_result = {
                                    'action': 'appreciation_blocked',
                                    'status': 'Blocked',
                                    'message': route.get('reason', 'Contact not permitted'),
                                    'channel': 'none'
                                }
                    else:
                        action_result = {
                            'action': 'appreciation_not_needed',
                            'message': 'Patient does not currently meet appreciation criteria.'
                        }
            except Exception as e:
                action_result = {
                    'action': 'error',
                    'error': str(e)
                }
        
        # Call the enhanced chatbot agent (pass requested member ID so agent can say "patient not found" if no row)
        response = chatbot_agent(
            user_message=user_message,
            dashboard_context=dashboard_context,
            patient_data=patient_data,
            patient_row=patient_row,
            conversation_history=conversation_history,
            allow_actions=wants_action,
            requested_member_id=member_id_match if member_id_match else None,
        )
        
        result = {
            "response": response,
            "success": True
        }
        
        # Include action result if action was executed
        if action_result:
            result["action_result"] = action_result
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "response": "I apologize, but I encountered an error. Please try again.",
            "success": False
        }), 500

# WebSocket events
@socketio.on('connect')
def handle_connect():
    emit('connected', {'data': 'Connected to dashboard'})

@socketio.on('disconnect')
def handle_disconnect():
    pass

# Serve React app (only if build folder exists; when frozen, static_folder is in _MEIPASS)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder = app.static_folder or ""
    if not static_folder or not os.path.isdir(static_folder):
        return jsonify({
            "error": "Frontend not available",
            "message": "Run 'cd frontend && npm run build' before building the executable, or start the backend with the frontend build present."
        }), 503

    if path and path != "index.html":
        full_path = os.path.join(static_folder, path)
        if os.path.isfile(full_path):
            return send_from_directory(static_folder, path)
    index_path = os.path.join(static_folder, "index.html")
    if os.path.isfile(index_path):
        return send_from_directory(static_folder, "index.html")
    return jsonify({
        "error": "Frontend not built",
        "message": "Run 'cd frontend && npm run build' first."
    }), 503

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").strip().lower() in ("1", "true", "yes")
    socketio.run(app, debug=debug, host="0.0.0.0", port=port, allow_unsafe_werkzeug=debug)
