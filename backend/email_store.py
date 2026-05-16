"""
Unified email storage layer.

Metadata (id, sender, subject, date, verdict, etc.) → Firestore 'emails' collection.
Body content (body, html_body, snippet, attachments with text) → GCS email-bodies/{id}.json.

Callers use these functions; no other module should reference saucer-emails.json.
_pdf_bytes_b64 and _file_size must be stripped by _strip_raw_bytes before any
email reaches this module — split_email_for_storage assumes they are absent.
"""

import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from google.cloud import firestore as _firestore

from gcs import read_json, write_json

_PROJECT = 'mediationmate'
_COLLECTION = 'emails'
_BODY_PREFIX = 'email-bodies'

_BODY_FIELDS = {'body', 'html_body', 'snippet'}
_RAW_BYTE_FIELDS = {'_pdf_bytes_b64', '_file_size', '_pdf_size'}
_INTERNAL_FIELDS = {'has_body', 'body_gcs_path', 'attachments_meta', 'created_at', 'updated_at'}


def _clean_for_caller(email: dict) -> dict:
    return {k: v for k, v in email.items() if k not in _INTERNAL_FIELDS}


def _db():
    return _firestore.Client(project=_PROJECT)


def _safe_doc_id(email_id: str) -> str:
    # Colons are fine in Firestore IDs; only forward slashes are forbidden.
    return email_id.replace('/', '_SLASH_')


def _body_gcs_path(email_id: str) -> str:
    return f"{_BODY_PREFIX}/{_safe_doc_id(email_id)}.json"


# ── Storage split ─────────────────────────────────────────────────────────────

def split_email_for_storage(email: dict) -> tuple:
    """Return (metadata_for_firestore, body_for_gcs).

    metadata_for_firestore goes into Firestore doc.
    body_for_gcs goes into GCS email-bodies/{id}.json.
    Raw byte fields (_pdf_bytes_b64, _file_size) must already be stripped.
    """
    body_data = {}
    meta = {}

    for k, v in email.items():
        if k in _RAW_BYTE_FIELDS:
            continue
        if k in _BODY_FIELDS:
            body_data[k] = v
        elif k == 'attachments':
            body_data['attachments_full'] = v
            meta['attachments_meta'] = [
                {kk: a[kk] for kk in ('filename', 'mime', 'file_id') if kk in a}
                for a in (v or [])
            ]
        else:
            meta[k] = v

    has_body = bool(
        body_data.get('body') or body_data.get('html_body') or body_data.get('snippet')
    )
    meta['has_body'] = has_body
    if has_body:
        meta['body_gcs_path'] = _body_gcs_path(email['id'])

    return meta, body_data


def _merge_email(meta: dict, body_data: dict) -> dict:
    """Reconstruct a full email dict from metadata and body data."""
    result = dict(meta)
    attachments_full = body_data.get('attachments_full')
    if attachments_full is not None:
        result['attachments'] = attachments_full
    elif 'attachments_meta' in result:
        result['attachments'] = result.get('attachments_meta', [])
    for k in _BODY_FIELDS:
        if k in body_data:
            result[k] = body_data[k]
    return result


def _load_body(meta: dict) -> dict:
    path = meta.get('body_gcs_path')
    if not path or not meta.get('has_body'):
        return {}
    try:
        data = read_json(path, None)
        if data is None:
            print(f"[email_store] WARNING: body blob missing for {meta.get('id')} at {path}")
            return {}
        return data
    except Exception as e:
        print(f"[email_store] WARNING: failed to load body for {meta.get('id')}:\n{traceback.format_exc()}")
        return {}


def _ts_to_str(meta: dict) -> dict:
    """Convert Firestore Timestamp objects to ISO strings in place, return meta."""
    for f in ('created_at', 'updated_at'):
        v = meta.get(f)
        if v is not None and hasattr(v, 'isoformat'):
            meta[f] = v.isoformat()
    return meta


# ── Read operations ───────────────────────────────────────────────────────────

def get_email(email_id: str) -> dict | None:
    try:
        db = _db()
        doc = db.collection(_COLLECTION).document(_safe_doc_id(email_id)).get()
        if not doc.exists:
            return None
        meta = _ts_to_str(doc.to_dict())
        body_data = _load_body(meta) if meta.get('has_body') else {}
        return _clean_for_caller(_merge_email(meta, body_data))
    except Exception as e:
        print(f"[email_store] get_email error {email_id}:\n{traceback.format_exc()}")
        return None


def get_emails_by_ids(email_ids: list) -> list:
    if not email_ids:
        return []
    results = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(get_email, eid): eid for eid in email_ids}
        for fut in as_completed(futures):
            e = fut.result()
            if e:
                results.append(e)
    id_order = {eid: i for i, eid in enumerate(email_ids)}
    results.sort(key=lambda e: id_order.get(e.get('id', ''), 9999))
    return results


def _stream_all_metas(verdict_eq: str = None, dismissed_by_eq: str = None) -> list:
    """Stream Firestore metadata docs, optionally with equality filters."""
    db = _db()
    q = db.collection(_COLLECTION)
    if verdict_eq is not None:
        q = q.where('verdict', '==', verdict_eq)
    if dismissed_by_eq is not None:
        q = q.where('dismissed_by', '==', dismissed_by_eq)
    metas = []
    for doc in q.stream():
        metas.append(_ts_to_str(doc.to_dict()))
    return metas


def _parse_date_for_sort(date_str: str):
    """Parse an email date string for sorting. Returns sortable datetime or min."""
    if not date_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def list_emails(
    limit: int = 500,
    exclude_dismissed: bool = True,
    exclude_reviewed: bool = True,
    exclude_blocked_verdict: bool = True,
    include_body: bool = False,
) -> list:
    return _query_emails(
        limit=limit,
        exclude_dismissed=exclude_dismissed,
        exclude_reviewed=exclude_reviewed,
        exclude_blocked_verdict=exclude_blocked_verdict,
        include_body=include_body,
    )


def list_emails_filtered(
    sender_filter: list = None,
    after_date_iso: str = None,
    verdict: str = None,
    dismissed_by: str = None,
    dismissed_by_not: str = None,
    limit: int = 500,
    include_body: bool = False,
) -> list:
    return _query_emails(
        limit=limit,
        exclude_dismissed=False,
        exclude_reviewed=False,
        exclude_blocked_verdict=False,
        include_body=include_body,
        sender_filter=sender_filter,
        after_date_iso=after_date_iso,
        verdict_eq=verdict,
        dismissed_by_eq=dismissed_by,
        dismissed_by_not=dismissed_by_not,
    )


def _query_emails(
    limit: int = 500,
    exclude_dismissed: bool = True,
    exclude_reviewed: bool = True,
    exclude_blocked_verdict: bool = True,
    include_body: bool = False,
    sender_filter: list = None,
    after_date_iso: str = None,
    verdict_eq: str = None,
    dismissed_by_eq: str = None,
    dismissed_by_not: str = None,
) -> list:
    try:
        metas = _stream_all_metas(
            verdict_eq=verdict_eq,
            dismissed_by_eq=dismissed_by_eq,
        )

        metas.sort(key=lambda m: _parse_date_for_sort(m.get('date', '')), reverse=True)

        dismissed_set = set(read_json('saucer-dismissed.json', [])) if exclude_dismissed else set()
        reviewed_set = set(read_json('saucer-reviewed.json', [])) if exclude_reviewed else set()

        filtered = []
        for m in metas:
            eid = m.get('id', '')
            if exclude_dismissed and eid in dismissed_set:
                continue
            if exclude_reviewed and eid in reviewed_set:
                continue
            if exclude_blocked_verdict and m.get('verdict', 'permitted') == 'blocked':
                continue
            if sender_filter:
                slc = [s.lower() for s in sender_filter]
                if m.get('sender', '').lower() not in slc:
                    continue
            if after_date_iso and (m.get('date') or '') < after_date_iso:
                continue
            if dismissed_by_not and m.get('dismissed_by') == dismissed_by_not:
                continue
            filtered.append(m)
            if len(filtered) >= limit:
                break

        if not include_body:
            result = []
            for m in filtered:
                e = dict(m)
                if 'attachments_meta' in e and 'attachments' not in e:
                    e['attachments'] = e.get('attachments_meta', [])
                result.append(_clean_for_caller(e))
            return result

        bodies = [None] * len(filtered)
        with ThreadPoolExecutor(max_workers=10) as ex:
            body_futures = {ex.submit(_load_body, m): i for i, m in enumerate(filtered)}
            for fut in as_completed(body_futures):
                idx = body_futures[fut]
                bodies[idx] = fut.result() or {}

        return [_clean_for_caller(_merge_email(m, bodies[i])) for i, m in enumerate(filtered)]

    except Exception as e:
        print(
            f"[email_store] _query_emails error "
            f"(limit={limit} excl_dismissed={exclude_dismissed} excl_reviewed={exclude_reviewed} "
            f"excl_blocked={exclude_blocked_verdict} include_body={include_body}):\n"
            f"{traceback.format_exc()}"
        )
        return []


def search_emails_text(query: str, limit: int = 3) -> list:
    emails = list_emails(
        limit=1000,
        exclude_dismissed=False,
        exclude_reviewed=False,
        exclude_blocked_verdict=False,
        include_body=True,
    )
    q_lower = query.lower()
    tokens = q_lower.split()
    matches = []
    for e in emails:
        haystack = ' '.join([
            e.get('sender', ''),
            e.get('subject', ''),
            e.get('body', '') or e.get('snippet', ''),
        ]).lower()
        if all(t in haystack for t in tokens):
            matches.append(e)
    matches.sort(key=lambda e: _parse_date_for_sort(e.get('date', '')), reverse=True)
    return matches[:limit]


# ── Write operations ──────────────────────────────────────────────────────────

def upsert_email(email: dict) -> None:
    try:
        db = _db()
        meta, body_data = split_email_for_storage(email)
        now = datetime.now(timezone.utc)
        doc_id = _safe_doc_id(email['id'])
        doc_ref = db.collection(_COLLECTION).document(doc_id)
        existing = doc_ref.get()
        if existing.exists:
            meta['updated_at'] = now
            meta.setdefault('created_at', existing.to_dict().get('created_at', now))
        else:
            meta['created_at'] = now
            meta['updated_at'] = now
        doc_ref.set(meta)
        if body_data:
            write_json(_body_gcs_path(email['id']), body_data)
    except Exception as e:
        print(f"[email_store] upsert_email error {email.get('id')}:\n{traceback.format_exc()}")


def upsert_emails_batch(emails: list) -> None:
    if not emails:
        return
    db = _db()
    now = datetime.now(timezone.utc)
    BATCH_SIZE = 500

    # Fetch existing docs to preserve created_at
    existing = {}
    for email in emails:
        try:
            doc = db.collection(_COLLECTION).document(_safe_doc_id(email['id'])).get()
            if doc.exists:
                existing[email['id']] = doc.to_dict()
        except Exception:
            pass

    # Firestore batched writes
    for batch_start in range(0, len(emails), BATCH_SIZE):
        batch = db.batch()
        chunk = emails[batch_start:batch_start + BATCH_SIZE]
        for email in chunk:
            meta, _ = split_email_for_storage(email)
            if email['id'] in existing:
                meta['updated_at'] = now
                meta.setdefault('created_at', existing[email['id']].get('created_at', now))
            else:
                meta['created_at'] = now
                meta['updated_at'] = now
            batch.set(db.collection(_COLLECTION).document(_safe_doc_id(email['id'])), meta)
        batch.commit()

    # Body blobs in parallel
    def _write_body(email):
        _, body_data = split_email_for_storage(email)
        if body_data:
            write_json(_body_gcs_path(email['id']), body_data)

    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(_write_body, emails))


def update_email_fields(email_id: str, fields: dict) -> None:
    try:
        db = _db()
        update = dict(fields)
        update['updated_at'] = datetime.now(timezone.utc)
        db.collection(_COLLECTION).document(_safe_doc_id(email_id)).update(update)
    except Exception as e:
        print(f"[email_store] update_email_fields error {email_id}:\n{traceback.format_exc()}")


def email_exists(email_id: str) -> bool:
    try:
        db = _db()
        return db.collection(_COLLECTION).document(_safe_doc_id(email_id)).get().exists
    except Exception as e:
        print(f"[email_store] email_exists error {email_id}:\n{traceback.format_exc()}")
        return False
