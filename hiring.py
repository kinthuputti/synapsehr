"""
hiring.py - candidates, interviews, and the facts behind a hiring decision.

A resume becomes a CANDIDATE when a reviewer records a screening decision for it. HR then schedules interviews, the
assigned interviewer records feedback and a rating, and the final hiring decision goes through the same human
checkpoint as everything else (hiring_agent -> reviewer -> offer, reject or hold).

Stored in the same SQLite database as the rest (SYNAPSEHR_DB). Without it (command line) nothing is stored.

Rules, enforced here so every caller gets them:
  - interviews can only be scheduled for shortlisted candidates, with a listed interviewer, not in the past
    and at most 90 days ahead, not overlapping another interview of the same interviewer or the same candidate
    (one hour slots), and at most one interview per round (phone screen, technical, final): a cancelled one does
    not count, so it can be booked again
  - only the assigned interviewer can record feedback, once the interview has started: rating 1 to 5 and a written note
  - a hiring decision needs at least one finished interview and none still scheduled
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

import checkpoint
from jobs import get_job

KINDS = ("phone screen", "technical", "final")
STAGE_AFTER_SCREENING = {"shortlist": "shortlisted", "review": "needs_review", "reject": "rejected"}
HIRING_CHOICES = ("offer", "reject", "hold")
STAGE_PHRASE = {"shortlisted": "is shortlisted", "needs_review": "is waiting for review", "interviewing": "is being interviewed",
                "offer": "has already been given an offer", "rejected": "has been rejected"}
SLOT = timedelta(minutes=60)
HORIZON = timedelta(days=90)
PAST_GRACE = timedelta(minutes=5)


class HiringError(ValueError):
    """Something the caller did that the rules do not allow. The message is written for the person."""


def available():
    return bool(os.environ.get("SYNAPSEHR_DB"))


@contextmanager
def _tx():
    path = os.environ.get("SYNAPSEHR_DB")
    if not path:
        raise HiringError("Candidate tracking needs the API database (SYNAPSEHR_DB is not set).")
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS candidates (candidate_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "resume_id TEXT NOT NULL, job_id INTEGER NOT NULL, stage TEXT NOT NULL, screening_decision TEXT, "
                 "screening_score INTEGER, created_on TEXT, UNIQUE (resume_id, job_id))")
    conn.execute("CREATE TABLE IF NOT EXISTS interviews (interview_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "candidate_id INTEGER NOT NULL, kind TEXT NOT NULL, scheduled_for TEXT NOT NULL, interviewer TEXT NOT NULL, "
                 "status TEXT NOT NULL, rating INTEGER, feedback TEXT, created_by TEXT)")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _now(now):
    return now or datetime.now().replace(second=0, microsecond=0)


def _when(text):
    try:
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        raise HiringError("Please give the interview time as a date and time, for example 2026-11-20T10:00.")


# ---------------------------------------------------------------- reading
def _interviews(conn, candidate_id):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM interviews WHERE candidate_id=? ORDER BY scheduled_for, interview_id", (candidate_id,))]


def _candidate(conn, candidate_id):
    row = conn.execute("SELECT * FROM candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
    return dict(row) if row else None


def _summary(conn, c):
    """The candidate row plus what the list needs: job title, interview counts, next interview, average rating."""
    items = [i for i in _interviews(conn, c["candidate_id"]) if i["status"] != "cancelled"]
    done = [i for i in items if i["status"] == "completed"]
    upcoming = [i["scheduled_for"] for i in items if i["status"] == "scheduled"]
    return dict(c, job_title=get_job(c["job_id"])["title"], interviews=len(items), completed=len(done),
                next_interview=min(upcoming) if upcoming else None,
                avg_rating=round(sum(i["rating"] for i in done) / len(done), 1) if done else None)


def get_candidate(candidate_id):
    with _tx() as conn:
        c = _candidate(conn, candidate_id)
        return _summary(conn, c) if c else None


def list_candidates():
    with _tx() as conn:
        return [_summary(conn, dict(r)) for r in conn.execute("SELECT * FROM candidates ORDER BY candidate_id DESC")]


def interviews_of(candidate_id):
    with _tx() as conn:
        return _interviews(conn, candidate_id)


def other_applications(resume_id, exclude_id):
    """The jobs the same resume applied for: whatever else this person is in the running for."""
    with _tx() as conn:
        return [_summary(conn, dict(r)) for r in conn.execute(
            "SELECT * FROM candidates WHERE resume_id=? AND candidate_id<>? ORDER BY candidate_id", (resume_id, exclude_id))]


def candidate_context(candidate_id):
    """Everything a reviewer needs beside a hiring recommendation (None if there is no such candidate)."""
    with _tx() as conn:
        c = _candidate(conn, candidate_id)
        if c is None:
            return None
        return {"candidate_id": c["candidate_id"], "resume_id": c["resume_id"], "job_id": c["job_id"],
                "job_title": get_job(c["job_id"])["title"], "stage": c["stage"],
                "screening_decision": c["screening_decision"], "screening_score": c["screening_score"],
                "interviews": [i for i in _interviews(conn, candidate_id) if i["status"] != "cancelled"]}


# ---------------------------------------------------------------- writing
def record_screening(resume_id, job_id, decision, score=None, by=""):
    """A reviewer decided on a screened resume: shortlist, review or reject. Creates or updates the candidate.
    A candidate already being interviewed or given an offer is never moved backwards by a re-screening."""
    if not available() or decision not in STAGE_AFTER_SCREENING:
        return None
    stage = STAGE_AFTER_SCREENING[decision]
    with _tx() as conn:
        row = conn.execute("SELECT * FROM candidates WHERE resume_id=? AND job_id=?", (str(resume_id), int(job_id))).fetchone()
        if row is None:
            cur = conn.execute("INSERT INTO candidates (resume_id, job_id, stage, screening_decision, screening_score, created_on) "
                               "VALUES (?,?,?,?,?,?)", (str(resume_id), int(job_id), stage, decision, score,
                                                        datetime.now().isoformat(timespec="seconds")))
            cid = cur.lastrowid
        elif row["stage"] in ("shortlisted", "needs_review", "rejected"):
            cid = row["candidate_id"]
            conn.execute("UPDATE candidates SET stage=?, screening_decision=?, screening_score=? WHERE candidate_id=?",
                         (stage, decision, score, cid))
        else:
            return dict(row)
        out = _candidate(conn, cid)
    checkpoint.log_event("candidate_stage", str(cid), resume_id=str(resume_id), job_id=int(job_id), stage=stage, by=by)
    return out


def schedule_interview(candidate_id, kind, when, interviewer, valid_interviewers, by="", now=None):
    now = _now(now)
    start = _when(when)
    if kind not in KINDS:
        raise HiringError(f"The interview type must be one of: {', '.join(KINDS)}.")
    if interviewer not in valid_interviewers:
        raise HiringError(f"{interviewer or 'That person'} cannot interview: choose one of {', '.join(sorted(valid_interviewers))}.")
    if start < now - PAST_GRACE:
        raise HiringError("That time has already passed. Choose a time from now on.")
    if start > now + HORIZON:
        raise HiringError("Interviews can be scheduled at most 90 days ahead.")
    with _tx() as conn:
        c = _candidate(conn, candidate_id)
        if c is None:
            raise HiringError(f"There is no candidate {candidate_id}.")
        if c["stage"] not in ("shortlisted", "interviewing"):
            raise HiringError(f"This candidate {STAGE_PHRASE[c['stage']]}. Interviews can only be scheduled for shortlisted candidates.")
        for other in conn.execute("SELECT i.*, c.job_id FROM interviews i JOIN candidates c USING (candidate_id) "
                                  "WHERE i.status='scheduled'"):
            if abs(_when(other["scheduled_for"]) - start) < SLOT:
                if other["interviewer"] == interviewer:
                    raise HiringError(f"{interviewer} already has an interview at {other['scheduled_for'].replace('T', ' ')}, which overlaps.")
                if other["candidate_id"] == candidate_id:
                    raise HiringError(f"This candidate already has an interview at {other['scheduled_for'].replace('T', ' ')}, which overlaps.")
        if conn.execute("SELECT 1 FROM interviews WHERE candidate_id=? AND kind=? AND status IN ('scheduled','completed')",
                        (candidate_id, kind)).fetchone():
            raise HiringError(f"This candidate already has a {kind} interview. Each round can only be booked once: "
                              "cancel the existing one first if it needs a new time.")
        cur = conn.execute("INSERT INTO interviews (candidate_id, kind, scheduled_for, interviewer, status, created_by) "
                           "VALUES (?,?,?,?, 'scheduled', ?)", (candidate_id, kind, start.isoformat(timespec="minutes"), interviewer, by))
        conn.execute("UPDATE candidates SET stage='interviewing' WHERE candidate_id=?", (candidate_id,))
        interview_id = cur.lastrowid
    checkpoint.log_event("interview_scheduled", str(candidate_id), interview_id=interview_id, interview_kind=kind,
                         scheduled_for=start.isoformat(timespec="minutes"), interviewer=interviewer, by=by)
    return interview_id


def add_feedback(interview_id, user_id, rating, feedback, now=None):
    now = _now(now)
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        raise HiringError("The rating must be a whole number from 1 to 5.")
    if len((feedback or "").strip()) < 10:
        raise HiringError("Please write a short note (at least 10 characters) explaining the rating.")
    with _tx() as conn:
        row = conn.execute("SELECT * FROM interviews WHERE interview_id=?", (interview_id,)).fetchone()
        if row is None:
            raise HiringError(f"There is no interview {interview_id}.")
        if row["status"] != "scheduled":
            raise HiringError(f"This interview is {row['status']}, so feedback cannot be recorded.")
        if row["interviewer"] != user_id:
            raise HiringError(f"Only the interviewer, {row['interviewer']}, can record feedback for this interview.")
        if _when(row["scheduled_for"]) > now:
            raise HiringError("This interview has not started yet. Feedback can be recorded once it has.")
        conn.execute("UPDATE interviews SET status='completed', rating=?, feedback=? WHERE interview_id=?",
                     (rating, feedback.strip(), interview_id))
        candidate_id = row["candidate_id"]
    checkpoint.log_event("interview_feedback", str(candidate_id), interview_id=interview_id, interviewer=user_id, rating=rating)
    return candidate_id


def cancel_interview(interview_id, by=""):
    with _tx() as conn:
        row = conn.execute("SELECT * FROM interviews WHERE interview_id=?", (interview_id,)).fetchone()
        if row is None:
            raise HiringError(f"There is no interview {interview_id}.")
        if row["status"] != "scheduled":
            raise HiringError(f"This interview is {row['status']}, so it cannot be cancelled.")
        conn.execute("UPDATE interviews SET status='cancelled' WHERE interview_id=?", (interview_id,))
        candidate_id = row["candidate_id"]
        live = conn.execute("SELECT COUNT(*) FROM interviews WHERE candidate_id=? AND status IN ('scheduled','completed')",
                            (candidate_id,)).fetchone()[0]
        if live == 0:
            conn.execute("UPDATE candidates SET stage='shortlisted' WHERE candidate_id=? AND stage='interviewing'", (candidate_id,))
    checkpoint.log_event("interview_cancelled", str(candidate_id), interview_id=interview_id, interview_kind=row["kind"], by=by)
    return candidate_id


# ---------------------------------------------------------------- the hiring decision
def decision_problem(context):
    """Why a hiring decision cannot be asked for yet, or None."""
    phrase = STAGE_PHRASE[context["stage"]]
    if context["stage"] in ("shortlisted", "needs_review"):
        return f"This candidate {phrase}: interviews have to take place before there is a hiring decision."
    if context["stage"] != "interviewing":
        return f"This candidate {phrase}, so there is nothing to decide."
    if any(i["status"] == "scheduled" for i in context["interviews"]):
        return "Finish or cancel the interviews that are still scheduled first."
    if not any(i["status"] == "completed" for i in context["interviews"]):
        return "No interview has been completed yet."
    return None


def judge(context):
    """The agent's recommendation from the interview ratings, with the reasons. It never decides anything."""
    done = [i for i in context["interviews"] if i["status"] == "completed"]
    if not done:
        return {"recommendation": "hold", "reasons": ["No interview has been completed yet."], "flagged": True, "average": None}
    ratings = [i["rating"] for i in done]
    avg = round(sum(ratings) / len(ratings), 1)
    reasons = [f"Average interview rating {avg} out of 5 from {_plural(len(done), 'interview')}."]
    decision = context.get("screening_decision")
    if decision:
        score = context.get("screening_score")
        reasons.append(f"Screening decision: {decision}" + (f", score {score} out of 100." if score is not None else "."))
    flagged = False
    if len(done) == 1:
        flagged = True
        reasons.append("Only one interview, so a second opinion would help.")
    if max(ratings) - min(ratings) >= 2:
        flagged = True
        reasons.append(f"The interviewers disagree: ratings run from {min(ratings)} to {max(ratings)}.")
    if avg >= 4 and decision == "shortlist":
        recommendation = "offer"
        reasons.append("Strong ratings on a shortlisted resume.")
    elif avg < 3:
        recommendation = "reject"
        reasons.append("The average rating is below 3.")
    else:
        recommendation = "hold"
        reasons.append("The ratings are in the middle, so more evidence is needed.")
    return {"recommendation": recommendation, "reasons": reasons, "flagged": flagged, "average": avg}


def apply_decision(candidate_id, final, by=""):
    """The reviewer's hiring decision moves the candidate: offer or reject. Hold leaves them where they are."""
    if not available() or final not in HIRING_CHOICES:
        return None
    with _tx() as conn:
        c = _candidate(conn, candidate_id)
        if c is None:
            return None
        stage = {"offer": "offer", "reject": "rejected"}.get(final, c["stage"])
        conn.execute("UPDATE candidates SET stage=? WHERE candidate_id=?", (stage, candidate_id))
    checkpoint.log_event("candidate_stage", str(candidate_id), resume_id=c["resume_id"], job_id=c["job_id"], stage=stage, by=by)
    return stage
