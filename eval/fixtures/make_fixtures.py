"""Builds the synthetic documents used by the evaluation datasets.

Run once (needs python-docx):  python eval/fixtures/make_fixtures.py
All content is invented for testing - it describes no real patient."""

import os

import docx

HERE = os.path.dirname(os.path.abspath(__file__))

DISCHARGE_SUMMARY = [
    "SUNRISE MULTISPECIALITY HOSPITAL - DISCHARGE SUMMARY",
    "Synthetic test document for ClinIQ evaluation. Not a real patient.",
    "Patient: Test Patient A (synthetic), Age/Sex: 62/M, MRN: TEST-0001",
    "Admission date: 03-10-2026. Discharge date: 09-10-2026. Consultant: Dr. R. Menon (Internal Medicine).",
    "Diagnosis:",
    "1. Community-acquired pneumonia, right lower lobe",
    "2. Type 2 diabetes mellitus, uncontrolled",
    "3. Hypertension",
    "4. Acute kidney injury (resolved)",
    "History of presenting illness: c/o fever for 5 days, productive cough and breathlessness on exertion. "
    "h/o type 2 diabetes for 8 years and hypertension for 5 years. Non-smoker.",
    "Examination on admission: Temperature 101.8 F, pulse 108/min, BP 150/92 mmHg, SpO2 91% on room air, "
    "respiratory rate 24/min. Crackles heard over the right lower zone.",
    "Investigations:",
    "Hemoglobin 11.4 g/dL (L), reference 13.0-17.0",
    "Total leukocyte count 15,800 /cumm (H), reference 4,000-11,000",
    "CRP 86 mg/L (H), reference below 5",
    "HbA1c 9.1 % (H), reference 4.0-5.6",
    "Serum creatinine 1.9 mg/dL (H) on admission and 1.1 mg/dL at discharge, reference 0.7-1.3",
    "Chest X-ray: right lower lobe consolidation. Blood culture: no growth after 48 hours.",
    "Hospital course: Started on IV Ceftriaxone 1 g BD and oral Azithromycin 500 mg OD for 3 days. "
    "Oxygen 2 L/min by nasal prongs for 2 days, weaned off on day 3. Insulin sliding scale was used for glucose "
    "control; metformin withheld during AKI and restarted on day 5 after creatinine improved. Fever settled by day 3.",
    "Condition at discharge: Afebrile, SpO2 97% on room air, walking without support.",
    "Discharge medications:",
    "Tab Amoxicillin-Clavulanate 625 mg TDS for 5 days",
    "Tab Metformin 500 mg BD after food",
    "Inj Insulin Glargine 12 units HS (subcutaneous)",
    "Tab Telmisartan 40 mg OD",
    "Tab Paracetamol 650 mg SOS for fever (maximum 4 tablets per day)",
    "Allergies: Sulfa drugs (rash).",
    "Advice: Diabetic diet. Monitor blood sugar twice daily (fasting and 2 hours after dinner). Drink plenty of "
    "fluids. Complete the full antibiotic course.",
    "Follow-up: Review in Medicine OPD after 7 days with fasting blood sugar, serum creatinine and a repeat chest "
    "X-ray. Return immediately if breathlessness worsens, fever comes back, or blood sugar is below 70 mg/dL.",
]


def build_discharge_summary(path: str):
    document = docx.Document()
    for line in DISCHARGE_SUMMARY:
        document.add_paragraph(line)
    document.save(path)


if __name__ == "__main__":
    out = os.path.join(HERE, "eval_discharge_summary.docx")
    build_discharge_summary(out)
    print("wrote", out)
