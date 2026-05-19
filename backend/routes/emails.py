import hashlib
import os
import uuid

from flask import Blueprint, request, jsonify, Response
from google.cloud.firestore import DELETE_FIELD

import email_store
from lib.firestore_client import get_db
from lib.email_helpers import (
    _extract_sender_addr,
    _get_email_intent,
    _auto_save_pdf_attachments,
    _strip_raw_bytes,
)
from logger import log_action, get_recent_actions

emails_bp = Blueprint('emails', __name__)


# ── Private helpers ───────────────────────────────────────────────────────────

def _parse_date_safe(date_str: str):
    """Parse an RFC 2822 date string to a timezone-aware datetime for sorting.

    Returns datetime.min (UTC) on any parse failure so malformed dates sort last.
    """
    from email.utils import parsedate_to_datetime
    from datetime import datetime, timezone
    if not date_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _record_deleted_task(title: str):
    """Append a task title to saucer-deleted-tasks.json and expire entries older than 30 days."""
    from gcs import read_json, write_json
    from datetime import datetime, timedelta, timezone
    entries = read_json('saucer-deleted-tasks.json', [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    entries = [e for e in entries if datetime.fromisoformat(e['deleted_at']) > cutoff]
    norm = title.strip().lower()
    if not any(e['title'] == norm for e in entries):
        entries.append({'title': norm, 'deleted_at': datetime.now(timezone.utc).isoformat()})
    write_json('saucer-deleted-tasks.json', entries)


def _is_task_deleted(title: str) -> bool:
    """Return True if this title is in saucer-deleted-tasks.json (not yet expired)."""
    from gcs import read_json
    from datetime import datetime, timedelta, timezone
    entries = read_json('saucer-deleted-tasks.json', [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    norm = title.strip().lower()
    return any(
        e['title'] == norm and datetime.fromisoformat(e['deleted_at']) > cutoff
        for e in entries
    )


def _req_user(data=None):
    """Extract the acting user's email from request body or query param."""
    if data:
        v = data.get('user', '')
        if v:
            return v
    return request.args.get('user', 'unknown')


def _is_vague_summary(summary):
    """Return True if the summary is missing or too short/generic to be useful."""
    if not summary:
        return True
    if len(summary) < 60:
        return True
    lower = summary.lower().strip()
    if lower.startswith('email from') or lower.startswith('message from'):
        return True
    return False


def _get_blocked_senders_set(db) -> set:
    doc = db.collection('settings').document('blocked_senders').get()
    addresses = doc.to_dict().get('addresses', []) if doc.exists else []
    return {a.lower() for a in addresses}


def _get_permitted_senders_list(db) -> list:
    doc = db.collection('settings').document('email_filters').get()
    return [a.lower() for a in (doc.to_dict().get('addresses', []) if doc.exists else [])]


def _get_excluded_keywords(db) -> list:
    doc = db.collection('settings').document('exclude_keyword_filters').get()
    return [kw.lower() for kw in (doc.to_dict().get('keywords', []) if doc.exists else [])]


def _run_intent_eval_batch(emails, email_intent, blocked_set, permitted_list, limit=20, excluded_keywords=None):
    """Evaluate intent for emails missing a verdict. Mutates emails in place."""
    from email_scanner import evaluate_email_intent
    needs_eval = [e for e in emails if 'verdict' not in e][:limit]
    if not needs_eval:
        return
    permitted_set = set(permitted_list)
    for e in needs_eval:
        try:
            result = evaluate_email_intent(e, email_intent, blocked_set, permitted_set, excluded_keywords=excluded_keywords)
            e['verdict'] = result['verdict']
            e['verdict_confidence'] = result['confidence']
            e['verdict_reason'] = result['reason']
            if result['verdict'] == 'blocked':
                e['dismissed_by'] = 'hana'
        except Exception as ex:
            print(f"[intent_eval] error for {e.get('id')}: {ex}")
            e['verdict'] = 'uncertain'


def _force_reevaluate_all_emails(emails, email_intent, excluded_keywords, blocked_set, permitted_set):
    """Re-evaluate ALL emails (ignoring existing verdicts) using batched Gemini calls.

    Mutates emails in place. Returns counts dict: {total, permitted, uncertain, blocked}.
    """
    from email_scanner import batch_evaluate_emails_intent
    results = batch_evaluate_emails_intent(
        emails, email_intent,
        excluded_keywords=excluded_keywords,
        blocked_senders=blocked_set,
        permitted_senders=permitted_set,
    )
    counts = {'total': len(emails), 'permitted': 0, 'uncertain': 0, 'blocked': 0}
    for e in emails:
        email_id = e.get('id', '')
        r = results.get(email_id)
        if r:
            new_verdict = r['verdict']
            e['verdict'] = new_verdict
            e['verdict_reason'] = r['reason']
            e.pop('verdict_confidence', None)
            if new_verdict == 'blocked':
                e['dismissed_by'] = 'hana'
            elif e.get('dismissed_by') == 'hana':
                e.pop('dismissed_by', None)
            counts[new_verdict] = counts.get(new_verdict, 0) + 1
        else:
            counts[e.get('verdict', 'uncertain')] = counts.get(e.get('verdict', 'uncertain'), 0) + 1
    return counts


def _backfill(sender_filter=None, keyword_filter=None):
    """Scan the last 90 days for a newly added sender or keyword and merge into stored emails."""
    try:
        from gmail_scanner import scan_emails
        from datetime import datetime, timedelta, timezone
        after_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
        new_emails = scan_emails(
            sender_filter=sender_filter,
            keyword_filter=keyword_filter,
            after_timestamp=after_ts
        )
        if new_emails:
            fresh = [e for e in new_emails if not email_store.email_exists(e['id'])]
            if fresh:
                _strip_raw_bytes(fresh)
                email_store.upsert_emails_batch(fresh)
    except Exception as e:
        print(f"Backfill error: {e}")


# ── Module-level cache ────────────────────────────────────────────────────────

_dismissed_review_cache = {}


# ── Routes ────────────────────────────────────────────────────────────────────

@emails_bp.route('/chat', methods=['POST'])
def chat():
    from mediator import process_message
    data = request.get_json()
    user = data.get('user')
    user_email = data.get('user_email') or user
    message = data.get('message')
    conversation_id = data.get('conversation_id') or str(uuid.uuid4())
    voice_mode = bool(data.get('voice_mode', False))

    if not user or not message:
        return jsonify({'error': 'Missing user or message'}), 400

    history = data.get('history', [])
    reply, actions = process_message(user, message, history, user_email=user_email, conversation_id=conversation_id, voice_mode=voice_mode)
    return jsonify({
        'reply': reply,
        'actions': actions,
        'model': 'gemini-2.5-flash'
    })


@emails_bp.route('/doc', methods=['GET'])
def get_doc():
    from gdocs import read_doc
    raw_content = read_doc()

    tasks = []
    lines = raw_content.split('\n')
    for line in lines:
        if not line.strip() or not line.startswith('TODO'):
            continue

        parts = [p.strip() for p in line.split('|')]
        task = {
            'title': parts[1] if len(parts) > 1 else 'Untitled Task',
            'due': None,
            'added': None,
            'owner': None,
            'priority': None,
            'recurrence': None,
            'location': None,
            'urgency': None,
            'notes': None,
            'assignee': None,
            'source_email_id': None,
            'source': None,
        }

        for part in parts[2:]:
            if part.startswith('due:'):
                task['due'] = part[4:]
            elif part.startswith('added:'):
                task['added'] = part[6:]
            elif part.startswith('owner:'):
                task['owner'] = part[6:]
            elif part.startswith('priority:'):
                task['priority'] = part[9:]
            elif part.startswith('recurrence:'):
                task['recurrence'] = part[11:]
            elif part.startswith('location:'):
                task['location'] = part[9:]
            elif part.startswith('urgency:'):
                task['urgency'] = part[8:]
            elif part.startswith('notes:'):
                task['notes'] = part[6:]
            elif part.startswith('assignee:'):
                task['assignee'] = part[9:]
            elif part.startswith('source_email_id:'):
                task['source_email_id'] = part[16:]
            elif part.startswith('source:'):
                task['source'] = part[7:]

        tasks.append(task)

    return jsonify({'tasks': tasks})


@emails_bp.route('/doc/task', methods=['DELETE'])
def complete_task():
    data = request.get_json()
    title = data.get('title')
    if not title:
        return jsonify({'error': 'Missing title'}), 400
    from gdocs import complete_task as gdocs_complete_task
    gdocs_complete_task(title)
    _record_deleted_task(title)
    user = _req_user(data)
    log_action(user, 'task_completed', {'title': title}, actor='user')
    return jsonify({'ok': True})


@emails_bp.route('/doc/dedup', methods=['POST'])
def dedup_tasks():
    from gdocs import dedup_tasks as gdocs_dedup
    removed = gdocs_dedup()
    return jsonify({'removed': removed})


@emails_bp.route('/emails', methods=['GET'])
def get_emails():
    from gmail_scanner import scan_emails
    from gcs import read_json, write_json
    from datetime import datetime, timedelta, timezone

    db = get_db()
    doc = db.collection('settings').document('email_filters').get()
    filters = doc.to_dict().get('addresses', []) if doc.exists else []
    print(f"[/emails] sender_filters from Firestore: {filters}")

    config = read_json('saucer-config.json', {})
    last_sync = config.get('last_sync_timestamp')

    if last_sync is None:
        after_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
    else:
        after_ts = last_sync

    kw_doc = db.collection('settings').document('keyword_filters').get()
    keywords = kw_doc.to_dict().get('keywords', []) if kw_doc.exists else []

    effective_filters = (filters + ['me']) if filters else None
    new_emails = scan_emails(
        sender_filter=effective_filters,
        keyword_filter=keywords if keywords else None,
        after_timestamp=after_ts
    )

    config['last_sync_timestamp'] = datetime.now(timezone.utc).timestamp()
    write_json('saucer-config.json', config)

    email_intent = _get_email_intent(db)
    blocked_set = _get_blocked_senders_set(db)
    permitted_list = _get_permitted_senders_list(db)
    excluded_keywords = _get_excluded_keywords(db)

    # Intent eval, PDF auto-save, and byte-strip run on new emails before upserting
    _run_intent_eval_batch(new_emails, email_intent, blocked_set, permitted_list, excluded_keywords=excluded_keywords)
    _auto_save_pdf_attachments(new_emails, db)
    _strip_raw_bytes(new_emails)
    for e in new_emails:
        email_store.upsert_email(e)

    # Generate summaries for visible emails that lack one (cap at 10 per request)
    visible_meta = email_store.list_emails(
        exclude_dismissed=True,
        exclude_reviewed=True,
        exclude_blocked_verdict=True,
        include_body=False,
    )
    to_summarize_ids = [e['id'] for e in visible_meta if _is_vague_summary(e.get('summary'))][:10]
    if to_summarize_ids:
        from email_scanner import summarize_emails
        to_summarize_with_body = email_store.get_emails_by_ids(to_summarize_ids)
        summaries = summarize_emails(to_summarize_with_body)
        if summaries:
            for eid, summary in summaries.items():
                email_store.update_email_fields(eid, {'summary': summary})

    excl_doc = db.collection('settings').document('exclude_keyword_filters').get()
    exclude_keywords = excl_doc.to_dict().get('keywords', []) if excl_doc.exists else []
    print(f"[/emails] exclude_keywords: {exclude_keywords}")

    visible = email_store.list_emails(
        exclude_dismissed=True,
        exclude_reviewed=True,
        exclude_blocked_verdict=True,
        include_body=True,
    )

    # Re-apply summaries updated above (in-memory refresh)
    if to_summarize_ids and summaries:
        for e in visible:
            if e['id'] in summaries:
                e['summary'] = summaries[e['id']]

    if exclude_keywords:
        before_count = len(visible)
        def _matches_exclude(e):
            haystack = ' '.join([
                e.get('subject', ''),
                e.get('sender', ''),
                (e.get('body', '') or e.get('snippet', ''))[:500],
            ]).lower()
            return any(kw in haystack for kw in exclude_keywords)
        visible = [e for e in visible if not _matches_exclude(e)]
        print(f"[/emails] exclude filter: {before_count} -> {len(visible)} emails")

    if blocked_set:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_set
                   and e.get('sender', '').lower() not in blocked_set]

    return jsonify({'emails': visible})


@emails_bp.route('/emails/cached', methods=['GET'])
def get_cached_emails():
    """Return stored emails from Firestore/GCS without triggering a Gmail scan."""
    db = get_db()

    excl_doc = db.collection('settings').document('exclude_keyword_filters').get()
    exclude_keywords = excl_doc.to_dict().get('keywords', []) if excl_doc.exists else []

    blocked_set = _get_blocked_senders_set(db)

    visible = email_store.list_emails(
        exclude_dismissed=True,
        exclude_reviewed=True,
        exclude_blocked_verdict=True,
        include_body=True,
    )

    if exclude_keywords:
        def _matches_exclude_cached(e):
            haystack = ' '.join([
                e.get('subject', ''),
                e.get('sender', ''),
                (e.get('body', '') or e.get('snippet', ''))[:500],
            ]).lower()
            return any(kw in haystack for kw in exclude_keywords)
        visible = [e for e in visible if not _matches_exclude_cached(e)]

    if blocked_set:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_set
                   and e.get('sender', '').lower() not in blocked_set]

    return jsonify({'emails': visible})


@emails_bp.route('/emails/resync', methods=['POST'])
def resync_emails():
    """Force a 90-day re-scan and re-evaluate all emails."""
    from gmail_scanner import scan_emails
    from gcs import read_json, write_json
    from datetime import datetime, timedelta, timezone

    db = get_db()
    doc = db.collection('settings').document('email_filters').get()
    filters = doc.to_dict().get('addresses', []) if doc.exists else []
    kw_doc = db.collection('settings').document('keyword_filters').get()
    keywords = kw_doc.to_dict().get('keywords', []) if kw_doc.exists else []

    after_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
    effective_filters = (filters + ['me']) if filters else None
    new_emails = scan_emails(
        sender_filter=effective_filters,
        keyword_filter=keywords if keywords else None,
        after_timestamp=after_ts
    )

    config = read_json('saucer-config.json', {})
    config['last_sync_timestamp'] = datetime.now(timezone.utc).timestamp()
    write_json('saucer-config.json', config)

    email_intent = _get_email_intent(db)
    blocked_set = _get_blocked_senders_set(db)
    permitted_list = _get_permitted_senders_list(db)
    excluded_keywords = _get_excluded_keywords(db)

    # Force re-evaluate all stored emails
    all_stored = email_store.list_emails(
        limit=2000,
        exclude_dismissed=False,
        exclude_reviewed=False,
        exclude_blocked_verdict=False,
        include_body=False,
    )
    # Merge new emails in-memory for batch re-eval
    merged_for_eval = new_emails + [e for e in all_stored if e['id'] not in {e2['id'] for e2 in new_emails}]
    eval_counts = _force_reevaluate_all_emails(merged_for_eval, email_intent, excluded_keywords, blocked_set, set(permitted_list))
    print(f"[resync] re-eval complete: {eval_counts}")

    _auto_save_pdf_attachments(merged_for_eval, db)
    _strip_raw_bytes(merged_for_eval)

    for e in merged_for_eval:
        email_store.upsert_email(e)

    visible = email_store.list_emails(
        exclude_dismissed=True,
        exclude_reviewed=True,
        exclude_blocked_verdict=True,
        include_body=True,
    )

    if blocked_set:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_set
                   and e.get('sender', '').lower() not in blocked_set]

    return jsonify({'emails': visible, 'synced': len(new_emails), 'eval_counts': eval_counts})


@emails_bp.route('/emails/<email_id>/dismiss', methods=['DELETE'])
def dismiss_email(email_id):
    from gcs import read_json, write_json
    dismissed = read_json('saucer-dismissed.json', [])
    if email_id not in dismissed:
        dismissed.append(email_id)
        write_json('saucer-dismissed.json', dismissed)
    email_store.update_email_fields(email_id, {'dismissed_by': 'user'})
    user = _req_user()
    log_action(user, 'email_dismissed', {'email_id': email_id}, actor='user')
    return jsonify({'ok': True})


@emails_bp.route('/emails/<email_id>/review', methods=['POST'])
def review_email(email_id):
    from gcs import read_json, write_json
    reviewed = read_json('saucer-reviewed.json', [])
    if email_id in reviewed:
        reviewed.remove(email_id)
    reviewed.insert(0, email_id)
    write_json('saucer-reviewed.json', reviewed)
    user = _req_user()
    log_action(user, 'email_reviewed', {'email_id': email_id}, actor='user')
    return jsonify({'ok': True})


@emails_bp.route('/reviewed-emails', methods=['GET'])
def get_reviewed_emails():
    from datetime import datetime, timedelta, timezone

    since_30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    actions = get_recent_actions(action_type=None, limit=200, since=since_30)

    ACTION_LABEL_MAP = {
        'email_dismissed': 'Dismissed by you',
        'email_reviewed': 'Marked reviewed',
        'email_restored': 'Restored from dismissed',
    }
    email_action_map = {}
    for a in reversed(actions):
        eid = a.get('metadata', {}).get('email_id') or a.get('email_id')
        if not eid:
            continue
        atype = a.get('action_type', '')
        if atype in ACTION_LABEL_MAP:
            email_action_map[eid] = {
                'label': ACTION_LABEL_MAP[atype],
                'timestamp': a.get('timestamp', ''),
                'actor': a.get('actor', 'user'),
            }

    action_email_ids = list(email_action_map.keys())
    fetched_emails = email_store.get_emails_by_ids(action_email_ids)
    email_map = {e['id']: e for e in fetched_emails}

    result = []
    for eid, action_info in email_action_map.items():
        if eid in email_map:
            entry = dict(email_map[eid])
            entry['_action_label'] = action_info['label']
            entry['_action_timestamp'] = action_info['timestamp']
            result.append(entry)

    result.sort(key=lambda x: x.get('_action_timestamp', ''), reverse=True)
    return jsonify({'emails': result[:60], 'window_days': 30})


@emails_bp.route('/emails/search', methods=['GET'])
def search_emails():
    from gmail_scanner import scan_emails
    from gcs import read_json
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'emails': []})
    emails = scan_emails(keyword_filter=[q])
    dismissed = set(read_json('saucer-dismissed.json', []))
    visible = [e for e in emails if e['id'] not in dismissed]
    return jsonify({'emails': visible[:20]})


@emails_bp.route('/email-intent', methods=['GET'])
def get_email_intent_route():
    db = get_db()
    return jsonify({'intent': _get_email_intent(db)})


@emails_bp.route('/email-intent', methods=['POST'])
def save_email_intent():
    from datetime import datetime, timezone
    data = request.get_json() or {}
    intent = (data.get('intent') or '').strip()
    db = get_db()
    db.collection('settings').document('email_intent').set({
        'intent': intent,
        'last_updated': datetime.now(timezone.utc).isoformat(),
    })
    user = _req_user(data)
    log_action(user, 'email_intent_saved', {'intent_length': len(intent)}, actor='user')
    return jsonify({'ok': True})


@emails_bp.route('/emails/<path:email_id>/dismiss-feedback', methods=['POST'])
def dismiss_email_with_feedback(email_id):
    from gcs import read_json, write_json
    from datetime import datetime, timezone
    data = request.get_json() or {}
    reason_type = data.get('reason_type', 'free_text')
    reason_text = data.get('reason_text', '')

    # Dismiss the email
    dismissed = read_json('saucer-dismissed.json', [])
    if email_id not in dismissed:
        dismissed.append(email_id)
        write_json('saucer-dismissed.json', dismissed)

    # Fetch metadata and mark dismissed_by='user' in Firestore
    email_meta = email_store.get_email(email_id) or {}
    if email_meta:
        email_store.update_email_fields(email_id, {'dismissed_by': 'user'})

    # Store feedback in Firestore
    db = get_db()
    db.collection('hana_filter_feedback').add({
        'email_id': email_id,
        'sender': email_meta.get('sender', ''),
        'subject': email_meta.get('subject', ''),
        'verdict_was': email_meta.get('verdict', 'uncertain'),
        'reason_type': reason_type,
        'reason_text': reason_text,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })

    # Save memory note
    try:
        from memory import save_note
        sender_display = email_meta.get('sender', 'unknown sender')
        subject_display = email_meta.get('subject', 'unknown subject')
        note_content = (
            f"Dismissed email from {sender_display} — subject: '{subject_display}'. "
            f"Reason ({reason_type}): {reason_text}"
        )
        save_note('email filtering feedback', note_content)
    except Exception as e:
        print(f"[dismiss_feedback] save_note error: {e}")

    user = _req_user(data)
    log_action(user, 'email_dismissed_with_feedback', {'email_id': email_id, 'reason_type': reason_type}, actor='user')
    return jsonify({'ok': True})


@emails_bp.route('/emails/hana-dismissed', methods=['GET'])
def get_hana_dismissed_emails():
    """Return emails Hana dismissed (dismissed_by=hana AND verdict=blocked), last 90 days, sorted by date desc."""
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    hana_dismissed = email_store.list_emails_filtered(
        verdict='blocked',
        dismissed_by='hana',
        after_date_iso=cutoff,
        limit=500,
        include_body=False,
    )
    return jsonify({'emails': [{
        'id': e['id'],
        'sender': e.get('sender', ''),
        'subject': e.get('subject', ''),
        'date': e.get('date', ''),
        'reason': e.get('verdict_reason', ''),
    } for e in hana_dismissed]})


@emails_bp.route('/emails/dismissed-review', methods=['GET'])
def get_dismissed_review():
    """Re-evaluate user-dismissed emails from last 90 days against current intent.

    Only shows emails the user explicitly dismissed (dismissed_by='user' or legacy entries
    in saucer-dismissed.json without dismissed_by='hana'). Hana-dismissed emails have their
    own endpoint: GET /emails/hana-dismissed.
    """
    from gcs import read_json
    from email_scanner import evaluate_email_intent
    from datetime import datetime, timedelta, timezone

    db = get_db()
    email_intent = _get_email_intent(db)
    blocked_set = _get_blocked_senders_set(db)
    permitted_list = _get_permitted_senders_list(db)
    excluded_keywords = _get_excluded_keywords(db)

    if not email_intent:
        return jsonify({'emails': [], 'message': 'No intent description set — add one in Email Filters to use this feature.'})

    dismissed_ids = set(read_json('saucer-dismissed.json', []))

    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    # User-dismissed only (not Hana's verdict=blocked ones); must also be in dismissed list
    candidate_metas = email_store.list_emails_filtered(
        after_date_iso=cutoff,
        dismissed_by_not='hana',
        limit=500,
        include_body=True,
    )
    candidates = [e for e in candidate_metas if e['id'] in dismissed_ids]

    results = []
    permitted_set = set(permitted_list)
    for e in candidates:
        cache_key = f"{e['id']}:{email_intent[:50]}"
        if cache_key in _dismissed_review_cache:
            verdict_info = _dismissed_review_cache[cache_key]
        else:
            verdict_info = evaluate_email_intent(e, email_intent, blocked_set, permitted_set, excluded_keywords=excluded_keywords)
            _dismissed_review_cache[cache_key] = verdict_info

        if verdict_info['verdict'] in ('permitted', 'uncertain'):
            results.append({
                'id': e['id'],
                'sender': e.get('sender', ''),
                'subject': e.get('subject', ''),
                'date': e.get('date', ''),
                'review_verdict': verdict_info['verdict'],
                'review_reason': verdict_info['reason'],
            })

    results.sort(key=lambda x: _parse_date_safe(x.get('date', '')), reverse=True)
    return jsonify({'emails': results[:50]})


@emails_bp.route('/emails/<path:email_id>/topic-phrase', methods=['GET'])
def get_email_topic_phrase(email_id):
    """Return a short noun phrase describing the main topic of an email (for dismissal UI)."""
    from email_scanner import extract_topic_noun_phrase
    email = email_store.get_email(email_id)
    if not email:
        return jsonify({'phrase': None})
    try:
        phrase = extract_topic_noun_phrase(email)
        return jsonify({'phrase': phrase})
    except Exception as e:
        print(f"[topic-phrase] error: {e}")
        return jsonify({'phrase': None})


@emails_bp.route('/emails/<path:email_id>/highlights', methods=['POST'])
def get_email_highlights(email_id):
    """Return up to 3 short phrases from the email body worth highlighting, given Hana's notes as context."""
    body_text = (request.json or {}).get('body_text', '')
    if not body_text:
        return jsonify({'highlights': []})
    try:
        from gcs import read_json
        import google.generativeai as genai
        notes_data = read_json('hana-notes.json', {})
        notes_text = notes_data.get('notes', '') if isinstance(notes_data, dict) else ''
        context_block = f"Hana's notes about this household:\n{notes_text}\n\n" if notes_text else ''
        prompt = (
            f"{context_block}"
            f"Email body:\n{body_text}\n\n"
            "Identify up to 3 short phrases (2–6 words each) in this email body that are most relevant "
            "to the household context above. Return only a JSON array of exact substrings from the email body. "
            "Example: [\"dentist appointment Thursday\", \"pick up kids\"]. "
            "Return [] if nothing stands out."
        )
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        import json as _json
        text = response.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        highlights = _json.loads(text)
        if not isinstance(highlights, list):
            highlights = []
        return jsonify({'highlights': highlights[:3]})
    except Exception as ex:
        print(f"[highlights] error: {ex}")
        return jsonify({'highlights': []})


@emails_bp.route('/emails/<path:email_id>/restore', methods=['POST'])
def restore_dismissed_email(email_id):
    """Remove an email from the dismissed list to restore it to the inbox."""
    from gcs import read_json, write_json
    dismissed = read_json('saucer-dismissed.json', [])
    if email_id in dismissed:
        dismissed.remove(email_id)
        write_json('saucer-dismissed.json', dismissed)
    # Clear dismissed_by; reset blocked verdict to uncertain so email reappears
    existing = email_store.get_email(email_id)
    if existing:
        fields = {'dismissed_by': DELETE_FIELD}
        if existing.get('verdict') == 'blocked':
            fields['verdict'] = 'uncertain'
        email_store.update_email_fields(email_id, fields)
    user = _req_user()
    log_action(user, 'email_restored', {'email_id': email_id}, actor='user')
    return jsonify({'ok': True})


@emails_bp.route('/emails/<path:email_id>/attachment-file-id', methods=['GET'])
def get_attachment_file_id(email_id):
    """Return file_id for an attachment — fetching from Gmail and saving to GCS if not yet stored."""
    import base64 as _b64
    from gcs import upload_file
    from datetime import datetime, timezone

    filename = request.args.get('filename', '')
    if not filename:
        return jsonify({'error': 'filename required'}), 400

    db = get_db()
    file_id = hashlib.md5(f"{email_id}:{filename}".encode()).hexdigest()
    doc = db.collection('hana_files').document(file_id).get()
    if doc.exists:
        return jsonify({'file_id': file_id})

    # Not in GCS yet — fetch from Gmail now.
    try:
        from gmail_scanner import _build_service, _extract_attachments
        _EXTRACTABLE_MIMES = {'application/pdf', 'image/jpeg', 'image/png', 'image/gif', 'image/webp'}

        service = None
        msg = None
        for token_key in ('GMAIL_REFRESH_TOKEN', 'GMAIL_REFRESH_TOKEN_2'):
            svc = _build_service(token_key)
            if not svc:
                continue
            try:
                msg = svc.users().messages().get(userId='me', messageId=email_id, format='full').execute()
                service = svc
                break
            except Exception:
                continue

        if not msg or not service:
            return jsonify({'error': 'Could not fetch message from Gmail'}), 404

        attachments = _extract_attachments(msg.get('payload', {}), service, 'me', email_id)
        target = next((a for a in attachments if a.get('filename') == filename), None)
        if not target or not target.get('_pdf_bytes_b64'):
            return jsonify({'error': 'Attachment not found in message'}), 404

        mime = target.get('mime', 'application/pdf')
        file_bytes = _b64.b64decode(target['_pdf_bytes_b64'])
        gcs_path = f"files/{file_id}_{filename}"
        if not upload_file(file_bytes, gcs_path, mime):
            return jsonify({'error': 'GCS upload failed'}), 500

        db.collection('hana_files').document(file_id).set({
            'file_id': file_id,
            'filename': filename,
            'source': 'email',
            'email_id': email_id,
            'uploaded_at': datetime.now(timezone.utc).isoformat(),
            'size_bytes': len(file_bytes),
            'gcs_path': gcs_path,
            'content_text': target.get('extracted_text', '')[:8000],
        })
        return jsonify({'file_id': file_id})
    except Exception as ex:
        print(f"[attachment-file-id] on-demand fetch error: {ex}")
        return jsonify({'error': str(ex)}), 500


@emails_bp.route('/avatar', methods=['POST'])
def upload_avatar_route():
    from gcs import upload_avatar as gcs_upload_avatar
    user_email = request.form.get('user') or _req_user()
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    content_type = f.content_type or 'image/jpeg'
    if content_type not in ('image/jpeg', 'image/png'):
        return jsonify({'error': 'Only JPEG or PNG accepted'}), 400
    image_bytes = f.read()
    if len(image_bytes) > 5_000_000:
        return jsonify({'error': 'Image exceeds 5 MB'}), 400
    path = gcs_upload_avatar(user_email, image_bytes, content_type)
    if not path:
        return jsonify({'error': 'Upload failed'}), 500
    return jsonify({'ok': True})


@emails_bp.route('/avatar', methods=['GET'])
def get_avatar_route():
    from gcs import get_avatar as gcs_get_avatar
    user_email = request.args.get('user', '')
    if not user_email:
        return jsonify({'error': 'Missing user'}), 400
    image_bytes, content_type = gcs_get_avatar(user_email)
    if image_bytes is None:
        return jsonify({'error': 'No avatar'}), 404
    return Response(image_bytes, status=200, mimetype=content_type or 'image/jpeg')


@emails_bp.route('/stats', methods=['GET'])
def get_stats():
    from gcs import read_json
    stats = read_json('saucer-stats.json', {})
    return jsonify({
        'lifetime_tokens': stats.get('lifetime_tokens', 0),
        'chat_messages': stats.get('chat_messages', 0),
    })


@emails_bp.route('/emails/<path:email_id>', methods=['GET'])
def get_email_by_id(email_id):
    e = email_store.get_email(email_id)
    if e:
        return jsonify({'email': e})
    return jsonify({'error': 'Not found'}), 404


@emails_bp.route('/emails/backfill-sender', methods=['POST'])
def backfill_sender():
    agent_key = os.environ.get('AGENT_KEY', '')
    provided_key = request.headers.get('X-Agent-Key', '')
    if not agent_key or provided_key != agent_key:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    sender = (data.get('sender') or '').strip().lower()
    if not sender:
        return jsonify({'error': 'Missing sender'}), 400

    print(f"[backfill-sender] starting 90-day backfill for sender={sender!r}")
    _backfill(sender_filter=[sender])
    print(f"[backfill-sender] done for sender={sender!r}")
    return jsonify({'ok': True, 'sender': sender})


@emails_bp.route('/email/<path:email_id>/excerpt', methods=['GET'])
def get_email_excerpt(email_id):
    e = email_store.get_email(email_id)
    if not e:
        return jsonify({'error': 'Not found'}), 404
    body = (e.get('body') or e.get('snippet') or '')[:2000]
    # source_spans are stored on the Firestore email doc by /emails/scan-todos.
    # Fall back to empty list if the field is not yet present.
    source_spans = e.get('source_spans') or []
    return jsonify({
        'subject': e.get('subject', ''),
        'sender': e.get('sender', ''),
        'date': e.get('date', ''),
        'body': body,
        'source_spans': source_spans,
    })


@emails_bp.route('/emails/scan-todos', methods=['POST'])
def scan_todos():
    """Scan emails for household action items.

    Accepts: { "email_ids": ["id1", "id2", ...] }
    If email_ids is empty or omitted, scans all currently visible emails (up to 20).
    Returns: { "todos": [ { "email_id", "id", "title", "notes", "date_expression", "source_spans" }, ... ] }

    Also writes source_spans to each email's Firestore doc for use by /email/<id>/excerpt.
    """
    from email_scanner import scan_emails_for_todos

    data = request.get_json(force=True) or {}
    email_ids = data.get('email_ids') or []

    if email_ids:
        emails = email_store.get_emails_by_ids(email_ids)
    else:
        emails = email_store.list_emails(
            limit=20,
            exclude_dismissed=True,
            exclude_reviewed=True,
            exclude_blocked_verdict=True,
            include_body=True,
        )

    if not emails:
        return jsonify({'todos': []})

    proposals = scan_emails_for_todos(emails)

    # Build subject lookup for the response
    subject_by_id = {e['id']: e.get('subject', '') for e in emails}

    todos = []
    for email_id, items in proposals.items():
        # Deduplicate and flatten source_spans for this email across all proposals
        all_spans = list({
            span
            for item in items
            for span in (item.get('source_spans') or [])
            if span
        })
        # Write source_spans to Firestore email doc for the excerpt route
        if all_spans:
            try:
                email_store.update_email_fields(email_id, {'source_spans': all_spans})
            except Exception as ex:
                print(f"[scan-todos] failed to write source_spans for {email_id}: {ex}")

        for item in items:
            todos.append({
                'email_id': email_id,
                'email_subject': subject_by_id.get(email_id, ''),
                'id': item.get('id', ''),
                'title': item.get('title', ''),
                'notes': item.get('notes', ''),
                'date_expression': item.get('date_expression', ''),
                'source_spans': item.get('source_spans') or [],
            })

    return jsonify({'todos': todos})


@emails_bp.route('/emails/<path:email_id>/accept-todo', methods=['POST'])
def accept_todo(email_id):
    """Accept an extracted to-do and add it to the household Google Doc.

    Accepts: { "todo_id": str, "title": str, "notes": str, "date_expression": str, "user": str }
    """
    from mediator import add_todo

    data = request.get_json(force=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'Missing title'}), 400

    notes = data.get('notes') or ''
    date_expression = data.get('date_expression') or None
    user = _req_user(data)
    assignee = data.get('assignee') or None

    result = add_todo(
        title=title,
        date_expression=date_expression,
        notes=notes,
        assignee=assignee,
        source_email_id=email_id,
        source='user-accepted-scan',
    )

    if result.get('status') == 'ok':
        log_action(user, 'task_added', {'title': title, 'source_email_id': email_id}, actor='user')

    return jsonify({'ok': True, 'result': result})


@emails_bp.route('/emails/<path:email_id>/reject-todo', methods=['POST'])
def reject_todo(email_id):
    """Reject an extracted to-do. No backend action required — frontend removes the card.

    Accepts: { "todo_id": str }
    """
    return jsonify({'ok': True})
