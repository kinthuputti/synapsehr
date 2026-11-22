"""
leave_records.py - what a reviewer needs to see next to a leave request: the employee's balances,
their leave history this year, and the policy text the agent's rules come from.

Records of leave approved through the API are kept in the SQLite database (table leave_ledger) on top
of the fictional starting records in demo/employees.json: an approval adds a history entry and
lowers the balance, so the next request is judged against the new balance. Without SYNAPSEHR_DB
(command-line runs, unit tests) only the starting records are used and nothing is written.

ENTITLEMENT mirrors policies/leave_policy.md (18 annual, 10 sick), like the rules in leave_agent.py.
"""
import calendar
import copy
import os
import re
import sqlite3
from datetime import date
from pathlib import Path

ENTITLEMENT = {"annual": 18, "sick": 10}
POLICY_FILE = Path("policies") / "leave_policy.md"
POLICY_SECTIONS = {"annual": ["Annual leave", "Carry over"], "sick": ["Sick leave"], "parental": ["Parental leave"]}


def _db():
    return os.environ.get("SYNAPSEHR_DB")


def _connect(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS leave_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "employee_id TEXT, kind TEXT, days INTEGER, decided_on TEXT)")
    return conn


def employee_record(employee_id, base):
    """The employee's record with approved leave applied (a copy; None if the employee is unknown)."""
    if employee_id not in base:
        return None
    record = copy.deepcopy(base[employee_id])
    record["history"] = [dict(h, source="records") for h in record.get("history", [])]
    db = _db()
    if db:
        with _connect(db) as conn:
            rows = conn.execute("SELECT kind, days, decided_on FROM leave_ledger WHERE employee_id=? ORDER BY id",
                                (employee_id,)).fetchall()
        for kind, days, decided_on in rows:
            record[f"{kind}_balance"] -= days
            record["history"].append({"date": decided_on, "kind": kind, "days": days, "source": "approved here"})
    record["history"].sort(key=lambda h: h["date"], reverse=True)
    return record


def record_approved_leave(employee_id, kind, days):
    """Remember an approval (only when running under the API, where there is a database)."""
    db = _db()
    if not db or kind not in ENTITLEMENT or not days:
        return
    with _connect(db) as conn:
        conn.execute("INSERT INTO leave_ledger (employee_id, kind, days, decided_on) VALUES (?,?,?,?)",
                     (employee_id, kind, int(days), date.today().isoformat()))


def policy_excerpts(kind, path=POLICY_FILE):
    """The policy sections that apply to this kind of leave, as [{'source', 'text'}]."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    sections = {m.group(1).strip(): m.group(2).strip()
                for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, re.S | re.M)}
    return [{"source": f"{Path(path).name} > {h}", "text": sections[h]}
            for h in POLICY_SECTIONS.get(kind, []) if h in sections]


def case_context(employee_id, record, kind):
    """What the reviewer sees beside the recommendation (None when the employee is unknown)."""
    if record is None:
        return None
    return {"employee": {"employee_id": employee_id, "manager": record.get("manager", ""), "hire_date": record.get("hire_date"),
                         "annual_balance": record["annual_balance"], "annual_entitlement": ENTITLEMENT["annual"],
                         "sick_balance": record["sick_balance"], "sick_entitlement": ENTITLEMENT["sick"]},
            "history": record["history"],
            "policy": policy_excerpts(kind)}


# ---------------------------------------------------------------------------------------------
# Questions about *me*: "how many sick days do I get?" is answered from the employee's own record
# ---------------------------------------------------------------------------------------------
FIRST_PERSON = re.compile(r"\b(i|i'm|i've|me|my|mine)\b", re.I)
ABOUT_AMOUNT = re.compile(r"\bhow (?:many|much)\b|\bbalance\b|\bleft\b|\bremaining\b|\bremain\b|\bentitled\b|"
                          r"\ballowance\b|\bhave i (?:used|taken)\b|\bused\b", re.I)
SICK = re.compile(r"\bsick\b|\bunwell\b|\billness\b", re.I)
ANNUAL = re.compile(r"\bannual\b|\bvacation\b|\bholidays?\b|\bpto\b", re.I)
ANY_LEAVE = re.compile(r"\bleaves?\b|\bdays? off\b|\btime off\b|\bdays\b", re.I)
ABOUT_SOMEONE_ELSE = re.compile(r"\b(colleague|coworker|co-worker|teammate|manager|boss|spouse|wife|husband|friend|"
                                r"staff|team|E\d{3,6})\b", re.I)


AT_ONCE = re.compile(r"\b(at once|in a row|consecutive|at a time|continuous|continuously)\b", re.I)


def _short(label, entitlement, left):
    used = entitlement - left
    tail = f"{left} left." if left >= 0 else f"{-left} over the usual limit."
    return f"{label}: {used} of {entitlement} days used, {tail}"


REMOTE = re.compile(r"work(?:ing)?\s+(?:from\s+home|remotely)|\bwfh\b|\bremote(?:ly)?\b", re.I)
PERMISSION = re.compile(r"\b(can|may|could|am|allowed|eligible|permitted|able|entitled)\b", re.I)
REMOTE_OTHER = re.compile(r"\b(equipment|laptop|internet|wi-?fi|vpn|hours|core|security|expense|reimburse\w*|stipend|desk)\b", re.I)
REMOTE_POLICY = Path("policies") / "remote_work_policy.md"


def remote_rules(path=REMOTE_POLICY):
    """(probation months, remote days per week), read from the policy text so the answer follows the document."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    months = re.search(r"probation period of (\d+) months?", text)
    days = re.search(r"up to (\d+) days? per week", text)
    return (int(months.group(1)) if months else 3), (int(days.group(1)) if days else 2)


def _add_months(d, n):
    year, month0 = divmod(d.month - 1 + n, 12)
    year, month = d.year + year, month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _long(d):
    return f"{d.day} {d.strftime('%B %Y')}"


def _remote_answer(question, record, today=None):
    """'Can I work from home?' answered from the asker's own hire date. None when it is another kind of question."""
    hired = record.get("hire_date")
    if (not hired or not FIRST_PERSON.search(question) or not PERMISSION.search(question)
            or REMOTE_OTHER.search(question) or ABOUT_SOMEONE_ELSE.search(question)):
        return None
    months, days = remote_rules()
    start = date.fromisoformat(hired)
    ends = _add_months(start, months)
    today = today or date.today()
    rule = f"work from home up to {_n(days, 'day')} per week with your manager's approval"
    if today >= ends:
        text = f"Yes. You joined on {_long(start)}, so you are past the {months}-month probation period. You may {rule}."
    else:
        text = (f"Not yet. You joined on {_long(start)}, so your {months}-month probation period ends on "
                f"{_long(ends)}. After that you may {rule}.")
    sources = ["remote_work_policy.md > Eligibility", "Your employment record"]
    return {"answer": text + "".join(f"  [source: {s}]" for s in sources), "sources": sources}


def _n(count, word):
    return f"{count} {word}" if abs(count) == 1 else f"{count} {word}s"


def _use(entitlement, left):
    used = entitlement - left
    if used <= 0:
        return f"You have not used any, so all {entitlement} days are still available."
    if left > 0:
        return f"You have used {_n(used, 'day')}, so you have {_n(left, 'day')} left."
    if left == 0:
        return f"You have used all {entitlement} days."
    return (f"You have used {_n(used, 'day')}, which is {-left} more than the usual {entitlement}. "
            "HR can tell you how that was handled.")


def personal_answer(question, record, today=None):
    """Answer a question about the asker's own leave from their record, or None if it is not that kind of question.
    Returns {'answer': text ending in [source: ...] tags, 'sources': [...]}. Only ever uses the asker's own record."""
    if record is None or not question:
        return None
    if REMOTE.search(question):                       # work-from-home questions never fall through to leave balances
        return _remote_answer(question, record, today)
    if not (FIRST_PERSON.search(question) and ABOUT_AMOUNT.search(question)):
        return None
    if ABOUT_SOMEONE_ELSE.search(question) or AT_ONCE.search(question):    # about a limit or another person, not my balance
        return None
    sick, annual = bool(SICK.search(question)), bool(ANNUAL.search(question))
    if not (sick or annual or ANY_LEAVE.search(question)):
        return None
    both = (sick and annual) or not (sick or annual)
    ann, sk = ENTITLEMENT["annual"], ENTITLEMENT["sick"]
    if both:
        text = (_short("Annual leave", ann, record["annual_balance"]) + " "
                + _short("Sick leave", sk, record["sick_balance"]))
        sources = ["leave_policy.md > Annual leave", "leave_policy.md > Sick leave", "Your leave record"]
    elif sick:
        text = f"Employees usually get {sk} days of paid sick leave per year. " + _use(sk, record["sick_balance"])
        sources = ["leave_policy.md > Sick leave", "Your leave record"]
    else:
        text = (f"Full-time employees usually get {ann} days of annual leave per year. "
                + _use(ann, record["annual_balance"]))
        sources = ["leave_policy.md > Annual leave", "Your leave record"]
    return {"answer": text + "".join(f"  [source: {s}]" for s in sources), "sources": sources}
