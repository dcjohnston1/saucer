import anthropic
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import dateparser

from prompts import SYSTEM_PROMPT
from gdocs import read_doc, append_to_doc

client = anthropic.Anthropic()

ADD_TODO_TOOL = {
    "name": "add_todo",
    "description": "Add a to-do item to the shared household Google Doc.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The to-do item title."
            },
            "date_expression": {
                "type": "string",
                "description": "The user's exact date phrase, e.g. 'this weekend', 'next Tuesday', 'tomorrow'. Null if no date was given."
            },
            "notes": {
                "type": "string",
                "description": "Optional extra context or notes."
            }
        },
        "required": ["title"]
    }
}


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


def process_message(user, message, history=None):
    doc_contents = read_doc()
    today = datetime.now(_tz())
    date_line = f"TODAY: {today.strftime('%A, %B %-d, %Y')}"

    full_system = SYSTEM_PROMPT + f"\n\n{date_line}\n\nCURRENT DOC CONTENTS:\n{doc_contents}"

    prior = list(history) if history else []
    messages = prior + [{"role": "user", "content": f"{user}: {message}"}]

    # Agentic loop — handles at most one tool call (add_todo)
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=full_system,
            tools=[ADD_TODO_TOOL],
            messages=messages,
        )

        # Collect any text and tool_use blocks
        text_parts = []
        tool_use_block = None
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_use_block = block

        # No tool call — return text response directly
        if tool_use_block is None:
            return " ".join(text_parts).strip()

        # Process the tool call
        tool_input = tool_use_block.input
        title = tool_input.get("title", "")
        date_expr = tool_input.get("date_expression") or ""
        notes = tool_input.get("notes") or None

        status, value = resolve_date(date_expr)

        if status == "ambiguous":
            tool_result = {
                "status": "ambiguous",
                "expression": value,
                "message": f"Could not resolve '{value}' to a specific date."
            }
        else:
            added = today.strftime("%Y-%m-%d")
            due = value if status in ("date", "range") else "none"
            append_to_doc(title, due, added, notes)
            human = _human_readable(status, value)
            tool_result = {
                "status": "ok",
                "due": due,
                "human_readable": human
            }

        # Feed tool result back to model for final reply
        messages = messages + [
            {"role": "assistant", "content": response.content},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": str(tool_result)
                    }
                ]
            }
        ]
