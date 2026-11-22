"""
api.py - SynapseHR as an asynchronous FastAPI service, with authentication and a review web page.

    uvicorn api:app --reload        then open http://127.0.0.1:8000

POST /requests              send a message; the graph runs, and either answers or PAUSES for a person
GET  /requests              your own requests (a reviewer sees all of them)
GET  /pending               [reviewer] every request waiting for a decision, judged against the CURRENT records
POST /decisions/{thread_id} [reviewer] the decision resumes the paused graph (approving beyond the balance is refused)
GET  /audit                 [reviewer] the audit log
GET  /me                    who the API key belongs to

Paused graphs are stored in SQLite (AsyncSqliteSaver), so a pause survives a restart of the server.
"""
import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import aiosqlite
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

DB_PATH = os.environ.setdefault("SYNAPSEHR_DB", "synapsehr.db")

import checkpoint  # noqa: E402
import hiring  # noqa: E402
import config  # noqa: E402,F401
import leave_agent  # noqa: E402
import leave_records  # noqa: E402
from jobs import JOBS  # noqa: E402
from answers import split_answer  # noqa: E402
from auth import User, current_user, load_users, require_reviewer  # noqa: E402
from graph import build_graph, get_resume, list_resumes, live_leave_case  # noqa: E402
from router import route  # noqa: E402
from schemas import (CandidateDetail, CandidateRow, DecisionIn, EmployeeDetail, FeedbackIn, InterviewIn, EmployeeRow, JobOut, Me, PendingItem, Proposal,  # noqa: E402
                     RequestIn, RequestOut, ResumeOut, ResumeText, ThreadSummary)

SCHEMA = """CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY, owner TEXT, message TEXT, status TEXT, created_at TEXT,
    intent TEXT, answer TEXT, proposal TEXT, outcome TEXT, sources TEXT)"""
COLUMNS = "thread_id, owner, message, status, created_at, intent, answer, proposal, outcome, sources"


@asynccontextmanager
async def lifespan(app):
    app.state.users, generated = load_users()
    if generated:
        print("\nSynapseHR demo tokens (set SYNAPSEHR_TOKENS to choose your own):")
        for token, user in app.state.users.items():
            print(f"  {user.user_id:<6} {user.role:<9} {token}")
        print()
    async with aiosqlite.connect(DB_PATH) as db, AsyncSqliteSaver.from_conn_string(DB_PATH) as saver:
        await db.execute(SCHEMA)
        existing = [r[1] for r in await (await db.execute("PRAGMA table_info(threads)")).fetchall()]
        if "sources" not in existing:                     # database made by an older version
            await db.execute("ALTER TABLE threads ADD COLUMN sources TEXT")
        await db.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                         "time TEXT, kind TEXT, subject_id TEXT, entry TEXT)")
        await db.commit()
        app.state.db = db
        app.state.employees = leave_agent.load_employees()
        app.state.decide_lock = asyncio.Lock()            # one decision at a time: balances cannot be overspent
        app.state.graph = build_graph(checkpointer=saver)
        yield


app = FastAPI(title="SynapseHR", lifespan=lifespan)


def _cfg(thread_id):
    return {"configurable": {"thread_id": thread_id}}


def _to_out(thread_id, out):
    if "__interrupt__" in out:
        return RequestOut(thread_id=thread_id, status="awaiting_human", intent=out.get("intent"),
                          route_reason=out.get("route_reason"),
                          proposal=Proposal.model_validate(out["__interrupt__"][0].value))
    answer, sources = split_answer(out.get("answer"))
    return RequestOut(thread_id=thread_id, status="passed_to_hr" if out.get("escalated") else "completed",
                      intent=out.get("intent"), route_reason=out.get("route_reason"),
                      answer=answer or None, sources=sources, outcome=out.get("outcome"))


def _refreshed(proposal, message):
    """A paused case as it stands now: a leave case is re-judged against the employee's current record,
    and every case says which other reviewers could decide it."""
    others = sorted({u.user_id for u in app.state.users.values()
                     if u.role == "reviewer" and u.user_id != proposal["subject_id"]})
    proposal = dict(proposal, other_reviewers=others)
    if proposal["kind"] != "leave_request":
        return proposal
    live = live_leave_case(message, proposal["subject_id"], app.state.employees)
    return dict(proposal, recommendation=live["recommendation"], reasons=live["reasons"], flagged=live["flagged"],
                context=live["context"], approve_blocked=live["blocked"])


@app.get("/me", response_model=Me)
async def me(user: User = Depends(current_user)):
    return Me(user_id=user.user_id, role=user.role)


@app.post("/requests", response_model=RequestOut)
async def create_request(body: RequestIn, user: User = Depends(current_user)):
    return await _start(body.message, user)


async def _start(message, user):
    """Run one message through the graph for this user, and file the result."""
    body = type("Body", (), {"message": message})                 # the checks below read body.message
    intent = route(body.message)[0]
    if user.role == "employee" and intent == "screening":
        raise HTTPException(403, "resume screening is an HR function and needs the reviewer role")
    if user.role == "employee" and intent == "hiring_decision":
        raise HTTPException(403, "hiring decisions are an HR function and need the reviewer role")
    if intent == "leave_request" and user.user_id not in app.state.employees:
        raise HTTPException(422, f"There is no leave record for {user.user_id}, so a leave request cannot be made from "
                                 "this account. Leave requests are made by employees; ask HR to add a record if you should have one.")
    if intent == "leave_request":
        problem = leave_agent.request_problem(body.message)
        if problem:                                       # ask the employee now, instead of sending HR a case it cannot use
            raise HTTPException(422, problem)
    thread_id = uuid.uuid4().hex[:12]
    out = await app.state.graph.ainvoke({"message": body.message, "employee_id": user.user_id}, _cfg(thread_id))
    result = _to_out(thread_id, out)
    await app.state.db.execute(
        f"INSERT INTO threads ({COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (thread_id, user.user_id, body.message, result.status, datetime.now().isoformat(timespec="seconds"),
         result.intent, result.answer, result.proposal.model_dump_json() if result.proposal else None,
         json.dumps(result.outcome) if result.outcome else None, json.dumps(result.sources)))
    await app.state.db.commit()
    if user.role == "employee":                           # the agent's recommendation is for the reviewer, not the requester
        result = result.model_copy(update={"proposal": None})
    return result


def _summary(row, show_proposal):
    thread_id, owner, message, status, created, intent, answer, proposal, outcome, sources = row
    return ThreadSummary(thread_id=thread_id, owner=owner, message=message, created_at=created, status=status,
                         intent=intent, answer=answer, outcome=json.loads(outcome) if outcome else None,
                         sources=json.loads(sources) if sources else [],
                         proposal=(Proposal.model_validate(_refreshed(json.loads(proposal), message))
                                   if (proposal and show_proposal and status == "awaiting_human") else None))


@app.get("/requests", response_model=list[ThreadSummary])
async def my_requests(user: User = Depends(current_user)):
    reviewer = user.role == "reviewer"
    cur = await app.state.db.execute(
        f"SELECT {COLUMNS} FROM threads " + ("" if reviewer else "WHERE owner=? ") + "ORDER BY created_at DESC, rowid DESC LIMIT 200",
        () if reviewer else (user.user_id,))
    return [_summary(r, show_proposal=reviewer) for r in await cur.fetchall()]


@app.get("/pending", response_model=list[PendingItem])
async def pending(user: User = Depends(require_reviewer)):
    cur = await app.state.db.execute(
        "SELECT thread_id, owner, message, created_at, proposal FROM threads "
        "WHERE status='awaiting_human' ORDER BY created_at, rowid")
    return [PendingItem(thread_id=t, employee_id=e, message=m, created_at=c,
                        proposal=_refreshed(json.loads(p), m))
            for t, e, m, c, p in await cur.fetchall()]


@app.post("/decisions/{thread_id}", response_model=RequestOut)
async def decide(thread_id: str, body: DecisionIn, user: User = Depends(require_reviewer)):
    async with app.state.decide_lock:
        cur = await app.state.db.execute(
            "SELECT proposal, message FROM threads WHERE thread_id=? AND status='awaiting_human'", (thread_id,))
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(404, "no paused request with this id (unknown, or already decided)")
        proposal, message = _refreshed(json.loads(row[0]), row[1]), row[1]
        if proposal["kind"] == "hiring_decision":              # the candidate may have been decided in the meantime
            context = await asyncio.to_thread(hiring.candidate_context, int(proposal["subject_id"]))
            if context is None or context["stage"] != "interviewing":
                what = f"This candidate {hiring.STAGE_PHRASE[context['stage']]}" if context else "This candidate no longer exists"
                raise HTTPException(409, f"{what}, so this decision is no longer needed.")
        if proposal["subject_id"] == user.user_id:        # nobody approves their own request
            raise HTTPException(403, "you cannot decide a case about yourself; another reviewer must")
        if body.final not in proposal["choices"]:         # refuse BEFORE touching the paused graph
            raise HTTPException(422, f"decision must be one of {proposal['choices']}")
        if body.final == "approve" and proposal.get("approve_blocked"):
            raise HTTPException(409, proposal["approve_blocked"])
        out = await app.state.graph.ainvoke(
            Command(resume={"final": body.final, "note": body.note, "mode": "human", "reviewer": user.user_id}),
            _cfg(thread_id))
        if "__interrupt__" in out:                         # the checkpoint refused it and is waiting for another answer
            raise HTTPException(409, out["__interrupt__"][0].value.get("error") or "that decision was refused")
        await app.state.db.execute("UPDATE threads SET status='decided', outcome=? WHERE thread_id=?",
                                   (json.dumps(out.get("outcome")), thread_id))
        await app.state.db.commit()
        return _to_out(thread_id, out)


# ---------- HR tools (reviewers only) ----------
def _facts_and_history(employee_id):
    record = leave_records.employee_record(employee_id, app.state.employees)
    if record is None:
        return None, None
    return leave_records.case_context(employee_id, record, "annual")["employee"], record["history"]


@app.get("/employees", response_model=list[EmployeeRow])
async def employees(user: User = Depends(require_reviewer)):
    cur = await app.state.db.execute(
        "SELECT owner, COUNT(*) FROM threads WHERE status='awaiting_human' GROUP BY owner")
    waiting = dict(await cur.fetchall())
    rows = []
    for employee_id in sorted(app.state.employees):
        facts, _ = _facts_and_history(employee_id)
        rows.append(EmployeeRow(**facts, waiting=waiting.get(employee_id, 0)))
    return rows


@app.get("/employees/{employee_id}", response_model=EmployeeDetail)
async def employee(employee_id: str, user: User = Depends(require_reviewer)):
    facts, history = _facts_and_history(employee_id)
    if facts is None:
        raise HTTPException(404, f"no employee record for {employee_id}")
    checkpoint.log_event("record_view", employee_id, viewer=user.user_id)      # personal data: every look is logged
    cur = await app.state.db.execute(
        f"SELECT {COLUMNS} FROM threads WHERE owner=? ORDER BY created_at DESC, rowid DESC LIMIT 50", (employee_id,))
    return EmployeeDetail(employee=facts, history=history,
                          requests=[_summary(r, show_proposal=False) for r in await cur.fetchall()])


@app.get("/jobs", response_model=list[JobOut])
async def jobs(user: User = Depends(require_reviewer)):
    return [JobOut(**{k: j[k] for k in ("job_id", "title", "min_years", "must_have", "nice_to_have")}) for j in JOBS]


@app.get("/resumes", response_model=list[ResumeOut])
async def resumes(user: User = Depends(require_reviewer)):
    return list_resumes()


@app.get("/resumes/{resume_id}", response_model=ResumeText)
async def resume(resume_id: str, user: User = Depends(require_reviewer)):
    found = get_resume(resume_id)
    if found is None:
        raise HTTPException(404, f"resume {resume_id} was not found")
    checkpoint.log_event("record_view", resume_id, viewer=user.user_id)        # an applicant's data: every look is logged
    return ResumeText(**found)


# ---------- candidates and interviews (reviewers only) ----------
def _interviewers():
    return sorted({u.user_id for u in app.state.users.values() if u.role == "reviewer"})


async def _candidate_detail(candidate_id):
    row = await asyncio.to_thread(hiring.get_candidate, candidate_id)
    if row is None:
        raise HTTPException(404, f"There is no candidate {candidate_id}.")
    interviews = await asyncio.to_thread(hiring.interviews_of, candidate_id)
    others = await asyncio.to_thread(hiring.other_applications, row["resume_id"], candidate_id)
    resume = get_resume(row["resume_id"])
    return CandidateDetail(candidate=CandidateRow(**row), category=resume["category"] if resume else "",
                           interviews=interviews, other_applications=[CandidateRow(**o) for o in others],
                           interviewers=_interviewers(), kinds=list(hiring.KINDS))


async def _hiring(fn, *args, **kwargs):
    """Call a hiring rule; a refusal becomes a clear message for the person."""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except hiring.HiringError as e:
        text = str(e)
        raise HTTPException(403 if text.startswith("Only the interviewer") else 404 if text.startswith("There is no") else 422, text)


@app.get("/candidates", response_model=list[CandidateRow])
async def candidates(user: User = Depends(require_reviewer)):
    return [CandidateRow(**c) for c in await _hiring(hiring.list_candidates)]


@app.get("/candidates/{candidate_id}", response_model=CandidateDetail)
async def candidate(candidate_id: int, user: User = Depends(require_reviewer)):
    return await _candidate_detail(candidate_id)


@app.post("/candidates/{candidate_id}/interviews", response_model=CandidateDetail)
async def schedule(candidate_id: int, body: InterviewIn, user: User = Depends(require_reviewer)):
    await _hiring(hiring.schedule_interview, candidate_id, body.kind, body.scheduled_for, body.interviewer,
                  set(_interviewers()), user.user_id)
    return await _candidate_detail(candidate_id)


@app.post("/interviews/{interview_id}/feedback", response_model=CandidateDetail)
async def feedback(interview_id: int, body: FeedbackIn, user: User = Depends(require_reviewer)):
    candidate_id = await _hiring(hiring.add_feedback, interview_id, user.user_id, body.rating, body.feedback)
    return await _candidate_detail(candidate_id)


@app.post("/interviews/{interview_id}/cancel", response_model=CandidateDetail)
async def cancel(interview_id: int, user: User = Depends(require_reviewer)):
    candidate_id = await _hiring(hiring.cancel_interview, interview_id, user.user_id)
    return await _candidate_detail(candidate_id)


@app.post("/candidates/{candidate_id}/decision-request", response_model=RequestOut)
async def decision_request(candidate_id: int, user: User = Depends(require_reviewer)):
    """Ask for the hiring decision: the agent recommends from the interview ratings, a reviewer decides."""
    context = await _hiring(hiring.candidate_context, candidate_id)
    if context is None:
        raise HTTPException(404, f"There is no candidate {candidate_id}.")
    problem = hiring.decision_problem(context)
    if problem:
        raise HTTPException(409, problem)
    message = f"hiring decision for candidate {candidate_id}"
    cur = await app.state.db.execute("SELECT 1 FROM threads WHERE message=? AND status='awaiting_human'", (message,))
    if await cur.fetchone():
        raise HTTPException(409, "A hiring decision for this candidate is already waiting in the review queue.")
    return await _start(message, user)


@app.get("/audit")
async def audit(limit: int = 50, user: User = Depends(require_reviewer)):
    cur = await app.state.db.execute("SELECT entry FROM audit ORDER BY id DESC LIMIT ?", (min(limit, 500),))
    return [json.loads(r[0]) for r in await cur.fetchall()]


WEB = Path(__file__).parent / "web"
if WEB.exists():                                          # mounted last, so the API routes above win
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
