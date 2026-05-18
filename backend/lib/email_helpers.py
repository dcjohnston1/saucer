import hashlib
import re


def _extract_sender_addr(sender_str: str) -> str:
    """Return the bare email address from a From: header, lowercased."""
    m = re.search(r'<([^>]+)>', sender_str)
    return m.group(1).lower() if m else sender_str.lower()


def _get_email_intent(db) -> str:
    """Load email_intent string from Firestore settings."""
    try:
        doc = db.collection('settings').document('email_intent').get()
        return (doc.to_dict() or {}).get('intent', '') if doc.exists else ''
    except Exception as e:
        print(f"[email_intent] load error: {e}")
        return ''


def _auto_save_pdf_attachments(emails, db):
    """For permitted emails with raw attachment bytes, save to GCS and write Firestore metadata.

    Uses a deterministic document ID (MD5 of email_id:filename) so reprocessing
    the same email is idempotent — no duplicate entries, no composite index needed.
    """
    from gcs import upload_file
    from datetime import datetime, timezone

    for e in emails:
        if e.get('verdict') != 'permitted':
            continue
        for att in e.get('attachments', []):
            b64 = att.pop('_pdf_bytes_b64', None)
            size = att.pop('_file_size', att.pop('_pdf_size', 0))
            if not b64:
                continue
            try:
                filename = att['filename']
                content_type = att.get('mime', 'application/pdf')
                file_id = hashlib.md5(f"{e['id']}:{filename}".encode()).hexdigest()
                gcs_path = f"files/{file_id}_{filename}"
                file_bytes = __import__('base64').b64decode(b64)
                if not upload_file(file_bytes, gcs_path, content_type):
                    continue
                db.collection('hana_files').document(file_id).set({
                    'file_id': file_id,
                    'filename': filename,
                    'source': 'email',
                    'email_id': e['id'],
                    'uploaded_at': datetime.now(timezone.utc).isoformat(),
                    'size_bytes': size,
                    'gcs_path': gcs_path,
                    'content_text': att.get('extracted_text', '')[:8000],
                })
                att['file_id'] = file_id
                print(f"[files] auto-saved {filename} from email {e['id']}")
            except Exception as ex:
                print(f"[files] auto-save error for {att.get('filename')}: {ex}")


def _strip_raw_bytes(emails):
    """Remove in-memory attachment bytes before writing emails to GCS."""
    for e in emails:
        for att in e.get('attachments', []):
            att.pop('_pdf_bytes_b64', None)
            att.pop('_file_size', None)
            att.pop('_pdf_size', None)
