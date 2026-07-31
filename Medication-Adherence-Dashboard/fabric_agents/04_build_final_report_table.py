"""
═══════════════════════════════════════════════════════════════════════════════
  NOTEBOOK 4: Build Final Report Table for Power BI
═══════════════════════════════════════════════════════════════════════════════

STEPS TO RUN IN FABRIC:
  1. Create a new Fabric Notebook
  2. Attach it to your Lakehouse
  3. Copy-paste each cell below into separate notebook cells
  4. Ensure 02_run_agent_pipeline.py has been run first
  5. Run all cells

This notebook:
  - Reads `patients_with_agents` table
  - De-duplicates to one row per patient (latest state)
  - Adds computed columns: IsHighRisk, NotifiedToday, AdherenceGroup
  - Writes clean `patients_final_report` Delta table — the ONLY table
    that Power BI connects to
═══════════════════════════════════════════════════════════════════════════════
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 1: Imports and Spark session
# ═══════════════════════════════════════════════════════════════════════════════

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window
import pandas as pd

spark = SparkSession.builder.getOrCreate()

AGENTS_TABLE = "patients_with_agents"
FINAL_TABLE = "patients_final_report"

print(f"Source table: {AGENTS_TABLE}")
print(f"Target table: {FINAL_TABLE}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 2: Load agents table
# ═══════════════════════════════════════════════════════════════════════════════

agents_df = spark.table(AGENTS_TABLE)
total_rows = agents_df.count()
total_cols = len(agents_df.columns)
print(f"Loaded {total_rows} rows, {total_cols} columns from {AGENTS_TABLE}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 3: De-duplicate — one row per patient (latest agent run)
# ═══════════════════════════════════════════════════════════════════════════════

# Window: partition by Member_ID, order by agent_run_timestamp desc
window = Window.partitionBy("Member_ID").orderBy(F.col("agent_run_timestamp").desc())

# Add row number and keep only the latest row per patient
deduped_df = agents_df.withColumn("_row_num", F.row_number().over(window)) \
    .filter(F.col("_row_num") == 1) \
    .drop("_row_num")

deduped_count = deduped_df.count()
print(f"After de-duplication: {deduped_count} unique patients (from {total_rows} rows)")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 4: Add computed columns for Power BI
# ═══════════════════════════════════════════════════════════════════════════════

today = pd.Timestamp.now().normalize()
today_str = today.strftime("%Y-%m-%d")

report_df = deduped_df

# IsHighRisk: boolean flag for easy KPI filtering
report_df = report_df.withColumn(
    "IsHighRisk",
    F.col("risk_label") == "High"
)

# IsMediumRisk: boolean flag
report_df = report_df.withColumn(
    "IsMediumRisk",
    F.col("risk_label") == "Medium"
)

# IsLowRisk: boolean flag
report_df = report_df.withColumn(
    "IsLowRisk",
    F.col("risk_label") == "Low"
)

# AdherenceGroup: categorical (Low < 50, Medium 50-80, High >= 80)
report_df = report_df.withColumn(
    "AdherenceGroup",
    F.when(F.col("Adherence_Percentage") < 50, "Low")
     .when(F.col("Adherence_Percentage") < 80, "Medium")
     .otherwise("High")
)

# NotifiedToday: boolean — was this patient notified today?
report_df = report_df.withColumn(
    "NotifiedToday",
    F.when(
        F.col("NotificationSentOn").isNotNull() &
        (F.date_format(F.col("NotificationSentOn"), "yyyy-MM-dd") == today_str),
        True
    ).otherwise(False)
)

# EscalatedToClinician: boolean
report_df = report_df.withColumn(
    "EscalatedToClinician",
    F.col("should_route") == True
)

# RefillOverdue: boolean (days_until_refill <= 0)
report_df = report_df.withColumn(
    "RefillOverdue",
    F.when(F.col("days_until_refill").isNotNull() & (F.col("days_until_refill") <= 0), True)
     .otherwise(False)
)

# RefillUrgent: boolean (days_until_refill <= 3)
report_df = report_df.withColumn(
    "RefillUrgent",
    F.when(F.col("days_until_refill").isNotNull() & (F.col("days_until_refill") <= 3), True)
     .otherwise(False)
)

# NotificationSuccessful: boolean
report_df = report_df.withColumn(
    "NotificationSuccessful",
    F.col("notification_status").contains("Sent")
)

# report_date: when this report was generated
report_df = report_df.withColumn(
    "report_date",
    F.current_timestamp()
)

print("✅ Added computed columns: IsHighRisk, IsMediumRisk, IsLowRisk, AdherenceGroup,")
print("   NotifiedToday, EscalatedToClinician, RefillOverdue, RefillUrgent,")
print("   NotificationSuccessful, report_date")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 5: Select final columns for Power BI
# ═══════════════════════════════════════════════════════════════════════════════

# Select the most useful columns for Power BI reporting
final_columns = [
    # Patient identity
    "Member_ID",
    "Patient_Name",
    "City",
    "Medication_Name",
    "Patient_Contact",
    "Patient_EmailID",

    # Adherence metrics
    "Adherence_Percentage",
    "AdherenceGroup",
    "days_until_refill",
    "refill_due",
    "RefillOverdue",
    "RefillUrgent",

    # Risk assessment
    "risk_score",
    "risk_label",
    "IsHighRisk",
    "IsMediumRisk",
    "IsLowRisk",
    "risk_signals",
    "risk_confidence",

    # Sentiment & behavior
    "sentiment_score",
    "sentiment_label",
    "behavior_pattern",

    # Care routing
    "should_route",
    "EscalatedToClinician",
    "routing_level",
    "routing_reason",
    "routing_urgency",
    "care_priority",
    "care_summary",

    # Notification info
    "route_channel",
    "notification_status",
    "notification_channel_used",
    "NotificationSuccessful",
    "NotifiedToday",
    "NotificationSentOn",
    "AppreciationSentOn",

    # Metadata
    "agent_run_timestamp",
    "report_date",
]

# Only select columns that exist
existing_cols = [c for c in final_columns if c in report_df.columns]
missing_cols = [c for c in final_columns if c not in report_df.columns]

if missing_cols:
    print(f"Note: {len(missing_cols)} columns not found (may not have been populated): {missing_cols}")

final_df = report_df.select(*existing_cols)

print(f"\nFinal report table: {final_df.count()} rows, {len(existing_cols)} columns")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 6: Write final report table to Lakehouse
# ═══════════════════════════════════════════════════════════════════════════════

final_df.write.mode("overwrite").format("delta").saveAsTable(FINAL_TABLE)

print(f"\n✅ Successfully wrote {final_df.count()} rows to: {FINAL_TABLE}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 7: Verify and show summary statistics
# ═══════════════════════════════════════════════════════════════════════════════

result = spark.table(FINAL_TABLE)

print("=" * 60)
print("  FINAL REPORT TABLE SUMMARY")
print("=" * 60)
print(f"  Table:               {FINAL_TABLE}")
print(f"  Total patients:      {result.count()}")

# Risk distribution
risk_dist = result.groupBy("risk_label").count().orderBy("risk_label").toPandas()
print(f"\n  Risk Distribution:")
for _, r in risk_dist.iterrows():
    print(f"    {r['risk_label']:10s}: {r['count']}")

# Adherence group distribution
adh_dist = result.groupBy("AdherenceGroup").count().orderBy("AdherenceGroup").toPandas()
print(f"\n  Adherence Distribution:")
for _, r in adh_dist.iterrows():
    print(f"    {r['AdherenceGroup']:10s}: {r['count']}")

# Notification stats
notif_dist = result.groupBy("notification_status").count().orderBy("count", ascending=False).toPandas()
print(f"\n  Notification Status:")
for _, r in notif_dist.iterrows():
    status = r["notification_status"] or "(none)"
    print(f"    {status:20s}: {r['count']}")

# High risk count
hr = result.filter("IsHighRisk = true").count()
print(f"\n  High-risk patients:  {hr}")

# Average adherence
avg_adh = result.select(F.avg("Adherence_Percentage")).first()[0]
print(f"  Avg adherence %:     {avg_adh:.1f}%")

# Escalated
esc = result.filter("EscalatedToClinician = true").count()
print(f"  Escalated:           {esc}")

print("=" * 60)
print(f"\n  🎯 Power BI: Connect to table '{FINAL_TABLE}' in your Lakehouse")
print(f"  See powerbi_setup.md for step-by-step instructions")
print("=" * 60)

# Show sample rows
print("\nSample rows (first 5):")
result.select(
    "Member_ID", "Patient_Name", "Adherence_Percentage",
    "risk_label", "AdherenceGroup", "notification_status", "EscalatedToClinician"
).show(5, truncate=False)
