# Fabric Deployment Guide — Medication Adherence Dashboard

## End-to-End Steps to Deploy in Microsoft Fabric

---

## Prerequisites

- Microsoft Fabric workspace (F64 or higher, or trial capacity)
- A Fabric Lakehouse created in your workspace
- The project files from this folder
- Your `.env` file with API keys (OpenAI, Twilio, Pushover, SendGrid)

---

## Step 1: Upload Files to Fabric Lakehouse

1. Open your **Fabric Workspace** → open your **Lakehouse**
2. In the Lakehouse Explorer, click **Files** in the left panel
3. Create folders and upload files as follows:

```
Lakehouse Files/
├── .env                          ← your .env file with API keys
├── Data/
│   └── patients.xlsx             ← your patient data Excel file
└── code/
    ├── agent.py                  ← copy from project root
    ├── pharmacy.py               ← copy from project root
    ├── config.py                 ← copy from project root
    ├── runtime_paths.py          ← copy from project root
    ├── structure.py              ← copy from project root
    └── utils.py                  ← copy from project root
```

> **Important:** The `code/` folder must contain all the Python files that the notebooks import. Upload `agent.py`, `pharmacy.py`, `config.py`, `runtime_paths.py`, `structure.py`, and `utils.py` from your project root.

---

## Step 2: Create Fabric Environment (Install Python Packages)

1. In your Fabric workspace, click **+ New** → **Environment**
2. Name it: `MedicationAdherenceEnv`
3. Under **Public libraries**, add these packages:
   ```
   openai
   python-dotenv
   openpyxl
   requests
   twilio
   ```
4. Click **Publish** and wait for the environment to build
5. Attach this environment to all notebooks you create

> **Alternative:** Each notebook has a `%pip install` cell at the top that installs packages inline. You can skip creating an Environment if you prefer this approach.

---

## Step 3: Create and Run Notebooks (In Order)

### Notebook 1: Setup Lakehouse

1. Click **+ New** → **Notebook** in your workspace
2. Name it: `01_setup_lakehouse`
3. Attach it to your Lakehouse (click **Lakehouses** in left sidebar → Add your Lakehouse)
4. Copy the code from `fabric_agents/01_setup_lakehouse.py`
5. Split into cells where indicated by the `# CELL N` comments
6. Run all cells
7. **Verify:** In your Lakehouse Explorer, you should see a new table called `patients` under Tables

### Notebook 2: Run Agent Pipeline

1. Create a new notebook: `02_run_agent_pipeline`
2. Attach Lakehouse
3. Copy code from `fabric_agents/02_run_agent_pipeline.py`
4. Split into cells at `# CELL N` markers
5. Run all cells
6. **Verify:** Table `patients_with_agents` appears in Lakehouse with enriched columns
7. **Check console:** You should see notification send results (Sent/Failed)

### Notebook 3: High-Risk Alerts

1. Create: `03_high_risk_alerts`
2. Attach Lakehouse
3. Copy code from `fabric_agents/03_high_risk_alerts.py`
4. Run all cells
5. **Verify:** Table `notification_log` appears with send results
6. **Check phone/email:** You should receive real notifications if credentials are valid

### Notebook 4: Build Final Report Table

1. Create: `04_build_final_report_table`
2. Attach Lakehouse
3. Copy code from `fabric_agents/04_build_final_report_table.py`
4. Run all cells
5. **Verify:** Table `patients_final_report` appears — this is for Power BI

---

## Step 4: Create Data Pipeline (Scheduled Automation)

1. In your workspace, click **+ New** → **Data Pipeline**
2. Name it: `MedicationAdherence_AgentPipeline`
3. Add activities in this order:

```
[Notebook Activity: 02_run_agent_pipeline]
         ↓ (on success)
[Notebook Activity: 03_high_risk_alerts]
         ↓ (on success)
[Notebook Activity: 04_build_final_report_table]
```

4. **Configure each activity:**
   - Click the activity → Settings → Select the corresponding notebook
   - Set timeout: 60 min for pipeline, 30 min for alerts, 15 min for report
   - Set retry: 1 retry, 5 min interval

5. **Schedule the pipeline:**
   - Click **Schedule** (clock icon in toolbar)
   - Set: Recurring, every **60 minutes**
   - Start time: now
   - Time zone: India Standard Time

6. **Save and activate** the pipeline

> **Reference:** See `pipeline_definition.json` for the full pipeline structure.

---

## Step 5: Set Up Power BI Report

1. Follow the step-by-step instructions in **`powerbi_setup.md`**
2. Connect to the `patients_final_report` table
3. Create KPI cards, risk donut charts, patient tables
4. Set up auto-refresh (30–60 min)
5. Publish to workspace and share with your team

---

## Lakehouse Tables Summary

After running all notebooks, your Lakehouse will have these tables:

| Table | Description | Created By |
|-------|-------------|------------|
| `patients` | Raw patient data (from Excel) | Notebook 1 |
| `patients_with_agents` | Enriched with all agent outputs (risk, sentiment, routing, notifications) | Notebook 2 |
| `notification_log` | Log of all notification attempts (sent/failed/skipped) | Notebook 3 |
| `patients_final_report` | Clean, one-row-per-patient table for Power BI | Notebook 4 |

---

## Data Flow Diagram

```
patients.xlsx (uploaded to Lakehouse Files)
     │
     ▼ [Notebook 1: 01_setup_lakehouse]
 ┌──────────────────┐
 │ patients (Delta)  │
 └──────────────────┘
     │
     ▼ [Notebook 2: 02_run_agent_pipeline]
 ┌──────────────────────────────┐
 │ patients_with_agents (Delta)  │  ← All AI agent outputs
 └──────────────────────────────┘    ← Real notifications sent here
     │
     ├──▼ [Notebook 3: 03_high_risk_alerts]
     │  ┌───────────────────────┐
     │  │ notification_log       │  ← Append-only log of sends
     │  └───────────────────────┘
     │
     ▼ [Notebook 4: 04_build_final_report_table]
 ┌────────────────────────────────┐
 │ patients_final_report (Delta)  │  ← Power BI connects HERE
 └────────────────────────────────┘
     │
     ▼ [Power BI]
 ┌──────────────────────────────────┐
 │ Dashboard: KPIs, Charts, Tables  │
 └──────────────────────────────────┘
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'agent'` | Upload `agent.py` and all dependencies to Lakehouse Files/code/ |
| `.env not found` | Upload `.env` to Lakehouse Files root (not inside a subfolder) |
| `No .env file found. Using environment variables only.` | Check that `.env` is at `/lakehouse/default/Files/.env` |
| Twilio errors (20003, etc.) | Check `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` in `.env` — no spaces around `=` |
| Pushover not sending | Verify `PUSHOVER_USER_KEY` and `PUSHOVER_API_TOKEN` in `.env` |
| `patients` table not found | Run Notebook 1 first |
| Empty `patients_with_agents` | Check that `patients` table has data; check Notebook 2 error output |
| Power BI shows no data | Re-run Notebook 4, then refresh the Power BI dataset |
| Pipeline fails on schedule | Check each notebook individually; review Fabric Monitor → Pipeline runs |

---

## Files Reference

| File | Purpose |
|------|---------|
| `fabric_config.py` | Configuration loader (reads .env from Lakehouse Files) |
| `01_setup_lakehouse.py` | Upload Excel → Delta table |
| `02_run_agent_pipeline.py` | Full agent pipeline with real notifications |
| `03_high_risk_alerts.py` | Targeted high-risk notifications + log |
| `04_build_final_report_table.py` | Build final Power BI table |
| `pipeline_definition.json` | Pipeline structure reference |
| `powerbi_setup.md` | Power BI report setup guide |
| `FABRIC_DEPLOY.md` | This file — end-to-end deployment guide |
