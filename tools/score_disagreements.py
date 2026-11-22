"""
score_disagreements.py - turn your hand-checking into numbers.

1. Run compare_readers.py (it writes results/disagreements.csv).
2. Open that file in Excel. For each row, read the resume and fill the 'truth' column:
     skill rows     -> y if the resume really shows that skill, n if it does not
     years rows     -> the real number of years (or 'none' if the resume doesn't say)
     education rows -> the real highest level (diploma/associate/bachelor/master/doctorate) or 'none'
   Leave 'truth' empty for rows you did not check.
3. Run:  python tools/score_disagreements.py

IMPORTANT: only the DISAGREEMENTS are judged. Skills both readers agree on are assumed
correct but not verified, so these are NOT overall accuracy numbers. Say so in the README.
"""
import pandas as pd

d = pd.read_csv("results/disagreements.csv", dtype=str).fillna("")
judged = d[d["truth"].str.strip() != ""]
print(f"{len(judged)} of {len(d)} disagreements judged by you\n")

skills = judged[judged["field"].str.startswith("skill:")]
for label, mine, other in [("LLM-only skills", "llm", "rules"), ("rules-only skills", "rules", "llm")]:
    sub = skills[(skills[mine] == "found") & (skills[other] == "")]
    if len(sub):
        ok = sub["truth"].str.strip().str.lower().str.startswith("y").sum()
        print(f"{label}: {ok} of {len(sub)} were really in the resume ({ok / len(sub):.0%})")

for field in ["years", "education"]:
    sub = judged[judged["field"] == field]
    if len(sub):
        truth = sub["truth"].str.strip().str.lower()
        r = (sub["rules"].str.lower() == truth).sum()
        l = (sub["llm"].str.lower() == truth).sum()
        print(f"{field}: rules right on {r} of {len(sub)}, LLM right on {l} of {len(sub)}")

print("\nSmall numbers: with a handful of rows these are impressions, not proof.")
