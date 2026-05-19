"""db_schema.py — Canonical Firestore collection paths for Saucer / Hana.

This file is the authoritative reference for all Firestore collection paths
used across the backend. It does not contain runtime logic — it is
documentation plus string constants. Every collection used in any .py file
must appear here.

NAMESPACE RULE (zero exceptions, Sprint 4+):
  User-specific data must live under users/{user_id}/.
  Global config and shared observability collections are the only exceptions.

──────────────────────────────────────────────────────────────────────────────
USER-NAMESPACED COLLECTIONS  (users/{user_id}/...)
──────────────────────────────────────────────────────────────────────────────

  users/{user_id}/pending_actions/{action_id}
    Documents representing actions Hana has proposed or is executing.
    Fields: action_type, payload, status, processing_status, confidence,
            email_id, user_email, created_at.
    processing_status lifecycle: pending → in_progress → complete | failed
    status lifecycle:            pending → approved | rejected | expired
    Module: pending_actions.py

  users/{user_id}/emails/{email_id}
    Email metadata (sender, subject, date, verdict, etc.).
    Body content lives in GCS at email-bodies/{email_id}.json.
    Module: email_store.py
    NOTE: email_store.py currently uses the flat 'emails' collection.
    This was created before the multi-user namespace was locked in Sprint 4.
    Migration to users/{user_id}/emails/ is tracked as Sprint 5 debt.

  users/{user_id}/counters/daily_tasks
    Per-user daily task enqueue counter.
    Fields: count (int), reset_date (YYYY-MM-DD string).
    Resets automatically when reset_date differs from today.
    Module: task_queue.py

──────────────────────────────────────────────────────────────────────────────
GLOBAL CONFIG  (intentionally not user-namespaced)
──────────────────────────────────────────────────────────────────────────────

  config/limits
    System-wide configurable thresholds. A single document.
    Fields:
      min_confidence_threshold (float, default 0.7)
        — Actions below this confidence are refused by enqueue_action().
      max_tasks_per_user_per_day (int, default 30)
        — Per-user daily enqueue cap for Cloud Tasks.
    Module: task_queue.py

──────────────────────────────────────────────────────────────────────────────
SHARED OBSERVABILITY  (flat, pre-Sprint-4 — not user-namespaced)
──────────────────────────────────────────────────────────────────────────────
These collections predate the multi-user namespace lock. They contain a
user_email field for per-user filtering. Migrating them to the namespaced
scheme is Sprint 5/6 work.

  user_actions/{doc_id}
    Append-only action log. Fields include user, action_type, timestamp.
    Module: logger.py

  gemini_decisions/{doc_id}
    Gemini decision audit trail. Fields include user_email, action_type,
    full_prompt, tool_arguments, notes_consulted, timestamp.
    Module: logger.py, agent.py

  morning_briefings/{briefing_id}
    Daily briefing output from the morning agent.
    Fields: dan_message, emily_message, date, timestamp, tasks_added, etc.
    Module: agent.py, main.py

──────────────────────────────────────────────────────────────────────────────
HOUSEHOLD SETTINGS  (flat, pre-Sprint-4, single-household)
──────────────────────────────────────────────────────────────────────────────

  settings/email_filters        — permitted sender addresses
  settings/keyword_filters      — keyword watch filters
  settings/blocked_senders      — blocked sender addresses
  settings/exclude_keyword_filters — keywords to suppress from inbox
  settings/email_intent         — household email intent description
    Module: main.py

  user_settings/{user_email}
    Per-user roles and preferences (Dan, Emily).
    Module: mediator.py, main.py

  household_profile/{user_email}
    Household profile (family members, shopping habits, role division).
    Module: mediator.py

  hana_notes/{topic_slug}
    Household memory notes written by Hana.
    Module: memory.py

  hana_question_queue/queue
    Single-doc queue for Hana's outstanding question to the household.
    Module: memory.py

  hana_files/{file_id}
    Metadata for uploaded/auto-saved files (PDFs, images).
    Module: main.py

  hana_filter_feedback/{doc_id}
    User feedback on email filtering decisions.
    Module: main.py

  blocked_topics/{doc_id}
    Topics blocked by the user from appearing in Hana's suggestions.
    Module: main.py

  conversation_history/{doc_id}
    Chat conversation history per user.
    Module: conversation_history.py
"""

# ── String constants ──────────────────────────────────────────────────────────
# Use these in code rather than bare string literals to keep paths refactorable.

# User-namespaced paths (format with user_id before use)
COLL_PENDING_ACTIONS = 'users/{user_id}/pending_actions'
COLL_USER_EMAILS = 'users/{user_id}/emails'
COLL_USER_COUNTERS = 'users/{user_id}/counters'
DOC_DAILY_TASKS_COUNTER = 'users/{user_id}/counters/daily_tasks'

# Global config
COLL_CONFIG = 'config'
DOC_LIMITS = 'config/limits'

# Shared observability (flat, pre-Sprint-4)
COLL_USER_ACTIONS = 'user_actions'
COLL_GEMINI_DECISIONS = 'gemini_decisions'
COLL_MORNING_BRIEFINGS = 'morning_briefings'

# Household settings (flat, pre-Sprint-4)
COLL_SETTINGS = 'settings'
COLL_USER_SETTINGS = 'user_settings'
COLL_HOUSEHOLD_PROFILE = 'household_profile'
COLL_HANA_NOTES = 'hana_notes'
COLL_HANA_QUESTION_QUEUE = 'hana_question_queue'
COLL_HANA_FILES = 'hana_files'
COLL_HANA_FILTER_FEEDBACK = 'hana_filter_feedback'
COLL_BLOCKED_TOPICS = 'blocked_topics'
COLL_CONVERSATION_HISTORY = 'conversation_history'

# email_store still uses the flat 'emails' collection (pre-Sprint-4 debt)
# Migration to COLL_USER_EMAILS is tracked for Sprint 14.
COLL_EMAILS_LEGACY = 'emails'

# ── Sprint 13 Multi-User Scale Audit ─────────────────────────────────────────
#
# NAMESPACED (safe for multi-user):
#   users/{user_id}/pending_actions/        Sprint 4 — DONE
#   users/{user_id}/counters/daily_tasks    Sprint 4 — DONE
#   users/{user_id}/counters/daily_agent_calls   Sprint 13 — DONE
#   users/{user_id}/counters/daily_voice_calls   Sprint 13 — DONE
#   users/{user_id}/emails/                 DEFERRED — Sprint 14 named gate
#
# FLAT — must migrate before multi-user public launch (suggested order):
#   1. settings/                     — email_filters, blocked_senders, keyword_filters, etc.
#                                      Must become users/{user_id}/settings/.
#                                      Gates per-user filter isolation.
#   2. hana_notes/                   — Must become users/{user_id}/hana_notes/.
#                                      Household memory must be per-user.
#   3. gemini_decisions/             — Must become users/{user_id}/gemini_decisions/.
#   4. morning_briefings/            — Must become users/{user_id}/morning_briefings/.
#   5. user_actions/                 — Must become users/{user_id}/user_actions/.
#   6. conversation_history/         — Must become users/{user_id}/conversation_history/.
#   7. emails/ (flat, legacy)        — Sprint 14 named gate (highest priority).
#
# INTENTIONALLY GLOBAL (no migration needed):
#   config/limits                    — Global rate limit config. Correct as-is.
#
# SAFE WITH user_email FIELD (migration low-urgency):
#   user_settings/{user_email}       — already keyed by user_email; OK until multi-user.
#   household_profile/{user_email}   — same.
#   hana_question_queue/queue        — single household; low urgency.
#   hana_files/{file_id}             — needs user_email field added before multi-user.
#   hana_filter_feedback/{doc_id}    — has user_email field; low urgency.
#   blocked_topics/{doc_id}          — needs user_email/namespacing before multi-user.
#
# MIGRATION PRIORITY FOR SPRINT 14+:
#   Sprint 14: emails/ (named gate) + settings/ (blocks filter isolation)
#   Sprint 15: hana_notes/, gemini_decisions/, morning_briefings/
#   Sprint 16: remaining flat collections
