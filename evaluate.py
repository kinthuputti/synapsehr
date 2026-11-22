"""
evaluate.py - how often does the system agree with YOUR decisions?

    python evaluate.py              # keyword reader (no API needed)
    python evaluate.py --llm        # also needs GEMINI_API_KEY / GEMINI_MODEL; uses some free quota

Reads eval/labels.csv (made by make_eval_sheet.py, 'decision' filled in by you).
Prints a short report with the sample size, and a paragraph you can paste into the README.
"""
import sys

import config  # noqa: F401  (reference date for the old Kaggle resumes)
import pandas as pd

from jobs import get_job
from scorer import score

use_llm = "--llm" in sys.argv
if use_llm:
    from llm_reader import llm_read_resume as read_resume
else:
    from reader import read_resume

VALID = ("shortlist", "review", "reject")
labels = pd.read_csv("eval/labels.csv", dtype=str).fillna("")
labels["decision"] = labels["decision"].str.strip().str.lower()
resumes = pd.read_csv("data/sample/resume_sample.csv", dtype={"ID": str}).set_index("ID")

same = labels[labels["type"] == "same_profession"]
unlabeled = same[~same["decision"].isin(VALID)]
if len(unlabeled):
    print(f"Note: {len(unlabeled)} same-profession pairs have no valid decision and are skipped "
          f"(use shortlist / review / reject).\n")
labels = labels[labels["decision"].isin(VALID)]
if not (labels["type"] == "same_profession").any():
    raise SystemExit("No labeled pairs yet. Fill the 'decision' column in eval/labels.csv first.")

agent, scrutiny, failed = [], [], 0
for _, row in labels.iterrows():
    facts = read_resume(resumes.loc[row["resume_id"], "Resume_str"])
    if facts.get("error"):
        failed += 1
        agent.append("failed")
        scrutiny.append(False)
        continue
    result = score(facts, get_job(int(row["job_id"])))
    agent.append(result["recommendation"])
    scrutiny.append(result["needs_extra_scrutiny"])
labels = labels.assign(agent=agent, scrutiny=scrutiny)
scored = labels[labels["agent"] != "failed"]

hard = scored[scored["type"] == "same_profession"]          # the real test: same profession
easy = scored[scored["type"] == "different_profession"]     # reject by construction
agree = (hard["agent"] == hard["decision"]).sum()
advance = lambda s: s.isin(["shortlist", "review"])
binary = (advance(hard["agent"]) == advance(hard["decision"])).sum()
missed = ((hard["decision"] == "shortlist") & (hard["agent"] == "reject")).sum()
false_accept = ((hard["decision"] == "reject") & (hard["agent"] == "shortlist")).sum()
easy_ok = (easy["agent"] == "reject").sum()
flagged = int(hard["scrutiny"].sum())

print(f"Reader: {'LLM' if use_llm else 'keyword rules'}   |   labeled same-profession pairs: {len(hard)}"
      + (f"   |   reader failures: {failed}" if failed else ""))
print("\nYour decision (rows) vs the system's recommendation (columns), same-profession pairs:\n")
print(pd.crosstab(hard["decision"], hard["agent"]).reindex(index=VALID, columns=VALID, fill_value=0).to_string())
print(f"\n  exact agreement                         : {agree} of {len(hard)} ({agree / len(hard):.0%})")
print(f"  agree on 'advance (shortlist/review)' vs 'reject': {binary} of {len(hard)} ({binary / len(hard):.0%})")
print(f"  good candidates the system rejected (you: shortlist, system: reject): {missed}")
print(f"  weak candidates the system shortlisted (you: reject, system: shortlist): {false_accept}")
print(f"  flagged for extra checking: {flagged} of {len(hard)}")
print(f"  different-profession pairs rejected: {easy_ok} of {len(easy)}")

print("\n--- paragraph for the README (check every number and keep the caveats) ---")
print(f"I labeled {len(hard)} resume-and-job pairs from the same profession myself (shortlist, review or reject), "
      f"before running the system. The {'LLM' if use_llm else 'keyword'} reader agreed exactly with {agree} of "
      f"{len(hard)} ({agree / len(hard):.0%}) and agreed on advance versus reject for {binary} of {len(hard)}. "
      f"It rejected {missed} candidate(s) I would have shortlisted. It rejected {easy_ok} of {len(easy)} "
      f"pairs from a different profession. Caveats: one labeler, a small sample from one dataset of "
      f"resume-builder examples, and the labels reflect my own judgment of the job requirements.")
