"""
tenure.py - years of experience from job DATE RANGES (shared by both readers).

Definition used everywhere (write it in the README):
    years = whole years from the EARLIEST job start to the LATEST job end.
    "Current" / "Present" means today. Gaps between jobs are not subtracted.
Why code and not the LLM: language models are unreliable at counting and do not
know today's date. The LLM only copies the dates; this file does the arithmetic.

Date formats understood:
    July 2004 to Current      Jul '04 - Mar '09       03/2015 - 05/2019      03.2015 - 05.2019
    March, 2015 to June, 2019 Summer 2015 to Winter 2018   2015 - 2019      2015 to date
    Jan 2016 - Ongoing        Since March 2015        Since 2015              '15 - '19
"Present" can also be written current, currently, present, now, ongoing, till date, to date.

Rules of priority (so a stray year does not distort the result):
  1. ranges with a month or season ("Jan 2015 - Mar 2019")
  2. year-only ranges ("2015 - 2019"), only if there are no month ranges
     (year-only ranges are often education dates)
  3. "Since ..." only if there are no ranges at all ("since 2010 sales grew" is not a job start)
  (reader.py adds a fourth, flagged fallback: one lone date in the Experience section, e.g.
   "Designer, 02/2011", is treated as a start date with the job still current)
Limits: two-digit years need an apostrophe ('15). A resume with nothing readable gives None.
"""
import os
import re
from datetime import date

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
SEASON_MONTH = {"spring": 3, "summer": 6, "fall": 9, "autumn": 9, "winter": 12}

# real month names only ("Marketing" must not count as March)
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
          r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
_SEASON = r"(?:spring|summer|fall|autumn|winter)"
_YEAR = r"(?:19|20)\d{2}"
_SHORT = r"[’']\d{2}"
_MY = rf"{_MONTH}(?:[\s,.\-]*{_YEAR}|\s*{_SHORT})"
_SY = rf"{_SEASON}(?:[\s,]*{_YEAR}|\s*{_SHORT})"
_NUMERIC = rf"(?:0?[1-9]|1[0-2])[/.\-]{_YEAR}"
_DATE = rf"(?:{_MY}|{_SY}|{_NUMERIC}|{_YEAR}|{_SHORT})"
_NOW = r"(?:current(?:ly)?|present(?:\s+day)?|now|till\s+(?:date|now)|to\s+date|date|ongoing|today)"
RANGE = re.compile(rf"(?<![\w/])({_DATE})\s*(?:to|until|through|-|–|—)\s*({_DATE}|{_NOW})(?!\w)", re.IGNORECASE)
SINCE = re.compile(rf"(?<!\w)since\s+({_MY}|{_SY}|{_NUMERIC}|{_YEAR}|{_SHORT})(?!\w)", re.IGNORECASE)


LONE = re.compile(rf"(?<![\w/])({_MY}|{_SY}|{_NUMERIC})(?!\w)", re.IGNORECASE)


def lone_start(segment):
    """Earliest month-qualified date in a piece of text (a job start with no end date), or None.
    Plain years are ignored here: a bare 2011 could be almost anything."""
    now = today()
    dates = [_parse_text_date(m.group(1), False) for m in LONE.finditer(segment or "")]
    dates = [d for d in dates if 1950 <= d[0] <= now.year and d <= (now.year, now.month)]
    return min(dates) if dates else None


def today():
    """The date that "Current" means. Normally today. For an OLD dataset, set the date the resumes were
    written, e.g. in PowerShell:  $env:SYNAPSEHR_AS_OF="2018-12-31"   (YYYY-MM-DD). Unset = today."""
    override = os.environ.get("SYNAPSEHR_AS_OF")
    if override:
        try:
            return date.fromisoformat(override)
        except ValueError:
            pass                                        # a mistyped date is ignored, today is used
    return date.today()


def _qualified(token):
    """True if the date has a month or season (not just a year)."""
    return bool(re.match(rf"(?:{_MY}|{_SY}|{_NUMERIC})", token.strip(), re.IGNORECASE))


def _year_of(t):
    full = re.search(_YEAR, t)
    if full:
        return int(full.group())
    yy = int(re.search(r"[’'](\d{2})", t).group(1))
    return 2000 + yy if yy <= today().year % 100 else 1900 + yy


def _parse_text_date(token, is_end):
    t = token.lower().strip()
    if re.fullmatch(_NOW, t):
        d = today()
        return d.year, d.month
    year = _year_of(t)
    season = re.match(_SEASON, t)
    named = re.match(_MONTH, t)
    numeric = re.match(r"(\d{1,2})[/.\-]", t)
    if season:
        month = SEASON_MONTH[season.group()]
    elif named:
        month = MONTHS.index(named.group()[:3]) + 1
    elif numeric:
        month = int(numeric.group(1))
    else:
        month = 12 if is_end else 1
    return year, month


def periods_from_text(text):
    """Find job date ranges in raw resume text (see the priority rules above)."""
    text = text or ""
    found = []
    for m in RANGE.finditer(text):
        found.append((_qualified(m.group(1)), _parse_text_date(m.group(1), False),
                      _parse_text_date(m.group(2), True)))
    with_month = [(s, e) for q, s, e in found if q]
    chosen = with_month or [(s, e) for _, s, e in found]
    if not chosen:                                   # last resort: "Since March 2015"
        now = today()
        chosen = [(_parse_text_date(m.group(1), False), (now.year, now.month)) for m in SINCE.finditer(text)]
    return chosen


def parse_iso_date(token, is_end):
    """For LLM output: 'YYYY-MM', 'YYYY', or 'current'. Returns (year, month) or None."""
    t = str(token).strip().lower()
    if t in ("current", "present", "now"):
        d = today()
        return d.year, d.month
    m = re.fullmatch(rf"({_YEAR})(?:-(\d{{1,2}}))?", t)
    if not m:
        return None
    month = int(m.group(2)) if m.group(2) else (12 if is_end else 1)
    return (int(m.group(1)), month) if 1 <= month <= 12 else None


def span_years(periods):
    """Whole years from earliest start to latest end (None if nothing usable)."""
    now = today()
    now_ym = (now.year, now.month)
    ok = []
    for start, end in periods:
        end = min(end, now_ym)                         # an end date cannot be in the future
        if 1950 <= start[0] <= now.year and end >= start:
            ok.append((start, end))
    if not ok:
        return None
    start = min(s for s, _ in ok)
    end = max(e for _, e in ok)
    years = ((end[0] - start[0]) * 12 + (end[1] - start[1])) // 12
    return years if 0 <= years <= 60 else None
