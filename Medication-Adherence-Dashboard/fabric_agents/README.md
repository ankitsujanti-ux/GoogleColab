# Fabric Lakehouse Agent Pipeline

This folder contains code to run your existing `agent.py` logic on your Fabric Lakehouse `patients` table and write a target output table for Power BI.

## What it does
1. Reads `patients` from your Lakehouse.
2. Runs agent functions (`validate_and_normalize_row`, `assess_adherence_risk`, etc.) row-by-row.
3. Writes enriched results to `patients_with_agents` table.

## How to run
### In Fabric Notebook
```python
%run /path/to/project/fabric_agents/run_fabric_agents.py
```

or in a Python cell:
```python
from fabric_agents.run_fabric_agents import run_agents_on_patients_table
run_agents_on_patients_table(
    source_table="patients",
    target_table="patients_with_agents",
    database="default",
    write_mode="overwrite"
)
```

### In local environment with Spark configured
```bash
python fabric_agents/run_fabric_agents.py
```

## Configure for your environment
- If your source table is in another schema, update `database` argument.
- Ensure the users table exists in Lakehouse:
  - `CREATE TABLE default.patients ...` if not present.
  - Then run the script.

## Power BI connection
- In Power BI, connect to Fabric Lakehouse and point to table `patients_with_agents`.
- If you need a materialized table in SQL endpoint, create view/table from it in Fabric.
