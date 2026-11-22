"""test_api.py - end-to-end checks of the service: validation, roles, concurrency, restart during a pause."""
import asyncio, os, tempfile
from pathlib import Path

os.environ["SYNAPSEHR_DB"] = str(Path(tempfile.mkdtemp()) / "t.db")
os.environ["SYNAPSEHR_TOKENS"] = ("emp101-token-0001:E101:employee,emp102-token-0002:E102:employee,"
                                  "hr-one-token-0003:HR1:reviewer,hr-two-token-0004:E102:reviewer,"
                                  "emp103-token-0005:E103:employee,hr-nine-token-0006:HR9:reviewer")
import httpx
from api import app

E101 = {"X-API-Key": "emp101-token-0001"}
E102 = {"X-API-Key": "emp102-token-0002"}
HR = {"X-API-Key": "hr-one-token-0003"}
E102_REVIEWER = {"X-API-Key": "hr-two-token-0004"}     # a reviewer who is also employee E102
E103 = {"X-API-Key": "emp103-token-0005"}
HR9 = {"X-API-Key": "hr-nine-token-0006"}              # a reviewer with no employee record


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def main():
    results = []
    def check(name, ok):
        print(("PASS  " if ok else "FAIL  ") + name); results.append(ok)

    async with app.router.lifespan_context(app):
        async with client() as c:
            class Resp:                                     # like an httpx response, plus the reviewer's view of a new case
                def __init__(self, r): self.status_code, self._j = r.status_code, r.json()
                def json(self): return self._j

            async def post(h, msg):
                """Send a request. An employee's response carries no proposal, so (as the page does for a reviewer)
                read it back from the reviewer queue to be able to check it."""
                resp = Resp(await c.post("/requests", json={"message": msg}, headers=h))
                j = resp.json()
                if resp.status_code == 200 and j.get("status") == "awaiting_human" and not j.get("proposal"):
                    j["proposal"] = next(i["proposal"] for i in (await c.get("/pending", headers=HR)).json()
                                         if i["thread_id"] == j["thread_id"])
                return resp

            check("no API key -> 401", (await c.get("/pending")).status_code == 401)
            check("wrong API key -> 401", (await c.get("/me", headers={"X-API-Key": "nope-nope-nope"})).status_code == 401)
            check("/me reports the role", (await c.get("/me", headers=E101)).json() == {"user_id": "E101", "role": "employee"})

            r = (await post(E101, "How many sick days do I get?")).json()
            check("policy question answers without pausing", r["status"] == "completed" and "10" in r["answer"])

            r = (await post(E101, "I need 3 days off next week")).json()
            check("leave request pauses for a human", r["status"] == "awaiting_human" and r["proposal"]["recommendation"] == "approve")
            paused = r["thread_id"]

            check("blank message refused by Pydantic", (await post(E101, "   ")).status_code == 422)
            check("employee cannot start resume screening", (await post(E101, "screen resume 70089206 for job 1")).status_code == 403)
            check("employee cannot list pending cases", (await c.get("/pending", headers=E101)).status_code == 403)
            check("employee cannot read the audit log", (await c.get("/audit", headers=E101)).status_code == 403)
            check("employee cannot decide", (await c.post(f"/decisions/{paused}", json={"final": "approve"}, headers=E101)).status_code == 403)
            check("invalid decision refused, graph stays paused",
                  (await c.post(f"/decisions/{paused}", json={"final": "banana"}, headers=HR)).status_code == 422
                  and len((await c.get("/pending", headers=HR)).json()) == 1)

            mine = (await c.get("/requests", headers=E102)).json()
            check("employees see only their own requests", mine == [])
            check("employees do not see the agent's proposal", all(x["proposal"] is None for x in (await c.get("/requests", headers=E101)).json()))

            # a reviewer who is also an employee cannot approve their own leave
            own = (await post(E102_REVIEWER, "I want 2 days annual leave")).json()
            check("reviewer cannot decide a case about themselves",
                  (await c.post(f"/decisions/{own['thread_id']}", json={"final": "approve"}, headers=E102_REVIEWER)).status_code == 403)
            pend_own = [i for i in (await c.get("/pending", headers=HR)).json() if i["thread_id"] == own["thread_id"]][0]
            check("a case says who else could decide it (never the person it is about)",
                  pend_own["proposal"]["other_reviewers"] == ["HR1", "HR9"])
            check("another reviewer can decide it",
                  (await c.post(f"/decisions/{own['thread_id']}", json={"final": "approve"}, headers=HR)).status_code == 200)

            # the approval above (2 annual days for E102) must change what the next request sees
            nxt = (await post(E102, "I want 1 day annual leave")).json()
            ctx = nxt["proposal"]["context"] if nxt.get("proposal") else None
            check("approval lowered the balance: the next request is judged against 0 days left",
                  nxt["status"] == "awaiting_human" and nxt["proposal"]["recommendation"] == "deny"
                  and ctx["employee"]["annual_balance"] == 0)
            check("history shows the leave approved here, newest first",
                  ctx["history"][0]["source"] == "approved here" and ctx["history"][0]["days"] == 2
                  and len(ctx["history"]) == 4)
            check("case carries the policy text it relies on",
                  any("10 consecutive" in p["text"] for p in ctx["policy"]))
            check("a denied case does not change the balance",
                  (await c.post(f"/decisions/{nxt['thread_id']}", json={"final": "deny"}, headers=HR)).status_code == 200
                  and (await post(E102, "I want 1 day annual leave")).json()["proposal"]["context"]["employee"]["annual_balance"] == 0)
            for item in (await c.get("/pending", headers=HR)).json():          # clear that extra case: keep the count below at 6
                if item["employee_id"] == "E102":
                    await c.post(f"/decisions/{item['thread_id']}", json={"final": "deny"}, headers=HR)
            first = [i for i in (await c.get("/pending", headers=HR)).json() if i["thread_id"] == paused][0]
            check("reviewer's queue shows balances and history",
                  first["proposal"]["context"]["employee"]["annual_balance"] == 12 and len(first["proposal"]["context"]["history"]) == 4)

            raw = (await c.post("/requests", json={"message": "I want 1 day annual leave"}, headers=E101)).json()
            check("an employee's response does not carry the agent's recommendation or reasons",
                  raw["status"] == "awaiting_human" and raw["proposal"] is None)
            await c.post(f"/decisions/{raw['thread_id']}", json={"final": "deny"}, headers=HR)

            # ---- answers about me, arriving clean ----
            r = (await post(E101, "How many sick leaves do I get?")).json()
            check("sick leave question is answered from the asker's own record", "used 4 days" in r["answer"] and "6 days left" in r["answer"])
            check("answers arrive without tags or file names, sources listed apart",
                  "[source" not in r["answer"] and ".md" not in r["answer"] and r["sources"] == ["Leave policy, Sick leave", "Your leave record"])
            r = (await post(HR9, "How many sick leaves do I get?")).json()
            check("a reviewer with no leave record gets the general answer", r["status"] == "completed" and "You have" not in r["answer"])
            r = (await post(E101, "Can I work from home?")).json()
            check("work-from-home answer is about the asker (hire date 2023)",
                  r["answer"].startswith("Yes.") and "15 May 2023" in r["answer"] and r["sources"][0] == "Remote work policy, Eligibility")
            r = (await post(E101, "what is the dress code on mars")).json()
            check("a question the policies cannot answer is marked as passed to HR", r["status"] == "passed_to_hr" and bool(r["answer"]))
            check("the request list shows that status", any(x["status"] == "passed_to_hr" for x in (await c.get("/requests", headers=E101)).json()))

            # ---- requests that cannot become a case are refused with a reason ----
            r = await post(E103, "I want 10 annual leave days and 2 sick leave days")
            check("two requests in one message are refused with a reason", r.status_code == 422 and "one at a time" in r.json()["detail"])
            r = await post(E103, "I want some leave")
            check("a request without a number of days is refused with a reason", r.status_code == 422 and "how many days" in r.json()["detail"])

            # ---- approvals can never overspend a balance (E103 has 18 annual days) ----
            x = (await post(E103, "I want 10 annual leave days")).json()
            y = (await post(E103, "I want 10 days of annual leave")).json()
            check("'10 annual leave days' is understood and both look fine when sent",
                  x["proposal"]["recommendation"] == "approve" and y["proposal"]["recommendation"] == "approve")
            check("approving the first works", (await c.post(f"/decisions/{x['thread_id']}", json={"final": "approve"}, headers=HR)).status_code == 200)
            item = [i for i in (await c.get("/pending", headers=HR)).json() if i["thread_id"] == y["thread_id"]][0]["proposal"]
            check("the second case is re-judged against the new balance",
                  item["recommendation"] == "deny" and item["context"]["employee"]["annual_balance"] == 8 and "only 8" in item["approve_blocked"])
            r = await c.post(f"/decisions/{y['thread_id']}", json={"final": "approve"}, headers=HR)
            check("approving beyond the balance is refused", r.status_code == 409 and "only 8" in r.json()["detail"])
            check("the refused case is still waiting and can be denied",
                  (await c.post(f"/decisions/{y['thread_id']}", json={"final": "deny", "note": "not enough left"}, headers=HR)).status_code == 200)
            log = (await c.get("/audit", headers=HR)).json()
            check("audit records what the agent said at decision time",
                  any(e.get("subject_id") == "E103" and e.get("days") == 10 and e.get("final_decision") == "deny"
                      and e.get("agent_recommendation") == "deny" for e in log))
            z = (await post(E103, "I want 8 days annual leave")).json()
            check("using exactly what is left is allowed",
                  (await c.post(f"/decisions/{z['thread_id']}", json={"final": "approve"}, headers=HR)).status_code == 200)
            w = (await post(E103, "I want 1 day annual leave")).json()
            check("nothing left: approval refused", (await c.post(f"/decisions/{w['thread_id']}", json={"final": "approve"}, headers=HR)).status_code == 409)
            await c.post(f"/decisions/{w['thread_id']}", json={"final": "deny"}, headers=HR)
            r = await post(HR9, "I need 3 days off next week")                          # HR2 has no employee record
            check("an account with no leave record cannot make a leave request",
                  r.status_code == 422 and "no leave record for HR9" in r.json()["detail"])
            check("and no dead-end case is left in the queue",
                  all(i["employee_id"] != "HR9" for i in (await c.get("/pending", headers=HR)).json()))
            r = await post(HR9, "How many sick leaves do I get?")
            check("the same account can still ask policy questions", r.status_code == 200 and r.json()["status"] == "completed")

            # ---- HR staff take leave like anyone else: it needs a record, and a DIFFERENT reviewer decides ----
            hr_leave = (await post(HR, "I want 2 days annual leave")).json()               # HR1 has a record in the demo data
            check("a reviewer who has a record can ask for leave",
                  hr_leave["status"] == "awaiting_human" and hr_leave["proposal"]["context"]["employee"]["annual_balance"] == 14)
            check("but cannot decide it themselves",
                  (await c.post(f"/decisions/{hr_leave['thread_id']}", json={"final": "approve"}, headers=HR)).status_code == 403)
            check("a different reviewer decides it",
                  (await c.post(f"/decisions/{hr_leave['thread_id']}", json={"final": "approve"}, headers=E102_REVIEWER)).status_code == 200)

            # ---- HR tools: people, jobs, resumes (reviewers only) ----
            check("employees cannot open the People list or anyone's record",
                  (await c.get("/employees", headers=E101)).status_code == 403
                  and (await c.get("/employees/E102", headers=E101)).status_code == 403)
            check("employees cannot see jobs or resumes",
                  (await c.get("/jobs", headers=E101)).status_code == 403 and (await c.get("/resumes", headers=E101)).status_code == 403)
            people = {p["employee_id"]: p for p in (await c.get("/employees", headers=HR)).json()}
            check("People lists everyone, with live balances and waiting requests",
                  sorted(people) == ["E101", "E102", "E103", "HR1", "HR2"] and people["E101"]["annual_balance"] == 12
                  and people["E101"]["sick_balance"] == 6 and people["E101"]["waiting"] >= 1)
            check("an approval shows up in the list (E103 was approved for 18 days above)", people["E103"]["annual_balance"] == 0)
            d = (await c.get("/employees/E101", headers=HR)).json()
            check("a person's page has their record, leave history and requests",
                  d["employee"]["hire_date"] == "2023-05-15" and len(d["history"]) == 4
                  and any(r["message"] == "I need 3 days off next week" for r in d["requests"]))
            check("an unknown person is a clear 404", (await c.get("/employees/E999", headers=HR)).status_code == 404)
            check("looking at someone's record is written to the audit log",
                  any(e["kind"] == "record_view" and e["subject_id"] == "E101" and e["viewer"] == "HR1"
                      for e in (await c.get("/audit", headers=HR)).json()))
            jobs = (await c.get("/jobs", headers=HR)).json()
            check("jobs list the requirements", len(jobs) == 6 and jobs[0]["title"] == "Software Engineer" and "python" in jobs[0]["must_have"])
            check("resumes list the demo candidates", {"10001", "10006"} <= {r["resume_id"] for r in (await c.get("/resumes", headers=HR)).json()})
            check("a reviewer can read a resume, and it is logged",
                  "Brightwave" in (await c.get("/resumes/10001", headers=HR)).json()["text"]
                  and any(e["kind"] == "record_view" and e["subject_id"] == "10001" and e["viewer"] == "HR1"
                          for e in (await c.get("/audit", headers=HR)).json()))
            check("employees cannot read resumes; unknown resumes are a 404",
                  (await c.get("/resumes/10001", headers=E101)).status_code == 403
                  and (await c.get("/resumes/99999999", headers=HR)).status_code == 404)
            s = (await post(HR, "screen resume 10001 for job 1")).json()
            check("HR can screen a resume: it waits for a decision, with the agent's recommendation",
                  s["status"] == "awaiting_human" and s["proposal"]["kind"] == "resume_screening"
                  and s["proposal"]["recommendation"] == "shortlist" and s["proposal"]["subject_id"] == "10001")
            r = await c.post(f"/decisions/{s['thread_id']}", json={"final": "shortlist", "note": "strong match"}, headers=HR)
            check("and the decision is recorded", r.status_code == 200 and r.json()["outcome"]["final_decision"] == "shortlist")
            r = (await post(HR, "screen resume 99999999 for job 1")).json()
            check("an unknown resume is answered plainly, with nothing to decide", r["status"] == "completed" and "was not found" in r["answer"])

            # ---- candidates, interviews and the hiring decision ----
            from datetime import datetime, timedelta
            slot = lambda minutes=0: (datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")
            plan = {"kind": "technical", "scheduled_for": slot(), "interviewer": "HR9"}
            check("employees cannot reach candidates, interviews or hiring decisions",
                  [(await c.get("/candidates", headers=E101)).status_code, (await c.get("/candidates/1", headers=E101)).status_code,
                   (await c.post("/candidates/1/interviews", json=plan, headers=E101)).status_code,
                   (await c.post("/candidates/1/decision-request", headers=E101)).status_code] == [403, 403, 403, 403])
            check("nor through the chat box", (await post(E101, "hiring decision for candidate 1")).status_code == 403)
            cands = (await c.get("/candidates", headers=HR)).json()
            check("the shortlisted resume became a candidate",
                  len(cands) == 1 and cands[0]["stage"] == "shortlisted" and cands[0]["resume_id"] == "10001" and cands[0]["job_title"] == "Software Engineer")
            d = (await c.get("/candidates/1", headers=HR)).json()
            check("the candidate page offers the interviewers and interview types",
                  d["interviewers"] == ["E102", "HR1", "HR9"] and "technical" in d["kinds"] and d["category"] == "INFORMATION-TECHNOLOGY")
            check("an unknown candidate is a 404", (await c.get("/candidates/99", headers=HR)).status_code == 404)
            r = await c.post("/candidates/1/decision-request", headers=HR)
            check("no hiring decision before the interviews", r.status_code == 409 and "interviews have to take place" in r.json()["detail"])
            r = await c.post("/candidates/1/interviews", json=plan, headers=HR)
            check("HR schedules an interview", r.status_code == 200 and r.json()["candidate"]["stage"] == "interviewing"
                  and r.json()["interviews"][0]["status"] == "scheduled")
            iid = r.json()["interviews"][0]["interview_id"]
            for label, body, word in [("the same interviewer at the same time", plan, "overlaps"),
                                      ("someone who is not a reviewer", dict(plan, interviewer="E101"), "cannot interview"),
                                      ("a time that has passed", dict(plan, scheduled_for="2020-01-01T10:00", interviewer="HR1"), "passed"),
                                      ("an unknown interview type", dict(plan, kind="chat", interviewer="HR1", scheduled_for=slot(300)), "must be one of"),
                                      ("a time that is not a time", dict(plan, scheduled_for="next friday", interviewer="HR1"), "date and time")]:
                r = await c.post("/candidates/1/interviews", json=body, headers=HR)
                check(f"an interview is refused for {label}", r.status_code == 422 and word in r.json()["detail"])
            r = await c.post("/candidates/1/interviews", json=dict(plan, interviewer="HR1", scheduled_for=slot(300)), headers=HR)
            check("a round cannot be booked twice for the same candidate", r.status_code == 422 and "already has a technical" in r.json()["detail"])
            r = await c.post("/candidates/1/interviews", json=dict(plan, kind="final", interviewer="HR1", scheduled_for="2099-01-01T10:00"), headers=HR)
            check("an interview cannot be booked years ahead", r.status_code == 422 and "90 days" in r.json()["detail"])
            r = await c.post("/candidates/1/decision-request", headers=HR)
            check("no hiring decision while an interview is still scheduled", r.status_code == 409 and "still scheduled" in r.json()["detail"])
            note = {"rating": 5, "feedback": "Excellent design discussion."}
            check("a rating outside 1 to 5, or no real note, is refused",
                  (await c.post(f"/interviews/{iid}/feedback", json=dict(note, rating=9), headers=HR9)).status_code == 422
                  and (await c.post(f"/interviews/{iid}/feedback", json=dict(note, feedback="ok"), headers=HR9)).status_code == 422)
            r = await c.post(f"/interviews/{iid}/feedback", json=note, headers=HR)
            check("only the interviewer can record feedback", r.status_code == 403 and "Only the interviewer, HR9" in r.json()["detail"])
            r = await c.post(f"/interviews/{iid}/feedback", json=note, headers=HR9)
            check("the interviewer records feedback", r.status_code == 200 and r.json()["interviews"][0]["status"] == "completed"
                  and r.json()["candidate"]["avg_rating"] == 5.0)
            check("feedback cannot be given twice", (await c.post(f"/interviews/{iid}/feedback", json=note, headers=HR9)).status_code == 422)
            r = await c.post("/candidates/1/decision-request", headers=HR)
            case = r.json()
            check("the hiring decision goes to the review queue with the agent's recommendation",
                  r.status_code == 200 and case["status"] == "awaiting_human" and case["proposal"]["kind"] == "hiring_decision"
                  and case["proposal"]["recommendation"] == "offer" and case["proposal"]["flagged"])
            check("a second request for the same candidate is refused", (await c.post("/candidates/1/decision-request", headers=HR)).status_code == 409)
            item = [i for i in (await c.get("/pending", headers=HR)).json() if i["thread_id"] == case["thread_id"]][0]["proposal"]
            check("the queue shows the candidate and the interview feedback",
                  item["candidate"]["job_title"] == "Software Engineer" and item["candidate"]["interviews"][0]["rating"] == 5
                  and item["choices"] == ["offer", "reject", "hold"])
            r = await c.post(f"/decisions/{case['thread_id']}", json={"final": "offer", "note": "great fit"}, headers=HR)
            check("the decision is recorded and the candidate moves to offer",
                  r.status_code == 200 and r.json()["outcome"]["final_decision"] == "offer"
                  and (await c.get("/candidates/1", headers=HR)).json()["candidate"]["stage"] == "offer")
            r = await c.post("/candidates/1/decision-request", headers=HR)
            check("nothing is left to decide once an offer is made", r.status_code == 409 and "already been given an offer" in r.json()["detail"])

            # a resume that needs review cannot be interviewed until a reviewer shortlists it
            s2 = (await post(HR, "screen resume 10002 for job 1")).json()
            check("a middling resume is recommended for review", s2["proposal"]["recommendation"] == "review")
            await c.post(f"/decisions/{s2['thread_id']}", json={"final": "review"}, headers=HR)
            r = await c.post("/candidates/2/interviews", json=dict(plan, interviewer="HR1", scheduled_for=slot(240)), headers=HR)
            check("a candidate waiting for review cannot be interviewed", r.status_code == 422 and "waiting for review" in r.json()["detail"])
            s3 = (await post(HR, "screen resume 10002 for job 1")).json()
            await c.post(f"/decisions/{s3['thread_id']}", json={"final": "shortlist", "note": "second look: fine"}, headers=HR)
            check("a second look can shortlist them", (await c.get("/candidates/2", headers=HR)).json()["candidate"]["stage"] == "shortlisted")
            r = await c.post("/candidates/2/interviews", json=dict(plan, kind="phone screen", interviewer="HR1", scheduled_for=slot(240)), headers=HR)
            r = await c.post(f"/interviews/{r.json()['interviews'][0]['interview_id']}/cancel", headers=HR)
            check("cancelling the only interview returns the candidate to shortlisted",
                  r.status_code == 200 and r.json()["candidate"]["stage"] == "shortlisted" and r.json()["interviews"][0]["status"] == "cancelled")

            # the same person can apply for more than one job
            s4 = (await post(HR, "screen resume 10001 for job 2")).json()
            await c.post(f"/decisions/{s4['thread_id']}", json={"final": "reject"}, headers=HR)
            others = (await c.get("/candidates/1", headers=HR)).json()["other_applications"]
            check("the candidate page lists the other jobs the same resume applied for",
                  len(others) == 1 and others[0]["job_id"] == 2 and others[0]["stage"] == "rejected")
            kinds = {e["kind"] for e in (await c.get("/audit?limit=500", headers=HR)).json()}
            check("candidates and interviews are in the audit log",
                  {"candidate_stage", "interview_scheduled", "interview_feedback", "interview_cancelled", "hiring_decision"} <= kinds)

            rs = await asyncio.gather(*[post(E101, "I want 2 days annual leave") for _ in range(5)])
            check("5 concurrent requests all pause", all(x.json()["status"] == "awaiting_human" for x in rs))
            check("6 paused requests listed", len((await c.get("/pending", headers=HR)).json()) == 6)

    # --- restart the server: the pause must survive ---
    async with app.router.lifespan_context(app):
        async with client() as c:
            check("pause survives restart", len((await c.get("/pending", headers=HR)).json()) == 6)
            r = (await c.post(f"/decisions/{paused}", json={"final": "deny", "note": "team is short that week"}, headers=HR)).json()
            check("decision resumes the graph", r["status"] == "completed" and r["outcome"]["overridden"] is True)
            check("deciding twice is refused", (await c.post(f"/decisions/{paused}", json={"final": "approve"}, headers=HR)).status_code == 404)
            log = (await c.get("/audit", headers=HR)).json()
            check("audit log records the override and who decided",
                  any(e.get("final_decision") == "deny" and e["overridden"] and e.get("reviewer") == "HR1" for e in log))
            mine = (await c.get("/requests", headers=E101)).json()
            check("employee sees the final decision on their request",
                  any(x["thread_id"] == paused and x["status"] == "decided" and x["outcome"]["final_decision"] == "deny" for x in mine))
            page = await c.get("/")
            check("review page is served", page.status_code == 200 and "SynapseHR" in page.text)

    print(f"\n{sum(results)} of {len(results)} API tests passed")
    raise SystemExit(0 if all(results) else 1)

asyncio.run(main())
