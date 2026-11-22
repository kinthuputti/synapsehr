"""
leave_agent.py - the LEAVE step. Turns a request like "I need 3 days sick leave" into a
recommendation with reasons that point at the policy text. It never approves anything by itself:
the checkpoint asks a person.

The rules below mirror policies/leave_policy.md (18 annual days, 10 sick days, 10 consecutive-day
limit, medical certificate after 2 sick days, parental leave goes to HR). If you change the policy
document, change these numbers too: keeping them in sync is a known weak point.
"""
import json
import re
from pathlib import Path

ANNUAL_MAX_CONSECUTIVE = 10
SICK_CERTIFICATE_AFTER = 2


def load_employees(path="demo/employees.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


DAYS = re.compile(r"(\d{1,2})\s*(?:[a-z-]+\s+){0,3}?days?\b")      # "3 days", "10 annual leave days", "2 sick days"
ONE_DAY = re.compile(r"\b(?:a|one)\s+day\b")


def _kind(t):
    if re.search(r"parental|maternity|paternity|adoption|baby", t):
        return "parental"
    if re.search(r"\bsick\b|\bill\b|unwell|medical|doctor|fever", t):
        return "sick"
    return "annual"


def split_requests(text):
    """Every request the message contains: [{'days', 'kind'}]. One message can ask for more than one."""
    t = text.lower()
    found = list(DAYS.finditer(t))
    if not found:
        return [{"days": 1 if ONE_DAY.search(t) else None, "kind": _kind(t)}]
    cuts = [0] + [m.start() for m in found[1:]] + [len(t)]
    return [{"days": int(m.group(1)), "kind": _kind(t[cuts[i]:cuts[i + 1]])} for i, m in enumerate(found)]


def parse_request(text):
    return split_requests(text)[0]


def request_problem(text):
    """Why this message cannot become a leave request yet (said to the employee), or None if it can."""
    parts = split_requests(text)
    if len({(p["kind"], p["days"]) for p in parts}) > 1:
        return ("This looks like more than one request (for example annual and sick leave together). "
                "Please send them one at a time, such as: \"I need 10 days of annual leave\".")
    p = parts[0]
    if p["kind"] == "parental":
        return None
    if p["days"] is None:
        return "Please say how many days you need, for example: \"I need 3 days of annual leave\"."
    if not 1 <= p["days"] <= 60:
        return "Please ask for between 1 and 60 days in one request."
    return None


def _days(n):
    return f"{n} day" if n == 1 else f"{n} days"


def evaluate(request, employee):
    """Return {recommendation: approve|deny|escalate, reasons: [...], flagged: bool}."""
    kind, days = request["kind"], request["days"]
    if kind == "parental":
        return {"recommendation": "escalate",
                "reasons": ["Parental leave is handled by HR (leave_policy.md > Parental leave)"],
                "flagged": False}
    if employee is None:
        return {"recommendation": "escalate", "reasons": ["The employee was not found in the records."],
                "flagged": True}
    if days is None or not (1 <= days <= 60):
        return {"recommendation": "escalate",
                "reasons": ["Could not understand the number of days; ask the employee to restate the request."],
                "flagged": True}

    balance = employee["sick_balance"] if kind == "sick" else employee["annual_balance"]
    reasons = [f"Requested {_days(days)} of {kind} leave; {_days(balance)} left."]
    if days > balance:
        reasons.append(f"Not enough {kind} leave left (leave_policy.md > "
                       f"{'Sick leave' if kind == 'sick' else 'Annual leave'})")
        return {"recommendation": "deny", "reasons": reasons, "flagged": False}
    if kind == "annual" and days > ANNUAL_MAX_CONSECUTIVE:
        reasons.append(f"More than {ANNUAL_MAX_CONSECUTIVE} consecutive working days needs HR approval "
                       "(leave_policy.md > Annual leave)")
        return {"recommendation": "escalate", "reasons": reasons, "flagged": False}
    if kind == "sick" and days > SICK_CERTIFICATE_AFTER:
        reasons.append(f"More than {SICK_CERTIFICATE_AFTER} days: a medical certificate is required "
                       "(leave_policy.md > Sick leave)")
    reasons.append("Within the balance and policy limits.")
    return {"recommendation": "approve", "reasons": reasons, "flagged": False}
