"""
run_synapsehr.py - SynapseHR v0.3: a supervisor that routes each message to a workflow.

    python run_synapsehr.py                 # interactive: you type requests
    python run_synapsehr.py --demo          # runs a fixed set of example requests, no typing
    python run_synapsehr.py --llm           # policy answers are written by Gemini (needs the key variables)

Workflows: resume screening (needs data/sample), leave requests, policy questions.
Anything unclear goes to a human. Every decision is written to audit/audit_log.jsonl.
"""
import argparse
import re

import config  # noqa: F401  (reference date for the old Kaggle resumes)
import checkpoint
import leave_agent
import policy_agent
from router import route

parser = argparse.ArgumentParser()
parser.add_argument("--demo", action="store_true", help="run example requests without prompts")
parser.add_argument("--llm", action="store_true", help="let Gemini write policy answers (grounded, checked)")
args = parser.parse_args()

DEMO_REQUESTS = [
    "How many sick days do I get?",
    "I need 3 days off next week",
    "I want 14 days of annual leave",
    "Can I work from home?",
    "What is the capital of France?",
    "Please screen resumes for job 1",
    "blah blah",
]

index = policy_agent.PolicyIndex("policies")
employees = leave_agent.load_employees()


def handle(text, employee_id):
    intent, why = route(text)
    print(f"\n>> routed to: {intent}  ({why})")

    if intent == "leave_request":
        req = leave_agent.parse_request(text)
        result = leave_agent.evaluate(req, employees.get(employee_id))
        checkpoint.request_approval("leave_request", employee_id, result["recommendation"],
                                    result["reasons"], ("approve", "deny", "escalate"),
                                    result["flagged"], auto=args.demo)

    elif intent == "policy_question":
        out = policy_agent.answer(text, index, use_llm=args.llm)
        print(out["answer"])
        checkpoint.log_event("policy_answer", employee_id, question=text, mode=out["mode"],
                             sources=out["sources"], answered=out["answered"])

    elif intent == "screening":
        job = re.search(r"job\s*#?\s*(\d+)", text, re.I)
        try:
            import screening
            screening.screen(int(job.group(1)) if job else 1, n=3, others=1, auto=args.demo)
        except FileNotFoundError:
            print("Resume sample not found. Run sample_resumes.py first (see README).")

    else:
        print("I am not sure what this is, so a human will take over.")
        checkpoint.log_event("escalation", employee_id, message=text, reason=why)


if args.demo:
    for request in DEMO_REQUESTS:
        print("\n" + "#" * 64 + f"\nRequest: {request}")
        handle(request, "E101")
else:
    who = input("Your employee ID (E101, E102 or E103 in the demo) > ").strip() or "E101"
    print("Type a request, or 'quit'.")
    while True:
        text = input("\nRequest > ").strip()
        if text.lower() in ("quit", "exit", "q"):
            break
        handle(text, who)
