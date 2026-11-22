/* SynapseHR review page. React 18 via createElement (no build step). */
(function () {
  "use strict";
  var h = React.createElement, useState = React.useState, useEffect = React.useEffect, useCallback = React.useCallback;

  var KEY = "synapsehr_token";
  var KIND_LABEL = { resume_screening: "Resume screening", leave_request: "Leave request", hiring_decision: "Hiring decision" };
  var AGENT_LABEL = { resume_screening: "Screening agent", leave_request: "Leave agent", hiring_decision: "Hiring agent" };
  var STAGE = {
    shortlisted:  { label: "Shortlisted",        tone: "neutral" },
    needs_review: { label: "Waiting for review", tone: "warn" },
    interviewing: { label: "Interviewing",       tone: "warn" },
    offer:        { label: "Offer made",         tone: "good" },
    rejected:     { label: "Rejected",           tone: "bad" }
  };
  var EXAMPLES = ["How many sick days do I have left?", "Can I work from home?", "I need 3 days off next week", "I want 14 days of annual leave"];

  /* the words a person sees for each decision, and whether it is good news (green), bad news (red) or neither (amber) */
  var DECISION = {
    approve:   { action: "Approve",       done: "Approved",           tone: "good" },
    deny:      { action: "Deny",          done: "Denied",             tone: "bad" },
    escalate:  { action: "Escalate",      done: "Escalated",          tone: "warn" },
    shortlist: { action: "Shortlist",     done: "Shortlisted",        tone: "good" },
    review:    { action: "Needs review",  done: "Marked for review",  tone: "warn" },
    reject:    { action: "Reject",        done: "Rejected",           tone: "bad" },
    offer:     { action: "Make offer",    done: "Offer made",         tone: "good" },
    hold:      { action: "Hold",          done: "On hold",            tone: "warn" }
  };
  function cap(s) { s = String(s || ""); return s.charAt(0).toUpperCase() + s.slice(1); }
  function actionLabel(c) { return (DECISION[c] || { action: cap(c) }).action; }
  function doneLabel(c) { return (DECISION[c] || { done: cap(c) }).done; }
  function toneOf(c) { return (DECISION[c] || { tone: "neutral" }).tone; }
  function plural(n, word) { return n + " " + word + (n === 1 ? "" : "s"); }

  function getToken() { try { return sessionStorage.getItem(KEY) || ""; } catch (e) { return ""; } }
  function setToken(t) { try { t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY); } catch (e) {} }

  function ApiError(status, message) { this.status = status; this.message = message; }

  function api(path, options) {
    options = options || {};
    var headers = { "X-API-Key": getToken() };
    if (options.body) headers["Content-Type"] = "application/json";
    return fetch(path, { method: options.method || "GET", headers: headers, body: options.body ? JSON.stringify(options.body) : undefined })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) {
            var d = data.detail;
            var msg = typeof d === "string" ? d : Array.isArray(d) ? d.map(function (x) { return x.msg; }).join("; ") : "Something went wrong (" + res.status + ").";
            throw new ApiError(res.status, msg);
          }
          return data;
        });
      });
  }

  /* ---------- wording and dates ---------- */
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function when(iso) {                                   // "18 Nov, 5:58 am"
    var d = new Date(iso);
    if (isNaN(d)) return iso;
    var hour = d.getHours() % 12 || 12, min = d.getMinutes();
    return d.getDate() + " " + MONTHS[d.getMonth()] + ", " + hour + ":" + (min < 10 ? "0" : "") + min + (d.getHours() >= 12 ? " pm" : " am");
  }
  function dayLabel(iso) {                               // "5 Oct 2026"
    var d = new Date(String(iso).length === 10 ? iso + "T00:00:00" : iso);
    return isNaN(d) ? iso : d.getDate() + " " + MONTHS[d.getMonth()] + " " + d.getFullYear();
  }

  /* "(leave_policy.md > Annual leave)" is a code-level citation. Show "(Annual leave policy)" instead. */
  function cleanReason(text) {
    var t = text.replace(/\s*\(\s*[\w.-]+\.md\s*>\s*([^)]+?)\s*\)/g, function (_, section) {
      return " (" + cap(section.toLowerCase()) + " policy)";
    });
    return cap(t);
  }

  /* "leave_policy.md > Carry over" -> { document: "Leave policy", section: "Carry over" } */
  function sourceName(source) {
    var parts = source.split(">"), file = parts[0].trim().replace(/\.md$/i, "").replace(/[_-]+/g, " ");
    return { document: cap(file), section: (parts[1] || "").trim() };
  }
  function sourceLabel(source) {
    var n = sourceName(source);
    return n.section ? n.document + ", " + n.section : n.document;
  }

  /* The server already sends answers clean. This only covers an answer that still carries "[source: ...]" tags. */
  function splitAnswer(text) {
    var sources = [];
    var body = (text || "").replace(/\s*\[source:\s*([^\]]+?)\s*\]/g, function (_, src) { sources.push(sourceLabel(src)); return ""; }).trim();
    return { body: body, sources: sources };
  }

  /* ---------- small pieces ---------- */
  function Notice(props) {
    return props.text ? h("div", { className: "notice " + (props.kind || ""), role: props.kind === "error" ? "alert" : "status" }, props.text) : null;
  }

  function Answer(props) {
    var body = props.text, sources = props.sources;
    if (!sources || sources.length === 0) { var a = splitAnswer(props.text); body = a.body; sources = a.sources; }
    return h("div", { className: props.className },
      h("div", null, body),
      sources.length > 0 && h("div", { className: "source" }, (sources.length > 1 ? "Sources: " : "Source: ") + sources.join("; ")));
  }

  function StatusChip(props) {
    var r = props.item;
    if (r.status === "awaiting_human") return h("span", { className: "status waiting" }, "Waiting for a reviewer");
    if (r.status === "passed_to_hr") return h("span", { className: "status waiting" }, "Passed to HR");
    if (r.outcome && r.outcome.final_decision) {
      return h("span", { className: "status " + toneOf(r.outcome.final_decision) }, doneLabel(r.outcome.final_decision));
    }
    return h("span", { className: "status neutral" }, "Answered");
  }

  /* where the case sits in the graph: supervisor -> specialist -> human checkpoint -> decision */
  function Flow(props) {
    var kind = props.kind, decided = props.decided;
    var steps = [
      { name: "Supervisor", note: "routed", state: "done" },
      { name: AGENT_LABEL[kind] || "Agent", note: "recommended", state: "done" },
      { name: "Human checkpoint", note: decided ? "reviewed" : "graph is paused", state: decided ? "done" : "paused" },
      { name: "Decision", note: decided ? "logged" : "not yet made", state: decided ? "done" : "" }
    ];
    return h("ol", { className: "flow", "aria-label": "Where this case is in the workflow" },
      steps.map(function (s) {
        return h("li", { key: s.name, className: s.state, "aria-current": s.state === "paused" ? "step" : undefined },
          h("span", { className: "step" }, s.name), s.note);
      }));
  }

  /* ---------- sign in ---------- */
  function Login(props) {
    var _t = useState(""), token = _t[0], setTok = _t[1];
    var _e = useState(""), error = _e[0], setError = _e[1];
    var _b = useState(false), busy = _b[0], setBusy = _b[1];
    function submit(ev) {
      ev.preventDefault();
      setBusy(true); setError(""); setToken(token.trim());
      api("/me").then(props.onSignedIn).catch(function (e) {
        setToken(""); setError(e.status === 401 ? "That API key was not accepted. Check it and try again." : e.message);
      }).then(function () { setBusy(false); });
    }
    return h("main", null, h("div", { className: "panel login" },
      h("h1", null, "SynapseHR"),
      h("p", { className: "lede" }, "Every leave and screening decision waits here for a person to approve, change or reject it."),
      h("form", { onSubmit: submit },
        h("div", { className: "field" },
          h("label", { htmlFor: "token" }, "API key"),
          h("input", { id: "token", type: "password", autoComplete: "off", value: token, onChange: function (e) { setTok(e.target.value); }, required: true }),
          h("div", { className: "hint" }, "The server prints demo keys in its console when it starts.")),
        h(Notice, { kind: "error", text: error }),
        h("button", { className: "btn primary", disabled: busy || !token.trim() }, busy ? "Signing in" : "Sign in"))));
  }

  /* ---------- send a request ---------- */
  function Composer(props) {
    var _m = useState(""), message = _m[0], setMessage = _m[1];
    var _b = useState(false), busy = _b[0], setBusy = _b[1];
    var _r = useState(null), result = _r[0], setResult = _r[1];
    var _e = useState(""), error = _e[0], setError = _e[1];
    var examples = EXAMPLES;
    function send(ev) {
      ev.preventDefault();
      setBusy(true); setError(""); setResult(null);
      api("/requests", { method: "POST", body: { message: message } }).then(function (r) {
        setResult(r); setMessage(""); props.onSent();
      }).catch(function (e) { setError(e.message); }).then(function () { setBusy(false); });
    }
    return h("form", { className: "panel", onSubmit: send },
      h("h2", null, props.title || "Send a request"),
      h("div", { className: "field" },
        h("label", { htmlFor: "msg" }, "What do you need?"),
        h("textarea", { id: "msg", rows: 3, maxLength: 2000, value: message, onChange: function (e) { setMessage(e.target.value); },
          placeholder: "Ask about a policy or your own leave, or request time off. For example: I need 3 days off next week" }),
        h("div", { className: "chips" }, examples.map(function (x) {
          return h("button", { type: "button", key: x, className: "chip", onClick: function () { setMessage(x); } }, x);
        }))),
      h(Notice, { kind: "error", text: error }),
      result && result.status === "awaiting_human" && h(Notice, { kind: "paused", text: "Sent. A reviewer has to decide this one before it is final." }),
      result && result.status === "passed_to_hr" && h(Answer, { className: "notice paused", text: result.answer || "This has been passed to HR.", sources: result.sources }),
      result && result.status === "completed" && h(Answer, { className: "notice ok", text: result.answer || "Done.", sources: result.sources }),
      h("button", { className: "btn primary", disabled: busy || !message.trim() }, busy ? "Sending" : "Send request"));
  }

  function RequestList(props) {
    var items = props.items;
    return h("div", { className: "panel" }, h("h2", null, props.title),
      items === null ? h("p", { className: "empty" }, "Loading") :
      items.length === 0 ? h("p", { className: "empty" }, "No requests yet. Send one above and it will show up here.") :
      items.map(function (r) {
        return h("div", { className: "request", key: r.thread_id },
          h("div", { className: "request-head" }, h("span", { className: "msg" }, r.message), h(StatusChip, { item: r })),
          h("div", { className: "meta" }, (props.showOwner ? r.owner + ", " : "") + when(r.created_at)),
          r.answer && h(Answer, { className: "answer", text: r.answer, sources: r.sources }),
          r.outcome && r.outcome.note && h("div", { className: "meta" }, "Reviewer note: " + r.outcome.note));
      }));
  }

  /* ---------- reviewer: the facts beside a recommendation ---------- */
  var TYPE_LABEL = { annual: "Annual", sick: "Sick" };

  function Balance(props) {
    var pct = props.total > 0 ? Math.max(0, Math.min(100, (props.left / props.total) * 100)) : 0;
    return h("div", { className: "balance" },
      h("div", { className: "balance-row" }, h("span", null, props.label), h("strong", { className: props.left <= 0 ? "bad" : "" }, props.left + " of " + props.total + " days left")),
      h("div", { className: "track", role: "img", "aria-label": props.label + ": " + props.left + " of " + props.total + " days left" },
        h("div", { className: "fill" + (props.left <= 0 ? " empty" : ""), style: { width: pct + "%" } })));
  }

  function EmployeeRecord(props) {
    var e = props.employee, history = props.history;
    return h("div", null,
      h("h2", null, "Employee record"),
      h("p", { className: "meta" }, e.employee_id + (e.manager ? ", manager " + e.manager : "") + (e.hire_date ? ", joined " + dayLabel(e.hire_date) : "")),
      h(Balance, { label: "Annual leave", left: e.annual_balance, total: e.annual_entitlement }),
      h(Balance, { label: "Sick leave", left: e.sick_balance, total: e.sick_entitlement }),
      h("h2", { className: "spaced" }, "Leave taken this year"),
      history.length === 0 ? h("p", { className: "meta" }, "No leave on record.") :
      h("table", null,
        h("thead", null, h("tr", null, ["Date", "Type", "Days"].map(function (x) { return h("th", { key: x, scope: "col" }, x); }))),
        h("tbody", null, history.map(function (x, i) {
          return h("tr", { key: i },
            h("td", null, dayLabel(x.date)),
            h("td", null, (TYPE_LABEL[x.kind] || cap(x.kind)) + (x.source === "approved here" ? " (approved here)" : "")),
            h("td", null, x.days));
        }))));
  }

  function CaseFacts(props) {
    var c = props.context;
    return h("div", { className: "facts" },
      h(EmployeeRecord, { employee: c.employee, history: c.history }),
      h("div", null,
        h("h2", null, "Policy the agent used"),
        c.policy.length === 0 ? h("p", { className: "meta" }, "No policy text found for this kind of leave.") :
        h("p", { className: "meta" }, "From the " + sourceName(c.policy[0].source).document.toLowerCase() + " document."),
        c.policy.map(function (x) {
          return h("figure", { className: "policy", key: x.source },
            h("figcaption", null, sourceName(x.source).section || sourceName(x.source).document), h("blockquote", null, x.text));
        })));
  }

  /* the resume itself, fetched only when HR opens it (every look is logged by the server) */
  function ResumeText(props) {
    var _t = useState(null), text = _t[0], setText = _t[1];
    var _e = useState(""), error = _e[0], setError = _e[1];
    function toggle(ev) {
      if (ev.target.open && text === null && !error) {
        api("/resumes/" + props.id).then(function (r) { setText(r.text); }).catch(function (e) { setError(e.message); });
      }
    }
    return h("details", { className: "resume", onToggle: toggle },
      h("summary", null, "Read the resume"),
      error ? h(Notice, { kind: "error", text: error }) : text === null ? h("p", { className: "meta" }, "Loading") : h("pre", { className: "resume-text" }, text));
  }

  /* ---------- reviewer: queue and decision ---------- */
  function CaseDetail(props) {
    var item = props.item, p = item.proposal, blocked = p.approve_blocked;
    var own = p.subject_id === props.user.user_id;            // nobody decides a case about themselves
    var _c = useState(""), choice = _c[0], setChoice = _c[1];
    var _n = useState(""), note = _n[0], setNote = _n[1];
    var _b = useState(false), busy = _b[0], setBusy = _b[1];
    var _e = useState(""), error = _e[0], setError = _e[1];
    useEffect(function () { setChoice(""); setNote(""); setError(""); }, [item.thread_id]);
    useEffect(function () { if (choice === "approve" && blocked) setChoice(""); }, [blocked]);   // a refresh can make approving impossible
    var overriding = choice && choice !== p.recommendation;
    function confirm() {
      setBusy(true); setError("");
      api("/decisions/" + item.thread_id, { method: "POST", body: { final: choice, note: note } })
        .then(function () { props.onDecided(item.thread_id, choice); })
        .catch(function (e) { setError(e.message); props.onRefresh(); }).then(function () { setBusy(false); });
    }
    return h("section", { className: "panel", "aria-label": "Case detail" },
      h("h1", null, p.kind === "resume_screening" ? "Screening resume " + p.subject_id
        : p.kind === "hiring_decision" ? "Hiring decision for candidate " + p.subject_id : (KIND_LABEL[p.kind] || p.kind) + " for " + p.subject_id),
      h("p", { className: "meta" }, (p.kind === "hiring_decision" ? "Requested by " : "Sent by ") + item.employee_id + ", " + when(item.created_at)),
      p.kind !== "hiring_decision" && h("blockquote", { className: "ask" }, item.message),
      h(Flow, { kind: p.kind, decided: false }),
      p.kind === "resume_screening" && h(ResumeText, { id: p.subject_id }),
      p.candidate && h(CandidateFacts, { candidate: p.candidate }),
      own && h(Notice, { kind: "paused", text: p.other_reviewers && p.other_reviewers.length
        ? "This case is about you, so another reviewer has to decide it: " + p.other_reviewers.join(", ") + ". Nothing is needed from you."
        : "This case is about you, and no other reviewer is set up, so nobody can decide it yet. Add a second reviewer key (see SYNAPSEHR_TOKENS in the README)." }),
      !own && blocked && h(Notice, { kind: "error", text: blocked }),
      !own && !blocked && p.flagged && h(Notice, { kind: "error", text: "The agent flagged this one. Check it yourself before deciding." }),
      h("div", { className: "rec" }, "The agent recommends", h("strong", { className: toneOf(p.recommendation) }, actionLabel(p.recommendation))),
      h("ul", { className: "reasons" }, p.reasons.map(function (r, i) { return h("li", { key: i }, cleanReason(r)); })),
      p.context && h(CaseFacts, { context: p.context, kind: p.kind }),
      h("div", { role: "group", "aria-label": "Your decision", className: "choices" }, p.choices.map(function (c) {
        var off = own || (c === "approve" && !!blocked);
        return h("button", { key: c, className: "choice", "aria-pressed": choice === c, disabled: off, onClick: function () { setChoice(c); } },
          actionLabel(c),
          off && !own ? h("small", null, "not allowed") : !own && c === p.recommendation && h("small", null, "agent's pick"));
      })),
      h("div", { className: "field" },
        h("label", { htmlFor: "note" }, overriding ? "Why are you changing the agent's recommendation?" : "Note (optional)"),
        h("textarea", { id: "note", rows: 2, maxLength: 1000, value: note, onChange: function (e) { setNote(e.target.value); } })),
      h(Notice, { kind: "error", text: error }),
      h("button", { className: "btn primary", disabled: own || !choice || busy || (overriding && !note.trim()), onClick: confirm },
        own ? "Another reviewer must decide" : busy ? "Recording" : choice ? "Record decision: " + actionLabel(choice) : "Choose a decision"),
      overriding && !note.trim() && h("div", { className: "hint" }, "A note is required when you change the recommendation."));
  }

  function ReviewQueue(props) {
    var pending = props.pending, _s = useState(null), selected = _s[0], setSelected = _s[1];
    var current = pending && (pending.find(function (x) { return x.thread_id === selected; }) || pending[0]);
    if (pending === null) return h("p", { className: "empty" }, "Loading");
    if (pending.length === 0) return h("div", { className: "panel" }, h("h2", null, "Nothing is waiting"),
      h("p", { className: "lede" }, "When someone sends a leave request or a resume is screened, the case appears here and stays until you decide."));
    return h("div", { className: "review" },
      h("div", { className: "panel queue", role: "list", "aria-label": "Waiting cases" }, pending.map(function (x) {
        return h("button", { key: x.thread_id, role: "listitem", className: "queue-item",
            "aria-current": current && current.thread_id === x.thread_id, onClick: function () { setSelected(x.thread_id); } },
          h("div", { className: "kind" }, KIND_LABEL[x.proposal.kind] || x.proposal.kind),
          h("div", { className: "msg" }, x.message),
          h("div", { className: "sub" }, x.proposal.subject_id + ", " + when(x.created_at)),
          x.proposal.subject_id === props.user.user_id ? h("div", { className: "flag" }, "About you: another reviewer decides")
            : x.proposal.approve_blocked ? h("div", { className: "flag" }, "Cannot be approved")
            : x.proposal.flagged && h("div", { className: "flag" }, "Flagged by the agent"));
      })),
      current && h(CaseDetail, { item: current, user: props.user, onDecided: props.onDecided, onRefresh: props.onRefresh }));
  }

  /* ---------- candidates and interviews ---------- */
  function StageChip(props) {
    var st = STAGE[props.stage] || { label: cap(String(props.stage).replace(/_/g, " ")), tone: "neutral" };
    return h("span", { className: "status " + st.tone }, st.label);
  }

  var INTERVIEW_TONE = { scheduled: "warn", completed: "good", cancelled: "neutral" };

  function InterviewTable(props) {
    var rows = props.interviews;
    if (!rows.length) return h("p", { className: "meta" }, "No interviews yet.");
    return h("div", { className: "table-wrap" }, h("table", { className: "interviews" },
      h("thead", null, h("tr", null, ["When", "Type", "Interviewer", "Status", "Rating", "Feedback"].concat(props.actions ? ["Actions"] : [])
        .map(function (c) { return h("th", { key: c, scope: "col" }, c); }))),
      h("tbody", null, rows.map(function (i) {
        return h("tr", { key: i.interview_id },
          h("td", { className: "nowrap" }, when(i.scheduled_for)),
          h("td", null, cap(i.kind)),
          h("td", null, i.interviewer),
          h("td", null, h("span", { className: "status " + INTERVIEW_TONE[i.status] }, cap(i.status))),
          h("td", { className: "nowrap" }, i.rating != null ? i.rating + " out of 5" : ""),
          h("td", null, i.feedback || ""),
          props.actions && h("td", null, props.actions(i)));
      }))));
  }

  /* the candidate beside a hiring recommendation */
  function CandidateFacts(props) {
    var c = props.candidate;
    return h("div", { className: "block" },
      h("h2", null, "Candidate"),
      h("p", { className: "meta" }, c.job_title + ", resume " + c.resume_id +
        (c.screening_decision ? ". Screened: " + c.screening_decision + (c.screening_score != null ? " (" + c.screening_score + " out of 100)" : "") : "")),
      h(InterviewTable, { interviews: c.interviews }),
      h("div", { style: { height: 12 } }),
      h(ResumeText, { id: c.resume_id }));
  }

  function nowLocal(plusHours) {                          // "2026-11-20T10:00" in the browser's own time
    var d = new Date();
    d.setSeconds(0, 0);
    if (plusHours) { d.setMinutes(0); d.setHours(d.getHours() + plusHours); }
    function p(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T" + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  function CandidatePage(props) {
    var me = props.user;
    var _d = useState(null), detail = _d[0], setDetail = _d[1];
    var _e = useState(""), error = _e[0], setError = _e[1];
    var _b = useState(false), busy = _b[0], setBusy = _b[1];
    var _k = useState("technical"), kind = _k[0], setKind = _k[1];
    var _w = useState(nowLocal(1)), at = _w[0], setAt = _w[1];
    var _i = useState(""), who = _i[0], setWho = _i[1];
    var _f = useState(null), fbFor = _f[0], setFbFor = _f[1];
    var _r = useState("5"), rating = _r[0], setRating = _r[1];
    var _n = useState(""), note = _n[0], setNote = _n[1];
    var _s = useState(null), sent = _s[0], setSent = _s[1];

    function got(d) {
      var taken = d.interviews.filter(function (i) { return i.status !== "cancelled"; }).map(function (i) { return i.kind; });
      var free = d.kinds.filter(function (k) { return taken.indexOf(k) < 0; });
      setKind(function (k) { return taken.indexOf(k) < 0 ? k : free[0] || k; });          // never leave a booked round selected
      setDetail(d); setError("");
      setWho(function (w) { return w || (d.interviewers.indexOf(me.user_id) >= 0 ? me.user_id : d.interviewers[0] || ""); });
      props.onChanged();
    }
    function fail(e) { setError(e.message); }
    useEffect(function () { setDetail(null); setSent(null); api("/candidates/" + props.id).then(got).catch(fail); }, [props.id]);

    function schedule(ev) {
      ev.preventDefault(); setBusy(true); setError("");
      api("/candidates/" + props.id + "/interviews", { method: "POST", body: { kind: kind, scheduled_for: at, interviewer: who } })
        .then(got).catch(fail).then(function () { setBusy(false); });
    }
    function saveFeedback(ev) {
      ev.preventDefault(); setBusy(true); setError("");
      api("/interviews/" + fbFor + "/feedback", { method: "POST", body: { rating: parseInt(rating, 10), feedback: note } })
        .then(function (d) { setFbFor(null); setNote(""); got(d); }).catch(fail).then(function () { setBusy(false); });
    }
    function cancel(id) {
      setError("");
      api("/interviews/" + id + "/cancel", { method: "POST" }).then(got).catch(fail);
    }
    function askDecision() {
      setBusy(true); setError("");
      api("/candidates/" + props.id + "/decision-request", { method: "POST" })
        .then(function (r) { setSent(r); props.onChanged(); }).catch(fail).then(function () { setBusy(false); });
    }

    if (!detail) return h("div", null, h("button", { className: "btn small", onClick: props.onBack }, "All candidates"),
      error ? h(Notice, { kind: "error", text: error }) : h("p", { className: "empty" }, "Loading"));

    var c = detail.candidate, active = detail.interviews.filter(function (i) { return i.status !== "cancelled"; });
    var pendingOnes = active.filter(function (i) { return i.status === "scheduled"; }).length;
    var taken = active.map(function (i) { return i.kind; });
    var roundsLeft = detail.kinds.filter(function (k) { return taken.indexOf(k) < 0; });
    var canSchedule = (c.stage === "shortlisted" || c.stage === "interviewing") && roundsLeft.length > 0;
    var decisionHint = c.stage !== "interviewing" ? null : c.completed === 0 ? "A hiring decision needs at least one finished interview."
      : pendingOnes ? "Finish or cancel the interviews that are still scheduled first." : null;
    var canDecide = c.stage === "interviewing" && !decisionHint;

    return h("div", null,
      h("button", { className: "btn small", onClick: props.onBack }, "All candidates"),
      h("div", { style: { height: 16 } }),
      h("div", { className: "panel" },
        h("h1", null, "Candidate " + c.candidate_id + ": " + c.job_title),
        h("p", { className: "meta" }, "Resume " + c.resume_id + (detail.category ? ", " + cap(detail.category.toLowerCase().replace(/-/g, " ")) : "") +
          (c.screening_decision ? ". Screening decision: " + c.screening_decision + (c.screening_score != null ? ", score " + c.screening_score + " out of 100" : "") : "") + ". "),
        h(StageChip, { stage: c.stage }),
        detail.other_applications.length > 0 && h("div", { className: "others" },
          h("h2", null, "Also applied for"),
          detail.other_applications.map(function (o) {
            return h("div", { key: o.candidate_id, className: "meta" }, o.job_title + ": ", h(StageChip, { stage: o.stage }),
              " ", h("button", { className: "link", onClick: function () { props.onOpen(o.candidate_id); } }, "Open"));
          })),
        h("div", { style: { height: 12 } }),
        h(ResumeText, { id: c.resume_id })),
      h("div", { style: { height: 20 } }),
      h("div", { className: "panel" }, h("h2", null, "Interviews"),
        h(InterviewTable, { interviews: detail.interviews, actions: function (i) {
          if (i.status !== "scheduled") return null;
          return h("span", { className: "actions" },
            i.interviewer === me.user_id && h("button", { className: "btn small", onClick: function () { setFbFor(i.interview_id); } }, "Add feedback"),
            h("button", { className: "btn small", onClick: function () { cancel(i.interview_id); } }, "Cancel"));
        } }),
        fbFor && h("form", { className: "subform", onSubmit: saveFeedback },
          h("h2", null, "Your feedback"),
          h("div", { className: "field" }, h("label", { htmlFor: "rating" }, "Rating"),
            h("select", { id: "rating", value: rating, onChange: function (e) { setRating(e.target.value); } },
              ["5", "4", "3", "2", "1"].map(function (n) { return h("option", { key: n, value: n }, n + " out of 5"); }))),
          h("div", { className: "field" }, h("label", { htmlFor: "fb" }, "What did you see?"),
            h("textarea", { id: "fb", rows: 3, maxLength: 2000, value: note, onChange: function (e) { setNote(e.target.value); } }),
            h("div", { className: "hint" }, "At least 10 characters. This is part of the record the hiring decision rests on.")),
          h("button", { className: "btn primary", disabled: busy || note.trim().length < 10 }, busy ? "Saving" : "Save feedback"),
          " ", h("button", { type: "button", className: "btn", onClick: function () { setFbFor(null); } }, "Close")),
        h(Notice, { kind: "error", text: error }),
        canSchedule && h("form", { className: "subform", onSubmit: schedule },
          h("h2", null, "Schedule an interview"),
          h("div", { className: "row3" },
            h("div", { className: "field" }, h("label", { htmlFor: "kind" }, "Type"),
              h("select", { id: "kind", value: kind, onChange: function (e) { setKind(e.target.value); } },
                detail.kinds.map(function (k) { return h("option", { key: k, value: k, disabled: taken.indexOf(k) >= 0 }, cap(k) + (taken.indexOf(k) >= 0 ? " (booked)" : "")); }))),
            h("div", { className: "field" }, h("label", { htmlFor: "at" }, "Date and time"),
              h("input", { id: "at", type: "datetime-local", value: at, onChange: function (e) { setAt(e.target.value); } }),
              h("button", { type: "button", className: "link", onClick: function () { setAt(nowLocal(0)); } }, "Use the current time")),
            h("div", { className: "field" }, h("label", { htmlFor: "who" }, "Interviewer"),
              h("select", { id: "who", value: who, onChange: function (e) { setWho(e.target.value); } },
                detail.interviewers.map(function (p) { return h("option", { key: p, value: p }, p); })))),
          h("button", { className: "btn primary", disabled: busy || !at || !who }, busy ? "Scheduling" : "Schedule interview"),
          h("div", { className: "hint" }, "Each round can be booked once, up to 90 days ahead. Only the interviewer can record feedback, and only once the interview has started.")),
        !canSchedule && h("p", { className: "meta" }, c.stage === "shortlisted" || c.stage === "interviewing"
          ? "All three rounds (phone screen, technical, final) are booked or done. Cancel one if it needs a new time."
          : "No more interviews can be scheduled: this candidate is " + (STAGE[c.stage] || { label: c.stage }).label.toLowerCase() + ".")),
      h("div", { style: { height: 20 } }),
      h("div", { className: "panel" }, h("h2", null, "Hiring decision"),
        sent && sent.status === "awaiting_human" ? h("div", { className: "notice paused", role: "status" },
          "Sent to the review queue. ", h("button", { type: "button", className: "link", onClick: props.onOpenQueue }, "Open the review queue"))
        : h("div", null,
          h("p", { className: "meta" }, c.stage === "interviewing" ? "The agent recommends from the interview ratings. A reviewer decides." : "Nothing to decide at this stage."),
          decisionHint && h("p", { className: "hint" }, decisionHint),
          h("button", { className: "btn primary", disabled: busy || !canDecide, onClick: askDecision }, "Request hiring decision"))));
  }

  function Candidates(props) {
    var _l = useState(null), rows = _l[0], setRows = _l[1];
    var _s = useState(null), selected = _s[0], setSelected = _s[1];
    var _e = useState(""), error = _e[0], setError = _e[1];
    var _t = useState(0), n = _t[0], setN = _t[1];
    useEffect(function () { api("/candidates").then(setRows).catch(function (e) { setError(e.message); }); }, [props.refresh, n]);
    if (error) return h(Notice, { kind: "error", text: error });
    if (selected) return h(CandidatePage, { id: selected, user: props.user, onBack: function () { setSelected(null); setN(n + 1); },
      onOpen: setSelected, onChanged: function () { props.onChanged(); }, onOpenQueue: props.onOpenQueue });
    if (rows === null) return h("p", { className: "empty" }, "Loading");
    if (rows.length === 0) return h("div", { className: "panel" }, h("h1", null, "Candidates"),
      h("p", { className: "lede" }, "Nobody yet. When you shortlist a screened resume, that person becomes a candidate here, and you can schedule interviews."),
      h("button", { className: "btn primary", onClick: props.onOpenScreen }, "Screen a resume"));
    return h("div", { className: "panel table-wrap" }, h("h1", null, "Candidates"),
      h("p", { className: "lede" }, "Everyone whose resume has been screened. Open a candidate to see their resume, interviews and feedback."),
      h("table", null,
        h("thead", null, h("tr", null, ["Candidate", "Job", "Resume", "Stage", "Interviews", "Next interview", "Average rating"].map(function (c) { return h("th", { key: c, scope: "col" }, c); }))),
        h("tbody", null, rows.map(function (r) {
          return h("tr", { key: r.candidate_id },
            h("td", null, h("button", { className: "link", onClick: function () { setSelected(r.candidate_id); } }, "Candidate " + r.candidate_id)),
            h("td", null, r.job_title),
            h("td", null, r.resume_id),
            h("td", null, h(StageChip, { stage: r.stage })),
            h("td", null, r.interviews ? r.interviews + (r.completed ? " (" + r.completed + " done)" : "") : "None"),
            h("td", { className: "nowrap" }, r.next_interview ? when(r.next_interview) : ""),
            h("td", null, r.avg_rating != null ? r.avg_rating + " out of 5" : ""));
        }))));
  }

  /* ---------- HR tools ---------- */
  function People(props) {
    var _l = useState(null), rows = _l[0], setRows = _l[1];
    var _s = useState(null), selected = _s[0], setSelected = _s[1];
    var _d = useState(null), detail = _d[0], setDetail = _d[1];
    var _e = useState(""), error = _e[0], setError = _e[1];
    useEffect(function () { api("/employees").then(setRows).catch(function (e) { setError(e.message); }); }, [props.refresh]);
    useEffect(function () {
      setDetail(null);
      if (selected) api("/employees/" + selected).then(setDetail).catch(function (e) { setError(e.message); });
    }, [selected]);
    if (error) return h(Notice, { kind: "error", text: error });
    if (selected) {
      return h("div", null,
        h("button", { className: "btn small", onClick: function () { setSelected(null); } }, "All people"),
        h("div", { style: { height: 16 } }),
        detail === null ? h("p", { className: "empty" }, "Loading") :
        h("div", null,
          h("div", { className: "panel" }, h("h1", null, detail.employee.employee_id),
            h("p", { className: "meta" }, "Opening this page is written to the audit log."),
            h(EmployeeRecord, { employee: detail.employee, history: detail.history })),
          h("div", { style: { height: 20 } }),
          h(RequestList, { title: "Requests from " + detail.employee.employee_id, items: detail.requests })));
    }
    if (rows === null) return h("p", { className: "empty" }, "Loading");
    return h("div", { className: "panel table-wrap" }, h("h1", null, "People"),
      h("p", { className: "lede" }, "Everyone with a leave record. Open a person to see their balances, leave history and requests."),
      h("table", null,
        h("thead", null, h("tr", null, ["Employee", "Joined", "Manager", "Annual leave left", "Sick leave left", "Waiting"].map(function (c) { return h("th", { key: c, scope: "col" }, c); }))),
        h("tbody", null, rows.map(function (r) {
          return h("tr", { key: r.employee_id },
            h("td", null, h("button", { className: "link", onClick: function () { setSelected(r.employee_id); } }, r.employee_id)),
            h("td", null, r.hire_date ? dayLabel(r.hire_date) : ""),
            h("td", null, r.manager),
            h("td", null, r.annual_balance + " of " + r.annual_entitlement),
            h("td", null, r.sick_balance + " of " + r.sick_entitlement),
            h("td", null, r.waiting ? plural(r.waiting, "request") : "None"));
        }))));
  }

  function ScreenResume(props) {
    var _j = useState([]), jobs = _j[0], setJobs = _j[1];
    var _r = useState([]), resumes = _r[0], setResumes = _r[1];
    var _i = useState("1"), jobId = _i[0], setJobId = _i[1];
    var _n = useState(""), resumeId = _n[0], setResumeId = _n[1];
    var _b = useState(false), busy = _b[0], setBusy = _b[1];
    var _x = useState(null), result = _x[0], setResult = _x[1];
    var _e = useState(""), error = _e[0], setError = _e[1];
    useEffect(function () {
      api("/jobs").then(setJobs).catch(function () {});
      api("/resumes").then(setResumes).catch(function () {});
    }, []);
    var job = jobs.find(function (j) { return String(j.job_id) === jobId; });
    var valid = /^\d{5,9}$/.test(resumeId.trim());
    var onlyDemo = resumes.length > 0 && resumes.every(function (r) { return r.source === "demo"; });
    function run(ev) {
      ev.preventDefault();
      setBusy(true); setError(""); setResult(null);
      api("/requests", { method: "POST", body: { message: "screen resume " + resumeId.trim() + " for job " + jobId } })
        .then(function (r) { setResult(r); props.onSent(); })
        .catch(function (e) { setError(e.message); }).then(function () { setBusy(false); });
    }
    return h("form", { className: "panel", onSubmit: run },
      h("h1", null, "Screen a resume"),
      h("p", { className: "lede" }, "Pick a job and a resume. The agent reads the resume, scores it against the job and recommends shortlist, review or reject. You make the decision."),
      h("div", { className: "field" },
        h("label", { htmlFor: "job" }, "Job"),
        h("select", { id: "job", value: jobId, onChange: function (e) { setJobId(e.target.value); } },
          jobs.map(function (j) { return h("option", { key: j.job_id, value: String(j.job_id) }, j.job_id + ". " + j.title); })),
        job && h("div", { className: "hint" }, "Must have: " + job.must_have.join(", ") + ". Nice to have: " + job.nice_to_have.join(", ") + ". At least " + plural(job.min_years, "year") + " of experience.")),
      h("div", { className: "field" },
        h("label", { htmlFor: "resume-pick" }, "Resume"),
        h("select", { id: "resume-pick", value: resumes.some(function (r) { return r.resume_id === resumeId.trim(); }) ? resumeId.trim() : "",
          onChange: function (e) { setResumeId(e.target.value); } },
          h("option", { value: "" }, resumes.length ? "Choose a resume" : "No resumes found"),
          resumes.map(function (r) {
            return h("option", { key: r.resume_id, value: r.resume_id },
              r.resume_id + ", " + cap(r.category.toLowerCase().replace(/-/g, " ")) + (r.source === "demo" ? " (demo)" : ""));
          })),
        h("label", { htmlFor: "resume", className: "sub-label" }, "Or type a resume number"),
        h("input", { id: "resume", type: "text", inputMode: "numeric", autoComplete: "off", value: resumeId,
          onChange: function (e) { setResumeId(e.target.value); } }),
        h("div", { className: "hint" }, resumeId && !valid ? "A resume number has 5 to 9 digits, for example 10001."
          : onlyDemo ? "The list shows fictional demo candidates. Real resumes need the public dataset described in the README."
          : "Pick one from the list, or type a number.")),
      h(Notice, { kind: "error", text: error }),
      result && result.status === "awaiting_human" && h("div", { className: "notice paused", role: "status" },
        "Sent to the review queue. ", h("button", { type: "button", className: "link", onClick: props.onOpenQueue }, "Open the review queue")),
      result && result.status !== "awaiting_human" && h(Answer, { className: "notice", text: result.answer || "Nothing was decided.", sources: result.sources }),
      h("button", { className: "btn primary", disabled: busy || !valid || !jobId }, busy ? "Screening" : "Screen resume"));
  }

  /* ---------- the audit log ---------- */
  var EVENT_LABEL = { leave_request: "Leave decision", resume_screening: "Screening decision",
                      policy_answer: "Policy answer", escalation: "Passed to HR", record_view: "Record viewed",
                      hiring_decision: "Hiring decision", candidate_stage: "Candidate update", interview_scheduled: "Interview scheduled",
                      interview_feedback: "Interview feedback", interview_cancelled: "Interview cancelled" };
  var ABOUT_CANDIDATE = ["hiring_decision", "candidate_stage", "interview_scheduled", "interview_feedback", "interview_cancelled"];

  function auditDetail(e) {
    var s;
    if (e.final_decision !== undefined) {
      var rec = actionLabel(e.agent_recommendation).toLowerCase(), fin = actionLabel(e.final_decision).toLowerCase();
      s = (e.days ? plural(e.days, "day") + " of " + e.leave_kind + " leave. " : "") +
          "Agent suggested " + rec + (e.overridden ? "; reviewer chose " + fin + "." : "; reviewer agreed.");
      if (e.note) s += " Note: " + e.note;
      return s;
    }
    if (e.kind === "policy_answer") {
      s = "Asked: \u201c" + (e.question || "") + "\u201d.";
      if (e.sources && e.sources.length) s += " Sources: " + e.sources.map(sourceLabel).join("; ") + ".";
      return s;
    }
    if (e.kind === "record_view") return "Opened by " + e.viewer + ".";
    if (e.kind === "candidate_stage") return "Resume " + e.resume_id + " for job " + e.job_id + " is now: " + (STAGE[e.stage] || { label: e.stage }).label.toLowerCase() + ".";
    if (e.kind === "interview_scheduled") return "A " + e.interview_kind + " interview with " + e.interviewer + ", " + when(e.scheduled_for) + ".";
    if (e.kind === "interview_feedback") return e.interviewer + " rated the interview " + e.rating + " out of 5.";
    if (e.kind === "interview_cancelled") return "The " + e.interview_kind + " interview was cancelled.";
    if (e.kind === "escalation") return "Asked: \u201c" + (e.message || "") + "\u201d. Nothing in the policy documents answers this, so it was passed to HR.";
    return "";
  }

  function AuditLog(props) {
    var _l = useState(null), rows = _l[0], setRows = _l[1];
    var _e = useState(""), error = _e[0], setError = _e[1];
    useEffect(function () { api("/audit?limit=100").then(setRows).catch(function (e) { setError(e.message); }); }, [props.refresh]);
    if (error) return h(Notice, { kind: "error", text: error });
    if (rows === null) return h("p", { className: "empty" }, "Loading");
    if (rows.length === 0) return h("div", { className: "panel" }, h("p", { className: "empty" }, "Nothing has been recorded yet."));
    return h("div", { className: "panel table-wrap" }, h("h2", null, "Audit log"),
      h("table", { className: "audit" },
        h("thead", null, h("tr", null, ["When", "Event", "About", "Details", "By"].map(function (c) { return h("th", { key: c, scope: "col" }, c); }))),
        h("tbody", null, rows.map(function (e, i) {
          var decision = e.final_decision !== undefined;
          return h("tr", { key: i },
            h("td", { className: "nowrap" }, when(e.time)),
            h("td", null, EVENT_LABEL[e.kind] || cap(String(e.kind).replace(/_/g, " "))),
            h("td", null, ABOUT_CANDIDATE.indexOf(e.kind) >= 0 ? "Candidate " + e.subject_id : e.subject_id),
            h("td", null, auditDetail(e)),
            h("td", null, decision ? (e.reviewer || e.decided_by) : e.kind === "record_view" ? e.viewer
              : e.kind === "interview_feedback" ? e.interviewer : e.by || "Automatic"));
        }))));
  }

  /* ---------- the two role views ---------- */
  function EmployeeView(props) {
    var _i = useState(null), items = _i[0], setItems = _i[1];
    var load = useCallback(function () { api("/requests").then(setItems).catch(function () {}); }, []);
    useEffect(load, [load]);
    return h("main", null, h("h1", null, "Your requests"),
      h("p", { className: "lede" }, "Ask about a policy or your own leave, or request time off. Leave requests are final only after a reviewer decides."),
      h(Composer, { user: props.user, onSent: load }),
      h("div", { style: { height: 20 } }),
      h(RequestList, { title: "History", items: items }));
  }

  function ReviewerView(props) {
    var _t = useState("queue"), tab = _t[0], setTab = _t[1];
    var _p = useState(null), pending = _p[0], setPending = _p[1];
    var _a = useState(null), all = _a[0], setAll = _a[1];
    var _k = useState(0), tick = _k[0], setTick = _k[1];
    var load = useCallback(function () {
      api("/pending").then(setPending).catch(function () {});
      api("/requests").then(setAll).catch(function () {});
      setTick(function (n) { return n + 1; });
    }, []);
    useEffect(function () { load(); var t = setInterval(load, 15000); return function () { clearInterval(t); }; }, [load]);
    var waiting = pending ? pending.length : 0;
    function tabBtn(id, label, extra) {
      return h("button", { className: "tab", role: "tab", "aria-selected": tab === id, onClick: function () { setTab(id); } }, label, extra);
    }
    return h(React.Fragment, null,
      h("div", { className: "tabs", role: "tablist" },
        tabBtn("queue", "Review queue", waiting ? h("span", { className: "count" }, waiting, h("span", { className: "visually-hidden" }, " waiting")) : null),
        tabBtn("people", "People"), tabBtn("candidates", "Candidates"), tabBtn("screen", "Screen a resume"), tabBtn("send", "My leave and questions"),
        tabBtn("all", "All requests"), tabBtn("audit", "Audit log")),
      h("main", null,
        tab === "queue" && h(ReviewQueue, { pending: pending, user: props.user, onDecided: load, onRefresh: load }),
        tab === "people" && h(People, { refresh: tick }),
        tab === "candidates" && h(Candidates, { user: props.user, refresh: tick, onChanged: load,
          onOpenQueue: function () { setTab("queue"); }, onOpenScreen: function () { setTab("screen"); } }),
        tab === "screen" && h(ScreenResume, { onSent: load, onOpenQueue: function () { setTab("queue"); } }),
        tab === "send" && h(Composer, { user: props.user, onSent: load, title: "Your own leave and questions" }),
        tab === "all" && h(RequestList, { title: "All requests", items: all, showOwner: true }),
        tab === "audit" && h(AuditLog, { refresh: tick })));
  }

  /* ---------- app ---------- */
  function App() {
    var _u = useState(null), user = _u[0], setUser = _u[1];
    var _r = useState(!!getToken()), checking = _r[0], setChecking = _r[1];
    useEffect(function () {
      if (!getToken()) return;
      api("/me").then(setUser).catch(function () { setToken(""); }).then(function () { setChecking(false); });
    }, []);
    function signOut() { setToken(""); setUser(null); }
    if (checking) return h("main", null, h("p", { className: "empty" }, "Loading"));
    if (!user) return h(Login, { onSignedIn: setUser });
    return h(React.Fragment, null,
      h("header", { className: "bar" },
        h("span", { className: "brand" }, "SynapseHR"),
        h("span", { className: "who" }, user.user_id + " (" + user.role + ")"),
        h("button", { className: "btn small", onClick: signOut }, "Sign out")),
      user.role === "reviewer" ? h(ReviewerView, { user: user }) : h(EmployeeView, { user: user }));
  }

  ReactDOM.createRoot(document.getElementById("root")).render(h(App));
})();
