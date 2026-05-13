import io
import os
import re
import json
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def _normalize_sender(sender_str: str) -> str:
    """Extract bare email address from a filter value, stripping display name and angle brackets."""
    m = re.search(r'<([^>]+)>', sender_str)
    return m.group(1).strip().lower() if m else sender_str.strip().lower()


def build_gmail_query(sender_filter=None, keyword_filter=None, after_timestamp=None) -> str:
    """Build the Gmail search query string used in messages.list calls."""
    query_parts = []
    match_clauses = []
    if isinstance(sender_filter, list) and sender_filter:
        match_clauses.extend(f'from:{_normalize_sender(s)}' for s in sender_filter)
    elif sender_filter:
        match_clauses.append(f'from:{_normalize_sender(sender_filter)}')
    if isinstance(keyword_filter, list) and keyword_filter:
        match_clauses.extend(f'"{k}"' if ' ' in k else k for k in keyword_filter)
    elif keyword_filter:
        match_clauses.append(f'"{keyword_filter}"' if ' ' in keyword_filter else keyword_filter)
    if match_clauses:
        query_parts.append('(' + ' OR '.join(match_clauses) + ')')
    if after_timestamp:
        query_parts.append(f'after:{int(after_timestamp)}')
    return ' '.join(query_parts)


def _build_service(refresh_token_key='GMAIL_REFRESH_TOKEN'):
    """Build a Gmail service for the account identified by the given env var key."""
    refresh_token = os.environ.get(refresh_token_key)
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
    return None


def get_gmail_service():
    svc = _build_service('GMAIL_REFRESH_TOKEN')
    if svc:
        return svc
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


def _get_all_services():
    """Return list of (service, account_label) for every configured Gmail account."""
    services = []
    primary = get_gmail_service()
    if primary:
        services.append((primary, os.environ.get('GMAIL_USER', 'Account 1')))
    secondary = _build_service('GMAIL_REFRESH_TOKEN_2')
    if secondary:
        services.append((secondary, os.environ.get('GMAIL_USER_2', 'Account 2')))
    return services


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


def _extract_html_body(payload):
    """Recursively extract HTML body from email payload."""
    if payload.get('mimeType') == 'text/html':
        data = payload.get('body', {}).get('data')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
    for part in payload.get('parts', []):
        result = _extract_html_body(part)
        if result:
            return result
    return ''


_EXTRACTABLE_MIMES = {'application/pdf', 'image/jpeg', 'image/png'}

def _extract_attachments(payload, service, user_id, msg_id):
    """Walk MIME tree and return list of attachment dicts for PDF and image parts."""
    attachments = []
    mime = payload.get('mimeType', '')
    filename = payload.get('filename', '')

    if mime in _EXTRACTABLE_MIMES and filename:
        try:
            body = payload.get('body', {})
            data = body.get('data')
            if not data:
                attachment_id = body.get('attachmentId')
                if attachment_id:
                    resp = service.users().messages().attachments().get(
                        userId=user_id, messageId=msg_id, id=attachment_id
                    ).execute()
                    data = resp.get('data', '')
            if data:
                file_bytes = base64.urlsafe_b64decode(data)
                file_size = len(file_bytes)
                att = {
                    'filename': filename,
                    'mime': mime,
                    'extracted_text': '',
                    '_file_size': file_size,
                }
                if mime == 'application/pdf':
                    try:
                        import pdfplumber
                        text = ''
                        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                            for page in pdf.pages:
                                text += (page.extract_text() or '') + '\n'
                        att['extracted_text'] = text[:8000].strip()
                    except Exception as pdf_err:
                        print(f"PDF text extraction error ({filename}): {pdf_err}")
                if file_size <= 10_000_000:
                    att['_pdf_bytes_b64'] = base64.b64encode(file_bytes).decode()
                else:
                    print(f"Attachment {filename} too large ({file_size} bytes), skipping GCS auto-save")
                attachments.append(att)
        except Exception as e:
            print(f"Attachment extraction error ({filename}): {e}")
            attachments.append({'filename': filename, 'mime': mime, 'extracted_text': ''})

    for part in payload.get('parts', []):
        attachments.extend(_extract_attachments(part, service, user_id, msg_id))

    return attachments


def _scan_account(service, account_label, sender_filter=None, keyword_filter=None, after_timestamp=None, prefix_ids=False):
    """Scan a single Gmail account and return email list."""
    user_id = 'me'
    query_str = build_gmail_query(sender_filter, keyword_filter, after_timestamp)
    query = query_str if query_str else None
    print(f"[_scan_account] account={account_label} query={query!r}")
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
        html_body = _extract_html_body(message['payload'])
        attachments = _extract_attachments(message['payload'], service, user_id, msg_id)

        email_list.append({
            'id': f"{account_label}:{msg_id}" if prefix_ids else msg_id,
            'subject': subject,
            'sender': sender,
            'date': date,
            'body': body,
            'html_body': html_body,
            'snippet': message.get('snippet', ''),
            'attachments': attachments,
            'account': account_label,
        })

    return email_list


def scan_emails(sender_filter=None, keyword_filter=None, after_timestamp=None):
    all_services = _get_all_services()
    if not all_services:
        return []

    email_list = []
    for i, (service, label) in enumerate(all_services):
        try:
            email_list.extend(_scan_account(service, label, sender_filter, keyword_filter, after_timestamp, prefix_ids=(i > 0)))
        except Exception as e:
            print(f"Error scanning {label}: {e}")

    return email_list


def setup_gmail_watch(service, topic_name: str) -> dict:
    """Call users.watch() to enable Pub/Sub push notifications for this account.

    Returns the watch response dict containing historyId and expiration.
    """
    body = {
        'labelIds': ['INBOX'],
        'topicName': topic_name,
    }
    return service.users().watch(userId='me', body=body).execute()


def fetch_new_messages_since(service, start_history_id: str) -> tuple:
    """Fetch messages added to INBOX since start_history_id.

    Returns (emails, latest_history_id). latest_history_id is None if history
    is stale (historyId too old); caller should re-watch and reset.
    """
    user_id = 'me'
    try:
        history_resp = service.users().history().list(
            userId=user_id,
            startHistoryId=start_history_id,
            historyTypes=['messageAdded'],
            labelId='INBOX',
        ).execute()
    except Exception as e:
        print(f"[gmail] history.list error (stale historyId?): {e}")
        return [], None

    new_message_ids = set()
    for record in history_resp.get('history', []):
        for ma in record.get('messagesAdded', []):
            new_message_ids.add(ma['message']['id'])

    latest_history_id = str(history_resp.get('historyId', start_history_id))

    emails = []
    for msg_id in new_message_ids:
        try:
            message = service.users().messages().get(
                userId=user_id, id=msg_id, format='full'
            ).execute()
            headers = message['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            body_text = _extract_body(message['payload'])
            html_body = _extract_html_body(message['payload'])
            attachments = _extract_attachments(message['payload'], service, user_id, msg_id)
            emails.append({
                'id': msg_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body_text,
                'html_body': html_body,
                'snippet': message.get('snippet', ''),
                'attachments': attachments,
            })
        except Exception as e:
            print(f"[gmail] fetch message {msg_id} error: {e}")

    return emails, latest_history_id
