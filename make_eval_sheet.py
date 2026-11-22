"""
make_eval_sheet.py - builds the labeling pack for the final evaluation.

    python make_eval_sheet.py

Creates:
  eval/labels.csv               one row per resume-and-job pair. YOU fill the 'decision' column.
  eval/resumes_for_labeling.txt the resume text and job requirements, so you can read and decide

Pairs: for each of the 6 jobs, 5 resumes from the SAME profession (you label these) and
2 from a DIFFERENT profession (pre-filled 'reject': a nurse for a software job is a reject by construction).

IMPORTANT: label BEFORE you look at what the system says. Do not run evaluate.py or run_v01.py in between
and do not change a label after you see the results. That is what makes the number honest.
"""
import sys
from pathlib import Path

import pandas as pd

from jobs import JOBS

OUT = Path("eval")
OUT.mkdir(exist_ok=True)
LABELS, PACK = OUT / "labels.csv", OUT / "resumes_for_labeling.txt"

if LABELS.exists() and "--force" not in sys.argv:
    done = pd.read_csv(LABELS, dtype=str).fillna("")
    if ((done["type"] == "same_profession") & (done["decision"].str.strip() != "")).any():
        raise SystemExit("eval/labels.csv already has labels in it, so I did not overwrite it. "
                         "(Use --force only if you really want to start over.)")

df = pd.read_csv("data/sample/resume_sample.csv", dtype={"ID": str})
rows, pack = [], []
n = 0
for job in JOBS:
    same = df[df["Category"] == job["category"]].sample(min(5, (df["Category"] == job["category"]).sum()), random_state=7)
    other = df[df["Category"] != job["category"]].sample(2, random_state=7)
    for kind, group, decision in (("same_profession", same, ""), ("different_profession", other, "reject")):
        for _, r in group.iterrows():
            n += 1
            pid = f"P{n:02d}"
            rows.append({"pair_id": pid, "job_id": job["job_id"], "job_title": job["title"], "resume_id": r["ID"],
                         "resume_category": r["Category"], "type": kind, "decision": decision, "note": ""})
            if kind == "same_profession":
                text = " ".join(str(r["Resume_str"]).split())
                pack.append(f"{'=' * 78}\n{pid}   JOB: {job['title']}   (needs {job['min_years']}+ years)\n"
                            f"must have: {', '.join(job['must_have'])}   |   nice to have: {', '.join(job['nice_to_have'])}\n"
                            f"RESUME {r['ID']}:\n{text}\n")

pd.DataFrame(rows).to_csv(LABELS, index=False)
header = ("LABELING PACK. For each pair below, decide as a recruiter would, from the resume alone:\n"
          "  shortlist = I would invite this person to interview for this job\n"
          "  review    = borderline: a recruiter should look closer\n"
          "  reject    = clearly not a fit\n"
          "Type your decision in the 'decision' column of eval/labels.csv (shortlist / review / reject).\n"
          "Judge the job's must-haves and years of experience. Do NOT run the system until you are done.\n")
PACK.write_text(header + "\n".join(pack), encoding="utf-8")
todo = sum(r["type"] == "same_profession" for r in rows)
print(f"Created {LABELS} ({len(rows)} pairs, {todo} for you to label) and {PACK}")
print("Open the .txt to read each resume, and fill the 'decision' column in the .csv (Excel is fine).")
