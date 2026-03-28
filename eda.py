# ============================================================
# HOSPITAL READMISSION RISK ANALYSIS
# Script: eda.py
# Purpose: Exploratory Data Analysis — understand the data
#          before building SQL queries and Tableau dashboard
# Author: Shubham Rajiwade | Portfolio Project | 2025
# ============================================================

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
import mysql.connector
import os

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

OUTPUT_DIR = "./eda_outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Clean plot style
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams["figure.dpi"] = 150

# ============================================================
# HELPERS
# ============================================================
def get_conn():
    return mysql.connector.connect(**DB_CONFIG)

def query(conn, sql):
    return pd.read_sql(sql, conn)

def save(fig, name):
    path = f"{OUTPUT_DIR}/{name}.png"
    fig.savefig(path, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close(fig)

# ============================================================
# 1. PATIENT DEMOGRAPHICS
# ============================================================
def eda_demographics(conn):
    print("\n[1] Patient Demographics")
    df = query(conn, """
        SELECT p.subject_id, p.gender, p.anchor_age,
               p.anchor_year_grp, p.dod,
               COUNT(a.hadm_id) as admission_count
        FROM patients p
        LEFT JOIN admissions a ON p.subject_id = a.subject_id
        GROUP BY p.subject_id, p.gender, p.anchor_age,
                 p.anchor_year_grp, p.dod
    """)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    fig.suptitle("Patient Demographics", fontsize=14, fontweight="bold")

    # Age distribution
    axes[0].hist(df["anchor_age"], bins=15, color="#4C9BE8", edgecolor="white")
    axes[0].set_title("Age distribution")
    axes[0].set_xlabel("Age")
    axes[0].set_ylabel("Patient count")

    # Gender split
    gender_counts = df["gender"].value_counts()
    axes[1].pie(gender_counts, labels=["Male","Female"],
                autopct="%1.1f%%", colors=["#4C9BE8","#F28B82"],
                startangle=90)
    axes[1].set_title("Gender split")

    # Admissions per patient
    axes[2].hist(df["admission_count"], bins=10,
                 color="#81C995", edgecolor="white")
    axes[2].set_title("Admissions per patient")
    axes[2].set_xlabel("Number of admissions")
    axes[2].set_ylabel("Patient count")

    plt.tight_layout()
    save(fig, "1_demographics")

    print(f"  Patients:          {len(df)}")
    print(f"  Age range:         {df['anchor_age'].min()}–{df['anchor_age'].max()}")
    print(f"  Avg age:           {df['anchor_age'].mean():.1f}")
    print(f"  Gender (M/F):      {gender_counts.get('M',0)} / {gender_counts.get('F',0)}")
    print(f"  Avg admissions:    {df['admission_count'].mean():.1f}")
    print(f"  Max admissions:    {df['admission_count'].max()}")

# ============================================================
# 2. ADMISSIONS OVERVIEW
# ============================================================
def eda_admissions(conn):
    print("\n[2] Admissions Overview")
    df = query(conn, """
        SELECT hadm_id, admission_type, insurance,
               discharge_location, los_days,
               readmitted_30d, days_to_readmit,
               hospital_expire_flag
        FROM admissions
    """)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Admissions Overview", fontsize=14, fontweight="bold")

    # Admission type
    at = df["admission_type"].value_counts()
    axes[0,0].barh(at.index, at.values, color="#4C9BE8")
    axes[0,0].set_title("Admission type")
    axes[0,0].set_xlabel("Count")

    # Insurance type
    ins = df["insurance"].value_counts()
    axes[0,1].bar(ins.index, ins.values, color="#F9AB00", edgecolor="white")
    axes[0,1].set_title("Insurance type")
    axes[0,1].set_xlabel("Insurance")
    axes[0,1].set_ylabel("Count")
    axes[0,1].tick_params(axis="x", rotation=20)

    # LOS distribution
    axes[1,0].hist(df["los_days"].dropna(), bins=20,
                   color="#81C995", edgecolor="white")
    axes[1,0].axvline(df["los_days"].mean(), color="red",
                      linestyle="--", label=f"Mean: {df['los_days'].mean():.1f}d")
    axes[1,0].set_title("Length of stay distribution")
    axes[1,0].set_xlabel("Days")
    axes[1,0].legend()

    # Discharge location (top 6)
    dl = df["discharge_location"].value_counts().head(6)
    axes[1,1].barh(dl.index, dl.values, color="#CE93D8")
    axes[1,1].set_title("Discharge location (top 6)")
    axes[1,1].set_xlabel("Count")

    plt.tight_layout()
    save(fig, "2_admissions")

    readmit_rate = df["readmitted_30d"].mean() * 100
    print(f"  Total admissions:      {len(df)}")
    print(f"  30-day readmit rate:   {readmit_rate:.1f}%")
    print(f"  Avg LOS:               {df['los_days'].mean():.1f} days")
    print(f"  In-hospital deaths:    {df['hospital_expire_flag'].sum()}")
    print(f"  Avg days to readmit:   {df['days_to_readmit'].mean():.1f} days")

# ============================================================
# 3. READMISSION ANALYSIS
# ============================================================
def eda_readmissions(conn):
    print("\n[3] Readmission Analysis")
    df = query(conn, """
        SELECT a.hadm_id, a.admission_type, a.insurance,
               a.los_days, a.readmitted_30d,
               p.anchor_age, p.gender,
               r.total_risk_score, r.risk_tier
        FROM admissions a
        JOIN patients p      ON a.subject_id = p.subject_id
        JOIN patient_risk_scores r ON a.hadm_id = r.hadm_id
    """)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Readmission Analysis", fontsize=14, fontweight="bold")

    # Readmission rate by insurance
    ins_rate = df.groupby("insurance")["readmitted_30d"].mean().sort_values(ascending=False) * 100
    axes[0,0].bar(ins_rate.index, ins_rate.values,
                  color=["#E57373","#FFB74D","#81C995","#64B5F6"])
    axes[0,0].set_title("30-day readmission rate by insurance")
    axes[0,0].set_ylabel("Readmission rate (%)")
    axes[0,0].tick_params(axis="x", rotation=20)
    axes[0,0].axhline(19.3, color="gray", linestyle="--", label="Overall avg")
    axes[0,0].legend()

    # Readmission rate by admission type
    at_rate = df.groupby("admission_type")["readmitted_30d"].mean().sort_values(ascending=False) * 100
    axes[0,1].bar(at_rate.index, at_rate.values, color="#4C9BE8")
    axes[0,1].set_title("Readmission rate by admission type")
    axes[0,1].set_ylabel("Readmission rate (%)")
    axes[0,1].tick_params(axis="x", rotation=20)

    # Age vs risk score scatter
    colors = df["readmitted_30d"].map({0: "#81C995", 1: "#E57373"})
    axes[1,0].scatter(df["anchor_age"], df["total_risk_score"],
                      c=colors, alpha=0.6, s=40)
    axes[1,0].set_title("Age vs risk score\n(red = readmitted)")
    axes[1,0].set_xlabel("Age")
    axes[1,0].set_ylabel("Risk score")

    # LOS vs risk score scatter
    axes[1,1].scatter(df["los_days"], df["total_risk_score"],
                      c=colors, alpha=0.6, s=40)
    axes[1,1].set_title("LOS vs risk score\n(red = readmitted)")
    axes[1,1].set_xlabel("Length of stay (days)")
    axes[1,1].set_ylabel("Risk score")

    plt.tight_layout()
    save(fig, "3_readmissions")

# ============================================================
# 4. RISK SCORE DISTRIBUTION
# ============================================================
def eda_risk_scores(conn):
    print("\n[4] Risk Score Distribution")
    df = query(conn, """
        SELECT r.total_risk_score, r.risk_tier,
               r.age_score, r.los_score, r.comorbidity_score,
               r.icu_score, r.polypharmacy_score, r.abnormal_labs_score,
               a.readmitted_30d
        FROM patient_risk_scores r
        JOIN admissions a ON r.hadm_id = a.hadm_id
    """)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Risk Score Analysis", fontsize=14, fontweight="bold")

    # Risk score histogram
    colors_map = {"High": "#E57373", "Medium": "#FFB74D", "Low": "#81C995"}
    for tier, grp in df.groupby("risk_tier"):
        axes[0].hist(grp["total_risk_score"], bins=12, alpha=0.7,
                     label=tier, color=colors_map.get(tier, "gray"))
    axes[0].set_title("Risk score distribution by tier")
    axes[0].set_xlabel("Risk score")
    axes[0].set_ylabel("Count")
    axes[0].legend()

    # Risk tier counts
    tier_counts = df["risk_tier"].value_counts().reindex(["High","Medium","Low"])
    bar_colors  = [colors_map[t] for t in tier_counts.index]
    axes[1].bar(tier_counts.index, tier_counts.values, color=bar_colors)
    axes[1].set_title("Patients by risk tier")
    axes[1].set_ylabel("Count")
    for i, v in enumerate(tier_counts.values):
        axes[1].text(i, v + 1, str(v), ha="center", fontsize=11)

    # Score component breakdown (avg per tier)
    components = ["age_score","los_score","comorbidity_score",
                  "icu_score","polypharmacy_score","abnormal_labs_score"]
    comp_avg = df.groupby("risk_tier")[components].mean().reindex(["High","Medium","Low"])
    comp_avg.T.plot(kind="bar", ax=axes[2],
                    color=["#E57373","#FFB74D","#81C995"], width=0.7)
    axes[2].set_title("Avg score components by tier")
    axes[2].set_ylabel("Avg score")
    axes[2].tick_params(axis="x", rotation=30)
    axes[2].legend(title="Tier")

    plt.tight_layout()
    save(fig, "4_risk_scores")

    print(f"  High risk:    {(df['risk_tier']=='High').sum()} admissions")
    print(f"  Medium risk:  {(df['risk_tier']=='Medium').sum()} admissions")
    print(f"  Low risk:     {(df['risk_tier']=='Low').sum()} admissions")
    print(f"  Avg score (High):   {df[df['risk_tier']=='High']['total_risk_score'].mean():.1f}")
    print(f"  Avg score (Medium): {df[df['risk_tier']=='Medium']['total_risk_score'].mean():.1f}")
    print(f"  Avg score (Low):    {df[df['risk_tier']=='Low']['total_risk_score'].mean():.1f}")

# ============================================================
# 5. TOP DIAGNOSES
# ============================================================
def eda_diagnoses(conn):
    print("\n[5] Top Diagnoses")
    df = query(conn, """
        SELECT d.icd_code, d.icd_version,
               COUNT(DISTINCT d.hadm_id) AS admission_count,
               AVG(a.readmitted_30d) * 100 AS readmit_rate
        FROM diagnoses_icd d
        JOIN admissions a ON d.hadm_id = a.hadm_id
        WHERE d.seq_num = 1
        GROUP BY d.icd_code, d.icd_version
        ORDER BY admission_count DESC
        LIMIT 15
    """)

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    fig.suptitle("Top Primary Diagnoses", fontsize=14, fontweight="bold")

    # Top 15 by frequency
    axes[0].barh(df["icd_code"][::-1], df["admission_count"][::-1], color="#4C9BE8")
    axes[0].set_title("Most frequent primary diagnoses")
    axes[0].set_xlabel("Admission count")

    # Top 15 by readmission rate
    df_sorted = df.sort_values("readmit_rate", ascending=False).head(10)
    axes[1].barh(df_sorted["icd_code"][::-1],
                 df_sorted["readmit_rate"][::-1], color="#E57373")
    axes[1].set_title("Highest readmission rate by diagnosis")
    axes[1].set_xlabel("30-day readmission rate (%)")

    plt.tight_layout()
    save(fig, "5_diagnoses")

    print(f"  Unique primary diagnoses: {df['icd_code'].nunique()}")
    print(f"  Highest readmit rate:     {df['readmit_rate'].max():.1f}% ({df.loc[df['readmit_rate'].idxmax(),'icd_code']})")

# ============================================================
# MAIN
# ============================================================
def main():
    print("Connecting to MySQL...")
    conn = get_conn()
    print("Connected. Running EDA...\n")

    eda_demographics(conn)
    eda_admissions(conn)
    eda_readmissions(conn)
    eda_risk_scores(conn)
    eda_diagnoses(conn)

    conn.close()
    print(f"\n{'='*50}")
    print(f"EDA complete! All charts saved to ./{OUTPUT_DIR}/")
    print("Open the eda_outputs folder to review your charts.")

if __name__ == "__main__":
    main()