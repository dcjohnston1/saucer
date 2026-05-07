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

import os
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import google.generativeai as genai
from google.cloud import firestore as _firestore

from gcs import read_json, write_json
from logger import log_action, get_action_summary
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


AGENT_SYSTEM_PROMPT = """You are Saucer running your morning review. No user is present. Your job:

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
                               user_email=None) -> str:
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
        _, ref = db.collection('gemini_decisions').add(doc_data)
        return ref.id
    except Exception as e:
        print(f'[agent] log_gemini_decision_sync failed: {e}')
        return ''


def _make_agent_add_todo(agent_state: dict, context_available: str):
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
        result = add_todo(
            title=title, date_expression=date_expression, notes=notes,
            owner=owner, priority=priority, recurrence=recurrence,
            location=location, urgency=urgency, assignee=assignee,
            source_email_id=source_email_id,
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
            )
            if dec_id:
                agent_state['decision_ids'].append(dec_id)
        return result
    return add_todo_logged


def _make_agent_reassign(agent_state: dict, context_available: str):
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
        )
        if dec_id:
            agent_state['decision_ids'].append(dec_id)
        return {'status': 'ok', 'message': f"Task '{title}' reassigned to {new_assignee}."}
    return reassign_task


def _make_agent_dismiss_email(agent_state: dict):
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
        return {'status': 'ok', 'message': f"Email {email_id} dismissed."}
    return dismiss_email


def _make_write_briefing(db, agent_state: dict, overnight_emails: list):
    def write_briefing(dan_message: str, emily_message: str):
        """Write and store the morning briefing. Call this when you have finished reviewing all emails.

        Args:
            dan_message: Morning message for Dan. Warm, direct, 3-6 sentences.
            emily_message: Morning message for Emily. Warm, direct, 3-6 sentences.
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
        db.collection('morning_briefings').document(briefing_id).set(doc)
        agent_state['briefing_id'] = briefing_id
        print(
            f"[agent] Briefing written: {briefing_id} "
            f"tasks={agent_state['tasks_added']} "
            f"dismissed={agent_state['emails_dismissed']}"
        )
        return {'status': 'ok', 'briefing_id': briefing_id}
    return write_briefing


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

    all_emails = read_json('saucer-emails.json', [])
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

    add_todo_tool = _make_agent_add_todo(agent_state, context_available)
    reassign_tool = _make_agent_reassign(agent_state, context_available)
    dismiss_tool = _make_agent_dismiss_email(agent_state)
    write_briefing_tool = _make_write_briefing(db, agent_state, overnight_emails)

    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=full_system,
        tools=[add_todo_tool, reassign_tool, dismiss_tool, write_briefing_tool],
    )

    chat = model.start_chat(enable_automatic_function_calling=True)
    chat.send_message("Run the morning review.")

    config['last_agent_run'] = now_utc.timestamp()
    write_json('saucer-config.json', config)

    briefing_id = agent_state.get('briefing_id') or 'no-briefing-written'
    print(f"[agent] Done. briefing_id={briefing_id}")
    return briefing_id
