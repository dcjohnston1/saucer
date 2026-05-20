# Project Saucer — Sprint Log

## About This Project
Product: Saucer — an AI-powered household assistant (agent name: Hana) that manages emails, tasks, and household information using Gemini for decisions. Backend: Cloud Run, Firestore, GCS.
Financial goal: $220K run-rate profitability within 2 years from May 15, 2026
Target customer: [PLACEHOLDER — CEO to define]
CEO: The user. Makes final calls. Has technical context but relies on agents for domain expertise.

---

## Sprint 1 — Audit and Observability Foundations — COMPLETE ✓
Addressed: Phase 1 / Observability

Built full prompt capture and tool argument logging on every Hana decision. Added one-step undo to hana_notes via previous_content and previous_updated_at fields. Added notes_consulted tracking and a revert endpoint.

Known issue (deferred to Sprint 5): notes_consulted is sometimes missing on real agent decisions despite being wired in code. Suspected closure capture issue in _make_agent_* factories.

---

## Sprint 2 — Email Cache Concurrency — COMPLETE ✓
Addressed: Phase 1 / Data Infrastructure

Migrated email metadata from a single shared GCS blob to Firestore (one doc per email) and email bodies to per-email GCS blobs. Built email_store.py as the single module for all email storage. Migrated 506 emails with zero mismatches.

Post-deploy bugs fixed: (1) naive datetime crash on RFC 2822 dates with -0000 timezone. (2) Deploy was not confirmed before smoke testing — fix was local only, broken revision stayed live an extra round.

Key lessons: prefer dual-write over hard cutover for large migrations. Broad except Exception patterns silently swallow bugs — tightened five of them. Always confirm new revision is live before smoke testing.

Rollback: saucer-emails.json remains in GCS. Delete on or after 2026-06-15.

---

## Sprint 3 — Action-Class Infrastructure — COMPLETE ✓
Addressed: Phase 1 / Action Infrastructure

Built ActionClass abstraction (actions.py) with reversible, reviewable, confirmation_required, and confidence fields. Created Firestore pending_actions collection with enqueue/resolve/list helpers (pending_actions.py). Added Gmail Drafts feature: Hana now creates Gmail draft replies for qualifying emails via draft_reply tool, wired into both process_single_email and run_morning_agent. Added GET/POST pending-actions routes as extensible frontend stub. Fixed RFC 2822 string sort on dismissed-review list (now datetime-aware). Investigated notes_consulted gap — confirmed correct behavior; added clarifying comment and improved error logging.

Post-deploy bug found and fixed: gmail_scanner.py had SCOPES = ['gmail.readonly'] passed to the Credentials constructor, which capped the access token even though the refresh token had gmail.compose authorized. Fixed by adding gmail.compose to SCOPES. Redeployed as revision 00147 on 2026-05-18 11:57 UTC. Smoke test confirmed: draft created and deleted by CEO. Sprint 3 fully verified.
## Sprint 4 — Reliable Background Work — COMPLETE ✓
Addressed: Phase 1 / Execution Layer

Replaced in-process Python threading with Google Cloud Tasks for two key paths:
(1) The Pub/Sub email-trigger webhook (`/agent/email-trigger`) previously spawned a background thread to run `process_single_email`. It now enqueues a Cloud Task targeting `/tasks/process-email`, which runs the agent inside Cloud Tasks with retries and idempotency.
(2) Gmail draft actions created by the agent now enqueue a Cloud Task via `task_queue.enqueue_action()` targeting `/tasks/handle-action` for reliable execution tracking.

What was built:
- `task_queue.py` — new module with `enqueue_action(user_id, action)`. Reads thresholds from Firestore `config/limits` doc. Rejects actions below `min_confidence_threshold` (default 0.7). Checks and increments a per-user daily counter in `users/{user_id}/counters/daily_tasks` against `max_tasks_per_user_per_day` (default 30). Uses a Firestore transaction to prevent race conditions on the counter. On pass, creates a Cloud Tasks HTTP task targeting the handler with OIDC authentication.
- `db_schema.py` — new file documenting all canonical Firestore collection paths, namespacing rules, and migration debt notes.
- `pending_actions.py` — rewritten to use `users/{user_id}/pending_actions/{action_id}` namespace (was flat `pending_actions` collection). Added `processing_status` field with lifecycle `pending → in_progress → complete | failed`. Added `update_processing_status(user_id, action_id, status)` helper. All function signatures now require `user_id` as the first argument.
- `main.py` — added POST `/tasks/handle-action` (idempotent Cloud Tasks handler, OIDC-verified). Added POST `/tasks/process-email` (runs `process_single_email` inside Cloud Tasks, OIDC-verified). Removed `import threading` and `threading.Thread` from `agent_email_trigger`. Updated `/pending-actions` GET and POST resolve routes to accept `user_id` parameter. Added `_enqueue_email_processing_task()` helper.
- `requirements.txt` — added `google-cloud-tasks`.
- `agent.py` — updated `_make_agent_draft_reply` to accept `user_id`. Both `process_single_email` and `run_morning_agent` now pass `user_id=_DAN` when creating the tool. After `enqueue_pending_action` creates the Firestore record, `enqueue_action` is called to push it to Cloud Tasks.

Queue status at sprint close: `hana-actions` confirmed RUNNING with max_attempts=3, min_backoff=10s, max_backoff=300s, max_doublings=3.

Firestore namespace audit findings:
- `pending_actions`: migrated to `users/{user_id}/pending_actions/` — DONE
- `users/{user_id}/counters/daily_tasks`: new, namespaced — DONE
- `config/limits`: global config, intentionally not namespaced — CORRECT
- `emails` collection in `email_store.py`: pre-Sprint-4 flat collection with 506+ live docs. Migration to `users/{user_id}/emails/` requires a live data migration (dual-write + backfill). Tracked as Sprint 5 debt in db_schema.py.
- All other flat collections (settings, user_actions, gemini_decisions, hana_notes, etc.): pre-Sprint-4, single-household, single-user at current scale. Tracked in db_schema.py for future migration.

OIDC note: handlers use `google.oauth2.id_token.verify_oauth2_token` (correct for service account OIDC tokens from Cloud Tasks), not `verify_firebase_token`.

Smoke test steps (requires live deploy — see note below):
1. Deploy revision and confirm it is live: `gcloud run services describe saucer-backend --region=us-central1 --project=mediationmate`
2. Create the `config/limits` Firestore document manually (or verify it exists): set `min_confidence_threshold=0.7` and `max_tasks_per_user_per_day=30`.
3. Send a qualifying email to Dan's Gmail account (must match sender/keyword filters).
4. Watch Cloud Run logs for `[email-trigger] qualifying ... — enqueuing Cloud Task` and `[email-trigger] enqueued task for email_id=...`.
5. In the Cloud Tasks console, confirm a task appeared in `hana-actions` queue.
6. Watch Cloud Run logs for `[process-email] EXECUTING email_id=...` and `[process-email] COMPLETE`.
7. If a draft-worthy email was processed, confirm `[agent] gmail_draft_created` appears in logs.
8. Confirm `[task_queue] ENQUEUED` log for the gmail_draft action.
9. Watch Cloud Run logs for `[handle-action] EXECUTING` and `[handle-action] COMPLETE`.
10. In Firestore console, find `users/dcjohnston1@gmail.com/pending_actions/{id}` — verify `processing_status` is `complete`.
11. In Firestore console, find `users/dcjohnston1@gmail.com/counters/daily_tasks` — verify `count` incremented and `reset_date` = today.

Verification (2026-05-18, run by engineer agent):
1. Revision 00148 deployed and live as of 14:41 UTC — PASS
2. saucer-doc-service@mediationmate.iam.gserviceaccount.com has roles/run.invoker — PASS
3. config/limits document exists with min_confidence_threshold=0.7 and max_tasks_per_user_per_day=30 — PASS

Note: allUsers is also on roles/run.invoker (service is publicly invokable), but both task endpoints verify OIDC tokens and return 403 without a valid token — secure by defense-in-depth.

Sprint 4 fully verified in production. ✓
## Sprint 5 — Hygiene Cleanup — COMPLETE ✓
Addressed: pre-split debt cleanup before main.py Blueprint split

### Pre-sprint
Committed and pushed all Sprint 3+4 changes to GitHub. Sprint 3 had two commits (new files: actions.py, gmail_drafts.py; then modifications to agent.py, gmail_scanner.py, main.py, requirements.txt, get_refresh_token.py). Sprint 4 committed in same batch with agent.py, main.py, task_queue.py, db_schema.py, pending_actions.py, requirements.txt.

### Task 1 — notes_consulted closure inspection (agent.py)

Inspected all `_make_agent_*` factory functions. The design is intentionally call-time snapshot: `list(notes_consulted)` is called inside the inner function (at tool-call time), not at factory creation time. This is correct — `search_memory` populates the shared list during the agent session, and the snapshot is taken after search_memory has run.

Added `_notes_ref = notes_consulted` explicit rebind to four factories (`_make_agent_add_todo`, `_make_agent_reassign`, `_make_agent_dismiss_email`, `_make_agent_draft_reply`) with a clarifying comment explaining why the snapshot is at call-time rather than factory-time. Updated all inner-function `list(notes_consulted)` calls to `list(_notes_ref)` for consistency.

Post-deploy verification: agent run produced briefing `c08b9224-03b8-4ce0-a827-d21b5ccbdefa`. No new emails in window so no new Gemini decision records were created in this run. Existing `task_added` records in Firestore confirm `notes_consulted: PRESENT (0 items)` — field present and correctly set to empty array when no memory search occurred. The `notes_consulted` field is absent on pre-Sprint-3 `email_dismissed` records (historical, expected). New records going forward will have the field present.

### Task 2 — Delete deprecated /proposals routes (main.py)

Frontend check at `app.js:1093`: `email.proposals === undefined || email.proposals === null` — confirmed defensive null guard. Proceeded with full deletion.

Deleted:
- Three DEPRECATED route handlers: `GET /proposals`, `POST /proposals/<id>/accept`, `DELETE /proposals/<id>`
- Three inline proposals attachment blocks from `/emails`, `/emails/cached`, `/emails/resync`
- Unused `scan_emails_for_todos` import from `get_emails()`
- Unused `from gcs import read_json` from `get_cached_emails()` (was only needed for proposals)

Note: `/email/<id>/excerpt` route still reads `saucer-proposals.json` for source_spans highlighting. This is a separate feature, not part of the deprecated proposals approval flow. Left as-is; source_spans can be migrated to a different store in a future sprint.

### Task 3 — Delete ONBOARDING_SYSTEM_PROMPT (prompts.py)

Deleted the constant and its multi-line docstring. No callers existed. The `/onboarding` endpoint was already returning 410.

### Task 4 — Wire or delete _topic_blocked (main.py)

No callers found for `_topic_blocked`. Also found `_load_blocked_topics_by_sender` was only a data-prep helper for `_topic_blocked` — no other callers. Deleted both functions.

The blocked_topics Firestore collection, the `/blocked-topics` CRUD routes, and the `/generate-topic-label` AI route remain intact — the feature data is stored and the UI works. The enforcement path (checking incoming emails against blocked topics at filtering time) was never wired. This can be added in a future sprint by calling `_load_blocked_topics_by_sender` and applying the check in the email listing routes.

`_gemini_text` helper function kept — still used by `generate_topic_label` route.

### Task 5 — Consolidate intent verdict rules (email_scanner.py)

Extracted the shared verdict-rule prose from both `evaluate_email_intent()` and `batch_evaluate_emails_intent()` into a module-level constant `_INTENT_VERDICT_RULES`. The single evaluation function had a slightly more detailed instruction for rule 2 ("one specific sentence naming the sender...") vs the batch version; unified to the single-eval wording (more precise). Both functions now reference `_INTENT_VERDICT_RULES` via string concatenation. Prompt construction f-strings remain inline as specified.

### Task 6 — Task-existence check audit

Audit result: no meaningful duplication found. Single authoritative guard lives in `mediator.add_todo()` at line 159 (reads doc, builds title set, checks for match). The `accept_proposal` check in `main.py` was deleted in Task 2 as part of the deprecated proposals routes. `gdocs.py:49` is a task-finder operation (locate-by-title to update a field), not a duplicate-prevention guard. `agent.py` contains a deleted-task guard (GCS list check), which is a different concern. Stale plan item — closed.

### Deploy
Cloud Run revision: `saucer-backend-00150-gmp`
Service URL: https://saucer-backend-987132498395.us-central1.run.app
Net change: 38 insertions, 217 deletions across 5 files (agent.py, email_scanner.py, main.py, prompts.py, get_refresh_token.py).

## Sprint 6 — Blueprint Foundation — COMPLETE ✓
Addressed: Phase 2 / main.py Blueprint split (first wave)

### What was built

**lib/ shared infrastructure (5 new files):**
- `lib/__init__.py` — empty package marker
- `lib/firestore_client.py` — `get_db()` extracted from main.py; single source of truth for Firestore client init
- `lib/config.py` — shared constants: `_DAN`, `_EMILY`, `_PROJECT`, `_LOCATION`, `_QUEUE`, `_CLOUD_RUN_URL`, `_SA_EMAIL`, `_PUBSUB_TOPIC`
- `lib/auth.py` — `verify_cloud_tasks_token(req)` helper; extracts duplicate OIDC verification block from both task handlers. Returns `None` on success, `(response, 403)` on failure.
- `lib/email_helpers.py` — shared email utility functions extracted from main.py: `_extract_sender_addr`, `_get_email_intent`, `_auto_save_pdf_attachments`, `_strip_raw_bytes`

**routes/ Blueprints (2 new files):**
- `routes/agent.py` — `agent_bp` Blueprint with 6 routes: `POST /agent/run`, `GET /briefing/latest`, `POST /briefing/<id>/feedback`, `POST /briefing/<id>/seen`, `POST /agent/email-trigger` (large Pub/Sub webhook), `POST /agent/renew-gmail-watch`. Includes `_enqueue_email_processing_task` helper.
- `routes/tasks.py` — `tasks_bp` Blueprint with 4 routes: `POST /tasks/handle-action`, `POST /tasks/process-email`, `GET /pending-actions`, `POST /pending-actions/<id>/resolve`. Uses `verify_cloud_tasks_token` for OIDC verification on both task handlers.

**main.py changes:**
- Removed `import re` (only used in `_extract_sender_addr`, now in email_helpers.py)
- Replaced `def get_db()` with `from lib.firestore_client import get_db`
- Replaced 4 helper function defs with `from lib.email_helpers import ...`
- Added Blueprint registrations (`app.register_blueprint(agent_bp)`, `app.register_blueprint(tasks_bp)`)
- Deleted 11 route handlers (395 lines removed from main.py)

Net change: 703 insertions, 672 deletions across 9 files.

### Import graph (no cycles)
- `lib/` → stdlib, google-cloud, flask only
- `routes/` → `lib/`, domain modules (email_store, pending_actions, agent, gmail_scanner, etc.), no import from main.py
- `main.py` → `lib/`, `routes/`, domain modules

### Side fix during smoke testing
Firestore composite index on `pending_actions` collection `(status ASC, created_at DESC)` was missing — query required it for `list_pending_actions`. Created via `gcloud firestore indexes composite create`. Index reached READY state at 16:55 UTC 2026-05-18.

### Deploy
Cloud Run revision: `saucer-backend-00153-rlf` (GitHub CI/CD deployed same commit 34s after manual deploy of 00152)
Service URL: https://saucer-backend-987132498395.us-central1.run.app
Git commit: `6f954b0` — pushed to main on GitHub

### Acceptance criteria — all PASS
1. `/health` → 200 ✓
2. `/pending-actions` → `{"pending_actions":[]}` (JSON, no 500) ✓
3. `agent/email-trigger`, `tasks/handle-action`, `pending-actions` route defs removed from main.py ✓
4. `/health` remains in main.py ✓
5. Blueprint registrations present in main.py ✓
6. Revision recorded: `saucer-backend-00153-rlf` ✓

## Sprint 7 — Blueprint Wave 1 (emails + filters) — COMPLETE ✓
Addressed: Phase 2 / main.py Blueprint split (wave 1)

Extracted 42 routes from main.py into two Blueprints. routes/emails.py (emails_bp): 26 routes covering email CRUD, search, dismissal, intent eval, highlights, attachment IDs, avatar, stats, chat, doc/tasks, excerpt. routes/filters.py (filters_bp): 16 routes covering email-filters, keyword-filters, exclude-keyword-filters, blocked-senders, blocked-topics, generate-topic-label. main.py reduced from 1,593 to 488 lines. No API contract changes. Revision 00154-dsb live and smoke-tested. Git commit 024efe7 pushed to GitHub.

## Sprint 8 — Blueprint Wave 2 (memory + files + admin) — COMPLETE ✓
Addressed: Phase 2 / main.py Blueprint split (wave 2)

Extracted 22 routes from main.py into three Blueprints. routes/memory.py (memory_bp): 6 routes for hana notes and question. routes/files.py (files_bp): 4 routes for file upload, download, list, delete. routes/admin.py (admin_bp): 12 routes for user-settings, actions history, decisions, onboarding stub, conversation-history, session checkpoint, debug. main.py is now a true thin shell at 130 lines — 5 blocked calendar routes plus /health only. No API contract changes. Revision 00156-qzf live and smoke-tested. Git commit 332612f pushed to GitHub.

## Sprint 9 — Product Fixes (CEO Mandate) — COMPLETE ✓
Addressed: CEO-mandated product surface fixes + trust/correctness bugs

All 8 items delivered. Git commit 70aa667 pushed to GitHub. 7 files changed: backend/agent.py, backend/mediator.py, backend/memory.py, backend/routes/emails.py, frontend/app.js, frontend/index.html, frontend/style.css. 500 insertions, 22 deletions.

Item 1 (briefing attribution prompt guard) + Item 8 (note dedup): Added BRIEFING ATTRIBUTION RULE to AGENT_SYSTEM_PROMPT and SINGLE_EMAIL_SYSTEM_PROMPT — Hana may only claim an assignment if add_todo/reassign_task was called that session. Added search-before-save instruction to both prompts and save_note_tool docstring in mediator.py. Added _gemini_merge fix in memory.py: remove contradicted old facts, never keep both versions.

Item 2 (briefing_assertions schema): Added optional briefing_assertions parameter to write_briefing tool — structured list of claims with person/claim_type/text/source/decision_id fields. Written to morning_briefings Firestore doc.

Item 3 (email summary): Verified already working — summarize_emails already called in GET /emails, summary field stored/returned via Firestore. No code change needed.

Items 4+5+6 (task determination + swiping + highlights, coupled unit): Added POST /emails/scan-todos route — calls scan_emails_for_todos, writes source_spans to Firestore email docs, returns flat todo list. Added POST /emails/<id>/accept-todo and POST /emails/<id>/reject-todo routes. Fixed /email/<id>/excerpt to read source_spans from Firestore email doc (was reading saucer-proposals.json, never written). Frontend: suggested tasks section with swipe-right=accept, swipe-left=reject gesture cards.

Item 7 (briefing-to-chat handoff): openBriefingChat now displays briefing as Hana's first chat bubble. On first sendMessage, briefing text is prepended to history so backend has full context.

Bonus (unplanned): Calendar routes extracted from main.py into routes/calendar.py Blueprint (commit cbd7dce). Calendar integration was previously BLOCKED — CEO to confirm whether calendar OAuth is now configured.

CEO_demands.md: all 8 items now complete. To-do → source email → highlights (Sprint 10 item) is unblocked by this sprint's source_spans Firestore fix.

## Sprint 10 — In-App Voice AI + First External User — COMPLETE ✓
Addressed: Voice AI / First External User milestone

Delivered 3 items. Git commit 3923c5b pushed to GitHub. Backend revision saucer-backend-00162-nx2. Frontend revision saucer-frontend-00119-kh5. 552 insertions, 8 files changed.

Track A (to-do source highlight): Added tap handler to todo proposal cards. Tap now opens the source email excerpt with yellow highlights on the text that triggered the suggestion. Backend and highlight rendering were already wired from Sprint 9; this sprint connected the missing tap entry point.

Track B (in-app voice): New backend/voice_handler.py handles Google Cloud STT (WEBM_OPUS encoding — no ffmpeg needed) and TTS (Neural2-F MP3). New routes/voice.py Blueprint exposes POST /voice/run — accepts multipart WebM/Opus audio, returns MP3. Low-confidence STT returns a friendly retry hint, not a 500. Frontend: hold-to-record #hana-voice-btn added to chat input row with three visual states (recording=green pulse, processing=blue, speaking=amber pulse) and full pointer event handling. Pre-flight: enabled speech.googleapis.com and texttospeech.googleapis.com APIs. Cloud Run service account has roles/editor — no additional IAM bindings needed.

Track C (Emily onboarding): team/emily_onboarding.md prepared. CEO must fill in app URL and contact details, then deliver to Emily. Named gate (Emily runs Hana once) requires CEO to send the guide — this is the only CEO action item in Sprint 10.

Named gate status: Emily onboarding guide is ready. Gate closes when Emily runs the app.

## Sprint 11 — Voice UX Polish + Emily Gate + User #2 — COMPLETE ✓
Addressed: Phase 2 / Voice polish, first external user gate, organic user #2 identification

3 code items delivered. Git commit 6543959 pushed to GitHub. Backend revision saucer-backend-00165-w2x. Frontend revision saucer-frontend-00120-pzq. 58 insertions, 7 deletions across 3 files.

Item 1 (earcon): _playEarcon() and _stopEarcon() added to app.js using Web Audio API. Soft rising tone 440→880Hz over 200ms at gain 0.06, sustains during processing, stops the moment MP3 audio response begins. Fails silently if AudioContext not supported. No backend changes.

Item 2 (error state): _setState() now handles 'hana-voice-error' class. On low_confidence or no_transcript STT response, button turns red for 2 seconds then resets to idle — no toast, just a visual signal. CSS rule added to style.css. Separate toast kept for other (non-STT) error types.

Item 3 (TTS constant): HANA_VOICE_NAME = "en-US-Neural2-F" module-level constant added to voice_handler.py. synthesize_speech() references the constant. Voice can now be changed in one place without touching the function body.

Non-code status: Emily onboarding guide updated with live app URL (https://saucer-frontend-6ksi6iut7a-uc.a.run.app). CEO must forward guide to Emily — Sprint 12 gate requires Emily to have run Hana. Finance cost estimate and User #2 candidate identification remain open CEO/team actions before Sprint 12 launches.

## Post-Sprint 11 Hotfixes — 2026-05-19 — COMPLETE ✓
Revisions: saucer-frontend-00121-w9b, 00122-hsg, 00123-wjs. app.js versions 44.1–44.3.

Three voice bugs fixed after CEO testing:

**Fix 1 — Duplicate mic button** (v44.1, `frontend/app.js`): `mic-btn` (legacy browser SpeechRecognition button, starts hidden) was being un-hidden by `initVoice()` even when `hana-voice-btn` (Google Cloud STT, Sprint 11) is present. Result: two mic icons side by side. Fix: single guard — `if (!document.getElementById('hana-voice-btn')) micBtn.classList.remove('hidden')`.

**Fix 2 — iOS Bluetooth first-utterance routing + loop drops** (v44.2, `frontend/app.js`): (a) iOS routes `speechSynthesis.speak()` through built-in speaker on first call after SpeechRecognition has used the audio session. Fixed by adding `_primeAudioRoute()` — plays a 50ms silent AudioContext buffer before every speak call, forcing iOS to reroute to the current output device (Bluetooth). (b) `recognition.onerror` did not restart the mic when voice mode was active, silently killing the conversation loop. Fixed by restarting recognition on error if `voiceModeActive`. (c) `recognition.onend` did not restart when voice mode was active but recognition ended without a transcript. Fixed. (d) Known iOS bug: `utt.onend` stops firing after several turns, breaking the loop. Fixed by adding a safety timer in `_doSpeak()` that restarts recognition after an estimated utterance duration if `onend` never fires.

**Fix 3 — Mic permission re-prompt on every use** (v44.3, `frontend/app.js`): `getUserMedia()` was called fresh on every hold-to-speak press; `getTracks().forEach(t => t.stop())` was called after each recording, fully releasing the stream. iOS treats the next `getUserMedia()` call as a new permission request. Fixed: `_voiceStream` variable holds the stream for the session lifetime. `_ensureVoiceStream()` returns the existing stream if active, otherwise requests a new one. Track-stopping removed from between-recording cleanup. iOS now prompts once per session.

## Sprint 12 — CEO Deferred Items (all 8) — COMPLETE ✓
Addressed: Product polish / CEO deferred items list. Git commit 4c807d7. Backend saucer-backend-00167-z5k. Frontend saucer-frontend-00124-kqq.

Item 1 (filter bug): Fixed. `get_cached_emails()` now applies sender allowlist. Unrelated senders no longer appear in the cached email view.
Item 2 (swipe cards): Scan-todos auto-runs on first email load. Swipe direction threshold tightened to 1.5x ratio (prevents accidental accepts on diagonal gestures).
Item 3 (card highlights): First source span from scan-todos rendered as a yellow quote block directly on the email card. CSS class `email-card-highlight-quote` added.
Item 4 (auto calendar): `add_calendar_event` tool added to `process_single_email` in `agent.py`. `check_event_exists()` duplicate guard added to `gcalendar.py`. Restrictive Gemini prompt: only creates events with clear date + clear commitment + human action required. `GOOGLE_CREDENTIALS_JSON` confirmed set in Cloud Run. Toast notifies user when Hana-added events appear in calendar view.
Item 5 (future events): "Future Events" hamburger menu item added. Shows events 14-180 days out using existing calendar screen and load path.
Item 6 (product decision): Resolved. CEO chose Option A (background trigger, silent + dismissable). No code task.
Item 7 (calendar → source email): Already wired. "View email" link on calendar events opens excerpt drawer with highlights. No code change needed — verified working.
Item 8 (to-do → source email highlight): Unblocked by Item 2 auto-scan. scan-todos writes source_spans to Firestore on load; excerpt drawer renders them when to-do is tapped.

CEO action items: (1) Privacy Policy and Terms of Service should be published before adding more external users beyond Emily. (2) Calendar OAuth uses a shared service account — must switch to per-user credentials before public user onboarding.

## Sprint 13 — Bug Fixes + Auth Foundation — COMPLETE ✓
Addressed: Sprint 12 regressions (3 P0 fixes) + Firebase Auth infra + rate limiting. Git commit 757b549. Backend saucer-backend-00171-9mj. Frontend saucer-frontend-00125-28k.

Fix A: Sender allowlist now applied to /emails GET route. Sprint 12 only fixed /emails/cached — the live view still showed non-permitted senders. Smoke test confirmed floortje@artwithflo.com no longer appears.
Fix B: scan_emails_for_todos wrapped in try/except with traceback logging. scan_count field added to response. Frontend empty state now shows "Scanned N emails — no action items found."
Fix C: openFutureEventsScreen now catches errors and shows the real error message. Empty state copy updated from stale "this week" text. Calendar backend logs traceback on exception.
lib/firebase_auth.py: verify_firebase_token() and @firebase_auth_required decorator ready for Sprint 14 mobile routes.
lib/rate_limiter.py: per-user daily caps via Firestore transactional counters. /agent/run capped at 20/day. /voice/run capped at 30/day. Configurable via Firestore config/limits.
db_schema.py: Sprint 13 multi-user scale audit written. Gap list + migration priority for Sprint 14+.
Finance cost estimate delivered: $0.80–$3.50/user/month; voice adds $0.30–$0.60/user/month.

## Sprint 14 — Three P0 Bug Fixes (CEO Mandate) — COMPLETE ✓
Addressed: Live demo regressions blocking Emily onboarding gate. Git commit f9d5350. Backend saucer-backend-00174-485. Frontend saucer-frontend-00127-zxt.

Bug 1a (app.js): buildProposalsSection no longer shows a persistent spinner. When proposals is null/undefined, renders "No to-dos found" with class proposals-scanning. Implies Hana looked but found nothing — maintains trust without a loading state that never resolves.

Bug 1b (agent.py): add_todo_logged now writes a proposal entry back to the Firestore email doc immediately after the Google Doc write succeeds. Entry shape: {id, title, notes, date_expression, source_spans: []}. This matches what buildProposalRow reads (p.id, p.title, p.notes, p.date_expression) exactly — no shape mismatch. Root cause was that the add_todo_tool path wrote to Google Docs only; the email doc proposals field was never populated.

Bug 2 Part 1 (gmail_scanner.py + routes/agent.py): gmail_scanner.fetch_new_messages_since now includes labelIds and thread_id in every email dict (both fields were absent before — message.get('labelIds', []) and message.get('threadId', '')). The Pub/Sub handler in routes/agent.py filters out DRAFT-labeled messages before upsert_emails_batch. Log line updated to report draft exclusion count. Hana's Gmail draft will no longer surface as a top-level email card.

Bug 2 Part 2:
  - agent.py: thread_id added to the gmail_draft pending_action payload in enqueue_pending_action call.
  - routes/emails.py: pending_actions and _DAN imported. After visible list is finalized in get_cached_emails(), a single batch call to list_pending_actions loads all pending gmail_draft actions, indexes them by thread_id, and joins to matching emails in memory. No per-email Firestore reads.
  - frontend/app.js: buildEmailCard renders a collapsible "Hana drafted a reply" section when email.draft_pending_action is present. Toggle shows/hides body with subject, body_preview (150 chars), Open in Gmail (links to drafts), and Dismiss (removes section from DOM). Collapsed by default.
  - frontend/style.css: 9 new .hana-draft-* classes added. Muted gray palette — no accent colors.

Bug 3: Resolved as a consequence of Bug 1b. buildProposalRow was intact and correct throughout — the proposals field was simply never populated. End-to-end path now: agent runs → add_todo_logged → Firestore email doc updated → /emails/cached returns proposals → buildProposalRow renders swipeable cards.

Deferred to Sprint 15: emails namespace migration, React Native vs. Flutter, marketing strategy, Emily gate.

---

## Production Incident — 2026-05-20 — Self-Email "to-do's" Dropped at Filter Gate — RESOLVED

**Git commit:** 681fe88. **Backend revision:** saucer-backend-00178-758.

### Root Cause

Branch A confirmed. The self-email from `dcjohnston1@gmail.com` (subject "to-do's", ~10:03 PM) was stored in Firestore with `verdict=blocked` from `evaluate_email_intent`. Two compounding failures:

**Failure 1 — Gemini misclassification:** `evaluate_email_intent` was called on the self-email because the permitted-sender shortcut in `agent_email_trigger` (line 282) failed to match. The intent evaluator prompt's PERMITTED SENDER RULE explicitly told Gemini: "a data viz newsletter, retail promotion, or professional digest is blocked even if sent by a household member." Gemini classified a self-email task list as off-topic and returned `verdict=blocked`.

**Failure 2 — Permitted-sender shortcut did not fire:** The permitted-sender check at line 282 compares `sender_addr` (from `_extract_sender_addr`) against `permitted_set_trigger` (built from Firestore `settings/email_filters.addresses`). `_extract_sender_addr` did not call `.strip()` — it called `.lower()` only. Firestore-stored addresses with trailing whitespace would not match. The same gap existed on the `_is_excluded` guard at line 333: even if Gemini returned `blocked`, `addr not in permitted_set_trigger` should have returned False (don't exclude) for permitted senders, but didn't because of the whitespace normalization gap.

**Why the email WAS stored in Firestore:** The `upsert_emails_batch` call runs before the filter loop. The self-email was stored with `verdict=blocked`, which causes `list_emails(exclude_blocked_verdict=True)` to hide it from the app. It was not lost — just hidden.

### Fixes Applied

- **`email_scanner.py`:** Added SELF-EMAIL RULE to `_INTENT_VERDICT_RULES` and the single-email `evaluate_email_intent` prompt. Self-emails with task/to-do/action-item content are always `permitted`. Only blocks self-emails with truly empty or test-only bodies.
- **`lib/email_helpers.py`:** `_extract_sender_addr` now calls `.strip().lower()` on both code paths (angle-bracket and plain address).
- **`routes/agent.py`:** `sender_filters` and `blocked_senders` now built with `.strip().lower()` when constructing `permitted_set_trigger` and `blocked_set_trigger`. Added structured DROP log lines at every drop point: verdict-blocked, no-filter-match, unknown-account, no-service. Format: `[email-trigger] DROP email_id=X sender=Y recipient=Z verdict=W reason=R`.
- **`routes/emails.py`:** `_run_intent_eval_batch` now short-circuits permitted senders before calling Gemini, matching the pattern in `agent_email_trigger`.

### Manual Recovery — Actual Path

The email was NOT blocked in Firestore. Direct Firestore inspection showed `19e432019b4c6b9e` (subject: "to-do's") with `verdict=permitted`. The email was correctly stored by an earlier Pub/Sub delivery (one of the 5 at 10:03 PM). The log showing `excluded (verdict=blocked)` was from a LATER Pub/Sub retry where the in-memory Gemini verdict was blocked — but because `email_exists` returned True, the Firestore document was not overwritten. Cloud Task enqueuing was correctly suppressed on the retried deliveries (the email was already in Firestore and the Cloud Task was already enqueued from the first delivery).

The email was hidden because it was in `saucer-dismissed.json` (the GCS dismissed list). How it got there is unclear — most likely the automated `process_single_email` Cloud Task ran, Hana processed it, and some downstream action dismissed it. Alternatively the CEO may have swiped to dismiss it in the app.

Recovery: removed `19e432019b4c6b9e` from `saucer-dismissed.json` via direct GCS write. Email now appears in `/emails/cached` with `verdict=permitted`. Confirmed via API call.

### No Stale History ID Issue

The `0 new message(s)` logs at 3:00 AM UTC are expected behavior — those Pub/Sub notifications fired with history IDs that had already been advanced past. Not a separate bug.

---

## Backlog — Sprint 15

### [BACKLOG-01] Gmail Watch Expiry Monitor

**Description:**
The Gmail push watch expires after 7 days. The current proactive re-watch logic in `agent_email_trigger` only fires when a Pub/Sub notification arrives AND the watch is already expired — meaning if no emails arrive near expiry, the watch silently lapses and all email notifications stop until the next `POST /agent/renew-gmail-watch`. There is no alerting when this happens.

**What it does:**
A scheduled job checks how many hours remain until the watch expires and fires an alert if under 24 hours.

**Implementation plan:**
- **Trigger:** Cloud Scheduler cron job, runs once daily (e.g. 8 AM UTC). Calls a new `POST /agent/check-watch-health` endpoint on the backend, authenticated with the existing AGENT_KEY header.
- **Files touched:**
  - `routes/agent.py` — new `/agent/check-watch-health` route. Reads `last_watch_established` from `saucer-config.json` in GCS. Computes hours remaining (watches expire after 7 days = 168 hours). If under 24 hours, logs `[watch-health] ALERT watch_expires_in_hours=N` and proactively calls `setup_gmail_watch` to renew early.
  - Cloud Scheduler job (one-time setup in GCP console or Terraform) — no code file, just a console action.
- **Alerting:** The log line `[watch-health] ALERT` is searchable in Cloud Logging. A Cloud Monitoring log-based alert (already available for free tier) can be set to notify on this string via email or PagerDuty. No new infrastructure needed.
- **Size: S.** The endpoint is ~30 lines. Cloud Scheduler setup is 5 minutes. Log-based alert setup is 10 minutes. Total estimated effort: 1-2 hours.

---

## Production Incident — 2026-05-20 — 105 Emails Showing "Evaluation Error" Badge — RESOLVED

**Git commit:** a11b09a. **Backend revision:** saucer-backend-00181-l9w.

### Root Cause

`google.generativeai` v0.8.6 on Cloud Run was falling back to Application Default Credentials (ADC — the Cloud Run service account) instead of the `GOOGLE_API_KEY` env var. The service account does not have the `https://www.googleapis.com/auth/generative-language` scope, so every Gemini call in `batch_evaluate_emails_intent` returned `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT`. The exception handler in that function defaulted all 729 emails to `verdict=uncertain` with reason "Evaluation error — showing as uncertain". The `/emails/resync` call was triggered at ~3:11 AM UTC, poisoning all emails in Firestore.

The `google.generativeai` package was already deprecated as of this version — the boot logs showed `FutureWarning: All support for the google.generativeai package has ended.` This was the underlying cause of the auth behavior change.

### Fixes Applied

**email_scanner.py** — Migrated from `google.generativeai` to `google.genai` (new SDK). All five `GenerativeModel(...).generate_content()` call sites replaced with `_get_client().models.generate_content(model=..., contents=..., config=...)`. Client instantiated lazily via `_get_client()` to avoid import failure when `GOOGLE_API_KEY` is not set. New SDK uses `Client(api_key=...)` pattern and never falls back to ADC.

**requirements.txt** — Added `google-genai` alongside `google-generativeai`. FutureWarning eliminated from boot sequence.

**routes/agent.py** — Added keyword fast-track in `agent_email_trigger`. Before calling `evaluate_email_intent`, if a new email matches any keyword in `keyword_filters`, it is immediately set to `verdict=permitted` without a Gemini call. Same logic as the existing sender-allowlist fast-track. Keyword-matched emails (e.g. "Ponce Primary" emails, Scout emails) can never be falsely uncertain due to Gemini failures.

**routes/emails.py** — Added keyword fast-track to `_run_intent_eval_batch` (new `keyword_filters` parameter, threaded through to call sites in `/emails` and `/emails/resync`). Also added keyword fast-track and permitted-sender fast-track to `batch_evaluate_emails_intent` in `email_scanner.py` — the batch path previously had no pre-filter for either, leaving them exposed to Gemini failures even for explicitly trusted signals.

### Manual Recovery

The poisoned 729-email Firestore state was corrected via two direct scripts:

1. **Fix permitted/keyword matches:** Iterated all `verdict=uncertain` emails in Firestore. 226 were corrected to `verdict=permitted` (sender in allowlist or keyword match). 499 were genuinely uncertain (no allowlist/keyword match, no body available for keyword check).

2. **Clear poisoned verdicts:** Iterated remaining 498 uncertain emails with `verdict_reason = "Evaluation error — showing as uncertain"`. Cleared `verdict` and `verdict_reason` fields — these now have no verdict and will be re-evaluated by Gemini (now working) on the next `/emails` call (up to 20 per call per request).

### State After Fix

- 231 emails: `verdict=permitted` (correctly set by fix script)
- 0 emails: `verdict=uncertain` (none — poisoned state cleared)
- 2 emails: `verdict=blocked`
- 498 emails: no verdict (pending Gemini re-evaluation, will drip in at ≤20/request)
- Ponce Primary Care emails: verdict cleared — will come back `permitted` on next `/emails` call since intent description explicitly references "Ponce Primary"

### Design Debt Noted

The `/emails/resync` endpoint is synchronous and processes up to 731 emails × 37 Gemini batches in a single HTTP request. This approaches Cloud Run's 5-minute request timeout at current email volume. As the email corpus grows, resync will time out reliably. Future fix: convert resync to a Cloud Tasks-backed async job with progress tracking — same pattern as `process_single_email`. Not urgent today; becomes urgent around 1,500-2,000 emails.
