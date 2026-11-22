"""
compare_readers.py - run BOTH readers on the same resumes and show where they disagree.
Prints skill names and counts only, never resume text.

    python tools/compare_readers.py            # 10 resumes
    python tools/compare_readers.py --n 20
Needs GEMINI_API_KEY and GEMINI_MODEL set (see check_gemini.py).

Every disagreement is also saved to results/disagreements.csv. Open that file in
Excel, read the resumes, and fill in the last column (see score_disagreements.py).
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # lets this tool import the project modules
import config  # noqa: E402,F401  (same reference date as the main scripts)
from llm_reader import llm_read_resume  # noqa: E402
from reader import read_resume  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--n", type=int, default=10)
args = parser.parse_args()

df = pd.read_csv("data/sample/resume_sample.csv")
df = df.sample(min(args.n, len(df)), random_state=1)

both = rule_only = llm_only = years_same = edu_same = failed = 0
rows = []                                           # disagreements to check by hand
show = lambda v: "none" if v is None else str(v)

for _, row in df.iterrows():
    a = read_resume(row["Resume_str"])
    b = llm_read_resume(row["Resume_str"])
    if b.get("error"):
        failed += 1
        print(f"\n{row['ID']}  ({row['Category']})\n  LLM FAILED (not counted below): {b['error']}")
        time.sleep(5)
        continue
    sa, sb = set(a["skills"]), set(b["skills"])
    both += len(sa & sb)
    rule_only += len(sa - sb)
    llm_only += len(sb - sa)
    years_same += a["years"] == b["years"]
    edu_same += a["education"] == b["education"]

    for s in sorted(sa - sb):
        rows.append([row["ID"], row["Category"], f"skill:{s}", "found", "", ""])
    for s in sorted(sb - sa):
        rows.append([row["ID"], row["Category"], f"skill:{s}", "", "found", ""])
    if a["years"] != b["years"]:
        rows.append([row["ID"], row["Category"], "years", show(a["years"]), show(b["years"]), ""])
    if a["education"] != b["education"]:
        rows.append([row["ID"], row["Category"], "education", show(a["education"]), show(b["education"]), ""])

    print(f"\n{row['ID']}  ({row['Category']})")
    print(f"  both found      : {sorted(sa & sb) or '-'}")
    print(f"  only rules found: {sorted(sa - sb) or '-'}")
    print(f"  only LLM found  : {sorted(sb - sa) or '-'}")
    print(f"  years  rules={a['years']}  llm={b['years']}   education rules={a['education']}  llm={b['education']}")
    time.sleep(5)                                   # be gentle with the free-tier rate limit

n = len(df) - failed
print("\n" + "=" * 60)
print(f"LLM failed on {failed} of {len(df)} resumes; statistics below use the other {n}.")
print(f"{n} resumes | skills found by both: {both}, only rules: {rule_only}, only LLM: {llm_only}")
print(f"years agree on {years_same}/{n}, education agrees on {edu_same}/{n}")

Path("results").mkdir(exist_ok=True)
out = Path("results/disagreements.csv")
if out.exists() and (pd.read_csv(out, dtype=str).fillna("")["truth"].str.strip() != "").any():
    out = Path("results/disagreements_new.csv")      # never overwrite answers you already filled in
    print("\nYour existing disagreements.csv already has answers in it, so it was NOT overwritten.")
pd.DataFrame(rows, columns=["ID", "Category", "field", "rules", "llm", "truth"]).to_csv(out, index=False)
print(f"\nSaved {len(rows)} disagreements to {out}")
print("Next: open it, check each row against the resume, fill the 'truth' column, then run")
print("      python tools/score_disagreements.py")
