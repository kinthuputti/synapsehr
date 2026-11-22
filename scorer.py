"""
scorer.py - the SCORER step.
Compares the reader's facts with a job and returns a recommendation PLUS the
reasons, so a human can check it. It never acts on its own.

Reliability idea: if the reader found very little, the system says so
(needs_extra_scrutiny) instead of sounding confident about weak evidence.
"""


YEARS_GAP_FLAG = 3               # a stated-vs-dates gap of this many years OR MORE goes to the reviewer
YEARS_FLAG_DIRECTION = "claim_higher"   # "claim_higher": only when the resume claims MORE than its dates show. "both": any gap


def score(facts, job):
    have = set(facts["skills"])
    must, nice = job["must_have"], job["nice_to_have"]

    must_hit = [t for t in must if t in have]
    must_missing = [t for t in must if t not in have]
    nice_hit = [t for t in nice if t in have]

    years = facts["years"]
    if years is None:
        years_ok = None                       # unknown, not a failure
    else:
        years_ok = years >= job["min_years"]

    # score out of 100: 70 must-haves, 20 nice-to-haves, 10 experience
    points = 70 * len(must_hit) / len(must) + 20 * len(nice_hit) / len(nice)
    points += 10 if years_ok else (5 if years_ok is None else 0)

    if not must_missing:
        recommendation = "shortlist"
    elif len(must_missing) == 1:
        recommendation = "review"
    else:
        recommendation = "reject"
    if years_ok is False and recommendation == "shortlist":
        recommendation = "review"             # all skills present but too little experience

    reasons = []
    if must_hit:
        reasons.append("has must-haves: " + ", ".join(must_hit))
    if must_missing:
        reasons.append("missing must-haves: " + ", ".join(must_missing))
    if nice_hit:
        reasons.append("nice-to-haves: " + ", ".join(nice_hit))
    if facts.get("years_assumed"):
        reasons.append(facts.get("years_assumption") or "years of experience were assumed (please check)")
    elif years_ok is None:
        reasons.append("years of experience not found in text")
    else:
        source = "stated in the resume" if facts.get("years_stated") is not None else "from job dates"
        reasons.append(f"about {years} years of experience, {source} (needs {job['min_years']})")

    stated, dated = facts.get("years_stated"), facts.get("years_from_dates")
    conflict = False
    if stated is not None and dated is not None:
        gap = stated - dated                          # positive: the claim is higher than the dates support
        conflict = abs(gap) >= YEARS_GAP_FLAG if YEARS_FLAG_DIRECTION == "both" else gap >= YEARS_GAP_FLAG
    if conflict:
        reasons.append(f"resume states {stated} years but its job dates add up to {dated}: check which is right")

    thin = facts["word_count"] < 150                  # too little text to judge (few skills is normal for a mismatch)
    return {
        "score": round(points),
        "recommendation": recommendation,
        "reasons": reasons,
        "needs_extra_scrutiny": thin or conflict or bool(facts.get("years_assumed")),
    }
