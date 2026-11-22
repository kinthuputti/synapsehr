"""
show_resume.py - print the text of any resume in the full Kaggle CSV, by ID.

    python tools/show_resume.py 12345678
    python tools/show_resume.py 12345678 --chars 4000     # show more (default 2500)
Prints the resume on your own screen only. The data is the public Kaggle dataset.
"""
import sys

import pandas as pd

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) != 1:
    raise SystemExit("usage: python tools/show_resume.py RESUME_ID [--chars N]")
chars = int(sys.argv[sys.argv.index("--chars") + 1]) if "--chars" in sys.argv else 2500

df = pd.read_csv("data/resume/Resume/Resume.csv", dtype={"ID": str})
row = df[df["ID"] == args[0]]
if row.empty:
    raise SystemExit(f"resume {args[0]} not found in data/resume/Resume/Resume.csv")
text = " ".join(str(row.iloc[0]["Resume_str"]).split())
print(f"Resume {args[0]}  ({row.iloc[0]['Category']}, {len(text.split())} words)\n")
print(text[:chars] + (" ..." if len(text) > chars else ""))
