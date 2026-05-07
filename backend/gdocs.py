import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/documents']
DOC_ID = os.environ['DOC_ID']

def get_service():
    creds_json = os.environ['GOOGLE_CREDENTIALS_JSON']
    creds_info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=SCOPES
    )
    return build('docs', 'v1', credentials=creds)

def read_doc():
    service = get_service()
    doc = service.documents().get(documentId=DOC_ID).execute()
    content = doc.get('body').get('content')
    text = ''
    for element in content:
        if 'paragraph' in element:
            for para_element in element['paragraph']['elements']:
                if 'textRun' in para_element:
                    text += para_element['textRun']['content']
    return text

def complete_task(title):
    service = get_service()
    service.documents().batchUpdate(
        documentId=DOC_ID,
        body={'requests': [{'replaceAllText': {
            'containsText': {'text': f'TODO | {title}', 'matchCase': True},
            'replaceText': f'DONE | {title}'
        }}]}
    ).execute()

def _normalize(title):
    return title.strip().lower()

def update_task_assignee(title, new_assignee):
    """Find a task line by title and update (or add) its assignee field in-place."""
    existing = read_doc()
    title_norm = _normalize(title)
    target_line = None
    for line in existing.split('\n'):
        parts = [p.strip() for p in line.split('|')]
        if len(parts) > 1 and _normalize(parts[1]) == title_norm:
            target_line = line
            break
    if not target_line:
        return False

    parts = [p.strip() for p in target_line.split('|')]
    new_parts = []
    has_assignee = False
    for part in parts:
        if part.startswith('assignee:'):
            new_parts.append(f'assignee:{new_assignee}')
            has_assignee = True
        else:
            new_parts.append(part)
    if not has_assignee:
        new_parts.append(f'assignee:{new_assignee}')

    new_line = ' | '.join(new_parts)
    service = get_service()
    service.documents().batchUpdate(
        documentId=DOC_ID,
        body={'requests': [{'replaceAllText': {
            'containsText': {'text': target_line.rstrip(), 'matchCase': True},
            'replaceText': new_line,
        }}]}
    ).execute()
    return True

def dedup_tasks():
    """Remove duplicate TODO lines (same normalized title). Keeps first occurrence. Returns count removed."""
    service = get_service()
    doc = service.documents().get(documentId=DOC_ID).execute()
    content = doc.get('body').get('content')

    seen_titles = set()
    delete_requests = []

    for element in content:
        if 'paragraph' not in element:
            continue
        para_text = ''
        for pe in element['paragraph']['elements']:
            if 'textRun' in pe:
                para_text += pe['textRun']['content']
        line = para_text.strip()
        if not line.startswith('TODO'):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 2:
            continue
        title_norm = _normalize(parts[1])
        if title_norm in seen_titles:
            delete_requests.append({
                'deleteContentRange': {
                    'range': {
                        'startIndex': element['startIndex'],
                        'endIndex': element['endIndex'],
                    }
                }
            })
        else:
            seen_titles.add(title_norm)

    if not delete_requests:
        return 0

    # Delete in reverse order so earlier indices stay valid
    delete_requests.reverse()
    service.documents().batchUpdate(
        documentId=DOC_ID,
        body={'requests': delete_requests}
    ).execute()
    return len(delete_requests)


def append_to_doc(title, due, added, notes=None, owner=None, priority=None, recurrence=None, location=None, urgency=None, assignee=None, source_email_id=None):
    existing = read_doc()
    title_norm = _normalize(title)
    for line in existing.split('\n'):
        parts = [p.strip() for p in line.split('|')]
        if len(parts) > 1 and _normalize(parts[1]) == title_norm:
            return  # already in doc

    line = f"TODO | {title} | due:{due} | added:{added}"
    if owner:
        line += f" | owner:{owner}"
    if priority:
        line += f" | priority:{priority}"
    if recurrence and recurrence != "none":
        line += f" | recurrence:{recurrence}"
    if location:
        line += f" | location:{location}"
    if urgency:
        line += f" | urgency:{urgency}"
    if notes:
        line += f" | notes:{notes}"
    if assignee:
        line += f" | assignee:{assignee}"
    if source_email_id:
        line += f" | source_email_id:{source_email_id}"
    line += "\n"

    service = get_service()
    doc = service.documents().get(documentId=DOC_ID).execute()
    end_index = doc['body']['content'][-1]['endIndex'] - 1
    service.documents().batchUpdate(
        documentId=DOC_ID,
        body={'requests': [{'insertText': {'location': {'index': end_index}, 'text': line}}]}
    ).execute()
