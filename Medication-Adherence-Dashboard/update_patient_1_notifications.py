from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    path = base_dir / "Data" / "patient_1.xlsx"
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    df = pd.read_excel(path)

    # Expect 1000 rows as requested
    if len(df) != 1000:
        raise SystemExit(f"Expected 1000 rows, found {len(df)}")

    # Clear all notification-related columns so we can set them deterministically
    for col in [
        "NotificationSentOn",
        "NotificationSentAt",
        "NotificationStatus",
        "NotificationChannel",
        "NotificationMessageId",
    ]:
        if col in df.columns:
            if col.endswith("On") or col.endswith("At"):
                df[col] = pd.NaT
            else:
                df[col] = ""

    # Choose 100 distinct patients (Member ID) to receive notifications
    member_ids = df["Member ID"].dropna().unique()
    if len(member_ids) < 100:
        raise SystemExit(f"Need at least 100 unique Member IDs, found {len(member_ids)}")

    rng = np.random.default_rng(42)
    chosen_ids = rng.choice(member_ids, size=100, replace=False)

    start = pd.Timestamp("2026-01-01 00:00:00")
    end = pd.Timestamp("2026-02-10 23:59:59")
    total_seconds = int((end - start).total_seconds())

    # Distribute channels evenly across SMS, Call, WhatsApp, Pushover
    channels = ["SMS", "Call", "WhatsApp", "Pushover"]
    channel_cycle = (channels * (100 // len(channels) + 1))[:100]

    for idx, (member_id, channel) in enumerate(zip(chosen_ids, channel_cycle)):
        mask = df["Member ID"] == member_id
        sub = df.loc[mask]
        if sub.empty:
            continue

        # Use the most recent EventDate row for the notification, if available
        if "EventDate" in df.columns and sub["EventDate"].notna().any():
            row_idx = sub["EventDate"].idxmax()
        else:
            row_idx = sub.index[0]

        # Random datetime between 1st Jan and 10th Feb 2026
        offset_seconds = int(rng.integers(0, total_seconds + 1))
        ts = start + pd.Timedelta(seconds=offset_seconds)

        df.at[row_idx, "NotificationSentOn"] = ts.normalize()
        df.at[row_idx, "NotificationSentAt"] = ts
        df.at[row_idx, "NotificationStatus"] = "Sent"
        df.at[row_idx, "NotificationChannel"] = channel
        df.at[row_idx, "NotificationMessageId"] = f"msg_{1000 + idx}"

    df.to_excel(path, index=False)


if __name__ == "__main__":
    main()

