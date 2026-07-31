"""Fabric Lakehouse Agent Pipeline

Usage:
  - Run in Fabric Notebook or local env with Spark configured.
  - Loads source table `patients` from Lakehouse, runs agent pipeline, writes target table.

Outputs:
  - Target table: `patients_with_agents` (or configured custom name).

Pre-req:
  - Set up Fabric Lakehouse catalog and table `patients`.
  - Install required packages (pandas, openai, etc.) for your agent functions.
"""

from __future__ import annotations
import os
import pandas as pd
from typing import Any, Dict

# Use your local project code for agent logic
from agent import (
    validate_and_normalize_row,
    assess_adherence_risk,
    determine_contact_route,
    enforce_policy_and_throttle,
    determine_care_routing,
    analyze_patient_sentiment_and_behavior,
    identify_patient_care_needs,
)


def map_row_to_agent_output(row: Dict[str, Any]) -> Dict[str, Any]:
    """Run a subset of agent steps for the row and return enriched output."""
    base = validate_and_normalize_row(row)
    clean = base.get("clean", {})

    risk = assess_adherence_risk(clean)
    sentiment = analyze_patient_sentiment_and_behavior(clean)
    care_needs = identify_patient_care_needs(clean, risk_assessment=risk, sentiment_analysis=sentiment)
    care_routing = determine_care_routing(clean, risk_assessment=risk)
    route = determine_contact_route(clean)
    policy = enforce_policy_and_throttle(clean, policy_context={"today_sent": 0, "cap": 100, "cooldown_days": 2})

    out = {
        "Member ID": clean.get("Member ID"),
        "Patient Name": clean.get("Patient Name"),
        "Medication Name": clean.get("Medication Name"),
        "Adherence Percentage": clean.get("Adherence Percentage"),
        "days_until_refill": clean.get("days_until_refill"),
        "refill_due": clean.get("refill_due"),
        "ConsentOK": clean.get("ConsentOK"),
        "risk_score": risk.get("risk_score"),
        "risk_label": risk.get("risk_label"),
        "risk_signals": "; ".join(risk.get("signals", [])),
        "sentiment_score": sentiment.get("sentiment_score"),
        "sentiment_label": sentiment.get("sentiment_label"),
        "behavior_pattern": sentiment.get("behavior_pattern"),
        "should_route": care_routing.get("needs_routing"),
        "routing_level": care_routing.get("routing_level"),
        "routing_reason": care_routing.get("routing_reason"),
        "route_channel": route.get("channel"),
        "route_allowed": route.get("allowed"),
        "policy_allowed": policy.get("allowed"),
        "policy_reasons": "; ".join(policy.get("reasons", [])),
        "care_priority": care_needs.get("priority"),
        "care_summary": care_needs.get("summary", ""),
        "agent_run_ts": pd.Timestamp.now(),
    }
    return out


def run_agents_on_patients_table(
    source_table="patients",
    target_table="patients_with_agents",
    database="default",
    write_mode="overwrite",
):
    """Read patients table from Fabric Lakehouse, run agents, and write a target table."""
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()

    # Use correct default catalog or database as needed in Fabric
    # If your Lakehouse uses catalog/database names, set those in the SQL call.
    source_full_name = f"{database}.{source_table}" if database else source_table

    print(f"Loading source table: {source_full_name}")
    df = spark.table(source_full_name)
    print(f"Rows loaded: {df.count()}")

    pdf = df.toPandas()
    agent_rows = []

    for i, row in pdf.iterrows():
        row_dict = row.to_dict()
        out = map_row_to_agent_output(row_dict)
        agent_rows.append(out)

    target_pdf = pd.DataFrame(agent_rows)

    print("Agent transformation complete. Writing target table...")
    target_sdf = spark.createDataFrame(target_pdf)
    target_full_name = f"{database}.{target_table}" if database else target_table

    target_sdf.write.mode(write_mode).saveAsTable(target_full_name)
    print(f"Wrote target table: {target_full_name}")

    return target_sdf


if __name__ == "__main__":
    # Entry point for one-time script run.
    # Update names if your table uses a different database/schema.
    run_agents_on_patients_table(source_table="patients", target_table="patients_with_agents", database="default")
