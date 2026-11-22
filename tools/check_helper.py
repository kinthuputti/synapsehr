"""
check_helper.py - make hand-checking fast. For one resume, show short snippets of the
text that matter for each disagreement, so you don't have to read the whole resume.

    python tools/check_helper.py 57088974
    python tools/check_helper.py 57088974 --full     # also print the whole text the readers received

For every row of results/disagreements.csv that belongs to that resume it prints:
  skill rows     -> where the skill's words appear (or 'not found literally')
  years rows     -> every year-like number and every 'N years' phrase, to help you add up the career
  education rows -> snippets around degree words
Then you fill the 'truth' column in the CSV yourself.
(This prints resume text on your own screen only. The data is the public Kaggle dataset.)
"""
import re
import sys

import pandas as pd

args = [a for a in sys.argv[1:] if a != "--full"]
if len(args) != 1:
    raise SystemExit("usage: python tools/check_helper.py RESUME_ID [--full]")
rid = args[0]
show_full = "--full" in sys.argv

resumes = pd.read_csv("data/sample/resume_sample.csv", dtype={"ID": str})
text = resumes.loc[resumes["ID"] == rid, "Resume_str"]
if text.empty:
    raise SystemExit(f"resume {rid} not found in data/sample/resume_sample.csv")
text = " ".join(str(text.iloc[0]).split())            # tidy whitespace

rows = pd.read_csv("results/disagreements.csv", dtype=str).fillna("")
rows = rows[rows["ID"] == rid]
if rows.empty:
    raise SystemExit(f"no disagreements saved for {rid}")


def snippets(pattern, width=70, limit=3):
    out = []
    for m in re.finditer(pattern, text, re.IGNORECASE):
        a, b = max(0, m.start() - width), min(len(text), m.end() + width)
        out.append("..." + text[a:b] + "...")
        if len(out) == limit:
            break
    return out


print(f"Resume {rid}  ({len(text.split())} words)\n")
if show_full:                      # the exact text the readers received
    print("=" * 70)
    print(text)
    print("=" * 70 + "\n")
for _, r in rows.iterrows():
    print("-" * 70)
    field = r["field"]
    if field.startswith("skill:"):
        term = field.split(":", 1)[1]
        who = "rules" if r["rules"] else "LLM"
        print(f"SKILL '{term}'  (found only by {who})   -> truth: y or n")
        hits = snippets(re.escape(term).replace(r"\ ", r"\s+"))
        for h in hits or ["(the words do not appear literally; look for a synonym or related duties)"]:
            print("   ", h)
    elif field == "years":
        print(f"YEARS  rules={r['rules']}  llm={r['llm']}   -> truth: the real number, or none")
        print("    'N years' phrases:", re.findall(r"\d{1,2}\+?\s*(?:years?|yrs?)", text, re.IGNORECASE) or "none")
        yrs = sorted({int(y) for y in re.findall(r"\b(19[5-9]\d|20[0-3]\d)\b", text)})
        print("    year-like numbers:", yrs or "none")
    elif field == "education":
        print(f"EDUCATION  rules={r['rules']}  llm={r['llm']}   -> truth: the highest level, or none")
        hits = snippets(r"bachelor|master|\bmba\b|associate|diploma|\bb\.?s\.?\b|\bm\.?s\.?\b|degree|university|college")
        for h in hits or ["(no degree words found)"]:
            print("   ", h)
print("-" * 70)
