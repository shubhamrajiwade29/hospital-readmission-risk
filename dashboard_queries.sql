-- ============================================================
-- Dashboard Queries — Hospital Readmission Risk Analysis
-- Powers the Tableau Public dashboard (MIMIC-IV Demo)
-- ============================================================

-- 1. 30-Day Readmission Rate Overall
SELECT
    COUNT(*) AS total_admissions,
    SUM(readmitted_30day) AS total_readmissions,
    ROUND(SUM(readmitted_30day) * 100.0 / COUNT(*), 1) AS readmission_rate_pct
FROM admissions;

-- 2. Readmission Rate by Insurance Type
SELECT
    insurance,
    COUNT(*) AS total_admissions,
    SUM(readmitted_30day) AS readmissions,
    ROUND(SUM(readmitted_30day) * 100.0 / COUNT(*), 1) AS readmission_rate_pct
FROM admissions
GROUP BY insurance
ORDER BY readmission_rate_pct DESC;

-- 3. Readmission Rate by Age Group
SELECT
    CASE
        WHEN p.anchor_age < 40  THEN 'Under 40'
        WHEN p.anchor_age < 50  THEN '40-49'
        WHEN p.anchor_age < 60  THEN '50-59'
        WHEN p.anchor_age < 70  THEN '60-69'
        WHEN p.anchor_age < 80  THEN '70-79'
        ELSE '80+'
    END AS age_group,
    COUNT(*) AS total_admissions,
    SUM(a.readmitted_30day) AS readmissions,
    ROUND(SUM(a.readmitted_30day) * 100.0 / COUNT(*), 1) AS readmission_rate_pct
FROM admissions a
JOIN patients p ON a.subject_id = p.subject_id
GROUP BY age_group
ORDER BY MIN(p.anchor_age);

-- 4. Average Length of Stay — ICU vs Non-ICU
SELECT
    CASE WHEN i.stay_id IS NOT NULL THEN 'ICU' ELSE 'Non-ICU' END AS patient_type,
    ROUND(AVG(a.los_days), 1) AS avg_los_days,
    COUNT(*) AS total_admissions
FROM admissions a
LEFT JOIN icustays i ON a.hadm_id = i.hadm_id
GROUP BY patient_type;

-- 5. Top 10 Diagnoses by Readmission Rate (min 3 cases)
SELECT
    d.icd_code,
    COUNT(DISTINCT a.hadm_id) AS total_cases,
    SUM(a.readmitted_30day) AS readmissions,
    ROUND(SUM(a.readmitted_30day) * 100.0 / COUNT(*), 1) AS readmission_rate_pct
FROM admissions a
JOIN diagnoses_icd d ON a.hadm_id = d.hadm_id
GROUP BY d.icd_code
HAVING total_cases >= 3
ORDER BY readmission_rate_pct DESC
LIMIT 10;

-- 6. Risk Score Distribution (High / Medium / Low)
SELECT
    CASE
        WHEN risk_score >= 70 THEN 'High'
        WHEN risk_score >= 40 THEN 'Medium'
        ELSE 'Low'
    END AS risk_tier,
    COUNT(*) AS patient_count,
    ROUND(AVG(risk_score), 1) AS avg_score
FROM patient_risk_scores
GROUP BY risk_tier
ORDER BY MIN(risk_score) DESC;

-- 7. High-Risk Patients for Follow-Up (score >= 70)
SELECT
    prs.subject_id,
    prs.hadm_id,
    prs.risk_score,
    a.insurance,
    a.los_days,
    a.readmitted_30day
FROM patient_risk_scores prs
JOIN admissions a ON prs.hadm_id = a.hadm_id
WHERE prs.risk_score >= 70
ORDER BY prs.risk_score DESC;

-- 8. Monthly Admission Volume
SELECT
    DATE_FORMAT(admittime, '%Y-%m') AS month,
    COUNT(*) AS admissions
FROM admissions
GROUP BY month
ORDER BY month;
