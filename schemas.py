"""
schemas.py - Pydantic models: the validated shapes that cross every boundary
(HTTP in, HTTP out, the human's decision coming back into the paused graph).
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Kind = Literal["resume_screening", "leave_request", "hiring_decision"]


class RequestIn(BaseModel):
    """The sender is the signed-in user, never a field in the body (so nobody can send as someone else)."""
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def not_blank(cls, v):
        if not v.strip():
            raise ValueError("message must not be blank")
        return v.strip()


class InterviewOut(BaseModel):
    interview_id: int
    kind: str
    scheduled_for: str
    interviewer: str
    status: Literal["scheduled", "completed", "cancelled"]
    rating: Optional[int] = None
    feedback: Optional[str] = None


class CandidateContext(BaseModel):
    """What a reviewer needs beside a hiring recommendation."""
    candidate_id: int
    resume_id: str
    job_id: int
    job_title: str
    stage: str = ""
    screening_decision: Optional[str] = None
    screening_score: Optional[int] = None
    interviews: list[InterviewOut] = []


class HistoryItem(BaseModel):
    date: str
    kind: str
    days: int
    source: str = "records"


class PolicyExcerpt(BaseModel):
    source: str
    text: str


class EmployeeFacts(BaseModel):
    employee_id: str
    manager: str = ""
    hire_date: Optional[str] = None
    annual_balance: int
    annual_entitlement: int
    sick_balance: int
    sick_entitlement: int


class CaseContext(BaseModel):
    """What a reviewer needs beside a leave recommendation."""
    employee: EmployeeFacts
    history: list[HistoryItem] = []
    policy: list[PolicyExcerpt] = []


class Proposal(BaseModel):
    """What the graph shows a person when it pauses."""
    kind: Kind
    subject_id: str
    recommendation: str
    reasons: list[str]
    flagged: bool = False
    choices: list[str]
    context: Optional[CaseContext] = None
    approve_blocked: Optional[str] = None      # why "approve" is not allowed right now
    other_reviewers: list[str] = []            # who else could decide this case (never the person it is about)
    candidate: Optional[CandidateContext] = None   # hiring decisions: the candidate and their interviews


class DecisionIn(BaseModel):
    """What a reviewer sends over HTTP."""
    final: str = Field(min_length=1)
    note: str = Field(default="", max_length=1000)

    @field_validator("final")
    @classmethod
    def lowercase(cls, v):
        return v.strip().lower()


class HumanDecision(BaseModel):
    """What the paused graph receives. 'final' is checked against the proposal's choices at the checkpoint."""
    final: str = Field(min_length=1)
    note: str = Field(default="", max_length=1000)
    mode: Literal["human", "auto"] = "human"
    reviewer: str = ""

    @field_validator("final")
    @classmethod
    def lowercase(cls, v):
        return v.strip().lower()


class RequestOut(BaseModel):
    thread_id: str
    status: Literal["awaiting_human", "completed", "passed_to_hr"]
    intent: Optional[str] = None
    route_reason: Optional[str] = None
    answer: Optional[str] = None
    proposal: Optional[Proposal] = None
    outcome: Optional[dict] = None
    sources: list[str] = []


class PendingItem(BaseModel):
    thread_id: str
    employee_id: str
    message: str
    created_at: str
    proposal: Proposal


class ThreadSummary(BaseModel):
    thread_id: str
    owner: str
    message: str
    created_at: str
    status: Literal["awaiting_human", "completed", "decided", "passed_to_hr"]
    intent: Optional[str] = None
    answer: Optional[str] = None
    proposal: Optional[Proposal] = None     # reviewers only
    outcome: Optional[dict] = None
    sources: list[str] = []


class Me(BaseModel):
    user_id: str
    role: Literal["employee", "reviewer"]


class EmployeeRow(BaseModel):
    employee_id: str
    hire_date: Optional[str] = None
    manager: str = ""
    annual_balance: int
    annual_entitlement: int
    sick_balance: int
    sick_entitlement: int
    waiting: int = 0                        # leave requests still waiting for a decision


class EmployeeDetail(BaseModel):
    employee: EmployeeFacts
    history: list[HistoryItem] = []
    requests: list[ThreadSummary] = []


class JobOut(BaseModel):
    job_id: int
    title: str
    min_years: int
    must_have: list[str]
    nice_to_have: list[str]


class ResumeOut(BaseModel):
    resume_id: str
    category: str
    source: str


class ResumeText(ResumeOut):
    text: str


class CandidateRow(BaseModel):
    candidate_id: int
    resume_id: str
    job_id: int
    job_title: str
    stage: str
    screening_decision: Optional[str] = None
    screening_score: Optional[int] = None
    created_on: str = ""
    interviews: int = 0                     # not counting cancelled ones
    completed: int = 0
    next_interview: Optional[str] = None
    avg_rating: Optional[float] = None


class CandidateDetail(BaseModel):
    candidate: CandidateRow
    category: str = ""
    interviews: list[InterviewOut] = []
    other_applications: list[CandidateRow] = []    # the other jobs the same resume applied for
    interviewers: list[str] = []                   # who can be chosen to interview
    kinds: list[str] = []


class InterviewIn(BaseModel):
    kind: str = Field(min_length=1, max_length=30)
    scheduled_for: str = Field(min_length=10, max_length=32, description="e.g. 2026-11-20T10:00")
    interviewer: str = Field(min_length=1, max_length=40)


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    feedback: str = Field(min_length=10, max_length=2000)
