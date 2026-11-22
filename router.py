"""
router.py - the SUPERVISOR's routing step: which workflow should handle this message?

Rules only (no LLM), on purpose: a router that can be talked into anything is a risk.
If nothing matches clearly, the answer is "unknown" and a human takes over.
Order matters: screening, then leave request, then policy question.
"""
import re

SCREENING = re.compile(r"\b(resume|resumes|cv|cvs|candidate|candidates|applicant|applicants|shortlist|screen)\b", re.I)
LEAVE_WORDS = re.compile(r"\b(leave|day off|days off|time off|vacation|holiday|sick|unwell|off work)\b", re.I)
REQUEST_MARKERS = re.compile(r"\b(i want|i need|i would like|i'd like|please (?:approve|book|give)|request|apply|book|"
                             r"take|taking|i am (?:sick|unwell|ill)|i'm (?:sick|unwell|ill))\b", re.I)
QUESTION_MARKERS = re.compile(r"\b(how many|how much|how long|what|which|who|when|where|why|policy|allowed|"
                              r"entitled|eligible|rules?)\b|\?\s*$", re.I)
HAS_AMOUNT = re.compile(r"\b\d{1,2}\s*(?:[a-z-]+\s+){0,3}?days?\b|\b(?:a|one)\s+day\b", re.I)


HIRING = re.compile(r"\bhiring\s+decision\s+for\s+candidate\s+#?(\d+)\b", re.I)


def route(text):
    """Return (intent, why). intent is one of: screening, leave_request, policy_question, unknown."""
    t = (text or "").strip()
    if not t:
        return "unknown", "empty message"
    if HIRING.search(t):                       # before screening: it also says "candidate"
        return "hiring_decision", "asks for a hiring decision on a candidate"
    if SCREENING.search(t):
        return "screening", "mentions resumes/candidates"
    if re.search(r"\bhow (?:many|much)\b", t, re.I) and not HAS_AMOUNT.search(t):
        return "policy_question", "asks 'how many/how much' without stating an amount"
    if re.search(r"\b(balance|remaining|left)\b", t, re.I) and not HAS_AMOUNT.search(t):
        return "policy_question", "asks about a balance without stating an amount"
    if re.match(r"\s*(do|does|is|are|am|can|could|may|should|would|will)\b", t, re.I) and not HAS_AMOUNT.search(t):
        return "policy_question", "starts as a yes/no question without stating an amount"
    wants_leave = bool(LEAVE_WORDS.search(t))
    asks_for_it = bool(REQUEST_MARKERS.search(t)) or bool(HAS_AMOUNT.search(t))
    asks_question = bool(QUESTION_MARKERS.search(t))
    if wants_leave and asks_for_it and not re.match(r"\s*(how many|how much|what|which|who)\b", t, re.I):
        return "leave_request", "asks for leave with a request wording or an amount of days"
    if asks_question:
        return "policy_question", "reads as a question"
    return "unknown", "no clear workflow matched"
