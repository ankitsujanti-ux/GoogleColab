# Power BI Setup Guide — Medication Adherence Dashboard

## Overview

Connect Power BI to the `patients_final_report` Delta table in your Fabric Lakehouse.
This is the **only** table needed — it contains all patient data, risk scores, notification statuses, and computed KPI columns.

---

## Step 1: Connect to Lakehouse

1. Open **Power BI Desktop**
2. Click **Get Data** → **Microsoft Fabric** → **Lakehouses**
3. Select your Fabric workspace and Lakehouse
4. Choose the table: **`patients_final_report`**
5. Click **Load**

> **Alternative (Fabric native):** In your Fabric workspace, click on the Lakehouse → Click on the `patients_final_report` table → Click **"New Power BI Dataset"** from the toolbar. This auto-creates a semantic model.

---

## Step 2: Create DAX Measures

In Power BI Desktop, go to **Modeling** → **New Measure** and add these:

### KPI Measures

```dax
High Risk Count = COUNTROWS(FILTER(patients_final_report, patients_final_report[IsHighRisk] = TRUE))

Medium Risk Count = COUNTROWS(FILTER(patients_final_report, patients_final_report[IsMediumRisk] = TRUE))

Low Risk Count = COUNTROWS(FILTER(patients_final_report, patients_final_report[IsLowRisk] = TRUE))

Avg Adherence % = AVERAGE(patients_final_report[Adherence_Percentage])

Notified Today = COUNTROWS(FILTER(patients_final_report, patients_final_report[NotifiedToday] = TRUE))

Notifications Sent = COUNTROWS(FILTER(patients_final_report, patients_final_report[NotificationSuccessful] = TRUE))

Escalated Patients = COUNTROWS(FILTER(patients_final_report, patients_final_report[EscalatedToClinician] = TRUE))

Refill Overdue Count = COUNTROWS(FILTER(patients_final_report, patients_final_report[RefillOverdue] = TRUE))

Total Patients = COUNTROWS(patients_final_report)

Projected Monthly Savings = [Notifications Sent] * 1000
```

---

## Step 3: Build Report Pages

### Page 1: Executive Dashboard

| Visual | Type | Fields |
|--------|------|--------|
| **High Risk Patients** | Card | `High Risk Count` measure |
| **Avg Adherence** | Card | `Avg Adherence %` measure |
| **Notifications Sent** | Card | `Notifications Sent` measure |
| **Escalated** | Card | `Escalated Patients` measure |
| **Risk Distribution** | Donut Chart | Legend: `risk_label`, Values: count of `Member_ID` |
| **Adherence Distribution** | Donut Chart | Legend: `AdherenceGroup`, Values: count of `Member_ID` |
| **Notification Channel** | Bar Chart | Axis: `notification_channel_used`, Values: count of `Member_ID` |
| **Top High-Risk Patients** | Table | `Patient_Name`, `Adherence_Percentage`, `risk_score`, `Medication_Name`, `days_until_refill` |

### Page 2: Patient Details

| Visual | Type | Fields |
|--------|------|--------|
| **Patient Table** | Table | `Member_ID`, `Patient_Name`, `City`, `Medication_Name`, `Adherence_Percentage`, `risk_label`, `notification_status`, `sentiment_label` |
| **Adherence by City** | Map / Bar | Axis: `City`, Values: avg of `Adherence_Percentage` |
| **Risk Score vs Adherence** | Scatter | X: `Adherence_Percentage`, Y: `risk_score`, Details: `Patient_Name` |
| **Sentiment Distribution** | Pie Chart | Legend: `sentiment_label`, Values: count |

### Page 3: Notifications & Escalations

| Visual | Type | Fields |
|--------|------|--------|
| **Notifications by Channel** | Stacked Bar | Axis: `notification_channel_used`, Values: count, Legend: `notification_status` |
| **Care Priority** | Donut | Legend: `care_priority`, Values: count |
| **Escalated Patients** | Table | Filter: `EscalatedToClinician = TRUE`, Columns: `Patient_Name`, `routing_reason`, `routing_urgency`, `care_summary` |
| **Notification Timeline** | Line Chart | Axis: `NotificationSentOn`, Values: count |

---

## Step 4: Formatting Tips

- Use **conditional formatting** on `risk_label`: Red = High, Yellow = Medium, Green = Low
- Use **conditional formatting** on `Adherence_Percentage`: Red < 50, Yellow 50-80, Green >= 80
- Add **slicers** for: `risk_label`, `City`, `AdherenceGroup`, `notification_status`
- Set **card colors**: High Risk = red background, Avg Adherence = blue, Notifications = green

---

## Step 5: Auto-Refresh

1. **Publish** the report to your Fabric workspace
2. Go to **Workspace** → **Settings** on the dataset
3. Under **Scheduled Refresh**, set to refresh every **30–60 minutes**
   - This aligns with the Fabric Data Pipeline schedule from `pipeline_definition.json`
4. The data will automatically update after each pipeline run

---

## Step 6: Share

1. Go to your published report in Fabric workspace
2. Click **Share** or **Manage permissions**
3. Add team members (care coordinators, pharmacy managers, clinicians)
4. Optionally create a **Fabric App** for broader distribution

---

## Quick Start (Fabric Native — No Power BI Desktop Needed)

If you don't want to use Power BI Desktop:

1. In your Fabric workspace, go to your **Lakehouse**
2. Find `patients_final_report` in Tables
3. Right-click → **New Power BI Report**
4. Fabric opens the web-based report editor
5. Drag and drop columns to build visuals
6. Save the report to your workspace

This works entirely in the browser — no desktop installation needed.
