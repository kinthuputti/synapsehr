"""
run_graph.py - SynapseHR, the LangGraph multi-agent version (the main one).

    python run_graph.py                    # interactive: type requests, answer at each pause
    python run_graph.py --demo             # example requests, no typing
    python run_graph.py --reader llm       # Gemini reads resumes (needs GEMINI_API_KEY / GEMINI_MODEL)
    python run_graph.py --llm              # Gemini writes the policy answers (grounded and checked)

Requests it understands: leave ("I need 3 days off"), policy questions ("How many sick days do I get?"),
resume screening ("screen resume 70089206 for job 1"). Anything else goes to a human.
"""
import argparse
from pathlib import Path

import config  # noqa: F401  (reference date for the old Kaggle resumes)
import checkpoint
try:
    from graph import build_graph, run_request
except ImportError as e:
    raise SystemExit(f"LangGraph is not installed ({e}).\nRun:  python -m pip install langgraph\n"
                     "If that fails on your Python version, run_synapsehr.py does the same work without LangGraph.")

parser = argparse.ArgumentParser()
parser.add_argument("--demo", action="store_true", help="run example requests without prompts")
parser.add_argument("--reader", choices=["rule", "llm"], default="rule")
parser.add_argument("--llm", action="store_true", help="let Gemini write policy answers")
args = parser.parse_args()

app = build_graph(reader=args.reader, use_llm=args.llm)


def decide(payload):
    """Called whenever the graph pauses: show the proposal and get a person's decision."""
    checkpoint.show_recommendation(payload["kind"], payload["subject_id"], payload["recommendation"],
                                   payload["reasons"], payload["flagged"])
    print("  (the graph is paused until you decide)")
    final, note, mode = checkpoint.ask_for_decision(payload["recommendation"], payload["choices"], auto=args.demo)
    return {"final": final, "note": note, "mode": mode}


def handle(message, employee_id, number):
    out = run_request(app, message, employee_id, f"{employee_id}-{number}", decide)
    print(f"\n>> supervisor routed it to: {out['intent']}  ({out['route_reason']})")
    if out.get("outcome"):
        o = out["outcome"]
        print(f">> decision recorded: {o['final_decision']}  (agent suggested {o['agent_recommendation']}"
              f"{', overridden' if o['overridden'] else ''})")
    elif out.get("answer"):
        print(out["answer"])


if args.demo:
    requests = ["How many sick days do I get?", "I need 3 days off next week", "I want 14 days of annual leave",
                "Can I work from home?", "What is the capital of France?", "blah blah"]
    sample = Path("data/sample/resume_sample.csv")
    if sample.exists():
        import pandas as pd
        first = pd.read_csv(sample, dtype={"ID": str})
        first = first[first["Category"] == "INFORMATION-TECHNOLOGY"]
        if len(first):
            requests.append(f"screen resume {first.iloc[0]['ID']} for job 1")
    for i, request in enumerate(requests, 1):
        print("\n" + "#" * 64 + f"\nRequest: {request}")
        handle(request, "E101", i)
else:
    who = input("Your employee ID (E101, E102 or E103 in the demo) > ").strip() or "E101"
    print("Type a request, or 'quit'.")
    n = 0
    while True:
        text = input("\nRequest > ").strip()
        if text.lower() in ("quit", "exit", "q"):
            break
        n += 1
        handle(text, who, n)
