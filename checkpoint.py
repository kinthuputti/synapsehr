"""
checkpoint.py - the HUMAN CHECKPOINT and the audit log.
Nothing is final until a person approves, rejects or edits the recommendation. Every decision,
and every escalation, is written to audit/audit_log.jsonl. Only IDs are shown and logged
(no names, no resume text).

Three small steps, so they can be used on their own (the LangGraph version does this):
    show_recommendation -> ask_for_decision -> record_decision
request_approval() does all three in a row.
"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

AUDIT_FILE = Path("audit") / "audit_log.jsonl"
SCREENING_CHOICES = ("shortlist", "review", "reject")


def _write(entry):
    AUDIT_FILE.parent.mkdir(exist_ok=True)
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    db = os.environ.get("SYNAPSEHR_DB")          # set by the API: mirror the audit log into SQLite
    if db:
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                         "time TEXT, kind TEXT, subject_id TEXT, entry TEXT)")
            conn.execute("INSERT INTO audit (time, kind, subject_id, entry) VALUES (?,?,?,?)",
                         (entry["time"], entry["kind"], entry["subject_id"], json.dumps(entry)))


def log_event(kind, subject_id, **details):
    """Record something that needed no approval (a policy answer, an escalation)."""
    _write({"time": datetime.now().isoformat(timespec="seconds"), "kind": kind,
            "subject_id": str(subject_id), **details})


def show_recommendation(kind, subject_id, recommendation, reasons, flagged=False):
    print("\n" + "=" * 64)
    print(f"{kind.upper()} for {subject_id}")
    print(f"Agent recommends: {recommendation.upper()}")
    for reason in reasons:
        print("  -", reason)
    if flagged:
        print("  ! PLEASE CHECK THIS ONE YOURSELF (see the notes above).")


def ask_for_decision(recommendation, choices, auto=False):
    """Ask the person. Returns (final_decision, note, decided_by)."""
    if auto:                                           # demo/testing mode only
        return recommendation, "", "auto"
    while True:
        c = input("[a]pprove  [r]eject  [e]dit decision > ").strip().lower()
        if c == "a":
            return recommendation, "", "human"
        if c == "r" and "reject" in choices:
            return "reject", input("reason (optional) > ").strip(), "human"
        if c == "e":
            final = input(f"new decision {tuple(choices)} > ").strip().lower()
            if final in choices:
                return final, input("reason (optional) > ").strip(), "human"
            print("please type one of:", ", ".join(choices))


def record_decision(kind, subject_id, recommendation, final, note="", flagged=False, decided_by="human", **extra):
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, "subject_id": str(subject_id),
             "agent_recommendation": recommendation, "flagged_for_check": flagged, "final_decision": final,
             "overridden": final != recommendation, "note": note, "decided_by": decided_by, **extra}
    _write(entry)
    return entry


def request_approval(kind, subject_id, recommendation, reasons, choices, flagged=False, auto=False, **extra):
    """Show, ask and record, in one call (used by the plain-Python supervisor)."""
    show_recommendation(kind, subject_id, recommendation, reasons, flagged)
    final, note, mode = ask_for_decision(recommendation, choices, auto)
    return record_decision(kind, subject_id, recommendation, final, note, flagged, mode, **extra)


def ask_human(candidate_id, job, result, auto=False):
    """The screening version: one candidate, one job."""
    reasons = [f"Job: {job['title']}. Score {result['score']} out of 100.", *result["reasons"]]
    return request_approval("resume_screening", candidate_id, result["recommendation"], reasons,
                            SCREENING_CHOICES, result["needs_extra_scrutiny"], auto,
                            job_id=job["job_id"], agent_score=result["score"])
