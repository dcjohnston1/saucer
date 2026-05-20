# PM History
*Running log of sprint decisions, plan changes, and escalations.*

## 2026-05-16 — PM/Engineer Sprint Sequencing Review

**Sprint 3 committed as follows:**
- ActionClass abstraction + Firestore pending_actions collection + minimal frontend placeholder (as originally planned)
- ADDED: notes_consulted closure capture investigation and fix (if closure issue; document-and-defer if structural)
- ADDED: RFC 2822 string sort bug fix on dismissed-review list
- Scope constraint: if notes_consulted investigation reveals a concurrency or structural root cause, document it and defer the fix — no open-ended mid-sprint refactor

**Open question escalated to CEO — must answer before Sprint 4 is designed:**
Is Hana primarily a PROACTIVE agent (background automation, acts without being asked) or a REACTIVE assistant (command-driven, user asks Hana to act)?
- If PROACTIVE: Cloud Tasks stays at Sprint 4 (original plan). Delaying it further risks a rewrite.
- If REACTIVE: Sprint 4 becomes on-demand email drafting (with ActionClass wired in); Cloud Tasks deferred to Sprint 5 or 6.

**Plan constraints confirmed:**
- Sprint 5 (hygiene) and Sprint 6 (main.py split) are a coupled unit — neither can float independently of the other.
- Hygiene must precede the file split. Do not separate them.

---

## 2026-05-16 — PM/Engineer ROI and Visibility Interrogation (Session 2)

**Sprint 3 — revised and expanded:**
- Original scope: ActionClass, pending_actions collection, frontend placeholder, notes_consulted fix, RFC sort fix.
- ADDED: Gmail Drafts as the first ActionClass consumer. Hana writes draft replies to Gmail Drafts folder; user reviews and sends manually. No automated sending.
- This gives the CEO a visible, demonstrable output by end of Sprint 3.
- PREREQUISITE (blocks Drafts wiring): CEO must re-authorize OAuth with gmail.compose scope before Sprint 3 begins. Five-minute human action. If not done before sprint start, Drafts feature builds last when auth is confirmed.
- Engineer conceded that Drafts-only path is technically safe without ActionClass (user retains Send control), but proposed keeping ActionClass as the consumer layer to avoid future retrofit. PM accepted.

**Sprint 4 — formally escalated to CEO (unresolved):**
- Core question: Is Hana fundamentally PROACTIVE (background automation) or REACTIVE (command-driven)?
- If PROACTIVE: Cloud Tasks at Sprint 4 is mandatory. Engineer warns that adding background-driven features without it risks a complete rewrite.
- If REACTIVE: Sprint 4 becomes on-demand outbound capability; Cloud Tasks deferred.
- PM will not design Sprint 4 until the CEO answers this question. Do not begin Sprint 4 planning without resolution.

**Sprint 5 — scope acknowledged as variable:**
- Debt list will grow as Sprints 3 and 4 add complexity. Engineer estimates 2-3 new items by the time Sprint 5 arrives.
- Sprint 5 will be run as a token-budget sprint: prioritize by severity, defer what doesn't fit.

**notes_consulted bug — postmortem noted:**
- Engineer acknowledged it was mis-classified as cosmetic in Sprint 1. Root cause: bug only surfaces on real agent decisions, not simple tool-call tests. No test case existed to catch it. Reclassified as audit-trail gap; moved to Sprint 3.

**Key architectural point on record:**
- Engineer warned that building on-demand drafting before Cloud Tasks creates two diverging code paths (on-demand + background), which will need reconciliation. If Hana is proactive, Cloud Tasks must come first.

---

## 2026-05-17 — Full Roadmap to App Store (CEO Request)

CEO requested a comprehensive roadmap from Sprint 3 through app store submission. Proactive Hana decision is now resolved (CEO confirmed proactive). Roadmap presented as 12-sprint plan across 3 phases.

**Phase 1 — Backend Core (Sprints 1-6):** Sprints 1-2 complete. Sprint 3 (ActionClass + Gmail Drafts, blocked on OAuth re-auth). Sprint 4 (Cloud Tasks, non-negotiable given proactive bet). Sprint 5 (hygiene cleanup). Sprint 6 (main.py split into Flask Blueprints). Phase 1 ends with a production-grade backend ready to support a mobile client.

**Phase 2 — Voice AI (Sprints 7-8):** Twilio + GCS STT/TTS. Hana can receive phone calls and respond with synthesized speech. High-value differentiator for target user (working parents 28-45). Open question logged: does Hana initiate calls? CEO must answer before Sprint 7 ends.

**Phase 3 — Mobile Frontend (Sprints 9-12):** Sprint 9 (mobile API hardening, auth layer decision required). Sprint 10 (core mobile screens, stack decision required — React Native vs. Flutter). Sprint 11 (Stripe/RevenueCat subscription + paywall). Sprint 12 (app store prep, TestFlight beta, submission).

**Revenue math flagged:** At $12/month with Apple's 30% cut, net is $8.40/user/month year 1. $220K run-rate target requires ~2,180 active subscribers. Non-trivial for bootstrapped household app. Marketing strategy should be designed no later than Sprint 10.

**Key open questions logged for CEO (in urgency order):** (1) OAuth re-auth for gmail.compose — blocks Sprint 3 today. (2) Does Hana initiate calls? — needed before Sprint 8 scope. (3) Mobile auth layer — Firebase Auth recommended. (4) React Native vs. Flutter. (5) Solo developer or hire for mobile phase? (6) First 5-10 beta users — needed before Sprint 12 submission.

**App store gates identified:** Working payment flow, published privacy policy, OAuth scope justification, no cold-start crashes, at least 5-10 TestFlight beta users. Allow 2-4 weeks review buffer after submission given Gmail/Calendar scope sensitivity.

---

## 2026-05-17 — User Testing Strategy Decision (CEO Question)

**Decision: User testing is a rolling track, not a standalone sprint.**

- First real user touch: Sprint 6. Give 2-3 target users (working parents 28-45) access to the Gmail Drafts flow. Single question: did Hana draft something useful, or did it feel intrusive? This is the first read on confidence threshold, which is the highest-risk design question in the product.
- Sprint 8 checkpoint: Structured interviews with 5 users on the core loop (does Hana's judgment earn trust over a real week of household email?). Findings must lock the confidence threshold before Sprint 9 mobile work begins.
- Sprint 12 TestFlight beta is an app store compliance gate, not user testing. If Sprint 12 is the first stranger touchpoint, month-one churn will be severe.
- Action required from CEO: Recruit 5 target users now. Do not wait for Sprint 12.

---

## 2026-05-18 — Sprint 3 Kickoff Decision

**Sprint 3 scope finalized and handed to Coder. Both blockers resolved.**

**Scope (5 items):**
1. ActionClass abstraction — dataclass with fields: reversible, reviewable, confirmation_required, confidence (float, optional — added per Strategy recommendation to avoid costly retrofit later).
2. Firestore pending_actions collection — schema + enqueue/resolve helpers. No worker this sprint.
3. Gmail Drafts — Hana creates Gmail drafts for qualifying emails. ActionClass tagged reviewable=True, confirmation_required=False. Requires gmail.compose scope (now authorized).
4. notes_consulted fix — investigate closure capture in _make_agent_* factories. Fix if closure issue; document-and-defer if structural.
5. RFC sort fix — parse RFC 2822 dates before sorting on dismissed-review list.

**Amendments from meeting circle (Round 1 only — clean consensus):**
- ActionClass gets optional confidence: float = None field.
- Sprint completion criterion includes draft quality smoke test: trigger drafts against 2-3 real emails, review output before closing sprint.
- Frontend pending_actions stub must be a real extensible JSON route, not a throwaway.

**Token budget:** Estimated 2,800–2,900 tokens of active work against 39,600 ceiling. Well within budget.

---

## 2026-05-18 — Sprint 3 Deploy Status

Sprint 3 code complete. CEO ran ./deploy.sh backend. Gmail Drafts smoke test draft not yet visible in Gmail at deploy time — attributed to Cloud Run cold start or propagation delay, not a confirmed bug. CEO rechecking in ~5 minutes. Sprint 3 will be marked fully verified once smoke test draft is confirmed in Gmail. Do not begin Sprint 4 planning until verification resolves.

---

## 2026-05-18 — Group Chat Feature Inquiry (CEO Question)

Group chat has not been discussed previously. CEO raised the idea of Hana participating in a group chat. PM assessment: not on the current roadmap (Sprints 1-12). Platform is unspecified — complexity varies significantly (iMessage, WhatsApp, Slack). No decision made. Logged as a wishlist item alongside calendar views. Recommend revisiting at Sprint 10 (mobile frontend design) when the communication surface is being evaluated holistically. CEO to clarify target platform before this can be scoped.

---

## 2026-05-18 — SMS Channel Placement Decision

SMS confirmed as supplementary opt-in channel, not a primary interface. Placement: Sprint 10, additive track alongside core mobile screens. Rationale: opt-in toggle is a native UI element of the mobile app; building it in the same sprint avoids a separate SMS-only sprint. Scope: Twilio number, inbound webhook, opt-in toggle, constrained response formatter (short/conversational tone). Dependency: mobile auth layer decision must be resolved before Sprint 9 — same gate that already exists, no new dependency created. If Sprint 10 gets crowded, formatter ships minimal and is polished in Sprint 11. No displacement to Sprints 4-9.

---

## 2026-05-18 — Full 12-Sprint Roadmap Snapshot (Post-SMS Addition)

Full roadmap as of today. Plan.md covers Sprints 1-6 in detail; Sprints 7-12 are placeholder-level. SMS addition (today) is now incorporated into Sprint 10.

**Phase 1 — Backend Core (Sprints 1-6)**
- Sprint 1 — COMPLETE. Audit and observability foundations (prompt capture, tool args, notes tracking, revert endpoint).
- Sprint 2 — COMPLETE. Email cache migrated to Firestore + GCS blobs. 506 emails migrated.
- Sprint 3 — COMPLETE. ActionClass abstraction, pending_actions collection, Gmail Drafts feature, RFC sort fix, notes_consulted audit. CEO smoke test pending at close.
- Sprint 4 — NOT STARTED. Cloud Tasks integration — replace in-process threads with reliable background queue. Retry logic, processing_status field. Highest-complexity sprint; budget extra buffer.
- Sprint 5 — NOT STARTED. Hygiene cleanup — delete deprecated routes, consolidate duplicate prompt logic, wire or delete dead code. Scope partially reduced by Sprint 3 fixes.
- Sprint 6 — NOT STARTED. Split main.py into Flask Blueprints by domain (emails, tasks, calendar, files, filters, agent, memory, admin). Shared helpers in lib/. First real-user exposure (2-3 users on Gmail Drafts flow).

**Phase 2 — Voice AI (Sprints 7-8)**
- Sprint 7 — PLACEHOLDER. Twilio inbound phone integration + Google Cloud STT. Hana can receive calls and transcribe speech.
- Sprint 8 — PLACEHOLDER. Google Cloud TTS — Hana responds with synthesized voice. Structured user interviews (5 users) to lock confidence threshold before mobile begins. Open question: does Hana initiate calls? CEO must answer before Sprint 8 scope is finalized.

**Phase 3 — Mobile Frontend (Sprints 9-12)**
- Sprint 9 — PLACEHOLDER. Mobile API hardening — auth layer, rate limiting, mobile-specific endpoints. Decision required: Firebase Auth vs. alternatives.
- Sprint 10 — PLACEHOLDER. Core mobile screens + SMS opt-in channel. Twilio number, inbound webhook, opt-in toggle, constrained SMS formatter. Decision required: React Native vs. Flutter. Marketing strategy must be defined no later than this sprint.
- Sprint 11 — PLACEHOLDER. Stripe or RevenueCat subscription integration, paywall, pricing tier UX.
- Sprint 12 — PLACEHOLDER. App store prep — privacy policy, OAuth scope justification, TestFlight beta (5-10 users minimum), submission. Allow 2-4 week review buffer given Gmail/Calendar scope sensitivity.

**Open CEO decisions blocking future sprints (in urgency order):**
1. Does Hana initiate calls? — needed before Sprint 8 scope is finalized.
2. Mobile auth layer — Firebase Auth recommended; decision required before Sprint 9.
3. React Native vs. Flutter — decision required before Sprint 10.
4. Solo developer or hire for mobile phase?
5. First 5-10 beta users — recruit now; do not wait for Sprint 12.

---

## 2026-05-18 — Multi-User Scale Question (CEO Question)

Current plan (Sprints 1-6) is architected around a single user. Infrastructure choices (Firestore, Cloud Run, Cloud Tasks) are horizontally capable but the data model has never been reviewed for multi-tenant correctness. Two explicit gaps to address before mobile:

1. Sprint 4 gate: Engineer must confirm Cloud Tasks handler isolates work by user ID, not a single shared queue. Flag any single-user assumptions before sprint closes.
2. Sprint 9 gate: Add explicit scale-readiness audit to scope — review Firestore collection paths, auth scoping, and rate limiting model against multi-user tenancy before mobile client is built on top of single-user assumptions.

No redesign needed today. The risk is that we build the mobile client on a data model that breaks at user 2. Sprint 9 is the last safe checkpoint to catch this without a rewrite.

---

## 2026-05-18 — Pre-Sprint 4 CEO Confirmations

**Decision 1: Gmail Drafts OAuth re-authorization is confirmed complete.** The Drafts path is live and verified. Sprint 3 is fully closed. No outstanding smoke test dependency.

**Decision 2: Firestore schema will be multi-user-safe from day one.** All collection paths will follow the `users/{user_id}/pending_actions/{action_id}` pattern (and equivalent for other collections). No single-user shortcuts will be taken. The Sprint 9 scale-readiness audit gate still stands but its risk profile is materially lower — we are building correctly from the start, not retrofitting.

**Sprint 4 status: fully unblocked.** Cloud Tasks integration proceeds as planned.

---

## 2026-05-18 — Sprint Process Standing Rules (CEO Mandate)

Two standing rules are now baked into every sprint ceremony. Non-negotiable. Apply starting Sprint 4.

**Standing Rule 1 — GitHub commit before sprint launch:**
Before Coder writes a single line, the team must confirm the latest code is committed and pushed to GitHub. This is a rollback safety requirement. If a sprint introduces a breaking change, the team needs a clean revert point. No exceptions.

**Standing Rule 2 — Minimize CEO involvement:**
Agents and Coder handle everything they can without the CEO — bash commands, gcloud commands, deploys, IAM bindings, Firestore setup, and any other terminal operations. Only escalate to the CEO when something genuinely requires their credentials, billing access, or an account-level decision that cannot be delegated. The CEO is not a technical blocker.

---

## 2026-05-18 — Sprint 4 Kickoff

**Sprint 3 retrospective:** Closed cleanly. No open feedback from CEO. Post-deploy OAuth bug caught and fixed before sprint close. Smoke test confirmed.

**Sprint 4 scope finalized after one round of the meeting circle. Clean consensus.**

**Scope (8 items):**
1. GCP queue creation — `hana-actions` queue (CEO must run gcloud command if not already done).
2. Multi-user Firestore schema audit — all paths to `users/{user_id}/` namespace. New `db_schema.py` for documentation.
3. `task_queue.py` — enqueue helper with confidence gate (>= 0.7), per-user daily cap (default 30, configurable via Firestore config doc), idempotency.
4. POST `/tasks/handle-action` handler endpoint — OIDC secured, processing_status idempotency guard.
5. `processing_status` field — added to pending_actions schema. Values: pending, in_progress, complete, failed.
6. Wire enqueue into `process_single_email` and `run_morning_agent` — remove threading.Thread calls.
7. Cloud Tasks retry config — 3 attempts, 10s–300s backoff, max 3 doublings.
8. Smoke test — one end-to-end task enqueues, routes to handler, resolves in Firestore.

**Key amendments from meeting circle:**
- Finance: enqueue cap must be configurable via Firestore config doc, not hardcoded. Accepted.
- Strategy: confidence threshold must gate enqueue decisions. Resolved by adding `action.confidence >= 0.7` check to `enqueue_action()`. Threshold stored in Firestore config for tuning without redeploy.
- Designer: processing_status values must be clean and consistent. Added to acceptance criteria.
- Business: multi-user schema must be commented in code for future legal data-handling review. Added as acceptance criterion via `db_schema.py`.

**Token budget:** Engineer estimated 5,000–6,000 tokens. Well within 39,600 sprint ceiling.

**CEO action item before sprint can complete:** Confirm Cloud Tasks queue `hana-actions` exists in GCP project (`gcloud tasks queues create hana-actions --location=us-central1`).

---

## 2026-05-18 — Sprint 5 Kickoff

**Sprint 4 retrospective:** Closed fully verified. Revision 00148 live. Cloud Tasks RUNNING. All three verification items passed. No CEO feedback pending.

**Sprint 5 scope finalized after one round of meeting circle. Clean consensus.**

**Pre-sprint action:** Commit and push all Sprint 3 and Sprint 4 changes to GitHub (Standing Rule 1). Sprints 3+4 code was untracked/uncommitted at ceremony start.

**Scope (6 items):**
1. notes_consulted closure fix — inspect `_make_agent_*` factories, bind at factory time, verify via live agent decision log.
2. Delete deprecated /proposals routes — 3 DEPRECATED-tagged endpoints + inline proposals blocks (conditional on frontend defensive-handling check).
3. Delete ONBOARDING_SYSTEM_PROMPT from prompts.py — no callers, safe delete.
4. Wire or delete _topic_blocked — no call sites found, inspect then delete or add TODO.
5. Consolidate intent-evaluation verdict rules — extract `_INTENT_VERDICT_RULES` constant in email_scanner.py.
6. Task-existence check audit — consolidate if duplication found; close as stale if not.

**Explicit deferral:** emails flat namespace migration to `users/{user_id}/emails/` — deferred to Sprint 9. Named gate added to plan.md.

**Key amendment from meeting circle:**
- Strategy: acceptance criteria must be binary (done or deferred, no partial states). Notes_consulted fix requires live verification, not just code review.
- Designer/Marketing: frontend defensive-handling check required before removing inline proposals data from email list routes.

**Token budget:** Engineer estimated 2,200–2,800 tokens. Well within 39,600 ceiling.

---

## 2026-05-18 — Sprint 6 Kickoff

**Sprint 5 retrospective:** Closed cleanly. 38 insertions, 217 deletions across 5 files. Revision 00150 live. No CEO feedback pending.

**Critical discovery at sprint ceremony:** main.py is 2,254 lines with 80 routes — 60% larger than the ~1,400 line plan estimate. A full 8-domain Blueprint split is not tractable in one sprint.

**Plan updated:** Sprint 6 scope reduced to lib/ infrastructure + routes/agent.py + routes/tasks.py. Full split deferred to Sprint 7. Original Sprint 7 (Voice AI) slides to Sprint 8. Roadmap extended by one sprint — now 13 sprints total. Plan.md updated to reflect this.

**Sprint 6 scope finalized after two rounds (one disagreement resolved):**
- Round 1 disagreement: Engineer (easy domains first) vs. Strategy (high-value Phase-2 domains first). Resolved in Round 2 — Engineer updated proposal to build lib/ infrastructure first, then extract agent + tasks. Strategy accepted.
- Marketing resolution: first real-user exposure decoupled from Sprint 6. Can begin immediately — Gmail Drafts is live.

**Sprint 6 scope (4 items):**
1. backend/lib/ with auth.py (OIDC verifier), firestore_client.py (db singleton), config.py (shared constants)
2. routes/agent.py Blueprint: /agent/run, /agent/email-trigger, /agent/renew-gmail-watch, /briefing/* routes
3. routes/tasks.py Blueprint: /tasks/handle-action, /tasks/process-email, /pending-actions routes
4. main.py thinned to app factory + Blueprint registrations + /health + remaining unsplit routes

**Token budget:** Engineer: medium, 3,500–4,500 tokens. Session cumulative (last 5h): 126,506 — LARGE flag noted. Within subscription cap. Scope held at medium to avoid overrun.

---

## 2026-05-18 — Sprint 7 Kickoff and Completion

**Sprint 6 retrospective:** Closed cleanly. No CEO feedback. Revision 00153 live. Blueprint foundation complete.

**Token budget flag:** 171,655 output tokens in the last 5 hours (threshold 50K). Flag noted. Sprint 7 scope trimmed accordingly.

**Plan updated:**
- Sprint 7 scope reduced from 6 domains to 2 (emails + filters). memory, files, admin deferred to Sprint 8. calendar domain remains blocked — do not schedule until CEO confirms calendar integration unblocked.
- First external user named gate added: must occur no later than Sprint 11. Finance prerequisite: cost-per-active-user estimate must be produced before Sprint 11 launches.
- Roadmap extended by 1 sprint — now 14 sprints total. Sprints 9-14 renumbered in plan.md.

**Meeting circle — round 1, clean consensus:**
- Engineer: emails.py + filters.py only. MEDIUM. Estimated 4,000–5,500 tokens.
- Marketing: no domain objection. Flagged zero external users after 6 sprints — first user milestone needed.
- Designer: no objection. Seconded demo/interactive experience planning for before mobile.
- Finance: no objection. Flagged cost-per-active-user estimate needed before Sprint 11 pricing.
- Business: emails.py + filters.py only. Reinforced Marketing.
- Strategy: endorsed trim. Named gate: first external user no later than Sprint 11.

**Sprint 7 results:** routes/emails.py (26 routes) and routes/filters.py (16 routes) extracted. main.py reduced from 1,593 to 488 lines. No API contract changes. Revision 00154-dsb live and smoke-tested. Git commit 024efe7 pushed to GitHub.

---

## 2026-05-18 — Board Roadmap Visual Created

Generated `/home/dcjohnston1/saucer/team/roadmap.png` — a board-ready Series A deck visual of the full 13-sprint roadmap. Dark background, professional color coding: green = complete (Sprints 1–6), amber = Phase 2 current, blue = planned, grey = placeholder. Shows all four phases (Backend Core, Blueprint + Voice AI, Mobile Frontend, Growth), a progress bar (6/13 sprints, 46%), key milestones, and the $220K run-rate profitability target prominently in the header.

---

## 2026-05-18 — Sprint 8 Kickoff and Completion

**Sprint 7 retrospective:** Closed cleanly. No CEO feedback. Revision 00154-dsb live. Blueprint wave 1 complete.

**Token budget flag:** 168,441 output tokens in the last 5 hours (threshold 50K). Third consecutive LARGE flag. Scope held tight accordingly.

**Sprint 8 scope finalized after one round of meeting circle. Clean consensus.**

**Scope (3 items):**
1. routes/memory.py — 6 hana notes and question routes
2. routes/files.py — 4 file CRUD routes
3. routes/admin.py — 12 routes (user-settings, actions history, decisions, onboarding stub, conversation-history, session checkpoint, debug)

**Calendar routes:** Stayed in main.py (blocked). Calendar unblock trigger documented: CEO must confirm Google Calendar OAuth credentials are configured and gcalendar.py module is functional.

**Action items from meeting circle:**
- Sprint 9 must include first external user action (recruit + onboard at least 1 user), parallel to engineering work.
- Finance to begin building cost-per-active-user estimate (standing action, gate for Sprint 11).

**Sprint 8 results:** routes/memory.py (6 routes), routes/files.py (4 routes), routes/admin.py (12 routes) extracted. main.py is now a true thin shell — 130 lines, 5 blocked calendar routes + /health only. No API contract changes. Revision 00156-qzf live and smoke-tested. Git commit 332612f pushed to GitHub. Blueprint refactor is complete (minus blocked calendar domain).

---

## 2026-05-18 — CEO Mandate: Product Fixes Sprint Insertion (Sprint 9 Insertion)

**Trigger:** CEO direct mandate in huddle. Five product-facing items slotted between Sprint 8 (complete) and the previously planned Sprint 9 (Voice AI).

**Decision:** Insert new Sprint 9 — Product Fixes. Voice AI slides to Sprint 10. TTS to Sprint 11. All remaining sprints cascade by one. Roadmap is now 15 sprints total. Sprint 12 holds all formerly Sprint-11 named gates unchanged.

---

## 2026-05-18 — Sprint 9 Kickoff

**Sprint 8 retrospective:** Closed cleanly. No CEO feedback. Revision 00156-qzf live. Blueprint refactor complete. main.py is a true thin shell at 130 lines.

**Token budget flag:** 77,726 output tokens in the last 5 hours (threshold 50K). LARGE flag noted. Sprint 9 scope is CEO-mandated and cannot be trimmed. Proceeding. Monitor Sprint 10 closely.

**Sprint 9 scope finalized after one round of meeting circle. Clean consensus. No Round 2 needed.**

**Scope (8 CEO-mandated items):**
1. Briefing attribution fix — prompt guard (AGENT_SYSTEM_PROMPT, SINGLE_EMAIL_SYSTEM_PROMPT)
2. Briefing attribution fix — structural (briefing_assertions array in write_briefing tool schema, stored to Firestore)
3. Restore email summary — verify existing summarize_emails() path is live; fix if not
4. Restore task determination — scan_emails_for_todos as standalone on-demand endpoint
5. Restore task swiping — accept/reject swipe UI; ships with Item 4
6. Restore email highlights — source_spans stored to Firestore email doc field; excerpt route reads from there
7. Briefing-to-chat handoff — briefing appears as Hana's first history message in chat, not in input field
8. Note dedup fix — AGENT_SYSTEM_PROMPT + save_note_tool docstring (search before save) + _gemini_merge (remove contradictions)

**Sequencing:** Items 1,8 first (prompt-only) → Item 2 (structural) → Items 4+5+6 (coupled unit) → Item 3 (verify/fix) → Item 7 (frontend-only)

**Implementation note — Items 4+5+6 are a single unit:** scan_emails_for_todos generates source_spans; those spans write to Firestore email doc via update_email_fields; swipe accept calls mediator.add_todo(); excerpt route reads spans from Firestore (not saucer-proposals.json which is never written).

**Key engineering notes:**
- Item 3 (email summary): summarize_emails() and the summary field write path appear intact in routes/emails.py (lines 329-353). Coder should verify the summary field is being returned in API responses before adding any new code.
- Item 7 (briefing-to-chat): frontend already has openBriefingChat() at line 3163 but puts text in input field. Change to pass briefing message as first history entry in /chat POST body.

**Action items from meeting circle (not Sprint 9 blockers):**
- Business: Privacy Policy must cover briefing_assertions (person-specific structured claims) before first external user — pre-Sprint-10 action.
- Strategy: CEO to begin external user recruitment NOW in parallel. Sprint 10 must embed a user-acquisition milestone, not be purely technical.

**Complexity:** MEDIUM overall. No item is LARGE. All items are backend + frontend within existing Blueprint structure.

**Rationale:** Briefing attribution bug is a trust/correctness issue — Hana claiming credit for decisions it did not make. This cannot survive into the external-user window (Sprint 10+). The other four items (email summary, task determination, task swiping, email highlights) are product-surface regressions from Sprint 5 proposals cleanup. They belong in a single focused sprint before real users arrive, not scattered across Voice AI sprints.

**Item placement:**
1. Briefing attribution bug (prompt guard + write_briefing schema change) — Sprint 9. High priority, correctness.
2. Restore email summary (gray preview text on email card) — Sprint 9. Small. Independent.
3. Restore task determination (AI to-do extraction from email) — Sprint 9. Medium. Coupled with item 4.
4. Restore task swiping (swipe left/right to accept/reject tasks) — Sprint 9. Medium. Depends on item 3, ships together.
5. Restore email highlights (/email/<id>/excerpt + source_spans) — Sprint 9. Small. Backend likely intact per Sprint 5 notes; may be frontend-only wiring.

**Named gates unchanged:** All Sprint 11 gates now live at Sprint 12. No gate was removed or weakened. The first external user gate and emails namespace migration gate are still intact at the same relative position in the roadmap.

**Note on items 3+4:** The old task determination path was deleted in Sprint 5 as part of the proposals cleanup (scan_emails_for_todos import removed, proposals acceptance flow deleted). The rebuild must be a standalone extraction path — not a resurrection of the deprecated proposals flow.

---

## 2026-05-19 — Sprint 10 CEO Decisions (Pre-Circle Confirmed)

**Decision 1 — Voice direction: IN-APP voice only.**
No Twilio, no phone calls. User holds a button in the mobile app, speaks, Hana responds with audio. Like Siri.
Twilio inbound phone integration DROPPED from Sprint 10 scope entirely.
Google Cloud STT (speech-to-text) and TTS (text-to-speech) remain in scope.
Audio encoding decision: frontend records WebM/Opus (native MediaRecorder API), backend accepts multipart form-data, converts to LINEAR16 for Google Cloud STT API, returns MP3 audio blob.
Voice UX requirements (hard, not nice-to-have): hold-to-record button, pulsing recording indicator, auto-play response with stop/replay control, fallback prompt if STT confidence is low.

**Decision 2 — First external user: Emily confirmed.**
Emily (CEO's partner) is approved as external user #1.
CEO rationale: she won't hold back on feedback; CEO does not want to burden a friend until the product is more polished.
Named gate: Emily must run Hana at least once before Sprint 10 closes.
Team owns onboarding materials — not a CEO terminal action item.

---

## 2026-05-18 — To-Do Source Email Highlight Placement Decision (CEO Feature Request)

**Feature:** When user taps a to-do and navigates to its source email, highlight the pertinent text that caused the to-do creation. Uses existing source_spans / /email/<id>/excerpt route (confirmed intact, Sprint 5).

**Decision: Deferred to Sprint 10.**

**Rationale:** Sprint 9 is already medium complexity — briefing attribution structural fix, email summary restore, task determination rebuild (medium, coupled with swiping), task swiping, email highlights restore, and briefing-to-chat handoff are all in scope. This feature is logically downstream of Sprint 9 items 3, 4, and 5 (task determination, task swiping, and email highlights must all be confirmed working first). Adding it to Sprint 9 risks scope overrun. It is slotted as an additive item in Sprint 10 alongside Voice AI / first external user work.

---

## 2026-05-19 — Sprint 11 Kickoff

**Sprint 10 retrospective:** Voice is working. CEO reports lag between recording end and response start — earcon requested to fill the gap. Emily onboarding guide is ready but Emily has not yet run the app. Sprint 12 gate remains open.

**Token budget:** 85,290 output tokens in last 5 hours. LARGE flag. Sprint 11 scope kept light.

**Sprint 11 scope: all items small. Circle reached consensus in one round.**

**Code scope (3 items):**
1. Voice earcon — Web Audio API oscillator in app.js, plays on recording stop, loops during processing. Soft rising tone, under 500ms. Zero backend changes.
2. Voice retry state — red/neutral visual state + "Didn't catch that, try again" label + auto-reset on STT low-confidence response. Frontend only.
3. TTS voice constant — add configurable HANA_VOICE_NAME constant to voice_handler.py.

**Non-code scope (3 items):**
4. Emily onboarding guide handed to CEO with URL (https://saucer-frontend-6ksi6iut7a-uc.a.run.app). CEO to forward to Emily this week.
5. Finance to produce rough cost-per-active-user estimate (Sprint 12 named gate prerequisite).
6. CEO to name one organic User #2 candidate before Sprint 11 closes. Criteria: warm network, not family, working parent 25-45, will give unvarnished feedback.

**Strategy flag:** Sprint 12 cannot launch without Emily confirmed and cost estimate complete. These are named gates, not soft targets.

**Plan change:** plan.md Sprint 11 placeholder is accurate as-is. No update needed.

## 2026-05-19 — Sprint 12 Key Decisions

**CEO decision locked:** Auto-calendar trigger = Option A (background, silent + dismissable). Events appear on calendar immediately when Hana processes an email containing a date/event. No morning-briefing dependency.

**All 8 deferred items addressed in one sprint.** No deferrals. Items 1/2/3/5/7/8 were small. Item 4 was medium. Item 6 was resolved by CEO decision.

**Item 7 required no code change** — "View email" link on calendar events was already wired through to the excerpt drawer from Sprint 9+10. PM confirmed before handing off.

**Calendar trust rule locked:** Gemini prompt for `add_calendar_event` tool uses a restrictive instruction. Only creates events with (1) clear date, (2) clear household commitment, (3) human action required. The team (Strategy, Finance) emphasized this is a trust escalation — one false calendar entry is worth ten missed events in terms of churn damage.

**CEO action items flagged (not code tasks):**
1. Privacy Policy and Terms of Service — publish before adding more external users.
2. Calendar OAuth service account — must switch to per-user credentials before public user onboarding.

**Next sprint:** Sprint 13 — Mobile API Hardening. Named gates: Emily confirmed, Finance cost estimate, emails namespace migration.

**Token health at sprint close:** 19,318 output tokens (last 5h). Well within budget.

---

## 2026-05-19 — Sprint 13 Kickoff and Key Decisions

**CEO feedback on Sprint 12 (3 bugs):**
1. Sender filter still broken — floortje@artwithflo.com still appears. Root cause: Sprint 12 fix only patched /emails/cached; /emails GET was untouched.
2. To-do extraction broken for lamanti@gmail.com. Root cause unknown at kickoff — error logging added to diagnose.
3. Future Events doesn't load. Root cause: no try/catch around _loadCalendarContent in openFutureEventsScreen; calendar OAuth may also be broken (shared service account).

**Sprint renamed:** "Sprint 13 — Bug Fixes + Auth Foundation" (was "Mobile API Hardening").

**Emails namespace migration deferred to Sprint 14.** Engineer recommendation accepted by PM: 500+ live Firestore docs must be migrated in a dedicated sprint, not as a sidecar. Named gate preserved at Sprint 14, not dropped.

**Finance cost estimate delivered (Sprint 13 gate closed):** $0.80–$3.50/user/month (light to heavy user). Voice adds $0.30–$0.60/user/month. At $9/month: viable for average users, squeezed for heavy users. Recommendation: do not add prompt caching optimization until Sprint 15+ but track usage closely.

**Token health at sprint close:** 25,836 output tokens (last 5h). OK — well within 50K threshold.

**Sprint 14 named gates confirmed:**
- Emails flat collection migrated to users/{user_id}/emails/ (dual-write + backfill)
- Emily confirmed (has run Hana at least once)
- React Native vs. Flutter decision required
- Marketing strategy defined

---

## 2026-05-20 — CEO Live Demo Bugs (Pre-Sprint 14 Assessment)

Three UX bugs surfaced in a live CEO demo. All three are Sprint 14 material. Priority order:

1. **Issue 1 — Spinner never resolves / Gmail sync suspect (HIGH).** CEO sent himself a Gmail with two clear to-dos; nothing appeared after 5 minutes. Two possible root causes: (a) action item extraction not running or completing, (b) Gmail sync not delivering new mail. Issue 1 blocks meaningful QA of Issue 2. Fix first.

2. **Issue 3 — Hana draft appears as separate email card (MEDIUM, independent).** Draft should be embedded inline in the source email card. A floating draft card creates a trust risk — a new user could mistake it for a sent email. Self-contained frontend fix; can be parallelized with Issue 1 investigation.

3. **Issue 2 — Action item displays as quoted text string, not interactive card (MEDIUM, downstream of Issue 1).** Swipeable/assignable to-do card UI is missing; instead shows raw string. Cannot be properly QA'd until Issue 1 is confirmed delivering real action items. Implement after Issue 1 pipeline is confirmed end-to-end.

**Key dependency:** Issue 1 must be resolved before Issue 2 can be tested. Issue 3 is independent. All three must be closed before the Emily named gate (Sprint 14) can close cleanly.

---

## 2026-05-20 — Sprint 14 Scope Restructure (CEO Decision, No Objection)

Sprint 14 scope restructured by CEO mandate. PM confirmed no objection.

**New Sprint 14 scope (bugs first):**
1. Issue 1 — "Checking for action items" spinner never resolves + Gmail sync delay (HIGH, fix first)
2. Issue 2 — Action item displays as raw string instead of interactive swipeable card (MEDIUM, downstream of Issue 1)
3. Issue 3 — Hana draft floats as separate email card instead of embedded inline in source card (MEDIUM, independent)

**Pushed to Sprint 15+:**
- Emails flat namespace migration to users/{user_id}/emails/ (named gate preserved, not dropped)
- React Native vs. Flutter decision
- Marketing strategy definition
- Emily confirmation as named gate (cannot close cleanly until bugs are fixed anyway)

**Rationale:** Emily cannot be onboarded against a broken product. All three bugs block the Emily gate directly. The deferred items are either dependent on a working product or planning decisions that absorb a one-sprint delay without consequence.

---

## 2026-05-20 — Sprint 14 Kickoff

**Sprint 13 retrospective:** Closed cleanly. Three P0 fixes from Sprint 12 regressions plus Firebase Auth infrastructure and rate limiting. All acceptance criteria passed. Git commit 757b549.

**Token budget:** 12,568 output tokens in last 5 hours. Well within 50K threshold.

**Meeting circle:** Round 1, clean consensus. No Round 2 needed.

**Key decisions from circle:**
- Bug 1a and 1b must ship together (Strategy requirement). Fixing the frontend spinner text without the backend write would display "No to-dos found" on emails the agent actually processed — a different trust failure.
- Bug 2 Part 2 must use a single batch Firestore query for draft actions, then join in memory. No per-email reads. (Finance concern, accepted by Engineer.)
- Draft section must use muted gray styling. Do not use the app accent color for draft elements — risk of user mistaking draft for sent mail. (Designer requirement.)
- "No to-dos found" preferred over "No to-dos" — implies Hana looked, which is correct. (Designer decision.)
- All named gates (Emily, emails migration, mobile decisions) moved to Sprint 15.

**Root causes confirmed (Engineer):**
- Bug 1: add_todo_tool writes to Google Docs only. The proposals field on the Firestore email doc is never written by the agent path. The scan-todos route handles this for on-demand scanning but process_single_email has no equivalent write.
- Bug 2: Gmail DRAFT-labeled messages are not filtered before upsert_emails_batch in the Pub/Sub handler. Draft cards appear in the email list as a result.
- Bug 3: Downstream of Bug 1. buildProposalRow is intact and correct. Never fires because proposals is always null.

**Token estimate:** Engineer: 3,500–4,500 tokens. All other agents: no code work. Total sprint: well within budget.

---

## 2026-05-20 — CEO Screenshot Review (Pre-Sprint 15 Signal)

CEO shared a live screenshot of the app. Three filter tabs all show red notification dots ("This Week," "To-Do's," "Dismissed Emails"). Both visible email cards (Nextdoor neighborhood safety alert, Best Buy promo) show "No to-dos found" beneath them.

PM assessment: The notification dots are broadcasting false urgency. This is the Bug 1 symptom in production — proposals field is never written by the agent path, so "No to-dos found" is correct but the red dots are not. The dots have no awareness of whether Hana actually found anything. This is a trust-destroying combination: "look here" + "nothing here." Secondary signal: low-signal emails (neighborhood alert, promotional) are surfacing in the default view, compounding the empty-state problem. Both bugs must be confirmed closed in Sprint 14 before Emily is onboarded.

---

## 2026-05-20 — Sprint 16 Staged: Trust Pills + Honest Dismissed Labels (Live Huddle)

**Source bug:** CEO screenshot review showed Dismissed Emails view rendering "No to-dos found" beneath a DeKalb County Police safety alert and a Best Buy promo. Engineer confirmed both were correctly dismissed by the filter — but the "No to-dos found" label is a lie. Hana never scanned them. Filter blocked them upstream. Designer flagged this as the active trust leak.

**Locked decisions:**

1. **Honest Dismissed labels.** Replace "No to-dos found" with "Not scanned" (or equivalent) on filter-blocked emails in the Dismissed view. Files: `frontend/app.js` `buildProposalsSection`. Pure frontend, ~15 min.

2. **"Known sender" pill (allowlist passes).** Placement: left of sender address, top of card, main inbox. Shown only when filter passed because sender is allowlisted. Marketing copy: **"From someone you trust"** or **"You allowlisted this sender"** — NOT "Known sender" (sounds like IT helpdesk). Backend already writes `verdict_reason: 'Sender is on the permitted list'`. Engineer: ~30 min, pure frontend.

3. **"Relevant topic" pill (topic match passes).** Placement: under subject line, main inbox. Shown when email matched a topic from the "What emails belong here?" freetext box or Include Keywords list. Display the user's own matched phrase (**"Matched: school pickup"**), NOT system jargon. Needs new backend field `matched_topic`. Keyword case is trivial; freetext case extends Gemini JSON schema. ~1–2 hrs backend + ~1 hr frontend. Additive, no migration, cost-negligible.

4. **Pill visual constraints (Designer).** Low-weight outline pills (reassurance, not alerts). Separate rows so pills do not compete. Topic pill truncates at ~20 chars.

5. **No fallback pill.** When neither rule applies, render nothing. CRITICAL CONSEQUENCE: an email landing in the inbox with no pills means the filter has a hole. That is a bug, not a neutral case. Pills function as diagnostics. Fix upstream at the filter — do not paper over it in the UI.

**Backlog pushed to Later:**
- Sprint 15 blockers (CEO smoke-test sign-off, 5 backlog decisions)
- Calendar integration ("This Week" / "Next Week" views)
- Emails flat namespace migration
- React Native vs. Flutter decision
- Marketing strategy definition
- Emily named-gate close

**Sprint file:** `/home/dcjohnston1/saucer/team/sprint_16.md`

