# Huddle Notes

Running log of huddle sessions. Updated by @secretary at the close of each meeting.

---

_(No entries yet — first huddle pending.)_

---

## 2026-05-17 Huddle

**Topics:**
- Proactive vs. reactive product strategy decision
- Strategy advisor input on economics and risk of proactive approach
- Engineering sequencing confirmation
- Full 12-sprint roadmap to app store (PM)
- Sprint 3 blocker status

**Decisions:**
- Hana is a proactive assistant. Decision is locked. CEO rationale: firsthand parenting experience; does not want to replicate the run-of-the-mill reactive feature set of competitors (Nori, Ohai cited).
- Proactive framing confirmed as correct economic bet by strategy advisor: cannot compete with free on reactive features.
- Cloud Tasks remains sequenced for Sprint 4, not earlier. Engineering accepted decision without pushback.
- 12-sprint roadmap accepted as presented: Phase 1 (Sprints 1–6) backend core, Phase 2 (Sprints 7–8) voice AI, Phase 3 (Sprints 9–12) mobile frontend and app store submission.

**Open items:**
- Sprint 4 must define signal-to-action logic and confidence threshold before any proactive surface ships. Advisor flagged weak-signal self-censorship as the key risk.
- OAuth re-auth for gmail.compose scope remains the only blocker on Sprint 3 start. No resolution confirmed this session.
- App store gates and CEO decision points documented in roadmap but not yet scheduled.

### User Testing Strategy

**Decision:** User testing is a rolling track, not a standalone sprint.
- Sprint 6: 2-3 target users (working parents 28-45) access Gmail Drafts flow. Key question: useful or intrusive? First read on confidence threshold.
- Sprint 8: Structured interviews with 5 users on core loop. Findings must lock confidence threshold before Sprint 9 mobile development begins.
- Sprint 12 TestFlight is an app store compliance gate, not a user test.

**CEO action item:** Recruit 5 target users now. Do not wait for Sprint 12.

---

## 2026-05-17 Huddle (Session 2)

**Topics:**
- Market sizing: TAM $1.73B / SAM $137M; Y1 projection 3,000 subscribers / $270K ARR; Y5 57,000 / $7.6M ARR.
- Cost and margin model: infrastructure-only margins ~64% Y1, ~60% Y3/Y5. Claude API is ~99% of variable cost; proactive checks are primary cost driver at $2.70/user/month. Prompt caching flagged as Sprint 5/6 optimization.
- Voice add-on: $1.13/user/month at Y3. Cannot ship before ActionClass + Cloud Tasks (Sprint 7 earliest). CEO questioned earlier shipping; engineer confirmed no shortcut path.
- Direct web subscriptions: positioning framing confirmed as "subscribe at hana.com, then download the app." Y1 mix projected at 70/30 app-store-to-web. Apple anti-steering rules limit in-app promotion of web pricing.
- Cash burn pre-launch: CEO confirmed negligible.
- User testing track reviewed and confirmed (unchanged from Session 1).

**Decisions:**
- Voice is gated on Sprint 7. No accelerated path.
- Web subscription positioning confirmed.

**Open items:**
- CEO action item (carried from Session 1): Recruit 5 target users now.
- Prompt caching optimization deferred to Sprint 5/6; no owner assigned yet.

---

## 2026-05-18 Huddle

**Topics:**
- SMS as supplementary channel: opt-in only, activated post-app-setup. Short, conversational tone; never paragraphs. Proactivity style to be tuned post-launch via prompt config.
- Group chat via SMS: reviewed Ohai precedent; confirmed feasible via Twilio number, inbound webhook, opt-in toggle in mobile UI, constrained response formatter.
- Roadmap placement: PM slotted SMS into Sprint 10 alongside core mobile screens, dependent on Sprint 9 mobile auth layer.
- Full 12-sprint roadmap reviewed. Open decisions identified: Firebase Auth vs. alternative (Sprint 9), React Native vs. Flutter (Sprint 10), whether Hana initiates calls (Sprint 8), solo dev vs. mobile help (Phase 3).
- Infrastructure scalability: engineer flagged two Sprint 4 additions (lock multi-user Firestore namespace schema; add per-user Cloud Tasks enqueue cap). LLM API and Twilio cost modeling flagged before Sprint 11.

**Decisions:**
- SMS is opt-in supplementary, not primary interface. Slotted Sprint 10. No sprint reordering.
- Sprint 4 scope expanded with two infrastructure items.

**Open items:**
- CEO to recruit beta users now, not at Sprint 12 (carried forward).
- Four open roadmap decisions listed above require CEO resolution before their respective sprints begin.
- Cost model for LLM API and Twilio at volume needed before Sprint 11.

---

## 2026-05-18 Huddle (Session 2)

**Topics:**
- CEO requested a plain-English TLDR of all 12 sprints (Sprints 1-3 complete, Sprints 4-12 upcoming).
- CEO asked the team whether anything was needed or unresolved before Sprint 4 begins.
- Status confirmation on Gmail Drafts OAuth (gmail.compose scope) from Sprint 3.
- Firestore schema design: single-user vs. multi-user-safe structure.

**Decisions:**
- Gmail Drafts OAuth from Sprint 3 is confirmed live. Decision locked.
- Firestore schema will be built multi-user-safe from day one. Paths standardized as users/{user_id}/pending_actions/{action_id}. Decision locked.
- Sprint 4 is fully unblocked. No outstanding prerequisites.

**Open items:**
- None raised this session. Sprint 4 is cleared to begin.

---

## Standing CEO Directive (2026-05-18)

Never ask the CEO to run a terminal command that an agent or Coder can run directly. The CEO is not a technical blocker. If a shell command needs to be executed as part of sprint work or setup, run it — do not hand it off as a CEO action item unless it genuinely requires credentials or account access that agents cannot obtain.

---

## 2026-05-18 Huddle (Sprint Session)

**Topics:**
- Sprint 4 verification (all three checks passed: revision 00148 live, service account has roles/run.invoker, Firestore config/limits doc confirmed). Verification was run by the engineer agent, not the CEO.
- Protocol gap identified: PM and sprint protocol were directing the CEO to run terminal commands that agents can run themselves. pm.md updated with an explicit rule that the team handles all terminal work.
- Token tracking in pm.md revised: Step 4 updated to use a JSONL-based bash script (the built-in /usage command is not machine-readable via bash). The 39,600 token ceiling was removed as incorrect — project runs on a subscription. PM now tracks output token trends as a health signal and flags if output tokens exceed 50K in a 5-hour window.
- Sprint 5 ceremony and execution: six technical debt tasks completed, deployed as revision 00150-gmp. sprint_results.md written, plan.md updated to mark Sprint 5 COMPLETE.

**Decisions:**
- Team (not CEO) handles all gcloud/bash/Firestore verification work going forward.
- emails flat namespace migration is a Sprint 9 gate item; it is not a stretch target for earlier sprints.
- _topic_blocked and _load_blocked_topics_by_sender deleted (zero callers; feature was never wired).
- notes_consulted closure: no bug found; behavior was confirmed correct.

**Open items:**
- None raised this session. Sprint 6 is next in sequence.

---

## 2026-05-18 Huddle (Sprint 6 Session)

**Topics:**
- Sprint 6 (Blueprint Foundation) execution and verification.
- lib/ infrastructure created: firestore_client.py, config.py, auth.py, email_helpers.py.
- routes/agent.py Blueprint: agent/run, briefing/*, agent/email-trigger, agent/renew-gmail-watch.
- routes/tasks.py Blueprint: tasks/handle-action, tasks/process-email, pending-actions.
- main.py refactored: 395 lines removed, blueprint registrations added.
- Side fix: Firestore composite index on pending_actions (status, created_at) created and verified READY.
- Deployed as revision saucer-backend-00153-rlf, git commit 6f954b0.

**Decisions:**
- Sprint 6 COMPLETE and VERIFIED.
- Sprints 1–6 all complete. Phase 1 (backend core) is done.

**Open items:**
- None. Sprint 7 is next — split remaining route groups from main.py into blueprints (emails, calendar, files, filters, memory, admin).

---

## 2026-05-18 Huddle (Product Fixes Session)

**Topics:**
- Huddle notes gap: Sprint 6 completion was missing; entry added. Protocol updated so PM always logs sprint completion to huddle_notes.md even outside active huddles.
- Removed features: AI email summary gray preview text and task extraction with swipe left/right were silently deleted in Sprint 5 hygiene without product sign-off. New protocol: any hygiene sprint touching a user-facing capability requires explicit PM and CEO approval before removal.
- Team purpose alignment: agents each stated Hana's purpose in 140 chars. Business framed Hana too narrowly as an "email assistant." Strategy and Marketing converged on whole-household mental load reduction. Marketing framing: the customer fear is "I missed something important," not "I have too many emails."
- Briefing attribution bug: Hana summarized email content as a Hana decision. Root cause: no requirement to call add_todo/reassign_task before claiming an assignment; briefing text and decisions collection are siloed. Fix: prompt guard + briefing_assertions schema change.
- Note deduplication bug: contradictions and redundancies in grocery preferences note. Root cause: Hana doesn't search_memory before writing; merge prompt never instructs removal of old version. Fix: two-part prompt + merge prompt update.
- To-do source email highlights: source_spans write path deleted in Sprint 5 with no replacement. Fix: store source_spans in Firestore email doc.
- Briefing-to-chat handoff: tapping "Let's chat" on morning briefing should pre-load the briefing message as chat context.

**Decisions:**
- Sprint 9 (Product Fixes) inserted; Voice AI slides to Sprint 10. Roadmap is now 15 sprints.
- Sprint 9 scope: briefing attribution fix, email summary restore, task determination restore, task swiping restore, email highlights restore, briefing-to-chat handoff, note dedup fix.
- To-do → source email → highlights deferred to Sprint 10 (depends on Sprint 9 task and highlights work).
- CEO_demands.md created at /home/dcjohnston1/saucer/team/CEO_demands.md as a standing checklist.
- Protocol locked: sprint close must log to huddle_notes.md regardless of whether a huddle is active.

**Open items:**
- CEO beta user recruitment still pending (carried forward; named gate at Sprint 12).
- Four open roadmap decisions pending CEO resolution: Firebase Auth vs. alternative (Sprint 12), React Native vs. Flutter (Sprint 13), whether Hana initiates calls (Sprint 10), solo dev vs. mobile help (Phase 3).

---

## 2026-05-19 Sprint 9 Close

**Sprint 9 — Product Fixes — COMPLETE ✓** Git commit 70aa667.

- Briefing attribution: prompt guard + briefing_assertions schema added. Hana can no longer claim a task assignment without a logged tool call.
- Note dedup: search-before-save rule added to prompts; _gemini_merge now removes contradicted facts.
- Email summary: verified already working — no code change needed.
- Task determination + swiping + highlights: /emails/scan-todos route added; source_spans now written to Firestore; swipe accept/reject UI live; excerpt route fixed to read from Firestore.
- Briefing-to-chat handoff: briefing pre-loads as Hana's first chat bubble when "Let's chat" is tapped.
- Bonus: calendar routes extracted into Blueprint (calendar integration may now be unblocked — CEO to confirm).

**CEO_demands.md:** all 8 Sprint 9 items complete. To-do → source email → highlights (Sprint 10) is now unblocked.

---

## 2026-05-19 Sprint 10 Close

**Sprint 10 — In-App Voice AI + First External User — COMPLETE ✓** Git commit 3923c5b.

**What was delivered:**
- To-do source email highlight: tap a suggested todo → source email opens with yellow highlights on the text that triggered it. Sprint 9 had the backend wired; this sprint added the tap entry point.
- In-app voice (Google Cloud STT + TTS): hold-to-record button in chat UI. User holds, speaks, Hana responds with MP3 audio. No Twilio, no phone calls. WEBM_OPUS sent directly to Cloud STT (no ffmpeg). Neural2-F voice for TTS. Three button states: green pulse (recording), blue (processing), amber pulse (speaking). Low-confidence STT returns a friendly retry message, not an error.
- Emily onboarding guide: /home/dcjohnston1/saucer/team/emily_onboarding.md ready for CEO to customize and send.

**Key decisions this sprint:**
- Voice direction locked: in-app only, no Twilio. Backend STT/TTS pipeline via Google Cloud.
- Emily confirmed as external user #1. Named gate: she must run Hana once before this sprint is fully closed.
- Marketing to identify organic external user #2 candidate before Sprint 11 closes.
- Analyst voice UX research does not block Sprint 10. Findings feed Sprint 11 polish.

**Named gate — Emily:** The onboarding guide is ready. The PM flag stands: this sprint is not fully closed until Emily runs the app. CEO delivers the guide; Emily logs in.

**Next sprint:** Sprint 11 — Voice UX polish informed by analyst research and Emily feedback. TTS voice tuning. Organic user #2 identification. Structured user interview design.

**Next:** Sprint 11 — Voice UX Polish + Emily Gate + User #2.

---

## 2026-05-19 Sprint 11 Launch

**Sprint 11 — Voice UX Polish + Emily Gate + User #2 — LAUNCHED**

**What is being delivered:**
1. Voice earcon: Web Audio API tone plays immediately after recording stops and loops softly until Hana's audio response begins. Fills the perceived lag gap the CEO flagged. Zero backend changes.
2. Voice retry state: Red/neutral visual state + "Didn't catch that, try again" label + button auto-reset when STT returns low-confidence result. Closes the UX gap where failed voice attempts left the button in an ambiguous state.
3. TTS voice constant: Configurable HANA_VOICE_NAME constant added to voice_handler.py for easy future tuning.

**Key decisions made:**
- Sprint scope kept light: all items rated small. Appropriate given 85K output token flag in last 5 hours.
- Emily gate urgency confirmed: CEO must forward emily_onboarding.md (URL: https://saucer-frontend-6ksi6iut7a-uc.a.run.app) to Emily this week. Sprint 12 cannot launch without Emily confirmed.
- Finance to draft cost-per-active-user estimate before Sprint 12 scope is finalized (Sprint 12 named gate).
- CEO to identify one warm-network organic User #2 candidate (not family, working parent 25-45) before Sprint 11 closes.

**Next sprint:** Sprint 12 — Mobile API Hardening. Gates: Emily confirmed, cost-per-user estimate complete, emails namespace migration.

---

## 2026-05-19 Sprint 11 Close

**Sprint 11 — Voice UX Polish + Emily Gate + User #2 — COMPLETE ✓**
Git commit 6543959. Backend revision saucer-backend-00165-w2x. Frontend revision saucer-frontend-00120-pzq.

**What was delivered:**
1. Voice earcon: _playEarcon()/_stopEarcon() added to app.js. Soft 440→880Hz rising tone plays immediately when recording stops, sustains during processing, stops when MP3 audio response starts playing. Fails silently if Web Audio API not available. Directly addresses CEO feedback on the recording-to-response silence gap.
2. Voice error state: Button turns solid red for 2 seconds on low_confidence or no_transcript STT responses, then auto-resets to idle. CSS rule added. Closes the UX gap where failed voice attempts left the button with no feedback.
3. TTS voice constant: HANA_VOICE_NAME module-level constant in voice_handler.py. Voice tuning is now a one-line change.

**Key decisions:**
- All three code items were small. Sprint stayed within token budget.
- Emily onboarding guide updated with live URL: https://saucer-frontend-6ksi6iut7a-uc.a.run.app. CEO must send this to Emily — Sprint 12 cannot launch without Emily confirmed.
- Finance cost-per-active-user estimate remains an open pre-Sprint-12 action.
- User #2 candidate identification remains an open CEO action (warm network, not family, working parent 25-45).

**Next sprint:** Sprint 12 — Mobile API Hardening. Named gates that must close before Sprint 12 launches: (1) Emily runs Hana at least once, (2) Finance delivers cost-per-active-user estimate, (3) emails flat namespace migrated to users/{user_id}/emails/.

---

## 2026-05-19 Huddle

**Topics:**
- Sprint 10 delivery review: in-app voice (hold-to-record, Google STT + TTS Neural2, three visual states, MP3 auto-play, commit 3923c5b) and to-do → source email → highlights confirmed shipped.
- Emily onboarding guide written and awaiting CEO customization (app URL, contact info) before sending.
- Voice UX research presented by Analyst: ChatGPT and Claude voice benchmarked; Meta AI voice mode identified as benchmark (full-duplex, natural interjections). Ten design principles documented in analyst_history.md. Key principles: sub-600ms first audio, barge-in non-negotiable, design for the kitchen not the demo room.
- Hana opportunity framed: no current AI voice product is built for noisy household/parenting context.

**Decisions:**
- Voice direction confirmed: in-app only. Twilio phone calls deferred indefinitely.
- Emily approved as external user #1. Rationale: honest feedback; independent users deferred until product is more polished.

**Open items:**
- CEO to complete emily_onboarding.md (app URL + contact info) and send. Sprint 10 named gate closes when Emily runs Hana once.
- Sprint 11 next: voice UX polish informed by analyst research and Emily feedback.

---

## 2026-05-19 Post-Sprint 11 Hotfix Session

**Topics:**
- Sprint 11 CEO feedback: voice lag is better; suggested filling the gap with a liminal/processing sound (earcon — already shipped in Sprint 11, confirmed working).
- Emily onboarding guide surfaced with live URL (https://saucer-frontend-6ksi6iut7a-uc.a.run.app). CEO will forward to Emily.
- Bug: two mic icons appearing side by side in the chat input bar.
- Bug: first voice-to-voice response plays through iPhone speaker instead of Bluetooth headphones; loop drops after a few back-and-forths.
- Bug: browser prompts for microphone permission on every use.

**Hotfixes shipped (revisions 00121–00123):**

1. **Duplicate mic button** (`frontend/app.js`, v44.1): `mic-btn` (old browser SpeechRecognition button) was being un-hidden even when `hana-voice-btn` (Google Cloud STT) is present. Fixed: `mic-btn` now stays hidden when `hana-voice-btn` exists. One-line guard added to `initVoice()`.

2. **iOS Bluetooth routing + loop reliability** (`frontend/app.js`, v44.2): Added `_primeAudioRoute()` — plays a 50ms silent AudioContext buffer before every `speechSynthesis.speak()`, forcing iOS to reroute audio to the current output device (Bluetooth headphones) before Hana speaks. Fixed `recognition.onerror` to restart listening when voice mode is still active. Fixed `recognition.onend` to restart mic if voice mode is active but Hana isn't speaking (handles error/timeout cases that silently killed the loop). Added safety timer in `_doSpeak()` to restart recognition if iOS fails to fire `utt.onend` (known iOS bug after several turns).

3. **Microphone permission re-prompt** (`frontend/app.js`, v44.3): `getUserMedia()` was called fresh on every button press, and tracks were stopped after each recording — causing iOS to re-prompt on the next press. Fixed: persistent `_voiceStream` variable reuses the live stream across recordings. `getTracks().forEach(t => t.stop())` removed from between-recording cleanup paths. iOS now prompts once per session.

**Key decisions:**
- Emily onboarding guide is ready and CEO will forward it. Sprint 12 gate (Emily runs Hana once) is not yet closed.
- No sprint scope changes. All fixes were hotfixes, not sprint items.

**Open items (pre-Sprint 12 gates):**
1. CEO sends Emily the onboarding guide. Emily runs Hana once — gate closes.
2. CEO identifies warm-network User #2 candidate (working parent 25–45, not family, will give direct feedback).
3. Finance delivers cost-per-active-user estimate before Sprint 12 scope is finalized.

---

## 2026-05-19 Sprint 12 Close

**Sprint 12 — CEO Deferred Items (all 8) — COMPLETE ✓** Git commit 4c807d7. Backend saucer-backend-00167-z5k. Frontend saucer-frontend-00124-kqq.

**What was delivered:**
- Filter bug fixed: cached email path now applies sender allowlist. Unrelated senders no longer appear.
- Scan-todos auto-runs on first email load. Swipe direction guard tightened to 1.5x ratio.
- Yellow highlight quote block added directly to email cards (first source_span from scan-todos).
- Auto-calendar: Hana silently adds events to Google Calendar when processing emails with clear dates and commitments. Duplicate guard prevents reprocessing errors. Restrictive Gemini prompt prevents false positives. Toast notification when user opens calendar.
- Future Events: New hamburger menu item shows events 14-180 days out. Gives assurance Hana is tracking far-future commitments.
- Calendar "View email" and to-do source email highlight: both paths verified working (no new code needed for Item 7; Item 8 unblocked by auto-scan).

**Key decisions:**
- CEO chose Option A for auto-calendar (background trigger, silent + dismissable). Locked.
- Item 7 required no code change — already wired correctly from Sprint 9+10.
- Dockerfile saucer_logo.png reference removed (file was deleted post-Sprint 11).

**CEO action items raised:**
1. Publish Privacy Policy and Terms of Service before adding more external users beyond Emily.
2. Calendar OAuth currently uses a shared service account — must switch to per-user credentials before public user onboarding (named pre-public gate, not Sprint 13).

**Next sprint:** Sprint 13 — Mobile API Hardening. Named gates that must close first: Emily confirmed (runs Hana once), Finance cost-per-active-user estimate, emails namespace migration to users/{user_id}/emails/.

---

## 2026-05-19 Sprint 13 Close

**Sprint 13 — Bug Fixes + Auth Foundation — COMPLETE ✓**
Git commit 757b549. Backend saucer-backend-00171-9mj. Frontend saucer-frontend-00125-28k.

**What was delivered:**

Three P0 bug fixes from Sprint 12 regressions:
1. Sender allowlist applied to /emails GET route — the Sprint 12 fix only patched /emails/cached; the live email view still showed floortje@artwithflo.com and other non-permitted senders. Fixed by adding the same allowlist filter to get_emails(). Smoke test confirmed the filter works.
2. scan-todos error gap — scan_emails_for_todos now wrapped in try/except with full traceback logging. scan_count field added to backend response. Frontend empty state now says "Scanned N emails — no action items found" so the CEO can see whether the issue is no results vs. no emails scanned.
3. Future Events error handling — openFutureEventsScreen now catches exceptions from _loadCalendarContent and displays the real error message. Stale "Nothing on the calendar this week" copy replaced with "No events found in this period." Backend logs traceback on calendar exception.

Infrastructure shipped:
- lib/firebase_auth.py: Firebase Auth JWT verification helper and @firebase_auth_required decorator, ready for Sprint 14 mobile routes. No existing routes use it yet.
- lib/rate_limiter.py: Per-user daily caps via Firestore transactional counters. POST /agent/run capped at 20/day; POST /voice/run capped at 30/day. Configurable via Firestore config/limits (max_agent_calls_per_user_per_day=20, max_voice_calls_per_user_per_day=30 now set).
- db_schema.py: Sprint 13 multi-user scale audit written. 7 flat collections identified that need namespacing before public launch. Migration priority order documented.

Finance cost estimate delivered: $0.80–$3.50/user/month depending on usage intensity; voice adds $0.30–$0.60/user/month. At $9/month, margins are viable for average users but squeezed for heavy users.

**Key decisions:**
- Emails namespace migration deferred from Sprint 13 to Sprint 14 (named gate preserved, not dropped). Engineer and Finance agreed it warrants its own sprint — migration of 500+ live Firestore docs must not be a sidecar.
- Sprint 13 renamed from "Mobile API Hardening" to "Bug Fixes + Auth Foundation" to reflect what actually shipped.
- Sprint 14 named gates: emails namespace migration + Emily confirmed + React Native vs. Flutter decision required.

**Next sprint:** Sprint 14 — Emails Namespace Migration + Core Mobile Screens + SMS. Named gates: emails flat collection migrated to users/{user_id}/emails/, Emily confirmed, React Native vs. Flutter decision, marketing strategy defined.

---

## Sprint 14 Kickoff — 2026-05-20

**Sprint number:** 14

**Scope:**
Three CEO-mandated P0 bug fixes surfaced in a live demo. All three block the Emily onboarding gate. Emails namespace migration, mobile screens, React Native vs. Flutter decision, and marketing strategy all deferred to Sprint 15+.

Bug 1 (HIGH) — "Checking for action items..." spinner never resolves.
  Sub-fix 1a: app.js buildProposalsSection — replace spinner text with "No to-dos found".
  Sub-fix 1b: agent.py process_single_email — after add_todo_logged succeeds, write proposals back to Firestore email doc via email_store.update_email_fields. Root cause: add_todo_tool writes to Google Docs only; email doc proposals field is never populated by the agent path.

Bug 2 (MEDIUM, independent) — Hana draft appears as separate email card.
  Part 1: Filter DRAFT-labeled messages in routes/agent.py Pub/Sub handler before upsert_emails_batch.
  Part 2: Store thread_id on draft pending_action payload; batch-load draft actions in /emails/cached; join to emails in memory by thread_id; render collapsible "Hana drafted a reply" section in buildEmailCard.

Bug 3 (MEDIUM) — Action item displays as quoted string, not interactive card.
  Resolves automatically when Bug 1b populates proposals field. buildProposalRow (app.js:1150) is intact.

**Key decisions made:**
- Bug 1a and 1b must ship together — fixing the spinner text without the backend write gives users "No to-dos found" on emails the agent actually processed, which is a different trust problem.
- Finance N+1 concern accepted: Bug 2 Part 2 uses a single batch pending_actions query + in-memory join. No per-email Firestore reads.
- Designer text decision accepted: "No to-dos found" over "No to-dos" — implies Hana looked, which maintains trust.
- Draft section must use muted gray colors, not app accent color, to distinguish draft from confirmed action.
- All named gates (Emily, emails migration, mobile) moved to Sprint 15.

**Meeting circle:** One round, clean consensus. No Round 2 needed. Token estimate: 3,500–4,500 tokens.

**What is next:** Sprint 15 — Emails Namespace Migration + Mobile Screens + Emily Gate. Deferred items from Sprint 14: emails flat namespace migration to users/{user_id}/emails/, React Native vs. Flutter decision, marketing strategy, Emily confirmation gate.

---

## 2026-05-20 Sprint 14 Close

**Sprint 14 — Three P0 Bug Fixes — COMPLETE ✓**
Git commit f9d5350. Backend saucer-backend-00174-485. Frontend saucer-frontend-00127-zxt.

**What was delivered:**

Bug 1 (proposals spinner + Firestore write-back):
- "Checking for action items..." replaced with "No to-dos found" when proposals is null/undefined. Class proposals-scanning preserved.
- add_todo_logged now writes a structured proposal entry ({id, title, notes, date_expression, source_spans}) directly to the Firestore email doc after the Google Doc write succeeds. The proposals field was previously never written by the agent path — it was written to Google Docs only. End-to-end path is now closed: agent run → Firestore email doc updated → /emails/cached returns proposals → buildProposalRow renders swipeable cards.

Bug 2 (Hana draft polluting email feed):
- Part 1: gmail_scanner now includes labelIds and thread_id in every message dict. Routes/agent.py filters DRAFT-labeled messages before upsert_emails_batch. Draft count is logged.
- Part 2: thread_id stored on gmail_draft pending_action payload. /emails/cached batch-loads all pending draft actions and joins to emails by thread_id in memory (single Firestore read, no per-email reads). buildEmailCard renders a collapsible "Hana drafted a reply" section when draft_pending_action is present — subject, body preview, Open in Gmail, Dismiss. Collapsed by default. Muted gray palette.

Bug 3: Resolved as a side effect of Bug 1b. buildProposalRow was correct throughout.

**Key decisions:**
- proposal_entry shape matches buildProposalRow exactly — verified before shipping. No shape mismatch to fix post-deploy.
- Draft join uses in-memory thread_id index, not per-email Firestore reads. Finance N+1 concern addressed at design time.
- "No to-dos found" chosen over "No to-dos" to signal Hana checked — trust UX, not just empty state.

**What is next:** Sprint 15 — Emails Namespace Migration + Mobile Screens + Emily Gate.

---

## 2026-05-20 Huddle

**Topics:**
- CEO raised a niche-first GTM question, citing Campily (summer camp parents) as a model for targeting one underserved segment before expanding.
- Marketing presented 5 candidate niches; top recommendation: independent real estate agents (~2M US, high willingness to pay, concentrated and reachable, named acute pain point).
- Strategy noted the team has implicitly been building for dual-income parents all along; positioning language has not caught up. Recommendation: make the implicit explicit and retire "busy professionals" framing.
- Finance modeled both niches: real estate clears the $220K profitability gate at Y1 conservative (2,000 users); parents have a larger ceiling but diffuse acquisition (Y2 base path). Finance recommended sequencing: lead with real estate to prove unit economics, then expand to parents once CAC and retention are measured.

**Decisions:**
- None locked. CEO directed the team to log the discussion for later.

**Open items:**
- Whether to set a real estate-specific price point at $20/mo (Finance flagged as a required decision before any GTM work begins).
- Whether to commit to the real estate beachhead or name parents as the primary segment now.

---

## 2026-05-20 Huddle — Trust Leak in Dismissed View

**Topics:**
- CEO surfaced screenshot of "Dismissed Emails" view showing a DeKalb County Police safety alert and a Best Buy promo, both labeled "No to-dos found." Asked the team to identify the problem.
- Designer named it first: same flat treatment for a safety alert and spam erodes trust — brain stops reading reasons, next real warning gets the same shrug.
- Engineer confirmed the filter's verdict was correct (Nextdoor not in allowlist, no intent match, no keyword hit) but identified the label as the actual bug — Hana never scanned filter-blocked emails, so "No to-dos found" is dishonest.
- CEO proposed two diagnostic pills: a "Known sender" pill (left of sender, when allowlisted) and a "Relevant topic: [X]" pill (under subject, when freetext intent or keyword fires).
- Designer pushed for low-weight outline pills in separate rows, no fallback when neither applies. CEO challenged: if neither applies, why is the email in the inbox at all? Designer conceded — absence of either signal IS a filter hole, not a neutral case.
- Engineer confirmed: pills should be treated as diagnostics. Pill-less inbox emails are bugs to fix upstream, not UI gaps to paper over.

**Decisions locked:**
- "Not scanned" replaces "No to-dos found" on filter-blocked emails in Dismissed view.
- Marketing copy: "From someone you trust" (NOT "Known sender" — sounds IT-helpdesk).
- Topic pill echoes the user's own phrasing ("Matched: school pickup"), not system jargon.
- Pill visuals: 1px outline, gray #999/#666, 0.7em, separate rows, ~20-char topic truncation.
- No fallback pill — missing pill = filter hole, fix upstream.

**Sprint 16 — COMPLETE 2026-05-20.**
- Git commit 3b80e72 pushed to main. Backend revision saucer-backend-00181-l9w, frontend revision saucer-frontend-00128-pj8 both live.
- All four task scopes shipped: honest "Not scanned" label, trust pill, topic pill, no-fallback rule.
- Verified: deployed JS/CSS carry all required strings and classes; 38 of 101 cached emails already qualify for the trust pill on next page load; `matched_topic` populates on new emails via the eval batch.
- **Pending CEO smoke-test:** visual pill placement, color, truncation, and topic pill end-to-end against a real new email. I cannot drive a browser.

**What is next:** Sprint 17 planning, once CEO confirms Sprint 16 lands visually. Open backlog: Sprint 15 decisions (5 outstanding), calendar integration, namespace migration, mobile framework, Emily gate, Privacy Policy + ToS.
