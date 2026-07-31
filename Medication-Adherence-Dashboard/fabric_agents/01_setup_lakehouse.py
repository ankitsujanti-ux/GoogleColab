"""
═══════════════════════════════════════════════════════════════════════════════
  NOTEBOOK 1: Setup Lakehouse — Upload patients.xlsx to Delta Table
═══════════════════════════════════════════════════════════════════════════════

STEPS TO RUN IN FABRIC:
  1. Create a new Fabric Notebook in your workspace
  2. Attach it to your Lakehouse
  3. Copy-paste each cell below into separate notebook cells
  4. Upload your .env file and Data/patients.xlsx to Lakehouse Files
  5. Run all cells

This script uploads the patients Excel file into a Lakehouse Delta table.
═══════════════════════════════════════════════════════════════════════════════
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 1: Install dependencies
# ═══════════════════════════════════════════════════════════════════════════════
# %pip install openpyxl python-dotenv pandas

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 2: Configuration
# ═══════════════════════════════════════════════════════════════════════════════

import os
import sys
from pathlib import Path

# In Fabric, the Lakehouse is mounted here:
LAKEHOUSE_FILES = Path("/lakehouse/default/Files")
LAKEHOUSE_TABLES = Path("/lakehouse/default/Tables")

# Path to the uploaded Excel file in Lakehouse Files
EXCEL_FILE = LAKEHOUSE_FILES / "Data" / "patients.xlsx"

# Target Delta table name
TABLE_NAME = "patients"

print(f"Lakehouse Files path: {LAKEHOUSE_FILES}")
print(f"Excel file expected at: {EXCEL_FILE}")
print(f"Target table name: {TABLE_NAME}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 3: Verify Excel file exists
# ═══════════════════════════════════════════════════════════════════════════════

if not EXCEL_FILE.exists():
    # Also check directly in Files root
    alt_path = LAKEHOUSE_FILES / "patients.xlsx"
    if alt_path.exists():
        EXCEL_FILE = alt_path
        print(f"Found Excel at: {EXCEL_FILE}")
    else:
        raise FileNotFoundError(
            f"patients.xlsx not found at:\n"
            f"  {LAKEHOUSE_FILES / 'Data' / 'patients.xlsx'}\n"
            f"  {LAKEHOUSE_FILES / 'patients.xlsx'}\n\n"
            f"Please upload patients.xlsx to your Lakehouse Files section:\n"
            f"  1. Go to your Lakehouse in Fabric\n"
            f"  2. Click 'Files' in the left panel\n"
            f"  3. Create a 'Data' folder (optional)\n"
            f"  4. Upload patients.xlsx there"
        )
else:
    print(f"✅ Excel file found at: {EXCEL_FILE}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 4: Load Excel into Pandas DataFrame
# ═══════════════════════════════════════════════════════════════════════════════

import pandas as pd

df = pd.read_excel(str(EXCEL_FILE), engine="openpyxl")
df.columns = [str(c).strip() for c in df.columns]

print(f"Loaded {len(df)} rows, {len(df.columns)} columns from Excel")
print(f"Columns: {list(df.columns)}")
print(f"\nFirst 5 rows:")
print(df.head())

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 5: Ensure required columns exist
# ═══════════════════════════════════════════════════════════════════════════════

REQUIRED_COLUMNS = [
    "Member ID", "Patient Name", "Adherence Percentage", "Adeherence Percentage",
    "PDC Percentage", "Refill Days", "Patient Contact", "Patient EmailID",
    "City", "Medication Name", "EventDate",
    "NotificationSentOn", "NotificationSentAt", "NotificationStatus",
    "NotificationChannel", "NotificationMessageId",
    "RoutedToClinicianOn", "RoutedToClinicianNote",
    "AppreciationSentOn", "RiskScore", "RiskLabel",
    "ClinicianAssigned", "EscalationReason", "LastUpdated",
]

added = []
for col in REQUIRED_COLUMNS:
    if col not in df.columns:
        if col in ("NotificationSentOn", "NotificationSentAt", "RoutedToClinicianOn",
                    "AppreciationSentOn", "LastUpdated", "EventDate"):
            df[col] = pd.NaT
        elif col in ("Adherence Percentage", "Adeherence Percentage", "PDC Percentage",
                      "Refill Days", "RiskScore"):
            df[col] = None
        else:
            df[col] = ""
        added.append(col)

if added:
    print(f"Added {len(added)} missing columns: {added}")
else:
    print("✅ All required columns already present")

# Ensure Member ID exists
if "Member ID" not in df.columns and "Member_ID" not in df.columns:
    df["Member ID"] = df.index.astype(str)
    print("Added Member ID from row index")

print(f"\nFinal schema: {len(df.columns)} columns, {len(df)} rows")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 6: Convert to Spark DataFrame and write as Delta table
# ═══════════════════════════════════════════════════════════════════════════════

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# Convert datetime columns properly
datetime_cols = ["EventDate", "NotificationSentOn", "NotificationSentAt",
                 "RoutedToClinicianOn", "AppreciationSentOn", "LastUpdated"]
for col in datetime_cols:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")

# Convert numeric columns
numeric_cols = ["Adherence Percentage", "Adeherence Percentage", "PDC Percentage",
                "Refill Days", "RiskScore"]
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# Create Spark DataFrame
sdf = spark.createDataFrame(df)

# Write as Delta table (overwrite mode for initial setup)
sdf.write.mode("overwrite").format("delta").saveAsTable(TABLE_NAME)

print(f"\n✅ Successfully wrote {len(df)} rows to Delta table: {TABLE_NAME}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 7: Verify the table
# ═══════════════════════════════════════════════════════════════════════════════

result_df = spark.table(TABLE_NAME)
print(f"Table '{TABLE_NAME}' verification:")
print(f"  Row count: {result_df.count()}")
print(f"  Columns:   {result_df.columns}")
result_df.show(5, truncate=False)

print("\n" + "=" * 60)
print("  ✅ LAKEHOUSE SETUP COMPLETE")
print("  Next: Run 02_run_agent_pipeline.py")
print("=" * 60)
