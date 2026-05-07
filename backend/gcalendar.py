import json
import os
import dateparser
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar.events']
CALENDAR_ID = 'dcjohnston1@gmail.com'

def get_service():
    creds_json = os.environ['GOOGLE_CREDENTIALS_JSON']
    creds_info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=creds)

def get_events(start_iso, end_iso, calendar_id=None):
    service = get_service()
    result = service.events().list(
        calendarId=calendar_id or CALENDAR_ID,
        timeMin=start_iso,
        timeMax=end_iso,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = []
    for e in result.get('items', []):
        all_day = 'date' in e['start']
        start = e['start'].get('dateTime', e['start'].get('date'))
        end = e['end'].get('dateTime', e['end'].get('date'))
        events.append({
            'id': e['id'],
            'title': e.get('summary', '(No title)'),
            'start': start,
            'end': end,
            'location': e.get('location', ''),
            'description': e.get('description', ''),
            'all_day': all_day,
        })
    return events

import re
from datetime import timedelta

def _parse_date_range(date_expression):
    """Return (start_date, end_date) parsed from a date expression, handling ranges."""
    settings = {'PREFER_DATES_FROM': 'future'}
    # Split on common range separators: " - ", " – ", "–", " to ", " through "
    parts = re.split(r'\s*(?:–|-|to|through)\s*', date_expression, maxsplit=1)
    if len(parts) == 2:
        start = dateparser.parse(parts[0].strip(), settings=settings)
        end = dateparser.parse(parts[1].strip(), settings=settings)
        if start and end:
            if end < start:  # e.g. "May 5th - 7th" where end parsed without month
                end = end.replace(month=start.month, year=start.year)
            return start, end
    # Single date
    single = dateparser.parse(date_expression, settings=settings)
    return (single, single) if single else (None, None)

def create_event(title, date_expression, notes=None, assignee_label=None):
    start_dt, end_dt = _parse_date_range(date_expression)
    if not start_dt:
        return None
    start_str = start_dt.strftime('%Y-%m-%d')
    # Google Calendar all-day end date is exclusive (day after last day)
    end_exclusive = (end_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    description_parts = []
    if notes:
        description_parts.append(notes)
    if assignee_label:
        description_parts.append(f'Assigned to: {assignee_label}')
    event = {
        'summary': title,
        'start': {'date': start_str},
        'end': {'date': end_exclusive},
    }
    if description_parts:
        event['description'] = '\n'.join(description_parts)
    service = get_service()
    result = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return result.get('id')


def create_event_direct(title, date_str, time_str=None, end_date_str=None, notes=None):
    """Create a calendar event with an explicit date (and optional time)."""
    from datetime import datetime as _dt
    service = get_service()
    if time_str:
        dt = _dt.fromisoformat(f"{date_str}T{time_str}:00")
        end_dt = dt + timedelta(hours=1)
        event = {
            'summary': title,
            'start': {'dateTime': dt.isoformat(), 'timeZone': 'America/Los_Angeles'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'America/Los_Angeles'},
        }
    else:
        end = end_date_str or date_str
        from datetime import datetime as _dt2
        end_excl = (_dt2.fromisoformat(end) + timedelta(days=1)).strftime('%Y-%m-%d')
        event = {
            'summary': title,
            'start': {'date': date_str},
            'end': {'date': end_excl},
        }
    if notes:
        event['description'] = notes
    result = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return result.get('id')


def update_event(event_id, title=None, start_date=None, end_date=None, time_str=None, notes=None):
    """Patch a calendar event in-place."""
    from datetime import datetime as _dt
    service = get_service()
    event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
    if title is not None:
        event['summary'] = title
    if start_date is not None:
        if time_str:
            dt = _dt.fromisoformat(f"{start_date}T{time_str}:00")
            end_dt = dt + timedelta(hours=1)
            event['start'] = {'dateTime': dt.isoformat(), 'timeZone': 'America/Los_Angeles'}
            event['end'] = {'dateTime': end_dt.isoformat(), 'timeZone': 'America/Los_Angeles'}
        else:
            end = end_date or start_date
            end_excl = (_dt.fromisoformat(end) + timedelta(days=1)).strftime('%Y-%m-%d')
            event['start'] = {'date': start_date}
            event['end'] = {'date': end_excl}
    if notes is not None:
        event['description'] = notes
    service.events().update(calendarId=CALENDAR_ID, eventId=event_id, body=event).execute()


def delete_event(event_id):
    """Delete a calendar event."""
    service = get_service()
    service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
