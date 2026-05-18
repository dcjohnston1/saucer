"""gmail_drafts.py — Create Gmail draft replies on behalf of Hana.

Uses the same OAuth credentials as gmail_scanner.py. The GMAIL_REFRESH_TOKEN
env var must have the gmail.compose scope (updated by CEO before Sprint 3).

Drafts are created in Gmail Drafts — they are NEVER sent automatically.
The household user reviews and sends manually.
"""

import base64
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from gmail_scanner import _build_service


def create_gmail_draft(
    to: str,
    subject: str,
    body: str,
    in_reply_to_message_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> dict:
    """Create a Gmail draft and return its ID.

    Args:
        to: Recipient email address.
        subject: Subject line.
        body: Plain-text body of the draft.
        in_reply_to_message_id: Gmail message ID of the email being replied to.
            When provided, sets In-Reply-To and References headers so Gmail
            threads the draft under the original conversation.
        thread_id: Gmail thread ID. When provided, the draft is created under
            this thread so it appears inline in the conversation.

    Returns:
        {'draft_id': str, 'status': 'created'} on success.
        {'draft_id': None, 'status': 'error', 'error': str} on failure.
    """
    try:
        service = _build_service('GMAIL_REFRESH_TOKEN')
        if service is None:
            return {
                'draft_id': None,
                'status': 'error',
                'error': 'Gmail service could not be built — check GMAIL_REFRESH_TOKEN, GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET env vars',
            }

        # Build the MIME message
        msg = MIMEMultipart()
        msg['To'] = to
        msg['Subject'] = subject
        if in_reply_to_message_id:
            msg['In-Reply-To'] = in_reply_to_message_id
            msg['References'] = in_reply_to_message_id
        msg.attach(MIMEText(body, 'plain'))

        # Base64url-encode as required by the Gmail API
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')

        message_body: dict = {'raw': raw}
        if thread_id:
            message_body['threadId'] = thread_id

        draft = service.users().drafts().create(
            userId='me',
            body={'message': message_body},
        ).execute()

        return {'draft_id': draft.get('id'), 'status': 'created'}

    except Exception as e:
        print(f'[gmail_drafts] create_gmail_draft failed: {e}', file=sys.stderr)
        return {'draft_id': None, 'status': 'error', 'error': str(e)}


def build_draft_prompt_context(email: dict) -> str:
    """Format an email dict into a prompt-ready context block for draft generation.

    Args:
        email: Email dict with at minimum 'sender', 'subject', 'date', 'body' keys.

    Returns:
        A short formatted string suitable for inclusion in a Gemini prompt.
    """
    body_preview = (email.get('body') or '')[:500]
    return (
        f"From: {email.get('sender', '(unknown)')}\n"
        f"Subject: {email.get('subject', '(no subject)')}\n"
        f"Date: {email.get('date', '(unknown date)')}\n"
        f"Body preview: {body_preview}"
    )
