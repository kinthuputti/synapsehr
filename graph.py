"""
graph.py - SynapseHR as a LangGraph multi-agent graph with human-in-the-loop pauses.

    message -> SUPERVISOR --> screening agent --+
                          --> leave agent ------+--> HUMAN CHECKPOINT (the graph PAUSES here)
                          --> policy agent --> answer with its source
                                           --> not in the policies -> escalation
                          --> unknown message -> escalation (a person takes over)

What "agent" means here: each specialist is a graph node with one job. The supervisor and the
specialists use plain rules by default; Gemini can optionally read resumes and write grounded
policy answers. They are not free-roaming LLM agents, and that is deliberate for HR decisions.

The pause: the checkpoint node calls interrupt(). The graph stops, keeps its state, and carries on
only when a person's decision is passed back in. The saved state lives in memory (MemorySaver),
so a pause does not survive closing the program.
"""
import re
from typing import TypedDict

import pandas as pd
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import checkpoint
import hiring
import leave_agent
import leave_records
import policy_agent
from jobs import get_job
from router import route
from pydantic import ValidationError
from schemas import HumanDecision
from scorer import score

RESUME_FILES = ["data/sample/resume_sample.csv", "data/resume/Resume/Resume.csv", "demo/resumes.csv"]   # demo/ holds fictional candidates
LEAVE_CHOICES = ("approve", "deny", "escalate")
NOT_SURE = "I am not sure what this is, so a human will take over."


class State(TypedDict, total=False):
    message: str
    employee_id: str
    intent: str
    route_reason: str
    kind: str
    subject_id: str
    recommendation: str
    reasons: list
    flagged: bool
    choices: tuple
    extra: dict
    context: dict
    candidate: dict
    approve_blocked: str
    answer: str
    answered: bool
    outcome: dict
    escalated: bool


def find_resume(resume_id):
    """Text of one resume by ID, from the sample or the full dataset (None if not found)."""
    for path in RESUME_FILES:
        try:
            df = pd.read_csv(path, dtype={"ID": str})
        except FileNotFoundError:
            continue
        row = df[df["ID"] == str(resume_id)]
        if not row.empty:
            return str(row.iloc[0]["Resume_str"])
    return None


def get_resume(resume_id):
    """{'resume_id', 'category', 'source', 'text'} for one resume (None if not found)."""
    for path in RESUME_FILES:
        try:
            df = pd.read_csv(path, dtype={"ID": str})
        except FileNotFoundError:
            continue
        row = df[df["ID"] == str(resume_id)]
        if not row.empty:
            r = row.iloc[0]
            return {"resume_id": str(resume_id), "category": str(r.get("Category", "")),
                    "source": "demo" if path.startswith("demo") else "dataset", "text": str(r["Resume_str"])}
    return None


def list_resumes(limit=40):
    """[{'resume_id', 'category', 'source'}] for HR to pick from: the fictional demo candidates first, then the start of
    any real dataset that has been downloaded."""
    out, seen = [], set()
    for path in reversed(RESUME_FILES):
        try:
            df = pd.read_csv(path, dtype={"ID": str}, usecols=["ID", "Category"])
        except (FileNotFoundError, ValueError):
            continue
        for _, row in df.head(limit).iterrows():
            if row["ID"] not in seen:
                seen.add(row["ID"])
                out.append({"resume_id": row["ID"], "category": str(row["Category"]),
                            "source": "demo" if path.startswith("demo") else "dataset"})
    return out


def live_leave_case(message, employee_id, employees):
    """Judge a leave request against the employee's CURRENT record (approvals made since it was sent count).
    'blocked' says why it must not be approved, or None."""
    request = leave_agent.parse_request(message)
    record = leave_records.employee_record(employee_id, employees)
    result = leave_agent.evaluate(request, record)
    kind, days = request["kind"], request["days"]
    extra, blocked = {}, None
    if kind in ("annual", "sick"):
        if record is None:
            blocked = f"{employee_id} is not in the records, so this cannot be approved."
        elif not days:
            blocked = "The number of days could not be read, so this cannot be approved."
        else:
            extra = {"leave_kind": kind, "days": days}
            left = record[f"{kind}_balance"]
            if days > left:
                blocked = (f"{employee_id} has only {left} {kind} leave day{'' if left == 1 else 's'} left and this "
                           f"request is for {days}, so it cannot be approved.")
    return {"recommendation": result["recommendation"], "reasons": result["reasons"], "flagged": result["flagged"],
            "extra": extra, "blocked": blocked, "context": leave_records.case_context(employee_id, record, kind)}


def build_graph(reader="rule", use_llm=False, checkpointer=None):
    """reader: 'rule' or 'llm' (resume reading). use_llm: let Gemini write the policy answers."""
    if reader == "llm":
        from llm_reader import llm_read_resume as read_resume
    else:
        from reader import read_resume
    index = policy_agent.PolicyIndex("policies")
    employees = leave_agent.load_employees()

    # ---- the supervisor ----
    def supervisor(state):
        intent, why = route(state["message"])
        return {"intent": intent, "route_reason": why}

    def after_supervisor(state):
        return {"screening": "screening_agent", "leave_request": "leave_agent", "policy_question": "policy_agent",
                "hiring_decision": "hiring_agent"}.get(state["intent"], "escalation")

    # ---- specialist agents ----
    def screening_agent(state):
        resume = re.search(r"\b(\d{5,9})\b", state["message"])
        job = re.search(r"job\s*#?\s*(\d+)", state["message"], re.IGNORECASE)
        if not resume:
            return {"answer": "Tell me which resume, for example: screen resume 70089206 for job 1."}
        text = find_resume(resume.group(1))
        if text is None:
            return {"answer": f"Resume {resume.group(1)} was not found in the data."}
        facts = read_resume(text)
        if facts.get("error"):
            return {"answer": f"The reader failed on this resume ({facts['error'][:120]}). Nothing was decided."}
        the_job = get_job(int(job.group(1)) if job else 1)
        result = score(facts, the_job)
        return {"kind": "resume_screening", "subject_id": resume.group(1),
                "recommendation": result["recommendation"], "flagged": result["needs_extra_scrutiny"],
                "reasons": [f"Job: {the_job['title']}. Score {result['score']} out of 100.", *result["reasons"]],
                "choices": checkpoint.SCREENING_CHOICES,
                "extra": {"job_id": the_job["job_id"], "agent_score": result["score"]}}

    def hiring_node(state):
        candidate_id = int(re.search(r"candidate\s+#?(\d+)", state["message"], re.IGNORECASE).group(1))
        if not hiring.available():
            return {"answer": "Hiring decisions need the web service's database, so they cannot be made from the command line."}
        context = hiring.candidate_context(candidate_id)
        if context is None:
            return {"answer": f"There is no candidate {candidate_id}."}
        problem = hiring.decision_problem(context)
        if problem:
            return {"answer": problem}
        verdict = hiring.judge(context)
        return {"kind": "hiring_decision", "subject_id": str(candidate_id), "recommendation": verdict["recommendation"],
                "reasons": verdict["reasons"], "flagged": verdict["flagged"], "choices": hiring.HIRING_CHOICES,
                "extra": {"candidate_id": candidate_id, "job_id": context["job_id"], "average_rating": verdict["average"]},
                "candidate": context}

    def leave_node(state):
        live = live_leave_case(state["message"], state["employee_id"], employees)
        return {"kind": "leave_request", "subject_id": state["employee_id"],
                "recommendation": live["recommendation"], "reasons": live["reasons"],
                "flagged": live["flagged"], "choices": LEAVE_CHOICES, "extra": live["extra"],
                "context": live["context"], "approve_blocked": live["blocked"]}

    def policy_node(state):
        mine = leave_records.personal_answer(
            state["message"], leave_records.employee_record(state["employee_id"], employees))
        if mine:                                   # "how many sick days do I get?" -> from the asker's own record
            checkpoint.log_event("policy_answer", state["employee_id"], question=state["message"],
                                 mode="personal", sources=mine["sources"], answered=True)
            return {"answer": mine["answer"], "answered": True}
        out = policy_agent.answer(state["message"], index, use_llm=use_llm)
        if out["answered"]:
            checkpoint.log_event("policy_answer", state["employee_id"], question=state["message"],
                                 mode=out["mode"], sources=out["sources"], answered=True)
        return {"answer": out["answer"], "answered": out["answered"]}

    def has_a_proposal(state):          # screening and leave end at the checkpoint, the rest may end here
        return "human_checkpoint" if state.get("recommendation") else END

    def after_policy(state):
        return END if state.get("answered") else "escalation"

    # ---- the human checkpoint: the graph pauses here ----
    def human_checkpoint(state):
        payload = {"kind": state["kind"], "subject_id": state["subject_id"],
                   "recommendation": state["recommendation"], "reasons": state["reasons"],
                   "flagged": state.get("flagged", False), "choices": list(state["choices"]),
                   "context": state.get("context"), "candidate": state.get("candidate"),
                   "approve_blocked": state.get("approve_blocked")}
        error = None
        while True:
            # A refused decision pauses again, with the reason. Raising here would leave the case stuck:
            # LangGraph would keep replaying the refused answer instead of waiting for a new one.
            raw = interrupt(dict(payload, error=error))
            try:
                decision = HumanDecision.model_validate(raw).model_dump()       # Pydantic: shape and types
            except ValidationError:
                error = "That decision was not understood."
                continue
            final = decision["final"]
            if final not in state["choices"]:
                error = f"Decision must be one of {list(state['choices'])}, got {final!r}."
                continue
            recommendation, extra = state["recommendation"], state.get("extra", {})
            if state["kind"] == "leave_request":
                live = live_leave_case(state["message"], state["subject_id"], employees)   # the record as it is now
                recommendation, extra = live["recommendation"], live["extra"]
                if final == "approve" and live["blocked"]:
                    error = live["blocked"]
                    continue
            break
        entry = checkpoint.record_decision(state["kind"], state["subject_id"], recommendation, final,
                                           decision.get("note", ""), state.get("flagged", False),
                                           decision.get("mode", "human"),
                                           **extra, **({"reviewer": decision["reviewer"]} if decision.get("reviewer") else {}))
        if state["kind"] == "leave_request" and final == "approve" and extra.get("days"):
            leave_records.record_approved_leave(state["subject_id"], extra["leave_kind"], extra["days"])
        by = decision.get("reviewer") or ""
        if state["kind"] == "resume_screening":              # the decision makes (or updates) a candidate
            hiring.record_screening(state["subject_id"], extra.get("job_id"), final, extra.get("agent_score"), by=by)
        elif state["kind"] == "hiring_decision":             # the decision moves the candidate
            hiring.apply_decision(int(state["subject_id"]), final, by=by)
        return {"outcome": entry}

    def escalation(state):
        checkpoint.log_event("escalation", state.get("employee_id", "?"), message=state["message"],
                             reason=state.get("route_reason") or "not covered by the policy documents")
        return {"answer": state.get("answer") or NOT_SURE, "escalated": True}

    g = StateGraph(State)
    for name, node in (("supervisor", supervisor), ("screening_agent", screening_agent), ("leave_agent", leave_node),
                       ("hiring_agent", hiring_node),
                       ("policy_agent", policy_node), ("human_checkpoint", human_checkpoint),
                       ("escalation", escalation)):
        g.add_node(name, node)
    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", after_supervisor,
                            ["screening_agent", "leave_agent", "policy_agent", "hiring_agent", "escalation"])
    g.add_conditional_edges("screening_agent", has_a_proposal, ["human_checkpoint", END])
    g.add_conditional_edges("leave_agent", has_a_proposal, ["human_checkpoint", END])
    g.add_conditional_edges("hiring_agent", has_a_proposal, ["human_checkpoint", END])
    g.add_conditional_edges("policy_agent", after_policy, ["escalation", END])
    g.add_edge("human_checkpoint", END)
    g.add_edge("escalation", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())


def run_request(app, message, employee_id, thread_id, decide):
    """Send one message through the graph. Whenever it pauses for a person, decide(payload) supplies
    the answer: a dict with 'final', and optionally 'note' and 'mode'."""
    config = {"configurable": {"thread_id": thread_id}}
    out = app.invoke({"message": message, "employee_id": employee_id}, config)
    while "__interrupt__" in out:
        out = app.invoke(Command(resume=decide(out["__interrupt__"][0].value)), config)
    return out
