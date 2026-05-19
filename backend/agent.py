"""
Morning Agent — runs overnight, reviews emails, assigns tasks, writes briefings.

Cloud Scheduler setup (Google Cloud Console — not in code):
  Job name:     saucer-morning-agent
  Schedule:     30 10 * * *
                (5:30 AM Eastern during EDT/summer = 9:30 UTC; this uses 10:30 UTC which is
                 6:30 AM EDT. Adjust to 30 9 * * * in winter EST if needed, or accept 1-hour drift.)
  Target type:  HTTP
  URL:          https://saucer-backend-987132498395.us-central1.run.app/agent/run
  HTTP method:  POST
  Headers:      X-Agent-Key: <value of AGENT_KEY secret>
  Body:         {}
  Auth:         Add OIDC token — saucer-doc-service@mediationmate.iam.gserviceaccount.com
  Timeout:      540s

Cloud Run timeout — must be raised for this endpoint:
  gcloud run services update saucer-backend --timeout=600 --region=us-central1 --project=mediationmate

AGENT_KEY secret setup (one-time):
  echo -n "your-random-secret" | gcloud secrets create AGENT_KEY --data-file=- --project=mediationmate
  Then add it to the Cloud Run service as an env var mounted from Secret Manager.

Manual test (from Cloud Shell):
  curl -X POST https://saucer-backend-987132498395.us-central1.run.app/agent/run \
    -H "X-Agent-Key: $(gcloud secrets versions access latest --secret=AGENT_KEY --project=mediationmate)" \
    -H "Content-Type: application/json" -d '{}'
"""

import hashlib
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import google.generativeai as genai
from google.cloud import firestore as _firestore

from gcs import read_json, write_json
from logger import log_action, get_action_summary
import email_store as _email_store
from mediator import (
    _load_user_context,
    _load_household_profile,
    _load_calendar_context,
    _parse_task_load,
    _load_recent_gemini_decisions,
    add_todo,
)

_PROJECT = 'mediationmate'
_DAN = 'dcjohnston1@gmail.com'
_EMILY = 'emily.osteen.johnston@gmail.com'


def _tz():
    return ZoneInfo("America/Los_Angeles")


SINGLE_EMAIL_SYSTEM_PROMPT = """You are Hana. A new email just arrived. No user is present. Your job:

1. Read the email and extract any actionable tasks or important dates.
2. If there are tasks: assign each to Dan or Emily based on their roles, workload, and calendar. Always log your reasoning.
3. If the email is clearly noise (promotional, newsletter with no action items, receipt with no follow-up): call dismiss_email.
4. Always call write_briefing at the end — 2-3 sentences per person summarizing what you found and what you decided.

Apply the same assignment rules as the morning review:
- Consult HOUSEHOLD MEMBER CONTEXT for each person's stated roles.
- Consult TASK LOAD SUMMARY to balance workload.
- Consult CALENDAR for upcoming commitments.
- Always populate the reasoning field with specifics.

GMAIL DRAFTS:
- If an email clearly warrants a reply — an RSVP, a scheduling request, a direct question to the household, or an action item requiring a response — call draft_reply to create a Gmail draft.
- The draft goes to Gmail Drafts for human review. It is NEVER sent automatically.
- Write the reply in a natural, warm household tone, as Dan or Emily would write it.
- Do NOT draft replies to newsletters, marketing, automated notifications, receipts, or any email where a reply is not clearly expected.
- When in doubt, do not draft. One well-chosen draft is better than three unnecessary ones.
- Always populate the reasoning parameter with why this email warrants a reply.

PASSIVE LEARNING:
- If this email reveals household facts worth remembering (a recurring appointment, a family member mentioned,
  a preference stated), call save_note before writing the briefing.
- Before calling save_note on a topic you may have noted before (grocery preferences, family schedules,
  recurring appointments, etc.), call search_memory first. If you find an existing note that contradicts
  what you are about to write, state the correction explicitly in the content argument.
  Example: "Dan and Emily use Whole Foods, not Trader Joe's, for most grocery shopping."
  This helps the merge detect and remove the contradiction.

BRIEFING ATTRIBUTION RULE:
- Only claim a specific task assignment or commitment in your briefing if you called add_todo or
  reassign_task for it earlier in this same session.
- If an email merely mentions that someone will help with something, report it as email context —
  do not present it as a Hana decision.
  Example: say "The email mentions Emily will help Julia get ready" — not "I've assigned Emily to help Julia get ready."

BRIEFING: Tell each person what's relevant to them. Start with the main point. Sign off warmly."""

AGENT_SYSTEM_PROMPT = """You are Hana running your morning review. No user is present. Your job:

1. Review overnight emails and extract any actionable tasks or important dates.
2. Assign each task to Dan or Emily based on their roles, current workload, and calendar. Always log reasoning.
3. Dismiss emails that are clearly noise — promotions, newsletters with no action items, receipts with no follow-up.
4. Write a friendly morning briefing for each user summarizing what you found and decided.

TASK ASSIGNMENT RULES:
- Consult HOUSEHOLD MEMBER CONTEXT for each person's stated roles.
- Consult TASK LOAD SUMMARY to balance workload across Dan and Emily.
- Consult CALENDAR for upcoming commitments — don't pile tasks on whoever has a busy week.
- Always populate the reasoning field with specifics: cite roles, task count, or calendar events.

EMAIL DISMISSAL:
- Dismiss: purely promotional, newsletters with no action items, order confirmations with no follow-up needed.
- Do NOT dismiss: anything with a deadline, sign-up, permission slip, appointment, or date to remember.

BRIEFING TONE:
- Warm and direct. You're texting a friend who just woke up, not filing a report.
- 3-6 sentences per person. Lead with the most important thing.
- Tell each person about tasks assigned to THEM specifically.
- Sign off warmly.

KNOWLEDGE GAPS:
- While reviewing emails and tasks, if you encounter something you cannot resolve because you lack
  household context (who handles medical appointments, whether a recurring sender is important,
  what a family member's schedule is), call queue_question with a specific, natural question
  and your internal reasoning for why it matters.
- Only queue a question if it would genuinely help you do your job better.
  Do not manufacture questions. Do not queue more than one -- if a question is already queued,
  only replace it if yours is more urgent.

PASSIVE LEARNING:
- If any overnight email reveals household facts worth remembering (a recurring appointment,
  a family member mentioned, a preference stated), call save_note before writing the briefing.
- Before calling save_note on a topic you may have noted before (grocery preferences, family schedules,
  recurring appointments, etc.), call search_memory first. If you find an existing note that contradicts
  what you are about to write, state the correction explicitly in the content argument.
  Example: "Dan and Emily use Whole Foods, not Trader Joe's, for most grocery shopping."
  This helps the merge detect and remove the contradiction.

GMAIL DRAFTS:
- If any overnight email clearly warrants a reply — an RSVP, a scheduling request, a direct
  question to the household, or an action item requiring a response — call draft_reply to create
  a Gmail draft for human review. It is NEVER sent automatically.
- Write in a natural, warm household tone, as Dan or Emily would write it.
- Do NOT draft replies to newsletters, marketing, automated notifications, or ambiguous emails.
- When in doubt, do not draft. One well-chosen draft is better than several unnecessary ones.
- Always populate the reasoning parameter.

BRIEFING ATTRIBUTION RULE:
- Only claim a specific task assignment or commitment in your briefing if you called add_todo or
  reassign_task for it earlier in this same session.
- If an email merely mentions that someone will help with something, report it as email context —
  do not present it as a Hana decision.
  Example: say "The email mentions Emily will help Julia get ready" — not "I've assigned Emily to help Julia get ready."

When finished reviewing all emails, call write_briefing with both messages.
If there are no overnight emails, still call write_briefing with a brief "all quiet overnight" message for each user."""


def _parse_email_date(date_str: str) -> datetime:
    if not date_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _format_emails_for_agent(emails: list) -> str:
    lines = []
    for i, e in enumerate(emails[:20], 1):
        lines.append(f"[{i}] ID: {e['id']}")
        lines.append(f"    Date: {e.get('date', 'unknown')}")
        lines.append(f"    From: {e.get('sender', 'unknown')}")
        lines.append(f"    Subject: {e.get('subject', '(no subject)')}")
        body = (e.get('body', '') or e.get('snippet', ''))[:1500]
        if body:
            lines.append(f"    Body: {body}")
        for att in e.get('attachments', []):
            if att.get('extracted_text'):
                lines.append(f"    Attachment ({att['filename']}): {att['extracted_text'][:500]}")
        lines.append("")
    return "\n".join(lines)


def _load_action_history_extended() -> str:
    """Return the last 10 meaningful actions per user."""
    try:
        from logger import get_recent_actions
        _skip_types = {
            'sender_filter_added', 'sender_filter_removed',
            'keyword_filter_added', 'keyword_filter_removed',
            'exclude_keyword_filter_added', 'exclude_keyword_filter_removed',
            'sender_blocked', 'sender_unblocked', 'profile_updated',
        }
        _verbs = {
            'task_completed': 'completed task',
            'task_added': 'added task',
            'task_reassigned': 'reassigned task',
            'proposal_accepted': 'accepted proposal',
            'proposal_dismissed': 'dismissed proposal',
            'email_dismissed': 'dismissed email',
            'calendar_event_added': 'added calendar event',
            'calendar_event_edited': 'edited calendar event',
            'calendar_event_deleted': 'deleted calendar event',
        }
        users = [(_DAN, 'Dan'), (_EMILY, 'Emily')]
        lines = ['RECENT INDIVIDUAL ACTIONS:']
        for email, name in users:
            actions = get_recent_actions(user=email, limit=30)
            shown = 0
            for a in actions:
                if a.get('action_type') in _skip_types:
                    continue
                ts = a.get('timestamp', '')[:10]
                verb = _verbs.get(a.get('action_type', ''), a.get('action_type', '').replace('_', ' '))
                title = a.get('title') or a.get('sender') or ''
                entry = f'  • {name} {verb}'
                if title:
                    entry += f" '{title}'"
                entry += f' on {ts}'
                if a.get('actor') == 'gemini':
                    entry += ' (by Gemini)'
                lines.append(entry)
                shown += 1
                if shown >= 10:
                    break
        return '\n'.join(lines) if len(lines) > 1 else ''
    except Exception as e:
        print(f'[agent] action history error: {e}')
        return ''


def _log_gemini_decision_sync(action_type, input_context, context_consulted,
                               decision_made, reasoning, confidence='medium',
                               user_email=None, full_prompt=None,
                               tool_arguments=None, notes_consulted=None) -> str:
    """Write a Gemini decision synchronously and return the doc ID."""
    try:
        db = _firestore.Client(project=_PROJECT)
        doc_data = {
            'action_type': action_type,
            'input_context': input_context,
            'context_consulted': context_consulted,
            'decision_made': decision_made,
            'reasoning': reasoning,
            'confidence': confidence,
            'actor': 'gemini',
            'timestamp': datetime.now(timezone.utc),
        }
        if user_email:
            doc_data['user_email'] = user_email
        # notes_consulted invariant:
        #   [] means no memory search occurred this decision — correct and expected.
        #   None means the factory was called without a notes_consulted list — should not happen.
        #   A non-empty list means at least one memory search ran before this action fired.
        # The field is absent from pre-Sprint-1 records — that is historical, not a bug.
        try:
            if full_prompt:
                _orig = len(full_prompt)
                if _orig > 900_000:
                    doc_data['full_prompt'] = full_prompt[:900_000] + f'\n\n[TRUNCATED — original was {_orig} characters]'
                else:
                    doc_data['full_prompt'] = full_prompt
            if tool_arguments is not None:
                doc_data['tool_arguments'] = tool_arguments
            if notes_consulted is not None:
                doc_data['notes_consulted'] = notes_consulted
        except Exception as e:
            # Do not silently swallow — log the field name and value type for diagnosis.
            print(
                f'[agent] _log_gemini_decision_sync optional fields failed: {e} '
                f'(notes_consulted type={type(notes_consulted).__name__})',
                file=sys.stderr,
            )
        _, ref = db.collection('gemini_decisions').add(doc_data)
        return ref.id
    except Exception as e:
        print(f'[agent] log_gemini_decision_sync failed: {e}')
        return ''


def _make_agent_add_todo(agent_state: dict, context_available: str, full_prompt: str = None, notes_consulted: list = None):
    # notes_consulted is captured by reference intentionally. The search_memory tool
    # appends to this same list during the agent session. list(notes_consulted) in the
    # inner function creates a snapshot at *call time* — after search_memory has run —
    # not at factory-creation time (when the list is still empty). Do not rebind to a
    # static copy here; doing so would always log an empty notes_consulted list.
    _notes_ref = notes_consulted  # explicit rebind for clarity; same object, same semantics
    def add_todo_logged(
        title: str,
        date_expression: str = None,
        notes: str = None,
        owner: str = None,
        priority: str = None,
        recurrence: str = None,
        location: str = None,
        urgency: str = None,
        assignee: str = None,
        source_email_id: str = None,
        reasoning: str = None,
    ):
        """Add a to-do item to the shared household Google Doc.

        Args:
            title: The to-do item title.
            date_expression: Exact date phrase, e.g. 'next Tuesday', 'May 15'. Null if no date.
            notes: Optional extra context.
            owner: Who is responsible - husband, wife, or both.
            priority: Task priority - high or normal.
            recurrence: How often it repeats - none, daily, weekly, monthly, or yearly.
            location: Where this task takes place, if relevant.
            urgency: Notes on urgency or timing.
            assignee: Email of the assignee (dcjohnston1@gmail.com for Dan, emily.osteen.johnston@gmail.com for Emily).
            source_email_id: ID of the source email if this task came from an email.
            reasoning: Why this task is being added and why assigned to that person. Always provide this.
        """
        # Check deleted-tasks list before calling add_todo
        _deleted = read_json('saucer-deleted-tasks.json', [])
        from datetime import timedelta, timezone as _tz_agent
        _cutoff_a = datetime.now(_tz_agent.utc) - timedelta(days=30)
        _norm_a = title.strip().lower()
        if any(
            e['title'] == _norm_a
            and datetime.fromisoformat(e['deleted_at']) > _cutoff_a
            for e in _deleted
        ):
            print(f"[agent] skipping re-add of deleted task: {title!r}")
            return {'status': 'skipped', 'reason': 'recently_deleted'}

        result = add_todo(
            title=title, date_expression=date_expression, notes=notes,
            owner=owner, priority=priority, recurrence=recurrence,
            location=location, urgency=urgency,
            assignee=assignee if assignee else 'unassigned',
            source_email_id=source_email_id,
            source='ai-suggested',
        )
        if result.get('status') == 'ok':
            agent_state['tasks_added'] += 1
            log_action('agent', 'task_added', {'title': title, 'assignee': assignee},
                       actor='gemini', reasoning=reasoning)
            dec_id = _log_gemini_decision_sync(
                action_type='task_added',
                input_context='morning agent review',
                context_consulted=context_available,
                decision_made=f"Added task '{title}'" + (f" assigned to {assignee}" if assignee else ""),
                reasoning=reasoning or '',
                user_email='agent',
                full_prompt=full_prompt,
                tool_arguments={'title': title, 'date_expression': date_expression, 'assignee': assignee, 'reasoning': reasoning},
                notes_consulted=list(_notes_ref) if _notes_ref is not None else None,
            )
            if dec_id:
                agent_state['decision_ids'].append(dec_id)
        return result
    return add_todo_logged


def _make_agent_reassign(agent_state: dict, context_available: str, full_prompt: str = None, notes_consulted: list = None):
    _notes_ref = notes_consulted  # snapshot semantics: see _make_agent_add_todo comment
    def reassign_task(title: str, new_assignee: str, reasoning: str = None):
        """Reassign an existing task in the Google Doc to a different household member.

        Args:
            title: The exact title of the task to reassign (case-insensitive).
            new_assignee: Email of the new assignee.
            reasoning: Why you are reassigning this task. Always provide this.
        """
        from gdocs import update_task_assignee
        if not update_task_assignee(title, new_assignee):
            return {'status': 'error', 'message': f"Task '{title}' not found."}
        log_action('agent', 'task_reassigned', {'title': title, 'new_assignee': new_assignee},
                   actor='gemini', reasoning=reasoning)
        dec_id = _log_gemini_decision_sync(
            action_type='task_reassigned',
            input_context='morning agent review',
            context_consulted=context_available,
            decision_made=f"Reassigned task '{title}' to {new_assignee}",
            reasoning=reasoning or '',
            user_email='agent',
            full_prompt=full_prompt,
            tool_arguments={'title': title, 'new_assignee': new_assignee, 'reasoning': reasoning},
            notes_consulted=list(_notes_ref) if _notes_ref is not None else None,
        )
        if dec_id:
            agent_state['decision_ids'].append(dec_id)
        return {'status': 'ok', 'message': f"Task '{title}' reassigned to {new_assignee}."}
    return reassign_task


def _make_agent_dismiss_email(agent_state: dict, full_prompt: str = None, notes_consulted: list = None):
    _notes_ref = notes_consulted  # snapshot semantics: see _make_agent_add_todo comment
    def dismiss_email(email_id: str, reasoning: str = None):
        """Dismiss an email so it won't appear in the inbox.

        Args:
            email_id: The ID of the email to dismiss.
            reasoning: Why this email is being dismissed. Always provide this.
        """
        dismissed = read_json('saucer-dismissed.json', [])
        if email_id not in dismissed:
            dismissed.append(email_id)
            write_json('saucer-dismissed.json', dismissed)
        agent_state['emails_dismissed'] += 1
        log_action('agent', 'email_dismissed', {'email_id': email_id},
                   actor='gemini', reasoning=reasoning)
        try:
            dec_id = _log_gemini_decision_sync(
                action_type='email_dismissed',
                input_context='morning agent review',
                context_consulted='task list, user roles and preferences, household profile, per-user task counts, calendar events (next 7 days)',
                decision_made=f"Dismissed email {email_id}",
                reasoning=reasoning or '',
                user_email='agent',
                full_prompt=full_prompt,
                tool_arguments={'email_id': email_id, 'reasoning': reasoning},
                notes_consulted=list(_notes_ref) if _notes_ref is not None else None,
            )
            if dec_id:
                agent_state['decision_ids'].append(dec_id)
        except Exception as e:
            print(f'[agent] dismiss_email decision log failed: {e}', file=sys.stderr)
        return {'status': 'ok', 'message': f"Email {email_id} dismissed."}
    return dismiss_email


def _make_agent_save_note():
    def save_note_agent(topic: str, content: str):
        """Save a household note based on something learned from an email.

        Call this when an overnight email reveals household facts worth keeping:
        a recurring appointment, a family member mentioned, a preference stated.
        Write the note in warm, first-person prose. Do not save sensitive details.

        Args:
            topic: Short descriptive name (e.g. 'school schedule', 'recurring bills').
            content: What you learned, in natural prose.
        """
        from memory import save_note
        return save_note(topic, content)
    return save_note_agent


def _make_agent_search_memory(notes_consulted: list):
    def search_memory_agent(query: str):
        """Search Hana's notes for household context relevant to a query.

        Call this before assigning a task, deciding who handles a responsibility,
        or when you need household context not present in the system prompt.

        Args:
            query: A few words describing what you're looking for
                   (e.g. 'school pickup', 'food allergies', 'Dan preferences').
        """
        from memory import search_memory
        results = search_memory(query)
        try:
            for r in results:
                notes_consulted.append({
                    'topic': r.get('topic', ''),
                    'content_hash': hashlib.sha256(r.get('content', '').encode()).hexdigest()[:16],
                })
        except Exception as e:
            print(f'[agent] notes_consulted tracking failed: {e}', file=sys.stderr)
        return results
    return search_memory_agent


def _make_agent_queue_question():
    def queue_question_agent(question: str, context: str, priority: str = "normal"):
        """Queue a question for Hana to ask the household.

        Call this when you hit a genuine knowledge gap that would help you do your
        job better -- who handles a certain responsibility, what a recurring sender
        means, what a family member's schedule looks like. Only call once per run;
        a higher-priority question will replace a lower-priority one.

        Args:
            question: The natural-language question to ask (shown to the user).
            context: Internal reasoning for why this matters (not shown to user).
            priority: 'high' or 'normal'. Use 'high' only for urgent gaps.
        """
        from memory import queue_question
        return queue_question(question, context, priority)
    return queue_question_agent


def _make_agent_draft_reply(agent_state: dict, user_id: str = None, full_prompt: str = None, notes_consulted: list = None):
    _notes_ref = notes_consulted  # snapshot semantics: see _make_agent_add_todo comment
    def draft_reply_logged(
        to: str,
        subject: str,
        body: str,
        reasoning: str = None,
        source_email_id: str = None,
        thread_id: str = None,
        in_reply_to_message_id: str = None,
    ):
        """Draft a reply to an email on behalf of the household.

        Call this when an email clearly warrants a response and you have enough
        context to draft a useful reply. The draft goes to Gmail Drafts for human
        review -- it is NOT sent automatically.

        Only draft replies to emails that require a direct response: RSVPs,
        scheduling requests, questions directed at the household, or action items.
        Do NOT draft replies to newsletters, marketing, automated notifications,
        or ambiguous emails. When in doubt, do not draft.

        Args:
            to: Recipient email address.
            subject: Subject line (typically 'Re: <original subject>').
            body: Full reply body. Write in a natural, friendly household tone.
            reasoning: Why this reply is warranted. Always provide this.
            source_email_id: ID of the email being replied to.
            thread_id: Gmail thread ID for threading the draft (if available).
            in_reply_to_message_id: Gmail message ID for the In-Reply-To header.
        """
        from gmail_drafts import create_gmail_draft
        from pending_actions import enqueue_pending_action
        from actions import get_action
        from task_queue import enqueue_action

        result = create_gmail_draft(
            to=to,
            subject=subject,
            body=body,
            in_reply_to_message_id=in_reply_to_message_id,
            thread_id=thread_id,
        )

        # Resolve user_id: use the closure-captured value, fall back to _DAN.
        _uid = user_id or _DAN

        action_meta = get_action('gmail_draft')
        # The ActionClass registry does not score individual instances — the agent
        # decided to call draft_reply, which is itself a high-confidence act.
        # Use 0.8 as the runtime confidence for gmail_draft actions created by the
        # agent session. This exceeds the default 0.7 threshold in config/limits.
        action_confidence = 0.8
        pending_id = enqueue_pending_action(
            user_id=_uid,
            action_type='gmail_draft',
            payload={
                'to': to,
                'subject': subject,
                'body_preview': body[:200],
                'draft_id': result.get('draft_id'),
                'source_email_id': source_email_id,
            },
            confidence=action_confidence,
            email_id=source_email_id,
        )

        # Enqueue into Cloud Tasks for reliable, retryable execution tracking.
        # Build a lightweight action object that task_queue.enqueue_action expects.
        if pending_id:
            class _ActionRef:
                pass
            _action_ref = _ActionRef()
            _action_ref.action_id = pending_id
            _action_ref.confidence = action_confidence
            _action_ref.action_type = 'gmail_draft'
            enqueue_action(_uid, _action_ref)

        log_action(
            'agent',
            'gmail_draft_created',
            {
                'to': to,
                'subject': subject,
                'draft_id': result.get('draft_id'),
                'pending_action_id': pending_id,
                'source_email_id': source_email_id,
            },
            actor='gemini',
            reasoning=reasoning,
        )

        dec_id = _log_gemini_decision_sync(
            action_type='gmail_draft_created',
            input_context='email draft generation',
            context_consulted='',
            decision_made=f"Drafted reply to {to}: {subject}",
            reasoning=reasoning or '',
            full_prompt=full_prompt,
            tool_arguments={
                'to': to,
                'subject': subject,
                'reasoning': reasoning,
                'source_email_id': source_email_id,
            },
            notes_consulted=list(_notes_ref) if _notes_ref is not None else None,
        )
        if dec_id:
            agent_state['decision_ids'].append(dec_id)

        print(
            f"[agent] gmail_draft_created to={to} subject={subject!r} "
            f"draft_id={result.get('draft_id')} status={result.get('status')}",
            file=sys.stderr,
        )
        return {
            'status': result.get('status'),
            'draft_id': result.get('draft_id'),
            'pending_action_id': pending_id,
        }
    return draft_reply_logged


def _make_write_briefing(db, agent_state: dict, overnight_emails: list):
    def write_briefing(dan_message: str, emily_message: str, briefing_assertions: list = None):
        """Write and store the morning briefing. Call this when you have finished reviewing all emails.

        Args:
            dan_message: Morning message for Dan. Warm, direct, 3-6 sentences.
            emily_message: Morning message for Emily. Warm, direct, 3-6 sentences.
            briefing_assertions: Optional list of structured claims made in the briefing.
                Each entry is an object with:
                  - person: "dan" or "emily"
                  - claim_type: "task_assignment", "email_detail", or "reminder"
                  - text: the claim as written in the briefing
                  - source: "email" (you read it in an email) or "hana_decision" (you called add_todo/reassign_task)
                  - decision_id: the Firestore gemini_decisions doc ID if source is "hana_decision", else null
                For each person-specific fact in the briefing, add an entry here.
                Use source="email" if you are reporting something from an email you read.
                Use source="hana_decision" with the decision_id if you are reporting a task you added or reassigned.
        """
        briefing_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        doc = {
            'briefing_id': briefing_id,
            'date': now.strftime('%Y-%m-%d'),
            'dan_message': dan_message,
            'emily_message': emily_message,
            'decisions_made': agent_state.get('decision_ids', []),
            'emails_processed': len(overnight_emails),
            'tasks_added': agent_state.get('tasks_added', 0),
            'timestamp': now,
            'dan_seen': False,
            'emily_seen': False,
        }
        if briefing_assertions:
            doc['briefing_assertions'] = briefing_assertions
        db.collection('morning_briefings').document(briefing_id).set(doc)
        agent_state['briefing_id'] = briefing_id
        print(
            f"[agent] Briefing written: {briefing_id} "
            f"tasks={agent_state['tasks_added']} "
            f"dismissed={agent_state['emails_dismissed']} "
            f"assertions={len(briefing_assertions) if briefing_assertions else 0}"
        )
        return {'status': 'ok', 'briefing_id': briefing_id}
    return write_briefing


def process_single_email(email: dict) -> str:
    """Process one qualifying inbound email and write/update the briefing.

    Called from the Pub/Sub webhook handler in a background thread.
    Returns the briefing_id written to Firestore (or 'no-briefing-written').
    """
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    db = _firestore.Client(project=_PROJECT)

    from gdocs import read_doc
    doc_contents = read_doc()
    today = datetime.now(_tz())

    user_context = _load_user_context()
    household_profile = _load_household_profile(_DAN)
    task_load = _parse_task_load(doc_contents)
    calendar_ctx = _load_calendar_context(today)
    gemini_decisions_ctx = _load_recent_gemini_decisions(_DAN)

    context_available = (
        'task list, user roles and preferences, household profile, '
        'per-user task counts, calendar events (next 7 days)'
    )

    date_line = f"TODAY: {today.strftime('%A, %B %-d, %Y')}"
    email_block = _format_emails_for_agent([email])

    full_system = SINGLE_EMAIL_SYSTEM_PROMPT + f"\n\n{date_line}"
    if user_context:
        full_system += f"\n\n{user_context}"
    if household_profile:
        full_system += f"\n\n{household_profile}"
    full_system += f"\n\n{task_load}"
    if calendar_ctx:
        full_system += f"\n\n{calendar_ctx}"
    if gemini_decisions_ctx:
        full_system += f"\n\n{gemini_decisions_ctx}"
    full_system += f"\n\nCURRENT DOC CONTENTS:\n{doc_contents}"
    full_system += f"\n\nINBOUND EMAIL:\n{email_block}"

    agent_state = {
        'briefing_id': None,
        'tasks_added': 0,
        'emails_dismissed': 0,
        'decision_ids': [],
    }

    notes_consulted = []
    add_todo_tool = _make_agent_add_todo(agent_state, context_available, full_system, notes_consulted)
    reassign_tool = _make_agent_reassign(agent_state, context_available, full_system, notes_consulted)
    dismiss_tool = _make_agent_dismiss_email(agent_state, full_system, notes_consulted)
    search_memory_tool = _make_agent_search_memory(notes_consulted)
    draft_reply_tool = _make_agent_draft_reply(agent_state, user_id=_DAN, full_prompt=full_system, notes_consulted=notes_consulted)
    write_briefing_tool = _make_write_briefing(db, agent_state, [email])
    save_note_tool = _make_agent_save_note()
    queue_question_tool = _make_agent_queue_question()

    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=full_system,
        tools=[add_todo_tool, reassign_tool, dismiss_tool, draft_reply_tool,
               write_briefing_tool, save_note_tool, search_memory_tool, queue_question_tool],
    )

    chat = model.start_chat(enable_automatic_function_calling=True)
    chat.send_message("Process this email.")

    briefing_id = agent_state.get('briefing_id') or 'no-briefing-written'
    print(f"[agent] process_single_email done. subject='{email.get('subject')}' briefing_id={briefing_id}")
    return briefing_id


def run_morning_agent() -> str:
    """Run the morning review agent and return the briefing_id."""
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    db = _firestore.Client(project=_PROJECT)

    config = read_json('saucer-config.json', {})
    last_run_ts = config.get('last_agent_run')
    now_utc = datetime.now(timezone.utc)

    since_dt = (
        datetime.fromtimestamp(last_run_ts, tz=timezone.utc)
        if last_run_ts
        else now_utc - timedelta(hours=12)
    )

    print(f"[agent] Overnight window: {since_dt.isoformat()} → {now_utc.isoformat()}")

    all_emails = _email_store.list_emails(
        limit=2000,
        exclude_dismissed=False,
        exclude_reviewed=False,
        exclude_blocked_verdict=False,
        include_body=True,
    )
    overnight_emails = [
        e for e in all_emails
        if _parse_email_date(e.get('date', '')) > since_dt
    ]
    print(f"[agent] {len(overnight_emails)} overnight emails out of {len(all_emails)} total")

    from gdocs import read_doc
    doc_contents = read_doc()
    today = datetime.now(_tz())

    user_context = _load_user_context()
    household_profile = _load_household_profile(_DAN)
    task_load = _parse_task_load(doc_contents)
    calendar_ctx = _load_calendar_context(today)
    action_history = _load_action_history_extended()
    action_summary = get_action_summary()
    gemini_decisions_ctx = _load_recent_gemini_decisions(_DAN)

    context_available = (
        'task list, user roles and preferences, household profile, '
        'per-user task counts, calendar events (next 7 days), '
        'action history (10 per user)'
    )

    date_line = f"TODAY: {today.strftime('%A, %B %-d, %Y')}"
    full_system = AGENT_SYSTEM_PROMPT + f"\n\n{date_line}"
    if user_context:
        full_system += f"\n\n{user_context}"
    if household_profile:
        full_system += f"\n\n{household_profile}"
    if action_summary:
        full_system += f"\n\nRECENT HOUSEHOLD ACTIVITY:\n{action_summary}"
    full_system += f"\n\n{task_load}"
    if calendar_ctx:
        full_system += f"\n\n{calendar_ctx}"
    if action_history:
        full_system += f"\n\n{action_history}"
    if gemini_decisions_ctx:
        full_system += f"\n\n{gemini_decisions_ctx}"
    full_system += f"\n\nCURRENT DOC CONTENTS:\n{doc_contents}"

    if overnight_emails:
        email_block = _format_emails_for_agent(overnight_emails)
        full_system += f"\n\nOVERNIGHT EMAILS ({len(overnight_emails)} new since last run):\n{email_block}"
    else:
        full_system += "\n\nOVERNIGHT EMAILS: None — no new emails since the last run."

    agent_state = {
        'briefing_id': None,
        'tasks_added': 0,
        'emails_dismissed': 0,
        'decision_ids': [],
    }

    notes_consulted = []
    add_todo_tool = _make_agent_add_todo(agent_state, context_available, full_system, notes_consulted)
    reassign_tool = _make_agent_reassign(agent_state, context_available, full_system, notes_consulted)
    dismiss_tool = _make_agent_dismiss_email(agent_state, full_system, notes_consulted)
    search_memory_tool = _make_agent_search_memory(notes_consulted)
    draft_reply_tool = _make_agent_draft_reply(agent_state, user_id=_DAN, full_prompt=full_system, notes_consulted=notes_consulted)
    write_briefing_tool = _make_write_briefing(db, agent_state, overnight_emails)
    save_note_tool = _make_agent_save_note()
    queue_question_tool = _make_agent_queue_question()

    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=full_system,
        tools=[add_todo_tool, reassign_tool, dismiss_tool, draft_reply_tool,
               write_briefing_tool, save_note_tool, search_memory_tool, queue_question_tool],
    )

    chat = model.start_chat(enable_automatic_function_calling=True)
    chat.send_message("Run the morning review.")

    config['last_agent_run'] = now_utc.timestamp()
    write_json('saucer-config.json', config)

    briefing_id = agent_state.get('briefing_id') or 'no-briefing-written'
    print(f"[agent] Done. briefing_id={briefing_id}")
    return briefing_id
