import os
import google.generativeai as genai
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import dateparser

from prompts import SYSTEM_PROMPT
from gdocs import read_doc, append_to_doc
from gcs import read_json, write_json
from logger import get_action_summary

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


def process_message(user, message, history=None):
    doc_contents = read_doc()
    today = datetime.now(_tz())
    date_line = f"TODAY: {today.strftime('%A, %B %-d, %Y')}"

    user_context = _load_user_context()
    full_system = SYSTEM_PROMPT + f"\n\n{date_line}"
    if user_context:
        full_system += f"\n\n{user_context}"
    action_summary = get_action_summary()
    if action_summary:
        full_system += f"\n\nRECENT HOUSEHOLD ACTIVITY:\n{action_summary}"
    full_system += f"\n\nCURRENT DOC CONTENTS:\n{doc_contents}"

    # Convert history to Gemini format
    chat_history = []
    if history:
        for m in history:
            role = 'user' if m['role'] == 'user' else 'model'
            chat_history.append({'role': role, 'parts': [m['content']]})

    # Initialize model with tools
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=full_system,
        tools=[add_todo, search_emails]
    )

    # Start chat with history and automatic function calling
    chat = model.start_chat(history=chat_history, enable_automatic_function_calling=True)

    # Send message
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

    return response.text
