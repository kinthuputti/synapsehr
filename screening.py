"""
screening.py - the resume-screening workflow: reader -> scorer -> human checkpoint.
Used by run_v01.py and by the supervisor (run_synapsehr.py). Every decision goes in the audit log.
"""
import os

import pandas as pd

import tenure
from checkpoint import ask_human
from jobs import get_job
from scorer import score


def screen(job_id=1, n=5, others=2, reader="rule", auto=False, csv_path="data/sample/resume_sample.csv"):
    if reader == "llm":
        from llm_reader import llm_read_resume as read_resume   # same fields as the keyword reader
    else:
        from reader import read_resume

    job = get_job(job_id)
    df = pd.read_csv(csv_path)
    same = df[df["Category"] == job["category"]].head(n)
    pool = df[df["Category"] != job["category"]]
    other = pool.sample(min(others, len(pool)), random_state=1)       # was len(df): could crash on small samples
    batch = pd.concat([same, other])

    date_note = "" if os.environ.get("SYNAPSEHR_AS_OF") else "  (today's date; see config.py for the old Kaggle resumes)"
    print(f"Job: {job['title']}  | must-have: {', '.join(job['must_have'])}")
    print(f"Screening {len(batch)} resumes ({len(same)} same profession, {len(other)} other)")
    print(f"'Current' in a job is counted up to {tenure.today()}{date_note}")

    entries = []
    for _, row in batch.iterrows():
        facts = read_resume(row["Resume_str"])
        if facts.get("error"):
            print(f"\nResume {row['ID']}: reader failed ({facts['error'][:120]}). Skipped.")
            continue
        entries.append(ask_human(row["ID"], job, score(facts, job), auto=auto))
    return entries
