
# SynapseHR

I built **SynapseHR**, a multi-agent HR workflow system structured around a **LangGraph** state graph. A rule-based supervisor routes incoming requests to specialist workflows (resume screening, leave requests, and policy Q&A), and the graph **pauses at a human checkpoint** so a reviewer can inspect, modify, or approve consequential decisions before they are finalized.

> **Work in progress.** This README documents what I built and tested across versions `v0.1`–`v0.12`, along with my evaluation results and current `v1.0` gaps.

## Live demo

**Try it:** https://synapsehr-w0u4.onrender.com

The demo uses fictional employees and resumes only. Sign in with one of these API keys:

| Role | API key |
|---|---|
| Employee (`E101`) | `demo-employee-0001` |
| Reviewer (`HR1`) | `demo-reviewer-0001` |
| Second reviewer (`HR2`) | `demo-reviewer-0002` |

Try the walkthrough below: sign in as the employee and submit a leave request, then sign in as a reviewer and decide it.

This runs on a free hosting plan, so the first load can take about a minute, and the data resets whenever it restarts.
---

## Core Design Principles

Because HR workflows affect people directly, I intentionally avoided autonomous, free-roaming LLM agents:

* **Deterministic routing & math:** The supervisor and core specialist workflows use explicit rules by default. Optional Gemini integration (`--reader llm`, `--llm`) is limited to resume text extraction and policy answer drafting—never routing decisions, date arithmetic, or final decisions.
* **Human-in-the-loop checkpoints:** Screening, leave, and hiring decisions pause via LangGraph `interrupt()` and persist workflow state until an authorized reviewer approves, denies, or overrides the agent's recommendation.
* **Grounded policy answers or explicit escalation:** Policy responses cite a source document and section; weak matches escalate to HR rather than guessing.
* **Visible failures:** Failed LLM calls surface explicitly as errors rather than silent empty outputs.
* **Reviewer guardrails:** Short resumes, inflated experience claims (3+ years above dated job history), and assumed dates are flagged automatically for human inspection.

---

## Status

| Version | Scope | State |
|---|---|---|
| **v0.1** | **Resume screening:** text reader, rule-based scorer, and human checkpoint | Built; tried on a small sample of a public resume dataset |
| **v0.2** | **Supervisor:** deterministic request routing to specialist workflows | Built, unit-tested |
| **v0.3** | **Policy Q&A:** section-level citations and abstention on weak matches | Built, unit-tested on fictional policies |
| **v0.4** | **LangGraph workflow:** multi-agent graph with `interrupt()` pauses (`graph.py`, `run_graph.py`) | Built, unit-tested |
| **v0.5** | **Evaluation harness:** blind labeling and agreement metrics (`make_eval_sheet.py`, `evaluate.py`) | Built; results recorded in Evaluation below |
| **v0.6** | **Async FastAPI service:** Pydantic schemas, SQLite-persisted pauses and audit log (`api.py`, `schemas.py`) | Built, tested |
| **v0.7** | **Authentication & roles:** API keys, `employee` and `reviewer` roles, and no self-approval (`auth.py`) | Built, tested (96 API tests, including server restart mid-pause) |
| **v0.8** | **React review UI:** served by FastAPI (`web/`); employees submit requests, reviewers decide | Built, tested with headless browser suite (76 checks) |
| **v0.9** | **Reviewer context:** displays employee leave balances, history, and cited policy; approvals deduct from balance (`leave_records.py`) | Built, tested |
| **v0.10** | **Balance & policy enforcement:** re-evaluates pending cases against live balances at decision time; blocks over-balance approvals and ambiguous multi-type leave requests; answers personal balance and WFH eligibility questions from employee records; marks unanswerable queries `"Passed to HR"` | Built, tested |
| **v0.11** | **HR workspace:** `People` directory (balances, history, requests), resume screening form with side-by-side resume viewer, separation of reviewer's own leave, audit logging for all record/resume views, and built-in fictional demo resumes (`demo/resumes.csv`) | Built, tested |
| **v0.12** | **Candidate & interview pipeline (`hiring.py`):** screening approvals create candidates; HR books interviews (blocking past times and double-bookings); assigned interviewers log feedback and 1–5 ratings; hiring decisions (`offer`, `reject`, `hold`) route through the human checkpoint; candidate view links resumes, interviews, and multi-job applications | Built, tested |
| **v1.0** | **Production readiness:** deployment setup, real user accounts, Postgres persistence | **Partly built.** Deployed as a free-tier demo with fictional data (see Live demo above). Real user accounts and Postgres persistence are **not built** |
---

## Architecture & Access Control

### Graph & Service Flow

```text
incoming message
  └─► SUPERVISOR (rule-based)
        ├─► screening agent ──┐
        ├─► leave agent ──────┼─► HUMAN CHECKPOINT (graph pauses via interrupt()) ─► decision logged
        ├─► policy agent ─────┴─► cited answer (or escalation if evidence is weak)
        └─► unrecognized ───────► escalation to human

```

Every decision, override, escalation, and record or resume view is appended to `audit/audit_log.jsonl` and the SQLite `audit` table when running via FastAPI.

```text
React UI (web/) ──[X-API-Key]──► FastAPI (api.py) ──► LangGraph (graph.py) ──► SQLite
  • employees: submit & track       • pauses at interrupt()                     • stores graph checkpoints,
  • reviewers: queue & decide       • resumes on validated decision             leave, hiring & audit log

```

When the graph hits `interrupt()`, execution halts and its state is serialized to SQLite. Resuming requires passing a human decision back into that `thread_id`. Reviewers can accept or override the agent's recommendation; invalid decisions are rejected, and the audit log records who decided and whether they changed the agent's recommendation.

### Role Permissions (Enforced in API & Graph)

| Capability | `employee` | `reviewer` |
| --- | --- | --- |
| Submit leave requests or policy questions (for self) | Yes | Yes |
| Initiate resume screening | No | Yes |
| View requests | Own requests only | All requests |
| View agent recommendation, reasoning, employee record, and policy excerpt | No | Yes |
| Browse People directory, employee records, jobs, or resumes *(views logged)* | No | Yes |
| View candidates, schedule interviews, request hiring decisions | No | Yes |
| Submit interview feedback & rating | No | Assigned interviewer only |
| Decide a paused checkpoint | No | Yes *(never on own case)* |
| Read the audit log | No | Yes |

---

## Quick Start

### 1. Install & Run Tests

```bash
python -m venv .venv
.venv\Scripts\activate          # On macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python test_synapsehr.py        # Core workflow tests (40 checks, no data or API key required)
python test_api.py              # API tests (roles, validation, concurrency, restart persistence)

```

*(Windows shortcuts: double-click `test.bat` to run the test suite, or `run.bat` to set up the environment and launch the server.)*

### 2. Run via CLI or Web Server

```bash
# Command-line graph runner
python run_graph.py --demo      # Runs canned demo requests through the graph
python run_graph.py             # Interactive CLI; prompts you at each pause

# FastAPI service + React review UI ([http://127.0.0.1:8000](http://127.0.0.1:8000), OpenAPI docs at /docs)
uvicorn api:app --reload

```

On startup, the server prints demo API keys to the console for three employees (`E101`–`E103`) and two reviewers (`HR1`, `HR2`, who also have employee records). Paste any key into the sign-in screen, or configure custom tokens via `SYNAPSEHR_TOKENS` (see `.env.example`).

### 3. Walkthrough: End-to-End Leave Approval

1. Sign in as **`E101`** and submit: `"I need 3 days off next week"`.
2. Open a second browser window, sign in as **`HR1`**, and open the review queue to inspect the agent's recommendation, balance breakdown, and cited policy section.
3. Change the recommendation, enter a reviewer note, and submit the decision.
4. Check the **Audit Log** tab and **`E101`**'s profile in **People** to verify the balance deduction and log entry.

### Optional Setups

* **Headless UI tests (Node 18+):** `cd ui_test && npm install && npm test` (launches an isolated server backed by a temporary SQLite database).
* **Direct API usage:** Send `POST /requests` with header `X-API-Key`. If the status returns `awaiting_human`, inspect `GET /pending` and resume via `POST /decisions/{thread_id}` with `{"final": "approve"}` (or `"deny"` / `"escalate"`).
* **External resume dataset:** Built-in screening works out of the box using 6 fictional resumes (`demo/resumes.csv`, IDs `10001`–`10006`). For larger tests or evaluation, download the public [Kaggle Resume Dataset](https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset) (CC0) into `data/resume`, then run `screen resume <ID> for job 1` in the graph or batch-sample via `python tools/sample_resumes.py && python run_v01.py`.
* **Optional Gemini integration (free tier):** Export `GEMINI_API_KEY` and `GEMINI_MODEL` in your shell environment (never commit them to a file). Run `python tools/check_gemini.py` to verify which models your key can access.

---

## Project Structure

```text
api.py                  Async FastAPI service (pause/resume endpoints, SQLite persistence)
auth.py                 API-key authentication and role enforcement
schemas.py              Pydantic models for requests, proposals, and human decisions
graph.py                LangGraph definition: supervisor, specialist nodes, human checkpoint
run_graph.py            CLI runner for the LangGraph workflow
run_synapsehr.py        Fallback CLI runner without LangGraph
run_v01.py              Standalone v0.1 resume screening script
router.py               Rule-based intent router
leave_agent.py          Leave request evaluation and balance checks
policy_agent.py         BM25 policy retrieval, citation formatting, and abstention logic
screening.py            Resume-to-job matching orchestrator
hiring.py               Candidate records, interview scheduling, feedback, and offer/reject rules
leave_records.py        Employee balances, leave history, and WFH eligibility lookups
answers.py              Employee-specific balance and WFH eligibility answer helpers
reader.py               Rule-based resume parser
experience.py           Experience claim extraction and discrepancy flagging
tenure.py               Date-range arithmetic for total years of experience
scorer.py               Rule-based candidate scoring
jobs.py                 Job descriptions and requirement definitions
llm.py / llm_reader.py  Optional Gemini client and structured resume/policy prompts
checkpoint.py           Human checkpoint helper and JSONL audit logger
config.py               Reference as-of date (2018-12-31) for historical Kaggle resumes
make_eval_sheet.py      Generates blind evaluation pairs (30 same-profession, 12 mismatched)
evaluate.py             Runs system evaluation against human labels
test_synapsehr.py       Core unit and workflow tests
test_api.py             End-to-end API, auth, concurrency, and restart tests
web/                    Single-page React review UI (no build step; CDN-loaded React & Figtree)
ui_test/                Headless React UI test suite (Node + jsdom)
policies/               Fictional policy markdown files (leave, remote work, expense, code of conduct)
demo/                   Fictional employee records (employees.json) and sample resumes (resumes.csv)
tools/                  Development, comparison, and diagnostics scripts
.github/workflows/ci.yml  CI workflow running the test suites on push

```

---

## Evaluation

`make_eval_sheet.py` samples 30 same-profession resume/job pairs alongside 12 cross-profession pairs (expected rejections by construction). I labeled all 30 same-profession pairs manually (`shortlist`, `review`, or `reject`) from the resume alone **before** running the system, and kept those labels fixed afterward. `evaluate.py` then runs the pipeline once and reports agreement rates, error types, and sample size.

**Results (keyword reader):**

| Your decision \ System recommendation | `shortlist` | `review` | `reject` |
| --- | --- | --- | --- |
| **`shortlist`** | 4 | 4 | 5 |
| **`review`** | 1 | 3 | 3 |
| **`reject`** | 0 | 0 | 10 |

* **Exact agreement:** 17 of 30 (57%)
* **Advance (`shortlist`/`review`) vs. `reject` agreement:** 22 of 30 (73%)
* **Good candidates rejected (`shortlist` → `reject`):** 5
* **Weak candidates shortlisted (`reject` → `shortlist`):** 0
* **Flagged for extra checking:** 0 of 30
* **Different-profession pairs rejected:** 9 of 12

I labeled 30 resume-and-job pairs from the same profession myself (shortlist, review or reject), before running the system. The keyword reader agreed exactly with 17 of 30 (57%) and agreed on advance versus reject for 22 of 30. It rejected 5 candidate(s) I would have shortlisted. It rejected 9 of 12 pairs from a different profession. Caveats: one labeler, a small sample from one dataset of resume-builder examples, and the labels reflect my own judgment of the job requirements.

### Informal Development Notes (Keyword vs. LLM Reader)

Observations from comparing my rule-based reader against Gemini on a small sample of resumes (informal findings rather than benchmark accuracy numbers):

* **Synonym recognition:** The LLM recognized paraphrased skills that keyword rules missed, while keyword matching initially over-counted generic words (which I addressed by refining the skill list).
* **Date arithmetic:** Asking the LLM directly for total years of experience produced multi-year errors because it guessed the current date. I fixed this by having the LLM copy job dates while `tenure.py` computes the years.
* **False-positive patterns:** I fixed keyword parser bugs that misread `"3 Year Plan Process"` as work tenure, `"courses in an MBA program"` as a completed master's degree, and `"8 years of management experience"` as total experience.
* **PDF extraction noise:** Damaged PDF text (such as `"sta f"` for `"staff"`) breaks keyword matching.
* **Experience inflation threshold:** Across the full dataset, 94% of resumes stating a number of years differ from their own dates by a year or more, making a both-ways 1-year flag too noisy. I made the flag one-way (a claim 3 or more years above the dates).

---

## Known Limitations

### Infrastructure & Authentication

* **CLI vs. API persistence:** `run_graph.py` keeps pauses in memory (`MemorySaver`), so pauses do not survive exit. The FastAPI service uses a SQLite checkpointer and survives server restarts.
* **Concurrency & database:** Agent nodes are synchronous functions that LangGraph runs in worker threads behind an async FastAPI layer. SQLite works for demos and single-node testing, not for many writers—Postgres is needed for real deployment.
* **Auth & session handling:** Authentication uses static environment API keys with two roles and no user accounts, password reset, key rotation, expiry, or rate limiting. The web UI stores the key in `sessionStorage` (cleared when the tab closes). Put the service behind HTTPS and a real identity provider before real use.
* **Frontend polling & CDNs:** The UI polls every 15 seconds with no live updates or notifications, and loads React and the Figtree font from public CDNs (requiring internet access; fonts fall back to system defaults).

### Leave & Policy Workflows

* **No calendar date parsing:** Leave requests must state a number of days (`"3 days"`, `"10 annual leave days"`). Dates like `"next week"` are not read, so approvals are filed under the day decided and overlapping leave is not checked.
* **Single-category requests only:** Messages asking for two things at once (such as annual and sick leave together) are refused and must be sent one at a time.
* **No manager hierarchy:** The policy says a manager approves annual leave, whereas this project models `employee` and `reviewer` roles rather than managers. "No self-approval" compares the reviewer's ID with the case's subject rather than reporting lines.
* **Balance guards & single-reviewer deadlock:** Reviewers cannot approve more days than remain (blocked in the UI, API, and checkpoint). Concurrent pending requests are re-judged against the current balance at decision time. A reviewer with an employee record (`HR1`, `HR2`) can submit a leave request, but it waits for a *different* reviewer to decide it (if only one reviewer key is configured, it stays queued until a second reviewer is added in `SYNAPSEHR_TOKENS`). Accounts with no employee record cannot make leave requests.
* **Personal Q&A scope & rule drift:** Answers about the asker cover leave balances and work-from-home eligibility from the hire date and policy numbers (e.g., `E103` has a demo hire date of `2026-10-01`, shifting from `"not yet"` to `"yes"` on `2027-01-01`). Any other question or non-employee caller gets the general policy answer. Policy retrieval uses BM25 keyword matching, so paraphrases or uncovered questions are marked `"Passed to HR"` in the audit log (with no HR inbox UI to reply from). Leave rules in `leave_agent.py` duplicate `policies/leave_policy.md` and can drift apart.

### Resume Screening & Hiring Pipeline

* **Minimal ATS scope:** Candidates exist only because a reviewer made a screening decision—there is no applicant intake form, emails, calendar invitations, reminders, or offer letters, and `"offer"` is a recorded decision rather than an offer sent. Records track people by ID only with no names.
* **Interview constraints:** Each candidate can have one interview per round (`phone screen`, `technical`, `final`) booked at most 90 days ahead in server local time (cancelling frees the round). Only people with a reviewer key can be interviewers.
* **Simple hiring heuristic:** The hiring recommendation is a transparent rule (`shortlist` with average rating ≥ 4.0 → `offer`; below 3.0 → `reject`; otherwise `hold`, flagging single interviews or disagreeing ratings), not a validated model.
* **Resume parsing assumptions:** Years of experience means whole years from earliest job start to latest end, capped at `2018-12-31` (`config.py`) for historical Kaggle resumes (remove that line for live applicants). An Experience section with no readable years counts as under 1 year, and one lone date is read as a start date with the job still current—both are flagged as assumptions. Kaggle resumes also come from a resume-builder site with fairly uniform structure, and the free LLM tier has rate limits.

---

## Data and Privacy

All policies, employee records, and demo resumes in this repository are fictional. Resume data, the LLM cache, audit logs, and evaluation results are `.gitignore`d. Do not use real applicants' data with a free API tier.
