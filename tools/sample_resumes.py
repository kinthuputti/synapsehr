"""
sample_resumes.py - build a small, varied sample from the Kaggle Resume Dataset
and print simple structure checks (no resume text is printed).

Run from your SynapseHR folder (virtual environment active):
    python tools/sample_resumes.py

Reads : data/resume/Resume/Resume.csv  (+ PDFs under data/resume/data/ if found)
Writes: data/sample/resume_sample.csv
Keep data/ out of Git (it is in your .gitignore).
"""
from pathlib import Path

import pandas as pd

ROOT = Path("data/resume")
CSV = ROOT / "Resume" / "Resume.csv"
OUT = Path("data/sample")
OUT.mkdir(parents=True, exist_ok=True)

# Six very different professions, so the sample is genuinely heterogeneous
CATEGORIES = ["INFORMATION-TECHNOLOGY", "HEALTHCARE", "HR",
              "CONSTRUCTION", "FINANCE", "TEACHER"]
PER_CATEGORY = 8
SEED = 1

df = pd.read_csv(CSV)
print(f"loaded {len(df)} resumes, {df['Category'].nunique()} categories\n")

# 1) sample the same number from each chosen category
parts = []
for cat in CATEGORIES:
    group = df[df["Category"] == cat]
    parts.append(group.sample(min(PER_CATEGORY, len(group)), random_state=SEED))
sample = pd.concat(parts).reset_index(drop=True)

# 2) find the matching PDF for each resume, if the PDFs exist
pdf_index = {p.stem: str(p) for p in (ROOT / "data").rglob("*.pdf")} if (ROOT / "data").exists() else {}
sample["pdf_path"] = sample["ID"].astype(str).map(pdf_index).fillna("")

# 3) simple structure checks: how varied are the resumes?
text = sample["Resume_str"].fillna("").str.lower()
sample["words"] = text.str.split().str.len()
for section in ["summary", "skills", "experience", "education"]:
    sample[f"has_{section}"] = text.str.contains(section)
sample["has_pdf"] = sample["pdf_path"] != ""

sample.to_csv(OUT / "resume_sample.csv", index=False)
print(f"saved {len(sample)} resumes -> {OUT / 'resume_sample.csv'}\n")

checks = ["words", "has_summary", "has_skills", "has_experience", "has_education", "has_pdf"]
print("per-profession structure check (averages; has_* = share of resumes, 1.0 = all):\n")
print(sample.groupby("Category")[checks].mean().round(2).to_string())
print(f"\nPDFs found: {int(sample['has_pdf'].sum())} of {len(sample)}")
