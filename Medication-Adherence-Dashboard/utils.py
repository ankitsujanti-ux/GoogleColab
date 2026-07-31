# utils.py
import logging
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from config import EXCEL_PATH, THRESHOLD_LOW, THRESHOLD_MED

logger = logging.getLogger(__name__)

_last_mtime = None
_cached_df = None

EXCEL_INVALID_MSG = (
    "The file at EXCEL_PATH is not a valid Excel (.xlsx) file. "
    "It may be corrupted, empty, or saved in another format (e.g. CSV). "
    "Please ensure the file in .env (EXCEL_PATH) is a valid .xlsx workbook."
)

# Required columns for high-risk detection, notifications, and clinician routing.
# If missing, they are added to the Excel file with default empty/NaN values.
REQUIRED_EXCEL_COLUMNS = [
    "Member ID",
    "Patient Name",
    "Adherence Percentage",
    "Adeherence Percentage",
    "PDC Percentage",
    "Refill Days",
    "Patient Contact",
    "Patient EmailID",
    "City",
    "Medication Name",
    "EventDate",
    "NotificationSentOn",
    "NotificationSentAt",
    "NotificationStatus",
    "NotificationChannel",
    "NotificationMessageId",
    "RoutedToClinicianOn",
    "RoutedToClinicianNote",
    "AppreciationSentOn",
    "RiskScore",
    "RiskLabel",
    "ClinicianAssigned",
    "EscalationReason",
    "LastUpdated",
]

def ensure_excel_columns(path: Optional[str] = None) -> None:
    """
    Ensure the Excel file has all required columns. Adds any missing columns
    with default empty/NaN values and saves the file so updates work correctly.
    """
    p = path or EXCEL_PATH
    if not os.path.exists(p):
        return
    try:
        raw_df = pd.read_excel(p, engine="openpyxl")
        raw_df.columns = [str(c).strip() for c in raw_df.columns]
        member_col = "Member ID" if "Member ID" in raw_df.columns else ("Member_ID" if "Member_ID" in raw_df.columns else None)
        if member_col is None:
            raw_df["Member ID"] = raw_df.index.astype(str)
        changed = False
        for col in REQUIRED_EXCEL_COLUMNS:
            if col not in raw_df.columns:
                if col in ("NotificationSentOn", "NotificationSentAt", "RoutedToClinicianOn", "AppreciationSentOn", "LastUpdated", "EventDate"):
                    raw_df[col] = pd.NaT
                elif col in ("Adherence Percentage", "Adeherence Percentage", "PDC Percentage", "Refill Days", "RiskScore"):
                    raw_df[col] = pd.NA
                else:
                    raw_df[col] = ""
                changed = True
        if changed:
            raw_df.to_excel(p, index=False, engine="openpyxl")
    except Exception:
        pass


def update_excel_column_values(
    member_ids: Iterable[str],
    column_updates: Dict[str, Any],
    path: Optional[str] = None
) -> None:
    """
    Update specific column values in the Excel file for given Member IDs.
    Automatically adds missing columns if they don't exist.
    
    Args:
        member_ids: List of Member IDs to update
        column_updates: Dictionary mapping column names to values
        path: Optional path to Excel file (defaults to EXCEL_PATH)
    """
    global _cached_df, _last_mtime
    p = path or EXCEL_PATH
    if not os.path.exists(p):
        raise FileNotFoundError(f"Excel file not found at path: {p}")
    
    member_ids = list(member_ids)
    if not member_ids or not column_updates:
        return
    
    try:
        # Ensure columns exist first
        ensure_excel_columns(p)
        
        raw_df = pd.read_excel(p, engine="openpyxl")
        raw_df.columns = [str(c).strip() for c in raw_df.columns]
        
        member_col = "Member ID" if "Member ID" in raw_df.columns else ("Member_ID" if "Member_ID" in raw_df.columns else None)
        if member_col is None:
            raise KeyError("Member ID column not found in the Excel sheet.")
        
        # Add missing columns if needed
        for col in column_updates.keys():
            if col not in raw_df.columns:
                if col in ("NotificationSentOn", "NotificationSentAt", "RoutedToClinicianOn", "LastUpdated", "EventDate"):
                    raw_df[col] = pd.NaT
                elif col in ("Adherence Percentage", "Adeherence Percentage", "PDC Percentage", "Refill Days", "RiskScore"):
                    raw_df[col] = pd.NA
                else:
                    raw_df[col] = ""
        
        # Update values for matching Member IDs
        mask = raw_df[member_col].astype(str).isin([str(m) for m in member_ids])
        for col, value in column_updates.items():
            if col in raw_df.columns:
                raw_df.loc[mask, col] = value
        
        # Update LastUpdated timestamp
        if "LastUpdated" in raw_df.columns:
            raw_df.loc[mask, "LastUpdated"] = pd.Timestamp.now()
        
        raw_df.to_excel(p, index=False, engine="openpyxl")
        
        # Refresh cache
        _cached_df = compute_fields(raw_df.copy())
        _last_mtime = os.path.getmtime(p)
    except Exception as e:
        raise RuntimeError(f"Error updating Excel columns: {str(e)}")


def route_to_clinician(
    member_ids: Iterable[str],
    reason: str,
    clinician_note: Optional[str] = None,
    path: Optional[str] = None
) -> None:
    """
    Route patient records to clinicians by updating the Excel file.
    
    Args:
        member_ids: List of Member IDs to route
        reason: Escalation reason (e.g., "High risk score", "Refill overdue")
        clinician_note: Optional note for the clinician
        path: Optional path to Excel file
    """
    now = pd.Timestamp.now()
    note = clinician_note or f"Escalated: {reason}"
    
    update_excel_column_values(
        member_ids=member_ids,
        column_updates={
            "RoutedToClinicianOn": now,
            "RoutedToClinicianNote": note,
            "EscalationReason": reason,
        },
        path=path
    )

def load_patient_data(force_reload: bool = False) -> pd.DataFrame:
    """
    Loads Excel data and caches it; reloads automatically when file time changes.
    Uses EXCEL_PATH from config (set via .env). Ensures required columns exist
    before loading so schema changes are handled and high-risk detection keeps working.
    Returns empty DataFrame if file is missing (production-friendly: app still starts).
    """
    global _last_mtime, _cached_df

    if not os.path.exists(EXCEL_PATH):
        _cached_df = pd.DataFrame()
        _last_mtime = None
        return pd.DataFrame()
    ensure_excel_columns(EXCEL_PATH)
    mtime = os.path.getmtime(EXCEL_PATH)
    if force_reload or _cached_df is None or _last_mtime != mtime:
        try:
            df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
        except Exception as e:
            logger.error("Failed to read Excel at %s: %s", EXCEL_PATH, e)
            raise
        df.columns = [str(c).strip() for c in df.columns]
        for col in ["PDC Percentage", "Adeherence Percentage", "Adherence Percentage", "Refill Days"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = compute_fields(df)
        _cached_df = df
        _last_mtime = mtime
        logger.info("Loaded %d patients from %s", len(df), os.path.basename(EXCEL_PATH))
    return _cached_df.copy()

def compute_fields(df: pd.DataFrame) -> pd.DataFrame:
    # prefer Adeherence Percentage if present else PDC Percentage
    adherence_col = None
    if "Adeherence Percentage" in df.columns:
        adherence_col = "Adeherence Percentage"
    elif "Adherence Percentage" in df.columns:
        adherence_col = "Adherence Percentage"
    elif "PDC Percentage" in df.columns:
        df["Adeherence Percentage"] = df["PDC Percentage"]
        adherence_col = "Adeherence Percentage"

    if adherence_col is None:
        adherence_col = "Adeherence Percentage"
        df[adherence_col] = 0

    df[adherence_col] = df[adherence_col].fillna(0)
    # ensure both spellings exist for downstream compatibility
    if adherence_col == "Adherence Percentage" and "Adeherence Percentage" not in df.columns:
        df["Adeherence Percentage"] = df["Adherence Percentage"]
    if adherence_col == "Adeherence Percentage":
        df["Adherence Percentage"] = df["Adeherence Percentage"]

    # classify adherence percentage into Low/Medium/High
    def classify(a):
        if a < THRESHOLD_LOW:
            return "Low"
        if a < THRESHOLD_MED:
            return "Medium"
        return "High"
    df["adherence_group"] = df["Adeherence Percentage"].apply(classify)

    # standard display label for patient: "ID - Name"
    if "Member ID" in df.columns and "Patient Name" in df.columns:
        df["patient_display"] = df["Member ID"].astype(str) + " - " + df["Patient Name"].astype(str)

    # Refill Days = days until refill / days of supply left; adherence based on this column only
    refill_days_col = next((c for c in ["Refill Days", "RefillDays", "Refill_Days"] if c in df.columns), None)
    if refill_days_col:
        rd = pd.to_numeric(df[refill_days_col], errors="coerce")
        df["days_until_refill"] = rd
        df["refill_due"] = (rd < 7) & (rd.notna())
    else:
        df["days_until_refill"] = pd.NA
        df["refill_due"] = False

    # ensure notification and routing columns exist
    if "NotificationSentOn" not in df.columns:
        df["NotificationSentOn"] = pd.NaT
    else:
        df["NotificationSentOn"] = pd.to_datetime(df["NotificationSentOn"], errors="coerce")
    if "NotificationStatus" not in df.columns:
        df["NotificationStatus"] = ""
    if "RoutedToClinicianOn" not in df.columns:
        df["RoutedToClinicianOn"] = pd.NaT
    else:
        df["RoutedToClinicianOn"] = pd.to_datetime(df["RoutedToClinicianOn"], errors="coerce")
    if "RoutedToClinicianNote" not in df.columns:
        df["RoutedToClinicianNote"] = ""

    if "EventDate" in df.columns:
        df["EventDate"] = pd.to_datetime(df["EventDate"], errors="coerce")

    # contact safe string
    for col in ["Patient Contact", "Patient EmailID", "Patient Name"]:
        if col not in df.columns:
            df[col] = None

    # set an ID column if not present
    if "Member ID" not in df.columns:
        df["Member ID"] = df.index.astype(str)

    return df


def update_notification_sent_on(
    member_ids: Iterable[str],
    timestamp: Optional[datetime] = None,
    details_by_member_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    """
    Update NotificationSentOn column for provided Member IDs with given timestamp (date).
    Persists changes to the Excel file and refreshes the cached dataframe.
    """
    global _cached_df, _last_mtime

    member_ids = list(member_ids)
    if not member_ids:
        return

    if not os.path.exists(EXCEL_PATH):
        return  # No-op when Excel not configured (e.g. first run)

    # Keep both a date-level and time-level stamp for auditability / dashboard popups
    ts_full = pd.Timestamp(timestamp if timestamp is not None else pd.Timestamp.now())
    ts_date = ts_full.normalize()

    raw_df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
    raw_df.columns = [c.strip() for c in raw_df.columns]

    member_col = None
    if "Member ID" in raw_df.columns:
        member_col = "Member ID"
    elif "Member_ID" in raw_df.columns:
        member_col = "Member_ID"
    else:
        raise KeyError("Member ID column not found in the Excel sheet.")

    if "NotificationSentOn" not in raw_df.columns:
        raw_df["NotificationSentOn"] = pd.NaT
    if "NotificationSentAt" not in raw_df.columns:
        raw_df["NotificationSentAt"] = pd.NaT
    if "NotificationStatus" not in raw_df.columns:
        raw_df["NotificationStatus"] = ""
    if "NotificationChannel" not in raw_df.columns:
        raw_df["NotificationChannel"] = ""
    if "NotificationMessageId" not in raw_df.columns:
        raw_df["NotificationMessageId"] = ""
    if "RoutedToClinicianOn" not in raw_df.columns:
        raw_df["RoutedToClinicianOn"] = pd.NaT
    if "RoutedToClinicianNote" not in raw_df.columns:
        raw_df["RoutedToClinicianNote"] = ""

    mask = raw_df[member_col].astype(str).isin([str(m) for m in member_ids])
    raw_df.loc[mask, "NotificationSentOn"] = ts_date
    raw_df.loc[mask, "NotificationSentAt"] = ts_full

    # Optional per-member metadata (channel, message id, status, etc.)
    if details_by_member_id:
        for mid, details in details_by_member_id.items():
            m = raw_df[member_col].astype(str) == str(mid)
            if not m.any():
                continue
            if "NotificationStatus" in details and details["NotificationStatus"] is not None:
                raw_df.loc[m, "NotificationStatus"] = str(details["NotificationStatus"])
            if "NotificationChannel" in details and details["NotificationChannel"] is not None:
                raw_df.loc[m, "NotificationChannel"] = str(details["NotificationChannel"])
            if "NotificationMessageId" in details and details["NotificationMessageId"] is not None:
                raw_df.loc[m, "NotificationMessageId"] = str(details["NotificationMessageId"])

    raw_df.to_excel(EXCEL_PATH, index=False)

    # refresh cache
    _cached_df = compute_fields(raw_df.copy())
    _last_mtime = os.path.getmtime(EXCEL_PATH)


def update_appreciation_sent_on(
    member_ids: Iterable[str],
    timestamp: Optional[datetime] = None,
) -> None:
    """
    Update AppreciationSentOn column for provided Member IDs (governance: one appreciation per patient per day).
    """
    global _cached_df, _last_mtime

    member_ids = list(member_ids)
    if not member_ids:
        return

    if not os.path.exists(EXCEL_PATH):
        return  # No-op when Excel not configured (e.g. first run)

    ts = pd.Timestamp(timestamp if timestamp is not None else pd.Timestamp.now()).normalize()

    raw_df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
    raw_df.columns = [c.strip() for c in raw_df.columns]

    member_col = "Member ID" if "Member ID" in raw_df.columns else ("Member_ID" if "Member_ID" in raw_df.columns else None)
    if member_col is None:
        raise KeyError("Member ID column not found in the Excel sheet.")

    if "AppreciationSentOn" not in raw_df.columns:
        raw_df["AppreciationSentOn"] = pd.NaT

    mask = raw_df[member_col].astype(str).isin([str(m) for m in member_ids])
    raw_df.loc[mask, "AppreciationSentOn"] = ts

    raw_df.to_excel(EXCEL_PATH, index=False)
    _cached_df = compute_fields(raw_df.copy())
    _last_mtime = os.path.getmtime(EXCEL_PATH)