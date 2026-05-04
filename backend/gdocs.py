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
