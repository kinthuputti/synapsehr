"""
experience.py - years of experience from a resume's text.

Rules, in order (the first one that applies wins):
  1. an explicit claim of TOTAL experience ("20 years of progressive experience")
  2. job date ranges (see tenure.py): earliest start to latest end
  3. one lone date in the Experience section ("Designer, 02/2011"): read as a start, job still current (flagged)
  4. an Experience section with nothing readable: counted as under 1 year (flagged)
  5. otherwise unknown (None)
The dates are always worked out too, so the scorer can compare them with the claim.
"""
import re

import tenure

# ---- explicit claims -------------------------------------------------------------------------
# "8 years of management experience" or "5 years of sales experience" name ONE area, so they are ignored.
# A claim counts as total only if the words between "years" and "experience" are plain fillers.
NUMBER_WORDS = {w: i for i, w in enumerate(
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split(), 1)}
NUMBER_WORDS.update({"thirty": 30, "forty": 40})
_NUM = r"(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")"
TOTAL_FILLER = {"of", "and", "a", "an", "the", "professional", "progressive", "relevant", "work", "working",
                "combined", "total", "industry", "practical", "diverse", "extensive", "overall", "solid",
                "proven", "related", "paid", "real", "world", "hands", "on", "plus", "is", "approximately",
                "about", "nearly", "almost", "over", "more", "than", "years", "year"}
STATED_A = re.compile(rf"\b{_NUM}\+?\s*(?:years?|yrs?)\b(?!\s*(?:plan|old|term|contract|warranty|program|degree))"
                      r"([^.]{0,80}?)\b(?:experience|background|expertise|career)\b", re.IGNORECASE)
STATED_B = re.compile(rf"\bexperience\b([^.\d]{{0,20}}?){_NUM}\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)


def _number(word):
    word = word.lower()
    return int(word) if word.isdigit() else NUMBER_WORDS.get(word)


def _is_plain(middle):
    return set(re.findall(r"[a-z]+", middle.lower())) <= TOTAL_FILLER


def stated_years(text):
    """The largest explicit claim of TOTAL years of experience, or None."""
    found = []
    for m in STATED_A.finditer(text or ""):
        n = _number(m.group(1))
        if n and _is_plain(m.group(2)):
            found.append(n)
    for m in STATED_B.finditer(text or ""):
        n = _number(m.group(2))
        if n and _is_plain(m.group(1)):
            found.append(n)
    found = [n for n in found if 0 < n <= 45]
    return max(found) if found else None


# ---- the Experience section ------------------------------------------------------------------
EXPERIENCE_HEADING = re.compile(
    r"(?:^|\s)(?:(?:Work|Professional|Relevant)\s+)?(?:Experience|EXPERIENCE|Work History|Employment History)\s+(?:[A-Z]|\n)")
SECTION_END = re.compile(      # the next common heading after Experience
    r"(?:^|\s)(?:Education(?:\s+and\s+Training)?|EDUCATION|Skills|SKILLS|Additional Information|ADDITIONAL INFORMATION"
    r"|Certifications?|Interests|Languages|Affiliations|Awards|Accomplishments|Publications|References)(?=\s|$)")


def has_experience_heading(text):
    return bool(EXPERIENCE_HEADING.search(text or ""))


def experience_segment(text):
    m = EXPERIENCE_HEADING.search(text or "")
    if not m:
        return None
    rest = text[m.end():]
    stop = SECTION_END.search(rest)
    return rest[:stop.start()] if stop else rest


def lone_start_years(text):
    """Years if the Experience section holds a single date like '02/2011' (read as start, still current)."""
    segment = experience_segment(text)
    start = tenure.lone_start(segment) if segment else None
    if start is None:
        return None
    now = tenure.today()
    return tenure.span_years([(start, (now.year, now.month))])


# ---- putting the rules together --------------------------------------------------------------
def years_of_experience(text):
    text = text or ""
    from_dates = tenure.span_years(tenure.periods_from_text(text))
    stated = stated_years(text)
    years = stated if stated is not None else from_dates
    assumption = None
    if years is None:
        lone = lone_start_years(text)
        if lone is not None:
            years = lone
            assumption = ("only one date found in the Experience section: treated as a start date with the job "
                          "still current (an assumption, please check)")
    if years is None and has_experience_heading(text):
        years = 0
        assumption = ("no years or dates found in the Experience section: counted as under 1 year "
                      "(an assumption, please check)")
    return {"years": years, "years_stated": stated, "years_from_dates": from_dates,
            "years_assumed": assumption is not None, "years_assumption": assumption}
