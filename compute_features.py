# ============================================================
# HOSPITAL READMISSION RISK ANALYSIS
# Script: compute_features.py
# Purpose: Compute LOS, 30-day readmission flags, and
#          risk scores → populate patient_risk_scores table
# Author: Shubham Rajiwade | Portfolio Project | 2026
# ============================================================

import pandas as pd
import mysql.connector
from mysql.connector import Error
from datetime import timedelta

# ============================================================
# CONFIG
# ============================================================
DB_CONFIG = {
    "host":     "127.0.0.1",
    "port":     3306,
    "user":     "root",
    "password": "YOUR_PASSWORD_HERE",
    "database": "readmission_risk"
}

# ============================================================
# RISK SCORE WEIGHTS (total = 100 pts)
# ============================================================
# Age score        → max 20 pts
# LOS score        → max 20 pts
# Comorbidity      → max 20 pts
# ICU stay         → max 15 pts
# Polypharmacy     → max 15 pts
# Abnormal labs    → max 10 pts
# ============================================================
RISK_THRESHOLDS = {
    "high":   70,   # >= 70 → High risk
    "medium": 40,   # 40-69 → Medium risk
                    # < 40  → Low risk
}

# ============================================================
# HELPERS
# ============================================================
def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

def run_query(conn, sql, params=None):
    """Run a SELECT query and return a DataFrame."""
    return pd.read_sql(sql, conn, params=params)

def execute(conn, sql, params=None):
    """Run an INSERT/UPDATE query."""
    cursor = conn.cursor()
    cursor.execute(sql, params or [])
    conn.commit()
    cursor.close()

def executemany(conn, sql, rows):
    """Run a bulk INSERT/UPDATE."""
    cursor = conn.cursor()
    cursor.executemany(sql, rows)
    conn.commit()
    cursor.close()

# ============================================================
# STEP 1: Compute LOS and 30-day readmission flag
# ============================================================
def compute_admissions_features(conn):
    print("\n--- STEP 1: Computing LOS and 30-day readmission flags ---")

    df = run_query(conn, """
        SELECT hadm_id, subject_id, admittime, dischtime
        FROM admissions
        ORDER BY subject_id, admittime
    """)

    df["admittime"] = pd.to_datetime(df["admittime"])
    df["dischtime"] = pd.to_datetime(df["dischtime"])

    # LOS in days
    df["los_days"] = (df["dischtime"] - df["admittime"]).dt.total_seconds() / 86400
    df["los_days"] = df["los_days"].round(2)

    # 30-day readmission flag
    # For each admission, check if the SAME patient has another admission
    # within 30 days after discharge
    df = df.sort_values(["subject_id", "admittime"]).reset_index(drop=True)
    df["readmitted_30d"] = 0
    df["days_to_readmit"] = None

    for i, row in df.iterrows():
        future = df[
            (df["subject_id"] == row["subject_id"]) &
            (df["admittime"]  >  row["dischtime"]) &
            (df["admittime"]  <= row["dischtime"] + timedelta(days=30))
        ]
        if not future.empty:
            df.at[i, "readmitted_30d"]  = 1
            next_admit = future["admittime"].min()
            df.at[i, "days_to_readmit"] = (next_admit - row["dischtime"]).days

    # Update admissions table
    rows = [
        (row["los_days"], int(row["readmitted_30d"]),
         row["days_to_readmit"], int(row["hadm_id"]))
        for _, row in df.iterrows()
    ]
    executemany(conn, """
        UPDATE admissions
        SET los_days = %s, readmitted_30d = %s, days_to_readmit = %s
        WHERE hadm_id = %s
    """, rows)

    total      = len(df)
    readmitted = df["readmitted_30d"].sum()
    print(f"  Total admissions:       {total}")
    print(f"  30-day readmissions:    {readmitted} ({readmitted/total*100:.1f}%)")
    print(f"  Avg LOS:                {df['los_days'].mean():.1f} days")
    return df

# ============================================================
# STEP 2: Compute comorbidity count per admission
# ============================================================
def compute_comorbidities(conn):
    print("\n--- STEP 2: Computing comorbidity counts ---")

    df = run_query(conn, """
        SELECT hadm_id, COUNT(DISTINCT icd_code) AS comorbidity_count
        FROM diagnoses_icd
        GROUP BY hadm_id
    """)
    print(f"  Admissions with diagnoses: {len(df)}")
    print(f"  Avg comorbidities:         {df['comorbidity_count'].mean():.1f}")
    return df

# ============================================================
# STEP 3: Compute polypharmacy flag per admission
# ============================================================
def compute_polypharmacy(conn):
    print("\n--- STEP 3: Computing polypharmacy flags ---")

    df = run_query(conn, """
        SELECT hadm_id, COUNT(DISTINCT drug) AS drug_count
        FROM prescriptions
        WHERE drug IS NOT NULL
        GROUP BY hadm_id
    """)
    df["polypharmacy"] = (df["drug_count"] >= 5).astype(int)
    flagged = df["polypharmacy"].sum()
    print(f"  Admissions with 5+ drugs:  {flagged} ({flagged/len(df)*100:.1f}%)")
    return df

# ============================================================
# STEP 4: Compute abnormal lab flag per admission
# ============================================================
def compute_abnormal_labs(conn):
    print("\n--- STEP 4: Computing abnormal lab flags ---")

    df = run_query(conn, """
        SELECT hadm_id,
               COUNT(*) AS total_labs,
               SUM(CASE WHEN flag = 'abnormal' THEN 1 ELSE 0 END) AS abnormal_count
        FROM labevents
        WHERE hadm_id IS NOT NULL
        GROUP BY hadm_id
    """)
    df["abnormal_ratio"] = df["abnormal_count"] / df["total_labs"]
    df["has_abnormal_labs"] = (df["abnormal_count"] > 0).astype(int)
    flagged = df["has_abnormal_labs"].sum()
    print(f"  Admissions with abnormal labs: {flagged} ({flagged/len(df)*100:.1f}%)")
    return df

# ============================================================
# STEP 5: Compute ICU flag per admission
# ============================================================
def compute_icu_flag(conn):
    print("\n--- STEP 5: Computing ICU flags ---")

    df = run_query(conn, """
        SELECT hadm_id,
               MAX(los) AS icu_los
        FROM icustays
        GROUP BY hadm_id
    """)
    df["had_icu_stay"] = 1
    print(f"  Admissions with ICU stay: {len(df)}")
    return df

# ============================================================
# STEP 6: Score each admission and assign risk tier
# ============================================================
def score_admission(row):
    score = 0

    # Age score (max 20)
    age = row.get("anchor_age", 0)
    if age >= 80:   score += 20
    elif age >= 70: score += 15
    elif age >= 60: score += 10
    elif age >= 50: score += 5

    # LOS score (max 20)
    los = row.get("los_days", 0)
    if los >= 14:   score += 20
    elif los >= 7:  score += 15
    elif los >= 3:  score += 8
    else:           score += 2

    # Comorbidity score (max 20)
    cc = row.get("comorbidity_count", 0)
    if cc >= 15:    score += 20
    elif cc >= 10:  score += 15
    elif cc >= 5:   score += 10
    elif cc >= 2:   score += 5

    # ICU score (max 15)
    if row.get("had_icu_stay", 0) == 1:
        icu_los = row.get("icu_los", 0)
        if icu_los >= 7:    score += 15
        elif icu_los >= 3:  score += 10
        else:               score += 5

    # Polypharmacy score (max 15)
    if row.get("polypharmacy", 0) == 1:
        drug_count = row.get("drug_count", 0)
        if drug_count >= 20:    score += 15
        elif drug_count >= 10:  score += 10
        else:                   score += 5

    # Abnormal labs score (max 10)
    if row.get("has_abnormal_labs", 0) == 1:
        ratio = row.get("abnormal_ratio", 0)
        if ratio >= 0.3:    score += 10
        elif ratio >= 0.1:  score += 6
        else:               score += 3

    # Cap at 100
    score = min(score, 100)

    # Tier
    if score >= RISK_THRESHOLDS["high"]:
        tier = "High"
    elif score >= RISK_THRESHOLDS["medium"]:
        tier = "Medium"
    else:
        tier = "Low"

    return score, tier

# ============================================================
# STEP 7: Assemble and insert into patient_risk_scores
# ============================================================
def build_risk_scores(conn, adm_df, comorbidity_df, poly_df, lab_df, icu_df):
    print("\n--- STEP 6: Building risk scores ---")

    # Start with admissions + patient age
    patients_df = run_query(conn, "SELECT subject_id, anchor_age FROM patients")
    df = adm_df[["hadm_id", "subject_id", "los_days"]].copy()
    df = df.merge(patients_df,     on="subject_id",  how="left")
    df = df.merge(comorbidity_df,  on="hadm_id",     how="left")
    df = df.merge(poly_df,         on="hadm_id",     how="left")
    df = df.merge(lab_df,          on="hadm_id",     how="left")
    df = df.merge(icu_df,          on="hadm_id",     how="left")

    # Fill missing values with 0
    df = df.fillna(0)

    # Score every admission
    scores = []
    for _, row in df.iterrows():
        total, tier = score_admission(row)

        # Individual component scores
        age = row.get("anchor_age", 0)
        age_score = 20 if age>=80 else 15 if age>=70 else 10 if age>=60 else 5 if age>=50 else 0

        los = row.get("los_days", 0)
        los_score = 20 if los>=14 else 15 if los>=7 else 8 if los>=3 else 2

        cc = row.get("comorbidity_count", 0)
        cc_score = 20 if cc>=15 else 15 if cc>=10 else 10 if cc>=5 else 5 if cc>=2 else 0

        icu_s = 0
        if row.get("had_icu_stay", 0) == 1:
            il = row.get("icu_los", 0)
            icu_s = 15 if il>=7 else 10 if il>=3 else 5

        poly_s = 0
        if row.get("polypharmacy", 0) == 1:
            dc = row.get("drug_count", 0)
            poly_s = 15 if dc>=20 else 10 if dc>=10 else 5

        lab_s = 0
        if row.get("has_abnormal_labs", 0) == 1:
            r = row.get("abnormal_ratio", 0)
            lab_s = 10 if r>=0.3 else 6 if r>=0.1 else 3

        scores.append((
            int(row["hadm_id"]),
            int(row["subject_id"]),
            age_score, los_score, cc_score,
            icu_s, poly_s, lab_s,
            total, tier
        ))

    # Insert into patient_risk_scores
    executemany(conn, """
        INSERT INTO patient_risk_scores
            (hadm_id, subject_id,
             age_score, los_score, comorbidity_score,
             icu_score, polypharmacy_score, abnormal_labs_score,
             total_risk_score, risk_tier)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            total_risk_score = VALUES(total_risk_score),
            risk_tier        = VALUES(risk_tier)
    """, scores)

    # Summary
    score_df = pd.DataFrame(scores, columns=[
        "hadm_id","subject_id","age_score","los_score","comorbidity_score",
        "icu_score","polypharmacy_score","abnormal_labs_score",
        "total_risk_score","risk_tier"
    ])
    print(f"\n  Admissions scored: {len(score_df)}")
    print(f"  High risk:         {(score_df['risk_tier']=='High').sum()}")
    print(f"  Medium risk:       {(score_df['risk_tier']=='Medium').sum()}")
    print(f"  Low risk:          {(score_df['risk_tier']=='Low').sum()}")
    print(f"  Avg risk score:    {score_df['total_risk_score'].mean():.1f}")
    return score_df

# ============================================================
# MAIN
# ============================================================
def main():
    print("Connecting to MySQL...")
    try:
        conn = get_connection()
        print("Connected successfully.")
    except Error as e:
        print(f"Connection failed: {e}")
        return

    adm_df  = compute_admissions_features(conn)
    cc_df   = compute_comorbidities(conn)
    poly_df = compute_polypharmacy(conn)
    lab_df  = compute_abnormal_labs(conn)
    icu_df  = compute_icu_flag(conn)
    scores  = build_risk_scores(conn, adm_df, cc_df, poly_df, lab_df, icu_df)

    conn.close()
    print("\n" + "="*50)
    print("compute_features.py complete!")
    print("patient_risk_scores table is ready for Tableau.")
    print("Next step: run exploratory_analysis.py for EDA.")

if __name__ == "__main__":
    main()