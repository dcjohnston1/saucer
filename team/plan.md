# Project Saucer — Master Plan

*Maintained by the PM. Updated after each sprint as needed.*
*Items 3+ sprints away use placeholders. All items are still in the plan.*
*The engineer drafted the initial 6-sprint sequence below. The PM should present this to all agents at the first /roundup for discussion and buy-in before committing to it.*

---

## Sprint Process Standing Rules

These rules apply to every sprint, starting Sprint 4. They are CEO mandates and are not subject to team vote.

**Standing Rule 1 — GitHub commit before sprint launch:**
Before Coder writes a single line of new code, the team must confirm the latest code is committed and pushed to GitHub. This is a rollback safety requirement. If a sprint introduces a breaking change, the team needs a clean revert point. This step happens as the first act of every sprint ceremony, before the meeting circle runs.

**Standing Rule 2 — Minimize CEO involvement:**
Agents and Coder must handle everything they can without the CEO. This includes bash commands, gcloud commands, deploys, IAM bindings, Firestore setup, and any other terminal operations. Only escalate to the CEO when something genuinely requires their credentials, billing access, or an account-level decision that cannot be delegated. The CEO is not a technical blocker.

---

## Sprint 1 — Audit and Observability Foundations — COMPLETE ✓
Full prompt and tool argument capture on every Hana decision. One-step undo on hana_notes. Notes consulted tracking. Revert endpoint.

## Sprint 2 — Email Cache Concurrency — COMPLETE ✓
Migrated email storage to Firestore + per-email GCS blobs. Single email_store.py module. 506 emails migrated.

## Sprint 3 — Action-Class Infrastructure — COMPLETE ✓
ActionClass abstraction (actions.py) with reversible, reviewable, confirmation_required, confidence fields. Firestore pending_actions collection (pending_actions.py) with enqueue/resolve/list. Gmail Drafts feature (gmail_drafts.py) wired into both agent entry points. GET/POST /pending-actions routes as extensible frontend stub. RFC sort fixed. notes_consulted investigated — correct behavior confirmed, error logging improved.
CEO action: deploy backend and confirm smoke test draft appears in Gmail Drafts.

## Sprint 4 — Reliable Background Work — COMPLETE ✓
Cloud Tasks integration complete. `hana-actions` queue RUNNING. `task_queue.py` with confidence gate (>=0.7) and per-user daily cap (configurable via Firestore `config/limits`). POST `/tasks/handle-action` and `/tasks/process-email` endpoints (OIDC-secured, idempotent). `processing_status` lifecycle on pending_actions. Threading removed. `db_schema.py` documents all Firestore collection paths. `pending_actions` migrated to `users/{user_id}/pending_actions/` namespace. Revision 00148 live and verified.

## Sprint 5 — Hygiene Cleanup — COMPLETE ✓
Address accumulated small debt before splitting main.py. Binary outcomes only — done or explicitly deferred.
Pre-sprint: commit and push Sprints 3+4 to GitHub (Standing Rule 1).
1. notes_consulted closure capture fix — inspect `_make_agent_*` factories in agent.py, bind value at factory time. Verify via live agent decision log.
2. Delete deprecated /proposals routes (3 DEPRECATED-tagged endpoints in main.py). Inline proposals attachment from email list routes conditional on frontend defensive-handling check.
3. Delete ONBOARDING_SYSTEM_PROMPT from prompts.py (no callers).
4. Wire or delete _topic_blocked in main.py (no call sites found).
5. Consolidate duplicate intent-evaluation verdict rules into `_INTENT_VERDICT_RULES` constant in email_scanner.py.
6. Audit task-existence check duplication across mediator.py, agent.py, main.py, gdocs.py. Consolidate if found; close as stale if not.
Deferred: emails flat namespace migration → Sprint 9 (data migration, dual-write + backfill required).
Estimated: 2,500–3,000 tokens.

## Sprint 6 — Blueprint Foundation (agent + tasks) — NOT STARTED
main.py is 2,254 lines / 80 routes (60% larger than planned). Partial split: build lib/ infrastructure, then extract the two Phase-2-critical domains. Remaining domains deferred to Sprint 7.

Step 1 — Create backend/lib/ with three shared modules:
- lib/auth.py: OIDC verification helper, Pub/Sub secret verification
- lib/firestore_client.py: Firestore db singleton
- lib/config.py: Shared constants (_DAN user ID, queue name, service URL, region)

Step 2 — Extract routes/agent.py Blueprint:
- POST /agent/run, POST /agent/email-trigger, POST /agent/renew-gmail-watch
- GET /briefing/latest, POST /briefing/<id>/feedback, POST /briefing/<id>/seen

Step 3 — Extract routes/tasks.py Blueprint:
- POST /tasks/handle-action, POST /tasks/process-email
- GET /pending-actions, POST /pending-actions/<id>/resolve

Step 4 — Thin main.py: app factory, Blueprint registrations, GET /health, remaining unsplit routes.

Acceptance: no API contract changes, no import cycles, smoke test passes, revision recorded.
Estimated: 3,500–4,500 tokens (Engineer: medium).

Note: first real-user exposure (2-3 users on Gmail Drafts) is DECOUPLED from this sprint. It can and should begin now, independent of the Blueprint refactor.

## Sprint 7 — Blueprint Completion Wave 1 (emails + filters) — NOT STARTED
Extract two highest-priority domains from main.py. Token budget trimmed scope from 6 domains to 2.

Step 1 — routes/emails.py Blueprint:
- All email-reading and email-action routes: /emails (GET), /emails/cached, /emails/resync, /emails/search,
  /emails/<id>/dismiss, /emails/<id>/review, /reviewed-emails, /emails/hana-dismissed,
  /emails/dismissed-review, /emails/<id>/dismiss-feedback, /emails/<id>/topic-phrase,
  /emails/<id>/highlights, /emails/<id>/restore, /emails/<id>/attachment-file-id,
  /emails/<id> (GET single), /emails/backfill-sender, /email/<id>/excerpt,
  /email-intent (GET + POST), /doc (GET), /doc/task (DELETE), /doc/dedup (POST),
  /chat (POST), /avatar (GET + POST)
- Shared helpers used only by these routes should move with them or remain in lib/email_helpers.py.

Step 2 — routes/filters.py Blueprint:
- /email-filters (GET, POST, DELETE), /keyword-filters (GET, POST, DELETE),
  /exclude-keyword-filters (GET, POST, DELETE), /blocked-senders (GET, POST, DELETE),
  /blocked-topics (GET, POST, DELETE), /generate-topic-label (POST)

Acceptance: no API contract changes, no import cycles, smoke test passes, revision recorded.

Deferred to Sprint 8:
- routes/memory.py (hana/notes, hana/question — 6 routes)
- routes/files.py (files CRUD — 4 routes)
- routes/admin.py (user-settings, actions history, decisions, onboarding, conversation-history, debug — ~12 routes)
- routes/calendar.py: BLOCKED — do not schedule until CEO confirms calendar integration unblocked

## Sprint 8 — Blueprint Completion Wave 2 (memory + files + admin) — COMPLETE ✓
Extracted routes/memory.py (6 routes), routes/files.py (4 routes), routes/admin.py (12 routes).
main.py is now a true thin shell: 130 lines, 5 blocked calendar routes + /health only.
routes/calendar.py: BLOCKED. Trigger to unblock: CEO must confirm Google Calendar OAuth credentials
are configured and gcalendar.py module is functional. Until then, calendar routes stay in main.py.
Revision 00156-qzf live. Git commit 332612f pushed to GitHub.

## Sprint 9 — Product Fixes (CEO Mandate) — COMPLETE ✓
CEO-mandated product-facing fixes. All five items are independent of Voice AI and must ship before
the first external user touches the product. Briefing attribution bug is a trust/correctness issue
that cannot survive into the external-user window.

Scope (5 items):
1. Briefing attribution bug — prompt guard: add rule to AGENT_SYSTEM_PROMPT so Hana only claims
   an assignment in a briefing if it actually called add_todo or reassign_task that session.
   Structural fix: change write_briefing tool schema to require a briefing_assertions array with
   source tags ('email' vs 'hana_decision' linked by decision_id). Chat handler uses tags to
   distinguish "I read that in the email" from "I decided that."
2. Restore email summary — add brief gray preview text field to email list API response so frontend
   can display it on each email card. Was removed in Sprint 5 as part of proposals cleanup.
3. Restore task determination — AI extraction of potential to-dos from email content. Previously
   coupled to the deprecated proposals flow; rebuild as a standalone extraction path.
4. Restore task swiping — swipe left/right on extracted tasks to accept or reject them. Depends on
   item 3; ships in the same sprint. Cannot ship independently.
5. Restore email highlights — /email/<id>/excerpt route and source_spans feature still exist in
   routes/emails.py (confirmed Sprint 5). Verify backend is intact; wire or fix frontend rendering.
6. Briefing-to-chat context handoff — when user taps "Let's chat" on a morning briefing card, the
   chat opens with Hana's briefing message pre-loaded at the top of the conversation. Gives Hana
   full context for follow-up questions; partially mitigates attribution gap until structural fix ships.

Complexity estimates: items 1, 2, 5, 6 are small. Items 3+4 are medium (coupled unit). Total sprint
is medium overall. All items are backend + frontend across the existing Blueprint structure.

## Sprint 10 — In-App Voice AI + First External User — COMPLETE ✓
CEO decisions (2026-05-19):
- Voice direction: IN-APP voice only. No Twilio, no phone calls. User holds a button in the app,
  speaks, Hana responds with audio. Like Siri. Twilio inbound phone integration DROPPED.
- First external user: Emily (CEO's partner) confirmed as external user #1. Named gate: Emily must
  run Hana at least once before this sprint closes.

Scope (3 items):
1. To-do source email highlight — frontend app.js: tap to-do → navigate to source email →
   call /email/<id>/excerpt → render highlight. Small. Unblocked by Sprint 9 source_spans fix.
2. In-app voice: hold-to-record button in frontend → multipart audio upload → Google Cloud STT
   (backend) → existing agent run → Google Cloud TTS → MP3 audio response back to frontend.
   Audio encoding: WebM/Opus from frontend, LINEAR16 to STT API, MP3 back to frontend.
   UX requirements (hard): hold-to-record (not tap-to-toggle), pulsing recording indicator,
   auto-play response with stop/replay, fallback prompt if STT confidence is low.
   Frictionless UX is a requirement, not a nice-to-have.
   Files: routes/voice.py (new Blueprint), voice_handler.py (new domain module),
   frontend record button + audio playback, requirements.txt (google-cloud-speech, google-cloud-texttospeech).
3. Emily onboarding: team prepares onboarding materials (what Hana does, setup steps, how to run
   briefing, what feedback we want). CEO delivers them to Emily. Named gate: Emily runs Hana once.

Note: Analyst is researching ChatGPT/Claude voice UX patterns in parallel. Findings do not block
Sprint 10 engineering. If findings suggest UX changes, targeted pass in Sprint 11.

Note: Marketing to begin planning for organic external user #2. Target: candidate identified
(not necessarily onboarded) before Sprint 11 closes.

## Sprint 11 — Voice UX Polish + Organic User #2 — COMPLETE ✓
Voice UX refinements informed by analyst research and Emily feedback.
Structured user interviews to lock confidence threshold before mobile begins.
Organic external user #2: identify candidate by end of sprint.
Google Cloud TTS voice selection and tuning.

## Sprint 12 — CEO Deferred Items (all 8) — COMPLETE ✓
All 8 CEO-deferred product surface items addressed. Filter bug fixed. Swipe cards auto-run on load.
Yellow highlights on email cards. Auto-calendar (add_calendar_event in agent.py, background trigger,
silent + dismissable). Future Events view (14-180 days out). CEO chose Option A for calendar trigger.
Calendar → source email already wired. To-do → source email highlight unblocked by auto-scan.
Git commit 4c807d7. Backend saucer-backend-00167-z5k. Frontend saucer-frontend-00124-kqq.
CEO action items open: (1) Privacy Policy + ToS before more external users. (2) Calendar OAuth
service account must switch to per-user credentials before public onboarding.

## Sprint 13 — Bug Fixes + Auth Foundation — COMPLETE ✓
P0 bug fixes from Sprint 12 regressions + Firebase Auth integration + rate limiting.
Emails namespace migration deferred to Sprint 14 (named gate moved, not dropped).
Finance cost-per-active-user estimate delivered: $0.80–$3.50/user/month; voice adds $0.30–$0.60.

Fix A: sender allowlist applied to /emails GET route (was only on /emails/cached).
Fix B: scan-todos pipeline gap diagnosed and fixed; scan_count added to response.
Fix C: Future Events empty/error state fixed; stale copy updated; backend error surfaced.
Firebase Auth: JWT verification middleware added for mobile client requests.
Rate limiting: per-user daily caps on agent endpoints, configurable via Firestore config/limits.
Scale audit: remaining flat Firestore collections reviewed; gap list produced.

## Sprint 14 — Three P0 Bug Fixes (CEO Mandate) — COMPLETE ✓

CEO-mandated bug sprint. All three bugs surfaced in a live demo and block the Emily gate directly.
Emails namespace migration, mobile screens, React Native vs. Flutter, and marketing strategy all
pushed to Sprint 15+.

Bug 1 (HIGH) — "Checking for action items..." spinner never resolves.
  Sub-fix 1a: frontend guard in buildProposalsSection (frontend/app.js ~line 1117).
    When proposals is null after email load, replace spinner text "Checking for action items..."
    with "No to-dos found". One-line text change.
  Sub-fix 1b: backend write path in process_single_email (backend/agent.py ~line 737).
    After add_todo_logged succeeds (result status == 'ok'), call
    email_store.update_email_fields(source_email_id, {'proposals': [existing + new todo]})
    to write the todo back to the Firestore email doc. This requires source_email_id to be
    passed from the tool call through to the update. The proposals field must be a list of
    dicts matching the format returned by scan_emails_for_todos so buildProposalRow can render them.
  Acceptance criterion: 1a + 1b must ship together. End-to-end test: trigger agent on a qualifying
    email, confirm Firestore email doc has proposals field, confirm frontend renders swipeable card.

Bug 2 (MEDIUM, independent) — Hana draft appears as a separate email card.
  Part 1 (small): Filter DRAFT-labeled messages in routes/agent.py Pub/Sub handler, before
    upsert_emails_batch is called (~line 287). Check labelIds for 'DRAFT'; exclude those messages.
  Part 2 (medium): Inline UX.
    Backend: add thread_id to the payload stored by enqueue_pending_action in _make_agent_draft_reply
      (backend/agent.py ~line 556). In /emails/cached (backend/routes/emails.py), pre-load all
      gmail_draft pending_actions for the user in a single Firestore query (NOT per-email reads).
      Join in memory by thread_id or email_id. Attach matching draft action as draft_pending_action
      field on the email response object.
    Frontend (app.js): in buildEmailCard, check email.draft_pending_action. If present, add a
      collapsible section with header "Hana drafted a reply ▸". When expanded: show draft subject
      line, body preview (first 150 chars), "Open in Gmail" link, and "Dismiss" button. Section
      header color must be muted (not accent) to distinguish from sent mail.
  Acceptance criterion: new email from a permitted sender triggers agent, creates draft in Gmail,
    draft does NOT appear as a separate card in the email list, and the source email card shows
    the collapsible Hana draft section.

Bug 3 (MEDIUM, resolves with Bug 1) — Action item displays as quoted string, not interactive card.
  No additional code work. buildProposalRow (app.js:1150) already renders proper swipeable cards.
  Bug 3 resolves automatically when Bug 1b populates the proposals field on the email doc.
  Acceptance criterion: once Bug 1 is confirmed end-to-end, verify proposals render as swipeable
    cards (not raw strings) in the frontend.

Pre-sprint: confirm latest commit is pushed to GitHub (Standing Rule 1).

## Sprint 15 — Production Incident Response (Self-Email + Evaluation Error) — COMPLETE ✓
Two same-night incidents triaged and fixed after Sprint 14 close.
Incident A — self-email "to-do's" dropped at filter gate. Root cause: permitted-sender shortcut
did not normalize whitespace in `_extract_sender_addr`; Gemini misclassified self-email as off-topic.
Fixes: added SELF-EMAIL RULE to intent prompt, `.strip().lower()` on sender extraction, structured
DROP log lines, permitted-sender short-circuit added to batch eval. Email recovered from
saucer-dismissed.json.
Incident B — 105 emails showing "Evaluation Error" badge. Root cause: deprecated
`google.generativeai` SDK fell back to Cloud Run ADC instead of GOOGLE_API_KEY env var; all
batch Gemini calls returned 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT.
Fixes: migrated to `google.genai`, added keyword fast-track + permitted-sender fast-track to
batch eval (so trusted signals never depend on Gemini). Recovered 729 poisoned email verdicts.
Sprint 15 originally planned as Subscription/Paywall — deferred. Production incidents took the slot.
Git commits 681fe88 (self-email) and a11b09a (eval-error). Revisions 00178-758 and 00181-l9w.

## Sprint 16 — Trust Pills + Honest Dismissed Labels — COMPLETE ✓
Restore inbox trust after CEO screenshot review surfaced a live trust leak.
Task 1: Honest Dismissed labels. Replace "No to-dos found" with "Not scanned" on filter-blocked
emails in the Dismissed view. Distinguish from emails Hana actually scanned and found nothing.
Pure frontend in `buildProposalsSection`.
Task 2: "From someone you trust" / "You allowlisted this sender" pill, left of sender address on
main inbox cards. Triggered by existing `verdict_reason='Sender is on the permitted list'`.
Pure frontend.
Task 3: "Matched: {phrase}" pill under subject line on main inbox cards. Triggered by keyword or
freetext topic match. Backend writes new `matched_topic` field (additive — no migration). Keyword
case trivial; freetext case extends Gemini JSON schema. Phrase truncated at ~20 chars.
Task 4: No fallback pill. When neither rule applies, render nothing. An inbox email with zero
pills is a filter hole — to fix upstream, NOT paper over with UI.
Visual constraint: low-weight outline pills on separate rows. Not alarming.

Deferred to Sprint 17+:
- Subscription/Paywall (Stripe or RevenueCat)
- App Store prep + TestFlight beta
- Privacy Policy + Terms of Service publication
- Calendar OAuth: shared service account → per-user credentials
- Emails flat namespace migration (`users/{user_id}/emails/`)
- React Native vs. Flutter mobile decision
- Marketing strategy definition
- Emily named-gate close

## Sprint 17 — Inbox Signal Integrity — STAGED
Fix two trust regressions from Sprint 16 CEO smoke-test.

Task 1: Fix contradictory "No to-dos found" on cards with proposal items. `buildProposalsSection` in `app.js` — suppress fallback text when at least one proposal card was rendered. Pure frontend. Small.

Task 2: Route pill-less emails (verdict=permitted, no trust pill, no topic pill) to a collapsed "Other Emails" secondary tray at the bottom of the inbox. Pure frontend, in-memory classification using existing `verdict_reason` and `matched_topic` fields. No new Gemini calls, no new Firestore reads.

Acceptance: 7 criteria in sprint_17.md. Both tasks are frontend-only. Token estimate: 3,000–4,500.

Deferred to Sprint 18+: Subscription/Paywall, App Store prep, Privacy Policy/ToS, calendar OAuth, namespace migration, Emily gate, mobile framework decision.

## Sprint 18 — Subscription + Paywall — PLACEHOLDER
Stripe or RevenueCat subscription integration, paywall, pricing tier UX.

## Sprint 19 — App Store Prep + Submission — PLACEHOLDER
Privacy policy, OAuth scope justification, TestFlight beta (5-10 users minimum), submission.
Allow 2-4 week review buffer given Gmail/Calendar scope sensitivity.

---

## Sprint 14 Named Gates (updated per CEO mandate 2026-05-20)
- **All three P0 bugs confirmed fixed and deployed** — spinner resolves, draft inline, swipe cards render.
- **Emails namespace migration** — deferred to Sprint 15. Named gate preserved, not dropped.
- **First external user confirmed** — Emily must have run Hana at least once. Gate moves to Sprint 15.
- **Cost-per-active-user estimate** — DONE (Sprint 13): $0.80–$3.50/user/month.
- React Native vs. Flutter decision — deferred to Sprint 15.
- Marketing strategy — deferred to Sprint 15.
