# Engineer History
*Running log of tech stack decisions, architectural choices, and technical debt notes.*

## Prior Context
- Sprint 1 and Sprint 2 are complete. See sprint_results.md for full detail.
- Known open issue: notes_consulted closure capture bug — MOVED UP to Sprint 3 (was Sprint 5).
- Email storage now lives in Firestore + per-email GCS blobs via email_store.py.
- Rollback blob saucer-emails.json in GCS, delete on or after 2026-06-15.
- Lesson learned: always confirm deploy revision is live before smoke testing.

## 2026-05-16 — Technical Decisions and Concessions (PM/Engineer Sequencing Review)

**Conceded:**
- Acknowledged notes_consulted is more significant than previously treated. It's a gap in a feature we explicitly built (audit trail), not just a cosmetic issue. Agreed to move the fix into Sprint 3.
- RFC 2822 sort bug also moved into Sprint 3.

**Held firm on:**
- ActionClass must precede any outbound tool. Inline confirmation logic per-route is a copy-paste trap that costs more to retrofit than to front-load. PM accepted this.
- Cloud Tasks cannot be skipped if Hana is primarily a proactive agent. Adding background-driven features on top of the current in-process model without Cloud Tasks risks a complete rewrite.

**On-demand email drafting (Option B) — conditionally accepted:**
- If CEO declares Hana is reactive (command-driven), on-demand draft-email in Sprint 4 is architecturally viable via a separate code path.
- Risk flagged: two code paths for the same capability (on-demand + background). Not clean, but not fatal.
- If CEO declares Hana is proactive, Cloud Tasks stays at Sprint 4 and on-demand drafting is deferred.

**Sprint 5 + 6 coupling confirmed:**
- Hygiene cleanup must precede main.py file split. These two sprints cannot be reordered or separated.

**Investigation protocol for Sprint 3 notes_consulted fix:**
- If root cause is a closure issue: fix it.
- If root cause is structural (concurrency, shared factory state, etc.): document and defer. No open-ended refactor mid-sprint.

---

## 2026-05-16 — PM/Engineer ROI and Visibility Interrogation (Session 2)

**Conceded:**
- Acknowledged that "Drafts-only" outbound path (writing to Gmail Drafts, user sends manually) does not require ActionClass to be safe — the user retains full control of sending. PM correctly identified this gap in the original framing.
- Accepted PM's business argument: two invisible sprints followed by a high-complexity Cloud Tasks sprint before any user-visible feature is a retention risk for a product with no customers yet.
- Agreed to add Gmail Drafts as the first ActionClass consumer in Sprint 3, making Sprint 3 ship something the user can see.

**Held firm on:**
- ActionClass must still be the consumer layer even for Gmail Drafts. Bypassing it to ship faster creates a seam that would cost half a sprint to retrofit later. PM accepted this framing.
- Cloud Tasks sequencing cannot be resolved without CEO answering the proactive/reactive question. If Hana is proactive, delaying Cloud Tasks past Sprint 4 risks retrofitting reliability onto multiple features. Escalated to CEO.
- Sprint 5 scope is variable and will grow. Treating it as a fixed list is incorrect. Token-budget framing adopted.

**Sprint 3 — final engineering scope:**
- ActionClass abstraction + Firestore pending_actions collection
- notes_consulted closure capture fix (or document-and-defer if structural)
- RFC 2822 string sort fix
- Gmail Drafts wiring as first ActionClass consumer
- PREREQUISITE: gmail.compose OAuth scope re-authorization by CEO before sprint begins. Build Drafts last; if auth isn't confirmed, ship other items first.
- Estimated effort: ~6 hours (was 4-5 on original scope; +1 hour for Drafts wiring)

**Token budget note:**
- Sprint 3 is tight at ~6 hours. If notes_consulted investigation reveals a structural issue requiring more than a simple fix, that investigation time must come from Drafts wiring time. Do not let both run long simultaneously.

**On-demand vs. background code path risk (on record):**
- If CEO declares Hana reactive and on-demand drafting ships in Sprint 4, it creates a second code path alongside background processing. These will diverge. Engineer has flagged this risk formally and it is documented. If the CEO accepts that risk, engineer will build the on-demand path cleanly but will not be responsible for the reconciliation cost if the decision reverses later.

---

## 2026-05-17 — Voice AI (Phone Calls) Feasibility Assessment

**Verdict: Technically buildable. Not near-term. Earliest realistic slot is Sprint 7 or later.**

**Proposed stack:**
- Telephony: Twilio Programmable Voice (outbound calls, webhook callbacks). Twilio is the clear default — it has the widest API surface and the most LLM integration documentation. Vonage is a viable alternative but no material advantage here.
- STT: Google Cloud Speech-to-Text (streaming). Already in GCP ecosystem, lower latency than third-party options, cost-efficient.
- TTS: Google Cloud Text-to-Speech (Neural2 or Chirp voices). Same reasoning — stay in GCP, reduce vendor count.
- LLM orchestration: Gemini (already in use for Hana decisions) drives the conversation state machine. Each turn: STT output -> Gemini prompt with call context -> TTS -> audio back to Twilio.
- Integration: phone call completion triggers an ActionClass result back into Hana's pipeline (e.g., "appointment confirmed for Tuesday 2pm" writes to Firestore tasks).

**Per-call cost estimate (10-minute call, rough):**
- Twilio outbound voice: ~$0.014/min = ~$0.14
- STT (streaming, 10 min): ~$0.024
- TTS (Neural2, ~2000 chars output): ~$0.016
- Gemini API (multiple turns, ~5k tokens): ~$0.02–0.05
- Total per call: roughly $0.20–$0.25

**Monthly cost at modest scale (50 calls/month):** ~$10–15 in API costs. Not a blocker. At 500 calls/month it's $100–125 — still manageable. The main cost risk is runaway calls if the conversation loop errors out; need hard call-duration caps in the orchestration layer.

**Roadmap placement:**
- Cannot start before ActionClass is solid and Cloud Tasks is in place. Voice calls are stateful, long-running, and asynchronous — exactly the failure mode ActionClass and Cloud Tasks were designed to handle. Trying to bolt voice onto the current architecture before that foundation exists would be a painful retrofit.
- Sprint 7 is the earliest realistic slot, assuming Sprints 3–6 go cleanly.

**Key risks:**
- Call state management is more complex than email drafting. Partial failures mid-call (Twilio drops, STT hiccups, Gemini timeout) need explicit retry/resume logic, not just idempotency.
- The conversation prompt design for real phone calls is non-trivial. Pizza orders are simple; insurance company IVR trees are not. Scope needs to be tightly constrained in the first version.
- Twilio requires a verified caller ID or purchased number — minor setup but a CEO action item before any sprint work starts.
- Regulatory: outbound robocalls have TCPA exposure in the US. Calls made on the user's behalf to businesses are generally fine, but auto-dialing multiple numbers without consent is not. Keep this to single-call, user-initiated flows.

## 2026-05-17 — CEO locked proactive bet. Cloud Tasks stays at Sprint 4; on-demand drafting deferred. Bridge plan: Hana decides proactively, acts only on user-triggered pull until Cloud Tasks ships.

---

## 2026-05-17 — Infrastructure Cost-Per-User-Per-Month Model (for Finance P&L)

**Pricing sources:**
- Claude Sonnet 4.6: $3.00/MTok input, $15.00/MTok output (confirmed live from Anthropic docs)
- Firestore: $0.06/100K reads, $0.18/100K writes, $0.02/100K deletes (stable industry rates, labeled estimate)
- GCS Standard US: $0.020/GB/month storage, $0.000005/write, $0.0000004/read (labeled estimate)
- Cloud Run: $0.000024/vCPU-second, $0.0000025/GB-second (model-knowledge rates, consistent with GCP docs)
- Cloud Tasks: first 1M ops/month free, then $0.40/MTok (confirmed live)

**Cost summary table (per user per month):**

| Component | Calculation | Cost/User/Month |
|---|---|---|
| Claude API — base usage | 50K in + 5K out tokens at $3/$15 per MTok | $0.225 |
| Claude API — proactive checks | 300/mo * 2K in + 200 out at $3/$15 per MTok | $2.700 |
| Firestore | 3,200 reads + 2,000 writes + 300 deletes | $0.006 |
| GCS blob storage | ~0.005GB avg + 600 writes + 600 reads | $0.003 |
| Cloud Run | 500 req * 200ms * 512MB | $0.003 |
| Cloud Tasks | 700 ops/mo, inside free tier at near-term scale | $0.000 |
| Total WITHOUT voice | | $2.937 |
| Voice AI (Y3, 5 calls/mo) | 5 * $0.225/call midpoint | $1.125 |
| Total WITH voice | | $4.062 |

**Key architectural notes logged for engineering:**
- Claude API is ~99% of variable cost. GCP services are noise at current scale.
- Proactive check cadence (10/day * 2K tokens) drives $2.70/user/month — the dominant cost lever.
- Prompt caching on household notes/recurring context is a high-ROI optimization. Should target Sprint 5 or 6. Estimated 50-90% reduction on the proactive input token line if the household context block is cached across checks.
- Cloud Run free tier covers ~3,600 users before real compute costs kick in.
- Cloud Tasks free tier covers ~1,400 users.
- Voice adds ~$1.13/user/month at 5 calls/mo average — viable as a premium tier add-on rather than bundled in base plan.
- At $10/month subscription price: ~70% gross margin before fixed costs. At $5/month: ~40% gross margin.

---

## 2026-05-17 — CEO Question: Can Voice Slip Into Y1 Post-Launch?

**Answer: Only via a fire-and-forget narrow scope. Not recommended.**

Dependency chain: ActionClass (Sprint 3) -> Cloud Tasks (Sprint 4) -> Voice (Sprint 7+). Both links are load-bearing.

Without Cloud Tasks: voice runs in-process on Cloud Run. A container restart or request timeout mid-call leaves call state unknown with no retry path. Not safe.

Without ActionClass: call completion has no pipeline to write results back into Hana's task/action layer.

**The Y1 workaround path:** Fire-and-forget, user-triggered, no recovery on failure. Could start after Sprint 4. Architecturally cuts the Cloud Tasks requirement for this one feature, but ships an unreliable product. Recommendation: do not pull voice forward on this basis. Build it cleanly at Sprint 7. Trust erosion from failed calls outweighs the milestone value.

---

## 2026-05-18 — CEO Question: SMS Group Chat (Huddle)

**Verdict: Technically viable. Not near-term. Earliest realistic slot Sprint 9.**

**How iOS SMS group chat works for third-party numbers:**
- Requires a Twilio (or similar) long code or shortcode with SMS/MMS capability.
- Third-party numbers cannot join iMessage groups natively; adding Hana's number to a group thread forces a downgrade to SMS/MMS for all participants. Expect UX friction and user complaints.
- Incoming messages attributed by sender phone number, mapped to household member roster in Firestore.

**Build complexity drivers:**
- Multi-user context tracking: Hana must maintain conversational state across multiple senders, not a single authenticated user session.
- Speaker attribution: phone number -> household member lookup must be fast and reliable.
- Interjection policy: deciding when Hana speaks vs. stays silent in an active group thread is a non-trivial ML/heuristic problem requiring significant tuning.
- Conflict resolution: contradictory instructions from multiple senders (e.g., two people editing the shopping list simultaneously) need explicit arbitration logic.

**Dependencies before this is safe:**
- ActionClass (Sprint 3) — stable
- Cloud Tasks (Sprint 4) — stable
- Mature Hana decision layer with low false-positive interjection rate

**Roadmap placement:** Sprint 9 or later. If SMS is intended as the *primary* interface (replacing the mobile app concept), that is a strategic pivot requiring a full roadmap re-evaluation — flagged for CEO if that direction is being considered.

---

## 2026-05-18 — SMS Supplementary Channel Design (CEO Clarification)

**CEO confirmed:** SMS is opt-in, supplementary, activated post-setup. Style: short, conversational, family-member tone — a few lines, not paragraphs. Proactivity style and tone are product decisions, not technical blockers.

**Build components:**
- Twilio long code number (~$1/month): handles inbound and outbound SMS
- Cloud Run webhook endpoint: receives inbound Twilio callbacks
- Firestore fields per user: `sms_enabled: bool`, `sms_number: str` — toggled via app during onboarding
- Cloud Tasks trigger: when Hana has something worth surfacing, a task fires and the output channel is SMS (not just Gmail Drafts)
- Message formatter: thin wrapper that takes Hana's internal decision output and runs a short prompt pass ("summarize in 2-3 lines, conversational tone") before sending via Twilio

**Key architectural point:** SMS is just another output channel. Once Cloud Tasks is live in Sprint 4, SMS becomes a lightweight add-on. No separate architecture needed.

**Roadmap placement:** Sprint 5 or 6 as a small add-on. Tone/proactivity policy (how often, what triggers, style calibration) is a post-wiring tuning loop — does not need to be decided before build starts.

**Cost note:** Twilio SMS pricing is ~$0.0079/message outbound (US). At 30 messages/user/month, that is ~$0.24/user/month — not material. Add to cost model if SMS penetration is expected to be high.

---

## 2026-05-18 — CEO Scale Question: Is the 12-Sprint Roadmap Scale-Appropriate?

**Short answer: GCP stack is fine. Data model and per-user guardrails are the gaps.**

**What is already scale-appropriate:**
- Cloud Run, Firestore, GCS, Cloud Tasks — all managed services with no practical scale ceiling in our range.

**Critical gap — per-user Firestore namespace:**
- The current data model is single-user. Every collection needs a user namespace (`users/{uid}/emails`, etc.) or a `user_id` field with compound indexes before we accumulate large data volumes.
- Retrofitting this at 500 users with large collections is expensive. Must be locked by Sprint 4 design, codified in Sprint 5 hygiene. This is the most urgent structural risk.

**LLM cost at scale:**
- Already modeled: proactive checks drive ~$2.70/user/month. At 1K users = $2,700/month in API costs.
- Prompt caching on household context block is the highest-ROI mitigation. Target: Sprint 5–6. Must not slip past Sprint 6.

**Per-user rate limiting / circuit breakers:**
- No daily cap on outbound actions or LLM calls per user today. A scheduler bug could generate hundreds of SMS/LLM calls for one user.
- Lightweight per-user daily cap on task enqueue must ship with Cloud Tasks in Sprint 4, not later.

**Firestore query patterns:**
- Query auditing (composite indexes, no full-collection scans) should happen in Sprint 6 blueprint work, not as a Sprint 9 surprise.

**Cold starts:**
- Set Cloud Run min-instances=1 on production before mobile launch. ~$5–10/month. Not urgent until Sprint 10.

**Decision: No sprint reorder needed. Two targeted changes to Sprint 4:**
1. Lock the multi-user Firestore namespace schema during Sprint 4 planning.
2. Add per-user Cloud Tasks enqueue cap to Sprint 4 scope (small addition).

---

## 2026-05-18 — Pre-Sprint 4 CEO Confirmations

**Gmail Drafts path is live (not a stub):**
- CEO confirmed OAuth re-authorization for gmail.compose scope happened during Sprint 3.
- The Drafts wiring is real, working code. Sprint 4 can depend on it as a live capability.
- No stub-to-real migration cost to account for.

**Multi-user Firestore schema is a hard requirement from day one:**
- CEO confirmed: all Firestore paths must use the `users/{user_id}/` namespace from the start.
- Concrete example locked: `users/{user_id}/pending_actions/{action_id}`.
- Single-user shortcuts (flat collections, no uid prefix) are not permitted at any sprint.
- This aligns with and supersedes the earlier "lock by Sprint 4 design" note — it is now a zero-exception constraint, not just a planning target.
- All Sprint 4 schema design and code must use namespaced paths. Any existing code written with flat paths must be identified and corrected before Sprint 4 ships.

---

## 2026-05-18 — Sprint 4 Complete: Cloud Tasks, Firestore Namespace Lock, Enqueue Cap

### Files created or modified
- `/home/dcjohnston1/saucer/backend/task_queue.py` — new
- `/home/dcjohnston1/saucer/backend/db_schema.py` — new
- `/home/dcjohnston1/saucer/backend/pending_actions.py` — rewritten
- `/home/dcjohnston1/saucer/backend/main.py` — modified (two new endpoints, threading removed)
- `/home/dcjohnston1/saucer/backend/agent.py` — modified (user_id threading, Cloud Tasks wiring)
- `/home/dcjohnston1/saucer/backend/requirements.txt` — added google-cloud-tasks

### Architectural decisions

**Threading replaced with Cloud Tasks (two paths):**
The Pub/Sub email-trigger webhook previously used `threading.Thread` to run `process_single_email` in the background. This is fragile: if the Cloud Run container is recycled while the thread is running, the email goes unprocessed with no retry. Replaced with a Cloud Tasks enqueue targeting `/tasks/process-email`. Cloud Tasks handles retries with backoff.

The gmail_draft pending action now also enqueues a Cloud Tasks task (targeting `/tasks/handle-action`) immediately after the Firestore record is created. This closes the gap where Hana could create a Firestore record but the handler might never run.

**Confidence gate at runtime, not registry:**
The `ActionClass` registry `confidence` field is None for gmail_draft (intentional — the class-level confidence is unscored; individual invocations carry their own score). Rather than propagating None through, the `draft_reply_logged` function assigns 0.8 as the runtime confidence for actions the agent actually triggers. This is architecturally correct: the agent's decision to call `draft_reply` is the confidence signal. Future action types should follow the same pattern — pass a meaningful float, not None.

**OIDC verification: verify_oauth2_token not verify_firebase_token:**
Cloud Tasks sends OIDC tokens issued to a service account. The correct verification function from `google.oauth2.id_token` is `verify_oauth2_token` with the Cloud Run URL as the `audience`. `verify_firebase_token` is for Firebase user ID tokens and would reject Cloud Tasks calls.

**Firestore transaction on daily counter:**
The per-user daily counter uses a `@_firestore.transactional` decorator to atomically read-check-increment. Without this, two concurrent enqueue calls for the same user could both read count=N, both pass the cap check, and both write count=N+1. At current single-user scale this is low risk, but at multi-user scale it is not acceptable. Transaction cost: one extra roundtrip — negligible.

---

## 2026-05-18 — Sprint 5 Complete: Hygiene Cleanup

### Files modified
- `/home/dcjohnston1/saucer/backend/agent.py` — notes_consulted rebind + comment in all four _make_agent_* factories
- `/home/dcjohnston1/saucer/backend/main.py` — deleted 3 deprecated /proposals route handlers, 3 inline proposals attachment blocks, _topic_blocked, _load_blocked_topics_by_sender
- `/home/dcjohnston1/saucer/backend/email_scanner.py` — extracted _INTENT_VERDICT_RULES constant
- `/home/dcjohnston1/saucer/backend/prompts.py` — deleted ONBOARDING_SYSTEM_PROMPT
- `/home/dcjohnston1/saucer/backend/get_refresh_token.py` — added gmail.compose scope (Sprint 3 omission)

### Key decisions

**notes_consulted closure: no behavioral bug existed.**
The `list(notes_consulted)` snapshot at call-time is correct by design. `search_memory` appends to the shared list during the agent session; the snapshot captures what was accumulated. Added `_notes_ref` explicit rebind with comment in all four factories to make intent clear and prevent future misreading.

**_topic_blocked deletion — enforcement gap noted.**
The blocked_topics feature is half-built: CRUD routes and Firestore storage work, but `_topic_blocked` was never called from the email listing pipeline. Deleted both dead functions. The wiring gap should be addressed in a future sprint if the feature is still wanted. The intent was to call `_load_blocked_topics_by_sender(db)` in the email list routes and apply `_topic_blocked(email, by_sender)` as a filter. Easy to add when needed.

**Cloud Run revision: saucer-backend-00150-gmp**

**Fail-open on counter read error:**
If the Firestore transaction fails (network error, Firestore unavailable), `_check_and_increment_daily_counter` returns True (allows the enqueue) rather than False (blocks). Rationale: a transient Firestore error should not silently drop proactive work. The daily cap is a cost-control and UX dial, not a safety gate. If this reasoning is wrong (e.g. the cap is also rate-limiting a third-party API), change to fail-closed.

**Firestore namespace debt:**
The `emails` collection in `email_store.py` is still flat ('emails', not 'users/{user_id}/emails/'). It has 506+ live documents. Migrating it requires a dual-write phase and a backfill script — similar to what was done in Sprint 2 for the GCS-to-Firestore migration. This is the highest-priority namespace debt item. Tracked in db_schema.py. Target: Sprint 5.

All other flat collections (settings, user_actions, gemini_decisions, hana_notes, morning_briefings, etc.) are pre-Sprint-4 with their own migration cost. Documented in db_schema.py with rationale for deferral.

**Endpoint security note:**
Both `/tasks/handle-action` and `/tasks/process-email` verify the OIDC token audience against `CLOUD_RUN_URL`. If the Cloud Run URL is ever changed (e.g. custom domain), this env var must be updated, or the OIDC tokens will fail verification. This is a deploy-time concern, not a code concern.

### Pre-deploy CEO actions required
1. Deploy the new revision.
2. Grant `saucer-doc-service@mediationmate.iam.gserviceaccount.com` the `roles/run.invoker` role on the Cloud Run service (if not already granted). Without this, Cloud Tasks OIDC tokens will be rejected.
3. Create the `config/limits` Firestore document with `min_confidence_threshold` (float, e.g. 0.7) and `max_tasks_per_user_per_day` (int, e.g. 30). Without this document, the code uses hardcoded defaults — functionally fine but not operator-tunable.

---

## 2026-05-18 — Architecture Diagram Created

Generated `/home/dcjohnston1/saucer/team/architecture.png` — a visual overview of the Blueprint refactor target architecture.

**What the diagram shows:**
- Four horizontal layers (top to bottom): main.py entry point, routes/ blueprints, lib/ shared infrastructure, domain modules
- routes/ files distinguished by solid green (DONE: agent.py, tasks.py) vs dashed brown (PLANNED Sprint 7+: emails, calendar, files, filters, memory, admin)
- GCP services panel on the right: Cloud Run, Firestore, Cloud Storage, Cloud Tasks, Gmail/Pub-Sub, Cloud Scheduler
- Connector arrows from layers to the relevant GCP services they use
- Legend in the bottom-right corner

**Generation script:** `/home/dcjohnston1/saucer/team/gen_architecture.py` (matplotlib, 155 dpi PNG). Regenerate any time the target architecture changes.

---

## 2026-05-18 — CEO Question: Missing Features (Proposals + Email Summaries)

**Honest finding:** The `/proposals` routes and `scan_emails_for_todos` were deleted in Sprint 5 as a hygiene call, not a product decision. The frontend null-guard made them look safely removable. No CEO or PM sign-off was sought before removing user-visible capabilities. This was a process failure — engineering should have escalated before deleting features, not just dead routes.

**The "Checking for action items..." text in the current UI is a loading placeholder, not a replacement for either feature.** The backend analysis still runs but the result is not surfaced anywhere.

**Both features are product-aligned:**
- AI-generated gray preview text per email = ambient intelligence, reduces cognitive load without demanding attention. Directly serves Hana's core goal.
- Swipe-to-accept task extraction = low-friction path from email to task. Also directly serves the goal.

**Recommendation:** Restore both in Sprint 7 scope.
- Re-add `scan_emails_for_todos` logic (it existed; restore and wire to a per-email frontend gesture interaction).
- Surface the AI excerpt/summary text per email as it was before deletion.
- Process fix: before any future hygiene sprint deletes a route, confirm with PM whether the frontend feature it backs is still wanted.

---

## 2026-05-18 — Root Cause: Hana "Emily will help" hallucination bug (CEO huddle question)

**Verdict: Failure mode 2 — lifted email detail, not hallucination; follow-up query finds nothing because no action record exists.**

**Code path:** `run_morning_agent` (agent.py) builds a single monolithic system prompt that inlines the full email body alongside task-load, calendar, and household context, then calls `write_briefing(dan_message, emily_message)` with freeform strings. Gemini reads the email body — which mentions "Emily will be helping Julia get ready" — and synthesizes that into the briefing as though it were a Hana decision. No `add_todo` or `reassign_task` was called for Emily helping Julia; the mention was purely narrative from the sender. The `write_briefing` tool accepts any string, has no schema enforcing what counts as a Hana-decided fact vs. a reported email detail, and records no source attribution — it just writes `emily_message` and `dan_message` to Firestore as-is.

**Why the follow-up fails:** When the CEO asks "How did you decide Emily will help Julia?", `process_message` (mediator.py) calls `get_gemini_decisions` which queries the `gemini_decisions` Firestore collection. Because no `task_added` or `task_reassigned` record was ever created for Emily/Julia, the query returns nothing. Hana then correctly says she has no record — she doesn't. The briefing text that surfaced the detail is stored in `morning_briefings.emily_message` as a blob string, but `process_message` never queries `morning_briefings` and there is no search tool over briefing text. The two data stores are siloed with no join.

**The structural gap:** There is no enforcement in the briefing prompt distinguishing "what the email said" from "what Hana decided." AGENT_SYSTEM_PROMPT instructs Gemini to "tell each person what's relevant to them" without requiring that every person-specific assertion in the briefing correspond to a logged action. Gemini is free to narrate email content as settled fact in the briefing.

**Fix — two-part:**
1. Prompt change (immediate, no schema change): Add a rule to AGENT_SYSTEM_PROMPT that any person-specific task or assignment mentioned in the briefing MUST have a corresponding `add_todo` or `reassign_task` call earlier in the same run. Phrase it: "Only claim an assignment in your briefing if you called add_todo or reassign_task for it in this session." This is a soft guard — Gemini can still ignore it — but it closes most cases.
2. Structural change (Sprint 7 or Sprint 8 scope): Add a `briefing_assertions` array to the `write_briefing` tool schema — a list of structured claims (person, claim_type, text, source: 'email'|'hana_decision', linked_decision_id). When Hana narrates a detail from an email body, it must label it `source: 'email'`. When it reports its own action, it must link the decision_id. The follow-up chat handler can then query this array to distinguish "I read that in the email" from "I decided that." This is the correct long-term fix; the prompt change is a stopgap.

**Key files:**
- `/home/dcjohnston1/saucer/backend/agent.py` — AGENT_SYSTEM_PROMPT, `_make_write_briefing`, `run_morning_agent`
- `/home/dcjohnston1/saucer/backend/mediator.py` — `_make_get_decisions_tool`, `process_message` (no morning_briefings query here)
- `/home/dcjohnston1/saucer/backend/routes/agent.py` — `write_briefing` tool and `morning_briefings` Firestore collection

---

## 2026-05-18 — Root Cause: Grocery Preferences Note Contradiction Bug

**Verdict: Both. Prompt failure is the dominant cause; data model has a design gap that amplifies it.**

**What `save_note` actually does (memory.py lines 70-103):** When a note already exists, it reads the existing content from Firestore, calls `_gemini_merge()` (a separate Gemini invocation), and writes the merged result back. It does NOT blindly append. The `_gemini_merge` prompt explicitly says "Update any facts that have changed (use the newer version)" and "Do not duplicate information." This is the right design.

**Why contradictions still accumulate:** The merge is only as good as what Gemini can detect as contradictory. If the incoming `content` argument passed to `save_note` is phrased as a new fact ("Trader Joe's is used for most grocery shopping") without any explicit signal that it contradicts an existing fact, Gemini's merge prompt has no reason to discard the old statement. It sees two sentences that both sound factual and plausible, and keeps both. The merge model is not asked "does anything in NEW INFORMATION contradict EXISTING NOTE?" — it is only asked to "add new facts" and "update any facts that have changed." Gemini cannot reliably identify contradiction when both sides are stated as standalone truths.

**The prompt gap (dominant failure):** AGENT_SYSTEM_PROMPT and `save_note_tool` docstring in mediator.py give Hana no instruction to read the existing note before calling `save_note`. Hana calls `save_note('grocery preferences', 'Trader Joe's is used for most grocery shopping')` without ever calling `search_memory('grocery preferences')` first. So `_gemini_merge` is handed a rich existing note and a blunt new statement with no signal about which is authoritative. The merge falls back to keeping both.

**Fix — two-part:**
1. Prompt change (immediate): Add a rule to AGENT_SYSTEM_PROMPT and `save_note_tool` docstring: "Before calling save_note on a topic you may have noted before, call search_memory first. If you find an existing note that contradicts what you're about to write, state the correction explicitly in the content argument — e.g. 'Dan and Emily use Whole Foods, not Trader Joe's, for most shopping.' This helps the merge detect and remove the contradiction." This is a soft prompt guard; Gemini may still miss edge cases, but it closes the common path.
2. Strengthen the merge prompt (medium-term, low-risk code change in `_gemini_merge`): Add an explicit instruction: "If NEW INFORMATION contradicts a fact in EXISTING NOTE, remove the old fact and use the new one. Do not keep both versions of a contradictory statement." The current merge prompt says "Update any facts that have changed" but does not say "remove the old version." That omission is what causes both versions to survive. This is a 2-line fix in `_gemini_merge` and has no schema or infrastructure impact.

**Key files:**
- `/home/dcjohnston1/saucer/backend/memory.py` — `save_note`, `_gemini_merge` (the merge prompt is the code fix target)
- `/home/dcjohnston1/saucer/backend/mediator.py` — `save_note_tool` docstring (add the search-before-save instruction)
- `/home/dcjohnston1/saucer/backend/agent.py` — AGENT_SYSTEM_PROMPT (add the same instruction for the morning agent path)

---

## 2026-05-19 — Sprint 12 Item Assessment (Meeting Circle Round 1)

**Item 1 (filter bug): SMALL.** `get_cached_emails()` does not apply sender allowlist. One 10-line fix in `routes/emails.py`.

**Item 2 (swipe cards): SMALL.** Missing `fetch('/emails/scan-todos')` call on page load in `app.js`. Swipe-direction logic is a touch delta check.

**Item 3 (highlights on card): SMALL.** `source_spans` already in Firestore and on email doc. Ensure it's returned via cached route and rendered on card summary. Items 2, 3, 8 share the same fix path.

**Item 4 (auto calendar): MEDIUM.** `gcalendar.py` is production-ready including `source_email_id`. Need new `add_calendar_event` tool in `agent.py` + Gemini prompt instruction. Write inline inside `process_single_email`, not as a separate Cloud Tasks action.

**Item 5 (far-future events): SMALL, depends on Item 4.** One additional date-range filter in the frontend calendar view.

**Item 6: RESOLVED by CEO.** Option A (background trigger).

**Item 7 (calendar → source email): SMALL.** Frontend wiring only — render "View source email" button on event detail, call `/email/<id>/excerpt`, open excerpt drawer.

**Item 8 (to-do → highlight): SMALL, shares path with Items 2+3.** Unblocked once scan-todos auto-runs on load.

**Key check:** `GOOGLE_CREDENTIALS_JSON` env var in Cloud Run must be set for `gcalendar.py` to work. Coder should verify before Item 4 ships.

**Dependency order:** Item 1 independent. Items 2+3+8 together. Item 4 before Item 5. Item 7 frontend can ship independently.

---

## 2026-05-18 — To-Do Source Highlight Feature: Investigation Notes

**Feature request:** When a user taps a to-do and navigates to its source email, highlight the pertinent text (source_spans / excerpt).

**Finding: This is a SMALL feature. The backend is already 80% ready. The gap is one dead data path.**

**How to-dos store their source email reference:**
- Tasks are stored as pipe-delimited lines in a Google Doc via `gdocs.append_to_doc`. The `source_email_id` field is written into the line as `source_email_id:<gmail_id>`.
- `GET /doc` in `routes/emails.py` parses those lines and returns each task with a `source_email_id` field in the JSON payload.
- The frontend reads `task.source_email_id` and, if present, calls `GET /email/<id>/excerpt` to load the source email.

**What `/email/<email_id>/excerpt` returns:**
- Subject, sender, date, body (first 2000 chars of body or snippet).
- `source_spans`: a deduplicated list of verbatim phrase strings extracted from `saucer-proposals.json` — the file that `scan_emails_for_todos` (email_scanner.py) was intended to populate per-email.

**The broken link — source_spans is always empty:**
- `saucer-proposals.json` is read by the excerpt route but NEVER written anywhere in the current codebase. The Sprint 5 hygiene pass deleted the routes and scan logic that populated it, and no replacement write path was added. The GCS file either does not exist or is stale from a pre-Sprint-5 run.
- `scan_emails_for_todos` in `email_scanner.py` (lines 200-261) still exists and correctly generates `source_spans` per email_id, but nothing calls it and nothing writes its output to GCS.

**What the frontend already does correctly:**
- `_loadTaskSourceEmail(emailId)` fetches the excerpt and attaches a click handler to `openEmailExcerptDrawer(data)`.
- `openEmailExcerptDrawer` calls `_applyHighlights(bodyEl, email.source_spans)` if `source_spans` is non-empty. The highlighting infrastructure (`_highlightPhrase`, `_applyHighlights`) already works and is used for the email list view.
- The frontend passes no additional context when navigating from a to-do vs. the email list — it just calls the same excerpt endpoint. That is fine: the highlight data should come from the backend, not the frontend.

**What needs to change:**
The only missing piece is writing `source_spans` back to somewhere the excerpt route can read them. Two options:

1. Store spans in Firestore on the email document itself (cleanest long-term). Add a `source_spans` array field to the email record in `email_store`. Call `scan_emails_for_todos` when a to-do is accepted and write spans to the email document. The excerpt route reads from Firestore instead of `saucer-proposals.json`.

2. Restore the GCS write path (faster, lower-risk). When `scan_emails_for_todos` produces results (triggered from the to-do acceptance flow), write them to `saucer-proposals.json` in the same dict format the excerpt route already expects. No schema change to emails, no Firestore migration.

**Recommendation:** Option 1 (Firestore field on the email document) is the right long-term design — it avoids GCS as a second source of truth and survives multi-user namespace migration. Option 2 is a one-sprint patch that avoids touching email_store, acceptable if Sprint 7 scope is tight.

**Complexity: SMALL.** Frontend is complete. Backend excerpt route is complete. The only work is wiring `scan_emails_for_todos` output into persistent storage (either Firestore email field or GCS write) and ensuring the excerpt route reads from that storage. Estimated: 2-3 hours including a smoke test.

**Key files:**
- `/home/dcjohnston1/saucer/backend/email_scanner.py` — `scan_emails_for_todos` (lines 183-261), generates source_spans, needs a caller and a write path
- `/home/dcjohnston1/saucer/backend/routes/emails.py` — `get_email_excerpt` (line 903), reads saucer-proposals.json; needs to read from wherever spans are now stored
- `/home/dcjohnston1/saucer/backend/email_store.py` — `update_email_fields` is the write function if we go the Firestore route
- `/home/dcjohnston1/saucer/frontend/app.js` — `openEmailExcerptDrawer` (line 2990), `_applyHighlights` (line 34) — already correct, no changes needed

---

## 2026-05-20 — UX Bug Diagnosis: Three CEO-Reported Issues

### Issue 1 — "Checking for action items..." never resolves

**Root cause (1a — no-todos case):** `buildProposalsSection` in `app.js` (line 1117) renders "Checking for action items..." whenever `email.proposals` is `undefined` or `null`. The email objects returned by `GET /emails/cached` come from `email_store.list_emails()`, which reads Firestore email documents. The `proposals` field is **never set on Firestore email documents** — it has no write path anywhere in the backend. So every email always has `proposals === undefined`, and the loading state never resolves.

**Root cause (1b — known email with todos, nothing appears after 5 minutes):** When a new Gmail message arrives, Pub/Sub calls `/agent/email-trigger`, which enqueues a Cloud Task to `/tasks/process-email`, which calls `process_single_email`. That function runs the Gemini agent with an `add_todo_tool`, but `add_todo_tool` writes to a **Google Doc** (via `gdocs.append_to_doc`), not to the email's Firestore document. There is no step that populates a `proposals` field on the email record after the agent runs. The email card's proposals section therefore remains in loading state permanently. Additionally, `scan-todos` (the separate `/emails/scan-todos` endpoint) is only triggered manually via the scan button — it is not called automatically after `process_single_email` completes.

**Size: MEDIUM.** Two separate fixes. Fix 1a is a frontend guard (small — add a `null` check and render "No to-dos"). Fix 1b requires either: (a) wiring `scan_emails_for_todos` to run automatically after `process_single_email` and writing results to the email doc, or (b) writing extracted todos directly onto the email's Firestore doc inside `_make_agent_add_todo`. Option (b) is architecturally cleaner — the agent call that creates the to-do is the right moment to also record it on the source email document.

### Issue 2 — Action item renders as a text string, not a card

**Root cause:** This is a misread of which feature is broken. The `buildProposalRow` function (line 1150 in `app.js`) already renders full interactive swipeable cards with title, notes, date, and assignee buttons — it is correct. The `buildTodoProposalCard` function (line 3492) also renders swipeable cards in the scan-todos panel. Neither renders raw quoted strings. What the CEO is seeing is almost certainly the `buildProposalsSection` "Checking for action items..." state (Issue 1), not a broken card renderer. If `proposals` were populated correctly, the card infrastructure would render it properly. **Issue 2 is a symptom of Issue 1, not an independent bug.**

**Size: SMALL to NONE** as a standalone fix — it resolves when Issue 1 is fixed. If the CEO is seeing a quoted string somewhere else (e.g. in a chat response from Hana), that would be a different path worth investigating separately.

---

## 2026-05-20 — Sprint 14 Complete: Three P0 Bug Fixes

### Files modified
- `/home/dcjohnston1/saucer/frontend/app.js` — buildProposalsSection spinner text; draft section in buildEmailCard
- `/home/dcjohnston1/saucer/frontend/style.css` — 9 new .hana-draft-* CSS classes
- `/home/dcjohnston1/saucer/backend/agent.py` — add_todo_logged writes proposal entry to Firestore email doc; thread_id added to gmail_draft payload
- `/home/dcjohnston1/saucer/backend/gmail_scanner.py` — labelIds and thread_id added to email dicts from fetch_new_messages_since
- `/home/dcjohnston1/saucer/backend/routes/agent.py` — DRAFT filter before upsert_emails_batch
- `/home/dcjohnston1/saucer/backend/routes/emails.py` — pending_actions import + _DAN import; batch load + thread_id join in get_cached_emails()

### Architectural decisions

**Proposal write-back design (Bug 1b):**
The correct write point is inside `add_todo_logged`, immediately after the Google Doc write succeeds. Writing at the Cloud Task handler level (process_single_email) would require a second agent session read; writing at the route level would require passing the result back up. The inner function already has `source_email_id` in scope and uses `_email_store` (the module-level import alias). Shape locked to {id, title, notes, date_expression, source_spans: []} — matches buildProposalRow's p.id, p.title, p.notes, p.date_expression reads exactly. source_spans intentionally empty here; if a full scan-todos pass also runs, it will overwrite with real spans.

**Thread_id join strategy (Bug 2 Part 2):**
Single batch Firestore read of all pending gmail_draft actions, indexed in memory by thread_id. No per-email Firestore reads. This was the right call — the number of pending draft actions is bounded and small (typically 0-5); building a per-email index query would create an N-read pattern on the email list, which is already expensive. The in-memory join is O(N) on emails and O(1) lookup. Finance flagged this concern in the sprint kickoff; it was addressed at design time not after the fact.

**labelIds gap in gmail_scanner:**
fetch_new_messages_since was not including labelIds or thread_id in its returned email dicts. Both fields are present on the raw Gmail API message object (top-level keys, not in headers). The fix adds message.get('labelIds', []) and message.get('threadId', ''). Callers that don't need these fields are unaffected (they just ignore the extra keys). No migration needed — Firestore email docs already stored without these fields remain valid; the DRAFT filter only applies to emails being newly ingested.

**Draft section placement in buildEmailCard:**
Inserted between blockOverlay.appendChild and wrapper.appendChild(card) — after all card content is built, before the swipe wrapper is finalized. This is the correct placement: the draft section is appended to card (not wrapper), so it is inside the swipeable card boundary and not affected by the dismiss swipe listener which operates on wrapper.

### Revisions
- Backend: saucer-backend-00174-485
- Frontend: saucer-frontend-00127-zxt
- Git commit: f9d5350

---

## 2026-05-20 — Production Incident: Self-Email "to-do's" Dropped at Filter Gate

### Confirmed root cause: Branch A (intent evaluator blocked it) + normalization gap

**Log evidence:** `[email-trigger] excluded (verdict=blocked): to-do's` with `addr='dcjohnston1@gmail.com'`.

**Failure 1 — Gemini misclassified the self-email:**
The `evaluate_email_intent` prompt's PERMITTED SENDER RULE contained: "a data viz newsletter, retail promotion, or professional digest is blocked even if sent by a household member." Gemini classified a self-email task list as off-topic under the household intent and returned `verdict=blocked`. The SELF-EMAIL RULE was missing entirely from the prompt — there was no instruction telling Gemini that sender==recipient with action-item content is the strongest possible signal.

**Failure 2 — Permitted-sender shortcut did not fire:**
`_extract_sender_addr` called `.lower()` without `.strip()`. Firestore-stored addresses with trailing whitespace would not match the extracted address. The same gap in `sender_filters` and `blocked_senders` construction (no `.strip()` before adding to the sets). Result: even though `dcjohnston1@gmail.com` was in the allowlist, the comparison returned False, so neither the line-282 shortcut nor the `_is_excluded` line-333 guard fired correctly.

**Why it was recoverable:** `upsert_emails_batch` runs BEFORE the filter loop. The email was stored in Firestore with `verdict=blocked`. It was hidden by `list_emails(exclude_blocked_verdict=True)`, not lost. `/emails/resync` re-evaluates it with the new prompt and reclassifies it.

### Fixes applied (commit 681fe88, revision saucer-backend-00178-758)
- `email_scanner.py`: Added SELF-EMAIL RULE to `_INTENT_VERDICT_RULES` and `evaluate_email_intent` prompt preamble.
- `lib/email_helpers.py`: `_extract_sender_addr` now strips whitespace on both code paths.
- `routes/agent.py`: `.strip().lower()` on all Firestore address values before set construction. Structured DROP log lines at every drop point.
- `routes/emails.py`: `_run_intent_eval_batch` short-circuits permitted senders before Gemini call.

### Architectural note on the two-gate design
The current design evaluates intent THEN checks sender allowlist only as a content-eval bypass. The permitted shortcut should be the FIRST gate, not a shortcut inside the intent evaluator. The line-282 check is correct in principle but fragile because it depends on normalization being identical in two places. Future cleanup: centralize the permitted-sender check into a single `is_permitted_sender(email, permitted_set_trigger)` helper called once, before `evaluate_email_intent` is ever invoked. This was not fixed in this incident to keep the change minimal.

### Revised recovery finding
The email was NOT stuck in Firestore with `verdict=blocked`. Firestore showed `19e432019b4c6b9e` with `verdict=permitted` — a prior Pub/Sub delivery stored it correctly before the retried deliveries got a blocked in-memory verdict from Gemini. The email was hidden because it was in `saucer-dismissed.json` (the GCS dismissed list). Removed it from the dismissed list directly; email surfaced in the app immediately.

The `excluded (verdict=blocked)` log was from a RETRY delivery, not the initial one. On retry, `email_exists` returned True so the Firestore doc was not overwritten, but the in-memory blocked verdict was used by `_is_excluded` to suppress Cloud Task enqueuing (correct — the Cloud Task was already enqueued from the first delivery).

### New technical debt item noted
Why did the email land in `saucer-dismissed.json`? Possible paths: (1) Hana's `process_single_email` Cloud Task ran and some tool call dismissed it, (2) the CEO dismissed it, (3) there's an automated dismiss path that fires on certain conditions. The dismissed list should be append-only from explicit user gestures — no automated path should write to it. Worth auditing before Sprint 15.

### Backlog item added
`[BACKLOG-01] Gmail Watch Expiry Monitor` — Size S — added to `sprint_results.md` Backlog section.

---

## 2026-05-20 — Production Incident: 105 Emails Showing "Evaluation error" Badge

### Root cause
`google.generativeai` v0.8.6 on Cloud Run started falling back to ADC instead of `GOOGLE_API_KEY` for some Gemini API calls. The Cloud Run service account does not have `https://www.googleapis.com/auth/generative-language` scope, so every `batch_evaluate_emails_intent` call returned `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT`. All 729 emails were set to `verdict=uncertain` by the `/emails/resync` run at ~3:11 AM UTC.

### Fix
**email_scanner.py:** Migrated to `google.genai` (new SDK). Client initialized lazily via `_get_client()` using `genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))`. All five `GenerativeModel(...).generate_content()` call sites replaced with `_get_client().models.generate_content(model=..., contents=..., config=genai_types.GenerateContentConfig(...))`. New SDK never falls back to ADC when api_key is provided.

**requirements.txt:** Added `google-genai`. FutureWarning gone from boot sequence.

**routes/agent.py + routes/emails.py + email_scanner.py:** Added keyword fast-track everywhere a permitted-sender fast-track exists. Keyword-matched emails (`keyword_filters` doc in Firestore) are immediately `verdict=permitted` without a Gemini call. This makes them robust to any future Gemini API failure.

### Architectural note: resync timeout risk
`/emails/resync` runs synchronously. At 731 emails, it generates ~37 Gemini batch calls and approaches Cloud Run's 5-minute timeout. Future fix: convert to async Cloud Tasks job. Threshold for urgency: ~1,500-2,000 emails.

### Architectural note: new SDK import pattern
Other modules (`mediator.py`, `agent.py`, `conversation_history.py`, `routes/filters.py`, `routes/emails.py`) still use `google.generativeai`. They should be migrated to `google.genai` in a hygiene sprint before that SDK stops functioning. The email_scanner migration is the most urgent because it handles the batch resync path where failures have the largest blast radius. The other modules all use `genai.configure(api_key=...)` at module load, which should still work in v0.8.6 for now.

### Key files
- `/home/dcjohnston1/saucer/backend/email_scanner.py` — migrated to google.genai
- `/home/dcjohnston1/saucer/backend/requirements.txt` — added google-genai
- `/home/dcjohnston1/saucer/backend/routes/agent.py` — keyword fast-track added
- `/home/dcjohnston1/saucer/backend/routes/emails.py` — keyword fast-track added
- Git commit: a11b09a | Revision: saucer-backend-00181-l9w

---

## 2026-05-20 — CEO Screenshot: UX Observations (Huddle)

**Observed:** "No to-dos found" label under promotional/neighborhood-watch emails; red notification dots on all three filter tabs simultaneously.

**"No to-dos found" label:** Technically accurate (agent ran and found nothing) but product-wrong. Shows on emails that should never have triggered the agent at all. Recommendation: suppress the label entirely on emails where `proposals` is empty or null. Show nothing. "No to-dos found" implies effort and failure; blank implies correct triage.

**Red dots on all tabs:** All three tabs (This Week, To-Do's, Dismissed Emails) showing dots simultaneously is almost certainly a bug in the notification count logic in `app.js`. Suspect it is counting `emails.length` or a similar always-non-zero value rather than a delta or unread flag. Dismissed tab in particular should only dot when something is newly added to dismissed state.

**Backlog items to add:** (1) Suppress to-do label on emails with no proposals. (2) Fix notification dot logic per-tab. Both are SMALL.

---

## 2026-05-20 — Huddle: DeKalb Police alert in Dismissed (Designer trust flag)

**Question:** Should the Nextdoor / DeKalb County Police safety alert appear given current filters?

**Live filter state pulled from prod (us-east1):**
- email_intent: "School; extra-curriculars like ballet; summer camps; mental health; Scouts; City of Decatur; Village Walk; Ponce Primary"
- permitted senders (10): Procare, csdecatur, pestban, ACC, realm, etc. Nextdoor not present.
- keyword_filters (allow): infinite campus, glenwood, scout, 1st grade
- exclude_keyword_filters: goblins, "ai release"

**Verdict:** Filter behaved correctly. Nextdoor sender not in allowlist; content (neighborhood safety post) does not match the school/extracurricular intent; no keyword match. verdict=blocked → dismissed_by=hana → Dismissed view is the correct bucket. Same logic correctly blocked the Best Buy promo.

**Real bug Designer is seeing:** the "No to-dos found" label on filter-blocked emails. Hana never ran the to-do agent on these — the intent gate blocked them upstream. The label is a lie that erodes trust. Already on backlog from earlier today (suppress label when proposals is empty/null). Promote to next sprint.

---

## 2026-05-20 — Trust-Signal Pills on Email Cards (CEO huddle)

**Two new pills approved (no objections):**

1. **"Known sender" pill** — left of sender address, top of card. Shown when `verdict_reason == 'Sender is on the permitted list'`. Backend already writes this string. Pure frontend render in `buildEmailCard`. ~30 min.

2. **"Relevant topic: [X]" pill** — under subject line. Two source paths:
   - **Keyword match:** `_run_intent_eval_batch` and `batch_evaluate_emails_intent` already detect the matched keyword internally. Capture the specific matched string into a new `matched_topic` field on the email doc instead of the generic "Matches user keyword filter" reason. Small backend change.
   - **Freetext intent match:** Extend the Gemini JSON schema in `batch_evaluate_emails_intent` to require an additional `matched_topic` field (short phrase, e.g. "school", "scouts") when verdict=permitted. Additive field, no schema migration risk. ~5 extra output tokens per email — cost-negligible.

**Tech debt risk:** None. `matched_topic` is purely additive — old emails default to null/missing and frontend just hides the pill. No reverse-compatibility issue.

**Sizing:** Small-medium total. ~1-2 hours backend (schema + prompt update + write path in both `_run_intent_eval_batch` and `batch_evaluate_emails_intent`) + ~1 hour frontend (two pill renders, CSS). Lands cleanly in the next sprint.

**Files:**
- `/home/dcjohnston1/saucer/backend/email_scanner.py` — add `matched_topic` to verdict object
- `/home/dcjohnston1/saucer/backend/routes/emails.py` — write `matched_topic` alongside `verdict_reason`
- `/home/dcjohnston1/saucer/frontend/app.js` — `buildEmailCard` renders both pills
- `/home/dcjohnston1/saucer/frontend/style.css` — pill styles

---

### Issue 3 — Hana draft surfaces as a separate top-level email card

**Root cause:** When `draft_reply_tool` fires during `process_single_email`, it calls `gcalendar`/Gmail Drafts API to create a Gmail Draft. Gmail Drafts appear in the Gmail Drafts folder, but they also have a `DRAFT` label. The `gmail_scanner.scan_emails` / `fetch_new_messages_since` pipeline fetches messages — depending on how the Gmail API query is scoped, it may be picking up the draft as a new message and storing it in Firestore as a regular email record. When `/emails/cached` returns all stored emails, the draft surfaces alongside real emails with no visual distinction.

There is no `source_email_id` or `action_type` field being read by the frontend email card renderer — `buildEmailCard` in `app.js` treats every object from the emails array identically. The fix requires two things: (1) filter `DRAFT`-labeled messages out of the email store ingestion path (in `email_store.upsert_emails_batch` or the Pub/Sub handler), and (2) surface the draft inline on its source email card rather than as a top-level entry. The second part requires storing `thread_id` or `source_email_id` on the pending_actions record and joining it when building the email card.

**Size: MEDIUM.** Filtering drafts from the feed is a small backend fix (check for `DRAFT` label in `routes/agent.py` before `upsert_emails_batch`). The inline-on-card UX is the heavier lift: it requires the `gmail_draft` pending_action to carry a `source_email_id`, the `/emails/cached` route to join pending_actions by source email, and `buildEmailCard` to render a collapsible draft section when a pending_action of type `gmail_draft` is present.

### Dependencies

Issue 2 depends on Issue 1 — fix Issue 1 first. Issue 3 is independent of both. The draft filtering fix (part 1 of Issue 3) is safe to ship alone and immediately unblocks the feed from being polluted.

**Key files:**
- `/home/dcjohnston1/saucer/frontend/app.js` — `buildProposalsSection` (line 1117), `buildProposalRow` (line 1150), `buildEmailCard`
- `/home/dcjohnston1/saucer/backend/routes/emails.py` — `get_cached_emails` (line 389), `scan_todos` (line 949)
- `/home/dcjohnston1/saucer/backend/routes/agent.py` — `email_trigger` Pub/Sub handler, `upsert_emails_batch` call (line 289)
- `/home/dcjohnston1/saucer/backend/agent.py` — `process_single_email` (line 737), `_make_agent_add_todo`, `_make_agent_draft_reply`
- `/home/dcjohnston1/saucer/backend/pending_actions.py` — `enqueue_pending_action`, payload schema
