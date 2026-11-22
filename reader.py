"""
reader.py - the READER step, rule-based (no LLM).
Turns raw resume text into a few facts: skills, education and years of experience.
The LLM reader (llm_reader.py) returns the same fields, so the two can be compared.

Known weaknesses (they belong in the README):
  - keyword matching has false positives ("excel" can match the verb "excels")
  - a skill described in different words is missed ("managed budgets" vs "budgeting")
  - PDF text can be damaged ("sta f" for "staff"), which breaks keyword matching
"""
import re

from experience import years_of_experience
from jobs import all_terms

EDUCATION_LEVELS = [          # lowest to highest
    ("diploma", r"\bdiploma\b|\bcertificate\b"),
    ("associate", r"\bassociate'?s?\s+(?:degree|of|in)\b"),          # not "Sales Associate"
    ("bachelor", r"\bbachelor'?s?\b|\bb\.s\.|\bb\.a\.|\bbsc\b|\bbba\b|(?-i:\b(?:BS|BA)\s*:)"),
    ("master", r"\bmaster'?s\b|\bmaster\s*(?:degree|of)\b|\bm\.s\.|\bmsc\b|\bmba\b|(?-i:\b(?:MS|MA)\s*:)"),  # "MS : Major" yes, "MS Office" no
    ("doctorate", r"\bph\.?d\b|\bdoctorate\b"),
]

# A degree is NOT completed if one of these words sits directly before it ("courses in an MBA")
# or "in progress" follows it. Only the words next to the degree count, so one unfinished degree
# does not cancel the next one in the list.
BEFORE_UNFINISHED = re.compile(
    r"(?:\bcourses?\s+(?:in|toward|towards|for)|\bcoursework\s+(?:in|toward|towards|for)|\bpursuing"
    r"|\bcandidate\s+for|\benrolled\s+in|\bcredits?\s+(?:toward|towards|for)|\bstudying)\s+(?:an?\s+|the\s+)?$",
    re.IGNORECASE)
AFTER_UNFINISHED = re.compile(
    r"^[^.]{0,25}?\b(?:in progress|incomplete|not (?:yet )?(?:completed|finished|complete))\b", re.IGNORECASE)


def _term_pattern(term):
    # whole words only; allow simple endings: budget -> budgets, budgeting
    body = re.escape(term).replace(r"\ ", r"\s+")
    return re.compile(rf"\b{body}(?:s|es|ing|ed)?\b", re.IGNORECASE)


def _has_degree(text, pattern):
    for m in re.finditer(pattern, text, re.IGNORECASE):
        before = text[max(0, m.start() - 40):m.start()]
        after = text[m.end():m.end() + 40]
        if not BEFORE_UNFINISHED.search(before) and not AFTER_UNFINISHED.search(after):
            return True
    return False


def read_resume(text):
    text = text or ""
    skills = [t for t in all_terms() if _term_pattern(t).search(text)]
    education = None
    for level, pattern in EDUCATION_LEVELS:
        if _has_degree(text, pattern):
            education = level                           # keeps the highest one found
    return {"skills": skills, "education": education, "word_count": len(text.split()),
            **years_of_experience(text)}
