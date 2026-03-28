# ============================================================
# HOSPITAL READMISSION RISK ANALYSIS
# Script: load_data.py
# Purpose: Load MIMIC-IV demo CSV files into MySQL
# Author: Shubham Rajiwade | Portfolio Project | 2026
# ============================================================

import pandas as pd
import mysql.connector
from mysql.connector import Error
import os

# ============================================================
# CONFIG — update these paths to where your CSVs are
# ============================================================
DB_CONFIG = {
    "host":     "127.0.0.1",
    "port":     3306,
    "user":     "root",
    "password": "password",   # replace with your MySQL root password
    "database": "readmission_risk"
}

# Folder where your MIMIC-IV demo CSV files live
# e.g. "/Users/shubham/Downloads/mimic-iv-clinical-database-demo-2.2"
MIMIC_BASE = "/Users/shubhamrajiwade/Downloads/DATA projects/readmission_risk/mimic-iv-clinical-database-demo-2.2"


# Map: MySQL table name → relative path to CSV inside MIMIC folder
CSV_MAP = {
    "patients":       "hosp/patients.csv.gz",
    "admissions":     "hosp/admissions.csv.gz",
    "diagnoses_icd":  "hosp/diagnoses_icd.csv.gz",
    "procedures_icd": "hosp/procedures_icd.csv.gz",
    "labevents":      "hosp/labevents.csv.gz",
    "prescriptions":  "hosp/prescriptions.csv.gz",
    "icustays":       "icu/icustays.csv.gz",
}

# Load order matters — parent tables must load before child tables
LOAD_ORDER = [
    "patients",
    "admissions",
    "diagnoses_icd",
    "procedures_icd",
    "labevents",
    "prescriptions",
    "icustays",
]

# ============================================================
# COLUMN MAPPING
# MIMIC-IV CSV columns → your MySQL table columns
# Only keeps columns your schema actually needs
# ============================================================
COLUMN_MAP = {
    "patients": [
        "subject_id", "gender", "anchor_age",
        "anchor_year", "anchor_year_group", "dod"
    ],
    "admissions": [
        "hadm_id", "subject_id", "admittime", "dischtime",
        "deathtime", "admission_type", "admit_provider_id",
        "admission_location", "discharge_location", "insurance",
        "language", "marital_status", "race",
        "edregtime", "edouttime", "hospital_expire_flag"
    ],
    "diagnoses_icd": [
        "hadm_id", "subject_id", "seq_num", "icd_code", "icd_version"
    ],
    "procedures_icd": [
        "hadm_id", "subject_id", "seq_num", "icd_code", "icd_version", "chartdate"
    ],
    "labevents": [
        "labevent_id", "subject_id", "hadm_id", "itemid",
        "charttime", "storetime", "value", "valuenum",
        "valueuom", "ref_range_lower", "ref_range_upper",
        "flag", "priority", "comments"
    ],
    "prescriptions": [
        "pharmacy_id", "subject_id", "hadm_id", "starttime",
        "stoptime", "drug_type", "drug", "formulary_drug_cd",
        "gsn", "ndc", "prod_strength", "form_rx",
        "dose_val_rx", "dose_unit_rx", "route"
    ],
    "icustays": [
        "stay_id", "subject_id", "hadm_id",
        "first_careunit", "last_careunit",
        "intime", "outtime", "los"
    ],
}

# Rename MIMIC column → your schema column where names differ
RENAME_MAP = {
    "patients": {"anchor_year_group": "anchor_year_grp"},
}

# ============================================================
# HELPERS
# ============================================================
def get_connection():
    conn = mysql.connector.connect(**DB_CONFIG)
    return conn

def load_table(conn, table_name, csv_path):
    print(f"\n{'='*50}")
    print(f"Loading: {table_name}")
    print(f"File:    {csv_path}")

    if not os.path.exists(csv_path):
        print(f"  ERROR: File not found — {csv_path}")
        return

    # Read CSV
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"  Rows in CSV: {len(df):,}")

    # Keep only columns your schema needs
    cols = COLUMN_MAP[table_name]
    existing = [c for c in cols if c in df.columns]
    missing  = [c for c in cols if c not in df.columns]
    if missing:
        print(f"  Warning: columns not found in CSV: {missing}")
    df = df[existing]

    # Rename columns if needed
    if table_name in RENAME_MAP:
        df = df.rename(columns=RENAME_MAP[table_name])

    # Replace NaN/NaT with None so MySQL gets NULL
    df = df.where(pd.notnull(df), None)
    df = df.astype(object).where(pd.notnull(df), None)

    # Build INSERT query
    col_str         = ", ".join(df.columns)
    placeholder_str = ", ".join(["%s"] * len(df.columns))
    sql = f"INSERT IGNORE INTO {table_name} ({col_str}) VALUES ({placeholder_str})"

    # Insert in batches of 1000 rows
    cursor    = conn.cursor()
    rows      = [tuple(r) for r in df.itertuples(index=False)]
    batch_sz  = 1000
    inserted  = 0

    for i in range(0, len(rows), batch_sz):
        batch = rows[i : i + batch_sz]
        cursor.executemany(sql, batch)
        conn.commit()
        inserted += len(batch)
        print(f"  Inserted {inserted:,} / {len(rows):,} rows...", end="\r")

    cursor.close()
    print(f"\n  Done — {inserted:,} rows loaded into '{table_name}'")

# ============================================================
# MAIN
# ============================================================
def main():
    print("Connecting to MySQL...")
    try:
        conn = get_connection()
        print("Connected successfully.\n")
    except Error as e:
        print(f"Connection failed: {e}")
        return

    for table in LOAD_ORDER:
        csv_path = os.path.join(MIMIC_BASE, CSV_MAP[table])
        load_table(conn, table, csv_path)

    conn.close()
    print("\n" + "="*50)
    print("All tables loaded successfully!")
    print("Next step: run compute_features.py to calculate")
    print("LOS, 30-day readmission flags, and risk scores.")

if __name__ == "__main__":
    main()