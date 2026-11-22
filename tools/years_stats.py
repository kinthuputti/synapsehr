"""
years_stats.py - how do resumes in YOUR data actually express experience?
Counts, for every resume in the Kaggle CSV:
  - stated only   : says "N years of experience" but has no readable job dates
  - dates only    : readable job date ranges but no stated number
  - both          : and how often the two disagree by the reviewer-flag limit (1 year) or more
  - neither       : and how many of those still have an Experience heading

    python tools/years_stats.py                          # uses data/resume/Resume/Resume.csv (all resumes)
    python tools/years_stats.py data/sample/resume_sample.csv
    python tools/years_stats.py --as-of 2018-12-31       # count "Current" up to this date instead of today
Prints counts only, no resume text.
"""
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # lets this tool import the project modules
import config  # noqa: E402,F401  (same reference date as the main scripts)
import tenure  # noqa: E402
from experience import has_experience_heading, lone_start_years, stated_years  # noqa: E402
from scorer import YEARS_FLAG_DIRECTION, YEARS_GAP_FLAG  # noqa: E402

argv = sys.argv[1:]
if "--as-of" in argv:
    i = argv.index("--as-of")
    os.environ["SYNAPSEHR_AS_OF"] = argv[i + 1]            # read by tenure.today()
    del argv[i:i + 2]
path = argv[0] if argv else "data/resume/Resume/Resume.csv"
df = pd.read_csv(path)

both = stated_only = dates_only = neither = conflicts = neither_with_heading = lone_only = 0
assumed_ids = []
latest_starts = []
gaps = []
for row_id, text in zip(df["ID"], df["Resume_str"].fillna("")):
    stated = stated_years(text)
    periods = tenure.periods_from_text(text)
    dated = tenure.span_years(periods)
    if periods:
        latest_starts.append(max(start[0] for start, _ in periods))
    if stated is not None and dated is not None:
        both += 1
        gaps.append(dated - stated)
        conflicts += abs(dated - stated) >= YEARS_GAP_FLAG
    elif stated is not None:
        stated_only += 1
    elif dated is not None:
        dates_only += 1
    elif lone_start_years(text) is not None:
        lone_only += 1                                   # one lone date in the Experience section
    else:
        neither += 1
        if has_experience_heading(text):
            neither_with_heading += 1
            assumed_ids.append(row_id)

n = len(df)
pct = lambda k: f"{k} ({k / n:.0%})"
print(f"{n} resumes in {path}   (\"Current\" counted up to {tenure.today()})\n")
print(f"  both a stated number and job dates : {pct(both)}")
print(f"  stated number only                 : {pct(stated_only)}")
print(f"  job dates only                     : {pct(dates_only)}")
print(f"  one lone date in Experience section: {pct(lone_only)}   (read as a start date, still working)")
print(f"  neither (no years can be found)    : {pct(neither)}")
if neither:
    print(f"      of those, with an Experience-like heading: {neither_with_heading}")
if assumed_ids:
    import random
    random.Random(1).shuffle(assumed_ids)
    print("\nResumes the 'under 1 year' rule would apply to. Open a few and ask: do they look like beginners?")
    print("   ", ", ".join(str(i) for i in assumed_ids[:5]))
    print(f"   view one with:  python tools/show_resume.py {assumed_ids[0]}")
if both:
    gaps.sort()
    print(f"\nWhere both exist: dates differ from the claim by {YEARS_GAP_FLAG} year(s) or more in {conflicts} of {both} resumes.")
    print(f"Median (dates minus claim): {gaps[len(gaps) // 2]} years, "
          f"middle 80% between {gaps[len(gaps) // 10]} and {gaps[-1 - len(gaps) // 10]}.")
    median_gap = gaps[len(gaps) // 2]
    print("\nHow many resumes would the reviewer flag at different gap limits?  (gap = dates minus claim)")
    print(f"  {'limit':>9} {'flagged':>9} {'share':>6}   {'claim higher':>12}  {'dates higher':>12}")
    for limit in (1, 2, 3, 5, 8):
        claim_hi = sum(g <= -limit for g in gaps)
        dates_hi = sum(g >= limit for g in gaps)
        print(f"  {limit:>6} yr+ {claim_hi + dates_hi:>9} {(claim_hi + dates_hi) / both:>6.0%}   "
              f"{claim_hi:>12}  {dates_hi:>12}")
    print("  'claim higher' = the resume claims MORE years than its dates support (the case to check).")
    now_flagged = sum((abs(g) >= YEARS_GAP_FLAG) if YEARS_FLAG_DIRECTION == "both" else (-g >= YEARS_GAP_FLAG)
                      for g in gaps)
    print(f"\nWith your current setting (limit {YEARS_GAP_FLAG} yr, direction '{YEARS_FLAG_DIRECTION}'): "
          f"{now_flagged} of {both} flagged ({now_flagged / both:.0%}).")
    print("Claims are often rounded or conservative, so do not read the median gap as the age of the resumes.")

if latest_starts:
    latest_starts.sort()
    q = lambda f: latest_starts[min(int(len(latest_starts) * f), len(latest_starts) - 1)]
    print("\nA resume cannot be older than its newest job start. Newest job start year across resumes:")
    print(f"  median {q(0.5)}, 90th percentile {q(0.9)}, 99th percentile {q(0.99)}, latest {latest_starts[-1]}")
    for year in (2016, 2017, 2018, 2019):
        print(f"  resumes with a job starting after {year}: {sum(y > year for y in latest_starts)}")
    print("  A reference date earlier than these starts would contradict those resumes. Pick a date at or after "
          "the 99th percentile year-end.")
