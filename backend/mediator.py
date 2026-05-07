import os
import google.generativeai as genai
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import dateparser

from prompts import SYSTEM_PROMPT
from gdocs import read_doc, append_to_doc
from gcs import read_json, write_json
from logger import get_action_summary, log_action, log_gemini_decision

# Configure Gemini
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

def _tz():
    return ZoneInfo("America/Los_Angeles")


def _today():
    return datetime.now(_tz()).date()


WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _next_weekday(today, target_dow, at_least_days=1):
    """Return the next date with the given day-of-week, at least `at_least_days` ahead."""
    days_ahead = (target_dow - today.weekday()) % 7
    if days_ahead < at_least_days:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def resolve_date(expr):
    """
    Returns (status, value) where status is one of:
      "none"      — no date given
      "date"      — single ISO date string
      "range"     — ISO range string "YYYY-MM-DD..YYYY-MM-DD"
      "ambiguous" — could not resolve, value is the original expression
    """
    if not expr or not expr.strip():
        return ("none", None)

    today = _today()
    lower = expr.lower().strip()

    # today / tonight
    if lower in ("today", "tonight"):
        return ("date", today.isoformat())

    # tomorrow
    if lower in ("tomorrow", "tmrw"):
        return ("date", (today + timedelta(days=1)).isoformat())

    # weekend phrases
    if "next weekend" in lower:
        days_to_sat = (5 - today.weekday()) % 7
        if days_to_sat == 0:
            days_to_sat = 7
        sat = today + timedelta(days=days_to_sat + 7)
        return ("range", f"{sat.isoformat()}..{(sat + timedelta(days=1)).isoformat()}")

    if "this weekend" in lower or "the weekend" in lower:
        days_to_sat = (5 - today.weekday()) % 7
        if days_to_sat == 0:
            days_to_sat = 7
        sat = today + timedelta(days=days_to_sat)
        return ("range", f"{sat.isoformat()}..{(sat + timedelta(days=1)).isoformat()}")

    # "next <weekday>" — always the occurrence in the NEXT week
    if lower.startswith("next "):
        candidate = lower[5:].strip()
        if candidate in WEEKDAY_NAMES:
            target_dow = WEEKDAY_NAMES.index(candidate)
            d = _next_weekday(today, target_dow, at_least_days=1)
            # Ensure it's truly "next week" (at least 7 days if that day is coming soon)
            if (d - today).days <= 6 and d.weekday() != today.weekday():
                d = _next_weekday(today, target_dow, at_least_days=7)
            return ("date", d.isoformat())

    # "this <weekday>" — the coming occurrence; ambiguous if already passed this week
    if lower.startswith("this "):
        candidate = lower[5:].strip()
        if candidate in WEEKDAY_NAMES:
            target_dow = WEEKDAY_NAMES.index(candidate)
            if target_dow < today.weekday():
                return ("ambiguous", expr)
            d = _next_weekday(today, target_dow, at_least_days=0)
            return ("date", d.isoformat())

    # Fallback: dateparser for explicit dates like "May 5", "April 30", "in 3 days"
    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": False,
        "TIMEZONE": "America/Los_Angeles",
    }
    parsed = dateparser.parse(expr, settings=settings)
    if parsed is None:
        return ("ambiguous", expr)

    return ("date", parsed.date().isoformat())


def _human_readable(status, value):
    if status == "none":
        return "no due date"
    if status == "range":
        start, end = value.split("..")
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end)
        return f"{s.strftime('%A %B %-d')} – {e.strftime('%A %B %-d, %Y')}"
    if status == "date":
        d = datetime.fromisoformat(value)
        return d.strftime("%A, %B %-d, %Y")
    return value


def add_todo(title: str, date_expression: str = None, notes: str = None,
             owner: str = None, priority: str = None, recurrence: str = None,
             location: str = None, urgency: str = None, assignee: str = None,
             source_email_id: str = None):
    """Add a to-do item to the shared household Google Doc.

    Args:
        title: The to-do item title.
        date_expression: The user's exact date phrase, e.g. 'this weekend', 'next Tuesday', 'tomorrow'. Null if no date was given.
        notes: Optional extra context or notes.
        owner: Who is responsible - husband, wife, or both.
        priority: Task priority level - high or normal.
        recurrence: How often this task repeats - none, daily, weekly, monthly, or yearly.
        location: Where this task takes place, if relevant.
        urgency: Notes on urgency or timing flexibility.
    """
    status, value = resolve_date(date_expression)
    today = _today()

    if status == "ambiguous":
        return {
            "status": "ambiguous",
            "expression": value,
            "message": f"Could not resolve '{value}' to a specific date."
        }
    else:
        added = today.strftime("%Y-%m-%d")
        due = value if status in ("date", "range") else "none"
        append_to_doc(title, due, added, notes, owner, priority, recurrence, location, urgency, assignee, source_email_id=source_email_id)
        human = _human_readable(status, value)
        return {
            "status": "ok",
            "due": due,
            "human_readable": human
        }


def search_emails(query: str, limit: int = 3):
    """Search household emails by keyword, sender name, or subject.

    Args:
        query: Search term — sender name, subject keyword, or topic (e.g. "Brenda Bennett", "STAR testing", "Procare").
        limit: Maximum number of emails to return. Default 3.
    """
    emails = read_json('saucer-emails.json', default=[])
    q = query.lower()
    matches = []
    for e in emails:
        haystack = ' '.join([
            e.get('sender', ''),
            e.get('subject', ''),
            e.get('body', '') or e.get('snippet', ''),
        ]).lower()
        tokens = q.split()
        if all(t in haystack for t in tokens):
            matches.append(e)
    matches.sort(key=lambda e: e.get('date', ''), reverse=True)
    results = matches[:limit]
    if not results:
        return {"results": [], "message": f"No emails found matching '{query}'."}
    formatted = []
    for e in results:
        body = (e.get('body', '') or e.get('snippet', ''))[:2000]
        attachments = [a.get('filename', '') for a in e.get('attachments', [])]
        formatted.append({
            "date": e.get('date', ''),
            "sender": e.get('sender', ''),
            "subject": e.get('subject', ''),
            "body": body,
            "attachments": attachments,
        })
    return {"results": formatted}


def _load_user_context():
    from google.cloud import firestore as _fs
    db = _fs.Client(project='mediationmate')
    users = [
        ('dcjohnston1@gmail.com', 'Dan'),
        ('emily.osteen.johnston@gmail.com', 'Emily'),
    ]
    lines = []
    for email, name in users:
        doc = db.collection('user_settings').document(email).get()
        if not doc.exists:
            continue
        data = doc.to_dict()
        roles = data.get('roles', [])
        prefs = data.get('preferences', [])
        if roles or prefs:
            lines.append(f"{name} ({email}):")
            if roles:
                lines.append(f"  Roles: {'; '.join(roles)}")
            if prefs:
                lines.append(f"  Preferences: {'; '.join(prefs)}")
    if lines:
        return "HOUSEHOLD MEMBER CONTEXT:\n" + "\n".join(lines)
    return ""


def _load_household_profile(user_email):
    try:
        from google.cloud import firestore as _fs
        db = _fs.Client(project='mediationmate')
        doc = db.collection('household_profile').document(user_email).get()
        if not doc.exists:
            return ""
        data = doc.to_dict()
        lines = ["HOUSEHOLD PROFILE:"]
        if data.get('family_members'):
            lines.append(f"  Family: {data['family_members']}")
        if data.get('shopping_habits'):
            lines.append(f"  Shopping: {data['shopping_habits']}")
        if data.get('role_division'):
            lines.append(f"  Roles: {data['role_division']}")
        if data.get('communication_preferences'):
            lines.append(f"  Communication: {data['communication_preferences']}")
        return "\n".join(lines) if len(lines) > 1 else ""
    except Exception as e:
        print(f"[mediator] household profile error: {e}")
        return ""


def _load_recent_context(user_email):
    try:
        from conversation_history import get_recent_history
        recent = get_recent_history(user_email, limit=5)
        if not recent:
            return ""
        lines = ["RECENT CONVERSATIONS (last 5):"]
        for c in recent:
            ts = c.get('timestamp', '')[:10]
            if c.get('archived') and c.get('summary'):
                lines.append(f"  [{ts}] {c['summary']}")
            else:
                msg = c.get('message', '')[:120]
                reply = c.get('bot_response', '')[:120]
                lines.append(f"  [{ts}] You: {msg} → Saucer: {reply}")
        return "\n".join(lines)
    except Exception as e:
        print(f"[mediator] recent context error: {e}")
        return ""


def _make_search_history_tool(user_email):
    def search_conversation_history(keyword: str, days_back: int = 30) -> dict:
        """Search past conversations for a specific topic, name, or decision.

        Args:
            keyword: The topic, name, or phrase to search for (e.g. "camping trip", "Julia", "dentist").
            days_back: How many days back to search. Default 30.
        """
        from conversation_history import search_history
        results = search_history(user_email, keyword, days_back)
        if not results:
            return {"results": [], "message": f"No past conversations found about '{keyword}'."}
        formatted = []
        for c in results:
            ts = c.get('timestamp', '')[:10]
            if c.get('archived') and c.get('summary'):
                formatted.append({"date": ts, "summary": c['summary']})
            else:
                formatted.append({
                    "date": ts,
                    "you_said": c.get('message', ''),
                    "saucer_said": c.get('bot_response', ''),
                })
        return {"results": formatted}
    return search_conversation_history


def _parse_task_load(doc_contents: str) -> str:
    """Count open TODO items per assignee from the Google Doc text."""
    _name_map = {
        'dcjohnston1@gmail.com': 'Dan',
        'emily.osteen.johnston@gmail.com': 'Emily',
    }
    counts = {}
    unassigned = 0
    for line in doc_contents.split('\n'):
        if not line.strip() or not line.startswith('TODO'):
            continue
        assignee = None
        for part in line.split('|'):
            part = part.strip()
            if part.startswith('assignee:'):
                assignee = part[9:].strip()
                break
        if assignee:
            name = _name_map.get(assignee, assignee)
            counts[name] = counts.get(name, 0) + 1
        else:
            unassigned += 1
    lines = ['TASK LOAD SUMMARY:']
    for name in ['Dan', 'Emily']:
        n = counts.get(name, 0)
        lines.append(f"  {name}: {n} open task{'s' if n != 1 else ''}")
    if unassigned:
        lines.append(f"  Unassigned: {unassigned} open task{'s' if unassigned != 1 else ''}")
    return '\n'.join(lines)


def _load_calendar_context(today: datetime) -> str:
    """Fetch the next 7 days of calendar events for Dan and Emily."""
    try:
        from gcalendar import get_events
        start_iso = today.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_iso = (today + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
        lines = ['CALENDAR — NEXT 7 DAYS:']

        try:
            events = get_events(start_iso, end_iso)
            if events:
                lines.append("  Dan's calendar:")
                for e in events[:10]:
                    lines.append(f"    • {(e['start'] or '')[:10]}: {e['title']}")
            else:
                lines.append("  Dan's calendar: no events this week")
        except Exception:
            lines.append("  Dan's calendar: unavailable")

        try:
            events = get_events(start_iso, end_iso, calendar_id='emily.osteen.johnston@gmail.com')
            if events:
                lines.append("  Emily's calendar:")
                for e in events[:10]:
                    lines.append(f"    • {(e['start'] or '')[:10]}: {e['title']}")
            else:
                lines.append("  Emily's calendar: no events this week")
        except Exception:
            lines.append("  Emily's calendar: not yet connected")

        return '\n'.join(lines)
    except Exception as e:
        print(f'[mediator] calendar context error: {e}')
        return ''


def _load_action_history() -> str:
    """Return the last 5 meaningful actions per user as readable bullet points."""
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
        users = [
            ('dcjohnston1@gmail.com', 'Dan'),
            ('emily.osteen.johnston@gmail.com', 'Emily'),
        ]
        lines = ['RECENT INDIVIDUAL ACTIONS:']
        for email, name in users:
            actions = get_recent_actions(user=email, limit=20)
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
                if shown >= 5:
                    break
        return '\n'.join(lines) if len(lines) > 1 else ''
    except Exception as e:
        print(f'[mediator] action history error: {e}')
        return ''


def _make_add_todo_tool(user_email: str, user_message: str = '', context_available: str = ''):
    """Return an add_todo function instrumented with Gemini decision logging."""
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
            date_expression: The user's exact date phrase, e.g. 'this weekend', 'next Tuesday', 'tomorrow'. Null if no date was given.
            notes: Optional extra context or notes.
            owner: Who is responsible - husband, wife, or both.
            priority: Task priority level - high or normal.
            recurrence: How often this task repeats - none, daily, weekly, monthly, or yearly.
            location: Where this task takes place, if relevant.
            urgency: Notes on urgency or timing flexibility.
            assignee: Email address of the person to assign this task to (dcjohnston1@gmail.com for Dan, emily.osteen.johnston@gmail.com for Emily).
            source_email_id: ID of the source email if this task originated from an email.
            reasoning: Brief explanation of why you are adding this task and, if assigning it, why to that specific person. Always provide this.
        """
        result = add_todo(
            title=title,
            date_expression=date_expression,
            notes=notes,
            owner=owner,
            priority=priority,
            recurrence=recurrence,
            location=location,
            urgency=urgency,
            assignee=assignee,
            source_email_id=source_email_id,
        )

        if result.get('status') == 'ok':
            log_action(
                user_email,
                'task_added',
                {'title': title, 'assignee': assignee},
                actor='gemini',
                reasoning=reasoning,
            )
            decision_made = f"Added task '{title}'"
            if assignee:
                decision_made += f" assigned to {assignee}"
            log_gemini_decision(
                action_type='task_added',
                input_context=user_message[:500],
                context_consulted=context_available,
                decision_made=decision_made,
                reasoning=reasoning or '',
                confidence='medium',
                user_email=user_email,
            )

        return result

    return add_todo_logged


def _make_reassign_task_tool(user_email: str, user_message: str = '', context_available: str = ''):
    def reassign_task(title: str, new_assignee: str, reasoning: str = None):
        """Reassign an existing task in the Google Doc to a different household member.

        Args:
            title: The exact title of the task to reassign (case-insensitive match).
            new_assignee: Email address of the new assignee (dcjohnston1@gmail.com for Dan, emily.osteen.johnston@gmail.com for Emily).
            reasoning: Explanation of why you are reassigning — reference roles, task load, or calendar. Always provide this.
        """
        from gdocs import update_task_assignee
        if not update_task_assignee(title, new_assignee):
            return {'status': 'error', 'message': f"Task '{title}' not found in the doc."}
        log_action(
            user_email, 'task_reassigned',
            {'title': title, 'new_assignee': new_assignee},
            actor='gemini', reasoning=reasoning,
        )
        log_gemini_decision(
            action_type='task_reassigned',
            input_context=user_message[:500],
            context_consulted=context_available,
            decision_made=f"Reassigned task '{title}' to {new_assignee}",
            reasoning=reasoning or '',
            confidence='medium',
            user_email=user_email,
        )
        return {'status': 'ok', 'message': f"Task '{title}' reassigned to {new_assignee}."}
    return reassign_task


def _make_complete_task_tool(user_email: str, user_message: str = '', context_available: str = ''):
    def complete_task(title: str, reasoning: str = None):
        """Mark an existing task as complete (DONE) in the Google Doc.

        Args:
            title: The exact title of the task to mark as complete.
            reasoning: Brief note on why you are completing this task if Gemini-initiated. Optional for user-requested completions.
        """
        from gdocs import complete_task as _complete
        _complete(title)
        log_action(
            user_email, 'task_completed',
            {'title': title},
            actor='gemini', reasoning=reasoning,
        )
        if reasoning:
            log_gemini_decision(
                action_type='task_completed',
                input_context=user_message[:500],
                context_consulted=context_available,
                decision_made=f"Marked task '{title}' as complete",
                reasoning=reasoning,
                confidence='high',
                user_email=user_email,
            )
        return {'status': 'ok', 'message': f"Task '{title}' marked as complete."}
    return complete_task


def _load_recent_gemini_decisions(user_email: str) -> str:
    """Inject the last 5 Gemini decisions into the system prompt as readable context."""
    try:
        from logger import get_recent_decisions
        decisions = get_recent_decisions(user_email=user_email, limit=5)
        if not decisions:
            return ''
        lines = ['YOUR RECENT DECISIONS (Gemini-initiated actions):']
        for d in decisions:
            ts = d.get('timestamp', '')[:10]
            action = d.get('decision_made', d.get('action_type', ''))
            reasoning = d.get('reasoning', '')
            lines.append(f'  • [{ts}] {action}')
            if reasoning:
                lines.append(f'    Reasoning: {reasoning}')
        return '\n'.join(lines)
    except Exception as e:
        print(f'[mediator] recent decisions error: {e}')
        return ''


def _make_get_decisions_tool(user_email: str):
    def get_gemini_decisions(limit: int = 5, action_type: str = None):
        """Query your own past decisions from the decision log. Call this when asked 'why did you do X?' or 'what have you decided recently?'

        Args:
            limit: Number of recent decisions to retrieve. Default 5, max 20.
            action_type: Filter by type — 'task_added', 'task_reassigned', or 'task_completed'. Optional.
        """
        try:
            from logger import get_recent_decisions
            decisions = get_recent_decisions(user_email=user_email, action_type=action_type, limit=min(limit, 20))
            if not decisions:
                return {'decisions': [], 'message': 'No recent Gemini decisions found.'}
            return {'decisions': [
                {
                    'timestamp': d.get('timestamp', '')[:16],
                    'action_type': d.get('action_type', ''),
                    'decision_made': d.get('decision_made', ''),
                    'reasoning': d.get('reasoning', ''),
                    'confidence': d.get('confidence', ''),
                }
                for d in decisions
            ]}
        except Exception as e:
            print(f'[mediator] get_gemini_decisions tool error: {e}')
            return {'decisions': [], 'message': f'Error retrieving decisions: {e}'}
    return get_gemini_decisions


def process_message(user, message, history=None, user_email=None, conversation_id=None):
    user_email = user_email or user
    doc_contents = read_doc()
    today = datetime.now(_tz())
    date_line = f"TODAY: {today.strftime('%A, %B %-d, %Y')}"

    user_context = _load_user_context()
    household_profile = _load_household_profile(user_email)
    recent_context = _load_recent_context(user_email)
    action_summary = get_action_summary()
    task_load = _parse_task_load(doc_contents)
    calendar_ctx = _load_calendar_context(today)
    action_history = _load_action_history()
    gemini_decisions_ctx = _load_recent_gemini_decisions(user_email)

    full_system = SYSTEM_PROMPT + f"\n\n{date_line}"
    if user_context:
        full_system += f"\n\n{user_context}"
    if household_profile:
        full_system += f"\n\n{household_profile}"
    if recent_context:
        full_system += f"\n\n{recent_context}"
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

    context_parts = ['task list', "today's date"]
    if user_context:
        context_parts.append('user roles and preferences')
    if household_profile:
        context_parts.append('household profile')
    if recent_context:
        context_parts.append('recent conversations')
    if action_summary:
        context_parts.append('recent activity summary')
    context_parts.append('per-user task counts')
    if calendar_ctx:
        context_parts.append('calendar events (next 7 days)')
    if action_history:
        context_parts.append('individual action history')
    context_available = ', '.join(context_parts)

    chat_history = []
    if history:
        for m in history:
            role = 'user' if m['role'] == 'user' else 'model'
            chat_history.append({'role': role, 'parts': [m['content']]})

    add_todo_tool = _make_add_todo_tool(user_email, message, context_available)
    reassign_tool = _make_reassign_task_tool(user_email, message, context_available)
    complete_tool = _make_complete_task_tool(user_email, message, context_available)
    decisions_tool = _make_get_decisions_tool(user_email)

    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=full_system,
        tools=[add_todo_tool, reassign_tool, complete_tool, decisions_tool, search_emails]
    )

    chat = model.start_chat(history=chat_history, enable_automatic_function_calling=True)
    response = chat.send_message(f"{user}: {message}")

    try:
        tokens = getattr(response.usage_metadata, 'total_token_count', 0) or 0
        if tokens > 0:
            stats = read_json('saucer-stats.json', {})
            stats['lifetime_tokens'] = stats.get('lifetime_tokens', 0) + tokens
            stats['chat_messages'] = stats.get('chat_messages', 0) + 1
            write_json('saucer-stats.json', stats)
    except Exception:
        pass

    # The google.generativeai SDK (deprecated) sometimes returns a response object
    # pointing at an intermediate function-call turn rather than the final text turn.
    # Walk chat.history backwards for the last model turn that actually has text.
    try:
        reply_text = response.text
    except ValueError:
        reply_text = ""
        for turn in reversed(chat.history):
            if turn.role == 'model':
                text = ''.join(getattr(p, 'text', '') or '' for p in turn.parts)
                if text:
                    reply_text = text
                    break
        if not reply_text:
            reply_text = "Hmm, I had trouble with that one. Mind trying again?"

    if conversation_id and reply_text:
        import threading
        from conversation_history import log_conversation
        threading.Thread(
            target=log_conversation,
            args=(user_email, message, reply_text, conversation_id),
            daemon=True,
        ).start()

    return reply_text
