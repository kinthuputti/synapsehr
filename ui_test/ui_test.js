const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path"), os = require("os");
const { spawn } = require("child_process");
const PORT = process.env.PORT || "8765";
const BASE = "http://127.0.0.1:" + PORT;
const W = path.join(__dirname, "..", "web") + path.sep;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const results = [];
const check = (n, ok) => { console.log((ok ? "PASS  " : "FAIL  ") + n); results.push(ok); };

async function boot() {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: BASE + "/", runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (u, o) => fetch(BASE + u, o);
  w.eval(fs.readFileSync(path.join(__dirname, "node_modules", "react", "umd", "react.production.min.js"), "utf8"));
  w.eval(fs.readFileSync(path.join(__dirname, "node_modules", "react-dom", "umd", "react-dom.production.min.js"), "utf8"));
  w.eval(fs.readFileSync(W + "app.js", "utf8"));
  await sleep(300);
  return w;
}
const $ = (w, s) => w.document.querySelector(s);
const $$ = (w, s) => [...w.document.querySelectorAll(s)];
function type(w, el, value) {
  const proto = el.tagName === "TEXTAREA" ? w.HTMLTextAreaElement.prototype : w.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  el.dispatchEvent(new w.Event("input", { bubbles: true }));
}
const click = (w, el) => el.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
const submit = (w, form) => form.dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true }));
const text = (w) => w.document.body.textContent;
const tab = (w, name) => click(w, $$(w, ".tab").find(t => t.textContent.includes(name)));
const button = (w, start) => $$(w, "button").find(b => b.textContent.startsWith(start));

async function startServer() {
  const db = path.join(os.tmpdir(), "synapsehr_ui_" + Date.now() + ".db");
  const server = spawn(process.env.PYTHON || "python", ["-m", "uvicorn", "api:app", "--port", PORT], {
    cwd: path.join(__dirname, ".."), stdio: "ignore",
    env: Object.assign({}, process.env, { SYNAPSEHR_DB: db,
      SYNAPSEHR_TOKENS: "emp101-token-0001:E101:employee,hr-one-token-0003:HR1:reviewer,e102-rev-token-0002:E102:reviewer,hr-nine-token-0009:HR9:reviewer" }) });
  for (let i = 0; i < 60; i++) {
    try { await fetch(BASE + "/"); return server; } catch (e) { await sleep(500); }
  }
  server.kill(); throw new Error("server did not start");
}

(async () => {
  const server = await startServer();
  process.on("exit", () => server.kill());

  // ================= employee =================
  let w = await boot();
  check("login screen shows first", !!$(w, "#token"));
  type(w, $(w, "#token"), "wrong-key-wrong-key"); submit(w, $(w, "form")); await sleep(400);
  check("wrong key shows an error", text(w).includes("not accepted"));
  type(w, $(w, "#token"), "emp101-token-0001"); submit(w, $(w, "form")); await sleep(500);
  check("employee lands on their requests", text(w).includes("Your requests") && text(w).includes("E101 (employee)"));
  check("employee has no review tabs", !text(w).includes("Review queue"));

  const send = async (msg, wait) => { type(w, $(w, "#msg"), msg); submit(w, $(w, "form.panel")); await sleep(wait || 800); };

  await send("How many sick days do I have left?");
  check("a question about me is answered from my own record",
        text(w).includes("You have used 4 days, so you have 6 days left."));
  check("sources are a plain line: no file names, no brackets",
        text(w).includes("Sources: Leave policy, Sick leave; Your leave record") && !text(w).includes(".md") && !text(w).includes("[source"));

  await send("Can I work from home?");
  check("work from home is answered for this employee (joined 2023)",
        text(w).includes("Yes. You joined on 15 May 2023") && text(w).includes("Remote work policy, Eligibility"));

  await send("what is the dress code on mars");
  check("a question the policies cannot answer says it was passed to HR", text(w).includes("Passed to HR"));

  await send("I want 10 annual leave days and 2 sick leave days", 500);
  check("two requests in one message: told to send them one at a time", text(w).includes("one at a time"));
  await send("I want some leave", 500);
  check("no number of days: told to say how many", text(w).includes("how many days"));

  await send("I need 3 days off next week");
  check("leave request shows 'waiting for a reviewer'", text(w).includes("Waiting for a reviewer"));
  await send("I want 14 days of annual leave");
  await send("screen resume 70089206 for job 1", 500);
  check("employee screening attempt shows the server's error", text(w).includes("HR function"));
  check("no raw tags, file names or US-style dates anywhere on the employee page",
        !text(w).includes(".md") && !text(w).includes("[source") && !/\b[A-Z][a-z]{2} \d{1,2}, \d/.test(text(w)));

  // ================= reviewer =================
  w = await boot();
  type(w, $(w, "#token"), "hr-one-token-0003"); submit(w, $(w, "form")); await sleep(900);
  check("reviewer sees both cases in the queue", $$(w, ".queue-item").length === 2 && text(w).includes("Review queue2"));
  check("queue items show what was asked", text(w).includes("I need 3 days off next week") && text(w).includes("I want 14 days of annual leave"));
  check("queue says which case cannot be approved", text(w).includes("Cannot be approved"));

  // --- the case that asks for more than the balance
  click(w, $$(w, ".queue-item").find(b => b.textContent.includes("14 days"))); await sleep(200);
  check("over-balance case: a red notice says why it cannot be approved", !!$(w, ".notice.error") && text(w).includes("only 12 annual leave days left"));
  check("over-balance case: Approve cannot be chosen", button(w, "Approve").disabled && text(w).includes("not allowed"));
  check("recommendation is shown in words, in red for a denial", $(w, ".rec strong").textContent === "Deny" && $(w, ".rec strong").className === "bad");
  click(w, button(w, "Deny")); await sleep(100);
  click(w, button(w, "Record decision")); await sleep(900);
  check("denying it clears it from the queue", $$(w, ".queue-item").length === 1);

  // --- the ordinary case
  check("case shows the workflow strip with a paused checkpoint", !!$(w, ".flow .paused") && text(w).includes("graph is paused"));
  check("reasons are plain sentences", text(w).includes("Requested 3 days of annual leave; 12 days left.") && text(w).includes("Within the balance and policy limits."));
  check("recommendation is green for an approval", $(w, ".rec strong").textContent === "Approve" && $(w, ".rec strong").className === "good");
  check("employee record: balances, manager and start date",
        text(w).includes("12 of 18 days left") && text(w).includes("6 of 10 days left") && text(w).includes("manager M01") && text(w).includes("joined 15 May 2023"));
  check("balance bars are drawn", $$(w, ".track .fill").length === 2);
  check("leave history is a dated table", $$(w, ".facts tbody tr").length === 4 && text(w).includes("5 Oct 2026"));
  check("policy text is shown with plain section names", text(w).includes("Policy the agent used") && text(w).includes("10 consecutive working days") && $$(w, ".policy figcaption").map(f => f.textContent).includes("Annual leave"));
  check("no file names or '>' citations on the case page", !text(w).includes(".md") && !text(w).includes("md >"));
  click(w, $$(w, ".choice").find(b => b.textContent.startsWith("Deny"))); await sleep(100);
  const rec = () => $$(w, "button.btn.primary").find(b => b.textContent.startsWith("Record decision"));
  check("changing the recommendation requires a note", rec().disabled && text(w).includes("note is required"));
  type(w, $(w, "#note"), "team is short that week"); await sleep(100);
  check("note enables the button", !rec().disabled);
  click(w, rec()); await sleep(900);
  check("queue is empty after deciding", text(w).includes("Nothing is waiting"));

  // --- the audit log
  tab(w, "Audit"); await sleep(600);
  const audit = text(w);
  check("audit log names events in words", audit.includes("Leave decision") && audit.includes("Policy answer") && audit.includes("Passed to HR"));
  check("audit log says what was decided and by whom", audit.includes("reviewer chose deny") && audit.includes("HR1") && audit.includes("Note: team is short that week"));
  check("audit log says what was asked", audit.includes("Asked: \u201cHow many sick days do I have left?\u201d") && audit.includes("Sources: Leave policy, Sick leave; Your leave record"));
  check("audit log has no raw event names or file names", !audit.includes("policy_answer") && !audit.includes("escalation") && !audit.includes(".md"));
  check("audit log has no empty dash cells", !audit.includes("\u2013"));

  // --- a reviewer with no leave record cannot make a leave request (it would be a case nobody can decide)
  w = await boot();
  type(w, $(w, "#token"), "hr-nine-token-0009"); submit(w, $(w, "form")); await sleep(800);
  tab(w, "My leave"); await sleep(200);
  await send("I need 3 days off next week", 600);
  check("a reviewer with no leave record is told so, instead of getting a stuck case", text(w).includes("no leave record for HR9"));
  tab(w, "Review queue"); await sleep(300);
  check("and the queue stays empty", text(w).includes("Nothing is waiting"));

  // --- a reviewer who is also an employee: a case about themselves is not theirs to decide
  w = await boot();
  type(w, $(w, "#token"), "e102-rev-token-0002"); submit(w, $(w, "form")); await sleep(800);
  tab(w, "My leave"); await sleep(200);
  await send("I want 1 day annual leave", 900);
  tab(w, "Review queue"); await sleep(500);
  check("a case about the reviewer says another reviewer must decide it",
        text(w).includes("This case is about you") && text(w).includes("About you: another reviewer decides"));
  check("the case names the reviewer who can decide it", text(w).includes("another reviewer has to decide it: HR1"));
  check("and it cannot be decided from that account",
        $$(w, ".choice").length === 3 && $$(w, ".choice").every(b => b.disabled) && button(w, "Another reviewer must decide").disabled);

  // ================= HR tools =================
  w = await boot();
  type(w, $(w, "#token"), "hr-one-token-0003"); submit(w, $(w, "form")); await sleep(900);
  check("HR has its own tools, not just the employee's form",
        ["People", "Screen a resume", "My leave and questions"].every(n => $$(w, ".tab").some(t => t.textContent.includes(n))));
  tab(w, "People"); await sleep(500);
  check("People lists everyone with their balances", $$(w, "tbody tr").length === 5 && text(w).includes("E101") && text(w).includes("HR2"));
  click(w, $$(w, "button.link").find(b => b.textContent === "E101")); await sleep(600);
  check("a person's page shows their record, leave history and requests",
        text(w).includes("12 of 18 days left") && text(w).includes("joined 15 May 2023") && $$(w, "table")[0].querySelectorAll("tbody tr").length === 4
        && text(w).includes("Requests from E101") && text(w).includes("I need 3 days off next week"));
  check("their requests show decisions in words", text(w).includes("Denied"));

  tab(w, "Screen a resume"); await sleep(400);
  check("the screening form offers the jobs and the demo resumes", $$(w, "#job option").length === 6 && $$(w, "#resume-pick option").length >= 7);
  const pick = $(w, "#resume-pick");
  Object.getOwnPropertyDescriptor(w.HTMLSelectElement.prototype, "value").set.call(pick, "10002");
  pick.dispatchEvent(new w.Event("change", { bubbles: true })); await sleep(150);
  check("the resumes are a visible list, and choosing one fills in the number",
        $(w, "#resume").value === "10002" && text(w).includes("10002, Information technology (demo)"));
  check("it says what the job needs", text(w).includes("Must have: python, sql, git"));
  type(w, $(w, "#resume"), "123"); await sleep(100);
  check("a bad resume number is explained and cannot be sent", text(w).includes("5 to 9 digits") && button(w, "Screen resume").disabled);
  type(w, $(w, "#resume"), "99999999"); submit(w, $(w, "form.panel")); await sleep(800);
  check("an unknown resume is answered plainly", text(w).includes("was not found"));
  type(w, $(w, "#resume"), "10001"); submit(w, $(w, "form.panel")); await sleep(1000);
  check("a screened resume goes to the review queue", text(w).includes("Sent to the review queue"));
  click(w, $$(w, "button.link").find(b => b.textContent === "Open the review queue")); await sleep(500);
  click(w, $$(w, ".queue-item").find(b => b.textContent.includes("screen resume 10001"))); await sleep(300);
  check("the case reads as a screening, in green for a shortlist",
        text(w).includes("Screening resume 10001") && $(w, ".rec strong").textContent === "Shortlist" && $(w, ".rec strong").className === "good");
  check("the reasons name the job and the score", text(w).includes("Job: Software Engineer. Score 100 out of 100."));
  const det = $(w, "details.resume"); det.open = true; det.dispatchEvent(new w.Event("toggle")); await sleep(700);
  check("HR can read the resume itself", text(w).includes("Brightwave Systems"));
  const before = $$(w, ".queue-item").length;
  click(w, $$(w, ".choice").find(b => b.textContent.startsWith("Shortlist"))); await sleep(100);
  click(w, button(w, "Record decision")); await sleep(900);
  check("the decision clears it from the queue", $$(w, ".queue-item").length === before - 1);

  // --- the shortlisted resume is now a candidate: interviews, feedback, and the hiring decision
  tab(w, "Candidates"); await sleep(500);
  check("the shortlisted resume is now a candidate",
        $$(w, "tbody tr").length === 1 && text(w).includes("Software Engineer") && text(w).includes("Shortlisted"));
  click(w, $$(w, "button.link").find(b => b.textContent === "Candidate 1")); await sleep(600);
  check("the candidate page shows the job, the resume and the stage",
        text(w).includes("Candidate 1: Software Engineer") && text(w).includes("Resume 10001") && text(w).includes("Shortlisted") && !!$(w, "details.resume"));
  check("it offers the interviewers and the interview types",
        $$(w, "#who option").map(o => o.value).join() === "E102,HR1,HR9" && $$(w, "#kind option").length === 3);
  check("the interviewer defaults to the signed-in reviewer", $(w, "#who").value === "HR1");
  click(w, $$(w, "button.link").find(b => b.textContent === "Use the current time")); await sleep(100);
  submit(w, $$(w, "form.subform")[0]); await sleep(900);
  check("an interview is scheduled and the candidate is interviewing",
        text(w).includes("Interviewing") && text(w).includes("Scheduled") && text(w).includes("Technical"));
  check("the round that is booked is greyed out, and the form moves on to a free one",
        $(w, "#kind").value !== "technical" && $$(w, "#kind option").filter(o => o.disabled).map(o => o.value).join() === "technical");
  check("a decision cannot be asked for yet, and the page says why",
        button(w, "Request hiring decision").disabled && text(w).includes("at least one finished interview"));
  click(w, button(w, "Add feedback")); await sleep(200);
  check("a note that is too short cannot be saved", button(w, "Save feedback").disabled);
  type(w, $(w, "#fb"), "Excellent design discussion."); await sleep(100);
  submit(w, $$(w, "form.subform").find(f => f.textContent.includes("Your feedback"))); await sleep(900);
  check("feedback is saved with its rating",
        text(w).includes("5 out of 5") && text(w).includes("Completed") && text(w).includes("Excellent design discussion."));
  check("now a hiring decision can be requested", !button(w, "Request hiring decision").disabled);
  click(w, button(w, "Request hiring decision")); await sleep(1000);
  check("the request goes to the review queue", text(w).includes("Sent to the review queue"));
  click(w, $$(w, "button.link").find(b => b.textContent === "Open the review queue")); await sleep(500);
  click(w, $$(w, ".queue-item").find(b => b.textContent.includes("Hiring decision"))); await sleep(300);
  check("the case reads as a hiring decision, with the offer in green",
        text(w).includes("Hiring decision for candidate 1") && $(w, ".rec strong").textContent === "Make offer" && $(w, ".rec strong").className === "good");
  check("it shows the interview feedback and the ratings",
        text(w).includes("Excellent design discussion.") && text(w).includes("Average interview rating 5.0 out of 5 from 1 interview.") && !!$(w, "details.resume"));
  check("a single interview is flagged for a second opinion", text(w).includes("The agent flagged this one") && text(w).includes("Only one interview"));
  const beforeOffer = $$(w, ".queue-item").length;
  click(w, $$(w, ".choice").find(b => b.textContent.startsWith("Make offer"))); await sleep(100);
  click(w, button(w, "Record decision")); await sleep(900);
  check("the decision clears it from the queue", $$(w, ".queue-item").length === beforeOffer - 1);
  tab(w, "Candidates"); await sleep(500);
  check("the candidate now shows the offer", text(w).includes("Offer made") && text(w).includes("5 out of 5"));
  tab(w, "Audit"); await sleep(600);
  check("the audit log records the lookups and the screening decision",
        text(w).includes("Record viewed") && text(w).includes("Opened by HR1") && text(w).includes("Screening decision"));
  check("the audit log records the interview and the hiring decision",
        ["Interview scheduled", "Interview feedback", "Hiring decision", "Candidate update", "Candidate 1"].every(x => text(w).includes(x))
        && text(w).includes("rated the interview 5 out of 5"));

  // ================= employee again =================
  w = await boot();
  type(w, $(w, "#token"), "emp101-token-0001"); submit(w, $(w, "form")); await sleep(800);
  check("denials are red", $$(w, ".status.bad").length === 2 && $$(w, ".status.good").length === 0);
  check("decisions are in words, with the reviewer's note", text(w).includes("Denied") && text(w).includes("Reviewer note: team is short that week"));
  check("the HR hand-off keeps its own status", text(w).includes("Passed to HR"));

  console.log(`\n${results.filter(Boolean).length} of ${results.length} UI checks passed`);
  process.exit(results.every(Boolean) ? 0 : 1);
})();
