import os
import json
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def get_gmail_service():
    refresh_token = os.environ.get('GMAIL_REFRESH_TOKEN')
    client_id = os.environ.get('GMAIL_CLIENT_ID')
    client_secret = os.environ.get('GMAIL_CLIENT_SECRET')

    if refresh_token and client_id and client_secret:
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES
        )
        return build('gmail', 'v1', credentials=creds)

    creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    if not creds_json:
        return None
    creds_info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=SCOPES
    )
    gmail_user = os.environ.get('GMAIL_USER')
    if gmail_user:
        creds = creds.with_subject(gmail_user)
    return build('gmail', 'v1', credentials=creds)


def _extract_body(payload):
    """Recursively extract plain text body from email payload."""
    if payload.get('mimeType') == 'text/plain':
        data = payload.get('body', {}).get('data')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
    for part in payload.get('parts', []):
        result = _extract_body(part)
        if result:
            return result
    return ''


def scan_emails(sender_filter=None, after_timestamp=None):
    service = get_gmail_service()
    if not service:
        return []

    user_id = 'me'
    try:
        query_parts = []
        if isinstance(sender_filter, list):
            if sender_filter:
                query_parts.append('(' + ' OR '.join(f'from:{s}' for s in sender_filter) + ')')
        elif sender_filter:
            query_parts.append(f'from:{sender_filter}')

        if after_timestamp:
            query_parts.append(f'after:{int(after_timestamp)}')

        query = ' '.join(query_parts) if query_parts else None
        results = service.users().messages().list(
            userId=user_id, maxResults=50, q=query
        ).execute()
        messages = results.get('messages', [])

        email_list = []
        for msg in messages:
            msg_id = msg['id']
            message = service.users().messages().get(
                userId=user_id, id=msg_id, format='full'
            ).execute()

            headers = message['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')

            body = _extract_body(message['payload'])

            email_list.append({
                'id': msg_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body,
                'snippet': message.get('snippet', ''),
            })

        return email_list
    except Exception as e:
        print(f"Error scanning emails: {e}")
        return []
